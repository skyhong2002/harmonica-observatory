#!/usr/bin/env python3
"""Opt-in InstaStoriesViewer diagnostics and bounded standalone backup collector.

Only an explicit, completed stories response can establish an empty result.
HTML placeholders, missing dates and transport errors are not empty success.
Some service backends omit original IDs and times: those rows are never imported.
The normal Apify path is preserved. Scheduled backup is opt-in and bounded.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from story_lifecycle import display_expiry

PROVIDER = "insta_stories_viewer"
UTC = dt.timezone.utc
MAX_INPUT_BYTES = 2_000_000
MAX_MEDIA_BYTES = 10_000_000


def publication_time(value: Any) -> str | None:
    """Accept explicit Unix seconds or timezone-aware ISO, never infer from ID."""
    try:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, (float, int)):
            if not math.isfinite(value) or value <= 0:
                return None
            parsed = dt.datetime.fromtimestamp(value, UTC)
        else:
            parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
        return parsed.astimezone(UTC).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def classify_result(payload: Any, username: str) -> dict:
    """Parse the site's searchResult event envelope (not a documented API)."""
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
        return {"status": "service_failed", "reason": "invalid_envelope", "items": []}
    data = payload["data"]
    if data.get("serverType") not in {"stories", "stories-posts"}:
        return {"status": "loading", "reason": "stories_not_completed", "items": []}
    if data.get("status") == "error":
        code = data.get("code")
        status = {404: "not_found", 403: "private", 429: "rate_limited"}.get(code, "service_failed")
        return {"status": status, "reason": f"provider_{code}", "items": []}
    if data.get("status") != "success":
        return {"status": "loading", "reason": "no_success_evidence", "items": []}
    user = data.get("user")
    if not isinstance(user, dict):
        return {"status": "service_failed", "reason": "missing_user", "items": []}
    if str(user.get("username", "")).casefold() != username.casefold():
        return {"status": "service_failed", "reason": "account_mismatch", "items": []}
    if user.get("is_private"):
        return {"status": "private", "reason": "private_account", "items": []}
    reels = user.get("reels")
    if not isinstance(reels, list) or not all(isinstance(item, dict) for item in reels):
        return {"status": "service_failed", "reason": "missing_reels", "items": []}
    return {"status": "stories" if reels else "empty", "reason": "completed", "items": reels}


def eligible_items(items: list[dict], now: float) -> tuple[list[dict], list[dict]]:
    """Filter before downloading; retain provider expiry separately when present.

    These explicit date field names are accepted only if the response supplies
    them. A filename, story ID, request time or profile update time is not a date.
    """
    accepted, rejected, seen = [], [], set()
    for item in items:
        ident = str(item.get("id") or "")
        posted = publication_time(item.get("taken_at_timestamp", item.get("taken_at")))
        reason = ""
        if not ident.isdigit():
            reason = "invalid_id"
        elif ident in seen:
            reason = "duplicate"
        elif not posted:
            reason = "missing_publication_time"
        elif dt.datetime.fromisoformat(posted).timestamp() > now:
            reason = "future_publication_time"
        elif display_expiry({"posted_at": posted}).timestamp() <= now:
            reason = "display_expired"
        if reason:
            rejected.append({"id": ident if ident.isdigit() else None, "reason": reason})
            continue
        seen.add(ident)
        accepted.append({**item, "id": ident, "posted_at": posted,
                         "source_expires_at": publication_time(item.get("expiring_at"))})
    return accepted, rejected


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_media(opaque_value: str, *, opener=None, consume=None) -> dict:
    """Bounded download using the site's unmodified public CDN image mechanism.

    The opaque value comes from display_url in a normally obtained result. It is
    used exactly like the site's image element and is never included in output.
    No cookies, redirects, retries, media files or production cache writes.
    """
    if not isinstance(opaque_value, str) or not opaque_value or len(opaque_value) > 16384:
        return {"status": "download_failed", "reason": "missing_media"}
    url = "https://cdn.insta-stories-viewer.com/img.php?url=" + urllib.parse.quote(opaque_value, safe="")
    request = urllib.request.Request(url, headers={"User-Agent": "HarmonicaObserveDiagnostic/1.0"})
    open_url = opener or urllib.request.build_opener(NoRedirect()).open
    started = time.monotonic()
    try:
        with open_url(request, timeout=25) as response:
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if not content_type.startswith(("image/", "video/")):
                body = response.read(65536).lower()
                if any(marker in body for marker in (b"captcha", b"cf-chl-", b"verify you are human", b"just a moment")):
                    return {"status": "verification_required", "reason": "challenge_page"}
                return {"status": "download_failed", "reason": "unexpected_content_type"}
            digest, length, chunks = hashlib.sha256(), 0, []
            while True:
                if time.monotonic() - started > 30:
                    return {"status": "download_failed", "reason": "deadline"}
                block = response.read(min(65536, MAX_MEDIA_BYTES + 1 - length))
                if not block:
                    break
                length += len(block)
                if length > MAX_MEDIA_BYTES:
                    return {"status": "download_failed", "reason": "size_limit"}
                digest.update(block)
                if consume:
                    chunks.append(block)
            if not length:
                return {"status": "download_failed", "reason": "empty_body"}
            if consume:
                consume(b"".join(chunks), content_type)
            return {"status": "downloaded", "bytes": length, "content_type": content_type,
                    "sha256": digest.hexdigest(), "seconds": round(time.monotonic() - started, 3)}
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        return {"status": "rate_limited" if code == 429 else "access_blocked" if code in {401, 403} else "download_failed",
                "reason": f"http_{code}"}
    except (OSError, TimeoutError, ValueError):
        return {"status": "download_failed", "reason": "network_error"}


