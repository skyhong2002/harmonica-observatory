#!/usr/bin/env python3
"""Build the public ingestion status page and JSON snapshot."""

from __future__ import annotations

import collections
import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import site_chrome


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
STATUS_JSON_OUT = SITE_ROOT / "api" / "status.json"
STATUS_PAGE_OUT = SITE_ROOT / "status" / "index.html"
SOCIAL_SOURCES = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
SOCIAL_CANDIDATES = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
SOCIAL_INBOX = PROJECT_ROOT / "data" / "feeds" / "social_feed_inbox.jsonl"
SOCIAL_ERRORS = PROJECT_ROOT / "data" / "feeds" / "social_feed_errors.jsonl"
SOCIAL_SEEN = PROJECT_ROOT / "state" / "social_seen.json"
SOCIAL_FETCH_STATE = PROJECT_ROOT / "state" / "social_fetch_state.json"
PIPELINE_RUNTIME_STATUS = SITE_ROOT / "api" / "pipeline-runtime.json"
SOCIAL_FETCH_PROGRESS = SITE_ROOT / "api" / "social-fetch-progress.json"
APIFY_LEDGER = PROJECT_ROOT / "state" / "apify_facebook_fetcher.json"
YOUTUBE_LEDGER = PROJECT_ROOT / "state" / "youtube_ytdlp_fetcher.json"
LATEST_API = SITE_ROOT / "api" / "latest.json"
SOURCES_API = SITE_ROOT / "api" / "sources.json"
PIPELINE_LOG = PROJECT_ROOT / "logs" / "pipeline.log"
PIPELINE_ERR_LOG = PROJECT_ROOT / "logs" / "pipeline.err.log"
ASSET_VERSION = site_chrome.ASSET_VERSION
HEADER_HTML = site_chrome.render_header()
PUBLIC_BASE_URL = "https://harmonica.observe.tw"
TAIPEI_TZ = dt.timezone(dt.timedelta(hours=8))
CURRENT_ERROR_WINDOW_SECONDS = 15 * 60
FRESH_PIPELINE_HOURS = 2
STORY_EMPTY_ERROR_PATTERNS = (
    "content does not exist",
    "user has no stories",
    "this route is empty",
    "profile is private",
    "timed out",
)

STATUS_LABELS = {
    "ok": "正常",
    "paused": "節流中",
    "degraded": "部分異常",
    "down": "停止",
    "unknown": "未知",
}

STATUS_SORT = {
    "down": 0,
    "degraded": 1,
    "paused": 2,
    "unknown": 3,
    "ok": 4,
}


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                rows.append(value)
    return rows


def parse_time(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def taipei_iso(value: dt.datetime) -> str:
    return value.astimezone(TAIPEI_TZ).isoformat(timespec="seconds")


def time_label(value: dt.datetime | None) -> str:
    if value is None:
        return "未記錄"
    return value.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M:%S")


def file_mtime(path: Path) -> dt.datetime | None:
    if not path.exists():
        return None
    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)


def hours_since(value: dt.datetime | None, now: dt.datetime) -> float | None:
    if value is None:
        return None
    return max(0.0, (now - value).total_seconds() / 3600)


def max_time(values: list[dt.datetime | None]) -> dt.datetime | None:
    parsed = [value for value in values if value is not None]
    return max(parsed) if parsed else None


def latest_seen_at(rows: list[dict[str, Any]]) -> dt.datetime | None:
    return max_time([parse_time(row.get("seen_at")) for row in rows])


def compact_error(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:220] if text else "未提供錯誤訊息"


