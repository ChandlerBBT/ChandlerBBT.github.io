import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import financial_engineering_common as fec  # noqa: E402
import check_financial_engineering as checker  # noqa: E402
import phase0_financial_engineering as phase0  # noqa: E402
import translate_financial_engineering as translator  # noqa: E402


class FinancialEngineeringCommonTests(unittest.TestCase):
    def test_slugify_title_handles_numbered_chapters_and_appendix(self) -> None:
        self.assertEqual(fec.slugify_title("2 Returns"), "chapter-2")
        self.assertEqual(fec.slugify_title("21 Nonparametric Regression and Splines"), "chapter-21")
        self.assertEqual(fec.slugify_title("A Facts from Probability, Statistics, and Algebra"), "appendix-a")

    def test_build_units_skips_contents_without_absorbing_contents_pages(self) -> None:
        outline = [
            {"id": "outline-001", "parent_id": None, "level": 0, "title_en": "Preface", "pdf_page": 8, "slug": "preface", "kind": "front_matter"},
            {"id": "outline-002", "parent_id": None, "level": 0, "title_en": "Contents", "pdf_page": 12, "slug": "contents", "kind": "contents"},
            {"id": "outline-003", "parent_id": None, "level": 0, "title_en": "Notation", "pdf_page": 26, "slug": "notation", "kind": "front_matter"},
            {"id": "outline-004", "parent_id": None, "level": 0, "title_en": "1 Introduction", "pdf_page": 28, "slug": "chapter-1", "kind": "chapter"},
            {"id": "outline-005", "parent_id": "outline-004", "level": 1, "title_en": "1.1 Bibliographic Notes", "pdf_page": 31, "slug": "section-1-1", "kind": "section"},
            {"id": "outline-006", "parent_id": None, "level": 0, "title_en": "2 Returns", "pdf_page": 32, "slug": "chapter-2", "kind": "chapter"},
        ]

        units = fec.build_units(outline, page_count=40, slug="statistics-data-analysis-financial-engineering-cn")

        self.assertEqual([unit["slug"] for unit in units], ["preface", "notation", "chapter-1", "chapter-2"])
        self.assertEqual((units[0]["pdf_page_start"], units[0]["pdf_page_end"]), (8, 11))
        self.assertEqual((units[1]["pdf_page_start"], units[1]["pdf_page_end"]), (26, 27))
        self.assertEqual((units[2]["pdf_page_start"], units[2]["pdf_page_end"]), (28, 31))
        self.assertEqual(units[2]["sections"][0]["slug"], "section-1-1")

    def test_render_code_pair_escapes_code_and_sets_tabs(self) -> None:
        html = fec.render_code_pair(
            "code-001",
            "x <- c(1, 2)\nplot(x)",
            "x = [1, 2]\nprint(x < 3)",
        )

        self.assertIn('class="code-tabs"', html)
        self.assertIn('class="language-r"', html)
        self.assertIn('class="language-python"', html)
        self.assertIn("x &lt;- c(1, 2)", html)
        self.assertIn("x = [1, 2]", html)
        self.assertIn("x &lt; 3", html)

    def test_render_code_pair_trims_outer_blank_lines(self) -> None:
        html = fec.render_code_pair(
            "code-001",
            "\n\nx <- c(1, 2)\n\n",
            "\n\nx = [1, 2]\n\n",
        )

        self.assertIn('<code class="language-r">x &lt;- c(1, 2)</code>', html)
        self.assertIn('<code class="language-python">x = [1, 2]</code>', html)
        self.assertNotIn('language-r">\n\n', html)
        self.assertNotIn('language-python">\n\n', html)

    def test_replace_code_pair_placeholders_uses_structured_code(self) -> None:
        html = fec.replace_code_pair_placeholders(
            "<p>前文</p>[[CODE_PAIR:code-001]]<p>后文</p>",
            [{"id": "code-001", "r_code": "mean(x)", "python_code": "x.mean()"}],
        )

        self.assertIn("<p>前文</p>", html)
        self.assertIn("mean(x)", html)
        self.assertIn("x.mean()", html)
        self.assertNotIn("[[CODE_PAIR", html)


