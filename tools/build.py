from __future__ import annotations

import datetime as dt
import html
import re
import shutil
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

try:
    import markdown as markdown_lib
except ImportError:  # pragma: no cover - local fallback for minimal environments.
    markdown_lib = None


ROOT = Path(__file__).resolve().parents[1]
CONTENT_DIR = ROOT / "content" / "posts"
SITE_URL = "https://chandlerbbt.github.io"
SITE_TITLE = "Chandler's AI Productivity Notes"
SITE_SUBTITLE = "AI 提效研究笔记"
SITE_DESCRIPTION = "记录我在工作与学习中，围绕 AI 提升效率的探索、实践与复盘。"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", value)
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    return value.strip("-") or "post"


def parse_value(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        items = raw[1:-1].split(",")
        return [item.strip().strip("\"'") for item in items if item.strip()]
    if "," in raw and not raw.startswith(("http://", "https://", "/")):
        return [item.strip().strip("\"'") for item in raw.split(",") if item.strip()]
    return raw.strip("\"'")


def parse_post(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    if not raw.startswith("---\n"):
        raise ValueError(f"{path.name} is missing front matter.")

    _, front, body = raw.split("---\n", 2)
    meta: dict[str, object] = {}
    for line in front.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = parse_value(value)

    date_value = str(meta.get("date", "")).strip() or path.stem[:10]
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    slug = str(meta.get("slug", "")) or path.stem
    return {
        "source": path,
        "slug": slugify(slug),
        "title": str(meta.get("title", path.stem)),
        "date": date_value,
        "summary": str(meta.get("summary", "")),
        "version": str(meta.get("version", "")),
        "tags": [str(tag) for tag in tags],
        "cover": str(meta.get("cover", "/assets/img/hero-workspace.png")),
        "draft": str(meta.get("draft", "false")).lower() == "true",
        "body": body.strip(),
    }


def inline_markdown(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )
    return text


def flush_paragraph(out: list[str], paragraph: list[str]) -> None:
    if paragraph:
        out.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
        paragraph.clear()


def close_list(out: list[str], list_type: str | None) -> None:
    if list_type:
        out.append(f"</{list_type}>")


def fallback_markdown_to_html(markdown: str) -> str:
    out: list[str] = []
    paragraph: list[str] = []
    list_type: str | None = None
    in_code = False
    code_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                out.append("<pre><code>" + html.escape("\n".join(code_lines)) + "</code></pre>")
                code_lines.clear()
                in_code = False
            else:
                flush_paragraph(out, paragraph)
                close_list(out, list_type)
                list_type = None
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            flush_paragraph(out, paragraph)
            close_list(out, list_type)
            list_type = None
            continue

        image = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)$", line)
        if image:
            flush_paragraph(out, paragraph)
            close_list(out, list_type)
            list_type = None
            alt = html.escape(image.group(1), quote=True)
            src = html.escape(image.group(2), quote=True)
            out.append(f'<figure class="article-figure"><img src="{src}" alt="{alt}" loading="lazy"></figure>')
            continue

        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            flush_paragraph(out, paragraph)
            close_list(out, list_type)
            list_type = None
            level = len(heading.group(1))
            text = inline_markdown(heading.group(2))
            out.append(f"<h{level}>{text}</h{level}>")
            continue

        quote = re.match(r"^>\s+(.+)$", line)
        if quote:
            flush_paragraph(out, paragraph)
            close_list(out, list_type)
            list_type = None
            out.append(f"<blockquote>{inline_markdown(quote.group(1))}</blockquote>")
            continue

        unordered = re.match(r"^[-*]\s+(.+)$", line)
        ordered = re.match(r"^\d+\.\s+(.+)$", line)
        if unordered or ordered:
            flush_paragraph(out, paragraph)
            wanted = "ul" if unordered else "ol"
            if list_type != wanted:
                close_list(out, list_type)
                out.append(f"<{wanted}>")
                list_type = wanted
            item = unordered.group(1) if unordered else ordered.group(1)
            out.append(f"<li>{inline_markdown(item)}</li>")
            continue

        paragraph.append(line.strip())

    flush_paragraph(out, paragraph)
    close_list(out, list_type)
    return "\n".join(out)


def markdown_to_html(markdown: str) -> str:
    if markdown_lib is None:
        return fallback_markdown_to_html(markdown)
    return markdown_lib.markdown(
        markdown,
        extensions=["extra", "toc", "sane_lists", "smarty"],
        extension_configs={"toc": {"permalink": False}},
        output_format="html5",
    )


def date_label(value: str) -> str:
    try:
        parsed = dt.date.fromisoformat(value)
        return parsed.strftime("%Y.%m.%d")
    except ValueError:
        return value


def reading_minutes(markdown: str) -> int:
    plain = re.sub(r"[#>*`\-\[\]().]", "", markdown)
    units = len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9]+", plain))
    return max(1, round(units / 450))


