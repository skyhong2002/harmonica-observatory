#!/usr/bin/env python3
"""Sync generated public calendar events to the public Google Calendar."""

from __future__ import annotations

import argparse
import contextlib
import csv
import datetime as dt
import fcntl
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVENTS_PATH = PROJECT_ROOT / "site" / "api" / "public-calendar-events.json"
CALENDAR_CSV = PROJECT_ROOT / "data" / "sources" / "harmonica-public-calendars.csv"
STATUS_PATH = PROJECT_ROOT / "site" / "api" / "public-calendar-sync.json"
DEFAULT_TOKEN_PATH = Path.home() / ".hermes" / "profiles" / "bamboo" / "google_token.json"
DEFAULT_LOCK_PATH = PROJECT_ROOT / "state" / "google-calendar-sync.lock"
SCOPES = ["https://www.googleapis.com/auth/calendar"]
PRIVATE_MARKER_KEY = "harmonicaObserve"
PRIVATE_MARKER_VALUE = "public-calendar"
PRIVATE_EVENT_ID_KEY = "harmonicaObserveEventId"
DEFAULT_HISTORY_DAYS = 365
NETWORK_PROBE_HOST = "oauth2.googleapis.com"
NETWORK_WAIT_SECONDS = int(os.environ.get("HARMONICA_NETWORK_WAIT_SECONDS", "120"))


def wait_for_network(host: str = NETWORK_PROBE_HOST, timeout: int = NETWORK_WAIT_SECONDS) -> bool:
    """Block until the Google endpoint resolves. This job also runs at login, where
    it can start before the network is up; without the wait a cold boot fails the
    whole day's sync on a DNS error that clears seconds later."""
    deadline = time.monotonic() + timeout
    delay = 2.0
    while True:
        try:
            socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
            return True
        except socket.gaierror:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 15.0)


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def load_calendar_metadata_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with CALENDAR_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if (row.get("calendar_id") or "").strip():
                rows.append({key: (value or "").strip() for key, value in row.items()})
    if not rows:
        raise RuntimeError(f"No calendar_id found in {CALENDAR_CSV}")
    return rows


def load_calendar_metadata() -> dict[str, str]:
    return load_calendar_metadata_rows()[0]


def load_calendar_id() -> str:
    return load_calendar_metadata()["calendar_id"]


def load_events(path: Path = EVENTS_PATH) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    events = payload.get("events", [])
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def calendar_description(event: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            str(event.get("details") or "").strip(),
            "結束時間未公告；日曆結束時間為估計。End time not announced; calendar end time is estimated." if event.get("endEstimated") else "",
            str(event.get("evidenceUrl") or "").strip(),
        ]
        if part
    )


def event_resource(event: dict[str, Any]) -> dict[str, Any]:
    timezone = str(event.get("timezone") or "Asia/Taipei").strip()
    body: dict[str, Any] = {
        "summary": event.get("eventName") or event.get("title") or "公開口琴活動",
        "location": event.get("location") or "",
        "description": calendar_description(event),
        "source": {"title": "Harmonica Observatory", "url": event.get("evidenceUrl") or "https://harmonica.observe.tw/"},
        "extendedProperties": {
            "private": {
                PRIVATE_MARKER_KEY: PRIVATE_MARKER_VALUE,
                PRIVATE_EVENT_ID_KEY: str(event.get("id") or ""),
            }
        },
    }
    if event.get("allDay"):
        body["start"] = {"date": str(event.get("start"))[:10]}
        body["end"] = {"date": str(event.get("end"))[:10]}
    else:
        body["start"] = {"dateTime": event.get("start"), "timeZone": timezone}
        body["end"] = {"dateTime": event.get("end"), "timeZone": timezone}
    if event.get("evidenceUrl"):
        body["attachments"] = []
    return body


def event_patch_resource(event: dict[str, Any]) -> dict[str, Any]:
    """Clear mutually exclusive date fields when changing event type via PATCH."""
    body = event_resource(event)
    for key in ('start', 'end'):
        if event.get('allDay'):
            body[key].update(dateTime=None, timeZone=None)
        else:
            body[key]['date'] = None
    return body


