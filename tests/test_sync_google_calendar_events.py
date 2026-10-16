import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import sync_google_calendar_events as sync  # noqa: E402


class FakeRequest:
    def __init__(self, result=None):
        self.result = result or {}

    def execute(self):
        return self.result


class FakeEvents:
    def __init__(self, existing):
        self.existing = existing
        self.patched = []
        self.inserted = []
        self.deleted = []

    def list(self, **kwargs):
        return FakeRequest({"items": self.existing})

    def patch(self, **kwargs):
        self.patched.append(kwargs)
        return FakeRequest()

    def insert(self, **kwargs):
        self.inserted.append(kwargs)
        return FakeRequest()

    def delete(self, **kwargs):
        self.deleted.append(kwargs)
        return FakeRequest()


class FakeCalendars:
    def __init__(self, current=None):
        self.current = current or {}
        self.patched = []

    def get(self, **kwargs):
        return FakeRequest(dict(self.current))

    def patch(self, **kwargs):
        self.patched.append(kwargs)
        return FakeRequest()


class FakeService:
    def __init__(self, existing, calendar=None):
        self.fake_events = FakeEvents(existing)
        self.fake_calendars = FakeCalendars(calendar)

    def events(self):
        return self.fake_events

    def calendars(self):
        return self.fake_calendars


