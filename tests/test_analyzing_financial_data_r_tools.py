import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import analyzing_financial_data_r_common as common  # noqa: E402
import check_analyzing_financial_data_r as checker  # noqa: E402
import translate_analyzing_financial_data_r as translator  # noqa: E402


class AnalyzingFinancialDataCommonTests(unittest.TestCase):
    def test_book_identity_and_numbered_chapter_slug(self) -> None:
        self.assertEqual(common.SLUG, "analyzing-financial-data-r-cn")
        self.assertEqual(common.slugify_title("1 Prices"), "chapter-1")
        self.assertEqual(common.slugify_title("10 Machine Learning Models"), "chapter-10")

    def test_render_r_code_block_escapes_and_does_not_create_tabs(self) -> None:
        html = common.render_r_code_block("code-001", "x <- c(1, 2)\nplot(x < 3)")

        self.assertIn('class="r-code-block"', html)
        self.assertIn('class="language-r"', html)
        self.assertIn("x &lt;- c(1, 2)", html)
        self.assertIn("x &lt; 3", html)
        self.assertNotIn('class="code-tabs"', html)
        self.assertNotIn("language-python", html)

    def test_replace_r_code_placeholders_uses_structured_original_r(self) -> None:
        html = common.replace_r_code_placeholders(
            "<p>前文</p>[[R_CODE:code-001]]<p>后文</p>",
            [{"id": "code-001", "r_code": "library(quantmod)\ngetSymbols('AMZN')"}],
        )

        self.assertIn("<p>前文</p>", html)
        self.assertIn("library(quantmod)", html)
        self.assertIn("getSymbols", html)
        self.assertNotIn("[[R_CODE", html)


