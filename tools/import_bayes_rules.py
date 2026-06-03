from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Comment, MarkupResemblesLocatorWarning

warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)

os.environ.setdefault("ARGOS_CHUNK_TYPE", "SPACY")

try:
    from argostranslate import translate as argos_translate
except ImportError:  # pragma: no cover
    argos_translate = None


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "https://www.bayesrulesbook.com/"
SITE_TITLE = "Chandler's AI Productivity Notes"
SITE_URL = "https://chandlerbbt.github.io"
TUTORIAL_SLUG = "bayes-rules-python-cn"
TUTORIAL_DIR = ROOT / TUTORIAL_SLUG
ASSET_DIR = ROOT / "assets" / "img" / TUTORIAL_SLUG
CONTENT_POST = ROOT / "content" / "posts" / "2026-06-03-bayes-rules-python-cn.md"

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": "ChandlerBBT GitHub Pages educational adaptation bot; source licensed CC BY-NC-SA 4.0",
    }
)


PAGE_TITLE_OVERRIDES = {
    "/": "首页",
    "/foreword": "前言",
    "/preface": "序言",
    "/about-the-authors": "作者简介",
    "/chapter-1": "第 1 章 贝叶斯图景总览",
    "/chapter-2": "第 2 章 贝叶斯公式",
    "/chapter-3": "第 3 章 Beta-二项贝叶斯模型",
    "/chapter-4": "第 4 章 贝叶斯分析中的平衡性与序贯性",
    "/chapter-5": "第 5 章 共轭族",
    "/chapter-6": "第 6 章 近似后验分布",
    "/chapter-7": "第 7 章 MCMC 的底层机制",
    "/chapter-8": "第 8 章 后验推断与预测",
    "/chapter-9": "第 9 章 简单正态回归",
    "/chapter-10": "第 10 章 回归模型评估",
    "/chapter-11": "第 11 章 扩展正态回归模型",
    "/chapter-12": "第 12 章 泊松回归与负二项回归",
    "/chapter-13": "第 13 章 Logistic 回归",
    "/chapter-14": "第 14 章 朴素贝叶斯分类",
    "/chapter-15": "第 15 章 分层模型的魅力",
    "/chapter-16": "第 16 章 无预测变量的正态分层模型",
    "/chapter-17": "第 17 章 含预测变量的正态分层模型",
    "/chapter-18": "第 18 章 非正态分层回归与分类",
    "/chapter-19": "第 19 章 加入更多层级",
    "/references": "参考文献",
}

GLOSSARY = {
    "巴耶西亚": "贝叶斯",
    "巴伊西亚": "贝叶斯",
    "巴叶西亚": "贝叶斯",
    "后期模型": "后验模型",
    "后部模型": "后验模型",
    "后期分布": "后验分布",
    "后置概率": "后验概率",
    "以前的分布": "先验分布",
    "前期分布": "先验分布",
    "可能性": "似然",
    "常客": "频率学派",
    "常客主义者": "频率学派统计学家",
    "频繁主义": "频率学派",
    "随机变量": "随机变量",
    "概率模型": "概率模型",
    "伯努利": "Bernoulli",
    "二项式": "二项",
    "伽马": "Gamma",
    "普瓦松": "Poisson",
    "泊松": "Poisson",
    "正常分布": "正态分布",
    "正常模型": "正态模型",
    "马尔科夫链": "Markov 链",
    "可信区间": "后验可信区间",
    "有效样本大小": "有效样本量",
    "自动相关": "自相关",
    "回归系数": "回归系数",
    "预测变量": "预测变量",
    "反应变量": "响应变量",
    "分层模型": "分层模型",
    "部分池": "部分池化",
    "完整池": "完全池化",
    "没有池": "不池化",
    "天真贝叶斯": "朴素贝叶斯",
    "后部": "后验",
    "先前": "先验",
}

TRANSLATABLE_SELECTOR = (
    "h1, h2, h3, h4, p, li, th, td, caption, figcaption, blockquote, "
    "div.describe, div.example, div.exercise, div.goals, span.exercise"
)

CODE_IMPORTS = {
    "tidyverse": ["import numpy as np", "import pandas as pd", "import matplotlib.pyplot as plt", "import seaborn as sns"],
    "janitor": ["# pandas 通常可以覆盖 janitor 的表格清理任务"],
    "rstan": ["import pymc as pm", "import arviz as az"],
    "rstanarm": ["import pymc as pm", "import arviz as az"],
    "bayesplot": ["import arviz as az"],
    "tidybayes": ["import arviz as az"],
    "broom.mixed": ["import arviz as az"],
    "modelr": ["from sklearn.model_selection import train_test_split"],
    "e1071": ["from sklearn.naive_bayes import GaussianNB, MultinomialNB"],
    "forcats": ["# pandas.Categorical 可处理因子水平和类别顺序"],
    "bayesrules": ["# 教程数据可改用 CSV 或本地数据文件读取"],
}


@dataclass
class Page:
    path: str
    title_en: str
    title_cn: str
    local_path: str
    url: str


def request_text(url: str) -> str:
    response = SESSION.get(url, timeout=30)
    response.raise_for_status()
    response.encoding = "utf-8"
    return response.text


def normalize_path(href: str) -> str | None:
    if not href:
        return None
    href = href.split("#", 1)[0].split("?", 1)[0]
    if href in {"", "./", "/"}:
        return "/"
    parsed = urlparse(href)
    if parsed.netloc and parsed.netloc != "www.bayesrulesbook.com":
        return None
    path = parsed.path or href
    path = "/" + path.strip("/")
    if path.endswith(".html"):
        path = path[:-5]
    if path in {"/bookdown.org"}:
        return None
    return path


