from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Comment

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
TUTORIAL_DIR = ROOT / "bayes-rules-python-cn"
ASSET_DIR = ROOT / "assets" / "img" / "bayes-rules-python-cn"

BAD_NOTE_PATTERNS = [
    "Python ***",
    "sikit-learn",
    "NumPy-pandas",
    "原始内容存档于2018-09-25",
    "Python 转写",
    "R 代码",
    "R 包",
    "R包",
    "rstan",
    "rstanarm",
    "原教程",
    "原书",
]

BAD_NOTE_REGEX_PATTERNS = [
    r"\brstan\b",
    r"\brstanarm\b",
]

SYMBOL_ARTIFACT_PATTERNS = [
    r"\b[QX]*Q\d*@@",
    r"@@\d+@@",
    r"\d+@@",
    r"�",
    r"\\\\[()\[\]]",
    r"\\\\{3,}",
    r"#{8,}",
    r"\+{2,}\d*\+*",
    r"校对:Soup",
]

MACHINE_TRANSLATION_PATTERNS = [
    "常数正常化",
    "可能性函数",
    "后部",
    "前一个概率",
    "酒吧图",
    "感叹点",
]

R_CODE_PATTERNS = [
    r"\blibrary\s*\(",
    r"\binstall\.packages\s*\(",
    r"%>%",
    r"\bggplot\s*\(",
    r"\bstan_glm\s*\(",
]


@dataclass
class CodeBlock:
    text: str
    classes: str = ""


@dataclass
class PageAudit:
    path: Path
    links: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    ids: set[str] = field(default_factory=set)
    code_blocks: list[CodeBlock] = field(default_factory=list)


class AuditParser(HTMLParser):
    def __init__(self, path: Path) -> None:
        super().__init__(convert_charrefs=True)
        self.audit = PageAudit(path)
        self._code_parts: list[str] | None = None
        self._code_classes = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {name.lower(): value or "" for name, value in attrs}
        if "id" in values and values["id"]:
            self.audit.ids.add(values["id"])
        if tag == "a" and values.get("href"):
            self.audit.links.append(values["href"])
        elif tag == "img" and values.get("src"):
            self.audit.images.append(values["src"])
        elif tag == "code":
            self._code_parts = []
            self._code_classes = values.get("class", "")

    def handle_data(self, data: str) -> None:
        if self._code_parts is not None:
            self._code_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "code" and self._code_parts is not None:
            self.audit.code_blocks.append(CodeBlock("".join(self._code_parts), self._code_classes))
            self._code_parts = None
            self._code_classes = ""


def tutorial_pages() -> list[Path]:
    return sorted(TUTORIAL_DIR.glob("**/index.html"))


def parse_page(path: Path) -> PageAudit:
    parser = AuditParser(path)
    parser.feed(path.read_text(encoding="utf-8"))
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
    soup = BeautifulSoup(raw, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.find_all(["script", "style", "pre", "code", "math", "svg"]):
        tag.decompose()
    return soup.get_text("\n", strip=True)


def strip_latex_fragments(text: str) -> str:
    text = re.sub(r"\\\[(.*?)\\\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{equation\*?\}(.*?)\\end\{equation\*?\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\begin\{split\}(.*?)\\end\{split\}", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\\((.*?)\\\)", " ", text, flags=re.DOTALL)
    return " ".join(text.split())


def visible_blocks(raw: str) -> list[str]:
    soup = BeautifulSoup(raw, "html.parser")
    for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for tag in soup.find_all(["script", "style", "pre", "code", "math", "svg"]):
        tag.decompose()
    blocks: list[str] = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "p", "li", "caption", "blockquote"]):
        text = " ".join(tag.get_text(" ", strip=True).split())
        text = strip_latex_fragments(text)
        if text:
            blocks.append(text)
    for tag in soup.select("div.exercise, span.exercise"):
        text = " ".join(tag.get_text(" ", strip=True).split())
        text = strip_latex_fragments(text)
        if text:
            blocks.append(text)
    return blocks


def english_leak_blocks(raw: str) -> list[str]:
    leaks: list[str] = []
    for block in visible_blocks(raw):
        without_urls = re.sub(r"https?://\S+", " ", block)
        if not without_urls.replace("↩︎", "").strip():
            continue
        if without_urls.startswith("他的家人"):
            continue
        latin = len(re.findall(r"[A-Za-z]", without_urls))
        cjk = len(re.findall(r"[\u4e00-\u9fff]", without_urls))
        if re.search(r"\b(Exercise|FIGURE|TABLE|Chapter|Section)\b", without_urls):
            leaks.append(block)
            continue
        if latin >= 80 and (cjk < 20 or latin > cjk * 2):
            leaks.append(block)
    return leaks


