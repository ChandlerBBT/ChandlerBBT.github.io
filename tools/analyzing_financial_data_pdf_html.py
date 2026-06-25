from __future__ import annotations

import argparse
import base64
import concurrent.futures
import hashlib
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / "analyzing-financial-data-r-html"
EXTRACT_DIR = CACHE_DIR / "extract"
SLUG = "analyzing-financial-data-r-cn"
PROMPT_VERSION = "ang-pdf-html-v1.1"
BOOK_TITLE_EN = "Analyzing Financial Data and Implementing Financial Models Using R"
BOOK_TITLE_ZH = "《使用 R 分析金融数据并实现金融模型》"
BOOK_FULL_TITLE_ZH = "《使用 R 分析金融数据并实现金融模型》简体中文 HTML 版"
BOOK_AUTHORS = "Clifford S. Ang"
BLOG_DATE = "2026-06-25"

CAPTION_RE = re.compile(r"^\s*(?:Fig\.|Figure|Table)\s+[A-Z]?\d+(?:\.\d+)*", re.IGNORECASE)
R_PROMPT_RE = re.compile(r"^\s*(?:\d{1,4}\s+)?(?:>|[+])\s+")
R_OUTPUT_RE = re.compile(r"^\s*(?:\d{1,4}\s+)?(?:\[\d+\]|[A-Za-z][A-Za-z0-9_.]*\s{2,}|[0-9]{4}[-/][0-9]{2}[-/][0-9]{2})")
PAGE_HEADER_RE = re.compile(
    r"^\s*(?:\d+\s+)?(?:"
    r"Prices|Single Security Returns|Portfolio Returns|Risk|Factor Models|"
    r"Risk-Adjusted Measures of Portfolio Performance|Markowitz Mean-Variance Optimization|"
    r"Stocks|Fixed Income|Options|Simulation|Trading Strategies|"
    r"Introduction to R|Pre-Loaded Code|Constructing Hypothetical Portfolio|Index|"
    r"Preface|Acknowledgments|References"
    r")\s*$",
    re.IGNORECASE,
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def strip_json_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def loads_model_json(text: str) -> dict[str, Any]:
    text = strip_json_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


class DeepSeekClient:
    def __init__(self, model: str, timeout: int, max_tokens: int) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    def chat_json(self, system: str, user: dict[str, Any], temperature: float = 0.06, retries: int = 3) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
            ],
            "temperature": temperature,
            "max_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            req = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=data,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                outer = json.loads(raw)
                content = outer["choices"][0]["message"].get("content", "")
                return loads_model_json(content)
            except Exception as exc:
                last_error = exc
                if isinstance(exc, urllib.error.HTTPError):
                    try:
                        detail = exc.read().decode("utf-8", errors="replace")
                    except Exception:
                        detail = ""
                    last_error = RuntimeError(f"HTTP {exc.code}: {detail[:800]}")
                time.sleep(2 * attempt)
        raise RuntimeError(f"DeepSeek request failed: {last_error}")


def is_page_number(text: str) -> bool:
    value = text.strip()
    return bool(re.fullmatch(r"\d{1,4}", value))


def bbox(block: dict[str, Any]) -> list[float]:
    return [float(x) for x in block.get("bbox", [0, 0, 0, 0])]


def is_running_header(text: str, block_bbox: list[float]) -> bool:
    value = " ".join(text.split())
    if not value:
        return True
    if is_page_number(value):
        return True
    y0 = block_bbox[1]
    if y0 <= 78 and (PAGE_HEADER_RE.match(value) or re.fullmatch(r"\d+\s+\S.+", value)):
        return True
    return False


def is_r_code_block(text: str) -> bool:
    if is_caption(text):
        return False
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    if len(lines) == 1:
        stripped = lines[0].strip()
        return bool(R_PROMPT_RE.match(stripped) or re.match(r"^\s*\d{1,4}\s+>\s+", stripped))
    for index, line in enumerate(lines[:-1]):
        if line.strip().isdigit() and lines[index + 1].strip().startswith(">"):
            return True
    code_like = 0
    for index, line in enumerate(lines):
        stripped = line.strip()
        next_line = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if stripped.isdigit() and (next_line.startswith((">", "+")) or R_OUTPUT_RE.match(next_line)):
            code_like += 1
        elif R_PROMPT_RE.match(stripped) or R_OUTPUT_RE.match(stripped):
            code_like += 1
        elif any(token in stripped for token in (" <- ", "<-", "library(", "install.packages", "data.", "ggplot(", "plot(")):
            code_like += 1
    return code_like >= max(2, min(3, len(lines)))


