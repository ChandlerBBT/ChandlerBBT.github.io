from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]
TUTORIAL_DIR = ROOT / "bayes-rules-python-cn"
REVIEW_SELECTOR = (
    "h1, h2, h3, h4, p, li, table, caption, blockquote, "
    "div.describe, div.example, div.exercise, div.goals, span.exercise"
)


def page_text(path: Path) -> str:
    soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
    article = soup.select_one(".tutorial-content") or soup
    for tag in article.find_all(["script", "style", "pre", "code", "math", "svg"]):
        tag.decompose()
    blocks: list[str] = []
    candidates = list(article.select(REVIEW_SELECTOR))
    candidate_ids = {id(tag) for tag in candidates}
    for tag in candidates:
        if any(id(parent) in candidate_ids for parent in tag.parents):
            continue
        text = " ".join(tag.get_text(" ", strip=True).split())
        if text:
            blocks.append(text)
    return "\n".join(blocks)


def suspicion_samples(text: str, limit: int = 40) -> list[str]:
    patterns = [
        r".{0,45}[QX]*Q\d*@@.{0,45}",
        r".{0,45}@@\d+@@.{0,45}",
        r".{0,45}\d+@@.{0,45}",
        r".{0,45}�.{0,45}",
        r".{0,45}#{8,}.{0,45}",
        r".{0,45}(Exercise|FIGURE|TABLE|Chapter|Section)\b.{0,120}",
        r".{0,45}(原书|原教程|R 代码|Python 转写).{0,80}",
        r".{0,45}(常数正常化|可能性函数|后部|酒吧图|感叹点).{0,80}",
    ]
    hits: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            sample = " ".join(match.group(0).split())
            if sample and sample not in hits:
                hits.append(sample)
            if len(hits) >= limit:
                return hits
    return hits


def review_page(path: Path, model: str, api_key: str) -> dict:
    text = page_text(path)
    system = (
        "你是中文统计教材的终审校对。请严格审查文本是否存在：符号乱码、占位符残留、漏翻英文、"
        "机器翻译腔、不通顺句子、统计术语误译、迁移痕迹、脚注或跳转语义丢失。"
        "脚注中的 ↩︎ 表示可点击返回正文的正常回链，不要把它本身判为错误。"
        "不要重写全文，只输出 JSON。"
    )
    payload = {
        "page": path.relative_to(ROOT).as_posix(),
        "suspicion_samples": suspicion_samples(text),
        "text": text[:60000],
        "schema": {
            "score_0_to_100": "integer",
            "publishable": "boolean",
            "critical_issues": ["string"],
            "representative_fixes": [{"source": "string", "rewrite": "string", "reason": "string"}],
            "next_actions": ["string"],
        },
    }
    response = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        },
        timeout=180,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", content, flags=re.DOTALL)
    if fenced:
        content = fenced.group(1).strip()
    data = json.loads(content)
    data["page"] = path.relative_to(ROOT).as_posix()
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask DeepSeek to review Bayes Rules tutorial translation quality.")
    parser.add_argument("--model", default="deepseek-v4-pro")
    parser.add_argument("--page", help="Relative tutorial page, for example chapter-2/index.html.")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--out", default="tools/bayes_rules_deepseek_review.json")
    args = parser.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not set.")

    if args.page:
        pages = [TUTORIAL_DIR / args.page]
    else:
        pages = sorted(TUTORIAL_DIR.glob("**/index.html"))
        if args.limit:
            pages = pages[: args.limit]

    reports = [review_page(page, args.model, api_key) for page in pages]
    output = ROOT / args.out
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote DeepSeek review for {len(reports)} page(s) to {output.relative_to(ROOT).as_posix()}.")


if __name__ == "__main__":
    main()
