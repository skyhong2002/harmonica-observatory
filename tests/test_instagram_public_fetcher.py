import copy
import datetime as dt
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import instagram_public_fetcher as collector
import social_feed_watchdog as watchdog
import build_status_page as status


class InstagramPublicTests(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 9, 18, 12, tzinfo=dt.timezone.utc).timestamp()
        self.source = {"id": "ig_story_test", "username": "test", "name": "Test Club",
                       "provider": "apify_stories", "type": "rsshub_instagram_story",
                       "source_profile_url": "https://www.instagram.com/test/"}
        self.limits = {"limits": {"maxMonthlyUsageUsd": 5}, "current": {"monthlyUsageUsd": 3},
                       "monthlyUsageCycle": {"endAt": "2026-09-20T00:00:00Z"}}

    def test_budget_respects_project_and_account_caps(self):
        self.assertEqual(collector.remaining_credit(self.limits, 4), 1)
        self.assertEqual(collector.remaining_credit(self.limits, 50), 2)
        self.assertEqual(collector.remaining_credit({}, 5), 0)
        state = {"runs": [{"at": collector.iso(self.now), "reserved_usd": .2}]}
        self.assertEqual(collector.daily_budget(state, self.limits, 5, self.now), 0)

    def test_story_cap_and_tiny_budget(self):
        self.assertEqual(collector.story_plan(.05, 100, 0), (10, 10, .05))
        self.assertEqual(collector.story_plan(.05, 10, 39), (1, 1, .0095))
        self.assertEqual(collector.story_plan(.009, 10, 0), (0, 0, 0))
        self.assertEqual(collector.story_plan(.5, 10, 40), (0, 0, 0))

    def test_denied_does_not_claim_sources_scanned(self):
        state = {}
        with mock.patch.object(collector, "run_actor", return_value=([], {"outcome": "denied", "reason": "user_daily_exhausted"})):
            collector.collect_stories(state, [self.source], "secret", self.limits, 5, self.now, lambda: None, set())
        self.assertNotIn("sources", state)
        self.assertEqual(state["story"]["status"], "paused")
        self.assertEqual(state["story"]["next_run_at"], 1789776000)

    def test_missing_outcome_is_not_empty_success(self):
        with mock.patch.object(collector, "run_actor", return_value=([], {})):
            with self.assertRaisesRegex(RuntimeError, "omitted scan outcome"):
                collector.collect_stories({}, [self.source], "secret", self.limits, 5, self.now, lambda: None, set())

    def test_partial_scan_leaves_unattempted_due(self):
        second = {**self.source, "id": "ig_story_second", "username": "zsecond"}
        state = {}
        with mock.patch.object(collector, "run_actor", return_value=([], {"outcome": "ok", "granted_targets": 1})):
            collector.collect_stories(state, [self.source, second], "secret", self.limits, 5, self.now, lambda: None, set())
        self.assertIn(self.source["id"], state["sources"])
        self.assertNotIn(second["id"], state["sources"])
        self.assertEqual(collector.select_due([self.source, second], state, "apify_stories", self.now, 10), [second])

    def test_failed_target_not_success(self):
        state = {}
        outcome = {"outcome": "ok", "granted_targets": 1, "failed_targets": ["test"]}
        with mock.patch.object(collector, "run_actor", return_value=([], outcome)):
            collector.collect_stories(state, [self.source], "secret", self.limits, 5, self.now, lambda: None, set())
        self.assertNotIn("last_success_at", state["sources"][self.source["id"]])
        self.assertEqual(state["story"]["status"], "degraded")

    def test_result_cap_does_not_mark_later_targets_empty(self):
        second = {**self.source, "id": "ig_story_second", "username": "zsecond"}
        state = {}
        items = [{"username": "test", "story_pk": str(i), "taken_at": collector.iso(self.now - 60),
                  "expiring_at": collector.iso(self.now + 100)} for i in range(10)]
        with mock.patch.object(collector, "run_actor", return_value=(items, {"outcome": "ok", "granted_targets": 2})), mock.patch.object(collector, "cache_story_media", return_value="/assets/feed-images/test.webp"):
            collector.collect_stories(state, [self.source, second], "secret", self.limits, 5, self.now, lambda: None, set())
        self.assertEqual(state["story"]["scanned"], 1)
        self.assertNotIn(second["id"], state["sources"])

    def test_story_requires_current_public_media(self):
        item = {"story_pk": "123", "taken_at": collector.iso(self.now - 60),
                "expiring_at": collector.iso(self.now + 80000)}
        with mock.patch.object(collector, "cache_story_media", return_value="/assets/feed-images/test.webp"):
            post = collector.story_row(self.source, item, self.now)
            self.assertEqual(post["story_provider"], "apify_stories")
            self.assertEqual(post["key"], "ig_story_test:123")
            self.assertTrue(post["story_expires_at"])
            self.assertIsNone(collector.story_row(self.source, {**item, "is_private": True}, self.now))
            self.assertIsNone(collector.story_row(self.source, {**item, "expiring_at": collector.iso(self.now - 1)}, self.now))

    def test_media_failure_is_reported(self):
        state = {}
        item = {"username": "test", "story_pk": "123", "taken_at": collector.iso(self.now - 60), "expiring_at": collector.iso(self.now + 100)}
        with mock.patch.object(collector, "run_actor", return_value=([item], {"outcome": "ok", "granted_targets": 1})), mock.patch.object(collector, "cache_story_media", side_effect=ValueError("failed")):
            collector.collect_stories(state, [self.source], "secret", self.limits, 5, self.now, lambda: None, set())
        self.assertEqual(state["story"]["status"], "degraded")
        self.assertNotIn("last_success_at", state["sources"][self.source["id"]])

    def test_paid_post_reserves_before_request(self):
        state = {}; saved = []
        with mock.patch.object(collector, "api", side_effect=RuntimeError("connection lost")):
            with self.assertRaises(RuntimeError):
                collector.run_actor(state, "secret", collector.STORY_ACTOR, {}, 10, .05, self.now,
                                    lambda: saved.append(bool(state.get("runs"))))
        self.assertEqual(saved, [True])
        self.assertEqual(state["runs"][0]["reserved_results"], 10)

    def test_profile_refusal_does_not_block_stories(self):
        source = {**self.source, "id": "ig_test", "provider": "instagram_public"}
        state = {"story": {"status": "ok", "next_run_at": 123}}
        with mock.patch.object(collector, "fetch_public_profile", side_effect=ValueError("refused")), mock.patch.object(collector, "run_actor") as actor:
            collector.collect_profiles(state, [source], "", {}, 5, self.now, lambda: None, set())
            actor.assert_not_called()
        self.assertEqual(state["story"], {"status": "ok", "next_run_at": 123})
        self.assertEqual(state["profile"]["status"], "paused")
        self.assertGreater(state["profile"]["direct_cooldown_until"], self.now)

    def test_budget_uses_reservation_when_billing_lags(self):
        state = {"runs": [{"at": collector.iso(self.now), "reserved_usd": .2, "cost_usd": .01}]}
        self.assertEqual(collector.daily_budget(state, self.limits, 5, self.now), 0)

    def test_cache_bypasses_authenticated_helpers_and_expiry(self):
        expiry = collector.iso()
        state = {"sources": {self.source["id"]: {"posts": [{"story_expires_at": expiry}]}}}
        with mock.patch.object(watchdog, "load_json", return_value=state), mock.patch.object(watchdog, "fetch_rss") as rss:
            self.assertEqual(watchdog.fetch_source(self.source, None), [])
            rss.assert_not_called()
        self.assertEqual(watchdog.source_delay_secs(self.source, None, None), 0)

    def test_cached_previews_survive_provider_expiry_until_48_hours(self):
        now = dt.datetime.now(dt.timezone.utc).timestamp()
        recent = {'key': 'recent', 'posted_at': collector.iso(now - 30 * 3600),
                  'story_expires_at': collector.iso(now - 6 * 3600)}
        old = {'key': 'old', 'posted_at': collector.iso(now - 49 * 3600),
               'story_expires_at': collector.iso(now - 25 * 3600)}
        state = {'sources': {self.source['id']: {'posts': [recent, old]}}}
        collector.record_source(state, self.source, [], now, backend='apify_stories')
        self.assertEqual(state['sources'][self.source['id']]['posts'], [recent])
        with mock.patch.object(watchdog, 'load_json', return_value=state), mock.patch.object(watchdog, 'fetch_rss') as rss:
            self.assertEqual(watchdog.cached_instagram_posts(self.source), [recent])
            rss.assert_not_called()

    def test_status_never_labels_unchecked_sources_healthy(self):
        now = dt.datetime.fromtimestamp(self.now, dt.timezone.utc)
        result = status.public_instagram_component({"story": {"status": "ok"}}, [self.source], now)
        self.assertEqual(result["stories"]["status"], "degraded")
        self.assertEqual(result["stories"]["checkedSources24h"], 0)
        self.assertEqual(result["stories"]["totalSources"], 1)

    def test_small_budget_allocates_at_least_one_result_per_target(self):
        targets, results, budget = collector.story_plan(.029629, 10, 0)
        self.assertEqual((targets, results), (5, 5))
        self.assertLessEqual(budget, .029629)
        self.assertEqual(collector.story_plan(.05, 10, 39), (1, 1, .0095))

    def test_explicit_target_bypasses_delays_but_not_scope_or_pool_budget(self):
        other = {**self.source, "id": "ig_story_other", "username": "other"}
        original = {"next_due_at": self.now + 99999, "last_attempt_at": self.now - 100}
        state = {"_use_pool": True, "story": {"next_run_at": self.now + 9000},
                 "sources": {self.source["id"]: copy.deepcopy(original), other["id"]: copy.deepcopy(original)}}
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=[{"maxRunBudgetUsd": .0095, "resultsLeft": 40}]), mock.patch.object(
                collector, "run_actor", return_value=([], {"outcome": "ok", "granted_targets": 1})) as actor:
            collector.collect_stories(state, [self.source, other], "", {}, 0, self.now, lambda: None, {"test"})
        self.assertEqual(actor.call_args.args[3]["usernames"], ["test"])
        self.assertEqual(actor.call_args.args[5], .0095)
        self.assertEqual(state["sources"][other["id"]], original)
        self.assertEqual(state["story"]["next_run_at"], self.now + 9000)
        self.assertEqual(state["sources"][self.source["id"]]["interval_hours"], 12)
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=[]), mock.patch.object(collector, "run_actor") as actor:
            collector.collect_stories(state, [self.source], "", {}, 0, self.now + 10, lambda: None, {"test"})
        actor.assert_not_called()
        self.assertEqual(state["story"]["reason"], "credit_budget")

    def test_scheduled_collection_retains_global_delay(self):
        state = {"story": {"next_run_at": self.now + 100}}
        with mock.patch.object(collector, "run_actor") as actor:
            collector.collect_stories(state, [self.source], "secret", self.limits, 5, self.now, lambda: None, set())
        actor.assert_not_called()

    def test_legacy_weekly_story_checks_become_due_without_losing_error_backoff(self):
        state = {"sources": {self.source["id"]: {"status": "ok", "interval_hours": 168,
                 "next_due_at": self.now + 6 * 86400, "last_attempt_at": self.now - 86400}}}
        self.assertEqual(collector.select_due([self.source], state, "apify_stories", self.now, 10), [self.source])
        state["sources"][self.source["id"]]["status"] = "error"
        self.assertEqual(collector.select_due([self.source], state, "apify_stories", self.now, 10), [])

    def test_story_queue_balances_known_refresh_with_unscanned_sources(self):
        fresh = [{**self.source, "id": f"new{i}", "username": f"new{i}"} for i in range(12)]
        state = {"sources": {self.source["id"]: {"status": "ok", "next_due_at": 0,
                 "last_success_at": collector.iso(self.now - 86400), "last_attempt_at": self.now - 86400}}}
        selected = collector.select_due(fresh + [self.source], state, "apify_stories", self.now, 5)
        self.assertEqual(selected[0], self.source)
        self.assertEqual(len(selected), 5)
        self.assertEqual(len([s for s in selected if s["id"].startswith("new")]), 4)

    def test_unscanned_profiles_with_event_history_are_checked_first(self):
        profiles = [{"id": f"ig_{name}", "username": name, "name": name.title(), "provider": "instagram_public"}
                    for name in ("alpha", "beta", "toshi")]
        state = {"_affinity": {"toshi": 3}}
        selected = collector.select_due(profiles, state, "instagram_public", self.now, 2)
        self.assertEqual([s["username"] for s in selected], ["toshi", "alpha"])

    def test_event_affinity_counts_event_posts_by_source_name(self):
        import tempfile
        from source_priority import event_affinity
        rows = [{"source_name": "Toshi", "llm_categories": ["events"]},
                {"source_name": "toshi", "llm_categories": ["events", "news"]},
                {"source_name": "Toshi", "llm_categories": ["news"]},
                {"source_name": "Other", "text": "events"}]
        with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as handle:
            handle.write("\n".join(__import__("json").dumps(row) for row in rows) + "\nnot json \"events\"\n")
        self.assertEqual(event_affinity(Path(handle.name)), {"toshi": 2})
        self.assertEqual(event_affinity(Path(handle.name + ".missing")), {})

    def test_known_active_sources_outrank_older_inactive_checks_with_exploration(self):
        sources = [{**self.source, "id": f"s{i}", "username": f"s{i}"} for i in range(8)]
        state = {"sources": {s["id"]: {"last_success_at": collector.iso(self.now - 86400),
                 "last_attempt_at": self.now - (8-i)*86400, "next_due_at": 0}
                 for i, s in enumerate(sources[:6])},
                 "history": {"s5": [{"posted_at": collector.iso(self.now - 3600)}],
                             "s4": [{"posted_at": collector.iso(self.now - 7200)}]}}
        selected = collector.select_due(sources, state, "apify_stories", self.now, 4)
        self.assertEqual([s["id"] for s in selected[:2]], ["s4", "s5"])
        self.assertIn(selected[3]["id"], ["s6", "s7"])
        exploratory_slot = self.now + 9*3600
        self.assertIn(collector.select_due(sources, state, "apify_stories", exploratory_slot, 1)[0]["id"], ["s6", "s7"])

    def test_pool_story_plan_does_not_mix_account_money_and_result_slots(self):
        options = [{"maxRunBudgetUsd": .05, "resultsLeft": 1},
                   {"maxRunBudgetUsd": .009, "resultsLeft": 40}]
        self.assertEqual(collector.pool_story_plan(options, 10), (1, 1, .0095))
        state = {"_use_pool": True}
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=options), mock.patch.object(
                collector, "run_actor", return_value=([], {"outcome": "ok", "granted_targets": 1})) as actor:
            collector.collect_stories(state, [self.source], "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(actor.call_args.args[4:6], (1, .0095))

    def test_multi_account_capacity_runs_bounded_distinct_batches_and_rechecks_pool(self):
        options = [{"maxRunBudgetUsd": .2, "resultsLeft": 40} for _ in range(4)]
        sources = [{**self.source, "id": f"s{i}", "username": f"s{i:02}"} for i in range(25)]
        state = {"_use_pool": True}
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=options) as pool, mock.patch.object(
                collector, "run_actor", return_value=([], {"outcome": "ok", "granted_targets": 10})) as actor:
            collector.collect_stories(state, sources, "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(actor.call_count, 2)
        self.assertEqual(pool.call_count, 2)
        usernames = [name for call in actor.call_args_list for name in call.args[3]["usernames"]]
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertEqual(collector.paced_story_runs(options*100), 8)
        # Revocation/capacity loss before the second batch never borrows old quota.
        with mock.patch.object(collector.apify_pool, "story_run_options", side_effect=[options, []]), mock.patch.object(
                collector, "run_actor", return_value=([], {"outcome": "ok", "granted_targets": 10})) as actor:
            collector.collect_stories({"_use_pool": True}, sources, "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(actor.call_count, 1)

    def test_multi_run_unknown_or_denied_outcome_does_not_retry(self):
        options = [{"maxRunBudgetUsd": .2, "resultsLeft": 40} for _ in range(4)]
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=options), mock.patch.object(
                collector, "run_actor", side_effect=RuntimeError("Unknown provider outcome")) as actor:
            with self.assertRaises(RuntimeError):
                collector.collect_stories({"_use_pool": True}, [self.source], "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(actor.call_count, 1)
        with mock.patch.object(collector.apify_pool, "story_run_options", return_value=options), mock.patch.object(
                collector, "run_actor", return_value=([], {"outcome": "denied", "reason": "free_capacity_exhausted"})) as actor:
            collector.collect_stories({"_use_pool": True}, [self.source], "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(actor.call_count, 1)

    def test_free_tier_denial_keeps_reserved_cap_when_billing_reports_zero(self):
        state = {}
        responses = [{"data": {"id": "verified-run", "status": "SUCCEEDED", "usageTotalUsd": 0,
                              "defaultDatasetId": "dataset", "defaultKeyValueStoreId": "output"}},
                     [], {"outcome": "denied", "reason": "free_capacity_exhausted"}]
        with mock.patch.object(collector, "api", side_effect=responses):
            collector.run_actor(state, "test-token", collector.STORY_ACTOR, {"usernames": ["test"]},
                                1, .0095, self.now, lambda: None)
        self.assertEqual(state["runs"][0]["reserved_usd"], .0095)
        self.assertEqual(state["runs"][0]["reserved_results"], 1)
        self.assertEqual(state["runs"][0]["cost_usd"], 0)

    def test_completed_run_import_caches_media_without_starting_an_actor(self):
        state = {"sources": {"other": {"next_due_at": 123}}, "runs": [{"id": "verified", "status": "SUCCEEDED"}]}
        item = {"username": "test", "story_pk": "123", "taken_at": collector.iso(self.now - 60),
                "expiring_at": collector.iso(self.now + 80000)}
        with mock.patch.object(collector, "cache_story_media", return_value="/assets/feed-images/story.webp"), mock.patch.object(collector, "run_actor") as actor:
            collector.ingest_story_results(state, [self.source], [item], {"outcome": "ok", "granted_targets": 1}, 5, self.now, lambda: None)
            collector.ingest_story_results(state, [self.source], [item], {"outcome": "ok", "granted_targets": 1}, 5, self.now, lambda: None)
        actor.assert_not_called()
        self.assertEqual(len(state["sources"][self.source["id"]]["posts"]), 1)
        self.assertEqual(state["sources"][self.source["id"]]["posts"][0]["image_url"], "/assets/feed-images/story.webp")
        self.assertEqual(state["sources"]["other"], {"next_due_at": 123})
        self.assertEqual(len(state["runs"]), 1)


    def test_profile_posts_derive_profile_url_when_source_omits_it(self):
        source = {k: v for k, v in self.source.items() if k != "source_profile_url"}
        posts = collector.normalize_profile(source, {"latestPosts": [{"id": "1", "shortCode": "ABC", "timestamp": collector.iso(self.now)}]})
        self.assertEqual(posts[0]["source_profile_url"], "https://www.instagram.com/test/")

    def test_existing_id_is_preserved_for_profile_dedup(self):
        posts = collector.normalize_profile(self.source, {"latestPosts": [{"id": "123", "shortCode": "ABC", "timestamp": collector.iso(self.now), "isPinned": True}]})
        self.assertEqual(posts[0]["key"], "ig_story_test:123")
        self.assertTrue(posts[0]["is_pinned"])


if __name__ == "__main__":
    unittest.main()
