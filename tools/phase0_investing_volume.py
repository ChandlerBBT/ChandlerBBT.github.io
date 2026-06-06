from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import sys
from pathlib import Path

try:
    from pypdf import PdfReader
except Exception as exc:  # pragma: no cover - environment guard
    raise SystemExit(f"pypdf is required: {exc}") from exc


DEFAULT_PDF = Path(
    r"C:\Users\Chandler\Downloads\Buff Pelz Dormeier - Investing with Volume Analysis_ Identify, Follow, and Profit from Trends (2011, FT Press) - libgen.li.pdf"
)
SLUG = "investing-with-volume-analysis-cn"
CACHE_NAME = "investing-volume-analysis"


CAPTION_RE = re.compile(
    r"^(Figure|Fig\.|Exhibit|Table)\s+([0-9]+(?:\.[0-9]+)*)(?:\s*[:.\-]\s*|\s+)(.+)$",
    re.IGNORECASE,
)
CHAPTER_RE = re.compile(r"^Chapter\s+(\d+)\s*:\s*(.+)$", re.IGNORECASE)


def clean_text(value: object) -> str:
    text = html.unescape("" if value is None else str(value))
    return re.sub(r"\s+", " ", text).strip()


def slugify_title(title: str) -> str:
    lower = clean_text(title).lower()
    chapter_match = CHAPTER_RE.match(lower)
    if chapter_match:
        return f"chapter-{int(chapter_match.group(1))}"
    if lower in {"introduction", "contents", "index", "bibliography", "references"}:
        return lower
    cleaned = re.sub(r"[^a-z0-9]+", "-", lower).strip("-")
    return cleaned or "section"


def unit_kind(title: str) -> str:
    lower = clean_text(title).lower()
    if lower == "introduction":
        return "introduction"
    if CHAPTER_RE.match(lower):
        return "chapter"
    if lower in {"index", "bibliography", "references"}:
        return "back_matter"
    if lower == "contents":
        return "contents"
    return "front_or_back_matter"