def post_url(post: dict) -> str:
    return f"/posts/{post['slug']}/"


def render_tags(tags: list[str]) -> str:
    return "".join(f'<a class="tag" href="/tags/{slugify(tag)}/">{html.escape(tag)}</a>' for tag in tags)


def render_version_badge(version: str) -> str:
    version = version.strip()
    if not version:
        return ""
    label = version if version.lower().startswith("v") else f"v{version}"
    return f'<span class="version-badge">{html.escape(label)}</span>'


def nav(active: str) -> str:
    items = [
        ("home", "/", "首页"),
        ("posts", "/posts/", "最新文章"),
        ("tags", "/tags/", "主题"),
        ("about", "/about/", "关于"),
    ]
    links = []
    for key, href, label in items:
        selected = ' aria-current="page"' if key == active else ""
        links.append(f'<a href="{href}"{selected}>{label}</a>')
    return "\n".join(links)


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


def base(title: str, description: str, active: str, content: str, body_class: str = "") -> str:
    full_title = title if title == SITE_TITLE else f"{title} | {SITE_TITLE}"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description, quote=True)}">
  <meta property="og:title" content="{html.escape(full_title, quote=True)}">
  <meta property="og:description" content="{html.escape(description, quote=True)}">
  <meta property="og:type" content="website">
  <meta property="og:image" content="/assets/img/hero-workspace.png">
  <title>{html.escape(full_title)}</title>
  <link rel="icon" href="/assets/img/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/assets/css/styles.css">
  <link rel="alternate" type="application/rss+xml" title="{html.escape(SITE_TITLE)}" href="/feed.xml">
  {mathjax_script()}
</head>
<body class="{body_class}">
  <a class="skip-link" href="#content">跳到正文</a>
  <header class="site-header">
    <a class="brand" href="/" aria-label="{html.escape(SITE_TITLE)} 首页">
      <span class="brand-mark">C</span>
      <span class="brand-name">{html.escape(SITE_TITLE)}</span>
    </a>
    <nav class="site-nav" aria-label="主导航">
      {nav(active)}
    </nav>
  </header>
  <main id="content">
    {content}
  </main>
  <footer class="site-footer">
    <div>
      <strong>{html.escape(SITE_SUBTITLE)}</strong>
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


def post_card(post: dict, featured: bool = False) -> str:
    classes = "post-card featured" if featured else "post-card"
    excerpt = post["summary"] or "阶段性沉淀，留待继续展开。"
    return f"""
<article class="{classes}" data-title="{html.escape(str(post['title']).lower(), quote=True)}" data-tags="{html.escape(' '.join(post['tags']).lower(), quote=True)}">
  <a class="post-card-media" href="{post_url(post)}">
    <img src="{html.escape(str(post['cover']), quote=True)}" alt="" loading="lazy">
  </a>
  <div class="post-card-body">
    <div class="post-meta">
      <time datetime="{html.escape(str(post['date']))}">{date_label(str(post['date']))}</time>
      {render_version_badge(str(post.get('version', '')))}
      <span>{reading_minutes(str(post['body']))} 分钟读完</span>
    </div>
    <h2><a href="{post_url(post)}">{html.escape(str(post['title']))}</a></h2>
    <p>{html.escape(str(excerpt))}</p>
    <div class="tag-row">{render_tags(post['tags'])}</div>
  </div>
</article>
"""


