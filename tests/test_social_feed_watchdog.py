import importlib.util
import datetime as dt
import io
import socket
import subprocess
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("social_feed_watchdog", SCRIPTS / "social_feed_watchdog.py")
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(watchdog)


class FakeResponse:
    def __init__(self, body: str, headers=None, url="https://example.com/"):
        self.body = body.encode("utf-8")
        self.headers = headers or {}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, *_args):
        return self.body

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, responses):
        self.responses = iter(responses)

    def open(self, request, timeout):
        return FakeResponse(next(self.responses))


class SocialFeedWatchdogWebpageTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "web_249",
            "name": "上海豫園口琴樂團",
            "platform": "website",
            "type": "webpage_watch",
            "url": "https://example.com/news",
            "profile_url": "https://example.com/news",
            "interval_hours": 12,
            "include_without_keywords": True,
        }

    def test_fetch_webpage_fingerprints_visible_content(self):
        response = FakeResponse(
            "<html><head><title>口琴樂團公告</title><script>unstable()</script></head>"
            "<body><h1>秋季音樂會</h1><p>報名開始</p></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8", "Last-Modified": "Wed, 19 Aug 2026 10:00:00 GMT"},
            url="https://example.com/news",
        )
        with mock.patch.object(watchdog.urllib.request, "urlopen", return_value=response):
            posts = watchdog.fetch_webpage(self.source)
        self.assertEqual(posts[0]["posted_at"], "")

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["media_type"], "webpage_update")
        self.assertIn("秋季音樂會", posts[0]["text"])
        self.assertNotIn("unstable", posts[0]["text"])
        self.assertTrue(posts[0]["include_without_keywords"])

    def test_program_crawl_emits_only_detail_pages_mentioning_harmonica(self):
        source = {
            **self.source,
            "id": "web_363",
            "url": "https://fest.example/2026/tw/lineup/a.html",
            "index_urls": ["https://fest.example/2026/tw/lineup/b.html"],
            "follow_links": r"/\d{4}/tw/[a-z-]+-detail/[^/]+\.html$",
        }
        pages = {
            "https://fest.example/2026/tw/lineup/a.html":
                '<a href="../tour-detail/1.html">Trio</a><a href="../tour-detail/2.html">Quartet</a>'
                '<a href="https://other.example/2026/tw/tour-detail/9.html">elsewhere</a><a href="../news/x.html">news</a>',
            "https://fest.example/2026/tw/lineup/b.html": '<a href="../tour-detail/1.html">Trio again</a>'
                '<a href="../main-detail/3.html">Big band</a>',
            "https://fest.example/2026/tw/tour-detail/1.html":
                "<title>Fest 2026</title><p>10/2 19:10</p><p>烏克麗麗、鋼琴、貝斯與口琴</p>",
            "https://fest.example/2026/tw/tour-detail/2.html": "<title>Fest 2026</title><p>Sax quartet</p>",
        }
        requested = []

        def urlopen(request, timeout):
            requested.append(request.full_url)
            if request.full_url not in pages:
                raise urllib.error.HTTPError(request.full_url, 404, "missing", {}, None)
            return FakeResponse(pages[request.full_url], {"Content-Type": "text/html"}, request.full_url)

        with mock.patch.object(watchdog.urllib.request, "urlopen", side_effect=urlopen), \
                mock.patch.object(watchdog.time, "sleep"):
            posts = watchdog.fetch_webpage(source)

        self.assertEqual([post["url"] for post in posts], ["https://fest.example/2026/tw/tour-detail/1.html"])
        self.assertEqual(posts[0]["media_type"], "program_page")
        self.assertIn("口琴", posts[0]["text"])
        self.assertNotIn("https://other.example/2026/tw/tour-detail/9.html", requested)
        self.assertIn("https://fest.example/2026/tw/main-detail/3.html", requested)

    def test_program_crawl_keeps_harmonica_passage_of_long_pages(self):
        source = {**self.source, "url": "https://fest.example/lineup.html", "follow_links": r"/detail/"}
        detail = "<title>Fest</title><p>10/2 19:10 Plaza</p>" + "<p>" + "menu " * 600 + "</p><p>Trio with harmonica solo</p>"
        pages = {
            "https://fest.example/lineup.html": '<a href="/detail/1.html">a</a><a href="/detail/2.html">b</a>',
            "https://fest.example/detail/1.html": detail,
            "https://fest.example/detail/2.html": detail,
        }
        with mock.patch.object(watchdog.urllib.request, "urlopen",
                               side_effect=lambda request, timeout: FakeResponse(
                                   pages[request.full_url], {"Content-Type": "text/html"}, request.full_url)), \
                mock.patch.object(watchdog.time, "sleep"):
            posts = watchdog.fetch_webpage(source)

        self.assertEqual(len({post["key"] for post in posts}), 2)
        self.assertIn("10/2 19:10 Plaza", posts[0]["text"])
        self.assertIn("harmonica solo", posts[0]["text"])

    def test_program_crawl_reports_its_first_scan(self):
        state = {"version": 1, "sources": {}}
        now = dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc)
        source = {**self.source, "follow_links": "detail"}
        self.assertFalse(watchdog.webpage_due_info(source, state, now=now)[3])

    def test_webpage_schedule_baselines_once_then_waits(self):
        state = {"version": 1, "sources": {}}
        now = dt.datetime(2026, 8, 20, tzinfo=dt.timezone.utc)

        due, _, changed, initial = watchdog.webpage_due_info(self.source, state, now=now)
        self.assertTrue(due)
        self.assertTrue(changed)
        self.assertTrue(initial)

        watchdog.record_webpage_attempt(state, self.source, now=now, status="ok", post_count=1)
        due, reason, _, initial = watchdog.webpage_due_info(
            self.source,
            state,
            now=now + dt.timedelta(hours=1),
        )
        self.assertFalse(due)
        self.assertIn("scheduled until", reason)
        self.assertFalse(initial)


