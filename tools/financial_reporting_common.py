from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any

from pypdf import PdfReader


BOOK_TITLE_EN = "Financial Reporting, Financial Statement Analysis, and Valuation"
BOOK_AUTHORS = "James M. Wahlen; Stephen P. Baginski"
SLUG = "financial-reporting-statement-analysis-valuation-cn"
CACHE_NAME = "financial-reporting-wahlen"

CHAPTER_RE = re.compile(r"^(?:chapter|ch\.?)\s+(\d+)\b(?:\s*[:.\-]\s*|\s+)?(.*)$", re.IGNORECASE)
APPENDIX_RE = re.compile(r"^appendix\s+([a-z0-9]+)\b", re.IGNORECASE)
CAPTION_RE = re.compile(
    r"^(Exhibit|Figure|Fig\.|Table|Panel)\s+([0-9]+(?:[.-][0-9A-Za-z]+)*)(?:\s*[:.\-]\s*|\s+)(.+)$",
    re.IGNORECASE,
)
IMG_TAG_RE = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
SRC_ATTR_RE = re.compile(r"""\bsrc\s*=\s*(['"])(.*?)\1""", re.IGNORECASE)
PDF_RUNNING_HEADER_RE = re.compile(r"\b\d{1,4}\s+CHAPTER\s+\d+\s+[A-Z][A-Za-z,:\-\s]+(?=[\u4e00-\u9fff<])")
PUBLISHER_NOTICE_MARKERS = (
    "copyright 2023 cengage learning",
    "all rights reserved",
    "editorial review has deemed",
)

FRONT_MATTER_SLUGS = {
    "contents": "contents",
    "table of contents": "contents",
    "preface": "preface",
    "acknowledgments": "acknowledgments",
    "acknowledgements": "acknowledgments",
    "about the authors": "about-the-authors",
    "introduction": "introduction",
    "references": "references",
    "bibliography": "bibliography",
    "index": "index",
}

KNOWN_PDF_UNIT_SPECS = [
    ("summary-of-key-ratios", "front_matter", "Summary of Key Financial Statement Ratios", 2, 3),
    ("preface", "front_matter", "Preface", 6, 16),
    ("about-the-authors", "front_matter", "About the Authors", 17, 18),
    ("chapter-1", "chapter", "CHAPTER 1 Overview of Financial Reporting, Financial Statement Analysis, and Valuation", 29, 94),
    ("chapter-2", "chapter", "CHAPTER 2 Asset and Liability Valuation and Income Recognition", 95, 136),
    ("chapter-3", "chapter", "CHAPTER 3 Understanding the Statement of Cash Flows", 137, 194),
    ("chapter-4", "chapter", "CHAPTER 4 Profitability Analysis", 195, 272),
    ("chapter-5", "chapter", "CHAPTER 5 Risk Analysis", 273, 340),
    ("chapter-6", "chapter", "CHAPTER 6 Accounting Quality", 341, 418),
    ("chapter-7", "chapter", "CHAPTER 7 Financing Activities", 419, 468),
    ("chapter-8", "chapter", "CHAPTER 8 Investing Activities", 469, 536),
    ("chapter-9", "chapter", "CHAPTER 9 Operating Activities", 537, 590),
    ("chapter-10", "chapter", "CHAPTER 10 Forecasting Financial Statements", 591, 666),
    (
        "chapter-11",
        "chapter",
        "CHAPTER 11 Risk-Adjusted Expected Rates of Return and the Dividends Valuation Approach",
        667,
        706,
    ),
    ("chapter-12", "chapter", "CHAPTER 12 Valuation: Cash-Flow-Based Approaches", 707, 760),
    ("chapter-13", "chapter", "CHAPTER 13 Valuation: Earnings-Based Approach", 761, 790),
    ("chapter-14", "chapter", "CHAPTER 14 Valuation: Market-Based Approaches", 791, 832),
    ("appendix-a", "back_matter", "APPENDIX A Financial Statements and Notes for The Clorox Company", 833, 874),
    ("appendix-b", "back_matter", "APPENDIX B Management's Discussion and Analysis for The Clorox Company", 875, 876),
    ("appendix-c", "back_matter", "APPENDIX C Financial Statement Analysis Package (FSAP)", 877, 916),
    ("appendix-d", "back_matter", "APPENDIX D Financial Statement Ratios: Descriptive Statistics by Industry", 917, 918),
    ("index", "back_matter", "Index", 919, 944),
]


def clean_text(value: object) -> str:
    text = html.unescape("" if value is None else str(value))
    text = text.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text).strip()


def is_omittable_pdf_page(text: str) -> bool:
    cleaned = clean_text(text)
    if not cleaned or len(cleaned) > 900:
        return False
    lowered = cleaned.lower()
    return all(marker in lowered for marker in PUBLISHER_NOTICE_MARKERS)


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


def strip_pdf_running_headers(fragment: str) -> str:
    return PDF_RUNNING_HEADER_RE.sub("", fragment)


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def slugify_title(title: str) -> str:
    cleaned = clean_text(title)
    lower = cleaned.lower()
    if lower in FRONT_MATTER_SLUGS:
        return FRONT_MATTER_SLUGS[lower]

    chapter_match = CHAPTER_RE.match(cleaned)
    if chapter_match:
        return f"chapter-{int(chapter_match.group(1))}"

    appendix_match = APPENDIX_RE.match(cleaned)
    if appendix_match:
        return f"appendix-{appendix_match.group(1).lower()}"

    slug = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    return slug or "section"


