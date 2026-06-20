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

from financial_reporting_common import (
    BOOK_AUTHORS,
    BOOK_TITLE_EN,
    CACHE_NAME,
    SLUG,
    extract_page_text,
    is_omittable_pdf_page,
    read_json,
    sha1_text,
    strip_json_fence,
    strip_pdf_running_headers,
    strip_unapproved_img_tags,
    write_json,
    write_text,
)


ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / ".cache" / CACHE_NAME
SITE_TITLE = "Chandler's AI Productivity Notes"
SITE_URL = "https://chandlerbbt.github.io"
PROMPT_VERSION = "financial-reporting-v1.0"
BOOK_TITLE_ZH = "《财务报告、财务报表分析与估值》中文译稿"
BOOK_FULL_TITLE_ZH = "《财务报告、财务报表分析与估值》中文译稿"

FALLBACK_TITLE_MAP = {
    "summary-of-key-ratios": "关键财务报表比率汇总",
    "preface": "前言",
    "about-the-authors": "作者简介",
    "chapter-1": "第 1 章 财务报告、财务报表分析与估值概览",
    "chapter-2": "第 2 章 资产和负债估值与收益确认",
    "chapter-3": "第 3 章 理解现金流量表",
    "chapter-4": "第 4 章 盈利能力分析",
    "chapter-5": "第 5 章 风险分析",
    "chapter-6": "第 6 章 会计质量",
    "chapter-7": "第 7 章 融资活动",
    "chapter-8": "第 8 章 投资活动",
    "chapter-9": "第 9 章 经营活动",
    "chapter-10": "第 10 章 预测财务报表",
    "chapter-11": "第 11 章 风险调整后的预期报酬率与股利估值方法",
    "chapter-12": "第 12 章 基于现金流的估值方法",
    "chapter-13": "第 13 章 基于收益的估值方法",
    "chapter-14": "第 14 章 基于市场的估值方法",
    "appendix-a": "附录 A Clorox 公司的财务报表及附注",
    "appendix-b": "附录 B Clorox 公司的管理层讨论与分析",
    "appendix-c": "附录 C 财务报表分析包 FSAP",
    "appendix-d": "附录 D 按行业划分的财务报表比率描述性统计",
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

    def chat_json(self, system: str, user: dict[str, Any], temperature: float = 0.12, retries: int = 3) -> dict[str, Any]:
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


def asset_url(path: str) -> str:
    asset_path = ROOT / path.lstrip("/")
    version = hashlib.sha256(asset_path.read_bytes()).hexdigest()[:12] if asset_path.exists() else "missing"
    return f"{path}?v={version}"


def guide_system_prompt() -> str:
    return (
        "You are a senior Simplified Chinese translator and technical editor for accounting, "
        "financial statement analysis, and valuation textbooks. Return JSON only. Do not translate "
        "the whole book in this step. Create a full-book guide for an authorized public translation."
    )


def build_book_guide(client: DeepSeekClient, manifest: dict[str, Any], force: bool = False) -> str:
    guide_md = CACHE_DIR / "book_guide.md"
    guide_json = CACHE_DIR / "book_guide.json"
    if guide_md.exists() and not force:
        return guide_md.read_text(encoding="utf-8")

    compact_extract = (CACHE_DIR / "compact_guide_extract.md").read_text(encoding="utf-8")
    terminology_seed = (CACHE_DIR / "TERMINOLOGY_SEED.md").read_text(encoding="utf-8")
    style_seed_path = CACHE_DIR / "STYLE_SEED_CHAPTER1.md"
    style_seed = style_seed_path.read_text(encoding="utf-8", errors="replace")[:50_000] if style_seed_path.exists() else ""
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
                "table_and_exhibit_rules, html_rules, forbidden_visible_phrases, reviewer_checklist."
            ),
            "manifest": compact_manifest,
            "terminology_seed": terminology_seed,
            "style_seed_chapter_1": style_seed,
            "compact_guide_extract": compact_extract,
        },
        temperature=0.08,
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
                "caption_id": image.get("caption_id"),
            }
            for image in images
        ],
    }


