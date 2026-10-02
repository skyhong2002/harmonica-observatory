import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("build_social_sources", SCRIPTS / "build_social_sources.py")
assert SPEC and SPEC.loader
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)
import build_public_data


class BuildSocialSourcesWebpageTests(unittest.TestCase):
    def test_every_current_public_entry_has_update_source(self):
        entries = build_public_data.build_entries()

        self.assertGreaterEqual(len(entries), 318)
        self.assertEqual(
            [entry["name"] for entry in entries if not entry.get("monitorSources")],
            [],
        )

    def test_entry_without_social_account_gets_scheduled_webpage_watcher(self):
        source = builder.parse_webpage_source(
            {
                "public_id": "249",
                "name": "上海豫園口琴樂團",
                "website_url": "https://www.harmonica.org.cn/news-show.asp?nlt=103&none=17",
            }
        )

        self.assertEqual(source["id"], "web_249")
        self.assertEqual(source["type"], "webpage_watch")
        self.assertEqual(source["platform"], "website")
        self.assertEqual(source["interval_hours"], 12)
        self.assertTrue(source["include_without_keywords"])

    def test_shared_program_page_keeps_entry_specific_watcher_keys(self):
        first = builder.parse_webpage_source(
            {"public_id": "265", "name": "林筱茹", "website_url": "https://example.com/program"}
        )
        second = builder.parse_webpage_source(
            {"public_id": "266", "name": "蔡景玫", "website_url": "https://example.com/program"}
        )

        self.assertNotEqual(builder.source_key(first), builder.source_key(second))

    def test_webpage_watcher_preserves_identity_bearing_query(self):
        source = builder.parse_webpage_source(
            {
                "public_id": "112",
                "name": "Kim Changsik",
                "website_url": "https://weissenbergwind.com/artists_show.php?item=4&id=15#profile",
            }
        )

        self.assertEqual(
            source["url"],
            "https://weissenbergwind.com/artists_show.php?item=4&id=15",
        )

    def test_webpage_watcher_preserves_www_hostname(self):
        source = builder.parse_webpage_source(
            {"public_id": "210", "name": "SPCC", "website_url": "https://www.spcc.edu.hk/news"}
        )

        self.assertEqual(source["url"], "https://www.spcc.edu.hk/news")

    def test_registry_update_url_override_replaces_unreachable_profile_url(self):
        source = builder.parse_webpage_source(
            {
                "public_id": "216",
                "name": "武漢理工大學學生星一口琴協會",
                "website_url": "https://youth.whut.edu.cn/stfc/legacy.shtml",
            }
        )

        self.assertEqual(source["url"], "http://youth.whut.edu.cn/")

    def test_program_crawl_config_builds_lineup_crawler(self):
        row = {"public_id": "363", "name": "臺中爵士音樂節", "website_url": "https://www.taichungjazzfestival.tw/"}
        source = builder.parse_program_crawl_source(row)

        self.assertEqual(source["id"], "web_363")
        self.assertEqual(source["type"], "webpage_watch")
        self.assertTrue(source["url"].endswith("/team-tour/team-tour.html"))
        self.assertEqual(len(source["index_urls"]), 2)
        self.assertIn("detail", source["follow_links"])
        self.assertIsNone(builder.parse_program_crawl_source({**row, "public_id": "1"}))

    def test_invalid_webpage_url_is_not_accepted(self):
        self.assertIsNone(
            builder.parse_webpage_source(
                {"public_id": "1", "name": "Unsafe", "website_url": "file:///tmp/private"}
            )
        )

    def test_instagram_story_source_uses_apify(self):
        source = builder.parse_instagram_story_source(
            {"public_id": "54", "name": "CY Leo", "ig_url": "https://www.instagram.com/cy_leo/"}
        )

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source["type"], "rsshub_instagram_story")
        self.assertEqual(source["provider"], "apify_stories")
        self.assertEqual(source["story_provider"], "apify_stories")
        self.assertNotIn("route", source)
        self.assertNotIn("rsshub_base", source)

    def test_instagram_profile_source_uses_public_collector(self):
        source = builder.parse_instagram_source(
            {"public_id": "54", "name": "CY Leo", "ig_url": "https://www.instagram.com/cy_leo/"}
        )

        self.assertIsNotNone(source)
        assert source is not None
        self.assertEqual(source["type"], "rsshub_instagram_profile")
        self.assertEqual(source["provider"], "instagram_public")
        self.assertNotIn("route", source)
        self.assertNotIn("rsshub_base", source)

    def test_manual_instagram_profile_is_migrated_from_cookie_rsshub(self):
        sources = builder.normalize_instagram_providers(
            [
                {
                    "id": "ig_example",
                    "platform": "instagram",
                    "type": "rsshub_instagram_profile",
                    "provider": "cookie",
                    "rsshub_base": "https://rss.observe.tw",
                    "username": "example",
                }
            ]
        )

        self.assertEqual(sources[0]["provider"], "instagram_public")
        self.assertNotIn("rsshub_base", sources[0])


if __name__ == "__main__":
    unittest.main()
