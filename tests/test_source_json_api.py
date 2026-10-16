import importlib.util
import json
import os
import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("generate_seo_pages", SCRIPTS / "generate_seo_pages.py")
assert SPEC and SPEC.loader
seo = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(seo)


class SourceJsonApiTests(unittest.TestCase):
    def setUp(self):
        self.entry = {
            "id": "watchlist-198",
            "name": "陽明交大竹韻口琴社",
            "nameEn": "Bamboo Melody Harmonica Club",
        }

    def update(self, **overrides):
        row = {
            "directory_entry_id": "watchlist-198",
            "source_id": "fb_nycubmhc",
            "headline": "竹韻復社公告",
            "text": "竹韻口琴社恢復活動，歡迎追蹤公開消息。",
            "link": "https://www.facebook.com/nycubmhc/posts/123",
            "platform": "facebook",
            "posted_at": "2026-06-25T17:00:11Z",
        }
        row.update(overrides)
        return row

    def test_source_198_selects_registered_facebook_and_instagram_only(self):
        updates = [
            self.update(),
            self.update(
                source_id="ig_nycu_harmonica",
                headline="竹韻招生公告",
                text="竹韻 Instagram 招生消息。",
                link="https://www.instagram.com/p/ABC123/",
                platform="instagram",
                posted_at="2026-06-26T10:00:00Z",
            ),
            self.update(
                directory_entry_id="watchlist-199",
                headline="其他團體公告",
                link="https://www.facebook.com/other/posts/999",
            ),
        ]

        selected = seo.source_updates_for_entry(self.entry, updates)
        payload = seo.source_api_payload(self.entry, selected, "2026-06-27T00:00:00Z")

        self.assertEqual({item["platform"] for item in payload["items"]}, {"Facebook", "Instagram"})
        self.assertTrue(all(item["sourceName"] == self.entry["name"] for item in payload["items"]))
        self.assertNotIn("其他團體", json.dumps(payload, ensure_ascii=False))

    def test_duplicate_canonical_url_and_identical_content_are_removed(self):
        original = self.update(link="https://example.com/post/1?utm_source=test")
        same_url = self.update(link="https://example.com/post/1?fbclid=tracking", platform="instagram")
        same_content = self.update(link="https://example.com/post/2", platform="youtube")

        selected = seo.source_updates_for_entry(self.entry, [original, same_url, same_content])
        items = seo.source_api_items(self.entry, selected)

        self.assertEqual(len(selected), 1)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["url"], "https://example.com/post/1")

    def test_unsafe_fields_are_skipped_or_sanitized(self):
        unsafe_rows = [
            self.update(link="http://example.com/post"),
            self.update(link="https://127.0.0.1/private"),
            self.update(link="https://example.com/no-title", headline="", title="", display_title=""),
            self.update(link="https://example.com/no-date", posted_at="not-a-date"),
            self.update(link="https://example.com/private", public=False),
        ]
        safe = self.update(
            headline="<b>公開公告</b><script>alert(1)</script>",
            text=(
                "<p>公開內容</p>\n"
                "付款帳號 123-456\n"
                "email me@example.com\n"
                "電話 0912-345-678\n"
                "/Users/private/raw.html\n"
                "https://provider.example/raw"
            ),
            link="https://example.com/safe?utm_medium=social#fragment",
        )

        items = seo.source_api_items(self.entry, [*unsafe_rows, safe])

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["title"], "公開公告")
        self.assertEqual(items[0]["excerpt"], "公開內容")
        self.assertEqual(items[0]["url"], "https://example.com/safe")
        self.assertLessEqual(len(items[0]["excerpt"]), seo.SOURCE_API_EXCERPT_LIMIT)
        serialized = json.dumps(items, ensure_ascii=False)
        for forbidden in ("<script", "付款帳號", "provider.example", "/Users/", "0912"):
            self.assertNotIn(forbidden, serialized)

    def test_only_locally_cached_images_are_published(self):
        # 內文必須各自不同,否則會先被既有的重複內容過濾掉。
        remote = self.update(
            link="https://example.com/remote-image",
            text="第一則公開貼文。",
            image_url="https://scontent.cdninstagram.com/v/expiring.jpg",
        )
        missing_local = self.update(
            link="https://example.com/missing-image",
            text="第二則公開貼文。",
            image_url="/assets/feed-images/not-on-disk.webp",
        )
        cached = self.update(
            link="https://example.com/cached-image",
            text="第三則公開貼文。",
            image_url="/assets/feed-images/ok.webp",
        )

        with mock.patch.object(seo.feed_render, "local_image_asset_valid", lambda url: url.endswith("ok.webp")), \
             mock.patch.object(seo.feed_render, "image_dimensions", lambda url: (1080, 1350)):
            items = seo.source_api_items(self.entry, seo.source_updates_for_entry(self.entry, [remote, missing_local, cached]))

        by_url = {item["url"]: item for item in items}
        self.assertNotIn("image", by_url["https://example.com/remote-image"])
        self.assertNotIn("image", by_url["https://example.com/missing-image"])
        self.assertEqual(
            by_url["https://example.com/cached-image"]["image"],
            {"url": "https://harmonica.observe.tw/assets/feed-images/ok.webp", "width": 1080, "height": 1350},
        )
        self.assertNotIn("cdninstagram", json.dumps(items, ensure_ascii=False))

    def test_empty_source_writes_valid_schema(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(seo, "SOURCE_API_DIR", Path(temp_dir)):
                path = seo.write_source_api(self.entry, [], "2026-06-27T00:00:00Z")
                payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["source"]["id"], 198)
        self.assertEqual(payload["source"]["slug"], "bamboo-melody-harmonica-club")
        self.assertEqual(payload["items"], [])

    def test_generate_twice_preserves_source_files_and_removes_only_stale_json(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            api = root / "api"
            api.mkdir()
            for name, payload in {
                "sources": {"entries": [self.entry]},
                "public-calendar-events": {"events": []},
                "scores": {"scores": []},
                "latest": {"updates": [], "generatedAt": "2026-06-27T00:00:00Z"},
            }.items():
                (api / f"{name}.json").write_text(json.dumps(payload))
            with mock.patch.multiple(seo, SITE_ROOT=root, SOURCES_JSON=api / "sources.json",
                                     EVENTS_JSON=api / "public-calendar-events.json",
                                     SCORES_JSON=api / "scores.json", SOURCE_API_DIR=api / "source",
                                     SITEMAP_XML=root / "sitemap.xml"), \
                 mock.patch.object(seo, "read_legacy_alias_source_paths", return_value=set()), \
                 contextlib.redirect_stdout(io.StringIO()):
                seo.main()
                paths = [root / "source" / seo.make_slug(self.entry) / "index.html",
                         api / "source" / "198.json",
                         root / "source" / self.entry["id"] / "index.html",
                         root / "source" / "index.html"]
                for path in paths:
                    os.utime(path, ns=(1000000000, 1000000000))
                before = [(p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in paths]
                stale = api / "source" / "obsolete.json"
                stale.write_text("{}")
                keep = api / "source" / "keep.txt"
                keep.write_text("keep")
                seo.main()
                self.assertEqual(before, [(p.read_bytes(), p.stat().st_mtime_ns, p.stat().st_ino) for p in paths])
                self.assertFalse(stale.exists())
                self.assertTrue(keep.exists())

    def test_source_page_advertises_json_endpoint(self):
        page = seo.generate_source_page(self.entry, [], [])
        self.assertIn(
            '<link rel="alternate" type="application/json" title="陽明交大竹韻口琴社公開貼文" href="/api/source/198.json">',
            page,
        )

    def test_stale_generated_source_slug_is_removed_without_touching_facets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            site_root = Path(temp_dir)
            source_root = site_root / "source"
            stale = source_root / "198-old-expanded-name"
            canonical = source_root / "198-bamboo-melody-harmonica-club"
            facet = source_root / "category" / "學校社團"
            for path in (stale, canonical, facet):
                path.mkdir(parents=True)
                (path / "index.html").write_text("generated", encoding="utf-8")

            with mock.patch.object(seo, "SITE_ROOT", site_root):
                removed = seo.remove_stale_source_page_outputs([self.entry])

            self.assertEqual(removed, [stale])
            self.assertFalse(stale.exists())
            self.assertTrue(canonical.exists())
            self.assertTrue(facet.exists())


if __name__ == "__main__":
    unittest.main()
