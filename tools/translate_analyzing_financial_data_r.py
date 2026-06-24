from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import html
import json
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from analyzing_financial_data_r_common import (
    BOOK_AUTHORS,
    BOOK_EDITION,
    BOOK_TITLE_EN,
    CACHE_NAME,
    SLUG,
    extract_page_text,
    is_omittable_pdf_page,
    read_json,
    render_r_code_block,
    replace_r_code_placeholders,
    sha1_text,
    strip_json_fence,
    strip_unapproved_img_tags,
    write_json,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / CACHE_NAME
SITE_TITLE = "Chandler's AI Productivity Notes"
PROMPT_VERSION = "ang-afd-r-v1.2"
BOOK_TITLE_ZH = "《使用 R 分析金融数据并实现金融模型》"
BOOK_FULL_TITLE_ZH = "《使用 R 分析金融数据并实现金融模型》简体中文教程"
BLOG_POST_DATE = "2026-06-24"

FALLBACK_TITLE_MAP = {
    "preface": "前言",
    "dedication": "献词",
    "acknowledgments": "致谢",
    "chapter-1": "第 1 章 价格",
    "chapter-2": "第 2 章 单个证券收益率",
    "chapter-3": "第 3 章 投资组合收益率",
    "chapter-4": "第 4 章 风险",
    "chapter-5": "第 5 章 因子模型",
    "chapter-6": "第 6 章 风险调整后的投资组合绩效指标",
    "chapter-7": "第 7 章 Markowitz 均值-方差优化",
    "chapter-8": "第 8 章 股票",
    "chapter-9": "第 9 章 固定收益",
    "chapter-10": "第 10 章 期权",
    "chapter-11": "第 11 章 模拟",
    "chapter-12": "第 12 章 交易策略",
    "appendix-a": "附录 A R 入门",
    "appendix-b": "附录 B 预加载代码",
    "appendix-c": "附录 C 构造假设投资组合（月度收益率）",
    "appendix-d": "附录 D 构造假设投资组合（日度收益率）",
    "index": "索引",
}
SECTION_FALLBACK_TITLE_MAP = {
    "2.8 Comparing Performance of Multiple Securities": "2.8 比较多种证券的表现",
    "Reference": "参考文献",
    "References": "参考文献",
}


class DeepSeekClient:
    def __init__(self, model: str, timeout: int, max_tokens: int) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    def chat_json(self, system: str, user: dict[str, Any], temperature: float = 0.1, retries: int = 3) -> dict[str, Any]:
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
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=data,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    raw = response.read().decode("utf-8")
                outer = json.loads(raw)
                content = outer["choices"][0]["message"].get("content", "")
                return loads_model_json(strip_json_fence(content))
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


def loads_model_json(content: str) -> dict[str, Any]:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        repaired = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", content)
        repaired = re.sub(r'\\(?!["\\/bfnrtu])', r"\\\\", repaired)
        return json.loads(repaired)


def asset_url(path: str) -> str:
    asset_path = ROOT / path.lstrip("/")
    version = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:12] if asset_path.exists() else "missing"
    return f"{path}?v={version}"


def guide_system_prompt() -> str:
    return (
        "You are a senior Simplified Chinese translator, quantitative finance editor, "
        "financial modeling editor, and R code-preservation technical editor. "
        "Return JSON only. Do not translate the whole book in this step."
    )


def build_book_guide(client: DeepSeekClient, manifest: dict[str, Any], force: bool = False) -> str:
    guide_md = CACHE_DIR / "book_guide.md"
    guide_json = CACHE_DIR / "book_guide.json"
    if guide_md.exists() and not force:
        return guide_md.read_text(encoding="utf-8")

    compact_extract = (CACHE_DIR / "compact_guide_extract.md").read_text(encoding="utf-8")[:120_000]
    terminology_seed = (CACHE_DIR / "TERMINOLOGY_SEED.md").read_text(encoding="utf-8")
    compact_manifest = {
        "book": manifest["book"],
        "site": manifest["site"],
        "units": [
            {
                "task_id": unit["task_id"],
                "kind": unit["kind"],
                "title_en": unit["title_en"],
                "slug": unit["slug"],
                "pdf_page_start": unit["pdf_page_start"],
                "pdf_page_end": unit["pdf_page_end"],
            }
            for unit in manifest["units"]
        ],
    }
    data = client.chat_json(
        guide_system_prompt(),
        {
            "task": (
                "Create a full-book Simplified Chinese translation guide. Return JSON fields: "
                "book_title_zh, translator_style, glossary, unit_title_map, notation_rules, "
                "math_rules, r_code_preservation_rules, figure_table_link_footnote_rules, html_rules, "
                "forbidden_visible_phrases, reviewer_checklist. "
                "Terminology must follow professional finance, quantitative finance, statistics, "
                "econometrics, fixed income, options, risk, portfolio, and trading conventions. "
                "R code must be preserved, not converted to Python."
            ),
            "manifest": compact_manifest,
            "terminology_seed": terminology_seed,
            "compact_guide_extract": compact_extract,
        },
        temperature=0.06,
        retries=3,
    )
    write_json(guide_json, data)
    guide_text = json.dumps(data, ensure_ascii=False, indent=2)
    write_text(guide_md, guide_text)
    return guide_text


