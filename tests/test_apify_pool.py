import concurrent.futures
import datetime as dt
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import apify_pool as pool
import apify_facebook_fetcher as facebook
import instagram_public_fetcher as instagram

_real_token_accounts = pool.token_accounts
_real_verify_actor_cap = pool.verify_actor_cap


class ApifyPoolTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "pool.json"
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(pool, "verify_actor_cap").start()
        mock.patch.object(pool, "STATE_PATH", self.path).start()
        self.now = dt.datetime(2026, 9, 23, 12, tzinfo=dt.timezone.utc).timestamp()
        self.account = {"key": "owner-key", "token": "never-output-this-token", "community": False, "budgetUsd": 1}
        self.accounts = [self.account]
        mock.patch.object(pool, "token_accounts", side_effect=lambda: self.accounts).start()
        self.quota = {"accountId": "provider-id-hash", "checkedAt": self.now, "available": True,
                      "cycleStart": "2026-09-01T00:00:00Z", "cycleEnd": "2026-09-24T00:00:00Z",
                      "limitUsd": 4, "usedUsd": 0, "remainingUsd": 4}
        with pool._locked() as state:
            state["accounts"][self.account["key"]] = {"quota": self.quota}

    def test_public_view_never_exposes_token_or_provider_identity(self):
        result = pool.pool_status(now=self.now)
        text = json.dumps(result)
        self.assertNotIn(self.account["token"], text)
        self.assertNotIn("owner-key", text)
        self.assertNotIn("provider-id-hash", text)
        self.assertNotIn("accounts", result)
        self.assertEqual(result["remainingUsd"], 1)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_unknown_stale_and_failed_verification_fail_closed(self):
        self.assertEqual(pool.pool_status(now=self.now + 3601)["remainingUsd"], None)
        with self.assertRaisesRegex(RuntimeError, "paused"):
            pool.reserve_run("facebook", .01, now=self.now + 3601)
        with pool._locked() as state:
            state["accounts"]["owner-key"]["quota"] = {"available": False, "attemptedAt": self.now}
        result = pool.pool_status(now=self.now)
        self.assertFalse(result["available"])
        self.assertIsNone(result["remainingUsd"])
        self.assertEqual(result["unknownAccountCount"], 1)
        self.assertFalse(result["exhausted"])

    def test_atomic_concurrent_reservations_respect_daily_share(self):
        def reserve(_):
            try:
                return pool.reserve_run("facebook", .1, now=self.now)["id"]
            except RuntimeError:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            rows = list(executor.map(reserve, range(20)))
        # At noon the two idle platforms still hold half of their thirds.
        self.assertEqual(sum(bool(row) for row in rows), 6)
        self.assertEqual(len(set(filter(None, rows))), 6)
        self.assertAlmostEqual(sum(r["reservedUsd"] for r in pool._read()["runs"]), .6)
        self.assertLess(pool.available_budget("facebook", now=self.now), .1)
        self.assertGreater(pool.available_budget("instagram", now=self.now), 0)

    def test_unknown_run_and_lagging_billing_do_not_restore_budget(self):
        reservation = pool.reserve_run("facebook", .2, now=self.now)
        before = pool.available_budget("facebook", now=self.now)
        pool.finish_run(reservation["id"], status="UNKNOWN", now=self.now)
        self.assertEqual(pool.available_budget("facebook", now=self.now), before)
        pool.finish_run(reservation["id"], status="SUCCEEDED", actual_cost_usd=.001, now=self.now)
        self.assertEqual(pool.available_budget("facebook", now=self.now), before)
        self.assertEqual(pool._read()["runs"][0]["reportedCostUsd"], .001)
        self.assertEqual(pool._read()["runs"][0]["reservedUsd"], .2)

    def test_story_options_pair_credit_and_slots_and_reserve_rechecks(self):
        with pool._locked() as state:
            state["runs"].append({"id": "earlier", "account": "owner-key", "billingAccount": "provider-id-hash",
                                  "platform": "instagram_stories", "at": self.now, "reservedUsd": .02,
                                  "reservedResults": 37, "status": "UNKNOWN"})
        options = pool.story_run_options(now=self.now)
        self.assertEqual(len(options), 1)
        self.assertEqual(options[0]["resultsLeft"], 3)
        self.assertAlmostEqual(options[0]["maxRunBudgetUsd"], .646666)
        # The three remaining slots can fund a real smaller run; ten cannot.
        with self.assertRaises(RuntimeError):
            pool.reserve_run("instagram_stories", .05, result_count=10, now=self.now)
        pool.reserve_run("instagram_stories", .0185, source_count=3, result_count=3, now=self.now)
        self.assertEqual(pool.story_run_options(now=self.now), [])
        with self.assertRaises(RuntimeError):
            pool.reserve_run("instagram_stories", .0095, result_count=1, now=self.now)

    def test_story_options_do_not_mix_accounts_or_duplicate_aliases(self):
        self.accounts.extend([
            {**self.account, "key": "alias", "token": "alias-secret"},
            {**self.account, "key": "second", "token": "second-secret", "budgetUsd": .08},
        ])
        with pool._locked() as state:
            state["accounts"]["alias"] = {"quota": self.quota}
            state["accounts"]["second"] = {"quota": {**self.quota, "accountId": "second-provider"}}
            state["runs"].append({"id": "past", "account": "owner-key", "billingAccount": "provider-id-hash",
                                  "platform": "instagram_stories", "at": self.now, "reservedUsd": .02,
                                  "reservedResults": 39, "status": "UNKNOWN"})
        options = pool.story_run_options(now=self.now)
        self.assertEqual(options, [{"maxRunBudgetUsd": .053333, "resultsLeft": 40},
                                   {"maxRunBudgetUsd": .646666, "resultsLeft": 1}])
        serialized = json.dumps(options)
        for secret in ["owner-key", "alias", "second-provider", "secret"]:
            self.assertNotIn(secret, serialized)
        self.assertEqual(pool.story_run_options(now=self.now + 3601), [])

    def test_corrupt_ledger_never_resets_capacity(self):
        self.path.write_text("not-json")
        with self.assertRaisesRegex(RuntimeError, "unreadable"):
            pool.reserve_run("facebook", .01, now=self.now)
        self.assertEqual(self.path.read_text(), "not-json")

    def test_duplicate_provider_tokens_do_not_double_count_quota(self):
        self.accounts.append({**self.account, "key": "other-key", "token": "another-secret"})
        with pool._locked() as state:
            state["accounts"]["other-key"] = {"quota": self.quota}
        result = pool.pool_status(now=self.now)
        self.assertEqual(result["accountCount"], 2)
        self.assertEqual(result["verifiedAccountCount"], 1)
        self.assertEqual(result["remainingUsd"], 1)
        pool.reserve_run("facebook", .6, now=self.now)
        with self.assertRaises(RuntimeError):
            pool.reserve_run("facebook", .1, now=self.now)

    def test_registration_quota_changes_capacity_without_network_refresh(self):
        account = {"key": "community-key", "token": "community-token", "id": "contribution-id", "community": True,
                   "budgetRemainingUsd": 2, "verifiedQuota": {**self.quota, "accountId": "second-provider"}}
        sources = [{"type": "facebook_page_posts", "enabled": True} for _ in range(100)]
        before = pool.crawl_schedule_snapshot(now=self.now, sources=sources)
        self.accounts.append(account)
        after = pool.crawl_schedule_snapshot(now=self.now, sources=sources)
        self.assertLess(after["platforms"]["facebook"]["estimatedDays"], before["platforms"]["facebook"]["estimatedDays"])
        self.assertEqual(after["pool"]["remainingUsd"], 3)

    def test_contributor_denial_or_revocation_blocks_reservation(self):
        self.accounts[:] = [{"key": "community-key", "token": "community-token", "id": "contribution-id", "community": True,
                            "budgetRemainingUsd": 1, "verifiedQuota": self.quota}]
        provider = mock.Mock()
        provider.reserve_budget.return_value = False
        with mock.patch.object(pool, "_community", return_value=provider):
            with self.assertRaises(RuntimeError):
                pool.reserve_run("facebook", .1, now=self.now)
        self.assertEqual(pool._read()["runs"], [])

    def test_story_allowance_is_per_account_and_reserved_before_run(self):
        self.account["budgetUsd"] = 4
        for _ in range(4):
            pool.reserve_run("instagram_stories", .05, result_count=10, now=self.now)
        with self.assertRaises(RuntimeError):
            pool.reserve_run("instagram_stories", .01, result_count=1, now=self.now)
        self.assertEqual(pool.available_budget("instagram_stories", now=self.now), 0)

    def test_facebook_authorization_uses_header_and_errors_are_sanitized(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{}'
        with mock.patch.object(pool, "open_request", return_value=response) as opener:
            facebook.apify_request("GET", "/users/me/limits", self.account["token"])
            request = opener.call_args.args[0]
            self.assertNotIn(self.account["token"], request.full_url)
            self.assertEqual(request.get_header("Authorization"), "Bearer " + self.account["token"])
        import urllib.error
        error = urllib.error.HTTPError("https://api.apify.com/", 401, "rejected", {}, io.BytesIO(self.account["token"].encode()))
        self.addCleanup(error.close)
        with mock.patch.object(pool, "open_request", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "^Apify HTTP 401$"):
                facebook.apify_request("GET", "/users/me/limits", self.account["token"])

    def test_instagram_pool_reserves_before_paid_post_and_keeps_unknown(self):
        state = {"_use_pool": True}
        events = []
        with mock.patch.object(pool, "reserve_run", side_effect=lambda *a, **kw: events.append("reserve") or {"id": "r", "token": "s"}), \
             mock.patch.object(instagram, "api", side_effect=lambda *a, **kw: events.append("post") or (_ for _ in ()).throw(RuntimeError("lost"))):
            with self.assertRaises(RuntimeError):
                instagram.run_actor(state, "", instagram.PROFILE_ACTOR, {"usernames": ["test"]}, 1, .006,
                                    self.now, lambda: events.append("save"))
        self.assertEqual(events, ["reserve", "save", "post"])
        self.assertEqual(state["runs"][0]["reserved_usd"], .006)

    def test_disabled_direct_path_never_calls_instagram(self):
        state = {"_use_pool": True}
        source = {"id": "ig_test", "username": "test", "provider": "instagram_public", "name": "Test"}
        with mock.patch.dict(os.environ, {"HARMONICA_INSTAGRAM_PUBLIC_DIRECT": "0"}), \
             mock.patch.object(instagram.ig_public_host, "wait_turn") as turn, \
             mock.patch.object(pool, "available_budget", return_value=0), \
             mock.patch.object(instagram, "fetch_public_profile") as direct, \
             mock.patch.object(instagram, "run_actor") as actor:
            instagram.collect_profiles_pool(state, [source], "", {}, 0, self.now, lambda: None, set())
        direct.assert_not_called()
        turn.assert_not_called()
        actor.assert_not_called()
        self.assertEqual(state["profile"]["reason"], "pool_budget_pacing")
        self.assertEqual(state["profile"]["scanned"], 0)

    def test_real_community_budget_is_settled_conservatively_and_revoked(self):
        import community
        community_path = str(Path(self.directory.name) / "community")
        with mock.patch.dict(os.environ, {"HARMONICA_COMMUNITY_STATE": community_path}), \
             mock.patch.object(community, "verify_token", return_value=self.quota):
            account = community.register("test-owner", {"name": "Test", "token": "apify_token_012345678901234567890",
                                                        "budgetUsd": .4, "consent": True})
            with mock.patch.object(pool, "token_accounts", side_effect=lambda: [
                    {**a, "key": "contributed-key", "community": True} for a in community.active_tokens()]):
                reservation = pool.reserve_run("facebook", .1, now=self.now)
                row = community.owner_contributions("test-owner")[0]
                self.assertAlmostEqual(row["reservedUsd"], .1)
                self.assertAlmostEqual(row["budgetRemainingUsd"], .3)
                pool.finish_run(reservation["id"], status="SUCCEEDED", actual_cost_usd=.001, now=self.now)
                row = community.owner_contributions("test-owner")[0]
                self.assertAlmostEqual(row["spentUsd"], .1)
                self.assertEqual(row["reservedUsd"], 0)
                self.assertTrue(community.revoke("test-owner", account["id"]))
                self.assertEqual(pool.pool_status(now=self.now)["accountCount"], 0)
                with self.assertRaises(RuntimeError):
                    pool.reserve_run("facebook", .01, now=self.now)

    def test_facebook_main_uses_reserved_contribution_token_and_actor_cap(self):
        directory = Path(self.directory.name)
        config = directory / "sources.json"
        config.write_text(json.dumps({"sources": [{"id": "fb_test", "type": "facebook_page_posts", "page": "test", "name": "Test"}]}))
        args = ["collector", "--run", "--selection-mode", "round-robin", "--config", str(config),
                "--ledger", str(directory / "facebook.json"), "--inbox", str(directory / "inbox.jsonl"),
                "--errors", str(directory / "errors.jsonl")]
        status = pool.pool_status(now=self.now)
        with mock.patch.object(sys, "argv", args), mock.patch("run_pipeline.load_dotenv"), \
             mock.patch.object(pool, "pool_status", return_value=status), \
             mock.patch.object(pool, "reserve_run", return_value={"id": "r", "token": "contributed-secret"}) as reserve, \
             mock.patch.object(pool, "finish_run") as finish, \
             mock.patch.object(facebook, "run_actor", return_value=({"id": "actor", "status": "SUCCEEDED", "usageTotalUsd": .01}, [])) as actor, \
             mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(facebook.main(), 0)
            self.assertNotIn("contributed-secret", output.getvalue())
            self.assertEqual(actor.call_args.args[0], "contributed-secret")
            self.assertEqual(actor.call_args.kwargs["max_total_charge_usd"], reserve.call_args.args[1])
            self.assertEqual(finish.call_args.args[0], "r")

    def test_facebook_mocked_api_writes_sink_after_real_pool_reservation(self):
        directory = Path(self.directory.name)
        config = directory / "sources.json"
        sources = [{"id": "fb_" + name, "type": "facebook_page_posts", "page": name, "name": name} for name in ("test", "second")]
        config.write_text(json.dumps({"sources": sources}))
        inbox = directory / "inbox.jsonl"
        ledger = directory / "facebook.json"
        args = ["collector", "--run", "--selection-mode", "round-robin", "--config", str(config),
                "--ledger", str(ledger), "--inbox", str(inbox), "--errors", str(directory / "errors.jsonl")]
        def remote(method, path, token, **kwargs):
            self.assertEqual(token, self.account["token"])
            self.assertEqual(len(pool._read()["runs"]), 1)
            if method == "POST":
                self.assertEqual(pool._read()["runs"][0]["reservedUsd"], kwargs["query"]["maxTotalChargeUsd"])
                return {"data": {"id": "test-run", "status": "SUCCEEDED", "defaultDatasetId": "test-dataset", "usageTotalUsd": .001}}
            return [{"postId": "12345", "url": "https://www.facebook.com/test/posts/12345", "text": "Verified fixture concert",
                     "time": dt.datetime.fromtimestamp(self.now, dt.timezone.utc).isoformat()}]
        with mock.patch.object(sys, "argv", args), mock.patch("run_pipeline.load_dotenv"), \
             mock.patch.object(pool.time, "time", return_value=self.now), \
             mock.patch.object(pool, "refresh_quota", side_effect=lambda **kw: pool.pool_status(now=self.now)), \
             mock.patch.object(facebook, "apify_request", side_effect=remote), \
             mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(facebook.main(), 0)
        rows = [json.loads(line) for line in inbox.read_text().splitlines()]
        self.assertEqual(rows[0]["source_id"], "fb_test")
        self.assertEqual(rows[0]["text"], "Verified fixture concert")
        records = json.loads(ledger.read_text())
        stats = facebook.source_run_stats(records)
        self.assertEqual(stats["fb_test"]["success_count"], 1)
        self.assertEqual(stats["fb_second"]["success_count"], 0)
        self.assertEqual(pool._read()["runs"][0]["actorRunId"], "test-run")
        self.assertGreater(pool._read()["runs"][0]["reservedUsd"], .001)
        self.assertNotIn(self.account["token"], output.getvalue() + inbox.read_text() + self.path.read_text())

    def test_instagram_empty_result_does_not_claim_source_success(self):
        source = {"id": "ig_test", "username": "test", "provider": "instagram_public", "name": "Test",
                  "source_profile_url": "https://www.instagram.com/test/"}
        state = {"_use_pool": True}
        def remote(method, path, token, **kwargs):
            self.assertEqual(token, self.account["token"])
            self.assertTrue(pool._read()["runs"])
            if method == "POST":
                return {"data": {"id": "ig-run", "status": "SUCCEEDED", "defaultDatasetId": "ig-data", "usageTotalUsd": 0}}
            return []
        with mock.patch.dict(os.environ, {"HARMONICA_INSTAGRAM_PUBLIC_DIRECT": "0"}), \
             mock.patch.object(pool.time, "time", return_value=self.now), mock.patch.object(instagram, "api", side_effect=remote):
            instagram.collect_profiles_pool(state, [source], "", {}, 0, self.now, lambda: None, set())
        self.assertEqual(state["profile"]["successful"], 0)
        self.assertNotIn("last_success_at", state["sources"]["ig_test"])
        self.assertGreater(pool._read()["runs"][0]["reservedUsd"], 0)

    def test_current_scale_budget_still_plans_affordable_batches(self):
        facebook_budget, instagram_budget = .059652, .029826
        count = facebook.max_sources_for_budget(facebook_budget, 5, 24)
        self.assertEqual(count, 2)
        self.assertLessEqual(facebook.estimate_max_charge_usd(5, count), facebook_budget)
        self.assertEqual(int(instagram_budget // .006), 4)
        targets, results, budget = instagram.story_plan(instagram_budget, 179, 0)
        self.assertEqual((targets, results), (5, 5))
        self.assertLessEqual(budget, instagram_budget)
        self.assertEqual(facebook.run_cost({"usage_total_usd": .001, "reserved_usd": .056}), .056)

    def test_registered_token_never_reappears_as_owner_after_revocation(self):
        import hashlib
        token = "owner-configured-token"
        provider = mock.Mock()
        provider.registered_token_hashes.return_value = {hashlib.sha256(token.encode()).hexdigest()}
        provider.active_tokens.return_value = []
        with mock.patch.dict(os.environ, {"APIFY_TOKEN": token}, clear=True), mock.patch.object(pool, "_community", return_value=provider):
            self.assertEqual(_real_token_accounts(), [])
            provider.active_tokens.return_value = [{"id": "community", "token": token, "budgetRemainingUsd": .1}]
            result = _real_token_accounts()
            self.assertEqual(len(result), 1)
            self.assertTrue(result[0]["community"])

    def test_pricing_guard_rejects_non_capped_model_and_future_price(self):
        def response(prices):
            item = mock.MagicMock()
            item.__enter__.return_value.read.return_value = json.dumps({"data": {"pricingInfos": prices}}).encode()
            return item
        price = {"startedAt": "2026-01-01T00:00:00Z", "pricingModel": "PAY_PER_EVENT", "minimalMaxTotalChargeUsd": .01}
        with mock.patch.object(pool, "open_request", return_value=response([price])):
            _real_verify_actor_cap(instagram.PROFILE_ACTOR, .02, now=self.now)
            with self.assertRaisesRegex(RuntimeError, "authorized charge cap"):
                _real_verify_actor_cap(instagram.PROFILE_ACTOR, .001, now=self.now)
        with mock.patch.object(pool, "open_request", return_value=response([{**price, "pricingModel": "PRICE_PER_DATASET_ITEM"}])):
            with self.assertRaises(RuntimeError):
                _real_verify_actor_cap(instagram.PROFILE_ACTOR, .02, now=self.now)
        with mock.patch.object(pool, "open_request", return_value=response([{**price, "startedAt": "2030-01-01T00:00:00Z"}])):
            with self.assertRaises(RuntimeError):
                _real_verify_actor_cap(instagram.PROFILE_ACTOR, .02, now=self.now)

    def test_tiny_unusable_contribution_does_not_invent_frequency_improvement(self):
        sources = [{"type": "facebook_page_posts"}]
        before = pool.crawl_schedule_snapshot(now=self.now, sources=sources)
        self.accounts.append({"key": "tiny", "token": "tiny-token", "community": True, "id": "tiny-id",
                              "budgetRemainingUsd": .01, "verifiedQuota": {**self.quota, "accountId": "tiny-provider"}})
        after = pool.crawl_schedule_snapshot(now=self.now, sources=sources)
        self.assertEqual(before["platforms"]["facebook"]["estimatedDays"], after["platforms"]["facebook"]["estimatedDays"])
        self.assertEqual(pool._daily_source_capacity("facebook", .03), 0)
        self.assertEqual(pool._daily_source_capacity("instagram", .005), 0)
        self.assertEqual(pool._daily_source_capacity("instagram_stories", .009), 0)

    def test_fixed_impact_timestamp_accepts_newly_verified_quota_only_with_bounded_skew(self):
        self.accounts[:] = [{"key": "community", "token": "token", "community": True, "id": "id", "budgetRemainingUsd": 1,
                            "verifiedQuota": {**self.quota, "checkedAt": self.now + 30}}]
        self.assertTrue(pool.pool_status(now=self.now)["available"])
        self.accounts[0]["verifiedQuota"]["checkedAt"] = self.now + 61
        self.assertFalse(pool.pool_status(now=self.now)["available"])

    def test_latest_provider_balance_applies_to_other_credential(self):
        self.accounts.append({**self.account, "key": "new-key", "token": "new-token",
                              "verifiedQuota": {**self.quota, "checkedAt": self.now + 1, "remainingUsd": .01, "usedUsd": 3.99}})
        self.assertEqual(pool.pool_status(now=self.now)["remainingUsd"], 0)
        with self.assertRaises(RuntimeError):
            pool.reserve_run("facebook", .01, now=self.now)

    def test_unexpected_provider_overrun_is_not_hidden_from_accounting(self):
        reservation = pool.reserve_run("facebook", .1, now=self.now)
        pool.finish_run(reservation["id"], status="SUCCEEDED", actual_cost_usd=.3, now=self.now)
        row = pool._read()["runs"][0]
        self.assertTrue(row["budgetOverrun"])
        self.assertEqual(row["reservedUsd"], .3)
        self.assertAlmostEqual(pool.available_budget("facebook", now=self.now), 1 - .3 - 1 / 3, places=5)

    def test_platforms_get_equal_thirds_at_day_start(self):
        start = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc).timestamp()
        with pool._locked() as state:
            state["accounts"]["owner-key"]["quota"] = {**self.quota, "checkedAt": start}
        budgets = pool.pool_status(now=start)["platforms"]
        for platform in ("facebook", "instagram", "instagram_stories"):
            self.assertAlmostEqual(budgets[platform]["availableTodayUsd"], 1 / 3, places=5)
            self.assertAlmostEqual(budgets[platform]["dailyShare"], 1 / 3)

    def test_unexpired_share_of_another_platform_cannot_be_taken(self):
        start = dt.datetime(2026, 9, 23, tzinfo=dt.timezone.utc).timestamp()
        with pool._locked() as state:
            state["accounts"]["owner-key"]["quota"] = {**self.quota, "checkedAt": start}
        pool.reserve_run("facebook", .3, now=start)
        with self.assertRaises(RuntimeError):
            pool.reserve_run("facebook", .05, now=start)
        self.assertAlmostEqual(pool.available_budget("instagram", now=start), 1 / 3, places=5)

    def test_idle_platform_holds_half_its_share_at_noon(self):
        # By noon half of each idle third has expired and is usable by others.
        self.assertAlmostEqual(pool.available_budget("facebook", now=self.now), 1 - 2 / 6, places=5)
        pool.reserve_run("facebook", .6, now=self.now)
        with self.assertRaises(RuntimeError):
            pool.reserve_run("facebook", .1, now=self.now)
        budgets = pool.pool_status(now=self.now)["platforms"]
        # Each idle platform still holds half its share; the other can use the rest.
        self.assertAlmostEqual(budgets["instagram_stories"]["availableTodayUsd"], .4 - 1 / 6, places=5)
        self.assertAlmostEqual(budgets["instagram"]["availableTodayUsd"], .4 - 1 / 6, places=5)
        self.assertAlmostEqual(budgets["facebook"]["availableTodayUsd"], .4 - 2 / 6, places=5)


if __name__ == "__main__":
    unittest.main()
