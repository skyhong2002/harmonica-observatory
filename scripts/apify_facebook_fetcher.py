#!/usr/bin/env python3
"""Fetch a small, budget-capped batch of public Facebook posts through Apify."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import apify_pool
from source_priority import affinity_of, event_affinity


PROJECT_ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
DEFAULT_INBOX = PROJECT_ROOT / "data" / "feeds" / "social_feed_inbox.jsonl"
DEFAULT_LEDGER = PROJECT_ROOT / "state" / "apify_facebook_fetcher.json"
DEFAULT_ERRORS = PROJECT_ROOT / "data" / "feeds" / "social_feed_errors.jsonl"

APIFY_BASE = "https://api.apify.com/v2"
FACEBOOK_POSTS_ACTOR = "apify/facebook-posts-scraper"
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}
DEFAULT_MAX_SOURCES_PER_RUN = 24
DEFAULT_MIN_SOURCES_PER_RUN = 8
DEFAULT_DAILY_BUDGET_USD = 0.0
DEFAULT_MONTHLY_BUDGET_USD = 4.0
DEFAULT_MAX_RUN_BUDGET_USD = 0.25
DEFAULT_BUDGET_PACING_MULTIPLIER = 1.25
DEFAULT_MIN_RUN_SPACING_DAYS = 0.0
GENERIC_FACEBOOK_NAMES = {
    "apify facebook posts",
    "apify/facebook-posts-scraper",
    "apify_facebook_posts",
    "facebook",
    "people",
}


PRIORITY_SOURCE_IDS = [
    "fb_ntubluesound",
    "fb_ntnu_harmonica",
    "fb_ncku_harmonica",
    "fb_nthuharmonica",
    "fb_fcu_harmonica",
    "fb_nutc_harmonica",
    "fb_csmu_bmharmonica",
    "fb_nkustharmonica",
    "fb_twharmonica",
    "fb_siriusharp",
    "fb_judys_harmonica_ensemble",
    "fb_punch_harp",
    "fb_harmonicasymphony",
    "fb_tcharmonicaa",
    "fb_harpdonuts",
    "fb_tcfsh_harmonica",
    "fb_hsnucozy",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


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


def read_token() -> tuple[str, str]:
    """Legacy internal helper; only credentials authorized for this project."""
    accounts = apify_pool.token_accounts()
    return (accounts[0]["token"], "harmonica_pool") if accounts else ("", "")


def actor_api_id(actor_id: str) -> str:
    return actor_id.replace("/", "~")


def apify_request(
    method: str,
    path: str,
    token: str,
    *,
    query: dict[str, Any] | None = None,
    body: Any | None = None,
    timeout: int = 60,
) -> Any:
    params = dict(query or {})
    url = APIFY_BASE + path + "?" + urllib.parse.urlencode(params)
    data = None
    headers = {"Accept": "application/json", "User-Agent": "HarmonicaObserveApifyFetcher/1.0",
               "Authorization": "Bearer " + token}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with apify_pool.open_request(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Apify HTTP {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("Apify network request failed") from None
    return json.loads(raw) if raw else {}


def load_facebook_sources(config_path: Path, source_ids: list[str]) -> list[dict[str, Any]]:
    config = load_json(config_path, {"sources": []})
    selected = set(source_ids)
    sources: list[dict[str, Any]] = []
    for source in config.get("sources", []):
        if source.get("type") != "facebook_page_posts":
            continue
        if not source.get("enabled", True):
            continue
        if selected and source.get("id") not in selected:
            continue
        if not (source.get("page") or source.get("url")):
            continue
        sources.append(source)
    return sources


def ledger_runs(ledger: dict[str, Any]) -> list[dict[str, Any]]:
    runs = ledger.get("runs")
    return runs if isinstance(runs, list) else []


def parse_ledger_datetime(value: Any) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def last_successful_run_at(ledger: dict[str, Any]) -> dt.datetime | None:
    for row in reversed(ledger_runs(ledger)):
        if row.get("actor") != FACEBOOK_POSTS_ACTOR:
            continue
        if row.get("status") != "SUCCEEDED" or row.get("error_count"):
            continue
        parsed = parse_ledger_datetime(row.get("finished_at") or row.get("started_at"))
        if parsed is not None:
            return parsed
    return None


def cadence_status(ledger: dict[str, Any], min_spacing_days: float) -> dict[str, Any]:
    last_run = last_successful_run_at(ledger)
    status: dict[str, Any] = {
        "min_run_spacing_days": min_spacing_days,
        "last_successful_run_at": last_run.isoformat() if last_run else None,
        "next_allowed_run_at": None,
        "cadence_ready": True,
    }
    if min_spacing_days <= 0 or last_run is None:
        return status
    now = dt.datetime.now(dt.timezone.utc)
    next_allowed = local_day_start_utc(last_run) + dt.timedelta(days=min_spacing_days)
    status["next_allowed_run_at"] = next_allowed.isoformat()
    if now < next_allowed:
        status["cadence_ready"] = False
        status["seconds_until_next_allowed"] = int((next_allowed - now).total_seconds())
    return status


def select_sources(sources: list[dict[str, Any]], ledger: dict[str, Any], max_sources: int) -> tuple[list[dict[str, Any]], int]:
    if max_sources <= 0 or max_sources >= len(sources):
        return sources, int(ledger.get("next_source_index") or 0)
    start = int(ledger.get("next_source_index") or 0) % len(sources)
    selected = [sources[(start + offset) % len(sources)] for offset in range(max_sources)]
    return selected, start


def select_priority_sources(sources: list[dict[str, Any]], max_sources: int) -> tuple[list[dict[str, Any]], int]:
    by_id = {str(source.get("id") or ""): source for source in sources}
    selected = [by_id[source_id] for source_id in PRIORITY_SOURCE_IDS if source_id in by_id]
    selected_ids = {str(source.get("id") or "") for source in selected}
    selected.extend(source for source in sources if str(source.get("id") or "") not in selected_ids)
    if max_sources > 0:
        selected = selected[:max_sources]
    return selected, 0


def source_run_stats(ledger: dict[str, Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for row in ledger_runs(ledger):
        finished = parse_ledger_datetime(row.get("finished_at") or row.get("started_at"))
        if finished is None:
            continue
        status = str(row.get("status") or "")
        for source_id in row.get("source_ids") or []:
            sid = str(source_id or "")
            if not sid:
                continue
            item = stats.setdefault(sid, {"attempt_count": 0, "success_count": 0})
            item["attempt_count"] += 1
            if item.get("last_attempted_at") is None or finished > item["last_attempted_at"]:
                item["last_attempted_at"] = finished
            if status == "SUCCEEDED" and sid in row.get("confirmed_source_ids", row.get("source_ids") or []):
                item["success_count"] += 1
                if item.get("last_successful_at") is None or finished > item["last_successful_at"]:
                    item["last_successful_at"] = finished
    return stats


def inbox_post_stats(path: Path, now: dt.datetime) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    if not path.exists():
        return stats
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("platform") != "facebook":
                continue
            sid = str(row.get("source_id") or "")
            if not sid:
                continue
            posted = parse_post_time(str(row.get("posted_at") or ""))
            if posted is not None and posted.year < 2005:
                posted = None
            item = stats.setdefault(sid, {"post_count": 0, "post_count_30d": 0, "post_count_90d": 0})
            item["post_count"] += 1
            if posted is None:
                continue
            if item.get("latest_post_at") is None or posted > item["latest_post_at"]:
                item["latest_post_at"] = posted
            age_days = (now - posted).total_seconds() / 86400
            if age_days <= 30:
                item["post_count_30d"] += 1
            if age_days <= 90:
                item["post_count_90d"] += 1
    return stats


def source_refresh_interval_days(source_id: str, post_stats: dict[str, Any], now: dt.datetime) -> float:
    if source_id in PRIORITY_SOURCE_IDS:
        return 2.0
    latest = post_stats.get("latest_post_at")
    if isinstance(latest, dt.datetime):
        age_days = (now - latest).total_seconds() / 86400
        if age_days <= 21:
            return 3.0
        if age_days <= 90:
            return 7.0
        return 21.0
    return 14.0


def select_adaptive_sources(
    sources: list[dict[str, Any]],
    ledger: dict[str, Any],
    inbox: Path,
    *,
    max_sources: int,
    min_sources: int,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    now = dt.datetime.now(dt.timezone.utc)
    run_stats = source_run_stats(ledger)
    post_stats = inbox_post_stats(inbox, now)
    affinity = event_affinity()
    scored: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    due_count = 0
    for source in sources:
        sid = str(source.get("id") or "")
        runs = run_stats.get(sid, {})
        posts = post_stats.get(sid, {})
        interval_days = source_refresh_interval_days(sid, posts, now)
        last_successful = runs.get("last_successful_at")
        if isinstance(last_successful, dt.datetime):
            days_since_success = (now - last_successful).total_seconds() / 86400
        else:
            days_since_success = 9999.0
        due = days_since_success >= interval_days
        if due:
            due_count += 1
        activity_bonus = min(1.5, float(posts.get("post_count_30d") or 0) * 0.25)
        priority_bonus = 1.0 if sid in PRIORITY_SOURCE_IDS else 0.0
        # Sources that announced events before are worth checking sooner.
        events = affinity_of(source, affinity)
        event_bonus = min(1.0, events * 0.25)
        score = (days_since_success / max(interval_days, 0.1)) + activity_bonus + priority_bonus + event_bonus
        scored.append(
            (
                score,
                source,
                {
                    "source_id": sid,
                    "due": due,
                    "refresh_interval_days": interval_days,
                    "days_since_success": None if days_since_success > 9000 else round(days_since_success, 2),
                    "latest_post_at": posts.get("latest_post_at").isoformat() if isinstance(posts.get("latest_post_at"), dt.datetime) else None,
                    "post_count_30d": posts.get("post_count_30d") or 0,
                    "event_posts": events,
                    "score": round(score, 3),
                },
            )
        )
    due_rows = [row for row in scored if row[2]["due"]]
    due_rows.sort(key=lambda row: row[0], reverse=True)
    selected_rows = due_rows[:max_sources] if max_sources > 0 else []
    min_needed = min(min_sources, len(sources))
    if 0 < len(selected_rows) < min_needed:
        selected_rows = []
    selected = [row[1] for row in selected_rows]
    return selected, 0, {
        "selection_mode": "adaptive",
        "sources_due_count": due_count,
        "min_sources_per_run": min_sources,
        "source_selection_notes": [
            row[2]
            for row in (selected_rows[:8] if selected_rows else due_rows[: min(8, len(due_rows))])
        ],
    }


def facebook_url(source: dict[str, Any]) -> str:
    url = str(source.get("url") or "").strip()
    if url.startswith("http://") or url.startswith("https://"):
        return url
    page = str(source.get("page") or "").strip().strip("/")
    if page.startswith("http://") or page.startswith("https://"):
        return page
    return f"https://www.facebook.com/{page}/" if page else ""


def apify_input(sources: list[dict[str, Any]], results_limit: int, days_back: int, include_video_transcript: bool) -> dict[str, Any]:
    data: dict[str, Any] = {
        "startUrls": [{"url": facebook_url(source)} for source in sources],
        "resultsLimit": results_limit,
        "captionText": include_video_transcript,
    }
    if days_back > 0:
        data["onlyPostsNewerThan"] = f"{days_back} days"
    return data


def estimate_max_charge_usd(results_limit: int, source_count: int) -> float:
    return round(0.006 + 0.005 * max(results_limit, 1) * max(source_count, 1), 4)


def max_sources_for_budget(budget_usd: float, results_limit: int, hard_max_sources: int) -> int:
    if budget_usd <= 0 or hard_max_sources <= 0:
        return 0
    for count in range(hard_max_sources, 0, -1):
        if estimate_max_charge_usd(results_limit, count) <= budget_usd:
            return count
    return 0


def remote_cycle_days_remaining(limits: dict[str, Any], now: dt.datetime) -> float:
    cycle = limits.get("cycle")
    if not isinstance(cycle, dict):
        return 30.0
    end = parse_ledger_datetime(cycle.get("endAt") or cycle.get("end_at"))
    if end is None or end <= now:
        return 1.0
    return max(1.0, (end - now).total_seconds() / 86400)


def budget_pacing_plan(
    remote_limits: dict[str, Any],
    *,
    source_count: int,
    results_limit: int,
    configured_max_sources: int,
    configured_min_sources: int,
    monthly_budget_usd: float,
    daily_budget_usd: float,
    max_run_budget_usd: float,
    pacing_multiplier: float,
    auto_budget_pacing: bool,
) -> dict[str, Any]:
    hard_max_sources = configured_max_sources if configured_max_sources > 0 else source_count
    hard_max_sources = max(0, min(hard_max_sources, source_count))
    if not auto_budget_pacing:
        return {
            "budget_pacing_mode": "static",
            "planned_run_budget_usd": max_run_budget_usd or daily_budget_usd or 0.0,
            "planned_max_sources_per_run": hard_max_sources,
            "planned_min_sources_per_run": min(configured_min_sources, hard_max_sources),
        }

    now = dt.datetime.now(dt.timezone.utc)
    current = float(remote_limits.get("monthly_usage_usd") or 0)
    account_limit = float(remote_limits.get("max_monthly_usage_usd") or 0)
    if monthly_budget_usd > 0 and account_limit > 0:
        effective_monthly_limit = min(monthly_budget_usd, account_limit)
    elif monthly_budget_usd > 0:
        effective_monthly_limit = monthly_budget_usd
    else:
        effective_monthly_limit = account_limit
    remote_remaining = max(0.0, effective_monthly_limit - current) if effective_monthly_limit > 0 else 0.0
    days_remaining = remote_cycle_days_remaining(remote_limits, now)
    paced_budget = remote_remaining / days_remaining if days_remaining > 0 else remote_remaining
    paced_budget *= max(0.1, pacing_multiplier)
    if daily_budget_usd > 0:
        paced_budget = min(paced_budget, daily_budget_usd)
    if max_run_budget_usd > 0:
        paced_budget = min(paced_budget, max_run_budget_usd)
    planned_run_budget = round(max(0.0, paced_budget), 4)
    planned_max_sources = max_sources_for_budget(planned_run_budget, results_limit, hard_max_sources)
    return {
        "budget_pacing_mode": "auto",
        "effective_monthly_budget_usd": round(effective_monthly_limit, 6) if effective_monthly_limit > 0 else 0.0,
        "remote_cycle_days_remaining": round(days_remaining, 2),
        "budget_pacing_multiplier": pacing_multiplier,
        "max_run_budget_usd": max_run_budget_usd,
        "planned_run_budget_usd": planned_run_budget,
        "planned_max_sources_per_run": planned_max_sources,
        "planned_min_sources_per_run": min(configured_min_sources, planned_max_sources),
        "planned_remote_remaining_usd": round(remote_remaining, 6),
    }


def fetch_user_limits(token: str) -> dict[str, Any]:
    data = apify_request("GET", "/users/me/limits", token, timeout=30).get("data", {})
    current = data.get("current") if isinstance(data.get("current"), dict) else {}
    limits = data.get("limits") if isinstance(data.get("limits"), dict) else {}
    return {
        "monthly_usage_usd": float(current.get("monthlyUsageUsd") or 0),
        "max_monthly_usage_usd": float(limits.get("maxMonthlyUsageUsd") or 0),
        "cycle": data.get("monthlyUsageCycle") or {},
    }


def run_cost(row: dict[str, Any]) -> float:
    # Preliminary event billing can lag; never restore a local daily allowance
    # below the full charge cap already authorized for the remote actor.
    amounts = [row.get(key) for key in ("usage_total_usd", "platform_usage_total_usd", "remote_usage_delta_usd",
                                       "charged_usd", "reserved_usd", "max_total_charge_usd")]
    return max((float(value) for value in amounts if isinstance(value, (int, float)) and value > 0), default=0.0)


def budget_window_cost(ledger: dict[str, Any], since: dt.datetime) -> float:
    total = 0.0
    for row in ledger_runs(ledger):
        raw = str(row.get("started_at") or row.get("created_at") or "")
        try:
            started = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=dt.timezone.utc)
        if started >= since:
            total += run_cost(row)
    return round(total, 6)


def local_day_start_utc(now: dt.datetime) -> dt.datetime:
    local_now = now.astimezone()
    local_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    return local_start.astimezone(dt.timezone.utc)


def enforce_budget(ledger: dict[str, Any], reserve_usd: float, daily_budget_usd: float, monthly_budget_usd: float) -> dict[str, float]:
    now = dt.datetime.now(dt.timezone.utc)
    day_start = local_day_start_utc(now)
    day_cost = budget_window_cost(ledger, day_start)
    month_cost = budget_window_cost(ledger, now - dt.timedelta(days=30))
    daily_remaining = 0.0
    monthly_remaining = 0.0
    if daily_budget_usd > 0:
        daily_remaining = round(max(0.0, daily_budget_usd - day_cost), 6)
        if day_cost >= daily_budget_usd:
            raise RuntimeError(
                f"Budget guard blocked run: local-day ledger {day_cost:.4f} >= daily {daily_budget_usd:.4f} USD"
            )
        if reserve_usd > 0 and day_cost + reserve_usd > daily_budget_usd:
            raise RuntimeError(
                f"Budget guard blocked run: local-day ledger {day_cost:.4f} + reserve {reserve_usd:.4f} > daily {daily_budget_usd:.4f} USD"
            )
    if monthly_budget_usd > 0:
        monthly_remaining = round(max(0.0, monthly_budget_usd - month_cost), 6)
        if month_cost >= monthly_budget_usd:
            raise RuntimeError(
                f"Budget guard blocked run: 30d ledger {month_cost:.4f} >= monthly {monthly_budget_usd:.4f} USD"
            )
        if reserve_usd > 0 and month_cost + reserve_usd > monthly_budget_usd:
            raise RuntimeError(
                f"Budget guard blocked run: 30d ledger {month_cost:.4f} + reserve {reserve_usd:.4f} > monthly {monthly_budget_usd:.4f} USD"
            )
    return {
        "daily_window_start": day_start.isoformat(),
        "daily_window_usd": day_cost,
        "daily_remaining_usd": daily_remaining,
        "last_30d_usd": month_cost,
        "monthly_remaining_usd": monthly_remaining,
    }


def enforce_remote_monthly_budget(limits: dict[str, Any], reserve_usd: float, monthly_budget_usd: float) -> dict[str, float]:
    current = float(limits.get("monthly_usage_usd") or 0)
    account_limit = float(limits.get("max_monthly_usage_usd") or 0)
    effective_limit = account_limit
    if monthly_budget_usd > 0:
        effective_limit = min(monthly_budget_usd, account_limit) if account_limit else monthly_budget_usd
    remaining = round(max(0.0, effective_limit - current), 6) if effective_limit > 0 else 0.0
    if effective_limit > 0 and current >= effective_limit:
        raise RuntimeError(
            f"Remote Apify budget guard blocked run: monthly usage {current:.4f} >= limit {effective_limit:.4f} USD"
        )
    if reserve_usd > 0 and effective_limit > 0 and current + reserve_usd > effective_limit:
        raise RuntimeError(
            f"Remote Apify budget guard blocked run: monthly usage {current:.4f} + reserve {reserve_usd:.4f} > limit {effective_limit:.4f} USD"
        )
    return {
        "remote_monthly_usage_usd": current,
        "remote_monthly_limit_usd": account_limit,
        "effective_remote_monthly_limit_usd": effective_limit,
        "remote_monthly_remaining_usd": remaining,
    }


def compact_text(value: Any, limit: int = 1800) -> str:
    if value is None:
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in str(value).splitlines()]
    if len(lines) <= 1:
        return re.sub(r"\s+", " ", str(value)).strip()[:limit]
    return "\n".join(line for line in lines if line).strip()[:limit]


def first_value(item: dict[str, Any], names: list[str]) -> Any:
    for name in names:
        value = item.get(name)
        if value not in (None, ""):
            return value
    return ""


def nested_first_value(item: Any, names: list[str]) -> Any:
    if isinstance(item, dict):
        direct = first_value(item, names)
        if direct:
            return direct
        for value in item.values():
            nested = nested_first_value(value, names)
            if nested:
                return nested
    elif isinstance(item, list):
        for value in item[:12]:
            nested = nested_first_value(value, names)
            if nested:
                return nested
    return ""


def nested_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("text", "title", "description", "name", "url"):
            if value.get(key):
                parts.append(str(value[key]))
        return " ".join(parts)
    if isinstance(value, list):
        return " ".join(nested_text(item) for item in value[:8])
    return ""


def looks_like_image_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold()
    suffix = Path(parsed.path).suffix.casefold()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        return True
    return any(marker in host for marker in ("fbcdn.net", "cdninstagram.com", "ytimg.com"))


def nested_image_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str) and value.startswith(("http://", "https://")) and looks_like_image_url(value):
        urls.append(value)
    elif isinstance(value, dict):
        for key in ("image", "imageUrl", "image_url", "url", "thumbnail", "thumbnailUrl", "displayUrl", "mediaUrl"):
            raw = value.get(key)
            if isinstance(raw, str) and raw.startswith(("http://", "https://")) and looks_like_image_url(raw):
                urls.append(raw)
        for key in ("attachments", "media", "images", "photos"):
            urls.extend(nested_image_urls(value.get(key)))
    elif isinstance(value, list):
        for item in value[:12]:
            urls.extend(nested_image_urls(item))
    result: list[str] = []
    for url in urls:
        if url not in result:
            result.append(url)
    return result


def is_actor_error_item(item: dict[str, Any]) -> bool:
    if not item.get("error"):
        return False
    has_post_fields = any(item.get(key) for key in ("url", "postUrl", "facebookUrl", "link", "permalink", "topLevelUrl"))
    return not has_post_fields


def parse_post_time(value: str) -> dt.datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.isdigit():
        timestamp = int(raw)
        if timestamp > 10_000_000_000:
            timestamp = int(timestamp / 1000)
        try:
            return dt.datetime.fromtimestamp(timestamp, tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
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


def local_recent_filter(rows: list[dict[str, Any]], max_age_days: int, now: dt.datetime) -> tuple[list[dict[str, Any]], int, int]:
    if max_age_days <= 0:
        return rows, 0, 0
    cutoff = now - dt.timedelta(days=max_age_days)
    kept: list[dict[str, Any]] = []
    dropped_old = 0
    dropped_undated = 0
    for row in rows:
        posted = parse_post_time(str(row.get("posted_at") or ""))
        if posted is None:
            dropped_undated += 1
            continue
        if posted < cutoff:
            dropped_old += 1
            continue
        kept.append(row)
    return kept, dropped_old, dropped_undated


def facebook_source_tokens(source: dict[str, Any]) -> set[str]:
    tokens: set[str] = set()
    page = str(source.get("page") or "").strip().strip("/")
    if page and not page.startswith(("http://", "https://")):
        tokens.add(page.casefold())

    raw_url = str(source.get("url") or "").strip()
    if raw_url.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(raw_url)
        path = urllib.parse.unquote(parsed.path).strip("/")
        parts = [part for part in path.split("/") if part]
        if parts and parts[0] not in {"p", "people", "pages", "profile.php"}:
            tokens.add(parts[0].casefold())
        for part in parts:
            match = re.search(r"(\d{8,})$", part)
            if match:
                tokens.add(match.group(1))
        query_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
        if query_id:
            tokens.add(query_id)
    return {token for token in tokens if token}


def is_generic_facebook_name(value: Any) -> bool:
    name = compact_text(value, 120).strip().strip("/").casefold()
    return name in GENERIC_FACEBOOK_NAMES


def is_usable_facebook_profile_url(value: Any) -> bool:
    url = compact_text(value, 500)
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold()
    if "facebook.com" not in host:
        return True
    path = urllib.parse.unquote(parsed.path).strip("/")
    if not path and not parsed.query:
        return False
    if path.casefold() == "people":
        return False
    if path.casefold() == "profile.php" and not urllib.parse.parse_qs(parsed.query).get("id"):
        return False
    return True


def facebook_source_name_aliases(source: dict[str, Any]) -> set[str]:
    raw = compact_text(source.get("name"), 180)
    if not raw or is_generic_facebook_name(raw):
        return set()
    aliases = {raw.casefold()}
    latin = " ".join(re.findall(r"[A-Za-z0-9][A-Za-z0-9'.-]*", raw)).strip()
    if latin:
        aliases.add(latin.casefold())
    for segment in re.split(r"[|｜/／()（）,，;；]+", raw):
        segment = compact_text(segment, 120)
        if segment:
            aliases.add(segment.casefold())
    result: set[str] = set()
    for alias in aliases:
        compact_alias = re.sub(r"\s+", " ", alias).strip()
        if len(compact_alias.replace(" ", "")) >= 4 or len(re.findall(r"[\u4e00-\u9fff]", compact_alias)) >= 3:
            result.add(compact_alias)
    return result


def match_source(item: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    url_fields = ["url", "postUrl", "facebookUrl", "pageUrl", "profileUrl", "userUrl", "link", "topLevelUrl"]
    urls = " ".join(compact_text(item.get(name)) for name in url_fields if item.get(name)).casefold()
    for source in sources:
        page = str(source.get("page") or "").strip("/").casefold()
        source_url = str(source.get("url") or "").strip("/").casefold()
        if page and page in urls:
            return source
        if source_url and source_url in urls:
            return source
        for token in facebook_source_tokens(source):
            if token.casefold() in urls or f"id={token}" in urls:
                return source
    account = compact_text(first_value(item, ["pageName", "profileName", "userName", "author", "ownerName"])).casefold()
    for source in sources:
        name = str(source.get("name") or "").casefold()
        if name and name in account:
            return source
        for token in facebook_source_tokens(source):
            if token.casefold() in account:
                return source
    item_text = compact_text(
        "\n".join(
            str(part)
            for part in [
                first_value(item, ["text", "message", "caption", "content", "description", "title"]),
                nested_text(item.get("attachments")),
                nested_text(item.get("media")),
                nested_text(item.get("externalLinks")),
            ]
            if part
        ),
        4000,
    ).casefold()
    haystack = re.sub(r"\s+", " ", "\n".join(part for part in [urls, account, item_text] if part)).strip()
    for source in sources:
        for alias in facebook_source_name_aliases(source):
            if alias in haystack:
                return source
    return sources[0] if len(sources) == 1 else None


def parse_count(value: Any) -> int | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    if isinstance(value, dict):
        total = 0
        found = False
        for nested_value in value.values():
            count = parse_count(nested_value)
            if count is None:
                continue
            total += count
            found = True
        return total if found else None
    if isinstance(value, list):
        total = 0
        found = False
        for nested_value in value:
            count = parse_count(nested_value)
            if count is None:
                continue
            total += count
            found = True
        return total if found else None
    text = str(value).strip()
    if not text:
        return None
    match = re.match(r"^([\d,.]+)\s*([kKmM萬万]?)$", text)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    suffix = match.group(2).casefold()
    if suffix == "k":
        number *= 1_000
    elif suffix == "m":
        number *= 1_000_000
    elif suffix in {"萬", "万"}:
        number *= 10_000
    return int(number) if number >= 0 else None


def dotted_value(item: Any, field: str) -> Any:
    value = item
    for part in field.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part)
        if value in (None, ""):
            return ""
    return value


def first_count(item: dict[str, Any], fields: list[str]) -> int | None:
    for field in fields:
        value = dotted_value(item, field) if "." in field else nested_first_value(item, [field])
        count = parse_count(value)
        if count is not None:
            return count
    return None


def reaction_breakdown(item: dict[str, Any]) -> dict[str, int]:
    reaction_fields = [
        "reactions",
        "reactionCounts",
        "reaction_counts",
        "reactionsCountByType",
        "topReactions",
        "feedback.reactions",
    ]
    result: dict[str, int] = {}
    for field in reaction_fields:
        value = dotted_value(item, field) if "." in field else nested_first_value(item, [field])
        if isinstance(value, dict):
            for key, raw_count in value.items():
                count = parse_count(raw_count)
                if count is not None:
                    result[str(key).strip().casefold()] = count
        elif isinstance(value, list):
            for row in value:
                if not isinstance(row, dict):
                    continue
                name = compact_text(first_value(row, ["type", "name", "reaction", "label"]))
                count = parse_count(first_value(row, ["count", "total", "value"]))
                if name and count is not None:
                    result[name.casefold()] = count
    return {key: value for key, value in result.items() if value >= 0}


def normalize_item(item: dict[str, Any], sources: list[dict[str, Any]]) -> dict[str, Any]:
    source = match_source(item, sources) or {"id": "apify_facebook_posts", "name": "Apify Facebook Posts", "page": ""}
    url = compact_text(first_value(item, ["url", "postUrl", "facebookUrl", "link", "permalink", "topLevelUrl"]))
    post_id = compact_text(first_value(item, ["postId", "id", "post_id", "legacyId", "shortCode"])) or url
    posted_at = compact_text(first_value(item, ["time", "timestamp", "date", "createdAt", "created_time", "publishedAt"]))
    raw_source_display_name = compact_text(
        first_value(item, ["pageName", "profileName", "authorName", "ownerName", "userName", "author"])
    )
    source_display_name = compact_text(
        ("" if is_generic_facebook_name(raw_source_display_name) else raw_source_display_name)
        or source.get("name")
        or source.get("id")
        or "Facebook"
    )
    raw_source_profile_url = compact_text(first_value(item, ["pageUrl", "profileUrl", "userUrl", "authorUrl", "ownerProfileUrl"]))
    source_profile_url = raw_source_profile_url if is_usable_facebook_profile_url(raw_source_profile_url) else facebook_url(source)
    text_parts = [
        first_value(item, ["text", "message", "caption", "content", "description", "title"]),
        nested_text(item.get("attachments")),
        nested_text(item.get("media")),
        nested_text(item.get("externalLinks")),
    ]
    images = nested_image_urls(item)
    source_avatar = compact_text(
        nested_first_value(item, ["profilePic", "profilePicture", "profileImage", "pageProfilePicture", "avatar", "authorProfilePic"])
    )
    raw_account = first_value(item, ["pageName", "profileName", "userName", "author"])
    account = source.get("page") or source.get("url") or ("" if is_generic_facebook_name(raw_account) else raw_account)
    reactions = reaction_breakdown(item)
    like_count = first_count(item, ["likeCount", "likesCount", "likes", "likes_count"])
    if like_count is None:
        like_count = reactions.get("like")
    reaction_count = first_count(
        item,
        [
            "reactionCount",
            "reactionsCount",
            "totalReactionCount",
            "total_reactions",
            "feedback.reaction_count",
        ],
    )
    if reaction_count is None and reactions:
        reaction_count = sum(reactions.values())
    return {
        "account": account,
        "image_url": images[0] if images else "",
        "images": images[:5],
        "platform": "facebook",
        "post_id": post_id,
        "posted_at": posted_at,
        "raw_source": FACEBOOK_POSTS_ACTOR,
        "source_avatar_url": source_avatar,
        "source_id": source.get("id") or "apify_facebook_posts",
        "source_display_name": source_display_name,
        "source_name": source.get("name") or source.get("id") or "Apify Facebook Posts",
        "source_profile_url": source_profile_url,
        "text": compact_text("\n".join(str(part) for part in text_parts if part)),
        "url": url,
        "like_count": like_count,
        "comment_count": first_count(item, ["commentCount", "commentsCount", "comments", "comments_count"]),
        "share_count": first_count(item, ["shareCount", "sharesCount", "shares", "shares_count"]),
        "reaction_count": reaction_count,
        "reactions": reactions,
        "view_count": first_count(item, ["viewCount", "viewsCount", "views", "playCount", "videoViews", "videoViewCount"]),
    }


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


def filter_new_rows(rows: list[dict[str, Any]], inbox: Path) -> list[dict[str, Any]]:
    seen = existing_inbox_keys(inbox)
    result = []
    for row in rows:
        key = f"{row.get('source_id')}:{row.get('post_id') or row.get('url')}"
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def run_actor(
    token: str,
    sources: list[dict[str, Any]],
    *,
    results_limit: int,
    days_back: int,
    max_items: int,
    max_total_charge_usd: float | None,
    memory_mbytes: int,
    timeout_secs: int,
    poll_secs: float,
    include_video_transcript: bool,
    reservation_id: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    actor_id = actor_api_id(FACEBOOK_POSTS_ACTOR)
    body = apify_input(sources, results_limit, days_back, include_video_transcript)
    query = {
        "maxItems": max_items,
        "memory": memory_mbytes,
        "timeout": timeout_secs,
        "restartOnError": "false",
    }
    if max_total_charge_usd is not None and max_total_charge_usd > 0:
        query["maxTotalChargeUsd"] = round(max_total_charge_usd, 4)
    run_data = apify_request(
        "POST",
        f"/acts/{actor_id}/runs",
        token,
        query=query,
        body=body,
        timeout=60,
    ).get("data", {})
    run_id = run_data.get("id")
    if not run_id:
        raise RuntimeError("Apify did not return a run id; budget remains reserved")

    if reservation_id:
        apify_pool.record_run_started(reservation_id, run_id)

    deadline = time.monotonic() + timeout_secs + 45
    while run_data.get("status") not in TERMINAL_STATUSES:
        if time.monotonic() > deadline:
            raise RuntimeError(f"Timed out waiting for Apify run {run_id}; current status={run_data.get('status')}")
        time.sleep(poll_secs)
        run_data = apify_request("GET", f"/actor-runs/{run_id}", token, timeout=30).get("data", {})

    dataset_id = run_data.get("defaultDatasetId")
    items: list[dict[str, Any]] = []
    if dataset_id and run_data.get("status") == "SUCCEEDED":
        items_data = apify_request(
            "GET",
            f"/datasets/{dataset_id}/items",
            token,
            query={"format": "json", "clean": "true", "limit": max_items},
            timeout=60,
        )
        items = items_data if isinstance(items_data, list) else []
    return run_data, items


def usage_total_usd(run_data: dict[str, Any]) -> float | None:
    for key in ("usageTotalUsd", "usageUsd", "costUsd"):
        value = run_data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    usage = run_data.get("usage") or {}
    if isinstance(usage, dict):
        total = usage.get("totalUsd") or usage.get("totalUSd")
        if isinstance(total, (int, float)):
            return float(total)
    return None


def main() -> int:
    from run_pipeline import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--source-id", action="append", default=[])
    parser.add_argument("--priority", action="store_true")
    parser.add_argument("--full-refresh", action="store_true")
    parser.add_argument(
        "--selection-mode",
        choices=("adaptive", "round-robin"),
        default=os.environ.get("HARMONICA_APIFY_SELECTION_MODE", "adaptive"),
    )
    parser.add_argument(
        "--max-sources-per-run",
        type=int,
        default=env_int("HARMONICA_APIFY_MAX_SOURCES_PER_RUN", DEFAULT_MAX_SOURCES_PER_RUN),
    )
    parser.add_argument(
        "--min-sources-per-run",
        type=int,
        default=env_int("HARMONICA_APIFY_MIN_SOURCES_PER_RUN", DEFAULT_MIN_SOURCES_PER_RUN),
    )
    parser.add_argument("--results-limit", type=int, default=5)
    parser.add_argument("--days-back", type=int, default=30)
    parser.add_argument("--local-max-post-age-days", type=int, default=30)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--max-total-charge-usd", type=float, default=0.0)
    parser.add_argument(
        "--daily-budget-usd",
        type=float,
        default=env_float("HARMONICA_APIFY_DAILY_BUDGET_USD", DEFAULT_DAILY_BUDGET_USD),
    )
    parser.add_argument(
        "--monthly-budget-usd",
        type=float,
        default=env_float("HARMONICA_APIFY_MONTHLY_BUDGET_USD", DEFAULT_MONTHLY_BUDGET_USD),
    )
    parser.add_argument(
        "--max-run-budget-usd",
        type=float,
        default=env_float("HARMONICA_APIFY_MAX_RUN_BUDGET_USD", DEFAULT_MAX_RUN_BUDGET_USD),
    )
    parser.add_argument(
        "--budget-pacing-multiplier",
        type=float,
        default=env_float("HARMONICA_APIFY_BUDGET_PACING_MULTIPLIER", DEFAULT_BUDGET_PACING_MULTIPLIER),
    )
    parser.add_argument("--no-auto-budget-pacing", dest="auto_budget_pacing", action="store_false")
    parser.add_argument(
        "--min-run-spacing-days",
        type=float,
        default=env_float("HARMONICA_APIFY_MIN_RUN_SPACING_DAYS", DEFAULT_MIN_RUN_SPACING_DAYS),
    )
    parser.add_argument("--memory-mbytes", type=int, default=1024)
    parser.add_argument("--timeout-secs", type=int, default=900)
    parser.add_argument("--poll-secs", type=float, default=5.0)
    parser.add_argument("--include-video-transcript", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    all_sources = load_facebook_sources(args.config, args.source_id)
    ledger = load_json(args.ledger, {"runs": [], "next_source_index": 0})
    # Read-only quota refresh; all billable requests require a later atomic pool
    # reservation. Owner caps are per account, so community capacity adds usable
    # collection capacity rather than hitting the old global owner ledger cap.
    os.environ["HARMONICA_APIFY_MONTHLY_BUDGET_USD"] = str(args.monthly_budget_usd)
    pool = apify_pool.pool_status(refresh=args.run or args.check)
    token, token_source = "", "harmonica_pool"
    remote_limits = {}
    remote_budget_fetch_error = ""
    available = pool["platforms"]["facebook"]["maxRunBudgetUsd"]
    run_budget = min(available, args.max_run_budget_usd) if args.max_run_budget_usd > 0 else available
    if args.daily_budget_usd > 0:
        day_start = local_day_start_utc(dt.datetime.now(dt.timezone.utc))
        run_budget = min(run_budget, max(0.0, args.daily_budget_usd - budget_window_cost(ledger, day_start)))
    if args.max_total_charge_usd > 0:
        run_budget = min(run_budget, args.max_total_charge_usd)
    use_auto_budget_pacing = True
    pacing_status = {
        "budget_pacing_mode": "community_pool",
        "planned_run_budget_usd": round(run_budget, 6),
        "planned_max_sources_per_run": max_sources_for_budget(run_budget, args.results_limit,
            min(args.max_sources_per_run or len(all_sources), len(all_sources))),
        "planned_min_sources_per_run": 0,
        "pool": pool,
    }

    if args.full_refresh or args.source_id:
        max_sources = int(pacing_status.get("planned_max_sources_per_run") or 0)
    elif use_auto_budget_pacing:
        max_sources = int(pacing_status.get("planned_max_sources_per_run") or 0)
    else:
        max_sources = args.max_sources_per_run if args.max_sources_per_run > 0 else len(all_sources)
    min_sources = int(pacing_status.get("planned_min_sources_per_run") if use_auto_budget_pacing else args.min_sources_per_run)
    selection_status: dict[str, Any] = {"selection_mode": args.selection_mode}
    if args.run and max_sources <= 0:
        print(json.dumps({"ok": True, "skipped": True, "skip_reason": "pool_budget_pacing_wait", **pacing_status}))
        return 0
    if args.full_refresh:
        sources, start_index = select_sources(all_sources, ledger, max_sources)
        selection_status["selection_mode"] = "full-refresh"
    elif args.source_id:
        sources, start_index = select_sources(all_sources, ledger, max_sources)
        selection_status["selection_mode"] = "explicit-source-id"
    elif args.priority:
        sources, start_index = select_priority_sources(all_sources, max_sources)
        selection_status["selection_mode"] = "priority"
    elif args.selection_mode == "adaptive":
        sources, start_index, selection_status = select_adaptive_sources(
            all_sources,
            ledger,
            args.inbox,
            max_sources=max_sources,
            min_sources=max(0, min_sources),
        )
    else:
        sources, start_index = select_sources(all_sources, ledger, max_sources)
    run_cadence = cadence_status(ledger, args.min_run_spacing_days)
    if args.run and not sources:
        skip_reason = "budget_pacing_wait" if int(pacing_status.get("planned_max_sources_per_run") or 0) <= 0 else "no_due_facebook_sources"
        print(json.dumps({
            "ok": True,
            "skipped": True,
            "skip_reason": skip_reason,
            "actor": FACEBOOK_POSTS_ACTOR,
            "sources_total": len(all_sources),
            **pacing_status,
            **selection_status,
        }, ensure_ascii=False, indent=2))
        return 0
    if args.run and not args.force and not run_cadence["cadence_ready"]:
        print(json.dumps({
            "ok": True,
            "skipped": True,
            "skip_reason": "recent_successful_apify_run",
            "actor": FACEBOOK_POSTS_ACTOR,
            "sources_total": len(all_sources),
            "sources_selected_count": len(sources),
            **run_cadence,
        }, ensure_ascii=False, indent=2))
        return 0
    max_items = args.max_items if args.max_items > 0 else max(args.results_limit * max(len(sources), 1), max(len(sources), 1))
    estimated_actor_price_usd = estimate_max_charge_usd(args.results_limit, len(sources)) if sources else 0.0
    actor_spend_cap_usd = round(min(run_budget, estimated_actor_price_usd), 4) if sources and run_budget > 0 else None
    reserve = actor_spend_cap_usd or 0.0
    budget_status = {"monthly_remaining_usd": pool.get("remainingUsd"),
                     "daily_remaining_usd": available, "owner_monthly_cap_usd": args.monthly_budget_usd}
    remote_budget_status = {"remote_monthly_remaining_usd": pool.get("remainingUsd")}

    plan = {
        "actor": FACEBOOK_POSTS_ACTOR,
        "sources_total": len(all_sources),
        "sources_selected": [{"id": s.get("id"), "page": s.get("page"), "url": s.get("url"), "name": s.get("name")} for s in sources],
        "sources_selected_count": len(sources),
        "selected_start_index": start_index,
        "results_limit": args.results_limit,
        "days_back": args.days_back,
        "local_max_post_age_days": args.local_max_post_age_days,
        "max_items": max_items,
        "independent_actor_cap_usd": args.max_total_charge_usd or None,
        "actor_spend_cap_usd": actor_spend_cap_usd,
        "reserve_usd_for_budget_guard": reserve,
        "estimated_actor_price_usd": estimated_actor_price_usd,
        "daily_budget_usd": args.daily_budget_usd,
        "monthly_budget_usd": args.monthly_budget_usd,
        "force": args.force,
        "ledger": str(args.ledger),
        "inbox": str(args.inbox),
        "has_token": pool["accountCount"] > 0,
        "token_source": token_source,
        "auto_budget_pacing": args.auto_budget_pacing,
        **pacing_status,
        **selection_status,
        **run_cadence,
        **budget_status,
        **remote_budget_status,
    }

    if args.check or not args.run:
        print(json.dumps({"dry_run": not args.run, **plan}, ensure_ascii=False, indent=2))
        return 0

    if not actor_spend_cap_usd:
        raise SystemExit("Apify pool has no verified budget available for this run.")
    if not sources:
        raise SystemExit("No enabled facebook_page_posts sources selected.")
    if args.results_limit < 1 or args.results_limit > 20:
        raise SystemExit("--results-limit must stay between 1 and 20 for this budget-capped fetcher.")
    if max_items < 1 or max_items > 2000:
        raise SystemExit("--max-items must stay between 1 and 2000 for this budget-capped fetcher.")

    started_at = dt.datetime.now(dt.timezone.utc).isoformat()
    errors: list[dict[str, Any]] = []
    remote_before = {}
    apify_pool.verify_actor_cap(FACEBOOK_POSTS_ACTOR, actor_spend_cap_usd)
    reservation = apify_pool.reserve_run("facebook", actor_spend_cap_usd, source_count=len(sources))
    token = reservation["token"]
    try:
        run_data, items = run_actor(
            token,
            sources,
            results_limit=args.results_limit,
            days_back=args.days_back,
            max_items=max_items,
            max_total_charge_usd=actor_spend_cap_usd,
            memory_mbytes=args.memory_mbytes,
            timeout_secs=args.timeout_secs,
            poll_secs=args.poll_secs,
            include_video_transcript=args.include_video_transcript,
            reservation_id=reservation["id"],
        )
        apify_pool.finish_run(reservation["id"], status=run_data.get("status"),
                              actual_cost_usd=usage_total_usd(run_data), actor_run_id=run_data.get("id"))
        if run_data.get("status") != "SUCCEEDED":
            raise RuntimeError("Apify Facebook run did not succeed")
        actor_error_items = [item for item in items if is_actor_error_item(item)]
        post_items = [item for item in items if not is_actor_error_item(item)]
        rows = [normalize_item(item, sources) for item in post_items]
        rows = [row for row in rows if row.get("url") or row.get("text")]
        confirmed_source_ids = sorted({row["source_id"] for row in rows if row.get("source_id")})
        rows, dropped_old, dropped_undated = local_recent_filter(
            rows,
            args.local_max_post_age_days,
            dt.datetime.now(dt.timezone.utc),
        )
        new_rows = filter_new_rows(rows, args.inbox)
        if not args.no_write:
            append_jsonl(args.inbox, new_rows)
    except Exception as exc:
        errors.append({"source_id": "apify_facebook_posts", "source_type": "apify", "error": str(exc).replace(token, "[redacted]")})
        append_errors(args.errors, errors)
        run_data = {"id": "", "status": "LOCAL_ERROR"}
        items = []
        actor_error_items = []
        post_items = []
        dropped_old = 0
        dropped_undated = 0
        new_rows = []
        confirmed_source_ids = []

    remote_after = {}
    platform_usage = usage_total_usd(run_data)
    remote_delta = None
    if remote_after:
        remote_delta = round(
            max(0.0, float(remote_after.get("monthly_usage_usd") or 0) - float(remote_before.get("monthly_usage_usd") or 0)),
            6,
        )
    charge_candidates = [
        value
        for value in (remote_delta, platform_usage)
        if isinstance(value, (int, float)) and value > 0
    ]
    charged = max(charge_candidates) if charge_candidates else None
    if all_sources:
        ledger["next_source_index"] = (start_index + len(sources)) % len(all_sources)
    record = {
        "started_at": started_at,
        "finished_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "actor": FACEBOOK_POSTS_ACTOR,
        "run_id": run_data.get("id"),
        "status": run_data.get("status"),
        "source_ids": [source.get("id") for source in sources],
        "confirmed_source_ids": confirmed_source_ids,
        "pool_reservation_id": reservation["id"],
        "results_limit": args.results_limit,
        "days_back": args.days_back,
        "local_max_post_age_days": args.local_max_post_age_days,
        "max_items": max_items,
        "max_total_charge_usd": args.max_total_charge_usd or None,
        "actor_spend_cap_usd": actor_spend_cap_usd,
        "reserved_usd": reserve,
        "selection_mode": selection_status.get("selection_mode"),
        "budget_pacing_mode": pacing_status.get("budget_pacing_mode"),
        "planned_run_budget_usd": pacing_status.get("planned_run_budget_usd"),
        "planned_max_sources_per_run": pacing_status.get("planned_max_sources_per_run"),
        "usage_total_usd": charged,
        "platform_usage_total_usd": platform_usage,
        "remote_monthly_usage_before_usd": remote_before.get("monthly_usage_usd"),
        "remote_monthly_usage_after_usd": remote_after.get("monthly_usage_usd"),
        "remote_usage_delta_usd": remote_delta,
        "dataset_item_count": len(items),
        "actor_error_item_count": len(actor_error_items),
        "item_count": len(post_items),
        "dropped_old_rows": dropped_old,
        "dropped_undated_rows": dropped_undated,
        "new_inbox_rows": len(new_rows),
        "error_count": len(errors),
    }
    ledger.setdefault("runs", []).append(record)
    ledger["updated_at"] = record["finished_at"]
    ledger["runs"] = ledger_runs(ledger)[-200:]
    save_json(args.ledger, ledger)

    output = {
        "ok": not errors,
        "record": record,
        "new_rows": new_rows[:5],
        "actor_error_items": [
            {
                "inputUrl": item.get("inputUrl"),
                "error": item.get("error"),
                "errorDescription": item.get("errorDescription"),
            }
            for item in actor_error_items[:10]
        ],
        "errors": errors,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