def page_translation_system_prompt(book_guide: str) -> str:
    return (
        "你是会计、财务报表分析与估值教材的资深简体中文译者。只返回 JSON。"
        "请把单个 PDF 页面的英文内容译为可发布的中文 HTML 片段。"
        "译文必须自然、专业、准确，不出现提示词痕迹、TODO、译者说明、原文标签或机器翻译腔。"
        "保留公式、比率符号、公司名、准则名、缩写、题号、图表编号和引用。"
        "如果页面包含 images_on_page，请在适当位置插入居中的 figure/img，并翻译对应图注；不要翻译图片像素内文字。"
        "HTML 必须包在 <section class=\"book-page\" data-pdf-page=\"N\">...</section> 内。"
        "标题使用 h1/h2/h3 并加稳定 ASCII id。"
        "全书翻译指南如下：\n"
        + book_guide[:70_000]
    )


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
                "html, title_zh_if_page_starts_unit, captions_zh, warnings. Omit running headers, "
                "footers, page numbers, and repeated copyright footers unless they are substantively part of the unit. "
                "Translate every visible English sentence in exercises, end-of-chapter questions, appendix notes, "
                "table notes, and chapter prose. Preserve proper nouns and citation titles only when appropriate."
            ),
            "page": payload,
        },
        temperature=0.12,
        retries=3,
    )
    result = {
        "page_number": page_number,
        "input_hash": cache_key,
        "translated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "html": strip_pdf_running_headers(
            strip_unapproved_img_tags(
                str(data.get("html", "")).strip(),
                (f"/assets/img/{SLUG}/",),
            )
        ),
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
    return strip_pdf_running_headers(
        strip_unapproved_img_tags(str(read_json(path).get("html", "")).strip(), (f"/assets/img/{SLUG}/",))
    )


def render_book(manifest: dict[str, Any], image_map: dict[str, Any], book_guide: str, allow_partial: bool = False) -> dict[str, Any]:
    copy_images(image_map)
    title_map = extract_title_map(book_guide)
    units = manifest["units"]
    reader = PdfReader(str(Path(manifest["book"]["source_pdf"])))
    book_dir = ROOT / SLUG
    book_dir.mkdir(parents=True, exist_ok=True)

    missing_pages: list[int] = []
    toc = "\n".join(
        f'<li><a href="{unit_local_path(unit)}">{html.escape(title_for_unit(unit, title_map))}</a></li>'
        for unit in units
    )
    index_body = f"""
<h1>{html.escape(BOOK_FULL_TITLE_ZH)}</h1>
<div class="license-note">
  <p>本译稿基于 {html.escape(BOOK_AUTHORS)} 的 <em>{html.escape(BOOK_TITLE_EN)}</em> 整理。你已说明拥有公开翻译与发布授权；本站按授权用于个人 GitHub Pages 博客发布。</p>
</div>
<p>本书围绕财务报告、财务报表分析、预测与估值展开，帮助读者理解企业盈利能力、风险、增长、会计质量与资本市场估值之间的关系。</p>
<h2>目录</h2>
<ol>{toc}</ol>
"""
    write_text(book_dir / "index.html", render_shell(BOOK_TITLE_ZH, BOOK_FULL_TITLE_ZH, index_body, render_sidebar(units, title_map)))

    for index, unit in enumerate(units):
        title_zh = title_for_unit(unit, title_map)
        parts = [f"<h1>{html.escape(title_zh)}</h1>"]
        for page in expected_pages_for_unit(unit, reader):
            fragment = load_page_html(page)
            if fragment is None:
                missing_pages.append(page)
                if allow_partial:
                    continue
                continue
            parts.append(fragment)
        prev_unit = units[index - 1] if index > 0 else None
        next_unit = units[index + 1] if index + 1 < len(units) else None
        nav = ['<nav class="chapter-nav">']
        if prev_unit:
            nav.append(f'<a href="{unit_local_path(prev_unit)}">上一节：{html.escape(title_for_unit(prev_unit, title_map))}</a>')
        else:
            nav.append("<span></span>")
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
    toc = "\n".join(
        f"- [{title_for_unit(unit, title_map)}]({unit_local_path(unit)})"
        for unit in units
    )
    today = dt.date.today().isoformat()
    path = ROOT / "content" / "posts" / f"{today}-{SLUG}.md"
    post = f"""---
title: "{BOOK_FULL_TITLE_ZH}"
date: {today}
summary: "《{BOOK_TITLE_EN}》的简体中文译稿入口，聚焦财务报告、财务报表分析、预测与估值。"
tags: ["财务报告", "财务报表分析", "估值", "会计"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇文章是《{BOOK_TITLE_EN}》中文译稿的入口页。原书由 {BOOK_AUTHORS} 编写，系统讲解财务报告、财务报表分析、会计质量、预测财务报表与企业估值。

> 说明：你已确认拥有公开翻译与发布授权；本译稿按授权用于个人 GitHub Pages 博客发布。

## 书稿入口

[打开完整分章节译稿](/{SLUG}/)

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
    missing_pages = [
        page for page in expected_pages if not (page_dir / f"page-{page:03d}.json").exists()
    ]
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
        "missing_asset_files": sorted(set(asset_missing))[:100],
        "render_missing_pages_count": len(render_stats.get("missing_translated_pages", [])),
        "updated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    write_json(CACHE_DIR / "quality_report.json", report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Translate and render the Wahlen financial reporting Chinese book pages.")
    parser.add_argument("--model", default=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"))
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
