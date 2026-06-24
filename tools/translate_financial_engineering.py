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

from financial_engineering_common import (
    BOOK_AUTHORS,
    BOOK_EDITION,
    BOOK_TITLE_EN,
    CACHE_NAME,
    SLUG,
    extract_page_text,
    is_omittable_pdf_page,
    read_json,
    replace_code_pair_placeholders,
    sha1_text,
    strip_json_fence,
    strip_unapproved_img_tags,
    write_json,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / CACHE_NAME
SITE_TITLE = "Chandler's AI Productivity Notes"
PROMPT_VERSION = "sdaf-ruppert-v1.0"
BOOK_TITLE_ZH = "《金融工程统计与数据分析：R 示例》"
BOOK_FULL_TITLE_ZH = "《金融工程统计与数据分析：R 示例》简体中文教程"

FALLBACK_TITLE_MAP = {
    "preface": "前言",
    "preface-first-edition": "第一版前言",
    "notation": "记号说明",
    "chapter-1": "第 1 章 引言",
    "chapter-2": "第 2 章 收益率",
    "chapter-3": "第 3 章 固定收益证券",
    "chapter-4": "第 4 章 探索性数据分析",
    "chapter-5": "第 5 章 单变量分布建模",
    "chapter-6": "第 6 章 重抽样",
    "chapter-7": "第 7 章 多元统计模型",
    "chapter-8": "第 8 章 Copula",
    "chapter-9": "第 9 章 回归：基础",
    "chapter-10": "第 10 章 回归：故障诊断",
    "chapter-11": "第 11 章 回归：高级主题",
    "chapter-12": "第 12 章 时间序列模型：基础",
    "chapter-13": "第 13 章 时间序列模型：进一步主题",
    "chapter-14": "第 14 章 GARCH 模型",
    "chapter-15": "第 15 章 协整",
    "chapter-16": "第 16 章 投资组合选择",
    "chapter-17": "第 17 章 资本资产定价模型",
    "chapter-18": "第 18 章 因子模型与主成分",
    "chapter-19": "第 19 章 风险管理",
    "chapter-20": "第 20 章 贝叶斯数据分析与 MCMC",
    "chapter-21": "第 21 章 非参数回归与样条",
    "appendix-a": "附录 A 概率、统计与代数基础",
    "index": "索引",
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
        "statistics/statistical-learning editor, and bilingual R/Python coding instructor. "
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
                "math_rules, r_python_code_rules, figure_table_link_footnote_rules, html_rules, "
                "forbidden_visible_phrases, reviewer_checklist. "
                "Terminology must follow quantitative finance, statistics, statistical learning, "
                "econometrics, and financial engineering conventions."
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
        if "© springer science+business media" in lower:
            skip_next = 4
            continue
        if lower.startswith("d. ruppert, d.s. matteson"):
            skip_next = 3
            continue
        if lower.startswith("doi 10.1007"):
            continue
        if lower in {"springer texts in statistics", "engineering, springer texts in statistics,"}:
            continue
        if re.fullmatch(r"\d{1,4}", line) and cleaned:
            continue
        if is_source_running_header(line):
            continue
        cleaned.append(raw)
    return "\n".join(cleaned)


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


def page_translation_system_prompt(book_guide: str) -> str:
    return (
        "你是金融工程、统计学、统计学习与计量金融教材的资深简体中文译者和技术编辑。只返回 JSON。"
        "请把单个 PDF 页面的英文内容译成可发布的中文 HTML 片段，风格应像中文技术教程而不是机器翻译稿。"
        "必须翻译练习题、图题、表题、脚注、页内说明；保留人名、数据集名、R/Python 包名、函数名、变量名和参考文献必要英文。"
        "数学公式必须用标准 LaTeX，行内用 \\(...\\)，展示公式用 \\[...\\]；不要翻译数学符号本身。"
        "如果页面包含 R 代码，HTML 中放 [[CODE_PAIR:code-id]] 占位符，并在 code_pairs 中给出 original R code 和等价 Python code。"
        "CODE_PAIR 占位符必须独占一行，不能放进 <p>、<pre> 或 <code> 内。"
        "每个 Python 代码块必须是标准 Python，可被 ast.parse 解析；使用 numpy, pandas, scipy, statsmodels, matplotlib, scikit-learn 等常规生态。"
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
    fragment = re.sub(r"<pre><code(?:\s+class=[\"'][^\"']*[\"'])?>\s*(\[\[CODE_PAIR:[^\]]+\]\])\s*</code></pre>", r"\1", fragment)
    fragment = re.sub(r"<p>\s*(\[\[CODE_PAIR:[^\]]+\]\])\s*</p>", r"\1", fragment)
    fragment = re.sub(r"<p>\s*(<figure\b)", r"\1", fragment)
    fragment = re.sub(r"(</figure>)\s*</p>", r"\1", fragment)
    return fragment


def unwrap_embedded_code_tabs(fragment: str) -> str:
    marker = '<div class="code-tabs"'
    search_from = 0
    while True:
        start = fragment.find("<pre><code", search_from)
        if start == -1:
            return fragment
        code_start = fragment.find("<code", start)
        code_open_end = fragment.find(">", code_start)
        if code_open_end == -1:
            return fragment
        content_start = code_open_end + 1
        while content_start < len(fragment) and fragment[content_start].isspace():
            content_start += 1
        if not fragment.startswith(marker, content_start):
            search_from = code_open_end + 1
            continue
        div_end = find_balanced_div_end(fragment, content_start)
        if div_end == -1:
            search_from = code_open_end + 1
            continue
        tail_match = re.match(r"\s*</code>\s*</pre>", fragment[div_end:], flags=re.IGNORECASE)
        if not tail_match:
            closing_match = re.search(r"\s*</code>\s*</pre>", fragment[div_end:], flags=re.IGNORECASE)
            if not closing_match:
                search_from = div_end
                continue
            tail_content = fragment[div_end : div_end + closing_match.start()].strip()
            output_block = ""
            if tail_content:
                output_block = f'\n<pre><code class="language-text">{html.escape(tail_content)}</code></pre>'
            fragment = fragment[:start] + fragment[content_start:div_end] + output_block + fragment[div_end + closing_match.end() :]
            search_from = start + 1
            continue
        fragment = fragment[:start] + fragment[content_start:div_end] + fragment[div_end + tail_match.end() :]
        search_from = start + 1


def find_balanced_div_end(fragment: str, start: int) -> int:
    depth = 0
    for match in re.finditer(r"</?div\b[^>]*>", fragment[start:], flags=re.IGNORECASE):
        tag = match.group(0)
        if tag.startswith("</"):
            depth -= 1
            if depth == 0:
                return start + match.end()
        else:
            depth += 1
    return -1


def strip_running_header_artifacts(fragment: str) -> str:
    def replace(match: re.Match[str]) -> str:
        body = match.group(3)
        text = html.unescape(re.sub(r"<[^>]+>", " ", body))
        text = " ".join(text.split())
        if is_rendered_running_header(text):
            return ""
        return match.group(0)

    return re.sub(r"<(h[1-6]|p)\b([^>]*)>([\s\S]*?)</\1>", replace, fragment, flags=re.IGNORECASE)


def is_rendered_running_header(text: str) -> bool:
    if not text:
        return False
    if re.fullmatch(r"\d{1,4}\s+第\s*\d{1,2}\s*章\s+.+", text):
        return True
    if re.fullmatch(r"\d{1,4}\s+第\d{1,2}章\s+.+", text):
        return True
    if re.fullmatch(r"\d{1,4}\s+附录\s+[A-Z]\s+.+", text):
        return True
    if re.fullmatch(r"\d{1,2}\s+[\u4e00-\u9fff][\u4e00-\u9fffA-Za-z\s：、]+", text):
        return True
    if re.fullmatch(r"\d{1,2}\s+[A-Z][A-Za-z0-9 ,:;'\-()]+", text):
        return True
    if is_source_running_header(text):
        return True
    return False


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
        r"(?is)<p[^>]*>[^<]*(?:Springer Science\+Business Media|Springer Texts in Statistics|DOI\s*10\.1007|D\.\s*Ruppert|D\.S\.\s*Matteson)[^<]*</p>",
        r"(?is)<p[^>]*>\s*\d{1,4}\s*</p>",
    ]
    for pattern in patterns:
        fragment = re.sub(pattern, "", fragment)
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
    fragment = replace_code_pair_placeholders(str(fragment).strip(), response.get("code_pairs", []) if isinstance(response.get("code_pairs"), list) else [])
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
                "html, code_pairs, title_zh_if_page_starts_unit, captions_zh, warnings. "
                "For code_pairs use objects with fields id, r_code, python_code. "
                "Preserve original R code in r_code as closely as PDF extraction allows; python_code must be equivalent and runnable. "
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
        "code_pairs": data.get("code_pairs", []),
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


COMMON_SECTION_TITLE_MAP = {
    "introduction": "引言",
    "bibliographic notes": "文献说明",
    "references": "参考文献",
    "r lab": "R 实验",
    "exercises": "习题",
    "the random walk model": "随机游走模型",
    "zero-coupon bonds": "零息债券",
    "coupon bonds": "附息债券",
    "yield to maturity": "到期收益率",
    "term structure": "期限结构",
    "continuous compounding": "连续复利",
    "continuous forward rates": "连续远期利率",
    "sensitivity of price to yield": "价格对收益率的敏感性",
    "histograms and kernel density estimation": "直方图与核密度估计",
    "order statistics, the sample cdf, and sample quantiles": "顺序统计量、样本 CDF 与样本分位数",
    "tests of normality": "正态性检验",
    "boxplots": "箱线图",
    "data transformation": "数据变换",
    "the geometry of transformations": "变换的几何解释",
    "transformation kernel density estimation": "变换核密度估计",
    "multiple linear regression": "多元线性回归",
    "bootstrap estimates of bias, standard deviation, and mse": "偏差、标准差和 MSE 的自助法估计",
    "probability distributions": "概率分布",
    "when do expected values and variances exist?": "期望值和方差何时存在？",
    "monotonic functions": "单调函数",
    "the minimum, maximum, infinum, and supremum of a set": "集合的最小值、最大值、下确界与上确界",
    "functions of random variables": "随机变量的函数",
    "random samples": "随机样本",
    "the binomial distribution": "二项分布",
    "some common continuous distributions": "一些常见连续分布",
    "sampling a normal distribution": "正态分布抽样",
    "law of large numbers and the central limit theoremfor the sample mean": "大数定律与样本均值的中心极限定理",
    "law of large numbers and the central limit theorem for the sample mean": "大数定律与样本均值的中心极限定理",
    "bivariate distributions": "二元分布",
    "correlation and covariance": "相关与协方差",
    "multivariate distributions": "多元分布",
    "stochastic processes": "随机过程",
    "estimation": "估计",
    "confidence intervals": "置信区间",
    "hypothesis testing": "假设检验",
    "prediction": "预测",
    "facts about vectors and matrices": "向量与矩阵知识",
    "roots of polynomials and complex numbers": "多项式根与复数",
}


def extract_heading_title_map_from_cached_pages() -> dict[str, str]:
    result: dict[str, str] = {}
    page_dir = CACHE_DIR / "page_translations"
    if not page_dir.exists():
        return result
    for path in sorted(page_dir.glob("page-*.json")):
        try:
            raw = str(read_json(path).get("html", ""))
        except Exception:
            continue
        for match in re.finditer(r"<h[1-6]\b([^>]*)>([\s\S]*?)</h[1-6]>", raw, flags=re.IGNORECASE):
            attrs, body = match.groups()
            id_match = re.search(r'\bid\s*=\s*["\']([^"\']+)["\']', attrs)
            if not id_match:
                continue
            anchor_id = html.unescape(id_match.group(1))
            if not (anchor_id.startswith("section-") or anchor_id.startswith("references")):
                continue
            text = html.unescape(re.sub(r"<[^>]+>", " ", body))
            text = " ".join(text.split())
            if not re.search(r"[\u4e00-\u9fff]", text):
                continue
            if text and not is_rendered_running_header(text):
                result.setdefault(anchor_id, text)
    return result


def augment_title_map(title_map: dict[str, str]) -> dict[str, str]:
    merged = dict(title_map)
    for key, value in extract_heading_title_map_from_cached_pages().items():
        merged.setdefault(key, value)
    return merged


def title_for_unit(unit: dict[str, Any], title_map: dict[str, str]) -> str:
    return title_map.get(str(unit["slug"])) or title_map.get(str(unit["title_en"])) or FALLBACK_TITLE_MAP.get(str(unit["slug"])) or str(unit["title_en"])


def title_for_section(section: dict[str, Any], title_map: dict[str, str]) -> str:
    slug = str(section.get("slug", ""))
    title_en = str(section.get("title_en", ""))
    number_match = re.match(r"^([A-Z]?\d*(?:\.\d+)+|[A-Z]\.\d+)\s+(.+)$", title_en)
    prefix = f"{number_match.group(1)} " if number_match else ""
    body = number_match.group(2) if number_match else title_en
    fallback = COMMON_SECTION_TITLE_MAP.get(body.strip().lower())
    if slug in title_map:
        title = title_map[slug]
        if fallback and not re.search(r"[\u4e00-\u9fff]", title):
            title = prefix + fallback
        return normalize_sidebar_title(title)
    if title_en in title_map:
        return normalize_sidebar_title(title_map[title_en])
    return normalize_sidebar_title(prefix + fallback if fallback else title_en)


def normalize_sidebar_title(title: str) -> str:
    return title.replace("Bootstrap ", "自助法").replace("Bootstrap", "自助法")


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


def render_sidebar(units: list[dict[str, Any]], title_map: dict[str, str], current_slug: str | None = None) -> str:
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
                f'<a class="section-link" href="{("#" if current else unit_local_path(unit) + "#")}{html.escape(str(section["slug"]), quote=True)}">{html.escape(title_for_section(section, title_map))}</a>'
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
    fragment = str(read_json(path).get("html", "")).strip()
    fragment = unwrap_embedded_code_tabs(fragment)
    fragment = strip_running_header_artifacts(fragment)
    return sanitize_python_code_html(fragment)


def sanitize_python_code_text(code: str) -> str:
    return re.sub(r"\blambda\b(?=\s*[*+\-/,)])", "lambda_", code)


def sanitize_python_code_html(fragment: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return match.group(1) + sanitize_python_code_text(match.group(2)) + match.group(3)

    return re.sub(r'(<code class="language-python">)([\s\S]*?)(</code>)', replace, fragment)


def sections_by_page(unit: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    result: dict[int, list[dict[str, Any]]] = {}
    for section in unit.get("sections", []):
        try:
            page = int(section.get("pdf_page"))
        except Exception:
            continue
        result.setdefault(page, []).append(section)
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
    title_map = augment_title_map(extract_title_map(book_guide))
    units = manifest["units"]
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
<p>本书围绕金融市场数据的统计分析展开，覆盖收益率、固定收益、探索性数据分析、分布建模、重抽样、多元模型、copula、回归、时间序列、GARCH、协整、投资组合、CAPM、因子模型、风险管理、贝叶斯分析与非参数回归等主题。每个 R 示例均保留原始 R 代码，并提供可切换查看的 Python 等价实现。</p>
<h2>目录</h2>
<ol>{toc}</ol>
"""
    write_text(book_dir / "index.html", render_shell(BOOK_TITLE_ZH, BOOK_FULL_TITLE_ZH, index_body, render_sidebar(units, title_map)))

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
            render_shell(title_zh, f"{title_zh} | {BOOK_TITLE_ZH}", "\n".join(parts), render_sidebar(units, title_map, str(unit["slug"]))),
        )

    if missing_pages and not allow_partial:
        raise RuntimeError(f"Missing {len(missing_pages)} translated pages; rerun with --allow-partial to render partial output.")
    return {"missing_translated_pages": missing_pages}


def write_blog_post(manifest: dict[str, Any], book_guide: str) -> Path:
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    toc = "\n".join(f"- [{title_for_unit(unit, title_map)}]({unit_local_path(unit)})" for unit in units)
    today = dt.date.today().isoformat()
    path = ROOT / "content" / "posts" / f"{today}-{SLUG}.md"
    post = f"""---
title: "{BOOK_FULL_TITLE_ZH}"
date: {today}
summary: "《{BOOK_TITLE_EN}》的简体中文教程入口，覆盖金融工程、统计学习、时间序列、风险管理与 R/Python 双语代码示例。"
tags: ["金融工程", "统计学习", "量化金融", "Python", "R"]
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
    parser = argparse.ArgumentParser(description="Translate and render the Ruppert/Matteson financial engineering Chinese book pages.")
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