def flatten_outline(reader: PdfReader) -> list[dict]:
    items: list[dict] = []

    def walk(outline: list, level: int = 0, parent_id: str | None = None) -> None:
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
                    "slug": slugify_title(title),
                    "kind": unit_kind(title),
                }
            )
            last_id = item_id

    try:
        walk(reader.outline)
    except Exception as exc:
        print(f"Warning: outline extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    return items


def build_units(outline_items: list[dict], page_count: int) -> list[dict]:
    top_items = [
        item
        for item in outline_items
        if item["level"] == 0 and item["pdf_page"] and item["kind"] != "contents"
    ]
    units: list[dict] = []
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
        units.append(
            {
                "id": f"unit-{len(units) + 1:03d}",
                "task_id": item["slug"],
                "kind": item["kind"],
                "title_en": item["title_en"],
                "title_zh": "",
                "slug": item["slug"],
                "pdf_page_start": start,
                "pdf_page_end": end,
                "source_text_file": f"source_text/{item['slug']}.txt",
                "translated_fragment_file": f"translated/{item['slug']}.html",
                "review_report_file": f"reviews/{item['slug']}.md",
                "site_output_path": f"{SLUG}/{item['slug']}/index.html",
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


def write_source_texts(reader: PdfReader, units: list[dict], source_dir: Path, full_book_path: Path) -> dict:
    source_dir.mkdir(parents=True, exist_ok=True)
    total_chars = 0
    empty_pages: list[int] = []

    with full_book_path.open("w", encoding="utf-8", newline="\n") as full_book:
        full_book.write("# Full-book text extraction for DeepSeek guide\n\n")
        full_book.write("Source: Investing with Volume Analysis, Buff Pelz Dormeier\n\n")
        for unit in units:
            parts = [
                f"# {unit['title_en']}\n",
                f"<!-- pdf_pages: {unit['pdf_page_start']}-{unit['pdf_page_end']} -->\n",
            ]
            for page_number in range(unit["pdf_page_start"], unit["pdf_page_end"] + 1):
                page_text = extract_page_text(reader, page_number)
                if not page_text.strip():
                    empty_pages.append(page_number)
                parts.append(f"\n\n<!-- pdf_page: {page_number} -->\n\n{page_text.strip()}\n")
            text = "\n".join(parts)
            total_chars += len(text)
            (source_dir / f"{unit['slug']}.txt").write_text(text, encoding="utf-8", newline="\n")
            full_book.write(text)
            full_book.write("\n\n")

    return {
        "source_text_chars": total_chars,
        "empty_text_pages": sorted(set(empty_pages)),
    }


def find_captions(reader: PdfReader, page_count: int) -> list[dict]:
    captions: list[dict] = []
    for page_number in range(1, page_count + 1):
        text = extract_page_text(reader, page_number)
        lines = [clean_text(line) for line in text.splitlines()]
        lines = [line for line in lines if line]
        for idx, line in enumerate(lines):
            match = CAPTION_RE.match(line)
            if not match:
                continue
            caption = line
            if len(caption) < 120 and idx + 1 < len(lines):
                next_line = lines[idx + 1]
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


def extract_images_with_fitz(pdf_path: Path, image_dir: Path, slug: str) -> tuple[list[dict], dict]:
    import fitz  # type: ignore

    image_dir.mkdir(parents=True, exist_ok=True)
    doc = fitz.open(str(pdf_path))
    records: list[dict] = []
    unique: dict[str, dict] = {}

    for page_index in range(len(doc)):
        page = doc[page_index]
        page_number = page_index + 1
        for image_on_page_index, image_ref in enumerate(page.get_images(full=True), start=1):
            xref = image_ref[0]
            extracted = doc.extract_image(xref)
            data = extracted.get("image", b"")
            if not data:
                continue
            digest = hashlib.sha1(data).hexdigest()[:12]
            ext = (extracted.get("ext") or "bin").lower()
            filename = f"image-{digest}.{ext}"
            output_path = image_dir / filename
            if digest not in unique:
                output_path.write_bytes(data)
                unique[digest] = {
                    "hash": digest,
                    "cache_file": str(output_path.relative_to(image_dir.parent)),
                    "target_asset_path": f"/assets/img/{slug}/{filename}",
                    "width_px": extracted.get("width"),
                    "height_px": extracted.get("height"),
                    "ext": ext,
                }

            rects = page.get_image_rects(xref)
            if not rects:
                rects = [None]
            for rect_index, rect in enumerate(rects, start=1):
                bbox = None
                if rect is not None:
                    bbox = [round(rect.x0, 2), round(rect.y0, 2), round(rect.x1, 2), round(rect.y1, 2)]
                records.append(
                    {
                        "id": f"image-{len(records) + 1:04d}",
                        "pdf_page": page_number,
                        "image_index_on_page": image_on_page_index,
                        "placement_index": rect_index,
                        "xref": xref,
                        "hash": digest,
                        "cache_file": unique[digest]["cache_file"],
                        "target_asset_path": unique[digest]["target_asset_path"],
                        "width_px": unique[digest]["width_px"],
                        "height_px": unique[digest]["height_px"],
                        "bbox": bbox,
                        "caption_id": None,
                    }
                )

    doc.close()
    stats = {
        "image_extractor": "pymupdf",
        "unique_image_files": len(unique),
        "image_placements": len(records),
    }
    return records, stats


def extract_images_with_pypdf(reader: PdfReader, image_dir: Path, slug: str) -> tuple[list[dict], dict]:
    image_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    unique: dict[str, dict] = {}

    for page_number, page in enumerate(reader.pages, start=1):
        try:
            images = list(page.images)
        except Exception:
            images = []
        for image_on_page_index, image_obj in enumerate(images, start=1):
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
                    "image_index_on_page": image_on_page_index,
                    "placement_index": 1,
                    "xref": None,
                    "hash": digest,
                    "cache_file": unique[digest]["cache_file"],
                    "target_asset_path": unique[digest]["target_asset_path"],
                    "width_px": None,
                    "height_px": None,
                    "bbox": None,
                    "caption_id": None,
                }
            )

    stats = {
        "image_extractor": "pypdf",
        "unique_image_files": len(unique),
        "image_placements": len(records),
    }
    return records, stats


def extract_images(pdf_path: Path, reader: PdfReader, image_dir: Path, slug: str) -> tuple[list[dict], dict]:
    try:
        return extract_images_with_fitz(pdf_path, image_dir, slug)
    except Exception as exc:
        print(f"Warning: PyMuPDF image extraction unavailable, using pypdf fallback: {exc}", file=sys.stderr)
        return extract_images_with_pypdf(reader, image_dir, slug)


def attach_captions(images: list[dict], captions: list[dict]) -> None:
    captions_by_page: dict[int, list[dict]] = {}
    for caption in captions:
        captions_by_page.setdefault(int(caption["pdf_page"]), []).append(caption)
    cursor_by_page: dict[int, int] = {}
    for image in images:
        page = int(image["pdf_page"])
        page_captions = captions_by_page.get(page, [])
        if not page_captions:
            continue
        cursor = cursor_by_page.get(page, 0)
        caption = page_captions[min(cursor, len(page_captions) - 1)]
        image["caption_id"] = caption["id"]
        cursor_by_page[page] = cursor + 1


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_terminology_seed(path: Path) -> None:
    path.write_text(
        """# Investing with Volume Analysis terminology seed

Use this as a seed only. DeepSeek should expand it after reading the full extraction.

| English | Preferred Simplified Chinese | Notes |
|---|---|---|
| volume | 成交量 | Use consistently for trading volume. |
| volume analysis | 成交量分析 | Book-level core term. |
| technical analysis | 技术分析 | Standard investment term. |
| fundamental analysis | 基本面分析 | Avoid literal "基础分析". |
| price analysis | 价格分析 | Use in contrast with volume analysis. |
| price action | 价格行为 | If paired with volume, consider 价量行为. |
| price-volume relationship | 价量关系 | Core technical-analysis phrase. |
| support and resistance | 支撑与阻力 | Standard chart-analysis term. |
| trend line | 趋势线 | Standard chart-analysis term. |
| breakout | 突破 | Use 突破走势/突破形态 when needed. |
| accumulation | 吸筹 | If indicator name requires, keep bilingual first mention. |
| distribution | 派发 | If indicator name requires, keep bilingual first mention. |
| liquidity | 流动性 | Market liquidity. |
| market breadth | 市场广度 | Standard term. |
| Dow Theory | 道氏理论 | Preserve Dow as proper noun. |
| tape reading | 读盘 | 可在首次出现时写作“读盘（tape reading）”。 |
| on-balance volume | 能量潮（OBV） | Keep OBV. |
| accumulation/distribution line | 累积/派发线 | Keep indicator name stable. |
| money flow | 资金流 | Depending on indicator, use 资金流量. |
| thrust | 推力 | For volume/price thrust; verify context. |
| divergence | 背离 | Standard technical-analysis term. |
| confirmation | 确认 | In chart context. |
""",
        encoding="utf-8",
        newline="\n",
    )


def write_full_book_guide_prompt(path: Path) -> None:
    path.write_text(
        f"""# DeepSeek V4 Pro full-book guide prompt

You are translating a finance/investing book into Simplified Chinese for an authorized public GitHub Pages publication.

Model requirements:
- Use DeepSeek V4 Pro.
- Use maximum thinking/reasoning effort.
- Use the large context window: read `manifest.json`, `TERMINOLOGY_SEED.md`, and `full_book_extract.md` together.
- Do not translate the whole book in this step.

Inputs:
- `manifest.json`: chapter/page/image/caption manifest.
- `TERMINOLOGY_SEED.md`: initial finance terminology seed.
- `full_book_extract.md`: compact full-book PDF text extraction.

Output file:
- `.cache/{CACHE_NAME}/book_guide.md`

Write `book_guide.md` in Simplified Chinese, with these sections:

1. 全书定位
- Explain the audience, investment discipline, style, and the author's conceptual framework.

2. 核心术语表
- Provide a table with columns: English, 简体中文译法, 适用语境, 禁用译法/注意事项.
- Cover technical analysis, volume indicators, market microstructure, trend analysis, chart patterns, and portfolio/investment language.

3. 章节标题译名表
- Translate every top-level unit and every chapter title from `manifest.json`.
- Keep chapter numbering stable.

4. 图表与图注规则
- Images are preserved as images.
- Do not translate text inside image pixels.
- Translate captions into polished Simplified Chinese.
- Keep figure/table numbering stable.

5. 文风规则
- Chinese should read like a professional investment/technical-analysis book.
- Avoid machine-translation phrasing.
- Avoid over-literal translations when established Chinese finance terms exist.
- Keep authorial meaning, examples, and nuance.

6. 专有名词规则
- Preserve people, institutions, indicators, and historical names where appropriate.
- First mention may use Chinese + English abbreviation.

7. HTML/anchor preservation rules
- Chapter slugs must remain from `manifest.json`.
- Section anchors should be stable ASCII slugs.
- Do not mutate image paths.
- Do not expose migration notes, TODO, or prompt artifacts.

8. Per-chapter translation checklist
- A concise checklist that every chapter translator must follow before writing output.

9. Reviewer checklist
- A concise checklist for DeepSeek review after a chapter is translated.
""",
        encoding="utf-8",
        newline="\n",
    )


def write_chapter_task_template(path: Path) -> None:
    path.write_text(
        f"""# DeepSeek V4 Pro chapter translation task template

Use DeepSeek V4 Pro with maximum thinking/reasoning effort.

Task:
Translate one chapter/unit of *Investing with Volume Analysis* into polished Simplified Chinese for an authorized public GitHub Pages book page.

Required inputs for each task:
- `.cache/{CACHE_NAME}/book_guide.md`
- `.cache/{CACHE_NAME}/manifest.json`
- `.cache/{CACHE_NAME}/image_caption_map.json`
- `.cache/{CACHE_NAME}/source_text/{{task_id}}.txt`

Output:
- Write only the final HTML fragment for the chapter body.
- Save to `.cache/{CACHE_NAME}/translated/{{task_id}}.html`.
- Do not include Markdown fences.
- Do not include translator notes, TODOs, source-extraction notes, or prompt commentary.

Chapter metadata placeholders:
- task_id: `{{task_id}}`
- source title: `{{title_en}}`
- target slug: `{{slug}}`
- PDF pages: `{{pdf_page_start}}-{{pdf_page_end}}`

Translation rules:
- Use professional Simplified Chinese finance/investing terminology.
- Follow `book_guide.md` terminology exactly unless the local context clearly requires an exception.
- Preserve original meaning, examples, indicator names, historical references, and market-analysis logic.
- Translate headings, body text, captions, table titles, notes, and footnotes.
- Keep mathematical symbols, indicator formulas, ticker-like notation, and abbreviations stable.

Image rules:
- Do not translate or redraw image pixels.
- Insert preserved images using their final target path from `image_caption_map.json`.
- Center every image.
- Translate the caption under the image.
- Use this shape for figures:

<div class="figure" style="text-align: center">
  <img src="/assets/img/{SLUG}/IMAGE_FILE" alt="" loading="lazy" />
  <p class="caption">图 X.X：中文图注。</p>
</div>

HTML rules:
- Output valid HTML fragment only.
- Use `<h1>`, `<h2>`, `<h3>`, paragraphs, lists, blockquotes, tables, figures, and footnotes as needed.
- Use stable ASCII `id` attributes for headings.
- Do not alter final site paths.
- Do not use external image URLs.

Quality rules:
- No visible English prose unless it is a proper noun, abbreviation, indicator name, citation, or intentionally bilingual first mention.
- No TODO, no placeholder markers, no machine-translation artifacts.
- No claims that code/images/text were converted by AI.
- If extraction appears garbled or incomplete, mark the issue in a separate review note, not in the reader-facing HTML.
""",
        encoding="utf-8",
        newline="\n",
    )


def write_publication_post_prompt(path: Path) -> None:
    path.write_text(
        f"""# Blog entry prompt

Use DeepSeek V4 Pro with maximum thinking/reasoning effort.

Write the public blog entry for:

`posts/{SLUG}/index.html`

The post should be in Simplified Chinese and include:
- A concise introduction to *Investing with Volume Analysis*.
- Author and publication context.
- Why volume analysis matters for investors and technical analysts.
- What readers will learn.
- A clickable chapter directory linking to `/{SLUG}/.../`.
- A brief authorization/source note supplied by the site owner.

Do not include full chapter text in the post. The post is an entry page; the book manuscript lives in separate chapter pages.
""",
        encoding="utf-8",
        newline="\n",
    )


def build_tasks(units: list[dict]) -> list[dict]:
    tasks = []
    for unit in units:
        tasks.append(
            {
                "task_id": unit["task_id"],
                "kind": unit["kind"],
                "title_en": unit["title_en"],
                "title_zh": "",
                "slug": unit["slug"],
                "pdf_page_start": unit["pdf_page_start"],
                "pdf_page_end": unit["pdf_page_end"],
                "input_files": [
                    f".cache/{CACHE_NAME}/book_guide.md",
                    f".cache/{CACHE_NAME}/manifest.json",
                    f".cache/{CACHE_NAME}/image_caption_map.json",
                    f".cache/{CACHE_NAME}/{unit['source_text_file']}",
                ],
                "output_file": f".cache/{CACHE_NAME}/{unit['translated_fragment_file']}",
                "review_file": f".cache/{CACHE_NAME}/{unit['review_report_file']}",
                "status": "pending",
                "retry_count": 0,
            }
        )
    return tasks


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Phase 0 translation assets for Investing with Volume Analysis.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--slug", default=SLUG)
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    repo_root = args.repo.resolve()
    slug = args.slug
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    cache_dir = repo_root / ".cache" / CACHE_NAME
    source_dir = cache_dir / "source_text"
    image_dir = cache_dir / "images"
    translated_dir = cache_dir / "translated"
    review_dir = cache_dir / "reviews"
    for folder in [cache_dir, source_dir, image_dir, translated_dir, review_dir]:
        folder.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    outline_items = flatten_outline(reader)
    units = build_units(outline_items, page_count)
    text_stats = write_source_texts(reader, units, source_dir, cache_dir / "full_book_extract.md")
    captions = find_captions(reader, page_count)
    images, image_stats = extract_images(pdf_path, reader, image_dir, slug)
    attach_captions(images, captions)

    image_caption_map = {
        "slug": slug,
        "notes": [
            "Images are extracted for preservation, not translation.",
            "Captions require Simplified Chinese translation during chapter translation.",
            "target_asset_path is the final public path after publishing assets.",
        ],
        "captions": captions,
        "images": images,
    }

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "generated_at_utc": generated_at,
        "phase": "0",
        "book": {
            "title_en": "Investing with Volume Analysis",
            "subtitle_en": "Identify, Follow, and Profit from Trends",
            "author": "Buff Pelz Dormeier",
            "publisher": "FT Press",
            "publication_year": 2011,
            "source_pdf": str(pdf_path),
            "pdf_pages": page_count,
            "authorization_assumption": "User stated they have publisher authorization for public translation/publication.",
        },
        "site": {
            "slug": slug,
            "post_path": f"posts/{slug}/index.html",
            "book_index_path": f"{slug}/index.html",
            "asset_target_dir": f"assets/img/{slug}",
            "asset_url_prefix": f"/assets/img/{slug}/",
        },
        "counts": {
            "outline_items": len(outline_items),
            "top_level_units": len(units),
            "captions_detected": len(captions),
            **image_stats,
            **text_stats,
        },
        "outline": outline_items,
        "units": units,
    }

    tasks = build_tasks(units)
    progress = {
        "generated_at_utc": generated_at,
        "model": "DeepSeek V4 Pro",
        "mode": "maximum thinking, chapter-level translation, full-book guide first",
        "status": "phase0_ready",
        "counts": {
            "tasks_total": len(tasks),
            "tasks_pending": len(tasks),
            "tasks_translated": 0,
            "tasks_reviewed": 0,
            "tasks_failed": 0,
        },
        "tasks": [{"task_id": task["task_id"], "status": task["status"], "retry_count": 0} for task in tasks],
    }

    write_json(cache_dir / "manifest.json", manifest)
    write_json(cache_dir / "image_caption_map.json", image_caption_map)
    write_json(cache_dir / "deepseek_tasks.json", {"generated_at_utc": generated_at, "tasks": tasks})
    write_json(cache_dir / "progress.json", progress)
    write_terminology_seed(cache_dir / "TERMINOLOGY_SEED.md")
    write_full_book_guide_prompt(cache_dir / "deepseek_full_book_guide_prompt.md")
    write_chapter_task_template(cache_dir / "deepseek_chapter_task_template.md")
    write_publication_post_prompt(cache_dir / "deepseek_publication_post_prompt.md")

    summary = {
        "cache_dir": str(cache_dir),
        "pdf_pages": page_count,
        "outline_items": len(outline_items),
        "top_level_units": len(units),
        "captions_detected": len(captions),
        "image_placements": image_stats.get("image_placements", 0),
        "unique_image_files": image_stats.get("unique_image_files", 0),
        "source_text_chars": text_stats["source_text_chars"],
        "empty_text_pages": len(text_stats["empty_text_pages"]),
        "status": "phase0_ready",
    }
    write_json(cache_dir / "phase0_summary.json", summary)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
