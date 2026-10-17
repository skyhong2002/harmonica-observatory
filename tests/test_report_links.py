import json
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import build_submit_page  # noqa: E402
import configure_submission_form  # noqa: E402
import generate_rss_feeds  # noqa: E402
import generate_seo_pages  # noqa: E402
import report_links  # noqa: E402
import site_chrome  # noqa: E402


class ReportLinkTests(unittest.TestCase):
    def test_shared_header_is_used_by_submit_page(self):
        rendered = build_submit_page.render_submit_page()
        self.assertEqual(rendered.count('<header class="site-header">'), 1)
        self.assertIn(site_chrome.render_header(), rendered)
        self.assertNotIn("aria-current", rendered)
        header = rendered.split('<header class="site-header">', 1)[1].split("</header>", 1)[0]
        for href in ("/post/", "/source/", "/scores/", "/status/", "/submit/"):
            self.assertEqual(header.count(f'href="{href}"'), 1)

    def test_asset_version_replacement_does_not_change_external_query_strings(self):
        document = (
            '<link rel="stylesheet" href="/assets/styles.css?v=old">'
            '<a href="https://www.youtube.com/watch?v=video-id">開啟來源</a>'
        )
        updated = site_chrome.replace_asset_versions(document)
        self.assertIn(f"/assets/styles.css?v={site_chrome.ASSET_VERSION}", updated)
        self.assertIn("https://www.youtube.com/watch?v=video-id", updated)

    def test_stale_header_is_replaced_with_canonical_navigation(self):
        document = """<body>
  <header class="site-header">
    <nav class="site-nav">
      <a href="/post/">公開貼文</a>
      <a href="/status/">狀態</a>
    </nav>
  </header>
</body>"""
        updated = site_chrome.normalize_document(document)
        header = updated.split('<header class="site-header">', 1)[1].split("</header>", 1)[0]
        self.assertIn("/assets/logo.svg?v=" + site_chrome.ASSET_VERSION, header)
        self.assertIn('href="/submit/">資料回報</a>', header)
        self.assertNotIn('href="/post/">公開貼文</a>\n      <a href="/status/">狀態</a>', header)

    def test_report_url_prefills_bounded_context(self):
        url = report_links.report_url(
            "correct",
            name="測試來源",
            source="https://example.com/post",
            page="/source/7-test/",
            desired="修正分類",
        )
        parsed = urllib.parse.urlsplit(url)
        params = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(parsed.path, "/submit/")
        self.assertEqual(params["kind"], ["correct"])
        self.assertEqual(params["name"], ["測試來源"])
        self.assertEqual(params["page"], ["https://harmonica.observe.tw/source/7-test/"])

    def test_unknown_kind_falls_back_to_correction_and_truncates(self):
        url = report_links.report_url("unknown", name="x" * 500)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(params["kind"], ["correct"])
        self.assertEqual(len(params["name"][0]), 240)

    def test_submit_page_embeds_public_form_configuration(self):
        rendered = build_submit_page.render_submit_page()
        self.assertNotIn("__GOOGLE_FORM_", rendered)
        self.assertIn("data-report-form-frame", rendered)
        self.assertIn("submission-form-public-config", rendered)
        config = json.loads((PROJECT_ROOT / "data/submission-form-public.json").read_text())
        for entry_id in config["entryIds"].values():
            self.assertIn(entry_id, rendered)

    def test_public_entry_ids_map_form_questions_and_require_every_public_field(self):
        items = []
        for index, title in enumerate(configure_submission_form.PUBLIC_ENTRY_KEYS, start=1):
            items.append(
                {
                    "title": title,
                    "questionItem": {"question": {"questionId": str(index)}},
                }
            )

        entry_ids = configure_submission_form.public_entry_ids(items)
        self.assertEqual(set(entry_ids), set(configure_submission_form.PUBLIC_ENTRY_KEYS.values()))
        self.assertEqual(entry_ids["kind"], "1")

        with self.assertRaisesRegex(ValueError, "missing public entry IDs"):
            configure_submission_form.public_entry_ids(items[:-1])

    def test_generated_feed_card_prefills_item_context(self):
        rendered = generate_rss_feeds.render_home_feed_item(
            {
                "source": "測試口琴頻道",
                "display_title": "公開演出",
                "title": "公開演出",
                "title_kind": "headline",
                "link": "https://example.com/watch?v=123",
                "platform": "youtube",
                "posted_at": "2026-07-30T12:00:00+08:00",
                "matched_keywords": ["演出", "半音階"],
            }
        )
        self.assertIn('class="context-report-link"', rendered)
        self.assertIn("kind=correct", rendered)
        self.assertIn("%E6%B8%AC%E8%A9%A6%E5%8F%A3%E7%90%B4%E9%A0%BB%E9%81%93", rendered)
        self.assertIn("https%3A%2F%2Fexample.com%2Fwatch%3Fv%3D123", rendered)

    def test_generated_source_index_card_omits_redundant_report_link(self):
        rendered = generate_seo_pages.render_static_source_index_card(
            {
                "id": "watchlist-777",
                "publicId": "777",
                "name": "測試口琴社",
                "nameEn": "Test Harmonica Club",
                "category": "學校社團",
                "country": "臺灣",
                "region": "新竹",
                "links": [{"label": "Instagram", "url": "https://instagram.com/test"}],
            }
        )
        self.assertNotIn('class="context-report-link"', rendered)
        self.assertNotIn(">回報</a>", rendered)
        self.assertIn('href="/source/777-test-harmonica-club/"', rendered)
        self.assertIn('<span class="entry-id" aria-label="來源 ID 777">ID 777</span><h3>', rendered)

    def test_source_index_uses_content_version_for_directory_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'data').mkdir()
            (root / 'data/site-data.js').write_text('window.SITE_DATA = {"entries": []};')
            with patch.object(generate_seo_pages, 'SITE_ROOT', root):
                rendered = generate_seo_pages.generate_source_index_base_page()
        self.assertRegex(rendered, r'/data/site-data\.js\?data=[0-9a-f]{12}')
        self.assertNotIn(
            f'/data/site-data.js?v={generate_seo_pages.ASSET_VERSION}', rendered
        )

    def test_generated_pages_replace_obsolete_github_form_wording(self):
        original = """<nav>\n        <a href=\"/status/\">狀態</a>\n</nav>\n<p>請先看回報頁整理需要準備的公開來源，再送出 GitHub 表單。</p>\n<a href=\"https://github.com/skyhong2002/Harmonica-in-Taiwan/issues\" target=\"_blank\" rel=\"noreferrer\">查看處理中的回報</a>\n<footer><a href=\"/submit/\">資料回報</a></footer>"""
        rendered = generate_rss_feeds.modernize_submission_links(original)
        self.assertNotIn("GitHub 表單", rendered)
        self.assertNotIn("查看處理中的回報", rendered)
        self.assertEqual(rendered.count('<a href="/submit/">資料回報</a>'), 2)
        self.assertIn('<a href="/submit/?kind=add-source">新增來源或頻道</a>', rendered)


if __name__ == "__main__":
    unittest.main()