class GoogleCalendarSyncTests(unittest.TestCase):
    def test_patch_clears_incompatible_date_fields_in_both_directions(self):
        timed = sync.event_patch_resource({'start':'2026-09-25T20:30:00+08:00', 'end':'2026-09-25T21:30:00+08:00', 'timezone':'Asia/Taipei'})
        self.assertIsNone(timed['start']['date'])
        self.assertIsNone(timed['end']['date'])
        self.assertIn('dateTime', timed['start'])
        civil = sync.event_patch_resource({'allDay':True,'start':'2026-09-25','end':'2026-09-26'})
        self.assertEqual(civil['start']['date'], '2026-09-25')
        self.assertIsNone(civil['start']['dateTime'])
        self.assertIsNone(civil['end']['timeZone'])

    def test_estimated_end_is_explicit_in_google_calendar_description(self):
        event = {'id': 'fixture', 'start': '2026-09-25T20:30:00+08:00', 'end': '2026-09-25T22:30:00+08:00',
                 'timezone': 'Asia/Taipei', 'details': 'Original announcement', 'endEstimated': True}
        resource = sync.event_resource(event)
        self.assertIn('End time not announced', resource['description'])
        self.assertIn('Original announcement', resource['description'])
        self.assertEqual(resource['source']['title'], 'Harmonica Observatory')
        event['endEstimated'] = False
        self.assertNotIn('End time not announced', sync.calendar_description(event))

    def test_default_lookback_covers_retained_past_events(self):
        self.assertEqual(sync.DEFAULT_HISTORY_DAYS, 365)

    def test_rest_client_can_be_selected_even_when_google_client_is_installed(self):
        args = Namespace(token=Path("/tmp/token.json"), history_days=7, allow_empty=False)
        with (
            mock.patch.dict(sync.os.environ, {"HARMONICA_GOOGLE_CALENDAR_CLIENT": "rest"}),
            mock.patch.object(sync, "load_token_info", return_value={}),
            mock.patch.object(sync, "refresh_access_token", return_value="access-token"),
            mock.patch.object(sync, "sync_one_calendar", return_value={"status": "ok"}),
            mock.patch.object(sync, "write_status"),
        ):
            status = {}
            result = sync.run_sync(args, status, [{"calendar_key": "taiwan"}])

        self.assertEqual(result, 0)
        self.assertEqual(status["client"], "rest")

    def test_timed_event_resource_preserves_event_timezone(self):
        resource = sync.event_resource(
            {
                "id": "tokyo-event",
                "eventName": "東京口琴音樂會",
                "start": "2026-08-02T19:00:00+09:00",
                "end": "2026-08-02T21:00:00+09:00",
                "allDay": False,
                "timezone": "Asia/Tokyo",
                "location": "Tokyo Concert Hall",
                "evidenceUrl": "https://example.test/tokyo",
            }
        )
        self.assertEqual(resource["start"]["timeZone"], "Asia/Tokyo")
        self.assertEqual(resource["end"]["timeZone"], "Asia/Tokyo")
        self.assertEqual(
            resource["extendedProperties"]["private"][sync.PRIVATE_EVENT_ID_KEY],
            "tokyo-event",
        )

    def test_calendar_metadata_contains_three_distinct_modes(self):
        rows = sync.load_calendar_metadata_rows()
        self.assertEqual(
            {row.get("event_mode") for row in rows},
            {"taiwan_physical", "overseas_physical", "online"},
        )
        self.assertEqual(len({row["calendar_id"] for row in rows}), 3)
        self.assertEqual(len(sync.selected_calendar_metadata(rows)), 3)
        self.assertEqual(
            [row["calendar_key"] for row in sync.selected_calendar_metadata(rows, calendar_key="online")],
            ["online"],
        )
        overridden = sync.selected_calendar_metadata(rows, calendar_id="explicit@example.test")
        self.assertEqual(len(overridden), 1)
        self.assertEqual(overridden[0]["calendar_id"], "explicit@example.test")

    def test_sync_keeps_one_copy_and_deletes_duplicate_managed_events(self):
        private = {
            sync.PRIVATE_MARKER_KEY: sync.PRIVATE_MARKER_VALUE,
            sync.PRIVATE_EVENT_ID_KEY: "same-event",
        }
        service = FakeService(
            [
                {"id": "older-copy", "created": "2026-07-01T00:00:00Z", "extendedProperties": {"private": private}},
                {"id": "newer-copy", "created": "2026-07-02T00:00:00Z", "extendedProperties": {"private": private}},
            ]
        )
        original_load_events = sync.load_events
        try:
            sync.load_events = lambda path: [
                {
                    "id": "same-event",
                    "eventName": "同一活動",
                    "start": "2026-08-08",
                    "end": "2026-08-09",
                    "allDay": True,
                }
            ]
            result = sync.sync_one_calendar(
                service,
                {
                    "calendar_id": "calendar@example.test",
                    "calendar_key": "taiwan",
                    "events_path": "site/api/public-calendar-events.json",
                },
            )
        finally:
            sync.load_events = original_load_events

        self.assertEqual(service.fake_events.patched[0]["eventId"], "older-copy")
        self.assertEqual([item["eventId"] for item in service.fake_events.deleted], ["newer-copy"])
        self.assertEqual(result["duplicatesDeleted"], 1)
        self.assertEqual(result["deleted"], 1)

    def run_sync_one(self, service, events, metadata=None):
        with mock.patch.object(sync, "load_events", return_value=events):
            return sync.sync_one_calendar(
                service,
                {
                    "calendar_id": "calendar@example.test",
                    "calendar_key": "taiwan",
                    "calendar_name": "臺灣口琴實體活動",
                    "purpose": "實際舉辦地點在臺灣的公開口琴實體活動",
                    "timezone": "Asia/Taipei",
                    "events_path": "site/api/public-calendar-events.json",
                    **(metadata or {}),
                },
            )

    def remote_copy(self, event, remote_id="remote-1", **overrides):
        """What the Calendar API returns for an event created from ``event``."""
        body = sync.event_resource(event)
        remote = {
            "id": remote_id,
            "created": "2026-07-01T00:00:00Z",
            "status": "confirmed",
            "htmlLink": "https://calendar.google.com/event?eid=x",
            **{key: value for key, value in body.items() if value not in ("", [])},
        }
        # Google echoes timed events in its own offset form and adds its own fields.
        for key in ("start", "end"):
            if "dateTime" in remote[key]:
                instant = sync.dt.datetime.fromisoformat(remote[key]["dateTime"])
                remote[key] = {**remote[key], "dateTime": instant.astimezone(sync.dt.timezone.utc).isoformat().replace("+00:00", "Z")}
        remote.update(overrides)
        return remote

    def test_unchanged_calendar_and_events_are_not_written(self):
        timed = {
            "id": "timed", "eventName": "口琴音樂會", "start": "2026-11-14T19:30:00+08:00",
            "end": "2026-11-14T21:30:00+08:00", "timezone": "Asia/Taipei", "location": "臺北",
            "details": "公開演出", "evidenceUrl": "https://example.test/post",
        }
        all_day = {"id": "all-day", "eventName": "口琴節", "start": "2026-10-31", "end": "2026-11-01", "allDay": True}
        service = FakeService(
            [self.remote_copy(timed, "remote-timed"), self.remote_copy(all_day, "remote-all-day")],
            calendar={
                "id": "calendar@example.test",
                "summary": "臺灣口琴實體活動",
                "description": "實際舉辦地點在臺灣的公開口琴實體活動",
                "timeZone": "Asia/Taipei",
            },
        )
        result = self.run_sync_one(service, [timed, all_day])

        self.assertEqual(service.fake_events.patched, [])
        self.assertEqual(service.fake_calendars.patched, [])
        self.assertEqual((result["updated"], result["unchanged"]), (0, 2))
        self.assertFalse(result["metadataUpdated"])

    def test_changed_fields_are_still_patched(self):
        event = {
            "id": "timed", "eventName": "口琴音樂會", "start": "2026-11-14T19:30:00+08:00",
            "end": "2026-11-14T21:30:00+08:00", "timezone": "Asia/Taipei", "location": "臺北",
        }
        stale_copies = [
            self.remote_copy(event, summary="舊名稱"),
            self.remote_copy(event, location=""),
            self.remote_copy(event, start={"dateTime": "2026-11-14T20:30:00+08:00", "timeZone": "Asia/Taipei"}),
            self.remote_copy(event, start={"date": "2026-11-14"}),
            self.remote_copy(event, end={"dateTime": "2026-11-14T21:30:00+08:00", "timeZone": "Asia/Tokyo"}),
            self.remote_copy(event, extendedProperties={"private": {sync.PRIVATE_EVENT_ID_KEY: "timed"}}),
        ]
        for stale in stale_copies:
            with self.subTest(stale=stale):
                service = FakeService([stale], calendar={"summary": "舊日曆"})
                result = self.run_sync_one(service, [event])
                self.assertEqual(len(service.fake_events.patched), 1)
                self.assertEqual((result["updated"], result["unchanged"]), (1, 0))
                self.assertEqual(len(service.fake_calendars.patched), 1)
                self.assertTrue(result["metadataUpdated"])

    def test_timed_event_becoming_all_day_is_patched(self):
        timed = {"id": "e", "eventName": "活動", "start": "2026-10-31T10:00:00+08:00", "end": "2026-10-31T12:00:00+08:00"}
        all_day = {"id": "e", "eventName": "活動", "start": "2026-10-31", "end": "2026-11-01", "allDay": True}
        service = FakeService([self.remote_copy(timed)])
        self.run_sync_one(service, [all_day])
        self.assertEqual(len(service.fake_events.patched), 1)

    def test_sync_refuses_to_empty_a_calendar_when_source_has_no_events(self):
        private = {
            sync.PRIVATE_MARKER_KEY: sync.PRIVATE_MARKER_VALUE,
            sync.PRIVATE_EVENT_ID_KEY: "existing-event",
        }
        service = FakeService(
            [{"id": "live-copy", "created": "2026-07-01T00:00:00Z", "extendedProperties": {"private": private}}]
        )
        original_load_events = sync.load_events
        try:
            sync.load_events = lambda path: []
            result = sync.sync_one_calendar(
                service,
                {
                    "calendar_id": "calendar@example.test",
                    "calendar_key": "taiwan",
                    "events_path": "site/api/public-calendar-events.json",
                },
            )
        finally:
            sync.load_events = original_load_events

        self.assertEqual(result["status"], "error")
        self.assertEqual(service.fake_events.deleted, [])
        self.assertEqual(result["deleted"], 0)

    def test_allow_empty_lets_an_empty_source_clear_the_calendar(self):
        private = {
            sync.PRIVATE_MARKER_KEY: sync.PRIVATE_MARKER_VALUE,
            sync.PRIVATE_EVENT_ID_KEY: "existing-event",
        }
        service = FakeService(
            [{"id": "live-copy", "created": "2026-07-01T00:00:00Z", "extendedProperties": {"private": private}}]
        )
        original_load_events = sync.load_events
        try:
            sync.load_events = lambda path: []
            result = sync.sync_one_calendar(
                service,
                {
                    "calendar_id": "calendar@example.test",
                    "calendar_key": "taiwan",
                    "events_path": "site/api/public-calendar-events.json",
                },
                allow_empty=True,
            )
        finally:
            sync.load_events = original_load_events

        self.assertEqual(result["status"], "ok")
        self.assertEqual([item["eventId"] for item in service.fake_events.deleted], ["live-copy"])
        self.assertEqual(result["deleted"], 1)


class SyncLockTests(unittest.TestCase):
    def test_second_holder_does_not_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "nested" / "sync.lock"
            with sync.sync_lock(lock_path) as first:
                self.assertTrue(first)
                with sync.sync_lock(lock_path) as second:
                    self.assertFalse(second)

    def test_lock_is_released_when_the_body_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "sync.lock"
            with self.assertRaises(RuntimeError):
                with sync.sync_lock(lock_path) as acquired:
                    self.assertTrue(acquired)
                    raise RuntimeError("boom")
            with sync.sync_lock(lock_path) as reacquired:
                self.assertTrue(reacquired)


if __name__ == "__main__":
    unittest.main()
