from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pdfplumber
import pypdfium2 as pdfium
from pypdf import PdfReader

from analyzing_financial_data_r_common import (
    BOOK_AUTHORS,
    BOOK_EDITION,
    BOOK_TITLE_EN,
    CACHE_NAME,
    FIGURE_CAPTION_RE,
    SLUG,
    build_units,
    clean_text,
    extract_page_text,
    find_captions,
    flatten_outline,
    sha1_text,
    write_json,
    write_text,
)


DEFAULT_PDF = Path(
    r"C:\Users\Chandler\Downloads\Clifford S. Ang (auth.) - Analyzing Financial Data and Implementing Financial Models Using R (2021, Springer).pdf"
)


def write_source_texts(reader: PdfReader, units: list[dict[str, Any]], source_dir: Path, full_book_path: Path) -> dict[str, Any]:
    source_dir.mkdir(parents=True, exist_ok=True)
    total_chars = 0
    empty_pages: list[int] = []

    with full_book_path.open("w", encoding="utf-8", newline="\n") as full_book:
        full_book.write(f"# Full-book text extraction for {BOOK_TITLE_EN}\n\n")
        full_book.write(f"Authors: {BOOK_AUTHORS}\n")
        full_book.write(f"Edition: {BOOK_EDITION}\n\n")
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
        """# Analyzing financial data and R financial modeling terminology seed

Use this as a seed only. DeepSeek should expand it after reading the compact extraction.

| English | Preferred Simplified Chinese | Notes |
|---|---|---|
| price | 价格 | Use 价格 for traded price. |
| value | 价值 | Distinguish from price. |
| return | 收益率 | Use 净收益率/gross return/log return precisely. |
| price return | 价格收益率 | Chapter 2 distinction. |
| total return | 总收益率 | Includes dividends/distributions. |
| logarithmic total return | 对数总收益率 | Preserve log-return distinction. |
| winsorization | 缩尾处理 | Quant/statistics term. |
| truncation | 截尾处理 | Distinguish from winsorization. |
| equal-weighted portfolio | 等权重投资组合 | EW portfolio. |
| value-weighted portfolio | 市值加权投资组合 | VW portfolio. |
| time-weighted rate of return | 时间加权收益率 | TWRR. |
| money-weighted rate of return | 资金加权收益率 | MWRR. |
| risk-return trade-off | 风险-收益权衡 | Standard finance term. |
| value-at-risk | 风险价值 | Keep VaR after first mention. |
| expected shortfall | 期望损失 | Keep ES after first mention. |
| CAPM | 资本资产定价模型 | Preserve CAPM after first mention. |
| market model | 市场模型 | Factor model context. |
| event study | 事件研究 | Standard finance/econometrics term. |
| Sharpe Ratio | 夏普比率 | Standard term. |
| Treynor Ratio | 特雷诺比率 | Standard term. |
| Sortino Ratio | 索提诺比率 | Standard term. |
| information ratio | 信息比率 | Standard term. |
| Markowitz mean-variance optimization | Markowitz 均值-方差优化 | Preserve Markowitz. |
| short selling | 卖空 | Portfolio context. |
| equity risk premium | 股权风险溢价 | ERP. |
| unlevering beta | 去杠杆化 beta | Preserve beta. |
| fixed income | 固定收益 | Asset class/chapter title. |
| zero-coupon bond | 零息债券 | Standard term. |
| coupon bond | 附息债券 | Standard term. |
| yield to maturity | 到期收益率 | Keep YTM when used as abbreviation. |
| duration | 久期 | Bond sensitivity context. |
| convexity | 凸性 | Bond risk context. |
| Black-Scholes-Merton | Black-Scholes-Merton | Preserve model name; BSM after first mention. |
| put-call parity | 看跌-看涨平价 | Options term. |
| implied volatility | 隐含波动率 | Options term. |
| volatility smile | 波动率微笑 | Options term. |
| binomial option pricing model | 二叉树期权定价模型 | CRR context. |
| geometric Brownian motion | 几何布朗运动 | Simulation chapter. |
| Monte Carlo simulation | 蒙特卡洛模拟 | Standard term. |
| efficient markets hypothesis | 有效市场假说 | EMH. |
| technical analysis | 技术分析 | Trading strategies. |
| Bollinger Bands | 布林带 | Preserve English if paired in source. |
| Relative Strength Index | 相对强弱指标 | RSI. |
| k-nearest neighbor | k 近邻 | KNN. |
| artificial neural network | 人工神经网络 | ANN. |
| R working directory | R 工作目录 | Appendix. |
| R package | R 包 | Preserve package names. |
""",
    )


