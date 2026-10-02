import copy
import datetime as dt
import contextlib
import io
import json
import sys
import tempfile
import shutil
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import insta_stories_viewer as adapter


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc).timestamp()
        self.item = {"id": "123", "taken_at_timestamp": self.now - 3600,
                     "expiring_at": self.now + 23 * 3600}
        self.payload = {"data": {"status": "success", "serverType": "stories",
                                 "user": {"username": "example", "is_private": False,
                                          "reels": [self.item]}}}

    def test_completed_success_and_explicit_empty(self):
        self.assertEqual(adapter.classify_result(self.payload, "example")["status"], "stories")
        self.payload["data"]["user"]["reels"] = []
        self.assertEqual(adapter.classify_result(self.payload, "EXAMPLE")["status"], "empty")

    def test_posts_event_and_pending_are_not_empty(self):
        self.payload["data"]["serverType"] = "posts"
        self.assertEqual(adapter.classify_result(self.payload, "example")["status"], "loading")
        self.payload["data"].update(serverType="stories", status="pending")
        self.assertEqual(adapter.classify_result(self.payload, "example")["status"], "loading")

    def test_missing_reels_and_wrong_account_fail_closed(self):
        self.assertEqual(adapter.classify_result(self.payload, "other")["reason"], "account_mismatch")
        del self.payload["data"]["user"]["reels"]
        self.assertEqual(adapter.classify_result(self.payload, "example")["status"], "service_failed")
        for value in [None, [], {}, {"data": []}]:
            self.assertEqual(adapter.classify_result(value, "example")["status"], "service_failed")

    def test_distinct_provider_errors(self):
        for code, status in [(404, "not_found"), (403, "private"), (408, "service_failed"),
                             (430, "service_failed"), (500, "service_failed"), (429, "rate_limited")]:
            payload = {"data": {"serverType": "stories", "status": "error", "code": code}}
            self.assertEqual(adapter.classify_result(payload, "example")["status"], status)

    def test_private_never_counts_as_empty(self):
        self.payload["data"]["user"].update(is_private=True, reels=[])
        self.assertEqual(adapter.classify_result(self.payload, "example")["status"], "private")

    def test_original_expiry_does_not_shorten_display_window(self):
        item = {**self.item, "taken_at_timestamp": self.now - 30 * 3600,
                "expiring_at": self.now - 6 * 3600}
        accepted, rejected = adapter.eligible_items([item], self.now)
        self.assertFalse(rejected)
        self.assertEqual(accepted[0]["posted_at"], adapter.publication_time(item["taken_at_timestamp"]))
        self.assertEqual(accepted[0]["source_expires_at"], adapter.publication_time(item["expiring_at"]))

    def test_48_hour_boundary_is_expired(self):
        items = [{**self.item, "taken_at_timestamp": self.now - 48 * 3600}]
        accepted, rejected = adapter.eligible_items(items, self.now)
        self.assertFalse(accepted)
        self.assertEqual(rejected[0]["reason"], "display_expired")

    def test_duplicate_story_id_downloaded_only_once(self):
        accepted, rejected = adapter.eligible_items([self.item, copy.deepcopy(self.item)], self.now)
        self.assertEqual(len(accepted), 1)
        self.assertEqual(rejected, [{"id": "123", "reason": "duplicate"}])

    def test_missing_dates_never_use_observation_or_story_id(self):
        item = {"id": "3991885410459699733", "date": self.now, "observed_at": self.now}
        accepted, rejected = adapter.eligible_items([item], self.now)
        self.assertFalse(accepted)
        self.assertEqual(rejected[0]["reason"], "missing_publication_time")

    def test_no_invented_source_expiry_and_no_future_publication(self):
        item = {"id": "123", "taken_at_timestamp": self.now - 3600}
        accepted, _ = adapter.eligible_items([item], self.now)
        self.assertIsNone(accepted[0]["source_expires_at"])
        _, rejected = adapter.eligible_items([{**item, "taken_at_timestamp": self.now + 1}], self.now)
        self.assertEqual(rejected[0]["reason"], "future_publication_time")

    def test_invalid_and_ambiguous_dates_are_rejected(self):
        for value in [None, True, False, 0, float("nan"), float("inf"), 1e30,
                      "2026-09-24T00:00:00", "2 hours ago", "bad"]:
            self.assertIsNone(adapter.publication_time(value))

    def test_actual_live_success_has_no_importable_original_metadata(self):
        path = Path(__file__).parent / "fixtures/insta_stories_viewer/nycu-success-redacted.json"
        report = adapter.diagnose(json.loads(path.read_text()), "nycu_harmonica", self.now)
        self.assertEqual(report["status"], "stories")
        self.assertEqual(report["story_count"], 1)
        self.assertEqual(report["numeric_ids"], 0)
        self.assertEqual(report["explicit_publication_times"], 0)
        self.assertEqual(report["explicit_source_expiries"], 0)
        self.assertEqual(report["eligible_count"], 0)
        self.assertFalse(report["collector_available"])

    def test_empty_failed_and_media_failure_cannot_modify_existing_cache(self):
        existing = [{"post_id": "123", "posted_at": "2026-09-23T00:00:00Z", "image_url": "/assets/retained.webp"}]
        before = copy.deepcopy(existing)
        cases = [self.payload, {"data": {"status": "error", "code": 408, "serverType": "stories"}},
                 {"data": {"status": "success", "serverType": "stories", "user": {"username": "example", "reels": []}}}]
        for payload in cases:
            report = adapter.diagnose(payload, "example", self.now, cached_posts=existing,
                                      download=lambda value: {"status": "download_failed"})
            self.assertFalse(report["cache_written"])
            self.assertEqual(existing, before)

    def test_network_probe_is_disabled_by_default(self):
        with mock.patch.dict(adapter.os.environ, {}, clear=True), mock.patch.object(adapter, "probe_media") as download:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                adapter.main(["--input", "unused.json", "--account", "example", "--probe-media"])
            self.assertEqual(error.exception.code, 2)
            download.assert_not_called()

    def test_cli_reads_fixture_without_network_and_never_writes(self):
        fixture = Path(__file__).parent / "fixtures/insta_stories_viewer/nycu-success-redacted.json"
        output = io.StringIO()
        with mock.patch.object(adapter, "probe_media") as download, contextlib.redirect_stdout(output):
            code = adapter.main(["--input", str(fixture), "--account", "nycu_harmonica"])
        self.assertEqual(code, 0)
        self.assertFalse(json.loads(output.getvalue())["cache_written"])
        download.assert_not_called()

    def test_oversized_input_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            path.write_bytes(b"x" * (adapter.MAX_INPUT_BYTES + 1))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(adapter.main(["--input", str(path), "--account", "example"]), 1)


