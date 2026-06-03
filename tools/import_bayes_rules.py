from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

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
    "bayesrules": ["# 原书 bayesrules 数据包中的数据需改用 CSV/本地数据文件读取"],
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


def translate_dom(root: BeautifulSoup) -> None:
    skip = {"script", "style", "pre", "code", "math", "svg"}
    block_selector = "h1, h2, h3, h4, p, li, th, td, figcaption, blockquote"
    for tag in list(root.select(block_selector)):
        if tag.name in skip or any(parent.name in skip for parent in tag.parents):
            continue
        # Let nested paragraphs/lists handle their own text.
        if tag.name == "li" and tag.find(["p", "ol", "ul"]):
            continue
        if tag.find("pre"):
            continue
        raw = " ".join(tag.get_text(" ", strip=True).split())
        if not raw or not re.search(r"[A-Za-z]", raw):
            continue
        translated = translate_text(raw)
        tag.clear()
        tag.append(translated)

    for tag in root.find_all(["img", "a"]):
        if tag.has_attr("alt") and tag["alt"]:
            tag["alt"] = translate_text(tag["alt"])
        if tag.has_attr("title") and tag["title"]:
            tag["title"] = translate_text(tag["title"])


def clean_chapter_body(soup: BeautifulSoup) -> BeautifulSoup:
    body = soup.select_one(".body-inner .page-wrapper .page-inner section.normal")
    if body is None:
        body = soup.select_one(".body-inner") or soup.body or soup
    body = BeautifulSoup(str(body), "html.parser")

    for selector in [
        ".header-section-number",
        ".footnotes",
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


def convert_r_to_python(r_code: str) -> str:
    imports: list[str] = []
    body_lines: list[str] = []
    packages = re.findall(r"library\(([^)]+)\)", r_code)
    for package in packages:
        package = package.strip().strip("\"'")
        for line in CODE_IMPORTS.get(package, [f"# TODO: 为 R 包 {package} 选择 Python 等价库"]):
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
        body_lines.append("# 该段原 R 代码依赖 tidyverse / rstanarm 的管道或建模语法。")
        body_lines.append("# 下面给出 Python 转写骨架；请按原文中的数据列名补齐。")

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
            cleaned.append("# TODO: 按原教程的数据处理意图补写对应的 pandas / PyMC 语句。")
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
    return "\n".join(result).strip() or "# 这一段 R 代码需要结合上下文改写为 Python。"


def rewrite_code_blocks(body: BeautifulSoup) -> None:
    for pre in list(body.find_all("pre")):
        classes = set(pre.get("class", []))
        code = pre.find("code")
        code_text = pre.get_text("", strip=False)
        if "r" in classes or (code and "r" in code.get("class", [])):
            python_code = convert_r_to_python(code_text)
            wrapper = BeautifulSoup(
                f"""
<div class="python-note"><strong>Python 转写</strong><p>原教程中的 R 代码已改写为 Python 方向，优先使用 NumPy、pandas、SciPy、PyMC、ArviZ 与 scikit-learn。</p></div>
<pre><code class="language-python">{html.escape(python_code)}</code></pre>
""",
                "html.parser",
            )
            pre.replace_with(wrapper)
        else:
            pre["class"] = ["sourceCode"]


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


def render_sidebar(pages: list[Page], current: Page | None = None) -> str:
    links = []
    for page in pages:
        current_attr = ' aria-current="page"' if current and page.path == current.path else ""
        links.append(f'<a href="{page.local_path}"{current_attr}>{html.escape(page.title_cn)}</a>')
    return f"""
<aside class="tutorial-sidebar">
  <h2>教程目录</h2>
  <nav>{''.join(links)}</nav>
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
  <p>本教程改编自 Alicia A. Johnson、Miles Q. Ott、Mine Dogucu 的 <a href="https://www.bayesrulesbook.com/">Bayes Rules! An Introduction to Applied Bayesian Modeling</a>。原作采用 <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a> 授权；本中文 Python 改写版按相同授权共享，仅用于非商业学习。</p>
</div>
<p>这个版本保留原书的章节结构、图片和 LaTeX 数学公式，并把原教程中的 R / rstan / rstanarm 代码块转写为 Python 方向的 NumPy、pandas、SciPy、PyMC、ArviZ 与 scikit-learn 示例。离线机器翻译已经用贝叶斯统计术语表做过一轮校正，但长篇教材仍建议逐章人工复核。</p>
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


def render_chapter(page: Page, pages: list[Page], pages_by_path: dict[str, Page]) -> str:
    soup = BeautifulSoup(request_text(page.url), "html.parser")
    body = clean_chapter_body(soup)
    rewrite_links(body, page, pages_by_path)
    localize_images(body, page.url)
    rewrite_code_blocks(body)
    translate_dom(body)

    title_node = body.find(["h1", "h2"])
    if title_node:
        title_node.string = page.title_cn
    else:
        body.insert(0, BeautifulSoup(f"<h1>{html.escape(page.title_cn)}</h1>", "html.parser"))

    notice = BeautifulSoup(
        """
<div class="tutorial-note">
  <p>译注：本页为原教程的中文 Python 改写初稿。统计术语已按“先验分布、似然函数、后验分布、后验预测、后验可信区间、共轭族、分层模型”等常用译法校正；代码块已替换为 Python 生态的转写或骨架。</p>
</div>
""",
        "html.parser",
    )
    first_heading = body.find(["h1", "h2"])
    if first_heading:
        first_heading.insert_after(notice)

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

    return render_shell(page.title_cn, f"{page.title_cn} | Bayes Rules! 中文 Python 改写教程", str(body), render_sidebar(pages, page))


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def write_blog_post(pages: list[Page]) -> None:
    chapter_links = "\n".join(f"- [{page.title_cn}]({page.local_path})" for page in pages if page.path != "/")
    content = f"""---
title: "Bayes Rules! 中文 Python 改写教程"
date: 2026-06-03
summary: "把 Bayes Rules! 在线教程改编为简体中文，并将 R/rstan/rstanarm 示例转写为 Python/PyMC/ArviZ 生态。"
tags: ["贝叶斯统计", "Python", "教程"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

这篇博客是一份可点击的教程入口：我把公开在线教材 [Bayes Rules! An Introduction to Applied Bayesian Modeling](https://www.bayesrulesbook.com/) 改编为简体中文，并把原教程里的 R 代码转写为 Python 生态示例。

> 原作作者为 Alicia A. Johnson、Miles Q. Ott、Mine Dogucu。原作采用 [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/) 授权；本改写版按相同授权共享，仅用于非商业学习。

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

这是离线批量翻译和代码迁移的第一版。数学公式、图片和章节结构已经保留；统计术语做了一轮校正。个别长段落和复杂 R 管道代码仍建议继续人工复核。
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
    parser.add_argument("--no-chapters", action="store_true", help="Only write the blog post and tutorial index.")
    args = parser.parse_args()

    start = time.time()
    pages = collect_pages()
    if args.limit:
        pages = pages[: args.limit]
    pages_by_path = {page.path: page for page in pages}

    write_blog_post(pages)
    write(TUTORIAL_DIR / "index.html", render_index(pages))
    if args.no_chapters:
        print(f"Wrote tutorial entry for {len(pages)} pages.")
        return

    for index, page in enumerate(pages, start=1):
        if page.path == "/":
            continue
        print(f"[{index}/{len(pages)}] {page.path} -> {page.title_cn}", flush=True)
        html_text = render_chapter(page, pages, pages_by_path)
        write(TUTORIAL_DIR / page_slug(page.path) / "index.html", html_text)

    update_sitemap(pages)
    print(f"Imported {len(pages)} tutorial pages in {time.time() - start:.1f}s.")


if __name__ == "__main__":
    main()