def diagnose(payload: Any, username: str, now: float, *, download=None, cached_posts=()) -> dict:
    result = classify_result(payload, username)
    items = result.pop("items")
    eligible, rejected = eligible_items(items, now)
    known_ids = {str(p.get("post_id")) for p in cached_posts}
    media = []
    if download and items:
        item = items[0]
        value = item.get("display_url") or item.get("thumbnail_src")
        media.append(download(value))
    result.update(account=username, provider=PROVIDER, observed_at=publication_time(now),
                  story_count=len(items) if result["status"] in {"stories", "empty"} else None,
                  eligible_count=len(eligible), rejections=rejected,
                  numeric_ids=sum(str(i.get("id", "")).isdigit() for i in items),
                  explicit_publication_times=sum(publication_time(i.get("taken_at_timestamp", i.get("taken_at"))) is not None for i in items),
                  explicit_source_expiries=sum(publication_time(i.get("expiring_at")) is not None for i in items),
                  matching_cached_ids=[str(i["id"]) for i in items if str(i.get("id")) in known_ids],
                  server_code=payload.get("data", {}).get("serverCode") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else None,
                  eligible_stories=[{k: i[k] for k in ("id", "posted_at", "source_expires_at")} for i in eligible],
                  media=media, cache_written=False, collector_available=bool(eligible))
    return result


def cache_preview(item: dict, media_dir: Path) -> str:
    """Cache a bounded image preview in the existing /assets/feed-images format.

    Videos use the site's provided image preview, like the existing Apify UI.
    Opaque URLs never enter the shared JSON cache. Conversion has its own timeout.
    """
    opaque = item.get("thumbnail_src") or item.get("display_url")
    digest = hashlib.sha256(f"{PROVIDER}:{item['id']}:{item['posted_at']}".encode()).hexdigest()[:20]
    destination = media_dir / f"{digest}.webp"
    if destination.exists():
        return f"/assets/feed-images/{destination.name}"
    def convert(data, content_type):
        if not content_type.startswith("image/"):
            raise ValueError("preview_is_not_image")
        binary = shutil.which("cwebp")
        if not binary:
            raise ValueError("cwebp_unavailable")
        media_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".isv-", dir=media_dir) as directory:
            source, target = Path(directory) / "input", Path(directory) / "preview.webp"
            source.write_bytes(data)
            subprocess.run([binary, "-quiet", "-q", "80", str(source), "-o", str(target)],
                           check=True, capture_output=True, timeout=30)
            target.replace(destination)
    try:
        result = probe_media(opaque, consume=convert)
    except subprocess.SubprocessError:
        raise ValueError("preview_conversion_failed") from None
    if result["status"] != "downloaded":
        raise MediaFailure(result["status"])
    return f"/assets/feed-images/{destination.name}"


