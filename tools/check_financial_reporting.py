from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from pypdf import PdfReader

from financial_reporting_common import CACHE_NAME, SLUG, extract_page_text, is_omittable_pdf_page, read_json, write_json


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / CACHE_NAME
TUTORIAL_DIR = ROOT / SLUG
ASSET_DIR = ROOT / "assets" / "img" / SLUG

BAD_VISIBLE_PATTERNS = [
    "TODO",
    "原文：",
    "翻译说明",
    "译者注",
    "作为AI",
    "提示词",
    "Markdown fence",
    "source_text",
    "TEXT_EXTRACTION_ERROR",
]

SYMBOL_ARTIFACT_PATTERNS = [
    r"\b[QX]*Q\d*@@",
    r"@@\d+@@",
    r"#{8,}",
    r"\+{4,}",
    r"锟",
    r"\\{3,}",
    r"\?{6,}",
]
SYMBOL_ARTIFACT_PATTERNS_COMPILED = [re.compile(pattern) for pattern in SYMBOL_ARTIFACT_PATTERNS]

REFERENCE_MARKERS = [
    "journal of",
    "working paper",
    "accounting research",
    "accounting review",
    "contemporary accounting research",
    "review of accounting studies",
    "journal of accounting",
    "journal of business",
    "issues in accounting education",
    "financial accounting standards board",
    "fasb",
    "international accounting standard",
    "international financial reporting standard",
    "accounting standards update",
    "工作论文",
    "未发表手稿",
]


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


def expected_pages(manifest: dict) -> list[int]:
    pages: list[int] = []
    reader = PdfReader(str(Path(manifest["book"]["source_pdf"])))
    for unit in manifest["units"]:
        for page in range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1):
            if not is_omittable_pdf_page(extract_page_text(reader, page)):
                pages.append(page)
    return pages


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


def is_allowed_english_block(block: str) -> bool:
    lower = block.lower()
    if any(marker in lower for marker in REFERENCE_MARKERS):
        return True
    if "&nbsp;" in block and len(re.findall(r"[\u4e00-\u9fff]", block)) >= 10:
        return True
    if re.search(r"\bEBIT(?:DA|DAR)?\b\s*=", block):
        return True
    if re.search(r"\b(pp?|nos?|vol|supplement)\.\s*\d", lower) and re.search(r"\b(19|20)\d{2}\b", lower):
        return True
    cjk = len(re.findall(r"[\u4e00-\u9fff]", block))
    has_proper_name = re.search(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,}\b", block)
    sentence_words = re.search(
        r"\b(should|suppose|describe|explain|compute|project|chapter|firm)\b",
        lower,
    )
    return bool(cjk >= 20 and has_proper_name and not sentence_words)


def english_leak_blocks(raw: str) -> list[str]:
    text = visible_text(raw)
    blocks = re.split(r"(?<=[。！？.!?])\s+|(?=<h[1-4]\b)", text)
    leaks: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        without_urls = re.sub(r"https?://\S+", " ", block)
        if is_allowed_english_block(without_urls):
            continue
        latin = len(re.findall(r"[A-Za-z]", without_urls))
        cjk = len(re.findall(r"[\u4e00-\u9fff]", without_urls))
        if re.search(r"\b(CHAPTER|Exercise|Problem|Case|EXHIBIT|TABLE|Learning Objectives)\b", without_urls):
            leaks.append(block[:220])
        elif latin >= 120 and (cjk < 30 or latin > cjk * 2):
            leaks.append(block[:220])
    return leaks


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the Wahlen financial reporting Chinese translation output.")
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
    missing_links: list[tuple[Path, str]] = []
    missing_anchors: list[tuple[Path, str]] = []
    missing_images: list[tuple[Path, str]] = []
    bad_visible_pages: list[tuple[Path, str]] = []
    symbol_artifacts: list[tuple[Path, str]] = []
    english_leaks: list[tuple[Path, str]] = []

    audit_by_path = {audit.path.resolve(): audit for audit in audits}
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
        if audit.path.parent.name != "index":
            for block in english_leak_blocks(raw)[:5]:
                english_leaks.append((audit.path, block))
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

    report = {
        "tutorial_pages": len(pages),
        "expected_translated_pages": len(pages_expected),
        "missing_translated_pages": len(missing_translated_pages),
        "image_records": len(image_map.get("images", [])),
        "missing_asset_files": len(set(missing_asset_files)),
        "missing_local_links": len(missing_links),
        "missing_local_anchors": len(missing_anchors),
        "missing_local_images": len(missing_images),
        "bad_visible_pages": len(bad_visible_pages),
        "symbol_artifact_pages": len(symbol_artifacts),
        "english_leak_blocks": len(english_leaks),
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
            english_leaks,
        ]
    )
    if hard_fail:
        report["status"] = "incomplete"
    write_json(CACHE_DIR / "strict_quality_report.json", report)

    print("Financial reporting translation quality report")
    for key, value in report.items():
        print(f"- {key}: {value}")

    for label, items in [
        ("Missing local link", missing_links[:10]),
        ("Missing local anchor", missing_anchors[:10]),
        ("Missing local image", missing_images[:10]),
        ("Bad visible text", bad_visible_pages[:10]),
        ("Symbol artifact", symbol_artifacts[:10]),
        ("English leak", english_leaks[:10]),
    ]:
        for path, value in items:
            print(f"  {label}: {path.relative_to(ROOT).as_posix()} -> {value}")

    if args.strict and hard_fail:
        raise SystemExit(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