def write_prompt_files(cache_dir: Path) -> None:
    write_text(
        cache_dir / "deepseek_full_book_guide_prompt.md",
        f"""# DeepSeek full-book guide prompt

Create a Simplified Chinese translation guide for an authorized public translation of:

*{BOOK_TITLE_EN}*
Authors: {BOOK_AUTHORS}
Edition: {BOOK_EDITION}

Do not translate the whole book in this step.

Inputs:
- `manifest.json`
- `TERMINOLOGY_SEED.md`
- `compact_guide_extract.md`

Required guide sections:
1. Book positioning and audience.
2. Professional glossary for quantitative finance, financial data analysis, financial modeling, statistics, econometrics, and R code.
3. Chinese title map for every unit in `manifest.json`.
4. Formula and notation preservation rules.
5. R code preservation rules. Every R code block must remain visible as R code; do not convert it to Python and do not add Python code.
6. Figure, table, URL, and footnote rules.
7. HTML structure rules for GitHub Pages.
8. Forbidden visible phrases and machine-translation smells.
9. Per-unit translation checklist.
10. Reviewer checklist.
""",
    )
    write_text(
        cache_dir / "deepseek_page_task_template.md",
        f"""# DeepSeek page translation task template

Translate one PDF page of *{BOOK_TITLE_EN}* into polished Simplified Chinese HTML for authorized GitHub Pages publication.

Inputs:
- `.cache/{CACHE_NAME}/book_guide.md`
- `.cache/{CACHE_NAME}/manifest.json`
- `.cache/{CACHE_NAME}/image_caption_map.json`
- `.cache/{CACHE_NAME}/source_text/{{task_id}}.txt`

Output JSON:
- `html`
- `r_code_blocks`
- `title_zh_if_page_starts_unit`
- `captions_zh`
- `warnings`

Rules:
- Output JSON only.
- Use `[[R_CODE:code-id]]` placeholders in HTML and put the original R code in `r_code_blocks`.
- Do not place raw `<pre>` blocks for R examples outside `r_code_blocks`.
- Do not create Python examples or Python code blocks.
- Preserve LaTeX math with `\\(...\\)` and `\\[...\\]`.
- Translate headings, prose, exercises, captions, table titles, and footnotes.
- Preserve links as clickable anchors and convert notes to bidirectional footnotes.
- Insert only image paths supplied in `images_on_page`; center figures in `<figure class="book-figure">`.
""",
    )


def group_words_into_lines(words: list[dict[str, Any]], tolerance: float = 3.0) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for word in sorted(words, key=lambda item: (float(item["top"]), float(item["x0"]))):
        top = float(word["top"])
        if lines and abs(lines[-1]["top"] - top) <= tolerance:
            line = lines[-1]
            line["words"].append(word)
            line["top"] = min(line["top"], float(word["top"]))
            line["bottom"] = max(line["bottom"], float(word["bottom"]))
            line["x0"] = min(line["x0"], float(word["x0"]))
            line["x1"] = max(line["x1"], float(word["x1"]))
            continue
        lines.append(
            {
                "words": [word],
                "top": float(word["top"]),
                "bottom": float(word["bottom"]),
                "x0": float(word["x0"]),
                "x1": float(word["x1"]),
            }
        )
    for line in lines:
        line["text"] = clean_text(" ".join(str(word["text"]) for word in line["words"]))
    return lines


