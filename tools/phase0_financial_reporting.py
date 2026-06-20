from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from financial_reporting_common import (
    BOOK_AUTHORS,
    BOOK_TITLE_EN,
    CACHE_NAME,
    SLUG,
    attach_captions,
    build_known_pdf_units,
    build_units,
    extract_images_with_pypdf,
    extract_page_text,
    find_captions,
    flatten_outline,
    write_json,
    write_text,
)


DEFAULT_PDF = Path(
    r"C:\Users\Chandler\Documents\自修室\Course-02-Financial Reporting,Statement Analysis,Valuation-Wahlen\Financial Reporting，Financial statement analysis and valuation (James M. Wahlen；Stephen P. Baginski) .pdf"
)
DEFAULT_CHAPTER1_TRANSLATION = Path(
    r"C:\Users\Chandler\Documents\自修室\Course-02-Financial Reporting,Statement Analysis,Valuation-Wahlen\教材第一章_完整翻译.md"
)


def write_source_texts(reader: PdfReader, units: list[dict[str, Any]], source_dir: Path, full_book_path: Path) -> dict[str, Any]:
    source_dir.mkdir(parents=True, exist_ok=True)
    total_chars = 0
    empty_pages: list[int] = []

    with full_book_path.open("w", encoding="utf-8", newline="\n") as full_book:
        full_book.write(f"# Full-book text extraction for {BOOK_TITLE_EN}\n\n")
        full_book.write(f"Authors: {BOOK_AUTHORS}\n\n")
        for unit in units:
            parts = [
                f"# {unit['title_en']}\n",
                f"<!-- pdf_pages: {unit['pdf_page_start']}-{unit['pdf_page_end']} -->\n",
            ]
            for page_number in range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1):
                page_text = extract_page_text(reader, page_number)
                if not page_text.strip():
                    empty_pages.append(page_number)
                parts.append(f"\n\n<!-- pdf_page: {page_number} -->\n\n{page_text.strip()}\n")
            text = "\n".join(parts)
            total_chars += len(text)
            write_text(source_dir / f"{unit['slug']}.txt", text)
            full_book.write(text)
            full_book.write("\n\n")

    return {
        "source_text_chars": total_chars,
        "empty_text_pages": sorted(set(empty_pages)),
    }


def write_compact_guide_extract(units: list[dict[str, Any]], source_dir: Path, output_path: Path) -> dict[str, Any]:
    parts = [
        f"# Compact guide extraction for {BOOK_TITLE_EN}",
        "",
        "This file is for building a full-book terminology/style guide. It includes unit metadata and short samples.",
        "",
    ]
    total_chars = 0
    for unit in units:
        source = source_dir / f"{unit['slug']}.txt"
        text = source.read_text(encoding="utf-8") if source.exists() else ""
        sample = text[:6500]
        total_chars += len(sample)
        parts.extend(
            [
                f"## {unit['title_en']}",
                f"- slug: {unit['slug']}",
                f"- pdf pages: {unit['pdf_page_start']}-{unit['pdf_page_end']}",
                "",
                sample,
                "",
            ]
        )
    write_text(output_path, "\n".join(parts))
    return {"guide_extract_chars": total_chars}