class MediaProbeTests(unittest.TestCase):
    def response(self, body=b"image-data", content_type="image/webp"):
        stream = io.BytesIO(body)
        stream.headers = {"Content-Type": content_type}
        return stream

    def test_success_keeps_only_hash_size_and_type(self):
        opener = mock.Mock(return_value=self.response())
        result = adapter.probe_media("temporary/opaque+value", opener=opener)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(result["bytes"], 10)
        request = opener.call_args.args[0]
        self.assertEqual(request.host, "cdn.insta-stories-viewer.com")
        self.assertNotIn("Cookie", request.headers)
        self.assertNotIn("temporary", json.dumps(result))
        self.assertEqual(opener.call_args.kwargs["timeout"], 25)

    def test_download_error_and_non_media_are_distinct_from_empty_stories(self):
        result = adapter.probe_media("opaque", opener=mock.Mock(side_effect=TimeoutError()))
        self.assertEqual(result["status"], "download_failed")
        result = adapter.probe_media("opaque", opener=mock.Mock(return_value=self.response(b"<html>verification</html>", "text/html")))
        self.assertEqual(result["reason"], "unexpected_content_type")

    def test_download_size_limit_reads_one_byte_over_limit(self):
        stream = self.response(b"123456")
        with mock.patch.object(adapter, "MAX_MEDIA_BYTES", 5):
            result = adapter.probe_media("opaque", opener=mock.Mock(return_value=stream))
        self.assertEqual(result["reason"], "size_limit")

    def test_rate_limit_access_denial_and_no_retry(self):
        for code, status in [(429, "rate_limited"), (403, "access_blocked"), (401, "access_blocked"), (500, "download_failed")]:
            opener = mock.Mock(side_effect=urllib.error.HTTPError("redacted", code, "denied", {}, None))
            result = adapter.probe_media("opaque", opener=opener)
            self.assertEqual(result["status"], status)
            opener.assert_called_once()

    def test_redirect_is_never_followed(self):
        self.assertIsNone(adapter.NoRedirect().redirect_request(None, None, 302, "", {}, "http://127.0.0.1/"))

    def test_verification_page_is_reported_without_retry(self):
        opener = mock.Mock(return_value=self.response(b"<html>Verify you are human</html>", "text/html"))
        result = adapter.probe_media("opaque", opener=opener)
        self.assertEqual(result["status"], "verification_required")
        opener.assert_called_once()

    def test_probe_is_limited_to_one_media(self):
        payload = {"data": {"status": "success", "serverType": "stories", "user": {"username": "example", "reels": [
            {"id": str(i), "display_url": f"opaque-{i}"} for i in range(10)]}}}
        downloader = mock.Mock(return_value={"status": "rate_limited"})
        report = adapter.diagnose(payload, "example", 1790208000, download=downloader)
        downloader.assert_called_once()
        self.assertFalse(report["cache_written"])


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 24, tzinfo=dt.timezone.utc).timestamp()
        self.source = {"id": "ig_story_example", "username": "example", "provider": "apify_stories",
                       "name": "Example", "source_profile_url": "https://www.instagram.com/example/"}
        self.item = {"id": "123", "taken_at": self.now - 3600, "thumbnail_src": "opaque"}
        self.payload = {"data": {"status": "success", "serverType": "stories",
                                 "user": {"username": "example", "is_private": False, "reels": [self.item]}}}
        self.cache = mock.Mock(return_value="/assets/feed-images/example.webp")

    def run_import(self, state, payload=None):
        return adapter.import_result(state, self.source, payload or self.payload, self.now,
                                     media_dir=Path("unused"), cacher=self.cache)

    def test_success_uses_existing_story_key_and_original_date(self):
        state = {}
        result = self.run_import(state)
        self.assertEqual(result["imported"], 1)
        row = state["sources"][self.source["id"]]["posts"][0]
        self.assertEqual(row["key"], "ig_story_example:123")
        self.assertEqual(row["posted_at"], adapter.publication_time(self.item["taken_at"]))
        self.assertIsNone(row["story_expires_at"])
        self.assertEqual(row["story_provider"], "insta_stories_viewer")
        self.assertEqual(adapter.display_expiry(row).timestamp(), self.item["taken_at"] + 48 * 3600)

    def test_existing_duplicate_keeps_media_and_date_even_if_provider_changes_date(self):
        state = {}
        self.run_import(state)
        original = copy.deepcopy(state)
        self.payload["data"]["user"]["reels"][0]["taken_at"] = self.now - 60
        self.cache.reset_mock()
        result = self.run_import(state)
        self.assertEqual(result["duplicates"], 1)
        self.assertEqual(result["rejections"][0]["reason"], "cached_time_conflict")
        self.assertEqual(state, original)
        self.cache.assert_not_called()

    def test_failure_empty_and_invalid_time_do_not_clear_existing_cache(self):
        state = {}
        self.run_import(state)
        original = copy.deepcopy(state)
        for data in [{"status": "error", "code": 436, "serverType": "stories"},
                     {"status": "success", "serverType": "stories", "user": {"username": "example", "reels": []}},
                     {"status": "success", "serverType": "stories", "user": {"username": "example", "reels": [{"id": "999"}]}}]:
            self.run_import(state, {"data": data})
            self.assertEqual(state, original)

    def test_download_failure_keeps_valid_old_rows_and_reports_error(self):
        state = {}
        self.run_import(state)
        original = copy.deepcopy(state)
        self.payload["data"]["user"]["reels"][0]["id"] = "456"
        self.cache.side_effect = ValueError("download failed")
        result = self.run_import(state)
        self.assertEqual(len(result["media_errors"]), 1)
        self.assertEqual(state, original)

    def test_download_denial_stops_remaining_items(self):
        self.payload["data"]["user"]["reels"].append({**self.item, "id": "456"})
        self.cache.side_effect = adapter.MediaFailure("rate_limited")
        result = self.run_import({})
        self.assertTrue(result["stopped"])
        self.cache.assert_called_once()

    def test_expired_and_duplicate_items_not_downloaded(self):
        self.payload["data"]["user"]["reels"] += [copy.deepcopy(self.item),
            {**self.item, "id": "456", "taken_at": self.now - 48 * 3600}]
        result = self.run_import({})
        self.cache.assert_called_once()
        self.assertEqual({r["reason"] for r in result["rejections"]}, {"duplicate", "display_expired"})

    def test_actual_sirius_fixture_has_valid_id_and_publication_but_unknown_expiry(self):
        payload = json.loads((Path(__file__).parent / "fixtures/insta_stories_viewer/sirius-success-redacted.json").read_text())
        source = {**self.source, "username": "siriusharmonicaensemble"}
        state = {}
        result = adapter.import_result(state, source, payload, self.now, media_dir=Path("unused"), cacher=self.cache)
        self.assertEqual(result["imported"], 1)
        row = state["sources"][source["id"]]["posts"][0]
        self.assertEqual(row["post_id"], "3992702751863962825")
        self.assertEqual(row["posted_at"], "2026-09-23T18:14:39+00:00")
        self.assertIsNone(row["story_expires_at"])

    def test_import_is_readable_by_existing_watchdog_cache_bridge(self):
        import social_feed_watchdog as watchdog
        state = {}
        self.run_import(state)
        fixed_now = dt.datetime.fromtimestamp(self.now, dt.timezone.utc)
        with mock.patch.object(watchdog, "load_json", return_value=state), mock.patch.object(watchdog.dt, "datetime", wraps=dt.datetime) as clock:
            clock.now.return_value = fixed_now
            rows = watchdog.cached_instagram_posts({**self.source, "type": "rsshub_instagram_story"})
        self.assertEqual(rows[0]["key"], "ig_story_example:123")
        self.assertTrue(watchdog.externally_collected_instagram(self.source))


class LiveControlTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        (self.root / "data/feeds").mkdir(parents=True)
        self.sources = [{"id": "ig_story_" + a, "username": a, "enabled": True, "provider": "apify_stories"} for a in ["a", "b"]]
        (self.root / "data/feeds/social_sources.json").write_text(json.dumps({"sources": self.sources}))

    def test_disabled_means_no_network_or_state_writes(self):
        with mock.patch.dict(adapter.os.environ, {}, clear=True), mock.patch.object(adapter, "fetch_account") as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(adapter.live_run(["a"], collect=False, root=self.root), 2)
            fetch.assert_not_called()
            self.assertFalse((self.root / "state").exists())

    def test_account_limit_and_allowlist_checked_before_network(self):
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account") as fetch:
            for names in [[], ["unknown"], [f"user{i}" for i in range(6)]]:
                with self.assertRaises(ValueError):
                    adapter.live_run(names, collect=False, root=self.root)
            fetch.assert_not_called()

    def test_429_stops_batch_and_persists_cooldown_without_touching_cache(self):
        payload = {"data": {"status": "error", "serverType": "stories", "code": 429}}
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account", return_value=payload) as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(adapter.live_run(["a", "b"], collect=False, root=self.root), 1)
                self.assertEqual(adapter.live_run(["b"], collect=False, root=self.root), 1)
            fetch.assert_called_once_with("a")
        self.assertFalse((self.root / "state/instagram_public.json").exists())
        self.assertFalse((self.root / "state/insta_stories_viewer.lock").exists())

    def test_account_pacing_and_crash_reservation(self):
        def fetch(account):
            self.assertTrue((self.root / "state/insta_stories_viewer.json").exists())
            return {"data": {"status": "success", "serverType": "stories", "user": {"username": account, "reels": []}}}
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account", side_effect=fetch), mock.patch.object(adapter.time, "time", return_value=1790208000), mock.patch.object(adapter.time, "sleep") as sleep:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(adapter.live_run(["a", "b"], collect=False, root=self.root), 0)
            sleep.assert_called_once_with(175)

    def test_transport_failure_stops_without_logging_provider_details(self):
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account", return_value={"transport_error": "verification_required"}) as fetch:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(adapter.live_run(["a", "b"], collect=False, root=self.root), 1)
            fetch.assert_called_once()

    def test_corrupt_state_fails_closed_and_releases_lock(self):
        (self.root / "state").mkdir()
        (self.root / "state/insta_stories_viewer.json").write_text("[]")
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account") as fetch:
            with self.assertRaises(ValueError):
                adapter.live_run(["a"], collect=False, root=self.root)
            fetch.assert_not_called()
        self.assertFalse((self.root / "state/insta_stories_viewer.lock").exists())


