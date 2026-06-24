from __future__ import annotations

import argparse
import ast
import html
import io
import re
import tokenize
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from pypdf import PdfReader

from financial_engineering_common import CACHE_NAME, SLUG, extract_page_text, is_omittable_pdf_page, read_json, write_json


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / CACHE_NAME
TUTORIAL_DIR = ROOT / SLUG
ASSET_DIR = ROOT / "assets" / "img" / SLUG

BAD_VISIBLE_PATTERNS = [
    "TODO",
    "source_text",
    "TEXT_EXTRACTION_ERROR",
    "Python 转写",
    "迁移说明",
    "由于原文使用 R",
    "作为AI",
    "提示词",
    "[[CODE_PAIR",
]
SYMBOL_ARTIFACT_PATTERNS = [
    r"\b[QX]*Q\d*@@",
    r"@@\d+@@",
    r"#{8,}",
    r"\+{4,}",
    r"\?{6,}",
]
SYMBOL_ARTIFACT_PATTERNS_COMPILED = [re.compile(pattern) for pattern in SYMBOL_ARTIFACT_PATTERNS]
R_RESIDUE_PATTERNS = [
    r"\blibrary\s*\(",
    r"\brequire\s*\(",
    r"<-",
    r"%>%",
    r"\binstall\.packages\s*\(",
    r"\bggplot\s*\(",
    r"\bdata\s*\(",
    r"\bfunction\s*\(",
    r"\bsetwd\s*\(",
    r"\bqnorm\s*\(",
    r"\brnorm\s*\(",
    r"\bpnorm\s*\(",
    r"\bdnorm\s*\(",
]
R_RESIDUE_RE = re.compile("|".join(R_RESIDUE_PATTERNS))


@dataclass
class PageAudit:
    path: Path
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)