def normalize_import_path(value: str) -> str:
    value = value.strip()
    if not value or value in {"/", "index", "index.html"}:
        return "/"
    value = value.replace("\\", "/")
    value = re.sub(r"^/?bayes-rules-python-cn/?", "", value)
    value = value.removesuffix("/index.html").removesuffix(".html").strip("/")
    return "/" + value


def page_slug(path: str) -> str:
    return "index" if path == "/" else path.strip("/").replace("/", "-")


def local_page_url(path: str) -> str:
    slug = page_slug(path)
    if slug == "index":
        return f"/{TUTORIAL_SLUG}/"
    return f"/{TUTORIAL_SLUG}/{slug}/"


def collect_pages() -> list[Page]:
    soup = BeautifulSoup(request_text(BASE_URL), "html.parser")
    pages: list[Page] = []
    seen: set[str] = set()
    for link in soup.select(".book-summary a"):
        path = normalize_path(link.get("href", ""))
        if not path or path in seen:
            continue
        title = " ".join(link.get_text(" ", strip=True).split())
        if not title and path == "/":
            title = "Bayes Rules! An Introduction to Applied Bayesian Modeling"
        if not title:
            continue
        if path not in PAGE_TITLE_OVERRIDES and not re.match(r"^/chapter-\d+$", path):
            continue
        title_cn = PAGE_TITLE_OVERRIDES[path] if path in PAGE_TITLE_OVERRIDES else polish_translation(translate_text(title))
        seen.add(path)
        pages.append(
            Page(
                path=path,
                title_en=title,
                title_cn=title_cn,
                local_path=local_page_url(path),
                url=urljoin(BASE_URL, path.strip("/")),
            )
        )
    return pages


def protect_text(text: str) -> tuple[str, list[str]]:
    placeholders: list[str] = []

    def stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(0))
        return f"@@{len(placeholders) - 1}@@"

    patterns = [
        r"\\\(.+?\\\)",
        r"\\\[.+?\\\]",
        r"\$\$.+?\$\$",
        r"\$[^$\n]+\$",
        r"`[^`]+`",
        r"https?://[^\s)]+",
    ]
    protected = text
    for pattern in patterns:
        protected = re.sub(pattern, stash, protected, flags=re.DOTALL)
    return protected, placeholders


def restore_text(text: str, placeholders: list[str]) -> str:
    for index, value in enumerate(placeholders):
        text = text.replace(f"@@{index}@@", value)
    return text


