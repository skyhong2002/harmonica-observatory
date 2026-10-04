#!/usr/bin/env python3
"""Run the standalone public data pipeline."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
DEFAULT_LOCK_FILE = PROJECT_ROOT / "state" / "run_pipeline.lock"
DEFAULT_RUNTIME_STATUS = PROJECT_ROOT / "site" / "api" / "pipeline-runtime.json"
DEFAULT_GOOGLE_WORKSPACE_PYTHON = Path.home() / ".hermes" / "harmonica-intake-venv" / "bin" / "python"


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


def google_workspace_python() -> str:
    configured = os.environ.get("HARMONICA_GOOGLE_WORKSPACE_PYTHON", "").strip()
    if configured:
        return configured
    if DEFAULT_GOOGLE_WORKSPACE_PYTHON.exists():
        return str(DEFAULT_GOOGLE_WORKSPACE_PYTHON)
    return PYTHON


def write_json_atomic(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # The temp name carries the pid so two pipeline processes writing the same
    # file never rename each other's half-written temp file away.
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(args: list[str], *, optional: bool = False, step: str = "", status_hook=None) -> None:
    if status_hook is not None:
        status_hook(step or " ".join(args), "running", args=args)
    process = subprocess.Popen(args, cwd=PROJECT_ROOT)
    while True:
        try:
            returncode = process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            if status_hook is not None:
                status_hook(step or " ".join(args), "running", args=args)
            continue
        break
    if returncode:
        if status_hook is not None:
            status_hook(
                step or " ".join(args),
                "optional_failed" if optional else "failed",
                args=args,
                returncode=returncode,
            )
        if not optional:
            raise subprocess.CalledProcessError(returncode, args)
        print(f"Optional pipeline step failed with exit code {returncode}: {' '.join(args)}", file=sys.stderr)
    else:
        if status_hook is not None:
            status_hook(step or " ".join(args), "ok", args=args, returncode=0)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def process_is_running(pid: object) -> bool:
    try:
        value = int(pid)
    except (TypeError, ValueError):
        return False
    if value <= 0:
        return False
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_lock(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def lock_is_stale(info: dict[str, object], *, stale_after: dt.timedelta, now: dt.datetime) -> bool:
    if not process_is_running(info.get("pid")):
        return True
    started_at = parse_time(info.get("started_at"))
    return started_at is None or now - started_at > stale_after


def acquire_lock(path: Path, *, stale_after_minutes: float) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = utc_now()
    stale_after = dt.timedelta(minutes=max(1.0, stale_after_minutes))
    lock_info = {
        "pid": os.getpid(),
        "started_at": now.isoformat(),
    }

    # Write the lock contents to a private file first and publish it with an
    # atomic link, so no other process can ever observe an empty lock file,
    # mistake it for stale and steal it.
    staging = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    staging.write_text(
        json.dumps(lock_info, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    try:
        for _attempt in range(3):
            try:
                os.link(staging, path)
                return True
            except FileExistsError:
                pass
            existing = load_lock(path)
            if not existing and path.exists() and lock_file_is_fresh(path, now=now):
                # Another process is mid-acquire with an older writer; treat as held.
                existing = {"pid": None, "started_at": None}
            elif lock_is_stale(existing, stale_after=stale_after, now=now):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                continue
            print(
                "Pipeline already running; skipping this scheduled tick "
                f"(lock={path}, pid={existing.get('pid')}, started_at={existing.get('started_at')})."
            )
            return False
        print(f"Pipeline lock contended; skipping this scheduled tick (lock={path}).")
        return False
    finally:
        try:
            staging.unlink()
        except FileNotFoundError:
            pass


def lock_file_is_fresh(path: Path, *, now: dt.datetime, grace_seconds: float = 60.0) -> bool:
    try:
        modified = dt.datetime.fromtimestamp(path.stat().st_mtime, tz=dt.timezone.utc)
    except OSError:
        return False
    return (now - modified).total_seconds() < grace_seconds


def release_lock(path: Path) -> None:
    existing = load_lock(path)
    if existing.get("pid") == os.getpid():
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-watch", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--emit-initial", action="store_true")
    parser.add_argument("--max-post-age-days", type=int, default=30)
    parser.add_argument("--skip-source-build", action="store_true")
    parser.add_argument("--skip-youtube", action="store_true")
    parser.add_argument("--skip-facebook", action="store_true")
    parser.add_argument("--skip-instagram", action="store_true")
    parser.add_argument("--skip-llm-tags", action="store_true")
    parser.add_argument("--facebook-dry-run", action="store_true")
    parser.add_argument("--youtube-full-refresh", action="store_true")
    parser.add_argument("--facebook-priority", action="store_true")
    parser.add_argument("--facebook-full-refresh", action="store_true")
    parser.add_argument("--facebook-provider-days-back", type=int, default=0)
    parser.add_argument("--skip-calendar-sync", action="store_true")
    parser.add_argument("--publish-pages", action="store_true")
    parser.add_argument("--pages-no-push", action="store_true")
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--lock-stale-minutes", type=float, default=240.0)
    parser.add_argument("--runtime-status", type=Path, default=DEFAULT_RUNTIME_STATUS)
    parser.add_argument("--no-lock", action="store_true")
    parser.add_argument("--rsshub-base", default=os.environ.get("HARMONICA_RSSHUB_BASE", ""))
    parser.add_argument("--request-timeout", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")

    lock_path = args.lock_file if args.lock_file.is_absolute() else PROJECT_ROOT / args.lock_file
    runtime_status_path = args.runtime_status if args.runtime_status.is_absolute() else PROJECT_ROOT / args.runtime_status
    started_at = utc_now()
    step_states: dict[str, dict[str, object]] = {}
    current_step_label = ""

    def publish_runtime_status(
        status: str,
        *,
        current_step: str = "",
        message: str = "",
        returncode: int | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "version": 1,
            "status": status,
            "pid": os.getpid(),
            "startedAt": started_at.isoformat(),
            "heartbeatAt": utc_now().isoformat(),
            "currentStep": current_step,
            "message": message,
            "lockFile": str(lock_path),
            "maxPostAgeDays": int(args.max_post_age_days),
            "steps": list(step_states.values()),
        }
        if returncode is not None:
            payload["returnCode"] = returncode
        write_json_atomic(runtime_status_path, payload)

    def mark_step(label: str, status: str, *, args: list[str], returncode: int | None = None) -> None:
        nonlocal current_step_label
        current_step_label = label
        now = utc_now().isoformat()
        entry = step_states.setdefault(
            label,
            {
                "name": label,
                "command": args,
                "status": "pending",
                "startedAt": "",
                "finishedAt": "",
                "returnCode": None,
            },
        )
        if status == "running":
            if entry["status"] != "running":
                entry["startedAt"] = now
            entry["status"] = "running"
            entry["finishedAt"] = ""
            entry["returnCode"] = None
            publish_runtime_status("running", current_step=label)
            return
        entry["status"] = status
        entry["finishedAt"] = now
        entry["returnCode"] = returncode
        if status == "failed":
            publish_runtime_status("failed", current_step=label, message=f"{label} failed", returncode=returncode)
        else:
            publish_runtime_status("running", current_step=label, returncode=returncode)

    locked = args.no_lock or acquire_lock(lock_path, stale_after_minutes=args.lock_stale_minutes)
    if not locked:
        return 0

    publish_runtime_status("running", message="Pipeline started")
    completed = False
    try:
        if not args.skip_source_build:
            run([PYTHON, "scripts/build_social_sources.py"], step="build social sources", status_hook=mark_step)

        if not args.skip_watch:
            if not args.skip_instagram:
                run([PYTHON, "scripts/instagram_public_fetcher.py", "--kind", "story", "--pipeline-lock-held"],
                    optional=True, step="fetch instagram stories", status_hook=mark_step)
                # Stories expire quickly: publish their existing cache before
                # unrelated collectors or the full watchdog can delay the feed.
                run([PYTHON, "scripts/publish_story_cache.py", "--pipeline-lock-held"],
                    optional=True, step="publish cached instagram stories", status_hook=mark_step)
                if os.environ.get("HARMONICA_ISV_ENABLED") == "1":
                    run([PYTHON, "scripts/insta_stories_viewer.py", "--scheduled", "--pipeline-lock-held"],
                        optional=True, step="fetch and publish instagram story backup", status_hook=mark_step)
                run([PYTHON, "scripts/instagram_public_fetcher.py", "--kind", "profile", "--pipeline-lock-held"],
                    optional=True, step="fetch instagram public", status_hook=mark_step)
            if not args.skip_youtube:
                youtube_args = [
                    PYTHON,
                    "scripts/youtube_ytdlp_fetcher.py",
                    "--max-post-age-days",
                    str(args.max_post_age_days),
                ]
                if args.youtube_full_refresh:
                    youtube_args.append("--full-refresh")
                if args.verbose:
                    youtube_args.append("--verbose")
                run(youtube_args, optional=True, step="fetch youtube", status_hook=mark_step)
            if not args.skip_facebook:
                provider_days_back = args.facebook_provider_days_back or args.max_post_age_days
                facebook_args = [
                    PYTHON,
                    "scripts/apify_facebook_fetcher.py",
                    "--days-back",
                    str(provider_days_back),
                    "--local-max-post-age-days",
                    str(args.max_post_age_days),
                ]
                if args.facebook_priority:
                    facebook_args.append("--priority")
                if args.facebook_full_refresh:
                    facebook_args.append("--full-refresh")
                if not args.facebook_dry_run and os.environ.get("HARMONICA_SKIP_APIFY_FACEBOOK", "") not in {"1", "true", "TRUE"}:
                    facebook_args.append("--run")
                run(facebook_args, optional=True, step="fetch facebook apify", status_hook=mark_step)

            watch_args = [PYTHON, "scripts/social_feed_watchdog.py", "--max-post-age-days", str(args.max_post_age_days)]
            if args.rsshub_base:
                watch_args.extend(["--rsshub-base", args.rsshub_base])
            if args.request_timeout:
                watch_args.extend(["--request-timeout", str(args.request_timeout)])
            if args.skip_llm_tags:
                watch_args.append("--no-llm-tags")
            if args.baseline:
                watch_args.append("--baseline")
            if args.emit_initial:
                watch_args.append("--emit-initial")
            if args.verbose:
                watch_args.append("--verbose")
            run(watch_args, step="watch social feeds", status_hook=mark_step)

        run([PYTHON, "scripts/build_public_data.py"], step="build public data", status_hook=mark_step)
        run(
            [PYTHON, "scripts/backfill_public_source_pages.py", "--skip-fetch"],
            step="backfill source pages",
            status_hook=mark_step,
        )
        run([PYTHON, "scripts/build_public_data.py"], step="rebuild public data", status_hook=mark_step)
        run([PYTHON, "scripts/build_score_publications.py"], step="build score publications", status_hook=mark_step)
        run([PYTHON, "scripts/build_score_sources.py"], step="build score sources", status_hook=mark_step)
        run([PYTHON, "scripts/generate_rss_feeds.py"], step="generate rss feeds", status_hook=mark_step)
        run([PYTHON, "scripts/build_public_calendar_events.py"], step="build public calendar events", status_hook=mark_step)
        run([PYTHON, "scripts/apply_submitted_events.py"], step="apply submitted events", status_hook=mark_step)
        if not args.skip_calendar_sync:
            run(
                [google_workspace_python(), "scripts/sync_google_calendar_events.py"],
                optional=True,
                step="sync google calendar",
                status_hook=mark_step,
            )
        run([PYTHON, "scripts/build_status_page.py"], step="build status page", status_hook=mark_step)
        run([PYTHON, "scripts/build_submit_page.py"], step="build submit page", status_hook=mark_step)
        run([PYTHON, "scripts/generate_seo_pages.py"], step="generate SEO pages", status_hook=mark_step)
        run([PYTHON, "scripts/generate_cloudflare_redirects.py"], step="generate cloudflare redirects", status_hook=mark_step)
        run([PYTHON, "scripts/check_source_coverage.py"], step="check source coverage", status_hook=mark_step)
        run([PYTHON, "scripts/validate_public_outputs.py"], step="validate public outputs", status_hook=mark_step)
        if args.publish_pages:
            pages_args = [PYTHON, "scripts/publish_github_pages.py"]
            if args.pages_no_push:
                pages_args.append("--no-push")
            publish_label = "publish github pages"
            mark_step(publish_label, "running", args=pages_args)
            mark_step(publish_label, "ok", args=pages_args, returncode=0)
            publish_runtime_status("ok", message="Pipeline completed; publishing snapshot")
            run(pages_args)
        completed = True
        publish_runtime_status("ok", message="Pipeline completed")
    finally:
        # Publish the final status while the lock is still held so a run that
        # starts the moment the lock drops never races this write.
        if not completed:
            try:
                publish_runtime_status(
                    "failed",
                    current_step=current_step_label,
                    message="Pipeline stopped before completion",
                )
            except OSError as exc:
                print(f"Could not publish failed runtime status: {exc}", file=sys.stderr)
        if not args.no_lock:
            release_lock(lock_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