class ScheduledControlTests(unittest.TestCase):
    setUp = LiveControlTests.setUp
    def test_rotation_skips_recent_primary_and_recent_attempt(self):
        now = 1790208000
        sources = {s["username"]: s for s in self.sources}
        cache = {"sources": {"ig_story_a": {"last_success_at": adapter.publication_time(now - 3600)}}}
        self.assertEqual(adapter.scheduled_accounts(["a", "b"], sources, cache, {}, now, 1), ["b"])
        guard = {"accounts": {"b": {"checked_at": adapter.publication_time(now - 3600)}}}
        self.assertEqual(adapter.scheduled_accounts(["a", "b"], sources, cache, guard, now, 1), [])
        self.assertEqual(adapter.scheduled_accounts(["a", "b"], sources, cache, guard, now + 43200, 1), ["a"])

    def test_scheduled_publish_holds_lock_and_reserves_three_hours(self):
        import run_pipeline
        now = 1790208000
        payload = {"data": {"status": "success", "serverType": "stories", "user": {"username": "a", "reels": []}}}
        def publisher(root):
            self.assertTrue((root / "state/run_pipeline.lock").exists())
            return {"status": "unchanged"}
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1", "HARMONICA_ISV_BATCH_SIZE": "1"}), mock.patch.object(adapter.time, "time", return_value=now), mock.patch.object(adapter, "fetch_account", return_value=payload) as fetch, mock.patch("publish_story_cache.publish_cached_stories", side_effect=publisher) as publish, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(adapter.live_run(["a", "b"], collect=True, scheduled=True, publish=True, root=self.root), 0)
            self.assertEqual(adapter.live_run(["a", "b"], collect=True, scheduled=True, publish=True, root=self.root), 0)
            fetch.assert_called_once_with("a")
            publish.assert_called_once()
        guard = json.loads((self.root / "state/insta_stories_viewer.json").read_text())
        self.assertEqual(guard["next_scheduled_at"], now + 10800)
        self.assertFalse((self.root / "state/run_pipeline.lock").exists())
        self.assertFalse((self.root / "state/instagram_public.json").exists())

    def test_inherited_pipeline_lock_is_not_reacquired_or_released(self):
        import run_pipeline
        pipeline_lock = self.root / "state/run_pipeline.lock"
        self.assertTrue(run_pipeline.acquire_lock(pipeline_lock, stale_after_minutes=240))
        payload = {"data": {"status": "success", "serverType": "stories", "user": {"username": "a", "reels": []}}}
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account", return_value=payload), mock.patch.object(run_pipeline, "acquire_lock", wraps=run_pipeline.acquire_lock) as acquire, mock.patch.object(run_pipeline, "release_lock", wraps=run_pipeline.release_lock) as release, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(adapter.live_run(["a"], collect=True, root=self.root, pipeline_lock_held=True), 0)
            self.assertEqual([call.args[0].name for call in acquire.call_args_list], ["insta_stories_viewer.lock"])
            self.assertEqual([call.args[0].name for call in release.call_args_list], ["insta_stories_viewer.lock"])
        self.assertTrue(pipeline_lock.exists())
        run_pipeline.release_lock(pipeline_lock)

    def test_publisher_failure_preserves_cache_and_reports_failure(self):
        state = self.root / "state/instagram_public.json"
        state.parent.mkdir()
        original = '{"sources": {}, "marker": "preserved"}'
        state.write_text(original)
        payload = {"data": {"status": "success", "serverType": "stories", "user": {"username": "a", "reels": []}}}
        with mock.patch.dict(adapter.os.environ, {"HARMONICA_ISV_ENABLED": "1"}), mock.patch.object(adapter, "fetch_account", return_value=payload), mock.patch("publish_story_cache.publish_cached_stories", side_effect=RuntimeError("fixture")), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(adapter.live_run(["a"], collect=True, publish=True, root=self.root), 1)
        self.assertEqual(state.read_text(), original)
        self.assertEqual(json.loads((self.root / "state/insta_stories_viewer.json").read_text())["last_publication"]["status"], "failed")


