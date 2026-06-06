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

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / "investing-volume-analysis"
SLUG = "investing-with-volume-analysis-cn"
BOOK_TITLE_ZH = "《成交量分析投资法》中文译稿"
BOOK_FULL_TITLE_ZH = "《成交量分析投资法：识别、跟随趋势并从中获利》中文译稿"
SITE_TITLE = "Chandler's AI Productivity Notes"
SITE_URL = "https://chandlerbbt.github.io"
PROMPT_VERSION = "investing-volume-v1.2"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def strip_json_fence(content: str) -> str:
    content = content.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, flags=re.DOTALL)
    return fenced.group(1).strip() if fenced else content


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def asset_url(path: str) -> str:
    asset_path = ROOT / path.lstrip("/")
    version = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:12] if asset_path.exists() else "missing"
    return f"{path}?v={version}"


class DeepSeekClient:
    def __init__(self, model: str, timeout: int, max_tokens: int) -> None:
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    def chat_json(self, system: str, user: dict, temperature: float = 0.15, retries: int = 3) -> dict:
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
                return json.loads(strip_json_fence(content))
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


def extract_pdf_page_texts(pdf_path: Path) -> dict[int, str]:
    reader = PdfReader(str(pdf_path))
    page_texts: dict[int, str] = {}
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = f"[TEXT_EXTRACTION_ERROR page={page_number} error={type(exc).__name__}: {exc}]"
        page_texts[page_number] = text.strip()
    return page_texts


def unit_for_page(units: list[dict], page_number: int) -> dict | None:
    for unit in units:
        if int(unit["pdf_page_start"]) <= page_number <= int(unit["pdf_page_end"]):
            return unit
    return None


def build_page_payload(
    page_number: int,
    page_text: str,
    manifest: dict,
    image_map: dict,
) -> dict:
    units = manifest["units"]
    unit = unit_for_page(units, page_number) or {}
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
        "source_text": page_text,
        "captions_on_page": captions,
        "images_on_page": [
            {
                "id": image.get("id"),
                "target_asset_path": image.get("target_asset_path"),
                "width_px": image.get("width_px"),
                "height_px": image.get("height_px"),
                "caption_id": image.get("caption_id"),
            }
            for image in images
        ],
    }


def guide_system_prompt() -> str:
    return (
        "You are a senior Simplified Chinese translator and technical editor for finance and investing books. "
        "Use maximum reasoning effort internally. Return JSON only. Do not translate the whole book in this step. "
        "Build a book-level translation guide for an authorized public Chinese translation of a finance book."
    )


def build_book_guide(client: DeepSeekClient, manifest: dict, force: bool = False) -> str:
    guide_md = CACHE_DIR / "book_guide.md"
    guide_json = CACHE_DIR / "book_guide.json"
    if guide_md.exists() and not force:
        return guide_md.read_text(encoding="utf-8")

    full_extract = (CACHE_DIR / "full_book_extract.md").read_text(encoding="utf-8")
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
                "sections": unit.get("sections", []),
            }
            for unit in manifest["units"]
        ],
    }
    data = client.chat_json(
        guide_system_prompt(),
        {
            "task": "Create the full-book Simplified Chinese translation guide. Return JSON fields: book_title_zh, subtitle_zh, translator_style, glossary, chapter_title_map, section_title_map, caption_rules, html_rules, reviewer_checklist.",
            "terminology_seed": terminology_seed,
            "manifest": compact_manifest,
            "full_book_extract": full_extract,
        },
        temperature=0.1,
        retries=3,
    )
    write_json(guide_json, data)
    guide_text = json.dumps(data, ensure_ascii=False, indent=2)
    write_text(guide_md, guide_text)
    return guide_text


def page_translation_system_prompt(book_guide: str) -> str:
    guide = book_guide[:60_000]
    return (
        "你是金融投资书籍的简体中文译者，负责把英文 PDF 页面翻译成可发布的 HTML 片段。"
        "请在内部充分思考，尤其注意金融投资和技术分析术语。只返回 JSON。"
        "译文必须自然、准确、专业，不要出现机器翻译腔。"
        "图片像素本身不翻译；如果本页有 images_on_page，必须在合适位置插入居中的 figure/img，并翻译图注。"
        "不要输出 TODO、译者说明、提示词痕迹、Markdown 代码围栏。"
        "保留专有名词、指标缩写、公式、证券市场术语的必要英文缩写。"
        "HTML 片段必须包在 <section class=\"book-page\" data-pdf-page=\"N\">...</section> 中。"
        "章节/小节标题使用 h1/h2/h3，并添加稳定 ASCII id。"
        "全书译法指南如下：\n"
        + guide
    )