class AnalyzingFinancialDataTranslatorTests(unittest.TestCase):
    def test_separate_adjacent_blocks_prevents_heading_concatenation(self) -> None:
        raw = "<p>段落。</p><h2 id=\"section-1-1\">1.1 标题</h2><p>下一段。</p>"

        html = translator.separate_adjacent_blocks(raw)

        self.assertIn("</p>\n<h2", html)
        self.assertIn("</h2>\n<p>", html)

    def test_clean_fragment_replaces_r_code_placeholders(self) -> None:
        payload = {"images_on_page": [], "captions_on_page": []}
        response = {"r_code_blocks": [{"id": "code-001", "r_code": "mean(x)"}]}

        html = translator.clean_fragment(
            '<section class="book-page" data-pdf-page="12"><p>代码：</p><p>[[R_CODE:code-001]]</p></section>',
            12,
            payload,
            response,
        )

        self.assertIn('class="language-r"', html)
        self.assertIn("mean(x)", html)
        self.assertNotIn("[[R_CODE", html)

    def test_clean_fragment_strips_unit_h1_from_non_start_page(self) -> None:
        payload = {
            "unit": {"pdf_page_start": 16},
            "images_on_page": [],
            "captions_on_page": [],
        }

        html = translator.clean_fragment(
            '<section class="book-page" data-pdf-page="29"><h1>第1章 价格</h1><p>正文。</p></section>',
            29,
            payload,
            {},
        )

        self.assertNotIn("<h1>", html)
        self.assertIn("<p>正文。</p>", html)

    def test_render_sidebar_uses_translated_section_title_map(self) -> None:
        units = [
            {
                "slug": "chapter-1",
                "title_en": "1 Prices",
                "sections": [{"slug": "section-1-1", "title_en": "1.1 Price Versus Value"}],
            }
        ]

        html = translator.render_sidebar(
            units,
            {"chapter-1": "第 1 章 价格"},
            "chapter-1",
            {"section-1-1": "1.1 价格与价值"},
        )

        self.assertIn("1.1 价格与价值", html)
        self.assertNotIn("Price Versus Value", html)

    def test_extract_section_title_map_reads_anchor_heading_pairs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_cache_dir = translator.CACHE_DIR
            try:
                translator.CACHE_DIR = Path(tmp)
                page_dir = translator.CACHE_DIR / "page_translations"
                page_dir.mkdir()
                (page_dir / "page-001.json").write_text(
                    json.dumps(
                        {
                            "html": (
                                '<span class="section-anchor" id="section-2-8"></span>'
                                "<h2>2.8 比较多种证券的表现</h2>"
                                '<h2 id="references-4">References</h2>'
                            )
                        },
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
                units = [
                    {
                        "sections": [
                            {"slug": "section-2-8"},
                            {"slug": "references-4"},
                        ]
                    }
                ]

                titles = translator.extract_section_title_map_from_translations(units)
            finally:
                translator.CACHE_DIR = old_cache_dir

        self.assertEqual(titles["section-2-8"], "2.8 比较多种证券的表现")
        self.assertEqual(titles["references-4"], "参考文献")

    def test_render_sidebar_uses_known_section_title_fallbacks(self) -> None:
        units = [
            {
                "slug": "chapter-2",
                "title_en": "2 Single Security Returns",
                "sections": [
                    {
                        "slug": "section-2-8",
                        "title_en": "2.8 Comparing Performance of Multiple Securities",
                    },
                    {"slug": "references-4", "title_en": "References"},
                ],
            }
        ]

        html = translator.render_sidebar(units, {"chapter-2": "第2章 单个证券收益率"}, "chapter-2")

        self.assertIn("2.8 比较多种证券的表现", html)
        self.assertIn("参考文献", html)
        self.assertNotIn("Comparing Performance of Multiple Securities", html)

    def test_write_blog_post_uses_stable_task_date(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            old_root = translator.ROOT
            try:
                translator.ROOT = Path(tmp)
                path = translator.write_blog_post(
                    {"units": [{"slug": "chapter-1", "title_en": "1 Prices", "sections": []}]},
                    "{}",
                )
                text = path.read_text(encoding="utf-8")
            finally:
                translator.ROOT = old_root

        self.assertEqual(path.name, "2026-06-24-analyzing-financial-data-r-cn.md")
        self.assertIn("date: 2026-06-24", text)

    def test_final_render_cleanup_splits_leading_r_code_from_prose(self) -> None:
        raw = '<section><p>1 &gt; dim(x) 2 [1] 10 2 步骤2：继续说明。</p></section>'

        html = translator.final_render_cleanup(raw)

        self.assertIn('class="language-r"', html)
        self.assertIn("1 &gt; dim(x) 2 [1] 10 2", html)
        self.assertIn("<p>步骤2：继续说明。</p>", html)

    def test_final_render_cleanup_removes_chart_artifact_paragraphs(self) -> None:
        raw = (
            '<section><p>2008 2010 2012 2014 2016 2018 2020</p>'
            '<p>10-Year Treasury Inflation Protected Securities</p>'
            '<figure class="book-figure"><img src="/assets/img/x.png"><figcaption>图9.7 实际国债收益率</figcaption></figure>'
            '<p>正文。</p></section>'
        )

        html = translator.final_render_cleanup(raw)

        self.assertNotIn("10-Year Treasury", html)
        self.assertNotIn("2008 2010", html)
        self.assertIn("<p>正文。</p>", html)


    def test_final_render_cleanup_translates_source_credit(self) -> None:
        raw = (
            '<figcaption>图8.6 断点。数据来源：'
            'Price data reproduced with permission of CSI \u00a92020. www.csidata.com'
            "</figcaption>"
        )

        html = translator.final_render_cleanup(raw)

        self.assertIn("\u4ef7\u683c\u6570\u636e\u7ecf CSI \u00a92020 \u6388\u6743\u8f6c\u8f7d", html)
        self.assertNotIn("Price data reproduced with permission", html)


class AnalyzingFinancialDataCheckerTests(unittest.TestCase):
    def test_checker_counts_r_blocks_and_flags_forbidden_python_tabs(self) -> None:
        raw = common.render_r_code_block("code-001", "x <- 1") + '<code class="language-python">x = 1</code>'

        self.assertEqual(len(checker.r_code_blocks(raw)), 1)
        self.assertEqual(checker.count_forbidden_python_code_blocks(raw), 1)


if __name__ == "__main__":
    unittest.main()