def render_home(posts: list[dict], all_tags: list[str]) -> str:
    latest = posts[0]
    other_posts = posts[1:6]
    tag_buttons = "".join(
        f'<button type="button" class="filter-chip" data-filter="{html.escape(tag.lower(), quote=True)}">{html.escape(tag)}</button>'
        for tag in all_tags[:8]
    )
    list_items = "\n".join(post_card(post) for post in other_posts) or "<p>更多文章正在路上。</p>"
    content = f"""
<section class="hero">
  <div class="hero-overlay">
    <p class="section-label">{html.escape(SITE_SUBTITLE)}</p>
    <h1>{html.escape(SITE_TITLE)}</h1>
    <p>{html.escape(SITE_DESCRIPTION)}</p>
    <div class="hero-actions">
      <a class="button primary" href="#latest">最新文章</a>
      <a class="button secondary" href="/tags/">浏览主题</a>
    </div>
  </div>
</section>
<section class="content-band" id="latest">
  <div class="section-heading">
    <div>
      <p class="section-label">最新文章</p>
      <h2>把想法变成可分享的周期沉淀</h2>
    </div>
    <label class="search-box">
      <span>搜索</span>
      <input type="search" data-search placeholder="输入关键词或标签">
    </label>
  </div>
  <div class="home-grid">
    <div class="post-list" data-post-list>
      {post_card(latest, featured=True)}
      {list_items}
    </div>
    <aside class="rail" aria-label="主题筛选">
      <section>
        <h3>标签</h3>
        <div class="filter-row">
          <button type="button" class="filter-chip active" data-filter="">全部</button>
          {tag_buttons}
        </div>
      </section>
      <section>
        <h3>沉淀节奏</h3>
        <p>每次阶段性复盘，尽量沉淀成一篇面向同事朋友也能读懂的文章：问题、方法、实验、局限、下一步。</p>
      </section>
    </aside>
  </div>
</section>
"""
    return base(SITE_TITLE, SITE_DESCRIPTION, "home", content, "home-page")


def render_posts_index(posts: list[dict]) -> str:
    cards = "\n".join(post_card(post) for post in posts)
    content = f"""
<section class="page-hero compact">
  <p class="section-label">最新文章</p>
  <h1>阶段性沉淀</h1>
  <p>所有公开分享的研究札记都会在这里归档。</p>
</section>
<section class="content-band">
  <div class="section-heading">
    <h2>全部文章</h2>
    <label class="search-box">
      <span>搜索</span>
      <input type="search" data-search placeholder="输入关键词或标签">
    </label>
  </div>
  <div class="post-list" data-post-list>{cards}</div>
</section>
"""
    return base("最新文章", "所有博客文章归档", "posts", content)


def render_tag_index(all_tags: list[str], posts: list[dict]) -> str:
    tag_blocks = []
    for tag in all_tags:
        count = sum(1 for post in posts if tag in post["tags"])
        tag_blocks.append(f'<a class="tag-card" href="/tags/{slugify(tag)}/"><strong>{html.escape(tag)}</strong><span>{count} 篇</span></a>')
    content = f"""
<section class="page-hero compact">
  <p class="section-label">主题</p>
  <h1>按问题域回看沉淀</h1>
  <p>用标签把文章和长期研究线索连接起来。</p>
</section>
<section class="content-band">
  <div class="tag-grid">{''.join(tag_blocks)}</div>
</section>
"""
    return base("主题", "博客主题标签", "tags", content)


def render_tag_page(tag: str, posts: list[dict]) -> str:
    cards = "\n".join(post_card(post) for post in posts)
    content = f"""
<section class="page-hero compact">
  <p class="section-label">主题</p>
  <h1>{html.escape(tag)}</h1>
  <p>这个主题下的所有文章。</p>
</section>
<section class="content-band">
  <div class="post-list">{cards}</div>
</section>
"""
    return base(tag, f"{tag} 主题文章", "tags", content)


def render_about() -> str:
    content = """
<section class="page-hero compact">
  <p class="section-label">关于</p>
  <h1>这不是一个教程站，而是一间公开的研究工作室</h1>
  <p>我会把 AI 提效、知识管理、工作流实验里的阶段性思考整理成文章，方便自己复盘，也方便同事和朋友快速理解。</p>
</section>
<section class="content-band article-body">
  <h2>写作原则</h2>
  <ul>
    <li>先讲问题，再讲方法。</li>
    <li>保留实验过程中的失败、边界和下一步。</li>
    <li>尽量把个人经验沉淀成可迁移的模板、清单或工作流。</li>
  </ul>
  <h2>内容方向</h2>
  <p>这里会持续记录 AI 工作流、Codex/VS Code/DeepSeek 环境适配、第三方 skills 试验、内容生产流水线，以及个人知识管理的复利机制。</p>
</section>
"""
    return base("关于", "博客说明", "about", content)