def unit_kind(title: str) -> str:
    lower = clean_text(title).lower()
    if lower in {"contents", "table of contents"}:
        return "contents"
    if lower in {"references", "bibliography", "index"} or APPENDIX_RE.match(lower):
        return "back_matter"
    if CHAPTER_RE.match(lower):
        return "chapter"
    if lower in {"preface", "acknowledgments", "acknowledgements", "about the authors", "introduction"}:
        return "front_matter"
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
            base_slug = slugify_title(title)
            items.append(
                {
                    "id": item_id,
                    "parent_id": parent_id,
                    "level": level,
                    "title_en": title,
                    "pdf_page": page,
                    "slug": unique_slug(base_slug, seen_slugs),
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
    top_items = [
        item
        for item in outline_items
        if item.get("level") == 0 and item.get("pdf_page") and item.get("kind") != "contents"
    ]
    units: list[dict[str, Any]] = []
    for index, item in enumerate(top_items):
        next_page = top_items[index + 1]["pdf_page"] if index + 1 < len(top_items) else page_count + 1
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
            if child.get("parent_id") == item["id"]
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


def unit_from_spec(index: int, spec: tuple[str, str, str, int, int], slug: str) -> dict[str, Any]:
    unit_slug, kind, title_en, page_start, page_end = spec
    return {
        "id": f"unit-{index:03d}",
        "task_id": unit_slug,
        "kind": kind,
        "title_en": title_en,
        "title_zh": "",
        "slug": unit_slug,
        "pdf_page_start": page_start,
        "pdf_page_end": page_end,
        "source_text_file": f"source_text/{unit_slug}.txt",
        "translated_fragment_file": f"translated/{unit_slug}.html",
        "review_report_file": f"reviews/{unit_slug}.md",
        "site_output_path": f"{slug}/{unit_slug}/index.html",
        "sections": [],
        "status": "pending",
    }


def build_known_pdf_units(page_count: int, slug: str = SLUG) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for index, spec in enumerate(KNOWN_PDF_UNIT_SPECS, start=1):
        unit = unit_from_spec(index, spec, slug)
        if int(unit["pdf_page_start"]) > page_count:
            continue
        unit["pdf_page_end"] = min(int(unit["pdf_page_end"]), page_count)
        units.append(unit)
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
            match = CAPTION_RE.match(line)
            if not match:
                continue
            caption = line
            if len(caption) < 140 and index + 1 < len(lines):
                next_line = lines[index + 1]
                if not CAPTION_RE.match(next_line) and not CHAPTER_RE.match(next_line):
                    caption = f"{caption} {next_line}"
            captions.append(
                {
                    "id": f"caption-{len(captions) + 1:04d}",
                    "pdf_page": page_number,
                    "label_type": match.group(1),
                    "number": match.group(2),
                    "text_en": caption,
                    "text_zh": "",
                    "status": "pending_translation",
                }
            )
    return captions


def extract_images_with_pypdf(reader: PdfReader, image_dir: Path, slug: str = SLUG) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    image_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    unique: dict[str, dict[str, Any]] = {}

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:
            images = []
        for image_index, image_obj in enumerate(images, start=1):
            data = getattr(image_obj, "data", b"") or b""
            if not data:
                continue
            digest = hashlib.sha1(data).hexdigest()[:12]
            raw_name = getattr(image_obj, "name", "") or ""
            ext = Path(raw_name).suffix.lower().lstrip(".") or "bin"
            filename = f"image-{digest}.{ext}"
            output_path = image_dir / filename
            if digest not in unique:
                output_path.write_bytes(data)
                unique[digest] = {
                    "hash": digest,
                    "cache_file": str(output_path.relative_to(image_dir.parent)),
                    "target_asset_path": f"/assets/img/{slug}/{filename}",
                    "width_px": None,
                    "height_px": None,
                    "ext": ext,
                }
            records.append(
                {
                    "id": f"image-{len(records) + 1:04d}",
                    "pdf_page": page_number,
                    "image_index_on_page": image_index,
                    "placement_index": 1,
                    "hash": digest,
                    "cache_file": unique[digest]["cache_file"],
                    "target_asset_path": unique[digest]["target_asset_path"],
                    "width_px": None,
                    "height_px": None,
                    "bbox": None,
                    "caption_id": None,
                }
            )

    return records, {
        "image_extractor": "pypdf",
        "unique_image_files": len(unique),
        "image_placements": len(records),
    }


def attach_captions(images: list[dict[str, Any]], captions: list[dict[str, Any]]) -> None:
    captions_by_page: dict[int, list[dict[str, Any]]] = {}
    for caption in captions:
        captions_by_page.setdefault(int(caption["pdf_page"]), []).append(caption)

    cursor_by_page: dict[int, int] = {}
    for image in images:
        page = int(image["pdf_page"])
        page_captions = captions_by_page.get(page, [])
        if not page_captions:
            continue
        cursor = cursor_by_page.get(page, 0)
        if cursor >= len(page_captions):
            continue
        image["caption_id"] = page_captions[cursor]["id"]
        cursor_by_page[page] = cursor + 1


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
