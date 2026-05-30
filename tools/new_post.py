from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POSTS_DIR = ROOT / "content" / "posts"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", value)
    return value.strip("-") or "new-post"


def main() -> None:
    title = " ".join(sys.argv[1:]).strip()
    if not title:
        raise SystemExit("Usage: python tools/new_post.py \"文章标题\"")

    today = dt.date.today().isoformat()
    slug = slugify(title)
    path = POSTS_DIR / f"{today}-{slug}.md"
    if path.exists():
        raise SystemExit(f"Post already exists: {path}")

    path.write_text(
        f"""---
title: "{title}"
date: {today}
summary: "用一句话说明这篇文章要解决的问题。"
tags: ["阶段性沉淀"]
cover: "/assets/img/hero-workspace.png"
draft: false
---

## 这次想解决什么问题

写下背景、约束和你真正想澄清的判断。

## 我做了什么

- 步骤一
- 步骤二
- 步骤三

## 得到的结论

把可复用的判断、方法或清单沉淀出来。

## 还有哪些边界

哪些地方还不确定，下一步要继续验证什么。
""",
        encoding="utf-8",
    )
    print(path)


if __name__ == "__main__":
    main()
