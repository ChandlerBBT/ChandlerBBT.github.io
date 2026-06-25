import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import analyzing_financial_data_pdf_html as tool  # noqa: E402


class PdfHtmlTranslationTests(unittest.TestCase):
    def test_r_console_blocks_are_detected(self) -> None:
        code = '1 > library(quantmod)\n2 > getSymbols("AMZN")\n3 [1] "AMZN"'
        split_number_code = '1\n> data.amzn <- read.csv("AMZN Yahoo.csv", header = TRUE)'
        collapsed = '4 > head.tail(data) 5 date AMZN GOOG AAPL SPY 6 1 2014-12-31 1.0'
        prose = "R is a useful environment for financial data analysis."
        caption = "Fig. 1.6 Alternative chart using ggplot(). Data source: Price data reproduced with permission."

        self.assertTrue(tool.is_r_code_block(code))
        self.assertTrue(tool.is_r_code_block(split_number_code))
        self.assertTrue(tool.is_r_code_block(collapsed))
        self.assertFalse(tool.is_r_code_block(prose))
        self.assertFalse(tool.is_r_code_block(caption))

    def test_r_code_block_has_blue_background_and_copy_button(self) -> None:
        html = tool.render_r_code_block('1 > x <- c(1, 2)\n2 > mean(x)', "code-1")

        self.assertIn('class="r-code-card"', html)
        self.assertIn('class="copy-code"', html)
        self.assertIn("data-code-target=\"code-1\"", html)
        self.assertIn("x &lt;- c(1, 2)", html)

    def test_prepare_units_skips_running_headers_page_numbers_and_code(self) -> None:
        struct = {
            "pages": [
                {
                    "page": 29,
                    "blocks": [
                        {"type": "text", "bbox": [80, 50, 120, 70], "text": "14", "size": 8},
                        {"type": "text", "bbox": [460, 50, 520, 70], "text": "1 Prices", "size": 8},
                        {"type": "text", "bbox": [80, 120, 500, 160], "text": "Another useful check is summary().", "size": 10},
                        {"type": "text", "bbox": [90, 700, 310, 740], "text": "1 > dim(data.amzn)\n2 [1] 1259 6", "size": 8},
                    ],
                }
            ]
        }

        units = tool.prepare_translation_units(struct)

        self.assertEqual([u["id"] for u in units], ["p29_t0"])
        self.assertEqual(units[0]["src"], "Another useful check is summary().")

    def test_detect_figure_region_from_caption_and_drawing(self) -> None:
        struct = {
            "pages": [
                {
                    "page": 29,
                    "blocks": [
                        {"type": "text", "bbox": [90, 590, 510, 630], "text": "Fig. 1.2 AMZN stock price.", "size": 9}
                    ],
                    "drawings": [
                        {"bbox": [110, 120, 500, 560]},
                        {"bbox": [20, 20, 40, 40]},
                    ],
                }
            ]
        }

        regions = tool.detect_figure_regions(struct)

        self.assertEqual(len(regions), 1)
        self.assertEqual(regions[0]["page"], 29)
        self.assertLess(regions[0]["bbox"][1], 130)
        self.assertGreater(regions[0]["bbox"][3], 550)

    def test_translate_chunk_resilient_retries_missing_units_singly(self) -> None:
        class FakeClient:
            model = "fake"

            def chat_json(self, _system, user, temperature=0.06, retries=3):
                ids = [unit["id"] for unit in user["units"]]
                if len(ids) > 1:
                    return {"units": [{"id": ids[0], "tr": "甲"}]}
                return {"units": [{"id": ids[0], "tr": f"译文-{ids[0]}"}]}

        old_cache = tool.CACHE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            try:
                tool.CACHE_DIR = Path(tmp)
                result = tool.translate_chunk_resilient(
                    FakeClient(),
                    "guide",
                    [{"id": "a", "page": 1, "src": "A"}, {"id": "b", "page": 1, "src": "B"}],
                    1,
                    force=True,
                )
            finally:
                tool.CACHE_DIR = old_cache

        self.assertEqual(result, {"a": "译文-a", "b": "译文-b"})

    def test_translate_chunk_accepts_bare_json_array_response(self) -> None:
        class FakeClient:
            model = "fake-array"

            def chat_json(self, _system, user, temperature=0.06, retries=3):
                return [{"id": user["units"][0]["id"], "tr": "数组译文"}]

        old_cache = tool.CACHE_DIR
        with tempfile.TemporaryDirectory() as tmp:
            try:
                tool.CACHE_DIR = Path(tmp)
                result = tool.translate_chunk(
                    FakeClient(),
                    "guide",
                    [{"id": "a", "page": 1, "src": "A"}],
                    1,
                    force=True,
                )
            finally:
                tool.CACHE_DIR = old_cache

        self.assertEqual(result, {"a": "数组译文"})

    def test_translate_chunk_resilient_uses_strict_single_unit_fallback(self) -> None:
        class FakeClient:
            model = "fake-strict"

            def __init__(self):
                self.calls = 0

            def chat_json(self, _system, user, temperature=0.06, retries=3):
                self.calls += 1
                if "unit" in user:
                    return {"id": user["unit"]["id"], "tr": "严格译文"}
                return {"units": []}

        old_cache = tool.CACHE_DIR
        client = FakeClient()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                tool.CACHE_DIR = Path(tmp)
                result = tool.translate_chunk_resilient(
                    client,
                    "guide",
                    [{"id": "a", "page": 1, "src": "A"}],
                    1,
                    force=True,
                )
            finally:
                tool.CACHE_DIR = old_cache

        self.assertEqual(result, {"a": "严格译文"})
        self.assertGreaterEqual(client.calls, 2)

    def test_render_document_skips_translations_that_drift_into_code(self) -> None:
        struct = {
            "pages": [
                {
                    "page": 1,
                    "blocks": [
                        {
                            "type": "text",
                            "bbox": [80, 120, 500, 160],
                            "text": "Use the square root T rule to scale a one-day VaR.",
                            "size": 10,
                        },
                        {
                            "type": "text",
                            "bbox": [80, 180, 500, 240],
                            "text": "1\n> as.numeric(quantile(-sim.pnl$PnL, 0.99) * sqrt(10))\n2\n[1] 184704.1",
                            "size": 8,
                        },
                    ],
                }
            ]
        }

        rendered = tool.render_document_html(
            struct,
            {"p1_t0": "1\n> as.numeric(quantile(-sim.pnl$PnL, 0.99) * sqrt(10))\n2\n[1] 184704.1"},
            [],
            {},
        )

        self.assertEqual(rendered.count('class="r-code-card"'), 1)
        self.assertNotIn("<p>1 &gt; as.numeric", rendered)
        self.assertIn("[1] 184704.1", rendered)

    def test_quality_report_ignores_data_uri_text_for_todo_scan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "index.html"
            path.write_text(
                '<html><body><img src="data:image/png;base64,TODO"></body></html>',
                encoding="utf-8",
            )
            old_cache = tool.CACHE_DIR
            try:
                tool.CACHE_DIR = Path(tmp)
                report = tool.quality_report(path, [], {}, [])
            finally:
                tool.CACHE_DIR = old_cache

        self.assertEqual(report["todo_markers"], 0)
        self.assertEqual(report["status"], "ready")


if __name__ == "__main__":
    unittest.main()