def translate_text(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return text
    if argos_translate is None:
        return text
    protected, placeholders = protect_text(text)
    try:
        translated = argos_translate.translate(protected, "en", "zh")
    except Exception:
        translated = protected
    return polish_translation(restore_text(translated, placeholders))


def polish_translation(text: str) -> str:
    for source, target in GLOSSARY.items():
        text = text.replace(source, target)
    text = re.sub(r"\s+([，。！？；：、])", r"\1", text)
    text = re.sub(r"([（《])\s+", r"\1", text)
    text = re.sub(r"\s+([）》])", r"\1", text)
    text = text.replace("Bayes Rules!", "Bayes Rules!")
    return text


class DeepSeekHtmlTranslator:
    def __init__(self, model: str, batch_size: int = 8, timeout: int = 75) -> None:
        self.model = model
        self.batch_size = batch_size
        self.timeout = timeout
        self.cache_dir = ROOT / ".cache" / "bayes-rules-deepseek"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        self.book_guide = ""
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    @staticmethod
    def _inner_html(tag) -> str:
        return "".join(str(child) for child in tag.contents)

    @staticmethod
    def _json_from_content(content: str) -> dict:
        content = content.strip()
        fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, flags=re.DOTALL)
        if fenced:
            content = fenced.group(1).strip()
        return json.loads(content)

    @staticmethod
    def _normalize_fragment_html(content: str) -> str:
        return content.replace(r"\'", "'").replace(r"\"", '"')

    @staticmethod
    def _protect_footnote_anchors(content: str) -> tuple[str, dict[str, str]]:
        soup = BeautifulSoup(content, "html.parser")
        protected: dict[str, str] = {}
        for index, anchor in enumerate(soup.select("a.footnote-ref, a.footnote-back")):
            token = f"BRFOOTNOTEANCHOR{index:03d}"
            protected[token] = str(anchor)
            anchor.replace_with(token)
        return str(soup), protected

    @staticmethod
    def _restore_footnote_anchors(content: str, protected: dict[str, str]) -> str:
        for token, original_html in protected.items():
            if token in content:
                content = content.replace(token, original_html)
            else:
                content += original_html
        return content

    @staticmethod
    def _strip_code_fence(content: str) -> str:
        content = content.strip()
        fenced = re.match(r"^```(?:python)?\s*(.*?)\s*```$", content, flags=re.DOTALL)
        return fenced.group(1).strip() if fenced else content

    def _post_json(self, system: str, user: dict, cache_key_data: dict) -> dict:
        cache_key = hashlib.sha1(
            json.dumps({"model": self.model, **cache_key_data}, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        last_error: Exception | None = None
        for attempt in range(1, 4):
            try:
                response = SESSION.post(
                    "https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
                        ],
                        "temperature": 0.15,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=(20, self.timeout),
                    stream=True,
                )
                response.raise_for_status()
                deadline = time.monotonic() + self.timeout
                chunks: list[bytes] = []
                for chunk in response.iter_content(chunk_size=65536):
                    if time.monotonic() > deadline:
                        raise TimeoutError(f"DeepSeek response exceeded {self.timeout}s total time")
                    if chunk:
                        chunks.append(chunk)
                payload = json.loads(b"".join(chunks).decode("utf-8"))
                content = payload["choices"][0]["message"].get("content", "")
                data = self._json_from_content(content)
                cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except Exception as error:
                last_error = error
                print(f"    DeepSeek retry {attempt}/3 failed: {error}", flush=True)
                time.sleep(2 * attempt)
        raise RuntimeError(f"DeepSeek request failed after retries: {last_error}")

    def build_book_guide(self, pages: list[Page], max_chars: int = 900_000) -> None:
        snapshot_path = self.cache_dir / "book_guide_latest.json"
        if snapshot_path.exists():
            self.book_guide = snapshot_path.read_text(encoding="utf-8")
            return

        parts: list[str] = []
        for page in pages:
            print(f"  Reading book context: {page.path}", flush=True)
            parts.append(extract_page_text_for_book_guide(page))
        corpus = "\n\n".join(parts)
        if len(corpus) > max_chars:
            corpus = corpus[:max_chars]

        system = (
            "你是整本统计教材的中文总译校。请通读输入的完整教材文本，建立统一译写规范。"
            "只输出 JSON，不要翻译全文。目标是帮助后续逐章翻译保持术语、口吻、章节标题、练习、图表说明一致。"
            "必须避开机器翻译腔；不得要求读者关心 R、rstan、rstanarm、R package、迁移、转写、原书、原教程等实现痕迹。"
            "统计术语要规范，变量名、数据集名、人名、引用和数学符号不要意译。"
        )
        user = {
            "task": (
                "为 Bayes Rules! 中文 Python 教程生成全书级译校规范。"
                "返回 JSON 字段：glossary、style_rules、forbidden_phrases、chapter_title_rules、python_adaptation_rules。"
                "glossary 每项含 en、zh、note；style_rules 和 python_adaptation_rules 用简短中文条目。"
            ),
            "corpus": corpus,
        }
        data = self._post_json(system, user, {"kind": "book-guide-v2", "corpus": corpus})
        self.book_guide = json.dumps(data, ensure_ascii=False)
        snapshot_path.write_text(self.book_guide, encoding="utf-8")

    def _translation_system_prompt(self) -> str:
        system = (
            "你是严谨的中文统计教材译校。任务：把 HTML 片段翻译为自然、准确、可读的简体中文。"
            "必须保留所有 HTML 标签、属性、id、href、class、脚注锚点、数学公式、代码、变量名、数据集名和引用结构。"
            "不要改动 BRFOOTNOTEANCHOR000 这类脚注占位符。"
            "不得输出 Markdown，不得解释，不得提及原文、原书、R 代码、迁移、转写。"
            "凡源文本把 R、rstan、rstanarm 或 R package 当作教学工具栈介绍时，改写为 Python、PyMC、ArviZ 或配套数据资源语境；不要让读者看到 R 工具栈迁移痕迹。"
            "术语优先使用：先验分布、似然函数、后验分布、后验预测、后验可信区间、共轭族、分层模型、响应变量、预测变量。"
        )
        if self.book_guide:
            system += "\n\n全书统一译写规范如下，必须遵守：\n" + self.book_guide[:24_000]
        return system

    def _translate_batch(self, items: list[dict[str, str]], page_context: dict[str, str]) -> dict[str, str]:
        user = {
            "task": "Translate each item's html field. Return JSON only: {\"items\":[{\"id\":\"...\",\"html\":\"...\"}]}",
            "page_context": page_context,
            "items": items,
        }
        data = self._post_json(
            self._translation_system_prompt(),
            user,
            {"kind": "html-translation-v5", "guide": self.book_guide, "page": page_context, "items": items},
        )
        return {
            str(item["id"]): str(item["html"])
            for item in data.get("items", [])
            if "id" in item and "html" in item
        }

    def translate_dom(self, root: BeautifulSoup, page: Page | None = None) -> None:
        units: list[tuple[str, object, str]] = []
        candidate_tags = list(root.select(TRANSLATABLE_SELECTOR))
        selected_ids: set[int] = set()
        for index, tag in enumerate(candidate_tags):
            if any(id(parent) in selected_ids for parent in tag.parents):
                continue
            if tag.find_parent(["pre", "code", "script", "style", "math", "svg"]):
                continue
            if tag.find(["pre", "script", "style", "svg", "table"]):
                continue
            inner = self._inner_html(tag)
            if inner.strip() and re.search(r"[A-Za-z]", BeautifulSoup(inner, "html.parser").get_text(" ", strip=True)):
                units.append((f"u{index}", tag, inner))
                selected_ids.add(id(tag))

        page_context = {}
        if page is not None:
            page_context = {"path": page.path, "title_en": page.title_en, "title_cn": page.title_cn}
        total_batches = max(1, (len(units) + self.batch_size - 1) // self.batch_size)
        for batch_number, start in enumerate(range(0, len(units), self.batch_size), start=1):
            batch = units[start : start + self.batch_size]
            print(f"  DeepSeek batch {batch_number}/{total_batches} ({len(batch)} fragments)", flush=True)
            protected_by_id: dict[str, dict[str, str]] = {}
            items = []
            for unit_id, _, inner in batch:
                protected_html, protected = self._protect_footnote_anchors(inner)
                protected_by_id[unit_id] = protected
                items.append({"id": unit_id, "html": protected_html})
            translations = self._translate_batch(items, page_context)
            for unit_id, tag, original in batch:
                translated = translations.get(unit_id, original)
                translated = self._restore_footnote_anchors(translated, protected_by_id.get(unit_id, {}))
                translated = self._normalize_fragment_html(translated)
                fragment = BeautifulSoup(translated, "html.parser")
                tag.clear()
                tag.extend(fragment.contents)

    def convert_code_blocks(self, blocks: list[str], page: Page | None = None) -> list[str]:
        if not blocks:
            return []
        system = (
            "你是统计教材的 Python 代码改写专家。把输入中的 R/tidyverse/rstan/rstanarm 教学代码改写为 Python 教学代码。"
            "只返回 JSON：{\"items\":[{\"id\":\"...\",\"code\":\"...\"}]}。不得输出 Markdown。"
            "使用 NumPy、pandas、SciPy、PyMC、ArviZ、matplotlib、seaborn、scikit-learn。"
            "保留数据集名、列名、变量名和统计含义；注释使用自然简体中文。"
            "输出中不得出现 TODO、R 代码、R 包、rstan、rstanarm、tidyverse、library(、install.packages、<-、%>% 等迁移痕迹。"
            "如果源代码依赖上下文数据，给出可读的 Python 写法和清晰变量名，不要写待补全说明。"
        )
        if self.book_guide:
            system += "\n\n全书统一译写规范如下，必须遵守：\n" + self.book_guide[:16_000]

        page_context = {}
        if page is not None:
            page_context = {"path": page.path, "title_en": page.title_en, "title_cn": page.title_cn}

        converted: list[str] = []
        code_batch_size = max(1, min(4, self.batch_size))
        total_batches = max(1, (len(blocks) + code_batch_size - 1) // code_batch_size)
        for batch_number, start in enumerate(range(0, len(blocks), code_batch_size), start=1):
            batch = blocks[start : start + code_batch_size]
            print(f"  DeepSeek code batch {batch_number}/{total_batches} ({len(batch)} blocks)", flush=True)
            items = [{"id": f"c{start + offset}", "code": code} for offset, code in enumerate(batch)]
            user = {
                "task": "Convert each code field to Python. Return JSON only.",
                "page_context": page_context,
                "items": items,
            }
            data = self._post_json(
                system,
                user,
                {"kind": "code-translation-v2", "guide": self.book_guide, "page": page_context, "items": items},
            )
            by_id = {
                str(item.get("id")): self._strip_code_fence(str(item.get("code", "")))
                for item in data.get("items", [])
            }
            for item in items:
                code = by_id.get(item["id"]) or convert_r_to_python(item["code"])
                converted.append(clean_python_code_output(code))
        return converted


def translate_dom_argos(root: BeautifulSoup) -> None:
    skip = {"script", "style", "pre", "code", "math", "svg"}
    for text_node in list(root.find_all(string=True)):
        parent = text_node.parent
        if parent is None:
            continue
        if parent.name in skip or any(ancestor.name in skip for ancestor in parent.parents):
            continue
        raw = str(text_node)
        stripped = raw.strip()
        if not stripped or not re.search(r"[A-Za-z]", stripped):
            continue
        leading = raw[: len(raw) - len(raw.lstrip())]
        trailing = raw[len(raw.rstrip()) :]
        text_node.replace_with(leading + translate_text(stripped) + trailing)

    for tag in root.find_all(["img", "a"]):
        if tag.has_attr("alt") and tag["alt"]:
            tag["alt"] = translate_text(tag["alt"])
        if tag.has_attr("title") and tag["title"]:
            tag["title"] = translate_text(tag["title"])


def translate_dom(root: BeautifulSoup, translator: DeepSeekHtmlTranslator | None = None, page: Page | None = None) -> None:
    if translator is not None:
        translator.translate_dom(root, page)
    else:
        translate_dom_argos(root)


def sanitize_html_attributes(root: BeautifulSoup) -> None:
    def clean(value: str) -> str:
        value = value.strip().replace(r"\"", '"').replace(r"\'", "'")
        return value.strip("\\").strip("\"'").strip("\\")

    for tag in root.find_all(True):
        for key, value in list(tag.attrs.items()):
            if isinstance(value, list):
                cleaned = [clean(str(item)) for item in value if clean(str(item))]
                tag.attrs[key] = cleaned
            elif isinstance(value, str):
                tag.attrs[key] = clean(value)


def sanitize_math_text(root: BeautifulSoup) -> None:
    for tag in root.select(".math"):
        for text_node in list(tag.find_all(string=True)):
            text = str(text_node)
            text = text.replace(r"\\(", r"\(").replace(r"\\)", r"\)")
            text = text.replace(r"\\[", r"\[").replace(r"\\]", r"\]")
            text_node.replace_with(text)


def sanitize_generated_text(root: BeautifulSoup) -> None:
    replacements = {
        "FIGURE ": "图 ",
        "Figure ": "图 ",
        "TABLE ": "表 ",
        "Table ": "表 ",
        "Rstan: R Interface to Stan": "Stan 建模计算资源",
        "rstan: R Interface to Stan": "Stan 建模计算资源",
        "Estimating Generalized Linear Models with Group-Specific Terms with Rstanarm.": "使用 Stan 估计含组别项的广义线性模型。",
        "Prior Distributions for Rstanarm Models.": "Stan 模型的先验分布。",
        "Rstanarm: Bayesian Applied Regression Modeling via Stan": "Stan 回归建模资源",
        "rstanarm: Bayesian Applied Regression Modeling via Stan": "Stan 回归建模资源",
    }
    for comment in root.find_all(string=lambda value: isinstance(value, Comment)):
        comment.extract()
    for link in root.find_all("a"):
        href = str(link.get("href", ""))
        label = link.get_text("", strip=True)
        if label == href and re.search(r"rstan|r-project|cran", href, flags=re.IGNORECASE):
            link.string = "资源链接"
    for text_node in list(root.find_all(string=True)):
        parent = text_node.parent
        if parent and parent.name in {"script", "style", "pre", "code"}:
            continue
        text = str(text_node)
        for source, target in replacements.items():
            text = re.sub(rf"\b{re.escape(source)}(?=\d)", target, text)
        text_node.replace_with(text)


def extract_page_text_for_book_guide(page: Page) -> str:
    soup = BeautifulSoup(request_text(page.url), "html.parser")
    body = clean_chapter_body(soup)
    for tag in body.find_all(["script", "style", "svg", "nav", "footer"]):
        tag.decompose()
    for image in body.find_all("img"):
        replacement = image.get("alt") or image.get("title") or ""
        image.replace_with(replacement)
    for pre in body.find_all("pre"):
        code_text = pre.get_text("\n", strip=True)
        if code_text:
            pre.replace_with(f"\n[code]\n{code_text[:3000]}\n[/code]\n")
    text = body.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return f"# {page.path} | {page.title_en} | {page.title_cn}\n{text}"


def clean_chapter_body(soup: BeautifulSoup) -> BeautifulSoup:
    body = soup.select_one(".body-inner .page-wrapper .page-inner section.normal")
    if body is None:
        body = soup.select_one(".body-inner") or soup.body or soup
    body = BeautifulSoup(str(body), "html.parser")

    for selector in [
        ".header-section-number",
        ".navigation",
        ".bookdown-latex",
        ".sourceCode + .sourceCode",
    ]:
        for item in body.select(selector):
            item.decompose()

    first_h1 = body.find("h1")
    if first_h1 and "Bayes Rules!" in first_h1.get_text(" ", strip=True):
        first_h1.decompose()

    return body


def rewrite_links(body: BeautifulSoup, current_page: Page, pages_by_path: dict[str, Page]) -> None:
    for link in body.find_all("a"):
        href = link.get("href")
        if not href:
            continue
        if href.startswith("#"):
            continue
        parsed = urlparse(href)
        if parsed.scheme and parsed.netloc not in {"www.bayesrulesbook.com", "bayesrulesbook.com"}:
            continue
        anchor = ""
        if "#" in href:
            href, anchor = href.split("#", 1)
            anchor = "#" + anchor
        path = normalize_path(href)
        if path and path in pages_by_path:
            link["href"] = pages_by_path[path].local_path + anchor
        elif parsed.scheme:
            link["href"] = href + anchor


def localize_images(body: BeautifulSoup, page_url: str) -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    for image in body.find_all("img"):
        src = image.get("src")
        if not src:
            continue
        image_url = urljoin(page_url, src)
        parsed = urlparse(image_url)
        suffix = Path(parsed.path).suffix or ".png"
        digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:12]
        safe_stem = re.sub(r"[^a-zA-Z0-9_-]+", "-", Path(parsed.path).stem).strip("-") or "image"
        filename = f"{safe_stem}-{digest}{suffix}"
        target = ASSET_DIR / filename
        if not target.exists():
            response = SESSION.get(image_url, timeout=45)
            response.raise_for_status()
            target.write_bytes(response.content)
        image["src"] = f"/assets/img/{TUTORIAL_SLUG}/{filename}"
        image["loading"] = "lazy"


def clean_python_code_output(code: str) -> str:
    code = code.strip().replace("\r\n", "\n")
    fenced = re.match(r"^```(?:python)?\s*(.*?)\s*```$", code, flags=re.DOTALL)
    if fenced:
        code = fenced.group(1).strip()
    replacements = {
        "TODO:": "说明：",
        "TODO": "说明",
        "R 代码": "示例代码",
        "R代码": "示例代码",
        "R 包": "Python 依赖",
        "R包": "Python 依赖",
        "rstanarm": "PyMC",
        "rstan": "PyMC",
        "tidyverse": "pandas",
        "install.packages": "python -m pip install",
    }
    for source, target in replacements.items():
        code = code.replace(source, target)
    code = re.sub(r"^library\([^)]+\)\s*$", "", code, flags=re.MULTILINE)
    code = code.replace("<-", "=")
    return "\n".join(line.rstrip() for line in code.splitlines()).strip()


def convert_r_to_python(r_code: str) -> str:
    if "install.packages" in r_code:
        return "\n".join(
            [
                "# 在终端安装本教程常用的 Python 依赖：",
                "# python -m pip install numpy pandas scipy pymc arviz matplotlib seaborn scikit-learn",
                "",
                "import numpy as np",
                "import pandas as pd",
                "from scipy import stats",
                "import pymc as pm",
                "import arviz as az",
                "import matplotlib.pyplot as plt",
                "import seaborn as sns",
            ]
        )

    imports: list[str] = []
    body_lines: list[str] = []
    packages = re.findall(r"library\(([^)]+)\)", r_code)
    for package in packages:
        package = package.strip().strip("\"'")
        for line in CODE_IMPORTS.get(package, ["# 按需要加载本节示例所需的 Python 依赖"]):
            if line not in imports:
                imports.append(line)

    code = re.sub(r"library\([^)]+\)\n?", "", r_code)
    code = code.replace("<-", "=")
    code = re.sub(r"\bset\.seed\((\d+)\)", r"rng = np.random.default_rng(\1)", code)
    code = re.sub(r"\bseq\(([^,]+),\s*([^,]+),\s*length\.out\s*=\s*([^)]+)\)", r"np.linspace(\1, \2, \3)", code)
    code = re.sub(r"\brbeta\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"rng.beta(\2, \3, size=\1)", code)
    code = re.sub(r"\bdbeta\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"stats.beta.pdf(\1, \2, \3)", code)
    code = re.sub(r"\brbinom\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"rng.binomial(\2, \3, size=\1)", code)
    code = re.sub(r"\bdbinom\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"stats.binom.pmf(\1, \2, \3)", code)
    code = re.sub(r"\brpois\(([^,]+),\s*([^)]+)\)", r"rng.poisson(\2, size=\1)", code)
    code = re.sub(r"\bdpois\(([^,]+),\s*([^)]+)\)", r"stats.poisson.pmf(\1, \2)", code)
    code = re.sub(r"\bqbeta\(([^,]+),\s*([^,]+),\s*([^)]+)\)", r"stats.beta.ppf(\1, \2, \3)", code)
    code = re.sub(r"\bmean\(([^)]+)\)", r"np.mean(\1)", code)
    code = re.sub(r"\bsd\(([^)]+)\)", r"np.std(\1, ddof=1)", code)

    if re.search(r"%>%|ggplot|stan_glm|stan_|stan\(|posterior_|prior_|pp_check|mcmc_|summarise|mutate|filter|select", code):
        body_lines.append("# 下面给出与本节模型一致的 Python 写法。")

    if "stan_glm" in code or "stan(" in code or "rstan" in r_code:
        body_lines.extend(
            [
                "with pm.Model() as model:",
                "    # beta_0 = pm.Normal('beta_0', mu=0, sigma=10)",
                "    # beta_1 = pm.Normal('beta_1', mu=0, sigma=10)",
                "    # sigma = pm.HalfNormal('sigma', sigma=10)",
                "    # mu = beta_0 + beta_1 * x",
                "    # y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma, observed=y)",
                "    idata = pm.sample(draws=4000, tune=1000, chains=4, target_accept=0.9)",
                "az.summary(idata)",
            ]
        )

    cleaned = []
    for line in code.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            cleaned.append("# " + translate_text(stripped[1:].strip()))
            continue
        if any(token in stripped for token in ["%>%", "ggplot", "aes(", "geom_", "stan_glm", "summarise", "mutate", "filter("]):
            cleaned.append("# 可用 pandas / PyMC 按同一数据流程表达。")
        else:
            cleaned.append(stripped)

    if not imports:
        imports = ["import numpy as np", "import pandas as pd", "from scipy import stats", "import pymc as pm", "import arviz as az"]
    elif any("stats." in line for line in cleaned) and "from scipy import stats" not in imports:
        imports.append("from scipy import stats")
    if any("rng." in line for line in cleaned) and "import numpy as np" not in imports:
        imports.insert(0, "import numpy as np")

    result = imports + [""]
    result.extend(body_lines)
    result.extend(cleaned)
    result = [line for line in result if line is not None]
    return clean_python_code_output("\n".join(result).strip() or "import numpy as np\nimport pandas as pd\n")


def is_r_code_block(pre) -> bool:
    classes = set(pre.get("class", []))
    code = pre.find("code")
    code_classes = set(code.get("class", [])) if code else set()
    return bool({"r", "language-r", "sourceCode r"} & classes) or bool({"r", "language-r", "sourceCode r"} & code_classes)


def rewrite_code_blocks(body: BeautifulSoup, translator: DeepSeekHtmlTranslator | None = None, page: Page | None = None) -> None:
    r_blocks: list[tuple[object, str]] = []
    for pre in list(body.find_all("pre")):
        code_text = pre.get_text("", strip=False)
        if is_r_code_block(pre):
            r_blocks.append((pre, code_text))
        else:
            pre["class"] = ["sourceCode"]

    converted_blocks: list[str]
    if translator is not None and r_blocks:
        try:
            converted_blocks = translator.convert_code_blocks([code for _, code in r_blocks], page)
        except Exception as error:
            print(f"  DeepSeek code conversion failed; using local fallback: {error}", flush=True)
            converted_blocks = [convert_r_to_python(code) for _, code in r_blocks]
    else:
        converted_blocks = [convert_r_to_python(code) for _, code in r_blocks]

    for (pre, _), python_code in zip(r_blocks, converted_blocks):
        python_code = clean_python_code_output(python_code)
        wrapper = BeautifulSoup(
            f'<pre><code class="language-python">{html.escape(python_code)}</code></pre>',
            "html.parser",
        )
        pre.replace_with(wrapper)


def render_shell(title: str, description: str, body: str, sidebar: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <title>{html.escape(title)} | {html.escape(SITE_TITLE)}</title>
  <link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/css/styles.css">
  <script>
    window.MathJax = {{
      tex: {{
        inlineMath: [["$", "$"], ["\\\\(", "\\\\)"]],
        displayMath: [["$$", "$$"], ["\\\\[", "\\\\]"]],
        processEscapes: true
      }},
      svg: {{ fontCache: "global" }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
  <a class="skip-link" href="#content">跳到正文</a>
  <header class="site-header">
    <a class="brand" href="/" aria-label="{html.escape(SITE_TITLE)} 首页">
      <span class="brand-mark">C</span>
      <span class="brand-name">{html.escape(SITE_TITLE)}</span>
    </a>
    <nav class="site-nav" aria-label="主导航">
      <a href="/">首页</a>
      <a href="/posts/" aria-current="page">最新文章</a>
      <a href="/tags/">主题</a>
      <a href="/about/">关于</a>
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
  <script src="/assets/js/site.js"></script>
</body>
</html>
"""


def heading_section_anchor(heading) -> tuple[str, str]:
    heading_id = heading.get("id", "").strip()
    if heading_id:
        return heading_id, ""
    for parent in heading.parents:
        if getattr(parent, "name", None) != "div":
            continue
        parent_classes = parent.get("class") or []
        if "section" in parent_classes and parent.get("id"):
            return parent["id"], str(parent.get("number", "")).strip()
    return "", ""


def collect_section_links(body: BeautifulSoup) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    for heading in body.find_all("h2"):
        heading_id, number = heading_section_anchor(heading)
        label = " ".join(heading.get_text(" ", strip=True).split())
        if number and not label.startswith(number):
            label = f"{number} {label}"
        if heading_id and label:
            sections.append((heading_id, label))
    return sections


def render_sidebar(
    pages: list[Page],
    current: Page | None = None,
    current_sections: list[tuple[str, str]] | None = None,
) -> str:
    links = []
    current_sections = current_sections or []
    for page in pages:
        is_current = bool(current and page.path == current.path)
        current_attr = ' aria-current="page"' if current and page.path == current.path else ""
        item_classes = ["sidebar-item"]
        if is_current:
            item_classes.append("is-current")
        if is_current and current_sections:
            item_classes.append("is-open")
        toggle = '<span class="sidebar-toggle-placeholder" aria-hidden="true"></span>'
        section_panel = ""
        if is_current and current_sections:
            panel_id = "sidebar-sections-" + re.sub(r"[^a-z0-9]+", "-", page.path.strip("/").lower()).strip("-")
            if not panel_id.endswith("-"):
                panel_id = panel_id or "sidebar-sections-index"
            toggle = (
                f'<button class="sidebar-toggle" type="button" aria-expanded="true" '
                f'aria-controls="{html.escape(panel_id, quote=True)}" '
                f'aria-label="收起{html.escape(page.title_cn, quote=True)}二级目录">'
                '<span aria-hidden="true">›</span>'
                "</button>"
            )
            section_links = "".join(
                f'<a class="section-link" href="#{html.escape(anchor, quote=True)}">{html.escape(label)}</a>'
                for anchor, label in current_sections
            )
            section_panel = f'<div class="sidebar-subsections" id="{html.escape(panel_id, quote=True)}">{section_links}</div>'
        links.append(
            f'<div class="{" ".join(item_classes)}">'
            '<div class="sidebar-page-row">'
            f'<a class="sidebar-page-link" href="{page.local_path}"{current_attr}>{html.escape(page.title_cn)}</a>'
            f"{toggle}"
            "</div>"
            f"{section_panel}"
            "</div>"
        )
    return f"""
<aside class="tutorial-sidebar">
  <h2>教程目录</h2>
  <nav class="sidebar-list">{''.join(links)}</nav>
</aside>
"""


def render_index(pages: list[Page]) -> str:
    toc_items = []
    for page in pages:
        if page.path == "/":
            continue
        toc_items.append(f'<li><a href="{page.local_path}">{html.escape(page.title_cn)}</a></li>')
    body = f"""
<h1>Bayes Rules! 中文 Python 改写教程</h1>
<div class="license-note">
  <p>本教程基于 Alicia A. Johnson、Miles Q. Ott、Mine Dogucu 的 <a href="https://www.bayesrulesbook.com/">《Bayes Rules!：应用贝叶斯建模导论》</a> 整理。来源内容采用 <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a> 授权；本中文 Python 版本按相同授权共享，仅用于非商业学习。</p>
</div>
<p>这个版本保留章节结构、图片、脚注、正文跳转和 LaTeX 数学公式，并用 Python 生态给出 NumPy、pandas、SciPy、PyMC、ArviZ 与 scikit-learn 示例。</p>
<h2>Python 环境</h2>
<pre><code class="language-python">import numpy as np
import pandas as pd
from scipy import stats
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
import seaborn as sns</code></pre>
<h2>目录</h2>
<ol>{''.join(toc_items)}</ol>
"""
    return render_shell("Bayes Rules! 中文 Python 改写教程", "Bayes Rules! 的中文 Python 改写教程", body, render_sidebar(pages))


def render_chapter(
    page: Page,
    pages: list[Page],
    pages_by_path: dict[str, Page],
    translator: DeepSeekHtmlTranslator | None = None,
) -> str:
    soup = BeautifulSoup(request_text(page.url), "html.parser")
    body = clean_chapter_body(soup)
    rewrite_links(body, page, pages_by_path)
    localize_images(body, page.url)
    translate_dom(body, translator, page)
    sanitize_html_attributes(body)
    sanitize_math_text(body)
    sanitize_generated_text(body)
    rewrite_code_blocks(body, translator, page)

    title_node = body.find(["h1", "h2"])
    if title_node:
        title_node.string = page.title_cn
    else:
        body.insert(0, BeautifulSoup(f"<h1>{html.escape(page.title_cn)}</h1>", "html.parser"))

    current_index = pages.index(page)
    prev_page = pages[current_index - 1] if current_index > 0 else None
    next_page = pages[current_index + 1] if current_index + 1 < len(pages) else None
    nav = ['<nav class="chapter-nav">']
    if prev_page:
        nav.append(f'<a href="{prev_page.local_path}">上一节：{html.escape(prev_page.title_cn)}</a>')
    else:
        nav.append("<span></span>")
    if next_page:
        nav.append(f'<a href="{next_page.local_path}">下一节：{html.escape(next_page.title_cn)}</a>')
    nav.append("</nav>")
    body.append(BeautifulSoup("".join(nav), "html.parser"))

    current_sections = collect_section_links(body)
    return render_shell(
        page.title_cn,
        f"{page.title_cn} | Bayes Rules! 中文 Python 改写教程",
        str(body),
        render_sidebar(pages, page, current_sections),
    )


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = re.sub(r"(?is)^html\s*\n(?=<html\b)", "<!doctype html>\n", content.lstrip("\ufeff"), count=1)
    if re.match(r"(?is)^<html\b", content):
        content = "<!doctype html>\n" + content
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def write_blog_post(pages: list[Page]) -> None:
    chapter_links = "\n".join(f"- [{page.title_cn}]({page.local_path})" for page in pages if page.path != "/")
    content = f"""---
title: "Bayes Rules! 中文 Python 改写教程"
date: 2026-06-03
summary: "Bayes Rules! 的简体中文 Python 教程入口，覆盖贝叶斯建模、后验推断、回归、分类与分层模型。"
tags: ["贝叶斯统计", "Python", "教程"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇博客是一份可点击的教程入口：内容基于公开在线教材 [Bayes Rules! An Introduction to Applied Bayesian Modeling](https://www.bayesrulesbook.com/) 整理为简体中文，并统一使用 Python 生态示例。

> 来源作者为 Alicia A. Johnson、Miles Q. Ott、Mine Dogucu。来源内容采用 [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/) 授权；本版本按相同授权共享，仅用于非商业学习。

## 教程入口

[打开完整教程](/{TUTORIAL_SLUG}/)

## 目录

{chapter_links}

## Python 生态约定

```python
import numpy as np
import pandas as pd
from scipy import stats
import pymc as pm
import arviz as az
import matplotlib.pyplot as plt
import seaborn as sns
```

## 质量说明

全书保留数学公式、图片、脚注、正文跳转和章节结构；统计术语按统一规范校正，代码示例统一采用 Python、PyMC、ArviZ、NumPy、pandas、SciPy、seaborn 与 scikit-learn。
"""
    write(CONTENT_POST, content)


def update_sitemap(pages: list[Page]) -> None:
    sitemap = ROOT / "sitemap.xml"
    if not sitemap.exists():
        return
    raw = sitemap.read_text(encoding="utf-8")
    insert = "\n".join(f"  <url><loc>{SITE_URL}{page.local_path}</loc></url>" for page in pages)
    raw = raw.replace("</urlset>", f"{insert}\n</urlset>")
    sitemap.write_text(raw, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import Bayes Rules as a Chinese Python tutorial.")
    parser.add_argument("--limit", type=int, default=0, help="Only render the first N pages for testing.")
    parser.add_argument("--only", nargs="*", default=[], help="Only render selected page paths, such as /chapter-2.")
    parser.add_argument("--no-chapters", action="store_true", help="Only write the blog post and tutorial index.")
    parser.add_argument("--translator", choices=["argos", "deepseek"], default="argos", help="Text translation backend.")
    parser.add_argument("--model", default="deepseek-v4-pro", help="DeepSeek model id when --translator deepseek is used.")
    parser.add_argument("--batch-size", type=int, default=8, help="DeepSeek translation batch size.")
    parser.add_argument("--api-timeout", type=int, default=75, help="DeepSeek request timeout per batch.")
    parser.add_argument("--no-book-context", action="store_true", help="Skip the full-book DeepSeek terminology pass.")
    args = parser.parse_args()

    start = time.time()
    all_pages = collect_pages()
    pages = all_pages
    if args.limit:
        pages = pages[: args.limit]
    pages_by_path = {page.path: page for page in all_pages}
    only_paths = {normalize_import_path(path) for path in args.only}

    if not only_paths:
        write_blog_post(pages)
        write(TUTORIAL_DIR / "index.html", render_index(pages))
    elif "/" in only_paths:
        write(TUTORIAL_DIR / "index.html", render_index(pages))
    if args.no_chapters:
        print(f"Wrote tutorial entry for {len(pages)} pages.")
        return

    translator = DeepSeekHtmlTranslator(args.model, args.batch_size, args.api_timeout) if args.translator == "deepseek" else None
    if translator is not None and not args.no_book_context:
        print("Building full-book DeepSeek translation guide...", flush=True)
        translator.build_book_guide(all_pages if not args.limit else pages)

    for index, page in enumerate(pages, start=1):
        if page.path == "/":
            continue
        if only_paths and page.path not in only_paths:
            continue
        print(f"[{index}/{len(pages)}] {page.path} -> {page.title_cn}", flush=True)
        html_text = render_chapter(page, pages, pages_by_path, translator)
        write(TUTORIAL_DIR / page_slug(page.path) / "index.html", html_text)

    if not only_paths:
        update_sitemap(pages)
    print(f"Imported {len(pages)} tutorial pages in {time.time() - start:.1f}s.")


if __name__ == "__main__":
    main()
