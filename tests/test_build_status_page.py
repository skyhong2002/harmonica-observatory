import sys
import datetime as dt
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_status_page  # noqa: E402


class CollectionStatusTests(unittest.TestCase):
    def test_facebook_due_without_selection_is_paused_even_with_zero_minimum(self):
        plan = {"ok": True, "has_token": True, "sources_due_count": 73,
                "sources_selected_count": 0, "min_sources_per_run": 0}
        self.assertEqual(build_status_page.facebook_plan_status(plan), ("paused", "budget_deferred"))
        self.assertEqual(build_status_page.facebook_plan_status({**plan, "sources_due_count": 0}),
                         ("paused", "no_sources_due"))
        self.assertEqual(build_status_page.facebook_plan_status({**plan, "sources_selected_count": 3}), ("ok", ""))
        self.assertEqual(build_status_page.facebook_plan_status({**plan, "sources_selected_count": 3, "cadence_ready": False}),
                         ("paused", "scheduled"))
        self.assertEqual(build_status_page.facebook_plan_status({**plan, "has_token": False})[0], "degraded")

    def test_coverage_uses_successful_checks_not_attempts_posts_or_plans(self):
        now = dt.datetime(2026, 10, 18, tzinfo=dt.timezone.utc)
        fresh = (now - dt.timedelta(hours=2)).isoformat()
        stale = (now - dt.timedelta(days=2)).isoformat()
        sources = [{"id": sid, "platform": platform, "type": kind} for sid, platform, kind in (
            ("web_ok", "website", "webpage_watch"), ("web_error", "website", "webpage_watch"),
            ("web_old", "website", "webpage_watch"), ("fb_ok", "facebook", "facebook_page_posts"),
            ("fb_unknown", "facebook", "facebook_page_posts"), ("yt", "youtube", "youtube_ytdlp"))]
        sources.append({"id": "ig", "platform": "instagram", "provider": "apify_stories"})
        fetch = {"sources": {"web_ok": {"last_success_at": fresh, "last_post_count": 0},
                             "web_error": {"last_attempt_at": fresh, "last_status": "error"},
                             "web_old": {"last_success_at": stale}}}
        facebook = {"runs": [{"finished_at": fresh, "status": "SUCCEEDED",
                               "source_ids": ["fb_ok", "fb_unknown"], "confirmed_source_ids": ["fb_ok"]}]}
        result = build_status_page.source_coverage(sources, fetch, {"sources": {"ig": {"last_success_at": fresh}}},
                                                  facebook, {"sources": {"yt": {"last_success_at": stale}}}, now=now)
        self.assertEqual(result["website"]["checkedSources24h"], 1)
        self.assertEqual(result["website"]["totalSources"], 3)
        self.assertEqual(result["facebook"]["checkedSources24h"], 1)
        self.assertEqual(result["instagram"]["checkedSources24h"], 1)
        self.assertEqual(result["youtube"]["checkedSources24h"], 0)
        self.assertEqual(result["youtube"]["lastSuccessAt"], stale)

    def build_fixture(self, *, offline=False):
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        values = {build_status_page.LATEST_API: {"generatedAt": now, "updates": [{}]},
                  build_status_page.SOURCES_API: {"count": 1}}
        with (patch.object(build_status_page, "enabled_watch_sources", return_value=[
                {"id": "fb", "platform": "facebook", "type": "facebook_page_posts"}]),
              patch.object(build_status_page, "read_json", side_effect=lambda path, default: values.get(path, default)),
              patch.object(build_status_page, "read_jsonl", return_value=[]),
              patch.object(build_status_page, "file_mtime", return_value=None),
              patch.object(build_status_page, "launch_agent_status", return_value={"available": True, "status": "ok"}),
              patch.object(build_status_page, "probe_url", return_value={"ok": True}),
              patch.object(build_status_page, "apify_check", return_value={"ok": True, "has_token": True,
                  "sources_due_count": 1, "sources_selected_count": 0, "min_sources_per_run": 0}),
              patch("apify_pool.crawl_schedule_snapshot", return_value={"available": False})):
            return build_status_page.build_status(offline=offline)

    def test_fresh_build_keeps_budget_pause_and_zero_source_coverage(self):
        result = self.build_fixture()
        self.assertEqual(result["overall"]["status"], "paused")
        facebook = result["watchSources"]["platformRows"][0]
        self.assertEqual(facebook["status"], "paused")
        self.assertEqual(facebook["reasonCode"], "budget_deferred")
        self.assertEqual(facebook["coverage"]["checkedSources24h"], 0)
        self.assertEqual(facebook["coverage"]["lastSuccessAt"], "")
        self.assertTrue(result["metrics"]["latestDataAt"])

    def test_offline_probes_are_unknown_before_overall_and_platform_statuses(self):
        result = self.build_fixture(offline=True)
        self.assertEqual(result["overall"]["status"], "unknown")
        self.assertEqual(result["watchSources"]["platformRows"][0]["status"], "unknown")


class PersistentSourceErrorTests(unittest.TestCase):
    def setUp(self):
        self.source_by_id = {
            "threads_example": {"id": "threads_example", "type": "rss", "platform": "threads"},
            "x_example": {"id": "x_example", "type": "rss", "platform": "x"},
        }

    def state(self, error):
        return {
            "sources": {
                source_id: {
                    "source_type": "rss",
                    "consecutive_errors": 4,
                    "last_error": error,
                    "last_error_at": "2026-10-16T06:00:00+00:00",
                }
                for source_id in self.source_by_id
            }
        }

    def test_backed_off_threads_upstream_outage_stays_hidden(self):
        rows = build_status_page.persistent_source_errors(
            self.state("RSSHub HTTP 503: Error: Failed to fetch thread data"), self.source_by_id, []
        )
        self.assertEqual([row["source_id"] for row in rows], ["x_example"])

    def test_backed_off_feed_with_other_errors_is_reported(self):
        rows = build_status_page.persistent_source_errors(self.state("HTTP 500"), self.source_by_id, [])
        self.assertEqual(sorted(row["source_id"] for row in rows), ["threads_example", "x_example"])
        self.assertTrue(all(row["error"].startswith("連續失敗 4 次") for row in rows))


if __name__ == "__main__":
    unittest.main()
