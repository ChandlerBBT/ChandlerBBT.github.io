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

from financial_engineering_common import (
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
    r"C:\Users\Chandler\Downloads\Statistics and Data Analysis for Financial Engineering_ with R examples (Springer Texts in Statis...{Ruppert, David, Matteson, David S.}(2015, Springer).pdf"
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
        """# Statistics and financial engineering terminology seed

Use this as a seed only. DeepSeek should expand it after reading the compact extraction.

| English | Preferred Simplified Chinese | Notes |
|---|---|---|
| financial engineering | 金融工程 | Core discipline term. |
| return | 收益率 | Use 净收益率/gross return/log return precisely. |
| net return | 净收益率 | Do not use 净回报率 unless context requires. |
| gross return | 总收益率 | Preserve relation to net return. |
| log return | 对数收益率 | Standard quantitative finance term. |
| random walk | 随机游走 | Standard stochastic process term. |
| geometric random walk | 几何随机游走 | Preserve distinction from random walk. |
| fixed income securities | 固定收益证券 | Chapter title. |
| zero-coupon bond | 零息债券 | Standard term. |
| coupon bond | 附息债券 | Standard term. |
| yield to maturity | 到期收益率 | Keep YTM when used as abbreviation. |
| term structure | 期限结构 | Interest-rate context. |
| duration | 久期 | Bond sensitivity context. |
| exploratory data analysis | 探索性数据分析 | Standard statistics term. |
| kernel density estimation | 核密度估计 | Standard term. |
| order statistics | 顺序统计量 | Standard term. |
| sample CDF | 样本分布函数 | Also note empirical CDF when appropriate. |
| quantile | 分位数 | Avoid 位数. |
| normal probability plot | 正态概率图 | Standard term. |
| QQ plot | QQ 图 | Preserve abbreviation. |
| skewness | 偏度 | Standard term. |
| kurtosis | 峰度 | Standard term. |
| heavy-tailed distribution | 厚尾分布 | Finance/statistics term. |
| maximum likelihood estimation | 极大似然估计 | Use MLE after first mention. |
| Fisher information | Fisher 信息量 | Keep Fisher name. |
| likelihood ratio test | 似然比检验 | Standard term. |
| bootstrap | bootstrap/自助法 | Use 自助法 after first bilingual mention if natural. |
| copula | copula/连接函数 | In finance statistics, keep copula at first mention. |
| time series | 时间序列 | Standard term. |
| stationarity | 平稳性 | Standard term. |
| autocorrelation | 自相关 | Standard term. |
| ARMA model | ARMA 模型 | Preserve model acronym. |
| GARCH model | GARCH 模型 | Preserve acronym. |
| cointegration | 协整 | Standard econometrics term. |
| portfolio selection | 投资组合选择 | Standard finance term. |
| CAPM | 资本资产定价模型 | Preserve CAPM after first mention. |
| factor model | 因子模型 | Standard quantitative finance term. |
| principal components | 主成分 | Standard term. |
| risk management | 风险管理 | Standard term. |
| Value at Risk | 风险价值 | Keep VaR. |
| expected shortfall | 期望损失 | Also known as ES; avoid overly literal translation. |
| Bayesian data analysis | 贝叶斯数据分析 | Standard term. |
| MCMC | 马尔可夫链蒙特卡洛 | Preserve MCMC. |
| nonparametric regression | 非参数回归 | Standard term. |
| splines | 样条 | Use 样条函数 when referring to basis/functions. |
| R Lab | R 实验 | Keep as R section title, but code tabs include R and Python. |
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
2. Professional glossary for quantitative finance, financial engineering, statistics, statistical learning, econometrics, and R/Python code.
3. Chinese title map for every unit in `manifest.json`.
4. Formula and notation preservation rules.
5. R-to-Python conversion rules. Every R code block must remain visible in an R tab, with a conceptually equivalent runnable Python tab.
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
- `code_pairs`
- `title_zh_if_page_starts_unit`
- `captions_zh`
- `warnings`

Rules:
- Output JSON only.
- Use `[[CODE_PAIR:code-id]]` placeholders in HTML and put the original R code plus Python conversion in `code_pairs`.
- Do not place raw `<pre>` blocks for R/Python examples outside code pairs.
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
        if match:
            number = match.group(2)
        else:
            inline_match = re.search(r"\bFig\.\s*([0-9]+(?:[.-][0-9A-Za-z]+)*)\.?", text)
            lower = text.lower().replace(" ", "")
            if not inline_match or any(marker in lower for marker in ("seefig.", "of fig.", "offig.", "infig.")):
                continue
            number = inline_match.group(1)
            if inline_match.start() < max(12, len(text) // 3):
                continue
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


def object_bbox(obj: dict[str, Any]) -> tuple[float, float, float, float]:
    left = float(obj.get("x0") or 0)
    right = float(obj.get("x1") or left)
    top = float(obj.get("top") or 0)
    bottom = float(obj.get("bottom") or top)
    return left, top, right, bottom


def cluster_graphic_objects(objects: list[dict[str, Any]], vertical_gap: float = 45.0) -> list[dict[str, float]]:
    clusters: list[dict[str, float]] = []
    for obj in sorted(objects, key=lambda item: (object_bbox(item)[1], object_bbox(item)[0])):
        left, top, right, bottom = object_bbox(obj)
        if not clusters or top > clusters[-1]["bottom"] + vertical_gap:
            clusters.append({"left": left, "top": top, "right": right, "bottom": bottom, "count": 1})
            continue
        cluster = clusters[-1]
        cluster["left"] = min(cluster["left"], left)
        cluster["top"] = min(cluster["top"], top)
        cluster["right"] = max(cluster["right"], right)
        cluster["bottom"] = max(cluster["bottom"], bottom)
        cluster["count"] += 1
    return clusters


def is_source_running_header(line: str) -> bool:
    if not line:
        return False
    if re.fullmatch(r"\d{1,4}\s+\d{1,2}\s+[A-Z][A-Za-z0-9 ,:;'\-()]+", line):
        return True
    if re.fullmatch(r"\d{1,2}\s+[A-Z][A-Za-z0-9 ,:;'\-()]+\s+\d{1,4}", line):
        return True
    if re.fullmatch(r"\d{1,4}\s+[A-Z]\s+[A-Z][A-Za-z0-9 ,:;'\-()]+", line):
        return True
    return False


def nearby_title_top(page: Any, selected: dict[str, float], previous_bottom: float) -> float | None:
    if not hasattr(page, "extract_words"):
        return None
    try:
        lines = group_words_into_lines(page.extract_words(use_text_flow=True, keep_blank_chars=False))
    except Exception:
        return None
    graph_width = selected["right"] - selected["left"]
    candidates: list[float] = []
    for line in lines:
        gap = selected["top"] - float(line["bottom"])
        if gap < -2 or gap > 65:
            continue
        if float(line["top"]) <= max(35, previous_bottom + 2):
            continue
        overlap = min(float(line["x1"]), selected["right"]) - max(float(line["x0"]), selected["left"])
        center = (float(line["x0"]) + float(line["x1"])) / 2
        text = str(line.get("text") or "").strip()
        if not text or len(text) > 90:
            continue
        if is_source_running_header(text):
            continue
        if len(text.split()) > 9 and "=" not in text:
            continue
        if "." in text and "=" not in text:
            continue
        if text.endswith(".") and "=" not in text:
            continue
        if overlap >= min(120.0, graph_width * 0.25) or selected["left"] <= center <= selected["right"]:
            candidates.append(float(line["top"]))
    return min(candidates) if candidates else None


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
    clusters = cluster_graphic_objects(relevant)
    candidates = [
        cluster
        for cluster in clusters
        if cluster["right"] - cluster["left"] >= 80
        and cluster["bottom"] - cluster["top"] >= 30
        and cluster["count"] >= 2
    ]
    if not candidates:
        caption_top = float(caption["top"])
        top = max(60, previous_bottom + 4, caption_top - 260)
        bottom = min(float(page.height), caption_top - 6)
        left = 20.0
        right = float(page.width) - 20.0
        if bottom - top < 40:
            return None
        return left, top, right, bottom
    selected = max(candidates, key=lambda cluster: cluster["bottom"])
    left = max(0, selected["left"] - 50)
    right = min(float(page.width), selected["right"] + 35)
    title_top = nearby_title_top(page, selected, previous_bottom)
    top = max(0, (title_top - 8) if title_top is not None else selected["top"] - 25)
    bottom = min(float(page.height), float(caption["top"]) - 6, selected["bottom"] + 50)
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
                number_slug = re.sub(r"[^0-9A-Za-z]+", "-", str(caption["number"])).strip("-") or str(len(records) + 1)
                filename = f"figure-{number_slug}-p{page_index + 1:03d}.png"
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare Phase 0 assets for the Ruppert/Matteson financial engineering translation.")
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
        "mode": "full-book guide first, page-level translation, R/Python code tabs, deterministic checks",
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