def format_usd(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    return f"${number:.2f}"


def source_counts(sources: list[dict[str, Any]], field: str) -> dict[str, int]:
    counter = collections.Counter(str(source.get(field) or "unknown") for source in sources)
    return dict(sorted(counter.items()))


def format_hours(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "-"
    if number.is_integer():
        return str(int(number))
    return f"{number:.1f}".rstrip("0").rstrip(".")


def instagram_schedule_details(
    fetch_state: dict[str, Any],
    social_seen: dict[str, Any],
    social_progress: dict[str, Any],
    now: dt.datetime,
) -> list[str]:
    settings = fetch_state.get("settings") if isinstance(fetch_state.get("settings"), dict) else {}
    last_run = social_seen.get("last_watchdog_run") if isinstance(social_seen.get("last_watchdog_run"), dict) else {}
    instagram_run = last_run.get("instagram") if isinstance(last_run.get("instagram"), dict) else {}
    entries = fetch_state.get("sources") if isinstance(fetch_state.get("sources"), dict) else {}
    auth_block = (
        fetch_state.get("instaloader_story_auth_block")
        if isinstance(fetch_state.get("instaloader_story_auth_block"), dict)
        else {}
    )

    details = [
        (
            "IG 節流：profile 每 "
            f"{format_hours(settings.get('instagram_profile_interval_hours', 12))} 小時、story 每 "
            f"{format_hours(settings.get('instagram_story_interval_hours', 12))} 小時；"
            f"來源間隔 {format_hours(settings.get('instagram_delay_secs', 8))} 秒、"
            f"每輪最多 {int(settings.get('instagram_max_attempts_per_run') or 40)} 個。"
        )
    ]
    if instagram_run:
        details.append(
            "本輪 IG："
            f"抓取 {int(instagram_run.get('attempted') or 0)}、"
            f"排程略過 {int(instagram_run.get('scheduled') or 0)}、"
            f"延後 {int(instagram_run.get('deferred') or 0)}、"
            f"錯誤 {int(instagram_run.get('errors') or 0)}。"
        )

    blocked_until = parse_time(auth_block.get("blocked_until"))
    if blocked_until is not None and blocked_until > now:
        details.append(f"Instagram 登入熔斷中：延後至 {time_label(blocked_until)}；不再逐一重試來源。")
        if auth_block.get("error"):
            details.append(f"Instagram 登入錯誤：{compact_error(auth_block.get('error'))}")

    progress_heartbeat = parse_time(social_progress.get("heartbeatAt"))
    progress_age = hours_since(progress_heartbeat, now)
    if social_progress.get("status") == "running" and progress_age is not None and progress_age < 0.25:
        current_source = social_progress.get("currentSource") if isinstance(social_progress.get("currentSource"), dict) else {}
        details.append(
            "執行中："
            f"{social_progress.get('phase') or 'watchdog'}，"
            f"{int(social_progress.get('processedSources') or 0)}/{int(social_progress.get('totalSources') or 0)}；"
            f"目前 {current_source.get('name') or current_source.get('id') or '未記錄'}；"
            f"heartbeat {time_label(progress_heartbeat)}。"
        )

    next_due_values = []
    for entry in entries.values():
        if not isinstance(entry, dict):
            continue
        source_type = str(entry.get("source_type") or "")
        if source_type not in {"rsshub_instagram_profile", "rsshub_instagram_story"}:
            continue
        due_at = parse_time(entry.get("next_due_at"))
        if due_at is not None:
            next_due_values.append(due_at)
    future_due = [value for value in next_due_values if value >= now]
    if future_due:
        details.append(f"下一個 IG 來源：約 {time_label(min(future_due))}")
    elif next_due_values:
        details.append("目前有 IG 來源已到期，下一輪會按慢速節流抓取。")
    return details


def enabled_watch_sources() -> list[dict[str, Any]]:
    payload = read_json(SOCIAL_SOURCES, {"sources": []})
    sources = payload.get("sources") if isinstance(payload, dict) else []
    return [
        source
        for source in sources
        if isinstance(source, dict)
        and source.get("enabled", True)
        and source.get("type") != "jsonl"
    ]


def probe_url(url: str, timeout: int = 6) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "HarmonicaStatusBot/1.0"})
    started = dt.datetime.now(dt.timezone.utc)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return {
                "ok": 200 <= int(response.status) < 400,
                "statusCode": int(response.status),
                "elapsedMs": int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "statusCode": int(exc.code),
            "elapsedMs": int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000),
            "error": compact_error(exc.reason),
        }
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        return {
            "ok": False,
            "statusCode": None,
            "elapsedMs": int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000),
            "error": compact_error(exc),
        }


def launch_agent_status() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/tw.observe.harmonica.pipeline"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"available": False, "status": "unknown", "summary": compact_error(exc)}

    if result.returncode != 0:
        return {"available": False, "status": "unknown", "summary": compact_error(result.stderr)}

    state_match = re.search(r"state = ([^\n]+)", result.stdout)
    exit_match = re.search(r"last exit code = (-?\d+)", result.stdout)
    runs_match = re.search(r"runs = (\d+)", result.stdout)
    last_exit = int(exit_match.group(1)) if exit_match else None
    status = "ok" if last_exit in (0, None) else "degraded"
    return {
        "available": True,
        "status": status,
        "state": state_match.group(1).strip() if state_match else "unknown",
        "lastExitCode": last_exit,
        "runs": int(runs_match.group(1)) if runs_match else None,
    }


def apify_check() -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "scripts/apify_facebook_fetcher.py", "--check"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=75,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": compact_error(exc)}

    if result.returncode != 0:
        return {"ok": False, "error": compact_error(result.stderr or result.stdout)}

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "Apify check did not return JSON"}

    # Keep only public-safe operational metadata; never expose token source or raw auth details.
    keys = [
        "has_token",
        "auto_budget_pacing",
        "budget_pacing_mode",
        "sources_due_count",
        "sources_selected_count",
        "min_sources_per_run",
        "planned_run_budget_usd",
        "remote_monthly_usage_usd",
        "effective_remote_monthly_limit_usd",
        "remote_monthly_remaining_usd",
        "monthly_remaining_usd",
        "last_successful_run_at",
        "cadence_ready",
    ]
    return {"ok": True, **{key: raw.get(key) for key in keys if key in raw}}


def component(
    component_id: str,
    name: str,
    status: str,
    summary: str,
    details: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": component_id,
        "name": name,
        "status": status,
        "label": STATUS_LABELS.get(status, status),
        "summary": summary,
        "details": details or [],
    }