@unittest.skipUnless(shutil.which("node"), "Node runtime unavailable")
class TransportTests(unittest.TestCase):
    def run_transport(self, fetch_body):
        helper = Path(adapter.__file__).with_name("insta_stories_viewer_transport.mjs").as_uri()
        program = f"""
process.argv[2] = 'example';
globalThis.fetch = async (url, options) => {{ {fetch_body} }};
globalThis.WebSocket = class extends EventTarget {{
  constructor() {{ super(); setTimeout(()=>this.dispatchEvent(new MessageEvent('message',{{data:'0{{}}'}})),0); }}
  send(packet) {{
    if (packet==='40') {{ this.dispatchEvent(new MessageEvent('message',{{data:'40{{}}'}})); return; }}
    if (packet.startsWith('42')) {{
      const [event, body] = JSON.parse(packet.slice(2));
      if (event!=='search'||body.username!=='example'||body.serverType!=='stories'||body.token!=='fixture-nonce') throw Error('incorrect protocol');
      this.dispatchEvent(new MessageEvent('message',{{data:'42'+JSON.stringify(['searchResult',{{data:{{status:'success',code:200,serverType:'stories',user:{{username:'example',reels:[]}}}}}}])}}));
    }}
  }}
  close() {{}}
}};
await import({json.dumps(helper)});
"""
        result = subprocess.run(["node", "--input-type=module", "-e", program], capture_output=True, text=True, timeout=5, check=True)
        self.assertNotIn("fixture-nonce", result.stdout)
        return json.loads(result.stdout)

    def test_success_protocol_and_no_cookie_headers(self):
        result = self.run_transport("""
if ('Cookie' in options.headers) throw Error('unexpected cookie');
return new Response(url.endsWith('/connect/') ? JSON.stringify({token:'fixture-nonce'}) : "var USER_NAME = 'example'; var USER_NEED_UPDATE = true;");
""")
        self.assertEqual(result["data"]["status"], "success")

    def test_http_rate_limit_and_access_block_stop_before_socket(self):
        for code in [401, 403, 429]:
            result = self.run_transport(f"return new Response('blocked', {{status:{code}}});")
            self.assertEqual(result["transport_error"], f"http_{code}")

    def test_verification_page_stops_before_nonce_request(self):
        result = self.run_transport("return new Response('<title>Just a moment</title>');")
        self.assertEqual(result["transport_error"], "verification_required")


if __name__ == "__main__":
    unittest.main()