class MediaFailure(ValueError):
    pass


def import_result(state: dict, source: dict, payload: dict, now: float, *, media_dir: Path, cacher=None) -> dict:
    """Merge only verified, dated previews. Empty/error results leave state intact."""
    from instagram_public_fetcher import post_row, record_source, iso
    result = classify_result(payload, source["username"])
    items = result.pop("items")
    eligible, rejected = eligible_items(items, now)
    existing = {p["key"]: p for p in state.get("sources", {}).get(source["id"], {}).get("posts", []) if p.get("key")}
    posts, duplicates, failures, stopped = [], 0, [], False
    cache = cacher or cache_preview
    for item in eligible[:5]:
        key = f"{source['id']}:{item['id']}"
        if key in existing:
            duplicates += 1
            if publication_time(existing[key].get("posted_at")) != item["posted_at"]:
                rejected.append({"id": item["id"], "reason": "cached_time_conflict"})
            continue  # Never replace a known original date or refresh its lifetime.
        try:
            image = cache(item, media_dir)
            if not image.startswith("/assets/feed-images/"):
                raise ValueError("media_not_cached")
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            reason = str(exc) if isinstance(exc, MediaFailure) else "download_failed"
            failures.append({"id": item["id"], "reason": reason})
            if reason in {"rate_limited", "access_blocked", "verification_required"}:
                stopped = True
                break
            continue
        post = post_row(source, item["id"], f"Instagram story @{source['username']}",
                        f"https://www.instagram.com/stories/{source['username']}/{item['id']}/", item["posted_at"], [image])
        post.update(story=True, ephemeral=True, include_without_keywords=True, media_type="instagram_story",
                    story_provider=PROVIDER, story_fetched_at=iso(now), story_expires_at=item["source_expires_at"])
        posts.append(post)
    if posts:
        record_source(state, source, posts, now, backend=PROVIDER)
    return {**result, "story_count": len(items) if result["status"] in {"stories", "empty"} else None,
            "eligible_count": len(eligible), "imported": len(posts), "duplicates": duplicates, "rejections": rejected,
            "media_errors": failures, "stopped": stopped, "cache_written": bool(posts)}