class AuditParser(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.audit = PageAudit(path)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if values.get("id"):
            self.audit.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.audit.links.append(values["href"])
        if tag == "img" and values.get("src"):
            self.audit.images.append(values["src"])


class PythonCodeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_python_code = False
        self.current: list[str] = []
        self.blocks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "code":
            return
        values = {name.lower(): value or "" for name, value in attrs}
        classes = values.get("class", "")
        if "language-python" in classes.split():
            self.in_python_code = True
            self.current = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "code" and self.in_python_code:
            self.blocks.append("".join(self.current))
            self.current = []
            self.in_python_code = False

    def handle_data(self, data: str) -> None:
        if self.in_python_code:
            self.current.append(data)


def tutorial_pages() -> list[Path]:
    if not TUTORIAL_DIR.exists():
        return []
    return sorted(TUTORIAL_DIR.glob("**/index.html"))


def parse_page(path: Path) -> PageAudit:
    parser = AuditParser(path)
    parser.feed(path.read_text(encoding="utf-8", errors="replace"))
    return parser.audit


def local_target(page_path: Path, reference: str) -> tuple[Path, str] | None:
    parsed = urlparse(reference)
    if parsed.scheme or parsed.netloc:
        return None
    if reference.startswith(("mailto:", "tel:", "javascript:")):
        return None
    raw_path = unquote(parsed.path)
    fragment = unquote(parsed.fragment)
    if not raw_path:
        return (page_path.resolve(), fragment) if fragment else None
    target = ROOT / raw_path.lstrip("/") if raw_path.startswith("/") else page_path.parent / raw_path
    if raw_path.endswith("/") or target.suffix == "":
        target = target / "index.html"
    return target.resolve(), fragment


def visible_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style|pre|code|svg|math)\b.*?</\1>", " ", raw)
    raw = re.sub(r"(?is)<!--.*?-->", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    return " ".join(raw.split())


def python_code_blocks(raw: str) -> list[str]:
    parser = PythonCodeParser()
    parser.feed(raw)
    return parser.blocks


def python_tab_r_residue_blocks(raw: str) -> list[str]:
    return [block[:500] for block in python_code_blocks(raw) if R_RESIDUE_RE.search(strip_python_comments(block))]


def strip_python_comments(block: str) -> str:
    try:
        tokens = tokenize.generate_tokens(io.StringIO(block).readline)
        return "".join(token.string for token in tokens if token.type != tokenize.COMMENT)
    except tokenize.TokenError:
        return "\n".join(line.split("#", 1)[0] for line in block.splitlines())


def python_syntax_errors(raw: str) -> list[str]:
    errors: list[str] = []
    for block in python_code_blocks(raw):
        try:
            ast.parse(block)
        except SyntaxError as exc:
            errors.append(f"line {exc.lineno}: {exc.msg}: {block[:220]}")
    return errors


def nested_code_tab_wrappers(raw: str) -> list[str]:
    if re.search(r"<pre><code\b[^>]*>\s*<div\b[^>]*class=[\"'][^\"']*\bcode-tabs\b", raw, flags=re.IGNORECASE):
        return ["pre-code-code-tabs"]
    return []


def running_header_artifacts(raw: str) -> list[str]:
    hits: list[str] = []
    for match in re.finditer(r"<(h[1-6]|p)\b[^>]*>([\s\S]*?)</\1>", raw, flags=re.IGNORECASE):
        text = html.unescape(re.sub(r"<[^>]+>", " ", match.group(2)))
        text = " ".join(text.split())
        if re.fullmatch(r"\d{1,4}\s+第\s*\d{1,2}\s*章\s+.+", text):
            hits.append(text)
        elif re.fullmatch(r"\d{1,2}\s+[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z\s：、]+", text):
            hits.append(text)
        elif re.fullmatch(r"\d{1,2}\s+[A-Z][A-Za-z0-9 ,:;'\-()]+", text):
            hits.append(text)
    return hits


def expected_pages(manifest: dict) -> list[int]:
    pages: list[int] = []
    reader = PdfReader(str(Path(manifest["book"]["source_pdf"])))
    for unit in manifest["units"]:
        for page in range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1):
            if not is_omittable_pdf_page(extract_page_text(reader, page)):
                pages.append(page)
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the Ruppert/Matteson financial engineering Chinese translation output.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if hard-fail checks are nonzero.")
    args = parser.parse_args()

    manifest = read_json(CACHE_DIR / "manifest.json")
    image_map = read_json(CACHE_DIR / "image_caption_map.json")
    pages_expected = expected_pages(manifest)
    page_dir = CACHE_DIR / "page_translations"
    missing_translated_pages = [
        page for page in pages_expected if not (page_dir / f"page-{page:03d}.json").exists()
    ]

    missing_asset_files = []
    for image in image_map.get("images", []):
        filename = Path(str(image.get("target_asset_path", ""))).name
        if filename and not (ASSET_DIR / filename).exists():
            missing_asset_files.append(filename)

    pages = tutorial_pages()
    audits = [parse_page(path) for path in pages]
    audit_by_path = {audit.path.resolve(): audit for audit in audits}
    missing_links: list[tuple[Path, str]] = []
    missing_anchors: list[tuple[Path, str]] = []
    missing_images: list[tuple[Path, str]] = []
    bad_visible_pages: list[tuple[Path, str]] = []
    symbol_artifacts: list[tuple[Path, str]] = []
    python_r_residue: list[tuple[Path, str]] = []
    python_parse_errors: list[tuple[Path, str]] = []
    nested_code_tabs: list[tuple[Path, str]] = []
    running_headers: list[tuple[Path, str]] = []

    for audit in audits:
        raw = audit.path.read_text(encoding="utf-8", errors="replace")
        text = visible_text(raw)
        for pattern in BAD_VISIBLE_PATTERNS:
            if pattern in text:
                bad_visible_pages.append((audit.path, pattern))
                break
        for pattern in SYMBOL_ARTIFACT_PATTERNS_COMPILED:
            match = pattern.search(text)
            if match:
                symbol_artifacts.append((audit.path, match.group(0)))
                break
        for block in python_tab_r_residue_blocks(raw)[:5]:
            python_r_residue.append((audit.path, block))
        for error in python_syntax_errors(raw)[:5]:
            python_parse_errors.append((audit.path, error))
        for error in nested_code_tab_wrappers(raw):
            nested_code_tabs.append((audit.path, error))
        for header in running_header_artifacts(raw):
            running_headers.append((audit.path, header))
        for href in audit.links:
            target = local_target(audit.path, href)
            if target is None:
                continue
            target_path, fragment = target
            if not target_path.exists():
                missing_links.append((audit.path, href))
            elif fragment:
                target_audit = audit_by_path.get(target_path) or parse_page(target_path)
                if fragment not in target_audit.ids:
                    missing_anchors.append((audit.path, href))
        for src in audit.images:
            target = local_target(audit.path, src)
            if target is not None and not target[0].exists():
                missing_images.append((audit.path, src))

    raw_pages = [path.read_text(encoding="utf-8", errors="replace") for path in pages]
    report = {
        "tutorial_pages": len(pages),
        "expected_translated_pages": len(pages_expected),
        "missing_translated_pages": len(missing_translated_pages),
        "image_records": len(image_map.get("images", [])),
        "missing_asset_files": len(set(missing_asset_files)),
        "code_tab_blocks": sum(raw.count('class="code-tabs"') for raw in raw_pages),
        "python_code_blocks": sum(raw.count("language-python") for raw in raw_pages),
        "r_code_blocks": sum(raw.count("language-r") for raw in raw_pages),
        "python_r_residue_blocks": len(python_r_residue),
        "python_syntax_errors": len(python_parse_errors),
        "nested_code_tab_wrappers": len(nested_code_tabs),
        "running_header_artifacts": len(running_headers),
        "missing_local_links": len(missing_links),
        "missing_local_anchors": len(missing_anchors),
        "missing_local_images": len(missing_images),
        "bad_visible_pages": len(bad_visible_pages),
        "symbol_artifact_pages": len(symbol_artifacts),
        "status": "ready",
    }
    hard_fail = any(
        [
            missing_translated_pages,
            missing_asset_files,
            missing_links,
            missing_anchors,
            missing_images,
            bad_visible_pages,
            symbol_artifacts,
            python_r_residue,
            python_parse_errors,
            nested_code_tabs,
            running_headers,
        ]
    )
    if hard_fail:
        report["status"] = "incomplete"
    write_json(CACHE_DIR / "strict_quality_report.json", report)

    print("Financial engineering translation quality report")
    for key, value in report.items():
        print(f"- {key}: {value}")

    for label, items in [
        ("Missing local link", missing_links[:10]),
        ("Missing local anchor", missing_anchors[:10]),
        ("Missing local image", missing_images[:10]),
        ("Bad visible text", bad_visible_pages[:10]),
        ("Symbol artifact", symbol_artifacts[:10]),
        ("Python tab R residue", python_r_residue[:10]),
        ("Python syntax error", python_parse_errors[:10]),
        ("Nested code tabs", nested_code_tabs[:10]),
        ("Running header artifact", running_headers[:10]),
    ]:
        for path, value in items:
            print(f"  {label}: {path.relative_to(ROOT).as_posix()} -> {value}")

    if args.strict and hard_fail:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
