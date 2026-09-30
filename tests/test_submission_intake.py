import csv
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import process_submission_intake as worker  # noqa: E402
import submission_intake as intake  # noqa: E402


def public_evidence(url: str, *, source_kind: str = "profile_or_page") -> intake.UrlEvidence:
    canonical = intake.canonical_url(url)
    return intake.UrlEvidence(
        submitted_url=url,
        canonical_url=canonical,
        final_url=canonical,
        status=200,
        reachable=True,
        verified=True,
        title="Public source",
        error="",
        source_kind=source_kind,
    )


def proposal(decision: str, *, confidence: float = 0.95) -> dict:
    return {
        "decision": decision,
        "confidence": confidence,
        "reason": "test",
        "target_public_id": "",
        "source_patch": {"country": "TW"},
        "event": {
            "event_name": "",
            "start": "",
            "end": "",
            "all_day": False,
            "venue": "",
            "city": "",
            "details": "",
        },
        "risk_flags": [],
    }


class UrlTests(unittest.TestCase):
    def test_canonical_url_removes_tracking_and_preserves_identity_query(self):
        self.assertEqual(
            intake.canonical_url(
                "http://www.youtube.com/watch?utm_source=x&v=AbC123&feature=share"
            ),
            "https://youtube.com/watch?v=AbC123",
        )
        self.assertEqual(
            intake.canonical_url(
                "https://www.facebook.com/profile.php?id=61590218560112&ref=bookmarks"
            ),
            "https://facebook.com/profile.php?id=61590218560112",
        )
        self.assertEqual(
            intake.canonical_url("https://example.com/a/?utm_medium=social&q=discarded#top"),
            "https://example.com/a",
        )

    def test_canonical_url_rejects_credentials_and_invalid_ports(self):
        self.assertEqual(intake.canonical_url("https://user:pass@example.com/"), "")
        self.assertEqual(intake.canonical_url("https://example.com:invalid/"), "")

    def test_verify_url_rejects_private_networks_before_request(self):
        evidence = intake.verify_url("http://127.0.0.1/private")
        self.assertFalse(evidence.reachable)
        self.assertFalse(evidence.verified)
        self.assertEqual(evidence.error, "host is not publicly routable")

    def test_generic_login_redirect_keeps_submitted_identity_url(self):
        canonical = "https://threads.net/@taiwanharmonica"
        self.assertEqual(
            intake.evidence_final_url(canonical, "https://www.threads.com/login/"),
            canonical,
        )
        self.assertEqual(
            intake.platform_field("https://threads.com/@taiwanharmonica"),
            "threads_url",
        )


class IntakeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.store = intake.IntakeStore(Path(self.tempdir.name) / "intake.sqlite")
        self.store.ingest("response-1", "2026-07-15T00:00:00Z", {"名稱": "測試"})

    def tearDown(self):
        self.store.close()
        self.tempdir.cleanup()

    def test_attempt_increments_once_per_claim(self):
        row = self.store.claim("response-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "processing")
        self.assertEqual(row["attempts"], 1)

        self.store.update("response-1", "processing", evidence_json=[{"status": 200}])
        self.store.update("response-1", "processing", result_json={"action": "add"})
        self.assertEqual(self.store.get("response-1")["attempts"], 1)

        self.store.update("response-1", "retry", error="temporary")
        row = self.store.claim("response-1")
        self.assertEqual(row["attempts"], 2)

    def test_claim_is_not_repeatable_until_retry(self):
        self.assertIsNotNone(self.store.claim("response-1"))
        self.assertIsNone(self.store.claim("response-1"))

    def test_stale_processing_is_recovered(self):
        self.store.claim("response-1")
        self.store.connection.execute(
            "UPDATE submissions SET updated_at = ? WHERE response_id = ?",
            ("2020-01-01T00:00:00+00:00", "response-1"),
        )
        self.store.connection.commit()
        self.assertEqual(self.store.recover_stale_processing(stale_minutes=30), 1)
        self.assertEqual(self.store.get("response-1")["status"], "retry")

    def test_json_decoders_preserve_evidence_lists(self):
        self.store.claim("response-1")
        self.store.update("response-1", "processing", evidence_json=[{"reachable": True}])
        row = self.store.get("response-1")
        self.assertEqual(worker.json_list(row, "evidence_json"), [{"reachable": True}])
        self.assertEqual(worker.json_object(row, "evidence_json"), {})


class DedupeAndProposalTests(unittest.TestCase):
    def test_candidate_matching_finds_exact_canonical_url(self):
        rows = [
            {
                "public_id": "22",
                "name": "測試口琴樂團",
                "website_url": "https://example.com/group/",
            }
        ]
        matches = intake.candidate_matches(
            rows,
            "不同名稱",
            ["http://www.example.com/group/?utm_source=form"],
        )
        self.assertEqual(matches[0]["public_id"], "22")
        self.assertEqual(matches[0]["exact_urls"], ["https://example.com/group"])

    def test_low_confidence_action_requires_review(self):
        answers = {
            intake.REPORT_TYPE: "新增來源或社團",
            intake.TARGET_NAME: "測試口琴樂團",
            intake.PUBLIC_CONFIRMATION: "我確認",
        }
        reviewed, auto_merge = intake.enforce_proposal(
            proposal("add_source", confidence=0.7),
            answers,
            [public_evidence("https://example.com/group")],
            [],
        )
        self.assertEqual(reviewed["decision"], "needs_review")
        self.assertIn("low_confidence", reviewed["risk_flags"])
        self.assertFalse(auto_merge)

    def test_high_confidence_clean_action_can_auto_merge(self):
        answers = {
            intake.REPORT_TYPE: "新增來源或社團",
            intake.TARGET_NAME: "測試口琴樂團",
            intake.PUBLIC_CONFIRMATION: "我確認",
        }
        reviewed, auto_merge = intake.enforce_proposal(
            proposal("add_source"),
            answers,
            [public_evidence("https://example.com/group")],
            [],
        )
        self.assertEqual(reviewed["decision"], "add_source")
        self.assertTrue(auto_merge)

    def test_source_without_country_is_not_assumed_taiwan(self):
        value = proposal("add_source")
        value["source_patch"] = {"name": "Global ensemble"}
        reviewed, automatic = intake.enforce_proposal(value, {
            intake.REPORT_TYPE: "新增來源或社團", intake.TARGET_NAME: "Global ensemble",
            intake.PUBLIC_CONFIRMATION: "confirmed",
        }, [public_evidence("https://example.org/ensemble")], [])
        self.assertEqual(reviewed["decision"], "needs_review")
        self.assertIn("missing_source_country", reviewed["risk_flags"])
        self.assertFalse(automatic)

    @mock.patch("submission_intake.llm_backend.codex_chat")
    def test_ai_review_defaults_to_existing_codex_entitlement(self, codex):
        codex.return_value = json.dumps({"choices": [{"message": {"content": json.dumps(proposal("reject"))}}]})
        result = intake.run_ai_review("response", {}, [], [])
        self.assertEqual(result["decision"], "reject")
        codex.assert_called_once()
        self.assertIn("worldwide", codex.call_args.args[0]["messages"][0]["content"])

    @mock.patch("submission_intake.llm_backend.codex_chat", side_effect=RuntimeError("quota exhausted"))
    def test_codex_quota_failure_has_no_paid_fallback(self, codex):
        with self.assertRaisesRegex(intake.IntakeError, "retained for review"):
            intake.run_ai_review("response", {}, [], [])

    def test_normalize_proposal_does_not_treat_string_false_as_true(self):
        raw = proposal("add_event")
        raw["event"] = {
            "event_name": "活動",
            "start": "2026-08-01",
            "end": "2026-08-01",
            "all_day": "false",
            "venue": "新竹",
        }
        self.assertFalse(intake.normalize_proposal(raw)["event"]["all_day"])


class ApplySourceTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / intake.SOURCE_CSV).parent.mkdir(parents=True)
        row = {field: "" for field in intake.SOURCE_FIELDS}
        row.update(
            {
                "public_id": "7",
                "name": "既有口琴社",
                "type": "學校社團",
                "website_url": "https://existing.example.org/",
            }
        )
        intake.write_source_rows(self.root, [row])

    def tearDown(self):
        self.tempdir.cleanup()

    def test_add_assigns_next_public_id_and_update_keeps_stable_id(self):
        add = proposal("add_source")
        add["source_patch"] = {"name": "新口琴樂團", "type": "團體", "country": "JP"}
        result = intake.apply_source_change(
            self.root,
            "response-add",
            {intake.TARGET_NAME: "新口琴樂團"},
            add,
            [public_evidence("https://new.example.org/")],
        )
        self.assertEqual(result["public_id"], "8")

        update = proposal("update_source")
        update["target_public_id"] = "8"
        update["source_patch"] = {"focus": "重奏與公開演出"}
        result = intake.apply_source_change(
            self.root,
            "response-update",
            {intake.TARGET_NAME: "新口琴樂團"},
            update,
            [public_evidence("https://new.example.org/")],
        )
        self.assertEqual(result["public_id"], "8")
        self.assertEqual(result["verification_key"], "重奏與公開演出")
        rows = intake.load_source_rows(self.root)
        self.assertEqual(intake.row_by_public_id(rows, "8")["focus"], "重奏與公開演出")

    def test_add_without_country_stops_before_writing(self):
        add = proposal("add_source")
        add["source_patch"] = {"name": "Unknown location"}
        before = (self.root / intake.SOURCE_CSV).read_bytes()
        with self.assertRaisesRegex(intake.NeedsReview, "country"):
            intake.apply_source_change(self.root, "missing", {intake.TARGET_NAME: "Unknown location"},
                                       add, [public_evidence("https://example.org/new")])
        self.assertEqual((self.root / intake.SOURCE_CSV).read_bytes(), before)

    def test_conflicting_existing_platform_url_requires_review(self):
        update = proposal("update_source")
        update["target_public_id"] = "7"
        with self.assertRaisesRegex(intake.NeedsReview, "conflicts"):
            intake.apply_source_change(
                self.root,
                "response-conflict",
                {intake.TARGET_NAME: "既有口琴社"},
                update,
                [public_evidence("https://different.example.org/")],
            )

    def test_writer_preserves_registry_crlf_and_complete_schema(self):
        rows = intake.load_source_rows(self.root)
        intake.write_source_rows(self.root, rows)
        raw = (self.root / intake.SOURCE_CSV).read_bytes()
        self.assertEqual(raw.count(b"\r\n"), raw.count(b"\n"))
        with (self.root / intake.SOURCE_CSV).open(
            newline="", encoding="utf-8-sig"
        ) as handle:
            self.assertTrue(
                all(len(row) == len(intake.SOURCE_FIELDS) for row in csv.reader(handle))
            )