def translate_page(
    page_number: int,
    page_text: str,
    manifest: dict,
    image_map: dict,
    book_guide: str,
    client_config: dict,
    force: bool = False,
) -> dict:
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
                "Translate this one PDF page into Simplified Chinese HTML. "
                "Return JSON fields: html, title_zh_if_page_starts_unit, captions_zh, warnings. "
                "If source text includes obvious running headers/footers/page numbers, omit them. "
                "If source text contains figure/table captions, translate them and associate with matching image if possible."
            ),
            "page": payload,
        },
        temperature=0.15,
        retries=3,
    )
    result = {
        "page_number": page_number,
        "input_hash": cache_key,
        "translated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "html": str(data.get("html", "")).strip(),
        "title_zh_if_page_starts_unit": str(data.get("title_zh_if_page_starts_unit", "")).strip(),
        "captions_zh": data.get("captions_zh", []),
        "warnings": data.get("warnings", []),
    }
    if not result["html"]:
        raise RuntimeError(f"DeepSeek returned empty html for page {page_number}")
    write_json(cache_path, result)
    return result


def translate_all_pages(
    manifest: dict,
    image_map: dict,
    book_guide: str,
    model: str,
    workers: int,
    timeout: int,
    max_tokens: int,
    force: bool,
    only_pages: list[int] | None = None,
) -> None:
    pdf_path = Path(manifest["book"]["source_pdf"])
    page_texts = extract_pdf_page_texts(pdf_path)
    start_page = min(int(unit["pdf_page_start"]) for unit in manifest["units"])
    end_page = max(int(unit["pdf_page_end"]) for unit in manifest["units"])
    selected_pages = set(only_pages or [])
    pages = [page for page in range(start_page, end_page + 1) if page_texts.get(page, "").strip()]
    if selected_pages:
        pages = [page for page in pages if page in selected_pages]
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

    failures: list[dict] = []
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
        raise RuntimeError(f"{len(failures)} page translations failed; see progress.json")
    progress["status"] = "pages_translated"
    write_json(progress_path, progress)


def fallback_title_zh(title_en: str) -> str:
    m = re.match(r"Chapter\s+(\d+)\s*:\s*(.+)", title_en, flags=re.I)
    if m:
        return f"第 {int(m.group(1))} 章 {m.group(2)}"
    mapping = {
        "Introduction": "导言",
        "Index": "索引",
        "Contents": "目录",
        "Acknowledgments": "致谢",
        "Bibliography": "参考文献",
        "About the Author": "作者简介",
    }
    return mapping.get(title_en, title_en)