def unit_for_page(units: list[dict[str, Any]], page_number: int) -> dict[str, Any] | None:
    for unit in units:
        if int(unit["pdf_page_start"]) <= page_number <= int(unit["pdf_page_end"]):
            return unit
    return None


def build_page_payload(page_number: int, page_text: str, manifest: dict[str, Any], image_map: dict[str, Any]) -> dict[str, Any]:
    unit = unit_for_page(manifest["units"], page_number) or {}
    sections = [
        section
        for section in unit.get("sections", [])
        if int(section.get("pdf_page") or -1) == page_number
    ]
    captions = [item for item in image_map.get("captions", []) if int(item.get("pdf_page", -1)) == page_number]
    images = [item for item in image_map.get("images", []) if int(item.get("pdf_page", -1)) == page_number]
    return {
        "page_number": page_number,
        "unit": {
            "task_id": unit.get("task_id", ""),
            "kind": unit.get("kind", ""),
            "title_en": unit.get("title_en", ""),
            "slug": unit.get("slug", ""),
            "pdf_page_start": unit.get("pdf_page_start", ""),
            "pdf_page_end": unit.get("pdf_page_end", ""),
        },
        "sections_starting_on_page": sections,
        "source_text": strip_source_boilerplate(page_text),
        "captions_on_page": captions,
        "images_on_page": [
            {
                "id": image.get("id"),
                "number": image.get("number"),
                "target_asset_path": image.get("target_asset_path"),
                "caption_id": image.get("caption_id"),
                "text_en": image.get("text_en"),
            }
            for image in images
        ],
    }