def caption_line_records(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        text = str(line["text"])
        match = FIGURE_CAPTION_RE.match(text)
        if not match:
            continue
        number = match.group(2)
        if str(line["top"]) and float(line["top"]) < 100:
            continue
        caption_lines = [line]
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            gap = float(candidate["top"]) - float(caption_lines[-1]["bottom"])
            candidate_text = str(candidate["text"])
            if gap > 13 or candidate_text.startswith(("©", "Springer", "DOI ")) or FIGURE_CAPTION_RE.match(candidate_text):
                break
            if float(candidate["top"]) > 620:
                break
            caption_lines.append(candidate)
            cursor += 1
        records.append(
            {
                "number": number,
                "text_en": clean_text(" ".join(str(item["text"]) for item in caption_lines)),
                "top": min(float(item["top"]) for item in caption_lines),
                "bottom": max(float(item["bottom"]) for item in caption_lines),
            }
        )
    return records


def crop_box_for_caption(page: Any, caption: dict[str, Any], previous_bottom: float) -> tuple[float, float, float, float] | None:
    objects: list[dict[str, Any]] = []
    for attr in ("lines", "curves", "rects"):
        objects.extend(getattr(page, attr, []))
    relevant = []
    caption_top = float(caption["top"])
    for obj in objects:
        top = float(obj.get("top") or 0)
        bottom = float(obj.get("bottom") or 0)
        width = float(obj.get("width") or 0)
        height = float(obj.get("height") or 0)
        if top < max(110, previous_bottom + 2):
            continue
        if bottom > caption_top + 4:
            continue
        if width < 1 and height < 1:
            continue
        relevant.append(obj)
    if not relevant:
        return None
    left = max(0, min(float(obj.get("x0") or 0) for obj in relevant) - 60)
    right = min(float(page.width), max(float(obj.get("x1") or page.width) for obj in relevant) + 60)
    top = max(55, min(float(obj.get("top") or 0) for obj in relevant) - 50)
    bottom = min(float(page.height), float(caption["top"]) - 4)
    if bottom - top < 40 or right - left < 80:
        return None
    return left, top, right, bottom


def render_page_crop(pdf_doc: Any, page_index: int, box: tuple[float, float, float, float], output_path: Path, scale: float = 2.5) -> None:
    page = pdf_doc[page_index]
    bitmap = page.render(scale=scale)
    image = bitmap.to_pil()
    left, top, right, bottom = box
    crop = image.crop((round(left * scale), round(top * scale), round(right * scale), round(bottom * scale)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crop.save(output_path)


def extract_figure_crops(pdf_path: Path, image_dir: Path, slug: str = SLUG) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    image_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    pdf_doc = pdfium.PdfDocument(str(pdf_path))
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            words = page.extract_words(use_text_flow=True, keep_blank_chars=False)
            captions = caption_line_records(group_words_into_lines(words))
            previous_bottom = 0.0
            for caption in captions:
                box = crop_box_for_caption(page, caption, previous_bottom)
                previous_bottom = max(previous_bottom, float(caption["bottom"]))
                if box is None:
                    continue
                digest = sha1_text(f"{page_index + 1}-{caption['number']}-{box}")[:12]
                filename = f"figure-{digest}.png"
                output_path = image_dir / filename
                if not output_path.exists():
                    render_page_crop(pdf_doc, page_index, box, output_path)
                records.append(
                    {
                        "id": f"figure-{len(records) + 1:04d}",
                        "pdf_page": page_index + 1,
                        "kind": "figure_crop",
                        "number": caption["number"],
                        "text_en": caption["text_en"],
                        "cache_file": str(output_path.relative_to(image_dir.parent)),
                        "target_asset_path": f"/assets/img/{slug}/{filename}",
                        "bbox_top_origin": [round(value, 2) for value in box],
                        "caption_id": None,
                    }
                )
    return records, {
        "image_extractor": "pypdfium2_page_crops",
        "unique_image_files": len({item["cache_file"] for item in records}),
        "image_placements": len(records),
    }


def attach_figure_crops_to_captions(images: list[dict[str, Any]], captions: list[dict[str, Any]]) -> None:
    by_page_number: dict[tuple[int, str], str] = {}
    for caption in captions:
        if caption.get("label_type") != "figure":
            continue
        by_page_number[(int(caption["pdf_page"]), str(caption["number"]))] = str(caption["id"])
    for image in images:
        image["caption_id"] = by_page_number.get((int(image["pdf_page"]), str(image["number"])))


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


def add_dedication_unit(reader: PdfReader, units: list[dict[str, Any]], slug: str = SLUG) -> list[dict[str, Any]]:
    if any(unit.get("slug") == "dedication" for unit in units):
        return units
    dedication_text = extract_page_text(reader, 6)
    if "To my family" not in dedication_text:
        return units
    unit = {
        "id": "unit-000",
        "task_id": "dedication",
        "kind": "front_matter",
        "title_en": "Dedication",
        "title_zh": "",
        "slug": "dedication",
        "pdf_page_start": 6,
        "pdf_page_end": 6,
        "source_text_file": "source_text/dedication.txt",
        "translated_fragment_file": "translated/dedication.html",
        "review_report_file": "reviews/dedication.md",
        "site_output_path": f"{slug}/dedication/index.html",
        "sections": [],
        "status": "pending",
    }
    result = [unit, *units]
    for index, item in enumerate(result, start=1):
        item["id"] = f"unit-{index:03d}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Phase 0 assets for the Ang financial data and R modeling translation.")
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--slug", default=SLUG)
    parser.add_argument("--skip-figures", action="store_true")
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
    units = build_units(outline_items, page_count, slug=slug)
    units = add_dedication_unit(reader, units, slug=slug)

    text_stats = write_source_texts(reader, units, source_dir, cache_dir / "full_book_extract.md")
    guide_stats = write_compact_guide_extract(units, source_dir, cache_dir / "compact_guide_extract.md")
    captions = find_captions(reader, page_count)
    if args.skip_figures:
        images: list[dict[str, Any]] = []
        image_stats: dict[str, Any] = {"image_extractor": "skipped", "unique_image_files": 0, "image_placements": 0}
    else:
        images, image_stats = extract_figure_crops(pdf_path, image_dir, slug=slug)
        attach_figure_crops_to_captions(images, captions)

    image_caption_map = {
        "slug": slug,
        "notes": [
            "Figures are page-rendered crops because most book figures are PDF vector drawings, not embedded bitmap images.",
            "Captions require Simplified Chinese translation during page translation.",
            "target_asset_path is the final public path after publishing assets.",
        ],
        "captions": captions,
        "images": images,
    }

    write_terminology_seed(cache_dir / "TERMINOLOGY_SEED.md")
    write_prompt_files(cache_dir)

    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()
    manifest = {
        "generated_at_utc": generated_at,
        "phase": "0",
        "book": {
            "title_en": BOOK_TITLE_EN,
            "authors": BOOK_AUTHORS,
            "edition": BOOK_EDITION,
            "publisher": "Springer",
            "source_pdf": str(pdf_path),
            "pdf_pages": page_count,
            "authorization_assumption": "User stated they have complete authorization for public translation/publication.",
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
        },
        "outline": outline_items,
        "units": units,
    }

    tasks = build_tasks(units)
    progress = {
        "generated_at_utc": generated_at,
        "model": "deepseek-v4-flash",
        "mode": "full-book guide first, page-level translation, preserve original R code, deterministic checks",
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
        "status": "phase0_ready",
    }
    write_json(cache_dir / "phase0_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