class FinancialEngineeringCheckerTests(unittest.TestCase):
    def test_python_tabs_flag_r_residue(self) -> None:
        raw = fec.render_code_pair(
            "code-001",
            "library(boot)\nboot(data, stat)",
            "library(boot)\nboot(data, stat)",
        )

        residues = checker.python_tab_r_residue_blocks(raw)

        self.assertEqual(len(residues), 1)
        self.assertIn("library(", residues[0])

    def test_python_tabs_accept_python_code(self) -> None:
        raw = fec.render_code_pair(
            "code-001",
            "x <- c(1, 2)\nmean(x)",
            "import numpy as np\nx = np.array([1, 2])\nnp.mean(x)",
        )

        self.assertEqual(checker.python_tab_r_residue_blocks(raw), [])

    def test_python_tabs_ignore_r_patterns_in_comments(self) -> None:
        raw = fec.render_code_pair(
            "code-001",
            "library(Ecdat)\ndata(SP500)",
            "import pandas as pd\n# library(Ecdat) is not needed.\n# Load data (requires local CSV)\ndf = pd.DataFrame()",
        )

        self.assertEqual(checker.python_tab_r_residue_blocks(raw), [])

    def test_nested_code_tabs_are_reported(self) -> None:
        raw = '<pre><code class="language-r"><div class="code-tabs"><div>x</div></div></code></pre>'

        self.assertEqual(checker.nested_code_tab_wrappers(raw), ["pre-code-code-tabs"])

    def test_running_header_artifacts_are_reported(self) -> None:
        raw = '<section><h2>4 探索性数据分析</h2><h2 id="section-4-6">4.6 数据变换</h2></section>'

        self.assertEqual(checker.running_header_artifacts(raw), ["4 探索性数据分析"])


class FinancialEngineeringTranslatorPostprocessTests(unittest.TestCase):
    def test_strip_source_boilerplate_removes_springer_footer(self) -> None:
        source = "\n".join(
            [
                "Substantive paragraph.",
                "© Springer Science+Business Media New York 2015",
                "D. Ruppert, D.S. Matteson, Statistics and Data Analysis for Financial",
                "Engineering, Springer Texts in Statistics,",
                "DOI 10.1007/978-1-4939-2614-54",
                "45",
            ]
        )

        cleaned = translator.strip_source_boilerplate(source)

        self.assertIn("Substantive paragraph.", cleaned)
        self.assertNotIn("Springer", cleaned)
        self.assertNotIn("DOI", cleaned)
        self.assertNotIn("45", cleaned)

    def test_strip_source_boilerplate_removes_running_headers(self) -> None:
        source = "\n".join(
            [
                "Substantive paragraph.",
                "58 4 Exploratory Data Analysis",
                "More content.",
                "24 3 Fixed Income Securities",
                "Final content.",
            ]
        )

        cleaned = translator.strip_source_boilerplate(source)

        self.assertIn("Substantive paragraph.", cleaned)
        self.assertIn("More content.", cleaned)
        self.assertIn("Final content.", cleaned)
        self.assertNotIn("58 4 Exploratory Data Analysis", cleaned)
        self.assertNotIn("24 3 Fixed Income Securities", cleaned)

    def test_strip_running_header_artifacts_removes_translated_page_headers(self) -> None:
        raw = (
            '<section class="book-page" data-pdf-page="92">'
            '<h1>66 第4章 探索性数据分析</h1>'
            '<p>64 第4章 探索性数据分析</p>'
            '<h2>4 探索性数据分析</h2>'
            '<h2 id="section-4-6">4.6 数据变换</h2>'
            '</section>'
        )

        html = translator.strip_running_header_artifacts(raw)

        self.assertNotIn("66 第4章", html)
        self.assertNotIn("64 第4章", html)
        self.assertNotIn("4 探索性数据分析", html)
        self.assertIn("4.6 数据变换", html)

    def test_namespace_page_footnotes_rewrites_refs_and_backlinks(self) -> None:
        raw = '<sup><a href="#fn1" id="fnref1">1</a></sup><ol><li id="fn1"><a href="#fnref1">↩</a></li></ol>'

        html = translator.namespace_page_footnotes(raw, 38)

        self.assertIn('href="#fn-p038-1"', html)
        self.assertIn('id="fnref-p038-1"', html)
        self.assertIn('id="fn-p038-1"', html)
        self.assertIn('href="#fnref-p038-1"', html)

    def test_loads_model_json_repairs_latex_backslashes(self) -> None:
        data = translator.loads_model_json('{"html": "公式 \\(x_t\\) 保持不变"}')

        self.assertEqual(data["html"], "公式 \\(x_t\\) 保持不变")

    def test_loads_model_json_repairs_non_json_unicode_escape(self) -> None:
        data = translator.loads_model_json('{"html": "保留 \\underbrace{x}_{t}"}')

        self.assertEqual(data["html"], "保留 \\underbrace{x}_{t}")

    def test_unwrap_block_placeholders_removes_pre_code_wrapper(self) -> None:
        raw = '<pre><code class="language-python">[[CODE_PAIR:code-1]]</code></pre>'

        self.assertEqual(translator.unwrap_block_placeholders(raw), "[[CODE_PAIR:code-1]]")

    def test_unwrap_embedded_code_tabs_removes_nested_pre_code_wrapper(self) -> None:
        raw = (
            '<pre><code class="language-r"><div class="code-tabs" data-code-tabs id="code-1">'
            '<div class="code-tab-list"><button>R</button></div>'
            '<div class="code-tab-panel"><pre><code class="language-r">x <- 1</code></pre></div>'
            '</div></code></pre>'
        )

        html = translator.unwrap_embedded_code_tabs(raw)

        self.assertTrue(html.startswith('<div class="code-tabs"'))
        self.assertNotIn('<pre><code class="language-r"><div', html)

    def test_unwrap_embedded_code_tabs_preserves_trailing_output(self) -> None:
        raw = (
            '<pre><code class="r"><div class="code-tabs" data-code-tabs id="code-1">'
            '<div class="code-tab-list"><button>R</button></div>'
            '<div class="code-tab-panel"><pre><code class="language-r">print(x)</code></pre></div>'
            '</div>\n> print(x)\n[1] 42\n</code></pre>'
        )

        html = translator.unwrap_embedded_code_tabs(raw)

        self.assertIn('<div class="code-tabs"', html)
        self.assertIn('<code class="language-text">&gt; print(x)\n[1] 42</code>', html)
        self.assertNotIn('<pre><code class="r"><div', html)

    def test_render_sidebar_translates_section_links(self) -> None:
        units = [
            {
                "slug": "chapter-4",
                "title_en": "4 Exploratory Data Analysis",
                "sections": [
                    {"slug": "section-4-1", "title_en": "4.1 Introduction"},
                    {"slug": "section-4-2", "title_en": "4.2 Histograms and Kernel Density Estimation"},
                    {"slug": "references-4", "title_en": "References"},
                ],
            }
        ]
        title_map = {
            "chapter-4": "第4章 探索性数据分析",
            "section-4-1": "4.1 引言",
            "section-4-2": "4.2 直方图与核密度估计",
            "references-4": "参考文献",
        }

        html = translator.render_sidebar(units, title_map, "chapter-4")

        self.assertIn("4.1 引言", html)
        self.assertIn("4.2 直方图与核密度估计", html)
        self.assertIn("参考文献", html)
        self.assertNotIn("Introduction", html)
        self.assertNotIn("Histograms and Kernel", html)

    def test_title_for_section_uses_chinese_fallback_for_english_headings(self) -> None:
        self.assertEqual(
            translator.title_for_section(
                {"slug": "section-9-3", "title_en": "9.3 Multiple Linear Regression"},
                {"section-9-3": "9.3 Multiple Linear Regression"},
            ),
            "9.3 多元线性回归",
        )
        self.assertEqual(
            translator.title_for_section(
                {"slug": "section-a-2", "title_en": "A.2 Probability Distributions"},
                {},
            ),
            "A.2 概率分布",
        )
        self.assertEqual(
            translator.title_for_section(
                {"slug": "section-6-2", "title_en": "6.2 Bootstrap Estimates of Bias, Standard Deviation, and MSE"},
                {"section-6-2": "6.2 Bootstrap 估计偏差、标准差和MSE"},
            ),
            "6.2 自助法估计偏差、标准差和MSE",
        )

    def test_sanitize_python_code_html_rewrites_reserved_lambda_variable(self) -> None:
        raw = '<pre><code class="language-python">x = np.exp(-lambda * returns)</code></pre>'

        html = translator.sanitize_python_code_html(raw)

        self.assertIn("lambda_ * returns", html)