def has_bad_note_text(text: str) -> bool:
    if any(pattern in text for pattern in BAD_NOTE_PATTERNS if pattern not in {"rstan", "rstanarm"}):
        return True
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in BAD_NOTE_REGEX_PATTERNS)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the Bayes Rules Chinese Python tutorial output.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero for missing local files or bad generated note text.")
    parser.add_argument("--page", help="Relative tutorial page, for example chapter-2/index.html.")
    args = parser.parse_args()

    pages = [TUTORIAL_DIR / args.page] if args.page else tutorial_pages()
    audits = [parse_page(path) for path in pages]

    missing_links: list[tuple[Path, str]] = []
    missing_images: list[tuple[Path, str]] = []
    missing_anchors: list[tuple[Path, str]] = []
    bad_note_pages: list[Path] = []
    symbol_artifacts: list[tuple[Path, str]] = []
    machine_translation_hits: list[tuple[Path, str]] = []
    english_leaks: list[tuple[Path, str]] = []
    todo_count = 0
    residual_r_blocks: list[tuple[Path, int]] = []

    for audit in audits:
        raw = audit.path.read_text(encoding="utf-8")
        text = visible_text(raw)
        todo_count += raw.count("TODO:")
        code_text = "\n".join(block.text for block in audit.code_blocks)
        if has_bad_note_text(text + "\n" + code_text):
            bad_note_pages.append(audit.path)
        for pattern in SYMBOL_ARTIFACT_PATTERNS:
            match = re.search(pattern, text)
            if match:
                symbol_artifacts.append((audit.path, match.group(0)))
        for pattern in MACHINE_TRANSLATION_PATTERNS:
            if pattern in text:
                machine_translation_hits.append((audit.path, pattern))
        for block in english_leak_blocks(raw)[:5]:
            english_leaks.append((audit.path, block[:180]))

        for href in audit.links:
            target = local_target(audit.path, href)
            if target is None:
                continue
            target_path, fragment = target
            if not target_path.exists():
                missing_links.append((audit.path, href))
            elif fragment and fragment not in parse_page(target_path).ids:
                missing_anchors.append((audit.path, href))
        for src in audit.images:
            target = local_target(audit.path, src)
            if target is not None and not target[0].exists():
                missing_images.append((audit.path, src))

        for index, block in enumerate(audit.code_blocks, start=1):
            if any(re.search(pattern, block.text) for pattern in R_CODE_PATTERNS):
                residual_r_blocks.append((audit.path, index))

    all_code_blocks = [block for audit in audits for block in audit.code_blocks]
    python_blocks = [block for block in all_code_blocks if "language-python" in block.classes]
    referenced_images = sum(len(audit.images) for audit in audits)

    print("Bayes Rules tutorial quality report")
    print(f"- Tutorial pages: {len(pages)}")
    print(f"- Localized image files: {len(list(ASSET_DIR.glob('*')))}")
    print(f"- Referenced images: {referenced_images}")
    print(f"- Code blocks: {len(all_code_blocks)}")
    print(f"- Python code blocks: {len(python_blocks)}")
    print(f"- Code TODO markers: {todo_count}")
    print(f"- Residual R-looking code blocks: {len(residual_r_blocks)}")
    print(f"- Bad migration-note pages: {len(bad_note_pages)}")
    print(f"- Symbol artifact pages: {len(symbol_artifacts)}")
    print(f"- Machine-translation phrase hits: {len(machine_translation_hits)}")
    print(f"- English leak blocks: {len(english_leaks)}")
    print(f"- Missing local links: {len(missing_links)}")
    print(f"- Missing local anchors: {len(missing_anchors)}")
    print(f"- Missing local images: {len(missing_images)}")

    for label, items in [
        ("Missing local link", missing_links[:10]),
        ("Missing local anchor", missing_anchors[:10]),
        ("Missing local image", missing_images[:10]),
        ("Symbol artifact", symbol_artifacts[:10]),
        ("Machine translation phrase", machine_translation_hits[:10]),
        ("English leak", english_leaks[:10]),
    ]:
        for path, value in items:
            rel = path.relative_to(ROOT).as_posix()
            print(f"  {label}: {rel} -> {value}")

    if args.strict and (
        bad_note_pages
        or missing_links
        or missing_anchors
        or missing_images
        or symbol_artifacts
        or residual_r_blocks
        or todo_count
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