def extract_title_map(book_guide: str) -> dict[str, str]:
    try:
        data = json.loads(book_guide)
    except Exception:
        return {}
    result: dict[str, str] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            if "title_en" in value and ("title_zh" in value or "zh" in value):
                result[clean_text(value.get("title_en"))] = clean_text(value.get("title_zh") or value.get("zh"))
            if "English" in value and ("Chinese" in value or "简体中文" in value):
                result[clean_text(value.get("English"))] = clean_text(value.get("Chinese") or value.get("简体中文"))
            for key, child in value.items():
                if isinstance(child, str) and isinstance(key, str) and re.search(r"[A-Za-z]", key):
                    if re.search(r"[\u4e00-\u9fff]", child):
                        result[clean_text(key)] = clean_text(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(data.get("chapter_title_map", data))
    return result


def load_page_translation(page_number: int) -> dict:
    path = CACHE_DIR / "page_translations" / f"page-{page_number:03d}.json"
    return read_json(path)


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


def unit_local_path(unit: dict) -> str:
    return f"/{SLUG}/{unit['slug']}/"


def render_sidebar(units: list[dict], title_map: dict[str, str], current_slug: str | None = None) -> str:
    links = []
    links.append(
        '<div class="sidebar-item">'
        f'<div class="sidebar-page-row"><a class="sidebar-page-link" href="/{SLUG}/">首页</a>'
        '<span class="sidebar-toggle-placeholder" aria-hidden="true"></span></div></div>'
    )
    for unit in units:
        title = title_map.get(unit["title_en"]) or unit.get("title_zh") or fallback_title_zh(unit["title_en"])
        current = unit["slug"] == current_slug
        links.append(
            f'<div class="sidebar-item{" is-current" if current else ""}">'
            '<div class="sidebar-page-row">'
            f'<a class="sidebar-page-link" href="{unit_local_path(unit)}"{" aria-current=\"page\"" if current else ""}>{html.escape(title)}</a>'
            '<span class="sidebar-toggle-placeholder" aria-hidden="true"></span>'
            "</div></div>"
        )
    return f"""
<aside class="tutorial-sidebar">
  <div class="sidebar-heading">
    <h2>书稿目录</h2>
  </div>
  <nav class="sidebar-list">{''.join(links)}</nav>
</aside>
"""


def copy_images(image_map: dict) -> None:
    target_dir = ROOT / "assets" / "img" / SLUG
    target_dir.mkdir(parents=True, exist_ok=True)
    for image in image_map.get("images", []):
        cache_file = CACHE_DIR / str(image.get("cache_file", ""))
        if not cache_file.exists():
            continue
        filename = Path(str(image.get("target_asset_path", ""))).name
        if filename:
            shutil.copy2(cache_file, target_dir / filename)


def normalize_title_for_compare(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value, flags=re.S)
    text = html.unescape(text)
    text = re.sub(r"[\s:：,，.。;；!！?？\-—_《》「」“”\"'()（）]+", "", text)
    return text.lower()


def strip_duplicate_initial_heading(fragment: str, title_zh: str) -> str:
    target = normalize_title_for_compare(title_zh)
    if not target:
        return fragment

    def should_remove(inner_html: str) -> bool:
        heading = normalize_title_for_compare(inner_html)
        return bool(heading and (heading == target or heading in target or target in heading))

    for _ in range(3):
        section_match = re.match(
            r"(?is)^(\s*<section\b[^>]*>\s*)<(h1|h2)\b[^>]*>(.*?)</\2>\s*",
            fragment,
        )
        if section_match and should_remove(section_match.group(3)):
            fragment = section_match.group(1) + fragment[section_match.end() :]
            continue

        leading_match = re.match(r"(?is)^(\s*)<(h1|h2)\b[^>]*>(.*?)</\2>\s*", fragment)
        if leading_match and should_remove(leading_match.group(3)):
            fragment = leading_match.group(1) + fragment[leading_match.end() :]
            continue
        break
    return fragment


def render_book(manifest: dict, image_map: dict, book_guide: str) -> None:
    copy_images(image_map)
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    book_dir = ROOT / SLUG
    book_dir.mkdir(parents=True, exist_ok=True)

    toc = "\n".join(
        f'<li><a href="{unit_local_path(unit)}">{html.escape(title_map.get(unit["title_en"]) or fallback_title_zh(unit["title_en"]))}</a></li>'
        for unit in units
    )
    index_body = f"""
<h1>{html.escape(BOOK_FULL_TITLE_ZH)}</h1>
<div class="license-note">
  <p>本译稿基于 Buff Pelz Dormeier 的 <em>Investing with Volume Analysis: Identify, Follow, and Profit from Trends</em> 整理。用户已说明拥有出版社授权，本站按非商业学习与研究用途发布简体中文译稿。</p>
</div>
<p>本书围绕成交量分析展开，讨论成交量如何验证价格、揭示市场参与者的信念、辅助识别趋势、形态和技术指标。译稿保留原书章节结构和图表，图片原样展示，图注翻译为简体中文。</p>
<h2>目录</h2>
<ol>{toc}</ol>
"""
    write_text(book_dir / "index.html", render_shell(BOOK_TITLE_ZH, BOOK_FULL_TITLE_ZH, index_body, render_sidebar(units, title_map)))

    page_dir = CACHE_DIR / "page_translations"
    for index, unit in enumerate(units):
        title_zh = title_map.get(unit["title_en"]) or fallback_title_zh(unit["title_en"])
        parts = [f"<h1>{html.escape(title_zh)}</h1>"]
        for page in range(int(unit["pdf_page_start"]), int(unit["pdf_page_end"]) + 1):
            page_path = page_dir / f"page-{page:03d}.json"
            if not page_path.exists():
                continue
            fragment = read_json(page_path).get("html", "")
            if page == int(unit["pdf_page_start"]):
                fragment = strip_duplicate_initial_heading(str(fragment), title_zh)
            parts.append(str(fragment))
        prev_unit = units[index - 1] if index > 0 else None
        next_unit = units[index + 1] if index + 1 < len(units) else None
        nav = ['<nav class="chapter-nav">']
        if prev_unit:
            prev_title = title_map.get(prev_unit["title_en"]) or fallback_title_zh(prev_unit["title_en"])
            nav.append(f'<a href="{unit_local_path(prev_unit)}">上一章：{html.escape(prev_title)}</a>')
        else:
            nav.append("<span></span>")
        if next_unit:
            next_title = title_map.get(next_unit["title_en"]) or fallback_title_zh(next_unit["title_en"])
            nav.append(f'<a href="{unit_local_path(next_unit)}">下一章：{html.escape(next_title)}</a>')
        nav.append("</nav>")
        parts.append("".join(nav))
        write_text(
            book_dir / unit["slug"] / "index.html",
            render_shell(title_zh, f"{title_zh} | {BOOK_TITLE_ZH}", "\n".join(parts), render_sidebar(units, title_map, unit["slug"])),
        )


def write_blog_post(manifest: dict, book_guide: str) -> None:
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    toc = "\n".join(
        f"- [{title_map.get(unit['title_en']) or fallback_title_zh(unit['title_en'])}]({unit_local_path(unit)})"
        for unit in units
    )
    today = dt.date.today().isoformat()
    post = f"""---
title: "{BOOK_FULL_TITLE_ZH}"
date: {today}
summary: "Buff Pelz Dormeier《Investing with Volume Analysis》的简体中文译稿入口，聚焦成交量、价量关系、趋势识别与技术分析。"
tags: ["投资", "技术分析", "成交量"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇博客是《Investing with Volume Analysis: Identify, Follow, and Profit from Trends》的简体中文译稿入口。原书由 Buff Pelz Dormeier 撰写，围绕成交量在市场分析中的作用展开：成交量如何验证价格、揭示流动性与市场兴趣、辅助识别趋势、形态和技术指标。

> 说明：你已确认拥有出版社授权；本译稿按授权用于个人 GitHub Pages 博客的非商业学习与研究发布。书中图片原样保留，图片下方说明文字翻译为简体中文。

## 书稿入口

[打开完整分章节译稿](/{SLUG}/)

## 内容简介

本书把成交量视为理解市场供需、价格运动和趋势持续性的核心线索。作者先比较基本面分析与技术分析，再回顾技术分析的发展脉络，随后进入价格与成交量的关系、趋势中的成交量、形态中的成交量，以及多类成交量指标的使用方式。对关注技术分析、趋势交易、市场行为和投资决策过程的读者来说，这本书的价值在于把“价量关系”从直觉经验提升为一套可持续观察和验证的分析框架。

## 目录

{toc}
"""
    write_text(ROOT / "content" / "posts" / f"{today}-{SLUG}.md", post)


def write_quality_report(manifest: dict, image_map: dict) -> None:
    page_dir = CACHE_DIR / "page_translations"
    units = manifest["units"]
    page_start = min(int(unit["pdf_page_start"]) for unit in units)
    page_end = max(int(unit["pdf_page_end"]) for unit in units)
    missing_pages = [page for page in range(page_start, page_end + 1) if not (page_dir / f"page-{page:03d}.json").exists()]
    book_pages = list((ROOT / SLUG).glob("**/index.html"))
    asset_missing = []
    for image in image_map.get("images", []):
        filename = Path(str(image.get("target_asset_path", ""))).name
        if filename and not (ROOT / "assets" / "img" / SLUG / filename).exists():
            asset_missing.append(filename)
    report = {
        "status": "ready" if not missing_pages and not asset_missing else "incomplete",
        "translation_units": len(units),
        "expected_pdf_page_range": [page_start, page_end],
        "missing_translated_pages": missing_pages[:100],
        "book_pages_generated": len(book_pages),
        "image_records": len(image_map.get("images", [])),
        "missing_asset_files": sorted(set(asset_missing))[:100],
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(CACHE_DIR / "quality_report.json", report)


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate and publish Investing with Volume Analysis Chinese pages.")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--timeout", type=int, default=360)
    parser.add_argument("--max-tokens", type=int, default=8192)
    parser.add_argument("--force-guide", action="store_true")
    parser.add_argument("--force-pages", action="store_true")
    parser.add_argument("--skip-translation", action="store_true")
    parser.add_argument("--only-pages", nargs="*", type=int, default=[])
    args = parser.parse_args()

    manifest = read_json(CACHE_DIR / "manifest.json")
    image_map = read_json(CACHE_DIR / "image_caption_map.json")
    client = DeepSeekClient(args.model, args.timeout, args.max_tokens)
    book_guide = build_book_guide(client, manifest, force=args.force_guide)
    if not args.skip_translation:
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
    render_book(manifest, image_map, book_guide)
    write_blog_post(manifest, book_guide)
    write_quality_report(manifest, image_map)
    print(json.dumps(read_json(CACHE_DIR / "quality_report.json"), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
