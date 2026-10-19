"""AST-only protocol regression tests; no product imports, state or network."""
from __future__ import annotations

import ast
import copy
import datetime as dt
import html
from pathlib import Path
import re
import socket
import subprocess
from typing import Any
import unittest
from unittest.mock import patch
import urllib.parse
import urllib.request


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/social_feed_watchdog.py"


def timeline(*posts):
    return {"data": {"mediaData": {"edges": [
        {"node": {"thread_items": [{"post": post} for post in posts]}}
    ]}}}


def example(**changes):
    return {"pk": "123", "id": "456", "code": "ABC123",
            "user": {"username": "example"}, "taken_at": 1700000000,
            "caption": {"text": "synthetic announcement"}, **changes}


class TimelineShapeTests(unittest.TestCase):
    def setUp(self):
        for owner, name in ((socket, "socket"), (socket, "getaddrinfo"),
                            (socket, "create_connection"), (urllib.request, "urlopen"),
                            (subprocess, "run"), (subprocess, "Popen")):
            guard = patch.object(owner, name, side_effect=AssertionError("live action forbidden"))
            guard.start()
            self.addCleanup(guard.stop)
        names = {"append_unique", "compact_text", "is_story_source", "normalize_post",
                 "threads_media_urls", "normalize_threads_graphql_posts"}
        nodes = [n for n in ast.parse(SCRIPT.read_bytes()).body
                 if isinstance(n, ast.FunctionDef) and n.name in names]
        self.assertEqual({n.name for n in nodes}, names)
        self.ns = {"Any": Any, "dt": dt, "html": html, "re": re,
                   "urllib": urllib, "THREADS_BASE_URL": "https://www.threads.com"}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SCRIPT), "exec"), self.ns)
        self.source = {"id": "rss_fixture", "username": "example", "platform": "threads", "limit": 5}

    def normalize(self, payload):
        return self.ns["normalize_threads_graphql_posts"](
            self.source, payload, source_feed_url="https://www.threads.com/@example")

    def test_real_empty_timeline_is_success(self):
        self.assertEqual(self.normalize({"data": {"mediaData": {"edges": []}}}), [])

    def test_missing_null_and_wrong_type_containers_fail(self):
        values = [None, [], {}, {"errors": [{"message": "synthetic"}]},
                  {"data": None}, {"data": []}, {"data": {"mediaData": None}},
                  {"data": {"mediaData": []}}, {"data": {"mediaData": {}}}]
        values += [{"data": {"mediaData": {"edges": v}}} for v in (None, {}, "", 0)]
        for value in values:
            with self.subTest(payload=value), self.assertRaisesRegex(ValueError, "Threads timeline"):
                self.normalize(value)

    def test_malformed_nonempty_edges_and_posts_fail(self):
        edges = [None, [], {}, {"node": None}, {"node": []}, {"node": {}},
                 {"node": {"thread_items": None}}, {"node": {"thread_items": {}}},
                 {"node": {"thread_items": []}}]
        edges += [{"node": {"thread_items": [v]}} for v in
                  (None, [], {}, {"post": None}, {"post": []}, {"post": {}},
                   {"post": {"pk": {"bad": "identity"}}}, {"post": {"pk": True}})]
        for edge in edges:
            with self.subTest(edge=edge), self.assertRaisesRegex(ValueError, "Threads timeline"):
                self.normalize({"data": {"mediaData": {"edges": [edge]}}})

    def test_bad_edge_after_usable_posts_never_becomes_partial_success(self):
        self.source["limit"] = 1
        value = timeline(example())
        value["data"]["mediaData"]["edges"].append(None)
        before = copy.deepcopy(value)
        with self.assertRaises(ValueError):
            self.normalize(value)
        self.assertEqual(value, before)

    def test_known_identity_precedence_and_media_stay_unchanged(self):
        for post, identity in ((example(), "123"), (example(pk=None), "456"),
                               (example(pk=None, id=None), "ABC123"), (example(pk=123), "123")):
            post.update(image_versions2={"candidates": [{"url": "https://img.invalid/post.jpg"}]},
                        video_versions=[{"url": "https://video.invalid/post.mp4"}])
            value = timeline(post)
            before = copy.deepcopy(value)
            with self.subTest(identity=identity):
                rows = self.normalize(value)
                self.assertEqual(rows[0]["post_id"], identity)
                self.assertEqual(rows[0]["key"], "rss_fixture:" + identity)
                self.assertEqual(rows[0]["source_id"], "rss_fixture")
                self.assertEqual(rows[0]["images"], ["https://img.invalid/post.jpg"])
                self.assertEqual(rows[0]["videos"], ["https://video.invalid/post.mp4"])
                self.assertEqual(value, before)

    def test_valid_other_author_filtering_and_duplicate_identity_stay_unchanged(self):
        self.assertEqual(self.normalize(timeline(example(user={"username": "other"}))), [])
        self.assertEqual(len(self.normalize(timeline(example(), example()))), 1)


if __name__ == "__main__":
    unittest.main()