def write_terminology_seed(path: Path) -> None:
    write_text(
        path,
        """# Financial reporting terminology seed

Use this as a seed only. DeepSeek should expand it after reading the compact full-book extraction.

| English | Preferred Simplified Chinese | Notes |
|---|---|---|
| financial reporting | 财务报告 | Book-level core term. |
| financial statement analysis | 财务报表分析 | Standard accounting/finance term. |
| valuation | 估值 | Use enterprise/equity context precisely. |
| balance sheet | 资产负债表 | Preserve statement names consistently. |
| income statement | 利润表 | If context requires, mention 损益表 at first use. |
| statement of cash flows | 现金流量表 | Use for formal statement title. |
| profitability | 盈利能力 | Avoid literal 利润性. |
| risk analysis | 风险分析 | Standard finance term. |
| accounting quality | 会计质量 | Use 财务报告质量 when context is broader. |
| earnings management | 盈余管理 | Standard academic/accounting term. |
| accrual accounting | 权责发生制会计 | First mention can be bilingual. |
| fair value | 公允价值 | Standard IFRS/US GAAP term. |
| representational faithfulness | 如实反映 | Conceptual Framework term. |
| relevance | 相关性 | Conceptual Framework term. |
| return on assets | 资产收益率 | Keep ROA. |
| return on common equity | 普通股权益收益率 | Keep ROCE. |
| free cash flow | 自由现金流 | Distinguish FCFE/FCFF where needed. |
| residual income | 剩余收益 | Valuation context. |
| market-to-book ratio | 市净率 | Keep MB if the text uses it as a model variable. |
| price-earnings ratio | 市盈率 | Keep PE if the text uses it as a model variable. |
| weighted-average cost of capital | 加权平均资本成本 | Keep WACC. |
| cost of equity capital | 权益资本成本 | Use consistently. |
| U.S. GAAP | 美国通用会计准则 | Preserve abbreviation after first mention. |
| IFRS | 国际财务报告准则 | Preserve abbreviation after first mention. |
""",
    )


def write_prompt_files(cache_dir: Path) -> None:
    write_text(
        cache_dir / "deepseek_full_book_guide_prompt.md",
        f"""# DeepSeek full-book guide prompt

Create a Simplified Chinese translation guide for an authorized public translation of:

*{BOOK_TITLE_EN}*
Authors: {BOOK_AUTHORS}

Use maximum reasoning effort internally. Do not translate the whole book in this step.

Inputs:
- `manifest.json`
- `TERMINOLOGY_SEED.md`
- `compact_guide_extract.md`
- `STYLE_SEED_CHAPTER1.md` when present

Output:
- `book_guide.json`
- `book_guide.md`

Required guide sections:
1. Book positioning and audience.
2. Professional glossary for financial reporting, accounting quality, forecasting, and valuation.
3. Chinese title map for every unit in `manifest.json`.
4. Formula and notation preservation rules.
5. Table, exhibit, figure, and footnote rules.
6. HTML structure rules for GitHub Pages.
7. Forbidden visible phrases and machine-translation smells.
8. Per-unit translation checklist.
9. Reviewer checklist.

Important:
- The existing Chapter 1 Chinese file may include study notes such as source/translation labels. Use it only as terminology and style seed; do not preserve those visible notes in public pages.
- Preserve accepted accounting and finance terms.
- Keep formulas, ratios, exhibit numbers, company names, standards, and abbreviations stable.
""",
    )
    write_text(
        cache_dir / "deepseek_chapter_task_template.md",
        f"""# DeepSeek chapter translation task template

Translate one unit of *{BOOK_TITLE_EN}* into polished Simplified Chinese HTML for authorized GitHub Pages publication.

Inputs:
- `.cache/{CACHE_NAME}/book_guide.md`
- `.cache/{CACHE_NAME}/manifest.json`
- `.cache/{CACHE_NAME}/image_caption_map.json`
- `.cache/{CACHE_NAME}/source_text/{{task_id}}.txt`

Output:
- `.cache/{CACHE_NAME}/translated/{{task_id}}.html`

Rules:
- Output valid HTML fragment only, no Markdown fence.
- Translate headings, paragraphs, captions, table titles, exercises, problems, and cases.
- Preserve formulas, ratio notation, exhibit numbers, company names, GAAP/IFRS abbreviations, and citations.
- Do not translate image pixels; insert preserved images from `image_caption_map.json` when needed.
- Use stable ASCII ids on headings.
- Do not include TODO, translator notes, prompt traces, source labels, or migration notes.
- Visible prose should be natural professional Simplified Chinese.
""",
    )