class SocialFeedWatchdogThreadsTests(unittest.TestCase):
    def setUp(self):
        watchdog._THREADS_QUERY_METADATA_CACHE = None
        self.source = {
            "id": "threads_example",
            "name": "Example",
            "platform": "threads",
            "type": "rss",
            "username": "example",
            "limit": 5,
            "rsshub_base": "https://rss.observe.tw",
            "route": "/threads/{username}",
        }

    def test_query_metadata_discovers_current_doc_id_and_relay_variables(self):
        html = '<script src="https://static.cdninstagram.com/one.js"></script>'
        script = (
            '__d("BarcelonaProfileThreadsTabRefetchableDirectQuery_threadsRelayOperation",[], '
            '(function(t,n,r,o,a,i){a.exports="27422205010763282"}),null);'
            'name:"__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider"'
        )

        doc_id, variables = watchdog.threads_query_metadata(FakeOpener([script]), html)

        self.assertEqual(doc_id, "27422205010763282")
        self.assertIn("__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider", variables)

    def test_normalize_threads_graphql_posts_keeps_authored_posts_and_media(self):
        payload = {
            "data": {
                "mediaData": {
                    "edges": [
                        {
                            "node": {
                                "thread_items": [
                                    {
                                        "post": {
                                            "pk": "123",
                                            "code": "ABC123",
                                            "taken_at": 1_700_000_000,
                                            "caption": {"text": "口琴演出公告"},
                                            "user": {"username": "example", "profile_pic_url": "https://img/avatar.jpg"},
                                            "image_versions2": {"candidates": [{"url": "https://img/post.jpg"}]},
                                            "video_versions": [{"url": "https://video/post.mp4"}],
                                        }
                                    },
                                    {
                                        "post": {
                                            "pk": "reply",
                                            "code": "REPLY",
                                            "caption": {"text": "other user reply"},
                                            "user": {"username": "someone_else"},
                                        }
                                    },
                                ]
                            }
                        }
                    ]
                }
            }
        }

        posts = watchdog.normalize_threads_graphql_posts(
            self.source,
            payload,
            source_feed_url="https://www.threads.com/@example",
        )

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["post_id"], "123")
        self.assertEqual(posts[0]["url"], "https://www.threads.com/@example/post/ABC123")
        self.assertEqual(posts[0]["images"], ["https://img/post.jpg"])
        self.assertEqual(posts[0]["videos"], ["https://video/post.mp4"])
        self.assertEqual(posts[0]["text"], "口琴演出公告")

    def test_rsshub_503_uses_threads_graphql_fallback(self):
        def rsshub_error(url, code):
            return urllib.error.HTTPError(
                url,
                code,
                "Service Unavailable",
                {},
                io.BytesIO(b"Error Message:<br/><code>Error: Failed to fetch thread data</code>"),
            )

        with (
            mock.patch.object(
                watchdog.urllib.request,
                "urlopen",
                side_effect=[
                    rsshub_error("https://rss.observe.tw/threads/example", 503),
                    rsshub_error("http://127.0.0.1:1200/threads/example", 503),
                ],
            ),
            mock.patch.object(watchdog, "fetch_threads_graphql", return_value=[]) as fallback,
        ):
            posts = watchdog.fetch_rss(self.source)

        self.assertEqual(posts, [])
        fallback.assert_called_once_with(self.source)

    def test_rsshub_socket_timeout_uses_threads_graphql_fallback(self):
        with (
            mock.patch.object(
                watchdog.urllib.request,
                "urlopen",
                side_effect=[socket.timeout("public timeout"), socket.timeout("local timeout")],
            ),
            mock.patch.object(watchdog, "fetch_threads_graphql", return_value=[]) as fallback,
        ):
            posts = watchdog.fetch_rss(self.source)

        self.assertEqual(posts, [])
        fallback.assert_called_once_with(self.source)


class SocialFeedWatchdogInstagramTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "id": "ig_example",
            "name": "Example Instagram",
            "platform": "instagram",
            "type": "rsshub_instagram_profile",
            "username": "example",
            "source_profile_url": "https://www.instagram.com/example/",
        }

    def test_public_post_html_fallback_normalizes_metadata(self):
        body = """
        <meta property="og:url" content="https://www.instagram.com/p/ABC123/">
        <meta property="og:description" content="12 likes, 2 comments - example on July 31, 2026: &quot;口琴演出公告&quot;">
        <meta property="og:image" content="https://cdn.example/post.jpg">
        """
        with mock.patch.object(watchdog.urllib.request, "urlopen", return_value=FakeResponse(body)):
            post = watchdog.fetch_instagram_public_post(
                self.source,
                "https://www.instagram.com/p/ABC123/",
            )

        self.assertIsNotNone(post)
        assert post is not None
        self.assertEqual(post["post_id"], "ABC123")
        self.assertEqual(post["posted_at"], "2026-07-31T00:00:00+00:00")
        self.assertEqual(post["text"], "口琴演出公告")
        self.assertEqual(post["images"], ["https://cdn.example/post.jpg"])

    def test_instaloader_story_fetch_normalizes_helper_json(self):
        source = {
            "id": "ig_story_example",
            "name": "Example Instagram",
            "platform": "instagram",
            "type": "rsshub_instagram_story",
            "provider": "instaloader",
            "story_provider": "instaloader",
            "username": "example",
            "instagram_user_id": "12345",
            "limit": 5,
            "media_type": "instagram_story",
            "ephemeral": True,
            "include_without_keywords": True,
            "source_profile_url": "https://www.instagram.com/example/",
        }
        helper_payload = {
            "version": 1,
            "provider": "instaloader",
            "username": "example",
            "fetched_at": "2026-08-30T01:00:00+00:00",
            "stories": [
                {
                    "id": "123",
                    "caption": "口琴限動",
                    "posted_at": "2026-08-30T00:30:00+00:00",
                    "expires_at": "2026-08-31T00:30:00+00:00",
                    "url": "https://www.instagram.com/stories/example/123/",
                    "images": ["https://cdn.example/story.jpg"],
                    "videos": [],
                }
            ],
        }
        completed = subprocess.CompletedProcess([], 0, stdout=watchdog.json.dumps(helper_payload), stderr="")
        with (
            mock.patch.dict(watchdog.os.environ, {"HARMONICA_INSTALOADER_PYTHON": sys.executable}),
            mock.patch.object(watchdog.subprocess, "run", return_value=completed) as run,
        ):
            posts = watchdog.fetch_rss(source)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["story_provider"], "instaloader")
        self.assertEqual(posts[0]["story_expires_at"], "2026-08-31T00:30:00+00:00")
        self.assertEqual(posts[0]["images"], ["https://cdn.example/story.jpg"])
        self.assertIn("--user-id", run.call_args.args[0])
        self.assertIn("12345", run.call_args.args[0])

    def test_instaloader_profile_fetch_uses_cached_user_id_and_normalizes_json(self):
        source = {
            "id": "ig_example",
            "name": "Example Instagram",
            "platform": "instagram",
            "type": "rsshub_instagram_profile",
            "provider": "instaloader",
            "username": "example",
            "instagram_user_id": "12345",
            "limit": 5,
            "source_profile_url": "https://www.instagram.com/example/",
        }
        helper_payload = {
            "version": 1,
            "provider": "instaloader",
            "username": "example",
            "fetched_at": "2026-08-31T00:00:00+00:00",
            "posts": [
                {
                    "id": "987",
                    "caption": "口琴貼文",
                    "posted_at": "2026-08-30T23:00:00+00:00",
                    "url": "https://www.instagram.com/p/ABC/",
                    "images": ["https://cdn.example/post.jpg"],
                    "videos": [],
                }
            ],
        }
        completed = subprocess.CompletedProcess([], 0, stdout=watchdog.json.dumps(helper_payload), stderr="")
        with (
            mock.patch.dict(watchdog.os.environ, {"HARMONICA_INSTALOADER_PYTHON": sys.executable}),
            mock.patch.object(watchdog.subprocess, "run", return_value=completed) as run,
        ):
            posts = watchdog.fetch_rss(source)

        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["text"], "口琴貼文")
        self.assertEqual(posts[0]["images"], ["https://cdn.example/post.jpg"])
        self.assertIn("--user-id", run.call_args.args[0])
        self.assertIn("12345", run.call_args.args[0])

    def test_instaloader_auth_failure_is_not_treated_as_empty_story(self):
        source = {
            "id": "ig_story_example",
            "name": "Example Instagram",
            "platform": "instagram",
            "type": "rsshub_instagram_story",
            "provider": "instaloader",
            "username": "example",
        }
        completed = subprocess.CompletedProcess(
            [], 2, stdout="", stderr="Instaloader session rejected by Instagram"
        )
        with (
            mock.patch.dict(watchdog.os.environ, {"HARMONICA_INSTALOADER_PYTHON": sys.executable}),
            mock.patch.object(watchdog.subprocess, "run", return_value=completed),
        ):
            with self.assertRaisesRegex(ValueError, "session rejected"):
                watchdog.fetch_rss(source)

    def test_instaloader_auth_error_detection(self):
        self.assertTrue(watchdog.is_instaloader_auth_error('401 Unauthorized - "Please wait a few minutes"'))
        self.assertTrue(watchdog.is_instaloader_auth_error("Instaloader session rejected by Instagram"))
        self.assertFalse(watchdog.is_instaloader_auth_error("profile has no public stories"))

    def test_instaloader_auth_block_expires(self):
        now = watchdog.dt.datetime(2026, 8, 31, 0, 0, tzinfo=watchdog.dt.timezone.utc)
        state = {}
        watchdog.set_instaloader_auth_block(
            state,
            now=now,
            cooldown_hours=6,
            error="401 Unauthorized",
        )
        self.assertIn("blocked until", watchdog.instaloader_auth_block_reason(state, now=now))
        self.assertEqual(
            watchdog.instaloader_auth_block_reason(
                state,
                now=now + watchdog.dt.timedelta(hours=7),
            ),
            "",
        )
        self.assertNotIn(watchdog.INSTALOADER_AUTH_BLOCK_KEY, state)


if __name__ == "__main__":
    unittest.main()