def iter_content_text_blocks(page: dict[str, Any]):
    page_no = int(page.get("page", 0))
    ti = 0
    for block in page.get("blocks", []):
        if block.get("type") != "text":
            continue
        text = str(block.get("text", "")).strip()
        if not text or is_running_header(text, bbox(block)):
            continue
        key = f"p{page_no}_t{ti}"
        ti += 1
        yield key, block, text


def is_caption(text: str) -> bool:
    return bool(CAPTION_RE.match(" ".join(text.split())))


def prepare_translation_units(struct: dict[str, Any]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for page in struct.get("pages", []):
        page_no = int(page.get("page", 0))
        for key, _block, text in iter_content_text_blocks(page):
            if is_r_code_block(text):
                continue
            units.append({"id": key, "page": page_no, "src": text})
    return units


def add_drawings_from_pdf(struct: dict[str, Any], source_pdf: Path) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised in integration via uv.
        raise RuntimeError("PyMuPDF/fitz is required to detect vector figures; run via uv --with pymupdf.") from exc

    doc = fitz.open(str(source_pdf))
    for page_data in struct.get("pages", []):
        page_no = int(page_data.get("page", 0))
        if not page_no or page_no > len(doc):
            continue
        drawings: list[dict[str, Any]] = []
        for drawing in doc.load_page(page_no - 1).get_drawings():
            rect = drawing.get("rect")
            if rect is None:
                continue
            drawings.append({"bbox": [float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)]})
        page_data["drawings"] = drawings
    return struct


def detect_figure_regions(struct: dict[str, Any]) -> list[dict[str, Any]]:
    regions: list[dict[str, Any]] = []
    for page in struct.get("pages", []):
        page_no = int(page.get("page", 0))
        captions = [
            block
            for block in page.get("blocks", [])
            if block.get("type") == "text" and is_caption(str(block.get("text", "")))
        ]
        if not captions:
            continue
        drawings = []
        for drawing in page.get("drawings", []):
            x0, y0, x1, y1 = [float(v) for v in drawing.get("bbox", [0, 0, 0, 0])]
            if (x1 - x0) < 24 or (y1 - y0) < 16:
                continue
            drawings.append([x0, y0, x1, y1])
        lower_bound = 70.0
        for caption in sorted(captions, key=lambda b: bbox(b)[1]):
            cap_box = bbox(caption)
            cap_top = cap_box[1]
            candidates = [
                d
                for d in drawings
                if d[1] >= lower_bound - 10 and d[3] <= cap_top + 3 and d[1] >= 65
            ]
            if not candidates:
                lower_bound = cap_box[3]
                continue
            x0 = max(45.0, min(d[0] for d in candidates) - 18)
            y0 = max(75.0, min(d[1] for d in candidates) - 22)
            x1 = min(float(struct.get("meta", {}).get("page_width", 612)), max(d[2] for d in candidates) + 18)
            y1 = min(cap_top - 4, max(d[3] for d in candidates) + 18)
            if y1 > y0 + 40:
                regions.append(
                    {
                        "page": page_no,
                        "bbox": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                        "caption": str(caption.get("text", "")).strip(),
                        "caption_bbox": cap_box,
                    }
                )
            lower_bound = cap_box[3]
    return regions


def crop_region_from_page(region: dict[str, Any], pages_dir: Path, out_dir: Path, dpi: int) -> Path | None:
    page = int(region["page"])
    page_png = pages_dir / f"page-{page:02d}.png"
    if not page_png.exists():
        page_png = pages_dir / f"page-{page}.png"
    if not page_png.exists():
        return None
    img = Image.open(page_png).convert("RGB")
    scale = dpi / 72.0
    x0, y0, x1, y1 = [float(v) for v in region["bbox"]]
    left = max(0, round(x0 * scale))
    top = max(0, round(y0 * scale))
    right = min(img.width, round(x1 * scale))
    bottom = min(img.height, round(y1 * scale))
    if right <= left or bottom <= top:
        return None
    crop = img.crop((left, top, right, bottom))
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"figure-p{page:03d}-{sha1_text(str(region['bbox']))[:10]}.png"
    crop.save(out)
    return out