class ApplyEventTests(unittest.TestCase):
    def test_event_is_written_once_per_evidence_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            start = (dt.datetime.now(intake.TAIPEI).date() + dt.timedelta(days=10)).isoformat()
            value = proposal("add_event")
            value["event"] = {
                "event_name": "公開口琴測試活動",
                "start": start,
                "end": start,
                "all_day": True,
                "venue": "新竹市文化局演藝廳",
                "city": "新竹市",
                "details": "公開活動",
                "country": "TW",
                "timezone": "Asia/Taipei",
                "event_mode": "physical",
            }
            evidence = [public_evidence("https://events.example.org/harmonica-2026")]
            first = intake.apply_event_change(root, "response-event", value, evidence)
            second = intake.apply_event_change(root, "response-event-2", value, evidence)
            self.assertEqual(first["action"], "add")
            self.assertEqual(second["action"], "no_change")
            with (root / intake.SUBMITTED_EVENTS_CSV).open(
                newline="", encoding="utf-8-sig"
            ) as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)


class GlobalEventTests(unittest.TestCase):
    def test_explicit_country_zone_and_mode_are_required(self):
        full = {"country": "JP", "timezone": "Asia/Tokyo", "event_mode": "physical"}
        self.assertEqual(intake.event_context(full), ("JP", "Asia/Tokyo", "overseas_physical"))
        for field in full:
            incomplete = {key: value for key, value in full.items() if key != field}
            with self.assertRaises(intake.NeedsReview):
                intake.event_context(incomplete)
        with self.assertRaises(intake.NeedsReview):
            intake.event_context({**full, "event_mode": "taiwan_physical"})
        with self.assertRaises(intake.NeedsReview):
            intake.event_context({**full, "timezone": "Asia/Invented"})
        self.assertEqual(intake.event_context({"country": "WORLD", "timezone": "UTC", "event_mode": "online"})[2], "online")

    def test_preserve_source_timezone_and_reject_offset_mismatch(self):
        tokyo = intake.parse_event_time("2026-10-01T20:00:00+09:00", all_day=False, timezone="Asia/Tokyo")
        self.assertEqual(tokyo.isoformat(), "2026-10-01T20:00:00+09:00")
        self.assertEqual(str(tokyo.tzinfo), "Asia/Tokyo")
        with self.assertRaisesRegex(intake.NeedsReview, "offset"):
            intake.parse_event_time("2026-10-01T20:00:00+08:00", all_day=False, timezone="Asia/Tokyo")
        with self.assertRaisesRegex(intake.NeedsReview, "offset"):
            intake.parse_event_time("2026-03-08T02:30:00-05:00", all_day=False, timezone="America/New_York")
        with self.assertRaisesRegex(intake.NeedsReview, "offset"):
            intake.parse_event_time("2026-10-01T20:00:00", all_day=False, timezone="Asia/Tokyo")
        self.assertEqual(intake.parse_event_time("2026-10-01", all_day=True).isoformat(), "2026-10-01")
        with self.assertRaises(intake.NeedsReview):
            intake.parse_event_time("2026-10-01T20:00:00Z", all_day=True)

    def test_global_event_roundtrip_and_legacy_csv_migration(self):
        from apply_submitted_events import load_submitted_events
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / intake.SUBMITTED_EVENTS_CSV
            path.parent.mkdir(parents=True)
            old_fields = [field for field in intake.EVENT_FIELDS if field not in {"country", "timezone", "event_mode"}]
            with path.open('w', newline='', encoding='utf-8-sig') as handle:
                writer = csv.DictWriter(handle, fieldnames=old_fields)
                writer.writeheader()
                writer.writerow({"submission_id": "old", "evidence_url": "https://example.org/old", "event_name": "Historical Taiwan", "start": "2026-08-01", "end": "2026-08-01", "all_day": "true", "venue": "Taipei"})
            start = (dt.datetime.now(intake.ZoneInfo("Asia/Tokyo")) + dt.timedelta(days=10)).replace(microsecond=0)
            value = proposal("add_event")
            value["event"] = {"event_name": "Tokyo concert", "start": start.isoformat(),
                "end": (start + dt.timedelta(hours=2)).isoformat(), "all_day": False,
                "venue": "Tokyo concert hall", "country": "JP", "timezone": "Asia/Tokyo", "event_mode": "physical"}
            result = intake.apply_event_change(root, "japan", value, [public_evidence("https://example.org/japan")])
            self.assertIn("overseas-calendar-events.json", result["verification_url"])
            events = load_submitted_events(path)
            self.assertEqual(len(events), 2)
            old, new = events
            self.assertEqual(old["country"], "TW")
            self.assertEqual(old["calendarType"], "taiwan_physical")
            self.assertEqual(old["end"], "2026-08-02")
            self.assertEqual(new["timezone"], "Asia/Tokyo")
            self.assertEqual(new["calendarType"], "overseas_physical")
            self.assertEqual(new["start"], start.isoformat())


if __name__ == "__main__":
    unittest.main()