def annotate_errors(
    errors: list[dict[str, Any]],
    source_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    annotated = []
    for row in errors:
        source_id = str(row.get("source_id") or "")
        source = source_by_id.get(source_id, {})
        annotated.append(
            {
                "seenAt": taipei_iso(parse_time(row.get("seen_at")) or dt.datetime.now(dt.timezone.utc)),
                "sourceId": source_id,
                "sourceName": source.get("name") or row.get("source_name") or source_id or "unknown",
                "platform": source.get("platform") or row.get("platform") or row.get("source_type") or "unknown",
                "sourceType": row.get("source_type") or source.get("type") or "unknown",
                "error": compact_error(row.get("error")),
            }
        )
    return annotated


def youtube_success_times(youtube_ledger: dict[str, Any]) -> dict[str, dt.datetime]:
    sources = youtube_ledger.get("sources") if isinstance(youtube_ledger, dict) else {}
    if not isinstance(sources, dict):
        return {}
    recovered: dict[str, dt.datetime] = {}
    for source_id, state in sources.items():
        if not isinstance(state, dict) or state.get("last_status") != "ok":
            continue
        success_at = parse_time(state.get("last_success_at") or state.get("last_checked_at"))
        if success_at is not None:
            recovered[str(source_id)] = success_at
    return recovered


def youtube_error_superseded(row: dict[str, Any], recovered: dict[str, dt.datetime]) -> bool:
    if row.get("source_type") != "youtube_ytdlp":
        return False
    source_id = str(row.get("source_id") or "")
    error_seen_at = parse_time(row.get("seen_at"))
    recovered_at = recovered.get(source_id)
    return bool(error_seen_at and recovered_at and recovered_at >= error_seen_at)


def is_active_source_error(row: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> bool:
    source_id = str(row.get("source_id") or "")
    return not source_id or source_id in source_by_id


def story_empty_error(row: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> bool:
    source_id = str(row.get("source_id") or "")
    source = source_by_id.get(source_id, {})
    source_type = str(row.get("source_type") or source.get("type") or "")
    if source_type != "rsshub_instagram_story":
        return False
    error = str(row.get("error") or "").casefold()
    if "http error 503" in error or "http error 404" in error:
        return True
    return any(pattern in error for pattern in STORY_EMPTY_ERROR_PATTERNS)


def ignorable_instagram_profile_error(row: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> bool:
    source_id = str(row.get("source_id") or "")
    source = source_by_id.get(source_id, {})
    source_type = str(row.get("source_type") or source.get("type") or "")
    if source_type != "rsshub_instagram_profile":
        return False
    error = str(row.get("error") or "").casefold()
    if str(source.get("provider") or "") == "instaloader" and error.strip() == "the read operation timed out":
        return True
    return "web_profile_info" in error or "instagram user feed returned no author" in error


def ignorable_threads_upstream_error(row: dict[str, Any], source_by_id: dict[str, dict[str, Any]]) -> bool:
    source_id = str(row.get("source_id") or "")
    source = source_by_id.get(source_id, {})
    source_type = str(row.get("source_type") or source.get("type") or "")
    if source_type != "rss" or str(source.get("platform") or "").casefold() != "threads":
        return False
    return "failed to fetch thread data" in str(row.get("error") or "").casefold()


def persistent_source_errors(
    fetch_state: dict[str, Any],
    source_by_id: dict[str, dict[str, Any]],
    current_errors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_ids = {str(row.get("source_id") or "") for row in current_errors}
    entries = fetch_state.get("sources") if isinstance(fetch_state.get("sources"), dict) else {}
    auth_block = fetch_state.get("instaloader_story_auth_block")
    auth_block_active = False
    if isinstance(auth_block, dict):
        blocked_until = parse_time(auth_block.get("blocked_until"))
        auth_block_active = blocked_until is not None and blocked_until > dt.datetime.now(dt.timezone.utc)
    persistent: list[dict[str, Any]] = []
    for source_id, state in entries.items():
        if not isinstance(state, dict) or str(source_id) in current_ids:
            continue
        consecutive_errors = int(state.get("consecutive_errors") or 0)
        error = str(state.get("last_error") or "")
        if consecutive_errors < 2 or not error or str(source_id) not in source_by_id:
            continue
        source_type = str(state.get("source_type") or source_by_id[str(source_id)].get("type") or "")
        source = source_by_id[str(source_id)]
        provider = str(source.get("story_provider") or source.get("provider") or "")
        if provider in {"instagram_public", "apify_stories"}:
            # This state belongs to the retired authenticated collector. The new
            # collector reports its own attempts; preserve old records as history.
            continue
        error_lower = error.casefold()
        if provider == "instaloader" and "asset asset://laser.provider/" in error_lower:
            continue
        if provider == "instaloader" and not auth_block_active and (
            "401 unauthorized" in error_lower
            or "session rejected" in error_lower
            or "please wait a few minutes before you try again" in error_lower
        ):
            continue
        if (
            source_type == "rsshub_instagram_profile"
            and str(source.get("provider") or "") == "instaloader"
            and error_lower.strip() == "the read operation timed out"
        ):
            continue
        if source_type == "rsshub_instagram_profile" and (
            "web_profile_info" in error.casefold()
            or "instagram user feed returned no author" in error.casefold()
        ):
            continue
        # A backed-off Threads feed keeps its streak in the fetch state; the
        # known upstream outage stays hidden just like it is for current errors.
        if ignorable_threads_upstream_error({"source_type": source_type, "error": error, "source_id": source_id}, source_by_id):
            continue
        if source_type == "rsshub_instagram_story" and (
            "timed out" in error.casefold()
            or "content does not exist" in error.casefold()
            or "user has no stories" in error.casefold()
            or "this route is empty" in error.casefold()
            or "profile is private" in error.casefold()
        ):
            continue
        persistent.append(
            {
                "source_id": str(source_id),
                "source_type": state.get("source_type") or source_by_id[str(source_id)].get("type") or "",
                "seen_at": state.get("last_error_at") or "",
                "error": f"連續失敗 {consecutive_errors} 次：{error}",
            }
        )
    return persistent


def public_instagram_component(state: dict[str, Any], sources: list[dict[str, Any]], now: dt.datetime) -> dict[str, Any]:
    labels = {
        "credit_budget": "每日免費額度預算不足，等待下一輪／額度重置",
        "daily_result_limit": "今日限動筆數已達上限",
        "user_daily_exhausted": "供應商今日免費筆數已用完",
        "free_capacity_exhausted": "供應商免費容量暫滿，一小時後重試",
        "public_unavailable_credit_reserve": "公開貼文端點受限，Apify 保留額度不足以補抓",
        "pool_budget_pacing": "Apify 社群池依授權額度分配，等待下次可用預算",
        "no_sources_due": "依排程等待下一批來源",
        "partial_scan": "部分來源或圖片抓取失敗",
    }
    entries = state.get("sources", {})
    details = ["限動：Apify Stories；貼文：免登入公開端點／Apify。無需維護者 Instagram 登入。"]
    sections = {}
    for kind, provider, title in (("story", "apify_stories", "限動"), ("profile", "instagram_public", "貼文")):
        row = state.get(kind, {})
        selected = [s for s in sources if s.get("provider") == provider]
        successful = [entries.get(s["id"], {}) for s in selected if entries.get(s["id"], {}).get("last_success_at")]
        fresh = sum(age is not None and 0 <= age <= 24
                    for e in successful for age in [hours_since(parse_time(e["last_success_at"]), now)])
        latest = max((e["last_success_at"] for e in successful), default="")
        status = row.get("status") or "paused"
        age = hours_since(parse_time(latest), now)
        if status == "ok" and (age is None or age > 24):
            status = "degraded"
        reason = labels.get(row.get("reason"), row.get("reason")) or ("尚未成功抓取" if not latest else "")
        active = sum(1 for e in successful for p in e.get("posts", [])
                     if (expiry := parse_time(p.get("story_expires_at"))) and expiry > now) if kind == "story" else 0
        sections[kind] = {"status": status, "reason": reason, "lastSuccessAt": latest,
                          "checkedSources24h": fresh, "totalSources": len(selected), "activeStories": active,
                          "nextRunAt": dt.datetime.fromtimestamp(float(row.get("next_run_at") or 0), dt.timezone.utc).isoformat()}
        details.append(f"{title}：24 小時內成功檢查 {fresh}/{len(selected)} 個來源；最後成功 {time_label(parse_time(latest))}。")
        if reason:
            details.append(f"{title}狀態：{reason}。")
    quota = state.get("quota", {})
    pool = quota.get("pool")
    if isinstance(pool, dict):
        remaining = pool.get("remainingUsd")
        capacity = f"US${float(remaining):.3f}" if isinstance(remaining, (int, float)) else "尚未驗證"
        details.append(f"Apify 社群池可用授權額度 {capacity}；{pool.get('verifiedAccountCount', 0)} 個已驗證帳戶，{pool.get('unknownAccountCount', 0)} 個額度待確認。")
        details.append("依帳戶剩餘天數平均分配，Facebook、Instagram 貼文與限動各保障三分之一，沒用完的份額會在當天逐步釋出給其他兩項；完整執行上限先行保留，未確認費用不回補。")
        details.append("限動每批最多 10 個來源、10 筆；每個 Apify 帳戶每日最多 40 筆。")
    else:
        remaining = quota.get('remaining_usd')
        capacity = f"US${float(remaining):.3f}" if isinstance(remaining, (int, float)) else "尚未驗證"
        details.append(f"可用月額度 {capacity}；每日按剩餘天數分配，與 Facebook 共用。")
        details.append(f"額度週期結束：{time_label(parse_time(quota.get('cycle_end')))}；限動每批最多 10 個來源、10 筆，每帳戶每日最多 40 筆。")
    if state.get("quota_error"):
        details.append(f"額度檢查：{state['quota_error']}")
    statuses = [r["status"] for r in sections.values()]
    overall = "degraded" if "degraded" in statuses else "paused" if "paused" in statuses else "ok"
    result = component("instagram", "Instagram 擷取", overall,
                       f"免登入分批抓取；目前可顯示 {sections['story']['activeStories']} 筆限動。", details)
    result.update(stories=sections["story"], profiles=sections["profile"])
    return result


def build_status(*, offline: bool = False) -> dict[str, Any]:
    now = dt.datetime.now(dt.timezone.utc)
    sources = enabled_watch_sources()
    source_by_id = {str(source.get("id")): source for source in sources if source.get("id")}
    candidates = read_jsonl(SOCIAL_CANDIDATES)
    inbox = read_jsonl(SOCIAL_INBOX)
    errors = read_jsonl(SOCIAL_ERRORS)
    social_seen = read_json(SOCIAL_SEEN, {})
    social_fetch_state = read_json(SOCIAL_FETCH_STATE, {})
    instagram_public_state = read_json(PROJECT_ROOT / "state/instagram_public.json", {})
    pipeline_runtime = read_json(PIPELINE_RUNTIME_STATUS, {})
    social_progress = read_json(SOCIAL_FETCH_PROGRESS, {})
    latest_payload = read_json(LATEST_API, {})
    sources_payload = read_json(SOURCES_API, {})
    apify_ledger = read_json(APIFY_LEDGER, {})
    youtube_ledger = read_json(YOUTUBE_LEDGER, {})
    youtube_recovered_at = youtube_success_times(youtube_ledger)

    latest_generated_at = parse_time(latest_payload.get("generatedAt"))
    latest_data_mtime = file_mtime(LATEST_API)
    latest_error_at = max_time([parse_time(row.get("seen_at")) for row in errors])
    latest_social_seen_at = max_time(
        [latest_seen_at(candidates), latest_seen_at(inbox), latest_error_at, parse_time(social_seen.get("updated_at"))]
    )
    current_errors = []
    last_watchdog_run = social_seen.get("last_watchdog_run") if isinstance(social_seen.get("last_watchdog_run"), dict) else {}
    last_watchdog_started_at = parse_time(last_watchdog_run.get("started_at"))
    if last_watchdog_started_at is not None:
        current_errors = [
            row
            for row in errors
            if (seen_at := parse_time(row.get("seen_at"))) is not None and seen_at >= last_watchdog_started_at
        ]
    elif latest_social_seen_at is not None:
        lower_bound = latest_social_seen_at - dt.timedelta(seconds=CURRENT_ERROR_WINDOW_SECONDS)
        current_errors = [
            row
            for row in errors
            if (seen_at := parse_time(row.get("seen_at"))) is not None and seen_at >= lower_bound
        ]
    elif latest_error_at is not None:
        current_errors = [row for row in errors if parse_time(row.get("seen_at")) == latest_error_at]
    story_empty_errors = [row for row in current_errors if story_empty_error(row, source_by_id)]
    current_errors = [
        row
        for row in current_errors
        if is_active_source_error(row, source_by_id)
        and not youtube_error_superseded(row, youtube_recovered_at)
        and not story_empty_error(row, source_by_id)
        and not ignorable_instagram_profile_error(row, source_by_id)
        and not ignorable_threads_upstream_error(row, source_by_id)
    ]
    current_errors.extend(persistent_source_errors(social_fetch_state, source_by_id, current_errors))
    current_errors = [row for row in current_errors if not (
        row.get("source_type") in {"rsshub_instagram_profile", "rsshub_instagram_story"}
        and source_by_id.get(str(row.get("source_id")), {}).get("provider") in {"instagram_public", "apify_stories"})]
    for source_id, entry in instagram_public_state.get("sources", {}).items():
        if entry.get("status") == "error" and entry.get("error") and source_id in source_by_id:
            current_errors.append({"source_id": source_id, "source_type": source_by_id[source_id].get("type"),
                                   "error": entry["error"], "seen_at": dt.datetime.fromtimestamp(
                                       float(entry.get("last_attempt_at") or 0), dt.timezone.utc).isoformat()})

    annotated_current_errors = annotate_errors(current_errors, source_by_id)
    current_error_platforms = collections.Counter(row["platform"] for row in annotated_current_errors)
    current_error_types = collections.Counter(row["sourceType"] for row in annotated_current_errors)

    if offline:
        launch_agent = {"available": False, "status": "unknown", "summary": "Offline build: live service not checked."}
        rsshub_probe = {"ok": False, "statusCode": None, "elapsedMs": 0, "error": "Offline build: endpoint not probed."}
        apify = {"ok": False, "error": "Offline build: provider quota not checked."}
    else:
        launch_agent = launch_agent_status()
        rsshub_probe = probe_url("http://127.0.0.1:1200/")
        apify = apify_check()

    watch_platforms = source_counts(sources, "platform")
    watch_types = source_counts(sources, "type")
    updates_count = len(latest_payload.get("updates") or [])
    directory_count = int(sources_payload.get("count") or 0)
    latest_age = hours_since(latest_generated_at or latest_data_mtime, now)

    components: list[dict[str, Any]] = []

    pipeline_status = "ok"
    pipeline_details = [
        f"最新公開資料：{time_label(latest_generated_at or latest_data_mtime)}",
        f"pipeline.log 更新：{time_label(file_mtime(PIPELINE_LOG))}",
        f"pipeline.err.log 更新：{time_label(file_mtime(PIPELINE_ERR_LOG))}",
    ]
    runtime_heartbeat = parse_time(pipeline_runtime.get("heartbeatAt"))
    runtime_age = hours_since(runtime_heartbeat, now)
    runtime_step = str(pipeline_runtime.get("currentStep") or "")
    if (
        pipeline_runtime.get("status") == "running"
        and runtime_age is not None
        and runtime_age < 0.25
        and runtime_step != "build status page"
    ):
        pipeline_details.insert(
            0,
            "執行中："
            f"{runtime_step or pipeline_runtime.get('message') or 'pipeline'}；"
            f"PID {pipeline_runtime.get('pid') or '-'}；"
            f"heartbeat {time_label(runtime_heartbeat)}。",
        )
    elif pipeline_runtime.get("status") == "failed" and runtime_age is not None and runtime_age < FRESH_PIPELINE_HOURS:
        pipeline_status = "degraded"
        pipeline_details.insert(
            0,
            "最近 pipeline 失敗："
            f"{pipeline_runtime.get('currentStep') or pipeline_runtime.get('message') or '未記錄'}；"
            f"heartbeat {time_label(runtime_heartbeat)}。",
        )
    if latest_age is None or latest_age > FRESH_PIPELINE_HOURS:
        pipeline_status = "degraded"
        pipeline_details.append(f"公開資料超過 {FRESH_PIPELINE_HOURS} 小時未更新")
    if launch_agent.get("available"):
        pipeline_details.append(
            f"LaunchAgent：{launch_agent.get('state')}，last exit {launch_agent.get('lastExitCode')}"
        )
        if launch_agent.get("status") == "degraded":
            pipeline_status = "degraded"
    else:
        pipeline_details.append("LaunchAgent：本次快照無法讀取")
    components.append(
        component(
            "pipeline",
            "主排程與輸出",
            pipeline_status,
            "定期 pipeline 已產生公開資料快照。" if pipeline_status == "ok" else "排程或輸出時間需要檢查。",
            pipeline_details,
        )
    )

    api_status = "ok" if updates_count and directory_count else "degraded"
    components.append(
        component(
            "public-api",
            "公開 API",
            api_status,
            f"latest.json 有 {updates_count} 筆更新，sources.json 有 {directory_count} 筆公開目錄。",
            [
                f"更新視窗：{latest_payload.get('updatesWindowDays') or '-'} 天",
                f"watch sources：{len(sources)}",
            ],
        )
    )

    components.append(
        component(
            "rsshub",
            "RSSHub 服務",
            "ok" if rsshub_probe.get("ok") else "degraded",
            "本機 RSSHub 入口回 200。" if rsshub_probe.get("ok") else "本機 RSSHub 入口無法正常回應。",
            [
                f"HTTP：{rsshub_probe.get('statusCode') or '無回應'}",
                f"耗時：{rsshub_probe.get('elapsedMs')} ms",
            ],
        )
    )

    ig_error_types = {"rsshub_instagram_profile", "rsshub_instagram_story"}
    ig_errors = sum(
        1
        for row in annotated_current_errors
        if row["platform"] == "instagram" or row["sourceType"] in ig_error_types
    )
    ig_profile_errors = int(current_error_types.get("rsshub_instagram_profile") or 0)
    ig_story_errors = int(current_error_types.get("rsshub_instagram_story") or 0)
    instagram_run = last_watchdog_run.get("instagram") if isinstance(last_watchdog_run.get("instagram"), dict) else {}
    ig_deferred = int(instagram_run.get("deferred") or 0) if instagram_run else 0
    ig_status = "degraded" if ig_errors else ("paused" if ig_deferred else "ok")
    ig_profile_sources = watch_types.get("rsshub_instagram_profile", 0)
    ig_story_sources = watch_types.get("rsshub_instagram_story", 0)
    components.append(
        component(
            "instagram",
            "Instagram 擷取",
            ig_status,
            (
                f"{watch_platforms.get('instagram', 0)} 個 Instagram 來源"
                f"（profile {ig_profile_sources}、story {ig_story_sources}）；"
                f"目前錯誤 profile {ig_profile_errors}、story {ig_story_errors}。"
            ),
            [
                f"最新社群觀測：{time_label(latest_social_seen_at)}",
                f"錯誤拆分：profile {ig_profile_errors}、story {ig_story_errors}。",
                f"story 無公開內容/空路由略過：{len(story_empty_errors)}",
                *instagram_schedule_details(social_fetch_state, social_seen, social_progress, now),
            ],
        )
    )
    if any(s.get("provider") in {"instagram_public", "apify_stories"} for s in sources):
        components[-1] = public_instagram_component(
            instagram_public_state, sources, now)

    x_errors = current_error_platforms.get("x", 0)
    components.append(
        component(
            "x-twitter",
            "X / Twitter RSS",
            "degraded" if x_errors else "ok",
            f"{watch_platforms.get('x', 0)} 個 X 來源；最新抓取批次目前 {x_errors} 個錯誤。",
            [
                "目前 route 依 RSSHub 設定抓取。",
                "若持續 503，通常要檢查 RSSHub 的 Twitter API 設定。",
            ],
        )
    )

    latest_apify_run = apify_ledger.get("last_run") or (apify_ledger.get("runs") or [None])[-1] if isinstance(apify_ledger, dict) else None
    apify_errors = current_error_types.get("apify", 0)
    apify_status = "ok"
    apify_summary = f"{watch_platforms.get('facebook', 0)} 個 Facebook 來源。"
    apify_details = []
    if isinstance(latest_apify_run, dict):
        apify_details.append(f"最近成功 run：{time_label(parse_time(latest_apify_run.get('finished_at')))}")
        apify_details.append(f"最近新增 inbox：{latest_apify_run.get('new_inbox_rows', 0)}")
    if not apify.get("ok"):
        apify_status = "degraded"
        apify_details.append(f"Apify check：{apify.get('error')}")
    elif not apify.get("has_token"):
        apify_status = "degraded"
        apify_details.append("Apify check：未偵測到 token")
    else:
        due = int(apify.get("sources_due_count") or 0)
        minimum = int(apify.get("min_sources_per_run") or 0)
        selected = int(apify.get("sources_selected_count") or 0)
        apify_details.extend(
            [
                f"due sources：{due}",
                f"selected this check：{selected}",
                f"min sources per run：{minimum}",
                f"遠端月額度剩餘：{format_usd(apify.get('remote_monthly_remaining_usd'))}",
                f"規劃單次預算：{format_usd(apify.get('planned_run_budget_usd'))}",
            ]
        )
        if selected == 0 and minimum and due < minimum:
            apify_status = "paused"
            apify_summary += " 目前依預算 pacing 暫停開 run，等待 due 來源累積。"
        else:
            apify_summary += " Apify token/quota check 正常。"
    if apify_errors:
        apify_status = "degraded"
        apify_summary += f" 最新抓取批次有 {apify_errors} 個 Apify 錯誤。"
    components.append(component("facebook-apify", "Facebook Apify", apify_status, apify_summary, apify_details))

    latest_youtube_run = youtube_ledger.get("last_run") or (youtube_ledger.get("runs") or [None])[-1] if isinstance(youtube_ledger, dict) else None
    youtube_errors = current_error_types.get("youtube_ytdlp", 0)
    if isinstance(latest_youtube_run, dict):
        youtube_error_count = int(latest_youtube_run.get("error_count") or 0)
        youtube_finished = parse_time(latest_youtube_run.get("finished_at"))
        youtube_new_rows = latest_youtube_run.get("new_inbox_rows", 0)
    else:
        youtube_error_count = 0
        youtube_finished = None
        youtube_new_rows = 0
    components.append(
        component(
            "youtube",
            "YouTube yt-dlp",
            "degraded" if youtube_errors or youtube_error_count else "ok",
            f"{watch_platforms.get('youtube', 0)} 個 YouTube 來源；最近 run error_count={youtube_error_count}。",
            [
                f"最近完成：{time_label(youtube_finished)}",
                f"最近新增 inbox：{youtube_new_rows}",
            ],
        )
    )

    other_rss_errors = sum(
        count
        for platform, count in current_error_platforms.items()
        if platform not in {"instagram", "x", "facebook", "youtube"}
    )
    components.append(
        component(
            "other-rss",
            "Threads / 其他 RSS",
            "degraded" if other_rss_errors else "ok",
            f"{watch_platforms.get('threads', 0)} 個 Threads 來源；其他 RSS 最新抓取批次目前 {other_rss_errors} 個錯誤。",
            [f"RSS 類型來源：{watch_types.get('rss', 0)}"],
        )
    )

    degraded_components = [item for item in components if item["status"] in {"down", "degraded"}]
    paused_components = [item for item in components if item["status"] == "paused"]
    if degraded_components:
        overall_status = "degraded"
        degraded_names = "、".join(item["name"] for item in degraded_components)
        overall_summary = f"核心 pipeline 有產出；需要注意：{degraded_names}。"
    else:
        overall_status = "ok"
        overall_summary = "核心資料抓取與公開 API 正常。"
    if paused_components:
        paused_names = "、".join(item["name"] for item in paused_components)
        overall_summary += f" {paused_names} 目前依排程或預算節流。"

    platform_rows = []
    for platform, count in sorted(watch_platforms.items()):
        error_count = current_error_platforms.get(platform, 0)
        platform_status = "degraded" if error_count else "ok"
        if platform == "instagram":
            platform_status = next(c["status"] for c in components if c["id"] == "instagram")
        platform_rows.append(
            {
                "platform": platform,
                "sources": count,
                "currentErrors": error_count,
                "status": platform_status,
            }
        )

    status = {
        "generatedAt": taipei_iso(now),
        "site": PUBLIC_BASE_URL,
        "overall": {
            "status": overall_status,
            "label": STATUS_LABELS[overall_status],
            "summary": overall_summary,
        },
        "metrics": {
            "updates": updates_count,
            "updatesWindowDays": latest_payload.get("updatesWindowDays"),
            "directoryEntries": directory_count,
            "watchSources": len(sources),
            "currentErrors": len(annotated_current_errors),
            "latestDataAt": taipei_iso(latest_generated_at) if latest_generated_at else "",
            "latestSocialObservationAt": taipei_iso(latest_social_seen_at) if latest_social_seen_at else "",
        },
        "watchSources": {
            "platforms": watch_platforms,
            "types": watch_types,
            "platformRows": platform_rows,
        },
        "components": components,
        "recentErrors": annotated_current_errors[-20:],
        "runtime": {
            "pipeline": pipeline_runtime,
            "socialFetch": social_progress,
        },
    }
    if offline:
        status["probeMode"] = "offline"
        status["crawlFrequency"] = {"available": False, "estimate": True, "platforms": {}, "reason": "offline_build"}
        for item in status["components"]:
            if item["id"] in {"rsshub", "facebook-apify"}:
                item.update(status="unknown", label=STATUS_LABELS["unknown"],
                                 summary="Offline build: live availability and provider quota were not checked.", details=[])
        return status
    try:
        from apify_pool import crawl_schedule_snapshot
        status["crawlFrequency"] = crawl_schedule_snapshot(now=now.timestamp(), sources=sources)
    except (OSError, RuntimeError, ValueError):
        status["crawlFrequency"] = {"available": False, "estimate": True, "platforms": {}}
    return status


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def render_badge(status: str, label: str | None = None) -> str:
    return f'<span class="status-badge status-{html_escape(status)}">{html_escape(label or STATUS_LABELS.get(status, status))}</span>'


def render_metric(label: str, value: Any, note: str = "") -> str:
    return f"""
      <article class="status-metric-card">
        <span>{html_escape(label)}</span>
        <strong>{html_escape(value)}</strong>
        <p>{html_escape(note)}</p>
      </article>
    """


def render_component_card(item: dict[str, Any]) -> str:
    details = "".join(f"<li>{html_escape(detail)}</li>" for detail in item.get("details", []))
    details_html = f'<ul class="status-detail-list">{details}</ul>' if details else ""
    return f"""
      <article class="status-component-card status-card-{html_escape(item.get('status'))}">
        <div class="status-component-head">
          <h2>{html_escape(item.get('name'))}</h2>
          {render_badge(str(item.get('status')), str(item.get('label')))}
        </div>
        <p>{html_escape(item.get('summary'))}</p>
        {details_html}
      </article>
    """


def render_platform_rows(rows: list[dict[str, Any]]) -> str:
    rendered = []
    for row in rows:
        status = str(row.get("status") or "unknown")
        rendered.append(
            f"""
            <tr>
              <th scope="row">{html_escape(row.get('platform'))}</th>
              <td>{html_escape(row.get('sources'))}</td>
              <td>{html_escape(row.get('currentErrors'))}</td>
              <td>{render_badge(status)}</td>
            </tr>
            """
        )
    return "\n".join(rendered)


def render_error_list(errors: list[dict[str, Any]]) -> str:
    if not errors:
        return '<div class="empty-state">最新抓取批次沒有記錄中的錯誤。</div>'
    items = []
    for row in sorted(errors, key=lambda item: (item.get("platform") or "", item.get("sourceName") or "")):
        items.append(
            f"""
            <article class="status-error-item">
              <div>
                <span class="feed-latest-meta">{html_escape(row.get('seenAt'))} · {html_escape(row.get('platform'))}</span>
                <strong>{html_escape(row.get('sourceName'))}</strong>
              </div>
              <p>{html_escape(row.get('error'))}</p>
            </article>
            """
        )
    return "\n".join(items)


def render_status_page(status: dict[str, Any]) -> str:
    overall = status["overall"]
    metrics = status["metrics"]
    component_cards = "\n".join(render_component_card(item) for item in status["components"])
    platform_rows = render_platform_rows(status["watchSources"]["platformRows"])
    error_list = render_error_list(status["recentErrors"])
    return f"""<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>抓資料狀態｜臺灣口琴觀測站</title>
    <meta name="description" content="臺灣口琴觀測站資料抓取、RSSHub、Apify、YouTube 與公開 API 的最新健康狀態。">
    <meta name="robots" content="noindex,follow">
    <link rel="canonical" href="https://harmonica.observe.tw/status/">
    <meta property="og:title" content="抓資料狀態｜臺灣口琴觀測站">
    <meta property="og:description" content="臺灣口琴觀測站資料抓取、RSSHub、Apify、YouTube 與公開 API 的最新健康狀態。">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://harmonica.observe.tw/status/">
    <meta property="og:image" content="https://harmonica.observe.tw/assets/hero-harmonica-observe.webp">
    <meta property="og:site_name" content="臺灣口琴觀測站">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="抓資料狀態｜臺灣口琴觀測站">
    <meta name="twitter:description" content="臺灣口琴觀測站資料抓取、RSSHub、Apify、YouTube 與公開 API 的最新健康狀態。">
    <meta name="twitter:image" content="https://harmonica.observe.tw/assets/hero-harmonica-observe.webp">
    <script type="application/ld+json">
    {{
      "@context": "https://schema.org",
      "@type": "WebPage",
      "@id": "https://harmonica.observe.tw/status/#webpage",
      "url": "https://harmonica.observe.tw/status/",
      "name": "抓資料狀態｜臺灣口琴觀測站",
      "description": "臺灣口琴觀測站資料抓取、RSSHub、Apify、YouTube 與公開 API 的最新健康狀態。",
      "isPartOf": {{
        "@type": "WebSite",
        "@id": "https://harmonica.observe.tw/#website",
        "name": "臺灣口琴觀測站",
        "url": "https://harmonica.observe.tw/"
      }}
    }}
    </script>
    <link rel="icon" href="/assets/favicon-20260623.svg?v={ASSET_VERSION}" type="image/svg+xml">
    <link rel="stylesheet" href="/assets/styles.css?v={ASSET_VERSION}">
  </head>
  <body>
{HEADER_HTML}

    <main class="status-page-main">
      <section class="feed-page-hero status-hero">
        <div class="band-inner split-layout">
          <div>
            <p class="section-kicker">Status</p>
            <h1>抓資料狀態</h1>
          </div>
          <div class="feed-page-summary status-summary-panel">
            <div class="status-summary-line">
              {render_badge(overall["status"], overall["label"])}
              <strong>{html_escape(overall["summary"])}</strong>
            </div>
            <p>快照時間 {html_escape(status.get("generatedAt"))}</p>
            <div class="feed-links">
              <a href="/api/status.json">Status JSON</a>
              <a href="/api/latest.json">Latest API</a>
              <a href="/feeds/updates.xml">更新 RSS</a>
            </div>
          </div>
        </div>
      </section>

      <section class="band status-overview-band" aria-labelledby="status-overview-title">
        <div class="band-inner">
          <div class="section-heading">
            <div>
              <p class="section-kicker">Snapshot</p>
              <h2 id="status-overview-title">目前快照</h2>
            </div>
            <p class="data-date">資料時間 {html_escape(metrics.get("latestDataAt") or "未記錄")}</p>
          </div>
          <div class="status-metric-grid">
            {render_metric("公開更新", metrics.get("updates"), f"最近 {metrics.get('updatesWindowDays') or '-'} 天")}
            {render_metric("公開目錄", metrics.get("directoryEntries"), "sources.json")}
            {render_metric("監看來源", metrics.get("watchSources"), "social_sources.json")}
            {render_metric("目前錯誤", metrics.get("currentErrors"), "最新抓取批次")}
          </div>
        </div>
      </section>

      <section class="band status-component-band" aria-labelledby="status-components-title">
        <div class="band-inner">
          <div class="section-heading">
            <div>
              <p class="section-kicker">Collectors</p>
              <h2 id="status-components-title">元件狀態</h2>
            </div>
            <p class="data-date">最新社群觀測 {html_escape(metrics.get("latestSocialObservationAt") or "未記錄")}</p>
          </div>
          <div class="status-component-grid">
            {component_cards}
          </div>
        </div>
      </section>

      <section class="band status-platform-band" aria-labelledby="status-platform-title">
        <div class="band-inner split-layout">
          <div>
            <p class="section-kicker">Platforms</p>
            <h2 id="status-platform-title">平台來源</h2>
          </div>
          <div class="status-table-wrap">
            <table class="status-table">
              <thead>
                <tr>
                  <th scope="col">平台</th>
                  <th scope="col">來源數</th>
                  <th scope="col">目前錯誤</th>
                  <th scope="col">狀態</th>
                </tr>
              </thead>
              <tbody>
                {platform_rows}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="band status-errors-band" aria-labelledby="status-errors-title">
        <div class="band-inner">
          <div class="section-heading">
            <div>
              <p class="section-kicker">Latest Errors</p>
              <h2 id="status-errors-title">最新錯誤</h2>
            </div>
            <p class="data-date">最多顯示 20 筆</p>
          </div>
          <div class="status-error-list">
            {error_list}
          </div>
        </div>
      </section>
    </main>

    <footer class="site-footer">
      <div class="site-footer-inner">
        <div class="footer-brand">
          <span class="footer-title">臺灣口琴觀測站</span>
          <p>公開口琴活動、社團、貼文影片與補助資訊索引。</p>
        </div>
        <nav class="footer-links" aria-label="頁尾導覽">
          <a href="/feeds/">RSS</a>
          <a href="/submit/">資料回報</a>
          <a href="/api/latest.json">API</a>
          <a href="/sitemap.xml">Sitemap</a>
          <a href="https://github.com/skyhong2002/harmonica-observatory" target="_blank" rel="noreferrer">GitHub</a>
        </nav>
        <p class="footer-meta">只收錄公開可查資料 · 由 <a href="https://www.facebook.com/nycubmhc/" target="_blank" rel="noreferrer">陽明交大竹韻口琴社</a> 維運 · MIT License · © 2026 Sky Hong</p>
      </div>
    </footer>
  </body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Build cached status without network, credentials or live service probes.")
    args = parser.parse_args()
    status = build_status(offline=args.offline)
    STATUS_JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    STATUS_JSON_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    STATUS_PAGE_OUT.parent.mkdir(parents=True, exist_ok=True)
    status_html = "\n".join(line.rstrip() for line in render_status_page(status).splitlines()) + "\n"
    STATUS_PAGE_OUT.write_text(status_html, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": status["overall"]["status"],
                "components": {item["id"]: item["status"] for item in status["components"]},
                "status_json": str(STATUS_JSON_OUT.relative_to(PROJECT_ROOT)),
                "status_page": str(STATUS_PAGE_OUT.relative_to(PROJECT_ROOT)),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