def _same_event_time(remote: Any, wanted: dict[str, Any]) -> bool:
    remote = remote if isinstance(remote, dict) else {}
    if wanted.get("date"):
        return remote.get("date") == wanted["date"] and not remote.get("dateTime")
    if remote.get("date") or (remote.get("timeZone") or "") != (wanted.get("timeZone") or ""):
        return False
    remote_time, wanted_time = str(remote.get("dateTime") or ""), str(wanted.get("dateTime") or "")
    try:
        # Google echoes dateTime in its own offset form, so compare instants.
        return dt.datetime.fromisoformat(remote_time) == dt.datetime.fromisoformat(wanted_time)
    except ValueError:
        return remote_time == wanted_time


def remote_event_matches(remote: dict[str, Any], body: dict[str, Any]) -> bool:
    """True when the remote event already has every field the PATCH body would send."""
    for key, wanted in body.items():
        have = remote.get(key)
        if key in {"start", "end"}:
            if not _same_event_time(have, wanted):
                return False
        elif key == "extendedProperties":
            have_private = ((have or {}).get("private") or {}) if isinstance(have, dict) else {}
            if any(have_private.get(name) != value for name, value in (wanted.get("private") or {}).items()):
                return False
        elif isinstance(wanted, str):
            # The API omits empty strings and empty lists from what it returns.
            if (have or "") != wanted:
                return False
        elif isinstance(wanted, list):
            if (have or []) != wanted:
                return False
        elif have != wanted:
            return False
    return True