class FinancialEngineeringFigureCropTests(unittest.TestCase):
    def test_crop_box_prefers_graphics_near_caption_and_excludes_caption(self) -> None:
        class FakePage:
            width = 500
            height = 700
            lines = [
                {"top": 150, "bottom": 152, "x0": 100, "x1": 300, "width": 200, "height": 2},
                {"top": 320, "bottom": 321, "x0": 120, "x1": 420, "width": 300, "height": 1},
                {"top": 470, "bottom": 471, "x0": 120, "x1": 420, "width": 300, "height": 1},
                {"top": 320, "bottom": 470, "x0": 120, "x1": 121, "width": 1, "height": 150},
                {"top": 320, "bottom": 470, "x0": 420, "x1": 421, "width": 1, "height": 150},
            ]
            curves: list[dict[str, float]] = []
            rects: list[dict[str, float]] = []

        box = phase0.crop_box_for_caption(FakePage(), {"top": 520, "bottom": 560}, previous_bottom=0)

        self.assertIsNotNone(box)
        assert box is not None
        left, top, right, bottom = box
        self.assertLessEqual(top, 300)
        self.assertGreater(top, 200)
        self.assertGreaterEqual(left, 60)
        self.assertLessEqual(right, 460)
        self.assertLess(bottom, 520)


if __name__ == "__main__":
    unittest.main()