def fetch_account(account: str) -> dict:
    """One normal website session. No retries, credentials or raw output in logs."""
    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", account):
        return {"transport_error": "invalid_account"}
    try:
        output = subprocess.run(["node", str(Path(__file__).with_name("insta_stories_viewer_transport.mjs")), account],
                                capture_output=True, timeout=85, check=True)
        if len(output.stdout) > MAX_INPUT_BYTES:
            return {"transport_error": "size_limit"}
        return json.loads(output.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return {"transport_error": "transport_failed"}


def scheduled_accounts(accounts: list[str], sources: dict, cache: dict, guard: dict, now: float, limit: int) -> list[str]:
    """Rotate the explicit pilot list, skipping recently checked primary sources."""
    due = []
    for account in accounts:
        report = guard.get("accounts", {}).get(account, {})
        checked = publication_time(report.get("checked_at"))
        last = dt.datetime.fromisoformat(checked).timestamp() if checked else 0
        entry = cache.get("sources", {}).get(sources[account]["id"], {})
        success = publication_time(entry.get("last_success_at"))
        primary_last = dt.datetime.fromisoformat(success).timestamp() if success else 0
        if max(last, primary_last) + 12 * 3600 <= now:
            due.append((max(last, primary_last), accounts.index(account), account))
    return [row[2] for row in sorted(due)[:limit]]


def live_run(accounts: list[str], *, collect: bool, root: Path, scheduled=False,
             pipeline_lock_held=False, publish=False) -> int:
    """Bounded manual or scheduled invocation; never starts a paid collector."""
    from run_pipeline import acquire_lock, release_lock, write_json_atomic
    if os.environ.get("HARMONICA_ISV_ENABLED") != "1":
        print(json.dumps({"status": "disabled"}))
        return 2
    accounts = list(dict.fromkeys(a.strip().lower().lstrip("@") for a in accounts if a.strip()))
    if not 1 <= len(accounts) <= 5 or any(not re.fullmatch(r"[a-z0-9._]{1,30}", a) for a in accounts):
        raise ValueError("Provide 1 to 5 public source accounts")
    def read(path, default):
        value = json.loads(path.read_text()) if path.exists() else default
        if not isinstance(value, dict):
            raise ValueError("Invalid existing state")
        return value
    sources = read(root / "data/feeds/social_sources.json", {}).get("sources", [])
    selected = {s["username"].lower(): s for s in sources if s.get("enabled", True) and s.get("provider") == "apify_stories"}
    if any(a not in selected for a in accounts):
        raise ValueError("Account is not an enabled public story source")
    lock = root / "state/insta_stories_viewer.lock"
    pipeline_lock = root / "state/run_pipeline.lock"
    if not acquire_lock(lock, stale_after_minutes=240):
        return 1
    pipeline_held = False
    try:
        if collect and not pipeline_lock_held:
            pipeline_held = acquire_lock(pipeline_lock, stale_after_minutes=240)
            if not pipeline_held:
                return 1
        guard_path = root / "state/insta_stories_viewer.json"
        guard = read(guard_path, {})
        if float(guard.get("cooldown_until", 0)) > time.time():
            print(json.dumps({"status": "cooldown", "until": guard["cooldown_until"]}))
            return 0 if scheduled else 1
        state_path = root / "state/instagram_public.json"
        state = read(state_path, {"sources": {}, "runs": []}) if collect else {}
        if scheduled:
            now = time.time()
            next_run = max(float(guard.get("next_scheduled_at", 0)), float(guard.get("next_query_at", 0)))
            if next_run > now:
                print(json.dumps({"status": "scheduled_wait", "until": next_run}))
                return 0
            limit = max(1, min(2, int(os.environ.get("HARMONICA_ISV_BATCH_SIZE", "1"))))
            accounts = scheduled_accounts(accounts, selected, state, guard, now, limit)
            if not accounts:
                print(json.dumps({"status": "no_sources_due"}))
                return 0
            guard["next_scheduled_at"] = now + 3 * 3600
            write_json_atomic(guard_path, guard)
        failed = False
        for account in accounts:
            delay = max(0, float(guard.get("next_query_at", 0)) - time.time())
            if delay:
                print(json.dumps({"status": "waiting", "seconds": math.ceil(delay)}), flush=True)
                time.sleep(delay)
            started = time.time()
            guard["next_query_at"] = started + 175
            if collect and publish:
                guard["next_scheduled_at"] = max(float(guard.get("next_scheduled_at", 0)), started + 3 * 3600)
            write_json_atomic(guard_path, guard)  # Reserve pace before network, including crashes.
            payload = fetch_account(account)
            now = time.time()
            transport_error = payload.get("transport_error")
            if transport_error:
                report = {"status": "transport_failed", "reason": transport_error, "stopped": True}
            elif collect:
                report = import_result(state, selected[account], payload, now, media_dir=root / "site/assets/feed-images")
                if report["cache_written"]:
                    state["updated_at"] = publication_time(now)
                    write_json_atomic(state_path, state)
            else:
                report = diagnose(payload, account, now)
            report.update(account=account, checked_at=publication_time(now), seconds=round(now - started, 3), collected=collect)
            guard.setdefault("accounts", {})[account] = report
            terminal = report.get("stopped") or report["status"] in {"rate_limited", "verification_required", "access_blocked"}
            if terminal or report["status"] in {"service_failed", "loading"}:
                # Stop the whole invocation. No session/IP rotation or immediate retry.
                guard["cooldown_until"] = now + (86400 if terminal else 3600)
            write_json_atomic(guard_path, guard)
            print(json.dumps(report, ensure_ascii=False), flush=True)
            failed |= report["status"] not in {"stories", "empty"} or bool(report.get("media_errors"))
            if collect and publish:
                from publish_story_cache import publish_cached_stories
                try:
                    publication = publish_cached_stories(root)
                except (OSError, ValueError, RuntimeError, subprocess.SubprocessError):
                    publication = {"status": "failed"}
                guard["last_publication"] = {**publication, "checked_at": publication_time(time.time())}
                write_json_atomic(guard_path, guard)
                print(json.dumps({"publication": publication}), flush=True)
                failed |= publication["status"] in {"failed", "incomplete"}
            if guard.get("cooldown_until", 0) > now:
                break
        return int(failed)
    finally:
        if pipeline_held:
            release_lock(pipeline_lock)
        release_lock(lock)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Saved searchResult JSON; never a token or cookie file")
    parser.add_argument("--account")
    parser.add_argument("--accounts", help="Live diagnosis of 1 to 5 enabled public source usernames, comma-separated")
    parser.add_argument("--collect", action="store_true", help="Import eligible previews into the existing cache; add --publish to publish")
    parser.add_argument("--publish", action="store_true", help="Publish collected previews with the existing offline publisher")
    parser.add_argument("--scheduled", action="store_true", help="Read .env and rotate the configured pilot with persistent cadence")
    parser.add_argument("--pipeline-lock-held", action="store_true", help="Only for the pipeline already holding its native lock")
    parser.add_argument("--observed-at", help="Timezone-aware ISO time of the captured response")
    parser.add_argument("--probe-media", action="store_true", help="Explicitly download at most one preview, without saving files")
    args = parser.parse_args(argv)
    if args.scheduled:
        if args.accounts or args.input or args.account or args.probe_media or args.observed_at or args.collect or args.publish:
            parser.error("--scheduled only accepts --pipeline-lock-held")
        from run_pipeline import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        try:
            return live_run(os.environ.get("HARMONICA_ISV_ACCOUNTS", "").split(","), collect=True,
                            root=Path(__file__).resolve().parents[1], scheduled=True,
                            pipeline_lock_held=args.pipeline_lock_held, publish=True)
        except (OSError, ValueError, TypeError):
            print(json.dumps({"status": "invalid_state_or_config"}))
            return 1
    if (args.publish or args.pipeline_lock_held) and not (args.accounts and args.collect):
        parser.error("--publish/--pipeline-lock-held require --accounts and --collect")
    if args.accounts:
        if args.input or args.account or args.probe_media or args.observed_at:
            parser.error("--accounts cannot be combined with saved-response options")
        try:
            return live_run(args.accounts.split(","), collect=args.collect, root=Path(__file__).resolve().parents[1],
                            pipeline_lock_held=args.pipeline_lock_held, publish=args.publish)
        except (OSError, ValueError, TypeError):
            print(json.dumps({"status": "invalid_state_or_config"}))
            return 1
    if not args.input or not args.account or args.collect:
        parser.error("Use --input and --account for offline diagnosis, or --accounts [--collect] for live mode")
    if args.probe_media and os.environ.get("HARMONICA_ISV_DIAGNOSTIC_ENABLED") != "1":
        parser.error("Media network access is disabled; set HARMONICA_ISV_DIAGNOSTIC_ENABLED=1 for this command")
    if args.observed_at and not publication_time(args.observed_at):
        parser.error("--observed-at requires a timezone-aware ISO timestamp")
    try:
        with args.input.open("rb") as stream:
            raw = stream.read(MAX_INPUT_BYTES + 1)
        if len(raw) > MAX_INPUT_BYTES:
            raise ValueError("size_limit")
        payload = json.loads(raw)
        now = dt.datetime.fromisoformat(publication_time(args.observed_at)).timestamp() if args.observed_at else time.time()
        result = diagnose(payload, args.account, now, download=probe_media if args.probe_media else None)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["status"] in {"stories", "empty"} and all(m["status"] == "downloaded" for m in result["media"]) else 1
    except (OSError, ValueError, TypeError):
        print(json.dumps({"status": "invalid_input", "cache_written": False}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