def load_credentials(token_path: Path):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    env_info = {
        "client_id": os.environ.get("HARMONICA_GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("HARMONICA_GOOGLE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.environ.get("HARMONICA_GOOGLE_REFRESH_TOKEN", "").strip(),
        "token_uri": os.environ.get("HARMONICA_GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token").strip(),
        "scopes": SCOPES,
    }
    if env_info["client_id"] and env_info["client_secret"] and env_info["refresh_token"]:
        info = env_info
    else:
        info = json.loads(token_path.read_text(encoding="utf-8"))
    creds = Credentials.from_authorized_user_info(info, scopes=SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json() + "\n", encoding="utf-8")
    return creds


def load_token_info(token_path: Path) -> dict[str, Any]:
    env_info = {
        "client_id": os.environ.get("HARMONICA_GOOGLE_CLIENT_ID", "").strip(),
        "client_secret": os.environ.get("HARMONICA_GOOGLE_CLIENT_SECRET", "").strip(),
        "refresh_token": os.environ.get("HARMONICA_GOOGLE_REFRESH_TOKEN", "").strip(),
        "token_uri": os.environ.get("HARMONICA_GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token").strip(),
    }
    if env_info["client_id"] and env_info["client_secret"] and env_info["refresh_token"]:
        return env_info
    return json.loads(token_path.read_text(encoding="utf-8"))


def refresh_access_token(token_info: dict[str, Any]) -> str:
    payload = urllib.parse.urlencode(
        {
            "client_id": token_info.get("client_id") or "",
            "client_secret": token_info.get("client_secret") or "",
            "refresh_token": token_info.get("refresh_token") or "",
            "grant_type": "refresh_token",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        token_info.get("token_uri") or "https://oauth2.googleapis.com/token",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.loads(response.read().decode("utf-8"))
    token = str(data.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Google OAuth refresh response did not include access_token.")
    return token


class CalendarRestRequest:
    def __init__(self, method: str, url: str, token: str, body: dict[str, Any] | None = None):
        self.method = method
        self.url = url
        self.token = token
        self.body = body

    def execute(self) -> dict[str, Any]:
        data = None
        headers = {"Authorization": f"Bearer {self.token}"}
        if self.body is not None:
            data = json.dumps(self.body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(self.url, data=data, headers=headers, method=self.method)
        raw = ""
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read().decode("utf-8")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")
                retryable = exc.code in {429, 500, 502, 503, 504} or (
                    exc.code == 403 and "rateLimitExceeded" in detail
                )
                if retryable and attempt < 4:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(
                    f"Google Calendar API {self.method} failed: HTTP {exc.code} {detail}"
                ) from exc
            except (TimeoutError, urllib.error.URLError) as exc:
                if attempt < 4:
                    time.sleep(2**attempt)
                    continue
                raise RuntimeError(f"Google Calendar API {self.method} failed: {exc}") from exc
        if not raw:
            return {}
        return json.loads(raw)


class CalendarRestEvents:
    def __init__(self, token: str):
        self.token = token

    @staticmethod
    def _base(calendar_id: str) -> str:
        return "https://www.googleapis.com/calendar/v3/calendars/" + urllib.parse.quote(calendar_id, safe="")

    @staticmethod
    def _query_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    def list(self, *, calendarId: str, **params: Any) -> CalendarRestRequest:
        query = urllib.parse.urlencode({key: self._query_value(value) for key, value in params.items() if value is not None})
        return CalendarRestRequest("GET", f"{self._base(calendarId)}/events?{query}", self.token)

    def patch(self, *, calendarId: str, eventId: str, body: dict[str, Any]) -> CalendarRestRequest:
        url = f"{self._base(calendarId)}/events/{urllib.parse.quote(eventId, safe='')}"
        return CalendarRestRequest("PATCH", url, self.token, body)

    def insert(self, *, calendarId: str, body: dict[str, Any]) -> CalendarRestRequest:
        return CalendarRestRequest("POST", f"{self._base(calendarId)}/events", self.token, body)

    def delete(self, *, calendarId: str, eventId: str) -> CalendarRestRequest:
        url = f"{self._base(calendarId)}/events/{urllib.parse.quote(eventId, safe='')}"
        return CalendarRestRequest("DELETE", url, self.token)


class CalendarRestService:
    def __init__(self, token: str):
        self._events = CalendarRestEvents(token)
        self._calendars = CalendarRestCalendars(token)

    def events(self) -> CalendarRestEvents:
        return self._events

    def calendars(self) -> "CalendarRestCalendars":
        return self._calendars


class CalendarRestCalendars:
    def __init__(self, token: str):
        self.token = token

    @staticmethod
    def _url(calendar_id: str) -> str:
        return "https://www.googleapis.com/calendar/v3/calendars/" + urllib.parse.quote(calendar_id, safe="")

    def get(self, *, calendarId: str) -> CalendarRestRequest:
        return CalendarRestRequest("GET", self._url(calendarId), self.token)

    def patch(self, *, calendarId: str, body: dict[str, Any]) -> CalendarRestRequest:
        return CalendarRestRequest("PATCH", self._url(calendarId), self.token, body)


def sync_calendar_metadata(service, calendar_id: str, metadata: dict[str, str]) -> bool:
    """Bring the calendar's name, description and time zone in line; return whether it wrote."""
    body = {
        "summary": metadata.get("calendar_name") or "口琴公開活動",
        "description": metadata.get("purpose") or "",
        "timeZone": metadata.get("timezone") or "Asia/Taipei",
    }
    current = service.calendars().get(calendarId=calendar_id).execute() or {}
    if all((current.get(key) or "") == value for key, value in body.items()):
        return False
    service.calendars().patch(calendarId=calendar_id, body=body).execute()
    return True


def env_credentials_available() -> bool:
    return all(
        os.environ.get(name, "").strip()
        for name in [
            "HARMONICA_GOOGLE_CLIENT_ID",
            "HARMONICA_GOOGLE_CLIENT_SECRET",
            "HARMONICA_GOOGLE_REFRESH_TOKEN",
        ]
    )


def existing_managed_events(
    service, calendar_id: str, *, history_days: int = DEFAULT_HISTORY_DAYS
) -> dict[str, list[dict[str, Any]]]:
    now = dt.datetime.now(dt.timezone.utc)
    time_min = (now - dt.timedelta(days=history_days)).isoformat().replace("+00:00", "Z")
    page_token = None
    found: dict[str, list[dict[str, Any]]] = {}
    while True:
        response = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty=f"{PRIVATE_MARKER_KEY}={PRIVATE_MARKER_VALUE}",
            singleEvents=True,
            showDeleted=False,
            timeMin=time_min,
            maxResults=2500,
            pageToken=page_token,
        ).execute()
        for item in response.get("items", []):
            private = ((item.get("extendedProperties") or {}).get("private") or {})
            event_id = private.get(PRIVATE_EVENT_ID_KEY)
            if event_id:
                found.setdefault(event_id, []).append(item)
        page_token = response.get("nextPageToken")
        if not page_token:
            return found


@contextlib.contextmanager
def sync_lock(path: Path):
    """Serialise concurrent syncs. Skipping a run beats queueing behind a stuck one."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def write_status(payload: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATUS_PATH.with_suffix(STATUS_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATUS_PATH)


def metadata_events_path(metadata: dict[str, str]) -> Path:
    configured = metadata.get("events_path") or str(EVENTS_PATH.relative_to(PROJECT_ROOT))
    path = Path(configured)
    return path if path.is_absolute() else PROJECT_ROOT / path


def sync_one_calendar(
    service,
    metadata: dict[str, str],
    *,
    history_days: int = DEFAULT_HISTORY_DAYS,
    allow_empty: bool = False,
) -> dict[str, Any]:
    calendar_id = metadata["calendar_id"]
    source_events = load_events(metadata_events_path(metadata))
    metadata_updated = sync_calendar_metadata(service, calendar_id, metadata)
    existing = existing_managed_events(service, calendar_id, history_days=history_days)
    wanted_ids = {str(event.get("id") or "") for event in source_events if event.get("id")}
    result: dict[str, Any] = {
        "calendarKey": metadata.get("calendar_key") or "",
        "eventMode": metadata.get("event_mode") or "",
        "calendarId": calendar_id,
        "calendarName": metadata.get("calendar_name") or "",
        "eventsPath": str(metadata_events_path(metadata).relative_to(PROJECT_ROOT)),
        "metadataUpdated": metadata_updated,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
        "duplicatesDeleted": 0,
        "kept": len(wanted_ids),
        "status": "ok",
    }
    # A build that failed halfway can leave an empty event list behind. Never let that
    # wipe a calendar that still holds managed events; pass --allow-empty when the
    # source really did run dry.
    if not wanted_ids and existing and not allow_empty:
        result["status"] = "error"
        result["error"] = (
            f"Source file has no events while the calendar still holds {len(existing)} "
            "managed events; refusing to delete them. Re-run with --allow-empty if intended."
        )
        return result
    for event in source_events:
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        body = event_resource(event)
        existing_copies = existing.get(event_id, [])
        if existing_copies:
            canonical = min(
                existing_copies,
                key=lambda item: (str(item.get("created") or ""), str(item.get("id") or "")),
            )
            patch_body = event_patch_resource(event)
            if remote_event_matches(canonical, patch_body):
                result["unchanged"] += 1
            else:
                service.events().patch(
                    calendarId=calendar_id,
                    eventId=canonical["id"],
                    body=patch_body,
                ).execute()
                result["updated"] += 1
            for duplicate in existing_copies:
                if duplicate.get("id") == canonical.get("id"):
                    continue
                service.events().delete(calendarId=calendar_id, eventId=duplicate["id"]).execute()
                result["deleted"] += 1
                result["duplicatesDeleted"] += 1
        else:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            result["created"] += 1

    for event_id, items in existing.items():
        if event_id not in wanted_ids:
            for item in items:
                service.events().delete(calendarId=calendar_id, eventId=item["id"]).execute()
                result["deleted"] += 1
    return result


def selected_calendar_metadata(
    rows: list[dict[str, str]], *, calendar_key: str = "", calendar_id: str = ""
) -> list[dict[str, str]]:
    selected = list(rows)
    if calendar_key:
        selected = [row for row in selected if row.get("calendar_key") == calendar_key]
        if not selected:
            raise RuntimeError(f"Unknown calendar key: {calendar_key}")
    if calendar_id:
        selected = [dict(selected[0], calendar_id=calendar_id)]
    return selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", type=Path, default=Path(os.environ.get("HARMONICA_GOOGLE_TOKEN_JSON", DEFAULT_TOKEN_PATH)))
    parser.add_argument("--calendar-id", default="")
    parser.add_argument("--calendar-key", default="")
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_HISTORY_DAYS,
        help="How far back to scan the calendar for managed events. Raise it to clean up old duplicates.",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="Let an empty source file delete every managed event instead of failing.",
    )
    parser.add_argument("--required", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")

    token_path = args.token.expanduser()
    status: dict[str, Any] = {
        "version": 3,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "status": "skipped",
        "calendarId": args.calendar_id or "",
        "created": 0,
        "updated": 0,
        "unchanged": 0,
        "deleted": 0,
        "duplicatesDeleted": 0,
        "kept": 0,
    }
    if not token_path.exists() and not env_credentials_available():
        status["message"] = f"Google token not found: {token_path}"
        write_status(status)
        if args.required:
            print(status["message"], file=sys.stderr)
            return 1
        print(status["message"])
        return 0

    if not wait_for_network():
        status["message"] = f"Network unavailable: cannot resolve {NETWORK_PROBE_HOST}"
        write_status(status)
        if args.required:
            print(status["message"], file=sys.stderr)
            return 1
        print(status["message"])
        return 0

    calendar_metadata_rows = selected_calendar_metadata(
        load_calendar_metadata_rows(),
        calendar_key=args.calendar_key,
        calendar_id=args.calendar_id,
    )
    lock_path = args.lock_file.expanduser()
    if not lock_path.is_absolute():
        lock_path = PROJECT_ROOT / lock_path
    status["lockFile"] = str(lock_path)
    with sync_lock(lock_path) as acquired:
        if not acquired:
            status["message"] = f"Another calendar sync already holds {lock_path}; skipping this run."
            write_status(status)
            print(status["message"])
            return 0
        return run_sync(args, status, calendar_metadata_rows)


def run_sync(args, status: dict[str, Any], calendar_metadata_rows: list[dict[str, str]]) -> int:
    token_path = args.token.expanduser()
    client_mode = os.environ.get("HARMONICA_GOOGLE_CALENDAR_CLIENT", "").strip().lower()
    if client_mode == "rest":
        token = refresh_access_token(load_token_info(token_path))
        service = CalendarRestService(token)
        status["client"] = "rest"
    else:
        try:
            from googleapiclient.discovery import build
        except ModuleNotFoundError:
            token = refresh_access_token(load_token_info(token_path))
            service = CalendarRestService(token)
            status["client"] = "rest"
        else:
            creds = load_credentials(token_path)
            service = build("calendar", "v3", credentials=creds, cache_discovery=False)
            status["client"] = "google-api-python-client"
    results: list[dict[str, Any]] = []
    for metadata in calendar_metadata_rows:
        try:
            results.append(
                sync_one_calendar(
                    service,
                    metadata,
                    history_days=args.history_days,
                    allow_empty=args.allow_empty,
                )
            )
        except Exception as exc:
            results.append(
                {
                    "calendarKey": metadata.get("calendar_key") or "",
                    "eventMode": metadata.get("event_mode") or "",
                    "calendarId": metadata.get("calendar_id") or "",
                    "calendarName": metadata.get("calendar_name") or "",
                    "status": "error",
                    "error": str(exc),
                    "created": 0,
                    "updated": 0,
                    "unchanged": 0,
                    "deleted": 0,
                    "duplicatesDeleted": 0,
                    "kept": 0,
                }
            )
    for field in ("created", "updated", "unchanged", "deleted", "duplicatesDeleted", "kept"):
        status[field] = sum(int(result.get(field) or 0) for result in results)
    failures = [result for result in results if result.get("status") != "ok"]
    status["calendars"] = results
    status["status"] = "degraded" if failures else "ok"
    status["message"] = (
        f"Google Calendar sync completed for {len(results) - len(failures)}/{len(results)} calendars."
    )
    write_status(status)
    print(
        "Google Calendar sync completed: "
        f"calendars={len(results) - len(failures)}/{len(results)} "
        f"created={status['created']} updated={status['updated']} unchanged={status['unchanged']} "
        f"deleted={status['deleted']} duplicate_deletions={status['duplicatesDeleted']} "
        f"kept={status['kept']}"
    )
    return 1 if failures and args.required else 0


if __name__ == "__main__":
    raise SystemExit(main())
