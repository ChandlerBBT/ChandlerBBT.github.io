from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader


BOOK_TITLE_EN = "Statistics and Data Analysis for Financial Engineering: with R examples"
BOOK_AUTHORS = "David Ruppert; David S. Matteson"
BOOK_EDITION = "Second Edition"
SLUG = "statistics-data-analysis-financial-engineering-cn"
CACHE_NAME = "sdaf-ruppert"

NUMBERED_CHAPTER_RE = re.compile(r"^(\d{1,2})\s+(.+)$")
APPENDIX_RE = re.compile(r"^([A-Z])\s+(.+)$")
SECTION_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+(.+)$")
FIGURE_CAPTION_RE = re.compile(
    r"^(Fig\.)\s+([0-9]+(?:[.-][0-9A-Za-z]+)*)(?:\.|\s+)(.*)$",
    re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    r"^(Table)\s+([0-9]+(?:[.-][0-9A-Za-z]+)*)(?:\.|\s+)(.*)$",
    re.IGNORECASE,
)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)
CODE_PAIR_PLACEHOLDER_RE = re.compile(r"\[\[CODE_PAIR:([A-Za-z0-9_.:-]+)\]\]")
PUBLISHER_NOTICE_MARKERS = (
    "springer science+business media",
    "statistics and data analysis for financial engineering",
    "doi 10.1007",
)

FRONT_MATTER_SLUGS = {
    "preface": "preface",
    "preface to the first edition": "preface-first-edition",
    "contents": "contents",
    "table of contents": "contents",
    "notation": "notation",
    "references": "references",
    "index": "index",
}


def clean_text(value: object) -> str:
    text = html.unescape("" if value is None else str(value))
    text = text.replace("\u00a0", " ")
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")
    text = text.replace("\ufb01", "fi").replace("\ufb02", "fl")
    return re.sub(r"\s+", " ", text).strip()