def image_data_uri(path: Path) -> str:
    img = Image.open(path)
    if img.width > 1400:
        height = round(img.height * 1400 / img.width)
        img = img.resize((1400, height), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def render_r_code_block(code: str, code_id: str) -> str:
    escaped = html.escape(code.strip())
    label = "复制"
    return (
        f'<div class="r-code-card">'
        f'<div class="code-toolbar"><span>R</span><button class="copy-code" type="button" '
        f'data-code-target="{html.escape(code_id, quote=True)}">{label}</button></div>'
        f'<pre><code id="{html.escape(code_id, quote=True)}" class="language-r">{escaped}</code></pre>'
        f"</div>"
    )


def text_to_paragraphs(text: str) -> str:
    chunks = [chunk.strip() for chunk in re.split(r"\n\s*\n", text.strip()) if chunk.strip()]
    if not chunks:
        return ""
    rendered: list[str] = []
    for chunk in chunks:
        lines = [line.strip() for line in chunk.splitlines() if line.strip()]
        if not lines:
            continue
        if all(line.startswith("- ") for line in lines):
            items = "".join(f"<li>{html.escape(line[2:].strip())}</li>" for line in lines)
            rendered.append(f"<ul>{items}</ul>")
        else:
            rendered.append(f"<p>{html.escape(' '.join(lines))}</p>")
    return "\n".join(rendered)


def infer_heading_tiers(struct: dict[str, Any]) -> dict[int, str]:
    sizes = [
        round(float(block.get("size", 0)))
        for page in struct.get("pages", [])
        for block in page.get("blocks", [])
        if block.get("type") == "text"
        and str(block.get("text", "")).strip()
        and not is_running_header(str(block.get("text", "")), bbox(block))
        and not is_r_code_block(str(block.get("text", "")))
    ]
    body = Counter(sizes).most_common(1)[0][0] if sizes else 10
    larger = sorted({size for size in sizes if size > body}, reverse=True)
    return {size: ("h1", "h2", "h3")[min(i, 2)] for i, size in enumerate(larger)}


def build_page_region_map(regions: list[dict[str, Any]]) -> dict[tuple[int, str], dict[str, Any]]:
    result: dict[tuple[int, str], dict[str, Any]] = {}
    for region in regions:
        result[(int(region["page"]), str(region.get("caption", "")).strip())] = region
    return result


def render_document_html(
    struct: dict[str, Any],
    translations: dict[str, str],
    regions: list[dict[str, Any]],
    figure_assets: dict[str, str],
) -> str:
    tiers = infer_heading_tiers(struct)
    region_map = build_page_region_map(regions)
    body_parts: list[str] = []
    toc: list[tuple[str, str]] = []
    code_index = 0
    for page in struct.get("pages", []):
        page_no = int(page.get("page", 0))
        for unit_id, block, raw in iter_content_text_blocks(page):
            if is_r_code_block(raw):
                code_index += 1
                body_parts.append(render_r_code_block(raw, f"r-code-{code_index}"))
                continue
            text = translations.get(unit_id, raw).strip()
            if not text:
                continue
            if is_r_code_block(text):
                continue
            caption_region = region_map.get((page_no, raw))
            if caption_region:
                asset = figure_assets.get(caption_region.get("asset", ""))
                if asset:
                    body_parts.append(
                        '<figure class="book-figure">'
                        f'<img src="{asset}" alt="{html.escape(text, quote=True)}">'
                        f"<figcaption>{html.escape(text)}</figcaption></figure>"
                    )
                    continue
            size = round(float(block.get("size", 0)))
            tag = tiers.get(size, "p")
            if tag == "p" or len(text) > 180:
                body_parts.append(text_to_paragraphs(text))
            else:
                anchor = "section-" + sha1_text(text)[:12]
                toc.append((anchor, text))
                body_parts.append(f'<{tag} id="{anchor}">{html.escape(text)}</{tag}>')
    toc_html = "".join(f'<a href="#{html.escape(anchor)}">{html.escape(title)}</a>' for anchor, title in toc[:80])
    return HTML_TEMPLATE.format(title=html.escape(BOOK_FULL_TITLE_ZH), toc=toc_html, body="\n".join(body_parts))


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="《Analyzing Financial Data and Implementing Financial Models Using R》的简体中文 HTML 版，保留原书 R 代码与图表。">
<title>{title} | Chandler&#x27;s AI Productivity Notes</title>
<style>
  :root {{ --ink:#1b1d22; --muted:#626b7a; --line:#d8e2ef; --paper:#ffffff; --soft:#f5f9ff; --code:#eaf6ff; --accent:#2563a8; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#f4f7fb; color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Segoe UI",Arial,sans-serif; font-size:17px; line-height:1.82; }}
  .shell {{ max-width:1180px; margin:0 auto; padding:24px; display:grid; grid-template-columns:250px minmax(0, 1fr); gap:28px; }}
  .topbar {{ grid-column:1 / -1; display:flex; justify-content:space-between; align-items:center; gap:16px; border-bottom:1px solid var(--line); padding:12px 0 22px; }}
  .brand {{ color:var(--accent); text-decoration:none; font-weight:700; }}
  .source-note {{ color:var(--muted); font-size:14px; }}
  aside {{ position:sticky; top:18px; align-self:start; max-height:calc(100vh - 36px); overflow:auto; padding:14px; background:var(--paper); border:1px solid var(--line); border-radius:8px; }}
  aside h2 {{ font-size:15px; margin:0 0 10px; }}
  .toc {{ display:grid; gap:6px; }}
  .toc a {{ color:#304052; text-decoration:none; font-size:13px; line-height:1.45; }}
  article {{ min-width:0; background:var(--paper); border:1px solid var(--line); border-radius:8px; padding:42px min(6vw,72px); box-shadow:0 16px 40px rgba(29,47,78,.06); }}
  h1 {{ font-size:34px; line-height:1.25; margin:0 0 18px; }}
  h2 {{ font-size:25px; line-height:1.32; margin:42px 0 14px; }}
  h3 {{ font-size:20px; line-height:1.4; margin:30px 0 10px; }}
  p {{ margin:0 0 1.05em; }}
  ul {{ margin:0 0 1.1em 1.2em; padding:0; }}
  .book-figure {{ margin:32px auto; text-align:center; }}
  .book-figure img {{ display:block; max-width:100%; margin:0 auto; border:1px solid var(--line); border-radius:6px; background:#fff; }}
  .book-figure figcaption {{ color:var(--muted); font-size:14px; line-height:1.65; margin-top:10px; text-align:left; }}
  .r-code-card {{ background:var(--code); border:1px solid #b8dcff; border-radius:8px; margin:20px 0 26px; overflow:hidden; }}
  .code-toolbar {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:8px 12px; border-bottom:1px solid #c8e5ff; color:#24527d; font-size:13px; font-weight:700; }}
  .copy-code {{ border:1px solid #8cc6f3; background:#fff; color:#175487; border-radius:6px; padding:4px 9px; cursor:pointer; font:inherit; font-weight:600; }}
  .copy-code:focus-visible {{ outline:2px solid var(--accent); outline-offset:2px; }}
  pre {{ margin:0; padding:14px 16px 16px; overflow:auto; }}
  code {{ font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace; font-size:13px; line-height:1.65; }}
  .intro {{ margin-bottom:34px; padding-bottom:24px; border-bottom:1px solid var(--line); color:var(--muted); }}
  @media (max-width:900px) {{ .shell {{ display:block; padding:14px; }} aside {{ position:relative; max-height:260px; margin-bottom:18px; }} article {{ padding:28px 18px; }} h1 {{ font-size:28px; }} body {{ font-size:16px; }} }}
</style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <a class="brand" href="/">Chandler&#x27;s AI Productivity Notes</a>
    <span class="source-note">中文翻译：DeepSeek v4-flash；R 代码保留原文</span>
  </header>
  <aside><h2>目录</h2><nav class="toc">{toc}</nav></aside>
  <article>
    <h1>《使用 R 分析金融数据并实现金融模型》简体中文 HTML 版</h1>
    <p class="intro">原书：Analyzing Financial Data and Implementing Financial Models Using R，作者：Clifford S. Ang。本文按授权发布为中文 HTML 阅读版；图表保留原图，图注与正文翻译为简体中文，R 代码保留并提供复制按钮。</p>
    {body}
  </article>
</div>
<script>
document.addEventListener("click", async (event) => {{
  const button = event.target.closest(".copy-code");
  if (!button) return;
  const target = document.getElementById(button.dataset.codeTarget);
  if (!target) return;
  try {{
    await navigator.clipboard.writeText(target.textContent || "");
    const old = button.textContent;
    button.textContent = "已复制";
    setTimeout(() => button.textContent = old, 1400);
  }} catch (error) {{
    button.textContent = "复制失败";
  }}
}});
</script>
</body>
</html>
"""


def build_book_guide(client: DeepSeekClient, units: list[dict[str, Any]], force: bool = False) -> str:
    path = CACHE_DIR / "book_guide.json"
    if path.exists() and not force:
        return path.read_text(encoding="utf-8")
    sample = "\n\n".join(f"[p{u['page']}] {u['src']}" for u in units[:700])[:90_000]
    data = client.chat_json(
        "You are a senior financial translation editor. Return strict JSON.",
        {
            "task": (
                "Create a Simplified Chinese translation guide for this finance/R textbook. "
                "Return JSON fields: title_zh, style, glossary, keep_verbatim, code_policy, "
                "caption_policy, forbidden_phrases, review_checklist. Use professional finance, "
                "statistics, econometrics, and R programming terminology."
            ),
            "book": {"title": BOOK_TITLE_EN, "authors": BOOK_AUTHORS},
            "sample": sample,
        },
        temperature=0.05,
        retries=3,
    )
    write_json(path, data)
    return json.dumps(data, ensure_ascii=False, indent=2)


def chunk_units(units: list[dict[str, Any]], max_chars: int = 14_000) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    size = 0
    for unit in units:
        unit_size = len(unit["src"]) + 80
        if current and size + unit_size > max_chars:
            chunks.append(current)
            current = []
            size = 0
        current.append(unit)
        size += unit_size
    if current:
        chunks.append(current)
    return chunks


def translate_chunk(client: DeepSeekClient, guide: str, chunk: list[dict[str, Any]], chunk_index: int, force: bool = False) -> dict[str, str]:
    payload_hash = sha1_text(PROMPT_VERSION + client.model + json.dumps(chunk, ensure_ascii=False) + guide)
    cache_path = CACHE_DIR / "translations" / f"chunk-{chunk_index:04d}-{payload_hash[:10]}.json"
    if cache_path.exists() and not force:
        return {str(k): str(v) for k, v in read_json(cache_path).items()}
    system = (
        "You translate financial/statistical/R textbook HTML text units into fluent Simplified Chinese. "
        "Return strict JSON only. Preserve all numbers, dates, securities tickers, package names, function names, "
        "URLs, formulas, and proper nouns. Do not add commentary. Do not translate R code; code-like units have "
        "already been removed. Captions must be translated, but chart image labels remain original."
    )
    response = client.chat_json(
        system,
        {
            "guide": guide,
            "output_schema": {"units": [{"id": "same id", "tr": "Simplified Chinese translation"}]},
            "units": chunk,
        },
        temperature=0.06,
        retries=3,
    )
    if isinstance(response, list):
        items = response
    elif isinstance(response.get("result"), dict):
        items = response["result"].get("units", [])
    else:
        items = response.get("units", [])
    result = {str(item.get("id")): html.unescape(str(item.get("tr", "")).strip()) for item in items if item.get("id")}
    missing = {unit["id"] for unit in chunk} - set(result)
    if missing:
        raise RuntimeError(f"chunk {chunk_index} missing translations: {sorted(missing)[:10]}")
    write_json(cache_path, result)
    return result


def translate_chunk_resilient(
    client: DeepSeekClient,
    guide: str,
    chunk: list[dict[str, Any]],
    chunk_index: int,
    force: bool = False,
) -> dict[str, str]:
    try:
        return translate_chunk(client, guide, chunk, chunk_index, force=force)
    except RuntimeError as exc:
        if "missing translations" not in str(exc):
            raise
        if len(chunk) <= 1:
            return translate_single_unit_strict(client, guide, chunk[0], chunk_index, force=force)
        result: dict[str, str] = {}
        for offset, unit in enumerate(chunk, 1):
            result.update(
                translate_chunk_resilient(
                    client,
                    guide,
                    [unit],
                    chunk_index * 10_000 + offset,
                    force=force,
                )
            )
        return result


def translate_single_unit_strict(
    client: DeepSeekClient,
    guide: str,
    unit: dict[str, Any],
    chunk_index: int,
    force: bool = False,
) -> dict[str, str]:
    payload_hash = sha1_text(PROMPT_VERSION + client.model + "strict-single" + json.dumps(unit, ensure_ascii=False) + guide)
    cache_path = CACHE_DIR / "translations" / f"single-{chunk_index:06d}-{payload_hash[:10]}.json"
    if cache_path.exists() and not force:
        return {str(k): str(v) for k, v in read_json(cache_path).items()}
    response = client.chat_json(
        "Translate exactly one textbook text unit into Simplified Chinese. Return strict JSON with id and tr only.",
        {
            "guide": guide,
            "unit": unit,
            "required_output": {"id": unit["id"], "tr": "Simplified Chinese translation"},
            "rules": [
                "Return the same id verbatim.",
                "Translate faithfully; preserve numbers, formulas, tickers, function names, URLs, and proper nouns.",
                "Do not add notes or omit the unit.",
            ],
        },
        temperature=0.03,
        retries=4,
    )
    if isinstance(response, dict) and response.get("id") == unit["id"] and response.get("tr"):
        result = {unit["id"]: html.unescape(str(response["tr"]).strip())}
    elif isinstance(response, dict) and response.get("units"):
        items = response.get("units", [])
        result = {str(item.get("id")): html.unescape(str(item.get("tr", "")).strip()) for item in items if item.get("id")}
    else:
        result = {}
    if unit["id"] not in result:
        raise RuntimeError(f"strict single-unit translation missing id: {unit['id']}")
    write_json(cache_path, result)
    return result


def translate_units(client: DeepSeekClient, units: list[dict[str, Any]], guide: str, workers: int, force: bool = False) -> dict[str, str]:
    chunks = chunk_units(units)
    all_results: dict[str, str] = {}
    failures: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_map = {
            executor.submit(translate_chunk_resilient, client, guide, chunk, idx, force): idx
            for idx, chunk in enumerate(chunks, 1)
        }
        for future in concurrent.futures.as_completed(future_map):
            idx = future_map[future]
            try:
                all_results.update(future.result())
            except Exception as exc:
                failures.append(f"chunk {idx}: {exc}")
            if len(all_results) and len(all_results) % 500 < 30:
                print(f"[translate] translated={len(all_results)}/{len(units)} failures={len(failures)}", flush=True)
    if failures:
        raise RuntimeError("; ".join(failures[:5]))
    missing = {unit["id"] for unit in units} - set(all_results)
    if missing:
        raise RuntimeError(f"missing translations after merge: {len(missing)}")
    return all_results


def prepare_structure(source_pdf: Path, extract_dir: Path) -> dict[str, Any]:
    struct = read_json(extract_dir / "structure.json")
    struct = add_drawings_from_pdf(struct, source_pdf)
    write_json(CACHE_DIR / "structure-with-drawings.json", struct)
    return struct


def crop_figures(regions: list[dict[str, Any]], extract_dir: Path) -> dict[str, str]:
    dpi = int(read_json(extract_dir / "structure.json").get("meta", {}).get("render_dpi", 120))
    out_dir = CACHE_DIR / "figure-crops"
    assets: dict[str, str] = {}
    for region in regions:
        path = crop_region_from_page(region, extract_dir / "pages", out_dir, dpi)
        if not path:
            continue
        key = path.name
        region["asset"] = key
        assets[key] = image_data_uri(path)
    return assets


def write_blog_post() -> None:
    post = f"""---
title: "{BOOK_FULL_TITLE_ZH}"
date: {BLOG_DATE}
slug: {SLUG}
summary: "《{BOOK_TITLE_EN}》的简体中文 HTML 阅读版，保留原书图表与 R 代码，并为代码块提供复制按钮。"
tags: ["金融数据分析", "金融建模", "量化金融", "R"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇文章是《{BOOK_TITLE_EN}》简体中文 HTML 阅读版的入口。原书由 {BOOK_AUTHORS} 编写，覆盖金融数据分析、投资组合、风险、固定收益、期权、模拟与交易策略，并保留原书 R 代码。

> 说明：你已确认拥有完整授权；本译稿按授权用于个人 GitHub Pages 博客发布。

[打开完整中文 HTML 版](/{SLUG}/)
"""
    write_text(ROOT / "content" / "posts" / f"{BLOG_DATE}-{SLUG}.md", post)


def quality_report(html_path: Path, units: list[dict[str, Any]], translations: dict[str, str], regions: list[dict[str, Any]]) -> dict[str, Any]:
    raw = html_path.read_text(encoding="utf-8") if html_path.exists() else ""
    scan_raw = re.sub(r'data:image/[^"\']+', "data:image/removed", raw)
    report = {
        "html_exists": html_path.exists(),
        "translation_units": len(units),
        "translated_units": len(translations),
        "missing_translations": len({u["id"] for u in units} - set(translations)),
        "figure_regions": len(regions),
        "r_code_blocks": raw.count('class="r-code-card"'),
        "copy_buttons": raw.count('class="copy-code"'),
        "todo_markers": len(re.findall(r"TODO|待翻译|未翻译", scan_raw, flags=re.IGNORECASE)),
        "old_chapter_links": len(re.findall(rf"/{SLUG}/chapter-\d+/", raw)),
        "red_flags": sum(
            scan_raw.count(flag)
            for flag in [
                "The above code produces Figure",
                "Price data reproduced with permission",
                "Comparing Performance of Multiple Securities",
                "Data source:",
            ]
        ),
    }
    report["status"] = (
        "ready"
        if report["html_exists"]
        and report["missing_translations"] == 0
        and report["r_code_blocks"] == report["copy_buttons"]
        and report["todo_markers"] == 0
        and report["red_flags"] == 0
        else "fail"
    )
    write_json(CACHE_DIR / "quality_report.json", report)
    return report


def run_pipeline(args: argparse.Namespace) -> dict[str, Any]:
    source_pdf = Path(args.source_pdf)
    extract_dir = Path(args.extract_dir)
    struct = prepare_structure(source_pdf, extract_dir)
    units = prepare_translation_units(struct)
    write_json(CACHE_DIR / "units_src.json", units)
    client = DeepSeekClient(args.model, args.timeout, args.max_tokens)
    guide = build_book_guide(client, units, force=args.force_guide)
    translations_path = CACHE_DIR / "units_zh.json"
    if args.skip_translation and translations_path.exists():
        translations = {str(k): str(v) for k, v in read_json(translations_path).items()}
    else:
        translations = translate_units(client, units, guide, workers=args.workers, force=args.force_translation)
        write_json(translations_path, translations)
    regions = detect_figure_regions(struct)
    figure_assets = crop_figures(regions, extract_dir)
    out_path = ROOT / SLUG / "index.html"
    write_text(out_path, render_document_html(struct, translations, regions, figure_assets))
    write_blog_post()
    return quality_report(out_path, units, translations, regions)


def check_only(args: argparse.Namespace) -> dict[str, Any]:
    struct = read_json(CACHE_DIR / "structure-with-drawings.json")
    units = read_json(CACHE_DIR / "units_src.json")
    translations = read_json(CACHE_DIR / "units_zh.json") if (CACHE_DIR / "units_zh.json").exists() else {}
    regions = detect_figure_regions(struct)
    return quality_report(ROOT / SLUG / "index.html", units, translations, regions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate the Ang R finance PDF-to-HTML output and publish as a GitHub Pages HTML tutorial.")
    parser.add_argument("--source-pdf", default=r"C:\Users\Chandler\Downloads\Clifford S. Ang (auth.) - Analyzing Financial Data and Implementing Financial Models Using R (2021, Springer).pdf")
    parser.add_argument("--extract-dir", default=str(EXTRACT_DIR))
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--force-guide", action="store_true")
    parser.add_argument("--force-translation", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    report = check_only(args) if args.check_only else run_pipeline(args)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report.get("status") != "ready":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