def strip_source_boilerplate(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    skip_next = 0
    for raw in lines:
        line = " ".join(raw.replace("\u00a0", " ").split())
        lower = line.lower()
        if skip_next:
            skip_next -= 1
            continue
        if "© the editor" in lower or "exclusive license to springer nature" in lower:
            skip_next = 4
            continue
        if lower.startswith("clifford s. ang"):
            skip_next = 3
            continue
        if lower.startswith("doi 10.1007"):
            continue
        if lower in {"springer texts in business and economics"}:
            continue
        if re.fullmatch(r"\d{1,4}", line) and cleaned:
            continue
        cleaned.append(raw)
    return "\n".join(cleaned)


def page_translation_system_prompt(book_guide: str) -> str:
    return (
        "你是金融工程、统计学、统计学习与计量金融教材的资深简体中文译者和技术编辑。只返回 JSON。"
        "请把单个 PDF 页面的英文内容译成可发布的中文 HTML 片段，风格应像中文技术教程而不是机器翻译稿。"
        "必须翻译练习题、图题、表题、脚注、页内说明；保留人名、数据集名、R 包名、函数名、变量名和参考文献必要英文。"
        "数学公式必须用标准 LaTeX，行内用 \\(...\\)，展示公式用 \\[...\\]；不要翻译数学符号本身。"
        "如果页面包含 R 代码，HTML 中放 [[R_CODE:code-id]] 占位符，并在 r_code_blocks 中给出原始 R 代码。"
        "R_CODE 占位符必须独占一行，不能放进 <p>、<pre> 或 <code> 内。"
        "保留 R 代码，不要改写为 Python，不要新增 Python 代码块。"
        "凡是源文本中以 R 控制台提示符 > 或 + 开头、带行号的 R 代码/输出、或包含 [1] 这类 R 输出标记的内容，都必须拆成 r_code_blocks；不要把代码和中文解释揉在同一个段落里。"
        "如果 images_on_page 非空，图中的坐标刻度、轴标题、图内英文标题属于图片像素，不要作为正文段落输出；只插入 supplied 图片并翻译 figcaption。"
        "不要在读者可见内容中写“Python 转写”“由于原文使用 R”“迁移说明”“TODO”等。"
        "如果页面有 footnotes，请用 sup/a 和 ol.footnotes 生成可点击跳转与返回链接，id/href 必须稳定。"
        "如果 images_on_page 非空，请在合适位置插入 supplied target_asset_path；图片用 <figure class=\"book-figure\"> 居中，并翻译 figcaption。"
        "HTML 必须包在 <section class=\"book-page\" data-pdf-page=\"N\">...</section> 中。"
        "sections_starting_on_page 中给出的标题若出现在本页，请将对应标题 id 精确设为该 section.slug。"
        "全书翻译指南如下：\n"
        + book_guide[:70_000]
    )


def caption_lookup(captions: list[dict[str, Any]], translated: Any) -> dict[str, str]:
    lookup = {str(caption.get("id")): str(caption.get("text_en", "")) for caption in captions}
    if isinstance(translated, list):
        for item in translated:
            if isinstance(item, dict) and item.get("id") and item.get("text_zh"):
                lookup[str(item["id"])] = str(item["text_zh"])
    return lookup


def ensure_page_section(fragment: str, page_number: int) -> str:
    if re.search(r'<section\b[^>]*class=["\'][^"\']*\bbook-page\b', fragment):
        return fragment
    return f'<section class="book-page" data-pdf-page="{page_number}">\n{fragment}\n</section>'


def unwrap_block_placeholders(fragment: str) -> str:
    fragment = re.sub(r"<pre><code(?:\s+class=[\"'][^\"']*[\"'])?>\s*(\[\[R_CODE:[^\]]+\]\])\s*</code></pre>", r"\1", fragment)
    fragment = re.sub(r"<p>\s*(\[\[R_CODE:[^\]]+\]\])\s*</p>", r"\1", fragment)
    fragment = re.sub(r"<p>\s*(<figure\b)", r"\1", fragment)
    fragment = re.sub(r"(</figure>)\s*</p>", r"\1", fragment)
    return fragment


def unwrap_embedded_code_tabs(fragment: str) -> str:
    return re.sub(
        r"<pre><code(?:\s+class=[\"'][^\"']*[\"'])?>\s*(<div class=\"code-tabs\"[\s\S]*?</div>)\s*</code></pre>",
        r"\1",
        fragment,
    )


def namespace_page_footnotes(fragment: str, page_number: int) -> str:
    page_key = f"p{page_number:03d}"

    def rewrite_fn_id(match: re.Match[str]) -> str:
        prefix, quote, name, number = match.groups()
        return f'{prefix}{quote}{name}-{page_key}-{number}{quote}'

    fragment = re.sub(r'(\bid\s*=\s*)(["\'])(fnref)(\d+)\2', rewrite_fn_id, fragment)
    fragment = re.sub(r'(\bid\s*=\s*)(["\'])(fn)(\d+)\2', rewrite_fn_id, fragment)

    def rewrite_href(match: re.Match[str]) -> str:
        prefix, quote, name, number = match.groups()
        return f'{prefix}{quote}#{name}-{page_key}-{number}{quote}'

    fragment = re.sub(r'(\bhref\s*=\s*)(["\'])#(fnref)(\d+)\2', rewrite_href, fragment)
    fragment = re.sub(r'(\bhref\s*=\s*)(["\'])#(fn)(\d+)\2', rewrite_href, fragment)
    return fragment


def strip_visible_boilerplate(fragment: str) -> str:
    patterns = [
        r"(?is)<p[^>]*>[^<]*(?:Springer Nature|Springer Texts in Business and Economics|DOI\s*10\.1007|Clifford\s+S\.\s+Ang|exclusive license)[^<]*</p>",
        r"(?is)<p[^>]*>\s*\d{1,4}\s*</p>",
    ]
    for pattern in patterns:
        fragment = re.sub(pattern, "", fragment)
    return fragment


def separate_adjacent_blocks(fragment: str) -> str:
    block_tags = r"(?:p|div|section|figure|figcaption|table|thead|tbody|tr|td|th|ol|ul|li|blockquote|pre|h[1-6]|nav)"
    fragment = re.sub(rf"(</{block_tags}>)(\s*)(<(?={block_tags}\b))", r"\1\n\3", fragment, flags=re.IGNORECASE)
    fragment = re.sub(rf"(<h[1-6]\b[^>]*>)(\s*)", r"\1", fragment, flags=re.IGNORECASE)
    return fragment


def strip_spurious_unit_h1(fragment: str, page_number: int, payload: dict[str, Any]) -> str:
    try:
        unit_start = int(payload.get("unit", {}).get("pdf_page_start") or 0)
    except Exception:
        unit_start = 0
    if unit_start and page_number != unit_start:
        fragment = re.sub(r"(?is)<h1\b[^>]*>.*?</h1>", "", fragment)
    return fragment


def ensure_page_images(fragment: str, images: list[dict[str, Any]], captions: list[dict[str, Any]], captions_zh: Any) -> str:
    if not images:
        return fragment
    cap_lookup = caption_lookup(captions, captions_zh)
    additions: list[str] = []
    for image in images:
        src = str(image.get("target_asset_path") or "")
        if not src or src in fragment:
            continue
        caption = cap_lookup.get(str(image.get("caption_id")), str(image.get("text_en") or ""))
        figure_id = f"fig-{image.get('number')}" if image.get("number") else ""
        id_attr = f' id="{html.escape(figure_id, quote=True)}"' if figure_id else ""
        additions.append(
            f'<figure class="book-figure"{id_attr}>'
            f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(caption, quote=True)}" loading="lazy">'
            f'<figcaption>{html.escape(caption)}</figcaption>'
            "</figure>"
        )
    if not additions:
        return fragment
    closing = re.search(r"</section>\s*$", fragment)
    if closing:
        return fragment[: closing.start()] + "\n" + "\n".join(additions) + "\n" + fragment[closing.start() :]
    return fragment + "\n" + "\n".join(additions)