def is_omittable_pdf_page(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned:
        return True
    if len(cleaned) > 900:
        return False
    lowered = cleaned.lower()
    return all(marker in lowered for marker in PUBLISHER_NOTICE_MARKERS)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def slugify_words(value: str) -> str:
    value = clean_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value or "section"


def slugify_title(title: str) -> str:
    cleaned = clean_text(title)
    lower = cleaned.lower()
    if lower in FRONT_MATTER_SLUGS:
        return FRONT_MATTER_SLUGS[lower]

    chapter_match = NUMBERED_CHAPTER_RE.match(cleaned)
    if chapter_match:
        return f"chapter-{int(chapter_match.group(1))}"

    appendix_match = APPENDIX_RE.match(cleaned)
    if appendix_match and appendix_match.group(1) != "I":
        return f"appendix-{appendix_match.group(1).lower()}"

    section_match = SECTION_RE.match(cleaned)
    if section_match:
        return "section-" + section_match.group(1).replace(".", "-")

    return slugify_words(cleaned)


def unit_kind(title: str) -> str:
    cleaned = clean_text(title)
    lower = cleaned.lower()
    if lower in {"contents", "table of contents"}:
        return "contents"
    if lower == "index" or APPENDIX_RE.match(cleaned):
        return "back_matter"
    if lower.startswith("preface") or lower == "notation":
        return "front_matter"
    if NUMBERED_CHAPTER_RE.match(cleaned):
        return "chapter"
    return "section"


def unique_slug(base: str, seen: set[str]) -> str:
    if base not in seen:
        seen.add(base)
        return base
    index = 2
    while f"{base}-{index}" in seen:
        index += 1
    value = f"{base}-{index}"
    seen.add(value)
    return value


def flatten_outline(reader: PdfReader) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen_slugs: set[str] = set()

    def walk(outline: list[Any], level: int = 0, parent_id: str | None = None) -> None:
        last_id = parent_id
        for item in outline:
            if isinstance(item, list):
                walk(item, level + 1, last_id)
                continue

            item_id = f"outline-{len(items) + 1:04d}"
            try:
                page = reader.get_destination_page_number(item) + 1
            except Exception:
                page = None
            title = clean_text(getattr(item, "title", str(item)))
            items.append(
                {
                    "id": item_id,
                    "parent_id": parent_id,
                    "level": level,
                    "title_en": title,
                    "pdf_page": page,
                    "slug": unique_slug(slugify_title(title), seen_slugs),
                    "kind": unit_kind(title),
                }
            )
            last_id = item_id

    try:
        walk(reader.outline)
    except Exception as exc:
        print(f"Warning: outline extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return items


def build_units(outline_items: list[dict[str, Any]], page_count: int, slug: str = SLUG) -> list[dict[str, Any]]:
    top_items = [item for item in outline_items if item.get("level") == 0 and item.get("pdf_page")]
    units: list[dict[str, Any]] = []
    for index, item in enumerate(top_items):
        next_page = top_items[index + 1]["pdf_page"] if index + 1 < len(top_items) else page_count + 1
        if item.get("kind") == "contents":
            continue
        start = int(item["pdf_page"])
        end = max(start, int(next_page) - 1)
        child_sections = [
            {
                "title_en": child["title_en"],
                "pdf_page": child["pdf_page"],
                "slug": child["slug"],
                "level": child["level"],
            }
            for child in outline_items
            if child.get("parent_id") == item["id"] and child.get("pdf_page")
        ]
        unit_slug = str(item["slug"])
        units.append(
            {
                "id": f"unit-{len(units) + 1:03d}",
                "task_id": unit_slug,
                "kind": item["kind"],
                "title_en": item["title_en"],
                "title_zh": "",
                "slug": unit_slug,
                "pdf_page_start": start,
                "pdf_page_end": end,
                "source_text_file": f"source_text/{unit_slug}.txt",
                "translated_fragment_file": f"translated/{unit_slug}.html",
                "review_report_file": f"reviews/{unit_slug}.md",
                "site_output_path": f"{slug}/{unit_slug}/index.html",
                "sections": child_sections,
                "status": "pending",
            }
        )
    return units


def extract_page_text(reader: PdfReader, page_number: int) -> str:
    try:
        return reader.pages[page_number - 1].extract_text() or ""
    except Exception as exc:
        return f"[TEXT_EXTRACTION_ERROR page={page_number} error={type(exc).__name__}: {exc}]"


def find_captions(reader: PdfReader, page_count: int) -> list[dict[str, Any]]:
    captions: list[dict[str, Any]] = []
    for page_number in range(1, page_count + 1):
        text = extract_page_text(reader, page_number)
        lines = [clean_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        for index, line in enumerate(lines):
            match = FIGURE_CAPTION_RE.match(line) or TABLE_CAPTION_RE.match(line)
            if not match:
                continue
            caption = line
            if len(caption) < 180 and index + 1 < len(lines):
                next_line = lines[index + 1]
                if not (FIGURE_CAPTION_RE.match(next_line) or TABLE_CAPTION_RE.match(next_line)):
                    caption = f"{caption} {next_line}"
            captions.append(
                {
                    "id": f"caption-{len(captions) + 1:04d}",
                    "pdf_page": page_number,
                    "label_type": "figure" if match.group(1).lower().startswith(("fig", "figure")) else "table",
                    "number": match.group(2),
                    "text_en": caption,
                    "text_zh": "",
                    "status": "pending_translation",
                }
            )
    return captions


def render_code_pair(code_id: str, r_code: str, python_code: str) -> str:
    safe_id = re.sub(r"[^A-Za-z0-9_-]+", "-", code_id).strip("-") or "code"
    r_panel = f"{safe_id}-r"
    py_panel = f"{safe_id}-python"
    return f"""
<div class="code-tabs" data-code-tabs id="{html.escape(safe_id, quote=True)}">
  <div class="code-tab-list" role="tablist" aria-label="Code language">
    <button type="button" class="code-tab is-active" role="tab" aria-selected="true" aria-controls="{html.escape(r_panel, quote=True)}">R</button>
    <button type="button" class="code-tab" role="tab" aria-selected="false" aria-controls="{html.escape(py_panel, quote=True)}">Python</button>
  </div>
  <div class="code-tab-panel is-active" id="{html.escape(r_panel, quote=True)}" role="tabpanel">
    <pre><code class="language-r">{html.escape(r_code.rstrip())}</code></pre>
  </div>
  <div class="code-tab-panel" id="{html.escape(py_panel, quote=True)}" role="tabpanel" hidden>
    <pre><code class="language-python">{html.escape(python_code.rstrip())}</code></pre>
  </div>
</div>""".strip()


def replace_code_pair_placeholders(fragment: str, code_pairs: list[dict[str, Any]]) -> str:
    by_id = {
        str(item.get("id", "")).strip(): render_code_pair(
            str(item.get("id", "")).strip(),
            str(item.get("r_code", "")).strip(),
            str(item.get("python_code", "")).strip(),
        )
        for item in code_pairs
        if str(item.get("id", "")).strip()
    }

    def replace(match: re.Match[str]) -> str:
        return by_id.get(match.group(1), "")

    return CODE_PAIR_PLACEHOLDER_RE.sub(replace, fragment)


def strip_unapproved_img_tags(fragment: str, allowed_src_prefixes: tuple[str, ...]) -> str:
    def replace(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = SRC_ATTR_RE.search(tag)
        if not src_match:
            return ""
        src = src_match.group(2)
        if any(src.startswith(prefix) for prefix in allowed_src_prefixes):
            return tag
        return ""

    return IMG_TAG_RE.sub(replace, fragment)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def strip_json_fence(content: str) -> str:
    content = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, flags=re.DOTALL)
    return fenced.group(1).strip() if fenced else content
