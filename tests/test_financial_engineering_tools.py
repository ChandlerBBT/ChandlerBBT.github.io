import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import financial_engineering_common as fec  # noqa: E402
import check_financial_engineering as checker  # noqa: E402
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

    def test_sanitize_python_code_html_rewrites_reserved_lambda_variable(self) -> None:
        raw = '<pre><code class="language-python">x = np.exp(-lambda * returns)</code></pre>'

        html = translator.sanitize_python_code_html(raw)

        self.assertIn("lambda_ * returns", html)


if __name__ == "__main__":
    unittest.main()