def copy_style_seed(source: Path, target: Path) -> dict[str, Any]:
    if not source.exists():
        return {"style_seed_present": False, "style_seed_chars": 0}
    text = source.read_text(encoding="utf-8", errors="replace")
    write_text(
        target,
        "# Existing Chapter 1 Chinese draft for terminology/style seeding\n\n"
        "Use this as terminology/style seed only. Public output must remove source labels and translation notes.\n\n"
        + text[:80_000],
    )
    return {"style_seed_present": True, "style_seed_chars": min(len(text), 80_000)}


def build_tasks(units: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    parser = argparse.ArgumentParser(description="Prepare Phase 0 assets for the Wahlen financial reporting translation.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--slug", default=SLUG)
    parser.add_argument("--chapter1-translation", type=Path, default=DEFAULT_CHAPTER1_TRANSLATION)
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args()

    pdf_path = args.pdf.resolve()
    repo_root = args.repo.resolve()
    slug = args.slug
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    cache_dir = repo_root / ".cache" / CACHE_NAME
    source_dir = cache_dir / "source_text"
    image_dir = cache_dir / "images"
    for folder in [cache_dir, source_dir, image_dir, cache_dir / "translated", cache_dir / "reviews"]:
        folder.mkdir(parents=True, exist_ok=True)

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    outline_items = flatten_outline(reader)
    units = build_units(outline_items, page_count, slug=slug) if outline_items else build_known_pdf_units(page_count, slug=slug)

    text_stats = write_source_texts(reader, units, source_dir, cache_dir / "full_book_extract.md")
    guide_stats = write_compact_guide_extract(units, source_dir, cache_dir / "compact_guide_extract.md")
    captions = find_captions(reader, page_count)
    if args.skip_images:
        images: list[dict[str, Any]] = []
        image_stats: dict[str, Any] = {"image_extractor": "skipped", "unique_image_files": 0, "image_placements": 0}
    else:
        images, image_stats = extract_images_with_pypdf(reader, image_dir, slug=slug)
    attach_captions(images, captions)

    image_caption_map = {
        "slug": slug,
        "notes": [
            "Images are extracted for preservation, not translation.",
            "Captions require Simplified Chinese translation during unit translation.",
            "target_asset_path is the final public path after publishing assets.",
        ],
        "captions": captions,
        "images": images,
    }

    style_stats = copy_style_seed(args.chapter1_translation.resolve(), cache_dir / "STYLE_SEED_CHAPTER1.md")
    write_terminology_seed(cache_dir / "TERMINOLOGY_SEED.md")
    write_prompt_files(cache_dir)

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "generated_at_utc": generated_at,
        "phase": "0",
        "book": {
            "title_en": BOOK_TITLE_EN,
            "authors": BOOK_AUTHORS,
            "edition": "10e",
            "publisher": "Cengage Learning",
            "source_pdf": str(pdf_path),
            "pdf_pages": page_count,
            "authorization_assumption": "User stated they have authorization for public translation/publication.",
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
            **guide_stats,
            **style_stats,
        },
        "outline": outline_items,
        "units": units,
    }

    tasks = build_tasks(units)
    progress = {
        "generated_at_utc": generated_at,
        "model": "DeepSeek",
        "mode": "full-book guide first, unit-level translation, deterministic checks",
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

    summary = {
        "cache_dir": str(cache_dir),
        "pdf_pages": page_count,
        "outline_items": len(outline_items),
        "top_level_units": len(units),
        "captions_detected": len(captions),
        "image_placements": image_stats.get("image_placements", 0),
        "unique_image_files": image_stats.get("unique_image_files", 0),
        "source_text_chars": text_stats["source_text_chars"],
        "guide_extract_chars": guide_stats["guide_extract_chars"],
        "empty_text_pages": len(text_stats["empty_text_pages"]),
        "style_seed_present": style_stats["style_seed_present"],
        "status": "phase0_ready",
    }
    write_json(cache_dir / "phase0_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
