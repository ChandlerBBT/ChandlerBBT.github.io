import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import financial_reporting_common as frc  # noqa: E402
import check_financial_reporting as checker  # noqa: E402


class FinancialReportingCommonTests(unittest.TestCase):
    def test_slugify_title_keeps_chapter_number(self) -> None:
        self.assertEqual(
            frc.slugify_title("CHAPTER 12 Forecasting Financial Statements"),
            "chapter-12",
        )

    def test_slugify_title_handles_front_matter(self) -> None:
        self.assertEqual(frc.slugify_title("Table of Contents"), "contents")
        self.assertEqual(frc.slugify_title("Appendix A: Compound Interest"), "appendix-a")

    def test_build_units_sets_page_ranges_and_skips_contents(self) -> None:
        outline = [
            {
                "id": "outline-001",
                "parent_id": None,
                "level": 0,
                "title_en": "Table of Contents",
                "pdf_page": 3,
                "slug": "contents",
                "kind": "contents",
            },
            {
                "id": "outline-002",
                "parent_id": None,
                "level": 0,
                "title_en": "CHAPTER 1 Overview",
                "pdf_page": 15,
                "slug": "chapter-1",
                "kind": "chapter",
            },
            {
                "id": "outline-003",
                "parent_id": "outline-002",
                "level": 1,
                "title_en": "Learning Objectives",
                "pdf_page": 16,
                "slug": "learning-objectives",
                "kind": "section",
            },
            {
                "id": "outline-004",
                "parent_id": None,
                "level": 0,
                "title_en": "CHAPTER 2 Asset and Liability Valuation",
                "pdf_page": 47,
                "slug": "chapter-2",
                "kind": "chapter",
            },
        ]

        units = frc.build_units(outline, page_count=80, slug="financial-reporting-cn")

        self.assertEqual([unit["slug"] for unit in units], ["chapter-1", "chapter-2"])
        self.assertEqual((units[0]["pdf_page_start"], units[0]["pdf_page_end"]), (15, 46))
        self.assertEqual((units[1]["pdf_page_start"], units[1]["pdf_page_end"]), (47, 80))
        self.assertEqual(units[0]["sections"][0]["title_en"], "Learning Objectives")

    def test_attach_captions_assigns_same_page_in_order(self) -> None:
        images = [
            {"id": "image-001", "pdf_page": 10, "caption_id": None},
            {"id": "image-002", "pdf_page": 10, "caption_id": None},
            {"id": "image-003", "pdf_page": 11, "caption_id": None},
        ]
        captions = [
            {"id": "caption-001", "pdf_page": 10, "text_en": "Exhibit 1.1 A"},
            {"id": "caption-002", "pdf_page": 10, "text_en": "Exhibit 1.2 B"},
        ]

        frc.attach_captions(images, captions)

        self.assertEqual(images[0]["caption_id"], "caption-001")
        self.assertEqual(images[1]["caption_id"], "caption-002")
        self.assertIsNone(images[2]["caption_id"])

    def test_build_known_pdf_units_covers_chapters_appendices_and_index(self) -> None:
        units = frc.build_known_pdf_units(page_count=946, slug="financial-reporting-cn")

        self.assertEqual(units[0]["slug"], "summary-of-key-ratios")
        chapter_1 = next(unit for unit in units if unit["slug"] == "chapter-1")
        chapter_14 = next(unit for unit in units if unit["slug"] == "chapter-14")
        appendix_c = next(unit for unit in units if unit["slug"] == "appendix-c")
        index = next(unit for unit in units if unit["slug"] == "index")

        self.assertEqual((chapter_1["pdf_page_start"], chapter_1["pdf_page_end"]), (29, 94))
        self.assertEqual((chapter_14["pdf_page_start"], chapter_14["pdf_page_end"]), (791, 832))
        self.assertEqual((appendix_c["pdf_page_start"], appendix_c["pdf_page_end"]), (877, 916))
        self.assertEqual((index["pdf_page_start"], index["pdf_page_end"]), (919, 944))
        self.assertLessEqual(units[-1]["pdf_page_end"], 946)

    def test_is_omittable_pdf_page_detects_publisher_notice_only_pages(self) -> None:
        notice_text = """
        Copyright 2023 Cengage Learning. All Rights Reserved. May not be copied,
        scanned, or duplicated, in whole or in part.
        Editorial review has deemed that any suppressed content does not
        materially affect the overall learning experience.
        """
        substantive_text = """
        Chapter 1 Overview of Financial Reporting
        Financial statements summarize profitability, risk, and growth.
        Exhibit 1.1 illustrates the accounting equation.
        """

        self.assertTrue(frc.is_omittable_pdf_page(notice_text))
        self.assertFalse(frc.is_omittable_pdf_page(substantive_text))

    def test_strip_unapproved_img_tags_removes_model_invented_images(self) -> None:
        fragment = (
            '<figure><img src="/assets/img/book-slug/figure-1.png" alt="ok" /></figure>'
            '<figure><img src="placeholder.png" alt="bad" /></figure>'
            '<img src="images/exhibit-2-1.png" alt="bad too" />'
        )

        cleaned = frc.strip_unapproved_img_tags(fragment, ("/assets/img/book-slug/",))

        self.assertIn('/assets/img/book-slug/figure-1.png', cleaned)
        self.assertNotIn("placeholder.png", cleaned)
        self.assertNotIn("images/exhibit-2-1.png", cleaned)

    def test_strip_pdf_running_headers_removes_chapter_headers(self) -> None:
        fragment = '<section><p>398 CHAPTER 7 Financing Activities 市场价即股票价格。</p></section>'

        cleaned = frc.strip_pdf_running_headers(fragment)

        self.assertNotIn("CHAPTER 7 Financing Activities", cleaned)
        self.assertIn("市场价即股票价格", cleaned)

    def test_english_leak_blocks_allows_reference_citations(self) -> None:
        raw = (
            "<p>1629–1666. See Peter Easton, Gary Taylor, Pervin Shroff and Theodore Sougiannis, "
            "“Using Forecasts of Earnings to Simultaneously Estimate Growth and the Rate of Return "
            "on Equity Investment,” <em>Journal of Accounting Research</em> 40 (2002), pp. 657–676.</p>"
        )

        self.assertEqual(checker.english_leak_blocks(raw), [])

    def test_english_leak_blocks_still_flags_untranslated_exercise_text(self) -> None:
        raw = (
            "<p><strong>10.1 Relying on Accounting to Avoid Forecast Errors.</strong> "
            "The chapter states that forecasts of financial statements should rely on the additivity "
            "within financial statements and the articulation across financial statements to avoid "
            "internal inconsistencies in forecasts. Explain how the concepts of additivity and "
            "articulation apply to financial statement forecasts.</p>"
        )

        self.assertTrue(checker.english_leak_blocks(raw))

    def test_symbol_artifact_patterns_flag_repeated_question_marks(self) -> None:
        self.assertTrue(any(pattern.search("???????????") for pattern in checker.SYMBOL_ARTIFACT_PATTERNS_COMPILED))


if __name__ == "__main__":
    unittest.main()