def clean_fragment(fragment: str, page_number: int, payload: dict[str, Any], response: dict[str, Any]) -> str:
    fragment = unwrap_block_placeholders(str(fragment).strip())
    fragment = replace_r_code_placeholders(str(fragment).strip(), response.get("r_code_blocks", []) if isinstance(response.get("r_code_blocks"), list) else [])
    fragment = unwrap_embedded_code_tabs(fragment)
    fragment = strip_unapproved_img_tags(fragment, (f"/assets/img/{SLUG}/",))
    fragment = strip_visible_boilerplate(fragment)
    fragment = namespace_page_footnotes(fragment, page_number)
    fragment = ensure_page_section(fragment, page_number)
    fragment = ensure_page_images(
        fragment,
        payload.get("images_on_page", []),
        payload.get("captions_on_page", []),
        response.get("captions_zh", []),
    )
    fragment = strip_spurious_unit_h1(fragment, page_number, payload)
    fragment = separate_adjacent_blocks(fragment)
    return fragment


def translate_page(
    page_number: int,
    page_text: str,
    manifest: dict[str, Any],
    image_map: dict[str, Any],
    book_guide: str,
    client_config: dict[str, Any],
    force: bool = False,
) -> dict[str, Any]:
    page_dir = CACHE_DIR / "page_translations"
    page_dir.mkdir(parents=True, exist_ok=True)
    payload = build_page_payload(page_number, page_text, manifest, image_map)
    cache_key = sha1_text(
        json.dumps(
            {
                "prompt_version": PROMPT_VERSION,
                "model": client_config["model"],
                "payload": payload,
                "guide_hash": sha1_text(book_guide),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    cache_path = page_dir / f"page-{page_number:03d}.json"
    if cache_path.exists() and not force:
        cached = read_json(cache_path)
        if cached.get("input_hash") == cache_key and cached.get("html"):
            return cached

    client = DeepSeekClient(
        model=client_config["model"],
        timeout=client_config["timeout"],
        max_tokens=client_config["max_tokens"],
    )
    data = client.chat_json(
        page_translation_system_prompt(book_guide),
        {
            "task": (
                "Translate this PDF page into Simplified Chinese HTML. Return JSON fields: "
                "html, r_code_blocks, title_zh_if_page_starts_unit, captions_zh, warnings. "
                "For r_code_blocks use objects with fields id and r_code. "
                "Preserve original R code in r_code as closely as PDF extraction allows. "
                "Do not convert R code to Python and do not create Python code blocks. "
                "Move every R console prompt/output line into r_code_blocks, including numbered lines, continuation lines, and [1] output lines. "
                "Do not emit chart tick labels, chart titles, or axis labels as prose when the page has images_on_page; the image already contains those pixels. "
                "Do not omit exercises, code, captions, footnotes, formulas, references, or links on the page."
            ),
            "page": payload,
        },
        temperature=0.08,
        retries=3,
    )
    result = {
        "page_number": page_number,
        "input_hash": cache_key,
        "translated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "html": clean_fragment(str(data.get("html", "")).strip(), page_number, payload, data),
        "r_code_blocks": data.get("r_code_blocks", []),
        "title_zh_if_page_starts_unit": str(data.get("title_zh_if_page_starts_unit", "")).strip(),
        "captions_zh": data.get("captions_zh", []),
        "warnings": data.get("warnings", []),
    }
    if not result["html"]:
        raise RuntimeError(f"DeepSeek returned empty html for page {page_number}")
    write_json(cache_path, result)
    return result


def translate_all_pages(
    manifest: dict[str, Any],
    image_map: dict[str, Any],
    book_guide: str,
    model: str,
    workers: int,
    timeout: int,
    max_tokens: int,
    force: bool,
    only_pages: list[int] | None = None,
) -> None:
    pdf_path = Path(manifest["book"]["source_pdf"])
    reader = PdfReader(str(pdf_path))
    selected_pages = set(only_pages or [])
    candidate_pages: list[int] = []
    for unit in manifest["units"]:
        for page in range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1):
            if selected_pages and page not in selected_pages:
                continue
            candidate_pages.append(page)
    page_texts = {
        page: text
        for page in candidate_pages
        if not is_omittable_pdf_page(text := extract_page_text(reader, page))
    }
    pages = list(page_texts)
    client_config = {"model": model, "timeout": timeout, "max_tokens": max_tokens}
    progress_path = CACHE_DIR / "progress.json"
    progress = read_json(progress_path) if progress_path.exists() else {}
    progress.update(
        {
            "status": "translating_pages",
            "model": model,
            "page_total": len(pages),
            "page_done": 0,
            "page_failed": 0,
            "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    write_json(progress_path, progress)

    failures: list[dict[str, Any]] = []
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        future_to_page = {
            executor.submit(
                translate_page,
                page,
                page_texts[page],
                manifest,
                image_map,
                book_guide,
                client_config,
                force,
            ): page
            for page in pages
        }
        for future in concurrent.futures.as_completed(future_to_page):
            page = future_to_page[future]
            try:
                future.result()
                completed += 1
            except Exception as exc:
                failures.append({"page": page, "error": str(exc)[:1000]})
            progress.update(
                {
                    "page_done": completed,
                    "page_failed": len(failures),
                    "failed_pages": failures[-20:],
                    "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            )
            write_json(progress_path, progress)
            if completed % 20 == 0 or failures:
                print(f"[translate] done={completed}/{len(pages)} failed={len(failures)}", flush=True)

    if failures:
        progress["status"] = "translation_failed"
        write_json(progress_path, progress)
        raise RuntimeError(f"{len(failures)} page translations failed; see {progress_path}")
    progress["status"] = "pages_translated"
    write_json(progress_path, progress)


def extract_title_map(book_guide: str) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        data = json.loads(book_guide)
    except Exception:
        data = {}
    candidates = data.get("unit_title_map") or data.get("chapter_title_map") or data.get("title_map") or {}
    if isinstance(candidates, dict):
        for key, value in candidates.items():
            if isinstance(value, str):
                result[str(key)] = value
            elif isinstance(value, dict):
                slug = value.get("slug") or value.get("task_id") or key
                title = value.get("title_zh") or value.get("zh") or value.get("Chinese")
                if title:
                    result[str(slug)] = str(title)
    return result


def title_for_unit(unit: dict[str, Any], title_map: dict[str, str]) -> str:
    return title_map.get(str(unit["slug"])) or title_map.get(str(unit["title_en"])) or FALLBACK_TITLE_MAP.get(str(unit["slug"])) or str(unit["title_en"])


def normalize_section_title(title: str) -> str:
    title = " ".join(str(title).split())
    if title in SECTION_FALLBACK_TITLE_MAP:
        return SECTION_FALLBACK_TITLE_MAP[title]
    return title


def title_for_section(section: dict[str, Any], section_title_map: dict[str, str]) -> str:
    slug = str(section.get("slug", ""))
    if slug in section_title_map:
        return normalize_section_title(section_title_map[slug])
    return normalize_section_title(str(section.get("title_en", "")))


def render_nav(active: str = "posts") -> str:
    items = [
        ("home", "/", "首页"),
        ("posts", "/posts/", "最新文章"),
        ("tags", "/tags/", "主题"),
        ("about", "/about/", "关于"),
    ]
    return "\n".join(
        f'<a href="{href}"{" aria-current=\"page\"" if key == active else ""}>{label}</a>'
        for key, href, label in items
    )


def mathjax_script() -> str:
    return r"""
  <script>
    window.MathJax = {
      tex: {
        inlineMath: [["$", "$"], ["\\(", "\\)"]],
        displayMath: [["$$", "$$"], ["\\[", "\\]"]],
        processEscapes: true
      },
      svg: { fontCache: "global" }
    };
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>"""


def render_shell(title: str, description: str, body: str, sidebar: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <title>{html.escape(title)} | {html.escape(SITE_TITLE)}</title>
  <link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{asset_url('/assets/css/styles.css')}">
  {mathjax_script()}
</head>
<body>
  <a class="skip-link" href="#content">跳到正文</a>
  <header class="site-header">
    <a class="brand" href="/" aria-label="{html.escape(SITE_TITLE)} 首页">
      <span class="brand-mark">C</span>
      <span class="brand-name">{html.escape(SITE_TITLE)}</span>
    </a>
    <nav class="site-nav" aria-label="主导航">
      {render_nav("posts")}
    </nav>
  </header>
  <main id="content" class="tutorial-page">
    <div class="tutorial-layout">
      {sidebar}
      <article class="tutorial-content">
        {body}
      </article>
    </div>
  </main>
  <footer class="site-footer">
    <div>
      <strong>AI 提效研究笔记</strong>
      <p>把阶段性沉淀整理成可以公开分享、持续复用的文章。</p>
    </div>
    <div class="footer-links">
      <a href="/feed.xml">RSS</a>
      <a href="https://github.com/ChandlerBBT/ChandlerBBT.github.io">GitHub</a>
    </div>
  </footer>
  <script src="{asset_url('/assets/js/site.js')}"></script>
</body>
</html>"""


def unit_local_path(unit: dict[str, Any]) -> str:
    return f"/{SLUG}/{unit['slug']}/"


def render_sidebar(
    units: list[dict[str, Any]],
    title_map: dict[str, str],
    current_slug: str | None = None,
    section_title_map: dict[str, str] | None = None,
) -> str:
    section_title_map = section_title_map or {}
    links = [
        '<div class="sidebar-item"><div class="sidebar-page-row">'
        f'<a class="sidebar-page-link" href="/{SLUG}/">首页</a>'
        '<span class="sidebar-toggle-placeholder" aria-hidden="true"></span></div></div>'
    ]
    for unit in units:
        title = title_for_unit(unit, title_map)
        current = unit["slug"] == current_slug
        current_attr = ' aria-current="page"' if current else ""
        section_links = ""
        toggle = '<span class="sidebar-toggle-placeholder" aria-hidden="true"></span>'
        panel = ""
        sections = unit.get("sections", [])
        if sections:
            panel_id = f"sidebar-sections-{html.escape(str(unit['slug']), quote=True)}"
            toggle = (
                f'<button class="sidebar-toggle" type="button" aria-expanded="{str(current).lower()}" '
                f'aria-controls="{panel_id}" aria-label="{"收起" if current else "展开"}{html.escape(title, quote=True)}二级目录">'
                '<span aria-hidden="true">›</span></button>'
            )
            section_links = "".join(
                f'<a class="section-link" href="{("#" if current else unit_local_path(unit) + "#")}{html.escape(str(section["slug"]), quote=True)}">{html.escape(title_for_section(section, section_title_map))}</a>'
                for section in sections
            )
            panel = f'<div class="sidebar-subsections" id="{panel_id}"{"" if current else " hidden"}>{section_links}</div>'
        links.append(
            f'<div class="sidebar-item{" is-current is-open" if current else ""}">'
            '<div class="sidebar-page-row">'
            f'<a class="sidebar-page-link" href="{unit_local_path(unit)}"{current_attr}>{html.escape(title)}</a>'
            f"{toggle}</div>{panel}</div>"
        )
    return f"""
<aside class="tutorial-sidebar">
  <div class="sidebar-heading">
    <h2>书籍目录</h2>
    <div class="sidebar-actions" aria-label="二级目录控制">
      <button type="button" data-sidebar-action="expand">全部展开</button>
      <button type="button" data-sidebar-action="collapse">全部收起</button>
    </div>
  </div>
  <nav class="sidebar-list">{''.join(links)}</nav>
</aside>
"""


def copy_images(image_map: dict[str, Any]) -> None:
    target_dir = ROOT / "assets" / "img" / SLUG
    target_dir.mkdir(parents=True, exist_ok=True)
    for image in image_map.get("images", []):
        cache_file = CACHE_DIR / str(image.get("cache_file", ""))
        if not cache_file.exists():
            continue
        filename = Path(str(image.get("target_asset_path", ""))).name
        if filename:
            shutil.copy2(cache_file, target_dir / filename)


def expected_pages_for_unit(unit: dict[str, Any], reader: PdfReader | None = None) -> list[int]:
    pages = list(range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1))
    if reader is None:
        return pages
    return [page for page in pages if not is_omittable_pdf_page(extract_page_text(reader, page))]


def load_page_html(page_number: int) -> str | None:
    path = CACHE_DIR / "page_translations" / f"page-{page_number:03d}.json"
    if not path.exists():
        return None
    return final_render_cleanup(str(read_json(path).get("html", "")).strip())


P_TAG_RE = re.compile(r"(?is)<p\b[^>]*>(.*?)</p>")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
LEADING_R_CONSOLE_RE = re.compile(
    r"^\s*(?:\d{1,3}\s*)?(?:&gt;|>|\+|\[\d+\]|[A-Za-z][A-Za-z0-9_.]*\s{2,}|[A-Za-z][A-Za-z0-9_.]*\s+[-−0-9])"
)
CHART_ARTIFACT_RE = re.compile(
    r"\b(?:Yields From|Date Yield|Value of|Investment|Treasury|Securities|Price|Returns|Portfolio|Percent|Years to Maturity|Simulated|Density)\b",
    re.IGNORECASE,
)
SOURCE_CREDIT_REPLACEMENTS = {
    "Price data reproduced with permission of CSI ©2020. www.csidata.com": "价格数据经 CSI ©2020 授权转载。www.csidata.com",
}


def html_to_text(fragment: str) -> str:
    return html.unescape(" ".join(re.sub(r"(?is)<[^>]+>", " ", fragment).split()))


def split_leading_r_code_paragraphs(fragment: str) -> str:
    def replace(match: re.Match[str]) -> str:
        text = html_to_text(match.group(1))
        if not LEADING_R_CONSOLE_RE.match(text):
            return match.group(0)
        cjk = CJK_RE.search(text)
        if cjk and cjk.start() > 0:
            code_text = text[: cjk.start()].strip()
            prose = text[cjk.start() :].strip()
        else:
            code_text = text.strip()
            prose = ""
        if len(code_text) < 3:
            return match.group(0)
        code_id = "post-r-" + sha1_text(code_text)[:12]
        output = render_r_code_block(code_id, code_text)
        if prose:
            prose = re.sub(r"\bStep\s+(\d+)\s*:", r"步骤\1：", prose)
            output += "\n<p>" + html.escape(prose) + "</p>"
        return output

    return P_TAG_RE.sub(replace, fragment)


def remove_chart_artifact_paragraphs(fragment: str) -> str:
    if "<figure" not in fragment:
        return fragment

    def replace(match: re.Match[str]) -> str:
        text = html_to_text(match.group(1))
        if CJK_RE.search(text):
            return match.group(0)
        if re.fullmatch(r"[0-9−\-.,% /]+", text) or CHART_ARTIFACT_RE.search(text):
            return ""
        return match.group(0)

    return P_TAG_RE.sub(replace, fragment)


def normalize_source_credits(fragment: str) -> str:
    for source, target in SOURCE_CREDIT_REPLACEMENTS.items():
        fragment = fragment.replace(source, target)
    return fragment


def final_render_cleanup(fragment: str) -> str:
    fragment = split_leading_r_code_paragraphs(fragment)
    fragment = remove_chart_artifact_paragraphs(fragment)
    fragment = normalize_source_credits(fragment)
    return separate_adjacent_blocks(fragment)


def sections_by_page(unit: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for section in unit.get("sections", []):
        try:
            page = int(section.get("pdf_page"))
        except Exception:
            continue
        result.setdefault(page, []).append(section)
    return result


def extract_section_title_map_from_translations(units: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    wanted = {
        str(section.get("slug"))
        for unit in units
        for section in unit.get("sections", [])
        if str(section.get("slug", "")).strip()
    }
    if not wanted:
        return result
    heading_re = re.compile(r'(?is)<h[1-6]\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>(.*?)</h[1-6]>')
    anchor_heading_re = re.compile(
        r'(?is)<span\b[^>]*\bid=["\']([^"\']+)["\'][^>]*>\s*</span>\s*<h[1-6]\b[^>]*>(.*?)</h[1-6]>'
    )

    def store_heading(slug: str, body: str) -> None:
        if slug not in wanted or slug in result:
            return
        text = normalize_section_title(html_to_text(body))
        if text:
            result[slug] = text

    for path in sorted((CACHE_DIR / "page_translations").glob("page-*.json")):
        fragment = str(read_json(path).get("html", ""))
        for slug, body in heading_re.findall(fragment):
            store_heading(slug, body)
        for slug, body in anchor_heading_re.findall(fragment):
            store_heading(slug, body)
    return result


def with_section_anchors(fragment: str, sections: list[dict[str, Any]]) -> str:
    anchors: list[str] = []
    for section in sections:
        slug = str(section.get("slug", "")).strip()
        if not slug or re.search(rf'\bid\s*=\s*["\']{re.escape(slug)}["\']', fragment):
            continue
        anchors.append(f'<span class="section-anchor" id="{html.escape(slug, quote=True)}"></span>')
    if not anchors:
        return fragment
    return "\n".join(anchors) + "\n" + fragment


def with_figure_anchors(fragment: str, images: list[dict[str, Any]]) -> str:
    for image in images:
        src = str(image.get("target_asset_path") or "")
        number = str(image.get("number") or "").strip()
        if not src or not number:
            continue
        figure_id = f"fig-{number}"
        if re.search(rf'\bid\s*=\s*["\']{re.escape(figure_id)}["\']', fragment):
            continue
        escaped_src = re.escape(html.escape(src, quote=True))
        pattern = rf'(<figure\b(?![^>]*\bid=)(?=[^>]*class=["\'][^"\']*\bbook-figure\b)[^>]*>\s*<img\b[^>]*src=["\']{escaped_src}["\'])'
        fragment = re.sub(pattern, rf'<figure class="book-figure" id="{html.escape(figure_id, quote=True)}"><img src="{html.escape(src, quote=True)}"', fragment, count=1)
    return fragment


def render_book(manifest: dict[str, Any], image_map: dict[str, Any], book_guide: str, allow_partial: bool = False) -> dict[str, Any]:
    copy_images(image_map)
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    section_title_map = extract_section_title_map_from_translations(units)
    reader = PdfReader(str(Path(manifest["book"]["source_pdf"])))
    book_dir = ROOT / SLUG
    book_dir.mkdir(parents=True, exist_ok=True)

    toc = "\n".join(
        f'<li><a href="{unit_local_path(unit)}">{html.escape(title_for_unit(unit, title_map))}</a></li>'
        for unit in units
    )
    index_body = f"""
<h1>{html.escape(BOOK_FULL_TITLE_ZH)}</h1>
<div class="license-note">
  <p>本教程基于 {html.escape(BOOK_AUTHORS)} 的 <em>{html.escape(BOOK_TITLE_EN)}</em>（{html.escape(BOOK_EDITION)}）整理翻译。你已确认拥有完整授权，本页按授权用于个人 GitHub Pages 博客发布。</p>
</div>
<p>本书围绕金融市场数据分析和金融模型实现展开，覆盖价格、单个证券收益率、投资组合收益率、风险、因子模型、风险调整绩效、Markowitz 均值-方差优化、股票、固定收益、期权、模拟和交易策略等主题。所有 R 示例均按授权保留为 R 代码，图片像素不翻译，图注和正文说明译为简体中文。</p>
<h2>目录</h2>
<ol>{toc}</ol>
"""
    write_text(book_dir / "index.html", render_shell(BOOK_TITLE_ZH, BOOK_FULL_TITLE_ZH, index_body, render_sidebar(units, title_map, section_title_map=section_title_map)))

    missing_pages: list[int] = []
    for index, unit in enumerate(units):
        title_zh = title_for_unit(unit, title_map)
        parts = [f"<h1>{html.escape(title_zh)}</h1>"]
        unit_sections_by_page = sections_by_page(unit)
        for page in expected_pages_for_unit(unit, reader):
            fragment = load_page_html(page)
            if fragment is None:
                missing_pages.append(page)
                if allow_partial:
                    continue
                continue
            page_images = [image for image in image_map.get("images", []) if int(image.get("pdf_page", -1)) == page]
            fragment = with_figure_anchors(fragment, page_images)
            parts.append(with_section_anchors(fragment, unit_sections_by_page.get(page, [])))
        prev_unit = units[index - 1] if index > 0 else None
        next_unit = units[index + 1] if index + 1 < len(units) else None
        nav = ['<nav class="chapter-nav">']
        nav.append(
            f'<a href="{unit_local_path(prev_unit)}">上一节：{html.escape(title_for_unit(prev_unit, title_map))}</a>'
            if prev_unit
            else "<span></span>"
        )
        if next_unit:
            nav.append(f'<a href="{unit_local_path(next_unit)}">下一节：{html.escape(title_for_unit(next_unit, title_map))}</a>')
        nav.append("</nav>")
        parts.append("".join(nav))
        write_text(
            book_dir / str(unit["slug"]) / "index.html",
            render_shell(title_zh, f"{title_zh} | {BOOK_TITLE_ZH}", "\n".join(parts), render_sidebar(units, title_map, str(unit["slug"]), section_title_map)),
        )

    if missing_pages and not allow_partial:
        raise RuntimeError(f"Missing {len(missing_pages)} translated pages; rerun with --allow-partial to render partial output.")
    return {"missing_translated_pages": missing_pages}


def write_blog_post(manifest: dict[str, Any], book_guide: str) -> Path:
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    toc = "\n".join(f"- [{title_for_unit(unit, title_map)}]({unit_local_path(unit)})" for unit in units)
    today = BLOG_POST_DATE
    path = ROOT / "content" / "posts" / f"{today}-{SLUG}.md"
    post = f"""---
title: "{BOOK_FULL_TITLE_ZH}"
date: {today}
summary: "《{BOOK_TITLE_EN}》的简体中文教程入口，覆盖金融数据分析、投资组合、固定收益、期权、模拟与交易策略，并保留原书 R 代码。"
tags: ["金融数据分析", "金融建模", "量化金融", "R"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇文章是《{BOOK_TITLE_EN}》简体中文教程的入口。原书由 {BOOK_AUTHORS} 编写，系统讲解金融市场数据的统计分析方法。

> 说明：你已确认拥有完整授权；本译稿按授权用于个人 GitHub Pages 博客发布。

## 书籍入口

[打开完整分章节教程](/{SLUG}/)

## 目录

{toc}
"""
    write_text(path, post)
    return path


def write_quality_report(manifest: dict[str, Any], image_map: dict[str, Any], render_stats: dict[str, Any] | None = None) -> dict[str, Any]:
    render_stats = render_stats or {}
    reader = PdfReader(str(Path(manifest["book"]["source_pdf"])))
    expected_pages: list[int] = []
    for unit in manifest["units"]:
        expected_pages.extend(expected_pages_for_unit(unit, reader))
    page_dir = CACHE_DIR / "page_translations"
    missing_pages = [page for page in expected_pages if not (page_dir / f"page-{page:03d}.json").exists()]
    book_pages = list((ROOT / SLUG).glob("**/index.html"))
    asset_missing = []
    for image in image_map.get("images", []):
        filename = Path(str(image.get("target_asset_path", ""))).name
        if filename and not (ROOT / "assets" / "img" / SLUG / filename).exists():
            asset_missing.append(filename)
    report = {
        "status": "ready" if not missing_pages and not asset_missing else "incomplete",
        "translation_units": len(manifest["units"]),
        "expected_translated_pages": len(expected_pages),
        "missing_translated_pages_count": len(missing_pages),
        "missing_translated_pages": missing_pages[:200],
        "book_pages_generated": len(book_pages),
        "image_records": len(image_map.get("images", [])),
        "missing_asset_files_count": len(set(asset_missing)),
        "render_missing_pages_count": len(render_stats.get("missing_translated_pages", [])),
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(CACHE_DIR / "quality_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate and render the Ang financial data and R modeling Chinese book pages.")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"))
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--force-guide", action="store_true")
    parser.add_argument("--force-pages", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--only-pages", nargs="*", type=int, default=[])
    args = parser.parse_args()

    manifest = read_json(CACHE_DIR / "manifest.json")
    image_map = read_json(CACHE_DIR / "image_caption_map.json")
    if args.skip_translation:
        guide_path = CACHE_DIR / "book_guide.md"
        book_guide = guide_path.read_text(encoding="utf-8") if guide_path.exists() else "{}"
    else:
        client = DeepSeekClient(args.model, args.timeout, args.max_tokens)
        book_guide = build_book_guide(client, manifest, force=args.force_guide)
        translate_all_pages(
            manifest,
            image_map,
            book_guide,
            model=args.model,
            workers=args.workers,
            timeout=args.timeout,
            max_tokens=args.max_tokens,
            force=args.force_pages,
            only_pages=args.only_pages,
        )

    render_stats: dict[str, Any] = {}
    if not args.no_render:
        render_stats = render_book(manifest, image_map, book_guide, allow_partial=args.allow_partial)
        if not render_stats.get("missing_translated_pages"):
            write_blog_post(manifest, book_guide)
    report = write_quality_report(manifest, image_map, render_stats)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
