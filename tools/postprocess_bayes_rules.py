from __future__ import annotations

from bs4 import BeautifulSoup

from import_bayes_rules import (
    PAGE_TITLE_OVERRIDES,
    Page,
    TUTORIAL_DIR,
    collect_section_links,
    local_page_url,
    render_sidebar,
    sanitize_generated_text,
    sanitize_html_attributes,
    sanitize_math_text,
    write,
)


def tutorial_pages() -> list[Page]:
    return [
        Page(path=path, title_en="", title_cn=title, local_path=local_page_url(path), url="")
        for path, title in PAGE_TITLE_OVERRIDES.items()
    ]


def path_to_page_path(path) -> str:
    relative_parent = path.parent.relative_to(TUTORIAL_DIR).as_posix()
    return "/" if relative_parent == "." else f"/{relative_parent}"


def main() -> None:
    count = 0
    pages = tutorial_pages()
    pages_by_path = {page.path: page for page in pages}
    for path in sorted(TUTORIAL_DIR.glob("**/index.html")):
        soup = BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")
        current = pages_by_path.get(path_to_page_path(path))
        article = soup.select_one(".tutorial-content")
        sidebar = soup.select_one(".tutorial-sidebar")
        if current and article and sidebar:
            sections = collect_section_links(article)
            refreshed_sidebar = BeautifulSoup(render_sidebar(pages, current, sections), "html.parser")
            sidebar.replace_with(refreshed_sidebar.select_one(".tutorial-sidebar"))
        sanitize_html_attributes(soup)
        sanitize_math_text(soup)
        sanitize_generated_text(soup)
        write(path, str(soup))
        count += 1
    print(f"Postprocessed {count} tutorial pages.")


if __name__ == "__main__":
    main()
