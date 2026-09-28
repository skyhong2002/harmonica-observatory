#!/usr/bin/env python3
"""Fetch recent public YouTube videos with yt-dlp into the social inbox."""

from __future__ import annotations

import argparse
import datetime as dt
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from youtube_atom import fetch_entries


PROJECT_ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
DEFAULT_INBOX = PROJECT_ROOT / "data" / "feeds" / "social_feed_inbox.jsonl"
DEFAULT_LEDGER = PROJECT_ROOT / "state" / "youtube_ytdlp_fetcher.json"
DEFAULT_ERRORS = PROJECT_ROOT / "data" / "feeds" / "social_feed_errors.jsonl"


def env_int(name: str, default: int, *, minimum: int = 0) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, value)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_errors(path: Path, errors: list[dict[str, Any]]) -> None:
    if not errors:
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    append_jsonl(path, [{**error, "seen_at": now} for error in errors])


def ytdlp_command() -> list[str]:
    env_value = os.environ.get("YTDLP_BIN")
    if env_value:
        return [env_value]
    path = shutil.which("yt-dlp")
    if path:
        return [path]
    probe = subprocess.run(
        [sys.executable, "-m", "yt_dlp", "--version"],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if probe.returncode == 0:
        return [sys.executable, "-m", "yt_dlp"]
    return []


def run_ytdlp(
    base_cmd: list[str],
    args: list[str],
    timeout: int,
    *,
    socket_timeout: int,
    retries: int,
    extractor_retries: int,
    timeout_retries: int,
    retry_delay_secs: int,
) -> str:
    command = [
        *base_cmd,
        "--no-warnings",
        "--ignore-errors",
        "--skip-download",
    ]
    if socket_timeout > 0:
        command.extend(["--socket-timeout", str(socket_timeout)])
    if retries >= 0:
        command.extend(["--retries", str(retries)])
    if extractor_retries >= 0:
        command.extend(["--extractor-retries", str(extractor_retries)])
    command.extend(args)

    attempts = max(1, timeout_retries + 1)
    for attempt in range(attempts):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            if attempt + 1 >= attempts:
                raise
            if retry_delay_secs > 0:
                time.sleep(retry_delay_secs)
            continue
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()[-1600:]
            raise RuntimeError(detail or f"yt-dlp exited with code {result.returncode}")
        return result.stdout
    raise RuntimeError("yt-dlp did not return output")


def load_youtube_sources(config_path: Path, source_ids: list[str]) -> list[dict[str, Any]]:
    config = load_json(config_path, {"sources": []})
    selected = set(source_ids)
    sources: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        if source.get("type") != "youtube_ytdlp":
            continue
        if not source.get("enabled", True):
            continue
        if selected and source.get("id") not in selected:
            continue
        if not source.get("url"):
            continue
        sources.append(source)
    return sources


def ledger_runs(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    runs = ledger.get("runs")
    return runs if isinstance(runs, list) else []


def ledger_sources(ledger: dict[str, Any]) -> dict[str, Any]:
    sources = ledger.get("sources")
    if not isinstance(sources, dict):
        sources = {}
        ledger["sources"] = sources
    return sources


def compact_error(value: Any, limit: int = 1600) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[-limit:] if text else "未提供錯誤訊息"


def mark_source_success(
    ledger: dict[str, Any],
    source_id: str,
    *,
    checked_at: str,
    duration_secs: float,
    new_rows: int,
) -> None:
    state = ledger_sources(ledger).setdefault(source_id, {})
    state.update(
        {
            "last_status": "ok",
            "last_checked_at": checked_at,
            "last_success_at": checked_at,
            "last_duration_secs": round(duration_secs, 2),
            "last_new_inbox_rows": new_rows,
            "consecutive_errors": 0,
        }
    )
    state.pop("last_error", None)
    state.pop("last_error_at", None)


def mark_source_error(
    ledger: dict[str, Any],
    source_id: str,
    *,
    checked_at: str,
    duration_secs: float,
    error: Any,
) -> None:
    state = ledger_sources(ledger).setdefault(source_id, {})
    previous_errors = int(state.get("consecutive_errors") or 0)
    state.update(
        {
            "last_status": "error",
            "last_checked_at": checked_at,
            "last_error_at": checked_at,
            "last_duration_secs": round(duration_secs, 2),
            "last_error": compact_error(error),
            "consecutive_errors": previous_errors + 1,
        }
    )


def select_sources(sources: list[dict[str, Any]], ledger: dict[str, Any], max_sources: int) -> tuple[list[dict[str, Any]], int]:
    if max_sources <= 0 or max_sources >= len(sources):
        return sources, int(ledger.get("next_source_index") or 0)
    start = int(ledger.get("next_source_index") or 0) % len(sources)
    selected = [sources[(start + offset) % len(sources)] for offset in range(max_sources)]
    return selected, start


def existing_inbox_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = f"{row.get('source_id')}:{row.get('post_id') or row.get('url')}"
            keys.add(key)
    return keys


def compact_text(value: Any, limit: int = 2400) -> str:
    if value is None:
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(value).splitlines()]
    return "\n".join(line for line in lines if line).strip()[:limit]


def channel_url(value: str) -> str:
    url = value.strip()
    parsed = urllib.parse.urlparse(url)
    if "youtube.com" not in parsed.netloc.casefold():
        return url
    path = parsed.path.rstrip("/")
    if path.endswith("/videos") or path.endswith("/streams") or path.endswith("/featured"):
        return url
    if path and not path.startswith("/watch") and not path.startswith("/playlist"):
        return urllib.parse.urlunparse(parsed._replace(path=path + "/videos", query="", fragment=""))
    return url


def entry_video_url(entry: dict[str, Any]) -> str:
    for key in ("webpage_url", "url"):
        value = str(entry.get(key) or "")
        if value.startswith("http://") or value.startswith("https://"):
            return value
    video_id = str(entry.get("id") or entry.get("url") or "").strip()
    if video_id:
        return f"https://www.youtube.com/watch?v={urllib.parse.quote(video_id, safe='')}"
    return ""


def parse_date(info: dict[str, Any]) -> dt.datetime | None:
    timestamp = info.get("timestamp") or info.get("release_timestamp")
    if isinstance(timestamp, (int, float)):
        return dt.datetime.fromtimestamp(float(timestamp), tz=dt.timezone.utc)
    upload_date = str(info.get("upload_date") or "")
    if re.fullmatch(r"\d{8}", upload_date):
        return dt.datetime(
            int(upload_date[0:4]),
            int(upload_date[4:6]),
            int(upload_date[6:8]),
            tzinfo=dt.timezone.utc,
        )
    return None


def too_old(posted: dt.datetime | None, max_age_days: int, now: dt.datetime) -> bool:
    return bool(max_age_days and posted and posted < now - dt.timedelta(days=max_age_days))


def first_thumbnail(info: dict[str, Any]) -> str:
    direct = str(info.get("thumbnail") or "")
    if direct:
        return direct
    thumbnails = info.get("thumbnails")
    if isinstance(thumbnails, list):
        for item in reversed(thumbnails):
            if isinstance(item, dict) and item.get("url"):
                return str(item["url"])
    return ""


def normalize_video(source: dict[str, Any], info: dict[str, Any]) -> dict[str, Any]:
    posted = parse_date(info)
    image_url = first_thumbnail(info)
    title = compact_text(info.get("title"), 600)
    description = compact_text(info.get("description"), 1800)
    video_url = str(info.get("webpage_url") or info.get("original_url") or entry_video_url(info))
    post_id = str(info.get("id") or video_url)
    source_name = source.get("name") or info.get("channel") or info.get("uploader") or "YouTube"
    source_display_name = compact_text(info.get("channel") or info.get("uploader") or source_name, 300)
    source_profile_url = str(info.get("channel_url") or info.get("uploader_url") or source.get("url") or "")
    return {
        "account": source_profile_url,
        "image_url": image_url,
        "images": [image_url] if image_url else [],
        "include_without_keywords": bool(source.get("include_without_keywords", True)),
        "media_type": "video",
        "platform": "youtube",
        "post_id": post_id,
        "posted_at": posted.isoformat() if posted else "",
        "raw_source": "yt-dlp",
        "source_id": source.get("id") or "youtube_ytdlp",
        "source_display_name": source_display_name,
        "source_name": source_name,
        "source_profile_url": source_profile_url,
        "text": compact_text("\n".join(part for part in [title, description] if part)),
        "url": video_url,
        "like_count": info.get("like_count"),
        "comment_count": info.get("comment_count"),
        "view_count": info.get("view_count"),
    }


def fetch_source(
    source: dict[str, Any],
    *,
    base_cmd: list[str],
    inbox_keys: set[str],
    max_age_days: int,
    timeout_secs: int,
    socket_timeout_secs: int,
    ytdlp_retries: int,
    extractor_retries: int,
    timeout_retries: int,
    retry_delay_secs: int,
    now: dt.datetime,
) -> list[dict[str, Any]]:
    limit = min(max(int(source.get("limit") or 5), 1), 10)
    if source.get("channel_id"):
        try:
            entries = fetch_entries(str(source["channel_id"]), timeout=min(timeout_secs, 15), limit=limit)
        except (OSError, ValueError, http.client.HTTPException):
            # A verified channel can still have an unavailable feed; retain the
            # existing public-video extractor as the fallback.
            pass
        else:
            rows = []
            for info in entries:
                key = f"{source.get('id')}:{info['id']}"
                if key in inbox_keys:
                    continue
                inbox_keys.add(key)
                if too_old(parse_date(info), max_age_days, now):
                    continue
                row = normalize_video(source, info)
                row["raw_source"] = "youtube-atom"
                rows.append(row)
            return rows
    url = channel_url(str(source["url"]))
    flat_output = run_ytdlp(
        base_cmd,
        ["--flat-playlist", "--dump-json", "--playlist-end", str(limit), url],
        timeout_secs,
        socket_timeout=socket_timeout_secs,
        retries=ytdlp_retries,
        extractor_retries=extractor_retries,
        timeout_retries=timeout_retries,
        retry_delay_secs=retry_delay_secs,
    )
    rows: list[dict[str, Any]] = []
    for line in flat_output.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        video_url = entry_video_url(entry)
        post_id = str(entry.get("id") or video_url)
        inbox_key = f"{source.get('id')}:{post_id}"
        if inbox_key in inbox_keys:
            continue
        if not video_url:
            continue
        info = entry
        if parse_date(info) is None or not first_thumbnail(info):
            try:
                detail_output = run_ytdlp(
                    base_cmd,
                    ["--dump-single-json", "--no-playlist", video_url],
                    timeout_secs,
                    socket_timeout=socket_timeout_secs,
                    retries=ytdlp_retries,
                    extractor_retries=extractor_retries,
                    timeout_retries=timeout_retries,
                    retry_delay_secs=retry_delay_secs,
                )
            except RuntimeError:
                continue
            try:
                info = json.loads(detail_output)
            except json.JSONDecodeError as exc:
                continue
        posted = parse_date(info)
        if too_old(posted, max_age_days, now):
            inbox_keys.add(inbox_key)
            continue
        row = normalize_video(source, info)
        if row.get("url") or row.get("text"):
            rows.append(row)
            inbox_keys.add(f"{row.get('source_id')}:{row.get('post_id') or row.get('url')}")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument("--max-sources-per-run", type=int, default=5)
    parser.add_argument("--max-post-age-days", type=int, default=30)
    parser.add_argument("--timeout-secs", type=int, default=env_int("HARMONICA_YTDLP_TIMEOUT_SECS", 90, minimum=1))
    parser.add_argument(
        "--socket-timeout-secs",
        type=int,
        default=env_int("HARMONICA_YTDLP_SOCKET_TIMEOUT_SECS", 20, minimum=0),
    )
    parser.add_argument("--ytdlp-retries", type=int, default=env_int("HARMONICA_YTDLP_RETRIES", 1, minimum=0))
    parser.add_argument(
        "--extractor-retries",
        type=int,
        default=env_int("HARMONICA_YTDLP_EXTRACTOR_RETRIES", 1, minimum=0),
    )
    parser.add_argument(
        "--timeout-retries",
        type=int,
        default=env_int("HARMONICA_YTDLP_TIMEOUT_RETRIES", 1, minimum=0),
    )
    parser.add_argument(
        "--retry-delay-secs",
        type=int,
        default=env_int("HARMONICA_YTDLP_RETRY_DELAY_SECS", 2, minimum=0),
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    explicit_source_selection = bool(args.source_id)
    sources = load_youtube_sources(args.config, args.source_id)
    ledger = load_json(args.ledger, {"runs": [], "next_source_index": 0})
    max_sources = 0 if args.full_refresh else args.max_sources_per_run
    selected, start_index = select_sources(sources, ledger, max_sources)
    base_cmd = ytdlp_command()

    if args.check:
        print(
            json.dumps(
                {
                    "config": str(args.config),
                    "inbox": str(args.inbox),
                    "ledger": str(args.ledger),
                    "sources_total": len(sources),
                    "sources_selected": len(selected),
                    "selected_start_index": start_index,
                    "has_ytdlp": bool(base_cmd),
                    "ytdlp_command": " ".join(base_cmd),
                    "timeout_secs": args.timeout_secs,
                    "socket_timeout_secs": args.socket_timeout_secs,
                    "ytdlp_retries": args.ytdlp_retries,
                    "extractor_retries": args.extractor_retries,
                    "timeout_retries": args.timeout_retries,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if not base_cmd:
        raise SystemExit("Missing yt-dlp. Install it with: python3 -m pip install --user yt-dlp")

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    now = dt.datetime.now(dt.timezone.utc)
    inbox_keys = existing_inbox_keys(args.inbox)
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    source_results: list[dict[str, Any]] = []
    for source in selected:
        source_id = str(source.get("id") or "")
        source_started = time.monotonic()
        try:
            if args.verbose:
                print(
                    f"Fetching YouTube source {source.get('id')}: {source.get('name') or source.get('url')}",
                    file=sys.stderr,
                    flush=True,
                )
            source_rows = fetch_source(
                source,
                base_cmd=base_cmd,
                inbox_keys=inbox_keys,
                max_age_days=args.max_post_age_days,
                timeout_secs=args.timeout_secs,
                socket_timeout_secs=args.socket_timeout_secs,
                ytdlp_retries=args.ytdlp_retries,
                extractor_retries=args.extractor_retries,
                timeout_retries=args.timeout_retries,
                retry_delay_secs=args.retry_delay_secs,
                now=now,
            )
            rows.extend(source_rows)
            duration_secs = time.monotonic() - source_started
            checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
            mark_source_success(
                ledger,
                source_id,
                checked_at=checked_at,
                duration_secs=duration_secs,
                new_rows=len(source_rows),
            )
            source_results.append(
                {
                    "source_id": source_id,
                    "status": "ok",
                    "new_inbox_rows": len(source_rows),
                    "duration_secs": round(duration_secs, 2),
                }
            )
        except (RuntimeError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
            duration_secs = time.monotonic() - source_started
            checked_at = dt.datetime.now(dt.timezone.utc).isoformat()
            mark_source_error(
                ledger,
                source_id,
                checked_at=checked_at,
                duration_secs=duration_secs,
                error=exc,
            )
            errors.append(
                {
                    "source_id": source_id,
                    "source_type": "youtube_ytdlp",
                    "error": str(exc),
                }
            )
            source_results.append(
                {
                    "source_id": source_id,
                    "status": "error",
                    "duration_secs": round(duration_secs, 2),
                    "error": compact_error(exc, 500),
                }
            )

    if not args.no_write:
        append_jsonl(args.inbox, rows)
    append_errors(args.errors, errors)

    if sources and not explicit_source_selection:
        ledger["next_source_index"] = (start_index + len(selected)) % len(sources)
    record = {
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_ids": [source.get("id") for source in selected],
        "new_inbox_rows": len(rows),
        "error_count": len(errors),
        "failed_source_ids": [error["source_id"] for error in errors],
        "source_results": source_results,
    }
    ledger.setdefault("runs", []).append(record)
    ledger["runs"] = ledger_runs(ledger)[-200:]
    ledger["updated_at"] = record["finished_at"]
    save_json(args.ledger, ledger)

    print(
        json.dumps(
            {
                "ok": not errors,
                "record": record,
                "new_rows": rows[:5],
                "errors": errors[:10],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
