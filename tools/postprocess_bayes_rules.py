from __future__ import annotations

from bs4 import BeautifulSoup

from import_bayes_rules import (
    TUTORIAL_DIR,
    sanitize_generated_text,
    sanitize_html_attributes,
    sanitize_math_text,
    write,
)


def main() -> None:
    count = 0
    for path in sorted(TUTORIAL_DIR.glob("**/index.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        sanitize_html_attributes(soup)
        sanitize_math_text(soup)
        sanitize_generated_text(soup)
        write(path, str(soup))
        count += 1
    print(f"Postprocessed {count} tutorial pages.")


if __name__ == "__main__":
    main()
