import datetime as dt
import hashlib
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import generate_rss_feeds  # noqa: E402


def digest_of(url):
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]


def http_error(url, code):
    return urllib.error.HTTPError(url, code, "error", {}, io.BytesIO(b""))


class FakeImageResponse:
    headers = {"content-type": "image/png"}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return b"png-bytes"


class RemoteImageCacheTests(unittest.TestCase):
    def setUp(self):
        generate_rss_feeds._IMAGE_DIR_INDEX.clear()
        generate_rss_feeds._IMAGE_FAILURES.clear()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.image_dir = root / "feed-images"
        self.image_dir.mkdir()
        self.failures = root / "state" / "remote_image_failures.json"
        self.addCleanup(generate_rss_feeds._IMAGE_DIR_INDEX.clear)
        self.addCleanup(generate_rss_feeds._IMAGE_FAILURES.clear)

    def cache(self, url):
        return generate_rss_feeds.cache_remote_image(
            url, self.image_dir, "/assets/feed-images", failure_cache=self.failures
        )

    def forget_memory(self):
        # A new pipeline run starts with nothing in memory.
        generate_rss_feeds._IMAGE_DIR_INDEX.clear()
        generate_rss_feeds._IMAGE_FAILURES.clear()

    def test_signed_url_expiry_reads_the_hex_oe_parameter(self):
        now = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)
        past = format(int(now.timestamp()) - 60, "x")
        future = format(int(now.timestamp()) + 3600, "x")
        self.assertTrue(generate_rss_feeds.signed_url_expired(f"https://cdn.example/a.jpg?oh=1&oe={past}", now))
        self.assertFalse(generate_rss_feeds.signed_url_expired(f"https://cdn.example/a.jpg?oe={future}", now))
        self.assertFalse(generate_rss_feeds.signed_url_expired("https://cdn.example/a.jpg", now))
        self.assertFalse(generate_rss_feeds.signed_url_expired("https://cdn.example/a.jpg?oe=zz", now))

    def test_expired_signed_url_is_never_requested_again(self):
        url = "https://scontent.cdninstagram.com/v/a.jpg?oe=5F000000"
        with mock.patch("urllib.request.urlopen", side_effect=http_error(url, 403)) as urlopen:
            self.assertEqual(self.cache(url), "")
        self.assertEqual(urlopen.call_count, 1)
        stored = json.loads(self.failures.read_text(encoding="utf-8"))["failures"][digest_of(url)]
        self.assertEqual(stored["status"], 403)
        self.assertTrue(stored["permanent"])

        self.forget_memory()
        far_future = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=365)
        with (
            mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")),
            mock.patch.object(generate_rss_feeds.dt, "datetime", wraps=dt.datetime) as fake_datetime,
        ):
            fake_datetime.now.return_value = far_future
            self.assertEqual(self.cache(url), "")

    def test_other_client_errors_are_retried_after_a_week(self):
        url = "https://example.org/missing.png"
        with mock.patch("urllib.request.urlopen", side_effect=http_error(url, 404)):
            self.assertEqual(self.cache(url), "")
        stored = json.loads(self.failures.read_text(encoding="utf-8"))["failures"][digest_of(url)]
        self.assertFalse(stored["permanent"])

        self.forget_memory()
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.cache(url), "")

        failed_at = dt.datetime.fromisoformat(stored["failed_at"])
        with (
            mock.patch("urllib.request.urlopen", return_value=FakeImageResponse()) as urlopen,
            mock.patch.object(generate_rss_feeds, "convert_image_bytes_to_webp", return_value=False),
            mock.patch.object(generate_rss_feeds.dt, "datetime", wraps=dt.datetime) as fake_datetime,
        ):
            fake_datetime.now.return_value = failed_at + dt.timedelta(days=7, minutes=1)
            self.assertEqual(self.cache(url), f"/assets/feed-images/{digest_of(url)}.png")
        self.assertEqual(urlopen.call_count, 1)
        # A success clears the failure.
        self.assertEqual(json.loads(self.failures.read_text(encoding="utf-8"))["failures"], {})

    def test_transient_failures_are_not_remembered(self):
        url = "https://example.org/flaky.png"
        for error in (http_error(url, 503), http_error(url, 429), urllib.error.URLError("down"), TimeoutError()):
            with mock.patch("urllib.request.urlopen", side_effect=error):
                self.assertEqual(self.cache(url), "")
        self.assertFalse(self.failures.exists())

    def test_without_a_failure_cache_every_miss_is_fetched(self):
        url = "https://example.org/missing.png"
        with mock.patch("urllib.request.urlopen", side_effect=http_error(url, 404)) as urlopen:
            generate_rss_feeds.cache_remote_image(url, self.image_dir, "/assets/feed-images")
            generate_rss_feeds.cache_remote_image(url, self.image_dir, "/assets/feed-images")
        self.assertEqual(urlopen.call_count, 2)
        self.assertFalse(self.failures.exists())

    def test_directory_is_listed_once_per_run(self):
        legacy = "https://example.org/legacy.jpg"
        (self.image_dir / f"{digest_of(legacy)}.jpg").write_bytes(b"jpeg")
        with (
            mock.patch.object(Path, "glob", side_effect=AssertionError("per-image glob")),
            mock.patch.object(Path, "iterdir", autospec=True, side_effect=Path.iterdir) as iterdir,
            mock.patch.object(generate_rss_feeds, "OFFLINE", True),
            mock.patch.object(generate_rss_feeds, "convert_image_bytes_to_webp", return_value=False),
        ):
            for index in range(5):
                self.assertEqual(self.cache(f"https://example.org/{index}.jpg"), "")
            self.assertEqual(self.cache(legacy), f"/assets/feed-images/{digest_of(legacy)}.jpg")
        self.assertEqual(iterdir.call_count, 1)

    def test_newly_cached_images_are_found_without_relisting(self):
        url = "https://example.org/new.png"
        with (
            mock.patch("urllib.request.urlopen", return_value=FakeImageResponse()),
            mock.patch.object(generate_rss_feeds, "convert_image_bytes_to_webp", return_value=False),
        ):
            first = self.cache(url)
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")):
            self.assertEqual(self.cache(url), first)


if __name__ == "__main__":
    unittest.main()