def render_post(post: dict) -> str:
    article = markdown_to_html(str(post["body"]))
    content = f"""
<article class="article-shell">
  <header class="article-header">
    <div class="article-kicker">{render_tags(post['tags'])}</div>
    <h1>{html.escape(str(post['title']))}</h1>
    <div class="post-meta">
      <time datetime="{html.escape(str(post['date']))}">{date_label(str(post['date']))}</time>
      {render_version_badge(str(post.get('version', '')))}
      <span>{reading_minutes(str(post['body']))} 分钟读完</span>
    </div>
  </header>
  <img class="article-cover" src="{html.escape(str(post['cover']), quote=True)}" alt="">
  <div class="article-body">
    {article}
  </div>
</article>
"""
    return base(str(post["title"]), str(post["summary"]), "posts", content, "article-page")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = "\n".join(line.rstrip() for line in content.splitlines()) + "\n"
    path.write_text(normalized, encoding="utf-8")


def render_feed(posts: list[dict]) -> str:
    items = []
    for post in posts[:20]:
        url = SITE_URL + post_url(post)
        try:
            pub_date = dt.datetime.fromisoformat(str(post["date"])).strftime("%a, %d %b %Y 00:00:00 +0800")
        except ValueError:
            pub_date = dt.datetime.now(dt.UTC).strftime("%a, %d %b %Y 00:00:00 +0800")
        items.append(f"""
    <item>
      <title>{xml_escape(str(post['title']))}</title>
      <link>{url}</link>
      <guid>{url}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>{xml_escape(str(post['summary']))}</description>
    </item>""")
    return f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0">
  <channel>
    <title>{xml_escape(SITE_TITLE)}</title>
    <link>{SITE_URL}</link>
    <description>{xml_escape(SITE_DESCRIPTION)}</description>
    {''.join(items)}
  </channel>
</rss>
"""


def render_sitemap(posts: list[dict], tags: list[str]) -> str:
    urls = ["/", "/posts/", "/tags/", "/about/"]
    urls.extend(post_url(post) for post in posts)
    urls.extend(f"/tags/{slugify(tag)}/" for tag in tags)
    tutorial_root = ROOT / "bayes-rules-python-cn"
    if tutorial_root.exists():
        for index_file in sorted(tutorial_root.glob("**/index.html")):
            rel = "/" + index_file.parent.relative_to(ROOT).as_posix().strip("/") + "/"
            if rel not in urls:
                urls.append(rel)
    entries = "\n".join(f"  <url><loc>{SITE_URL}{url}</loc></url>" for url in urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{entries}
</urlset>
"""


def main() -> None:
    for generated in ["posts", "tags", "about"]:
        target = ROOT / generated
        if target.exists():
            shutil.rmtree(target)

    posts = []
    for path in sorted(CONTENT_DIR.glob("*.md")):
        try:
            posts.append(parse_post(path))
        except ValueError:
            continue
    posts = [post for post in posts if not post["draft"]]
    posts.sort(key=lambda post: str(post["date"]), reverse=True)
    if not posts:
        raise SystemExit("No published posts found in content/posts.")

    tags = sorted({tag for post in posts for tag in post["tags"]})

    write(ROOT / "index.html", render_home(posts, tags))
    write(ROOT / "posts" / "index.html", render_posts_index(posts))
    write(ROOT / "tags" / "index.html", render_tag_index(tags, posts))
    write(ROOT / "about" / "index.html", render_about())
    write(ROOT / "feed.xml", render_feed(posts))
    write(ROOT / "sitemap.xml", render_sitemap(posts, tags))

    for post in posts:
        write(ROOT / "posts" / str(post["slug"]) / "index.html", render_post(post))

    for tag in tags:
        tagged_posts = [post for post in posts if tag in post["tags"]]
        write(ROOT / "tags" / slugify(tag) / "index.html", render_tag_page(tag, tagged_posts))

    print(f"Built {len(posts)} posts and {len(tags)} tags.")


if __name__ == "__main__":
    main()
