#!/usr/bin/env python3
"""Account-independent Instagram collectors, adapted from skyhong2002/chumei.

Stories use the isolated Harmonica Apify contribution pool. Profiles try the
free logged-out web query first, paced host-wide together with Chumei (see
``ig_public_host``); what it cannot serve falls back to the same pool. Shared
reservations protect contributed authorization across concurrent collectors.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import http.cookiejar
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from apify_facebook_fetcher import load_json, save_json
import apify_pool
import ig_public_host
from source_priority import affinity_of, event_affinity
from story_lifecycle import display_expiry
from run_pipeline import PROJECT_ROOT, load_dotenv, acquire_lock, release_lock

STATE = PROJECT_ROOT / "state/instagram_public.json"
CONFIG = PROJECT_ROOT / "data/feeds/social_sources.json"
STORY_ACTOR = "intropix/instagram-stories-scraper"
PROFILE_ACTOR = "apify/instagram-profile-scraper"
PROVIDERS = {"apify_stories", "instagram_public"}
PUBLIC_APP_ID = "936619743392459"
PUBLIC_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")
# Logged-out PolarisProfilePostsQuery. Instagram rotates these ids with web
# releases; HARMONICA_IG_PROFILE_POSTS_DOC_ID overrides it without a deploy.
PROFILE_POSTS_DOC_ID = "9310670392322965"
DIRECT_MAX_CONSECUTIVE_FAILURES = 3
UTC = dt.timezone.utc


def timestamp(value):
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def iso(value=None):
    return dt.datetime.fromtimestamp(time.time() if value is None else value, UTC).isoformat()


def api(method, path, token, *, body=None, query=None):
    # Credentials are headers, never URL parameters or diagnostics.
    url = "https://api.apify.com/v2" + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    try:
        with apify_pool.open_request(urllib.request.Request(url, data, headers, method=method), timeout=35) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Apify HTTP {exc.code} ({path.split('/')[1]})") from None
    except urllib.error.URLError:
        raise RuntimeError("Apify network request failed") from None


def remaining_credit(limits, monthly_cap):
    ceiling = min(float(limits.get("limits", {}).get("maxMonthlyUsageUsd") or 0), monthly_cap)
    return max(0.0, ceiling - float(limits.get("current", {}).get("monthlyUsageUsd") or 0))


def daily_budget(state, limits, monthly_cap, now):
    remaining = remaining_credit(limits, monthly_cap)
    days = max(1, math.ceil((timestamp(limits.get("monthlyUsageCycle", {}).get("endAt")) - now) / 86400))
    today = iso(now)[:10]
    # Apify's final event billing can lag terminal status; retain the worst-case
    # reservation for pacing even after a lower preliminary charge is reported.
    spent = sum(max(float(r.get("cost_usd") or 0), float(r.get("reserved_usd") or 0))
                for r in state.get("runs", []) if str(r.get("at", "")).startswith(today))
    # Half of evenly paced available credit stays available to Facebook.
    allowance = min(0.20, (remaining + spent) / days * 0.5)
    return max(0.0, min(remaining, allowance - spent))


def story_plan(available, targets, delivered_today):
    results = max(0, min(10, 40 - delivered_today))
    targets = min(10, targets, results)
    # Reserve at least one result per target. Otherwise a one-result run can
    # spend most of its allowance granting accounts it never actually reaches.
    while targets > 0:
        count = min(results, math.floor((available - 0.005 - targets * 0.002 + 1e-9) / 0.0025))
        if count >= targets:
            return targets, count, round(0.005 + targets * 0.002 + count * 0.0025, 6)
        targets -= 1
    return 0, 0, 0.0


def cadence(posts, now):
    times = sorted({timestamp(p.get("posted_at")) for p in posts if not p.get("is_pinned")}, reverse=True)
    times = [t for t in times if t > 0]
    if not times:
        return 168
    gaps = [(a - b) / 3600 for a, b in zip(times, times[1:])]
    target = max((now - times[0]) / 3600 / 4, statistics.median(gaps) / 2 if gaps else 12)
    return next((tier for tier in (12, 24, 48, 72, 168, 336) if tier >= target), 336)


def select_due(sources, state, kind, now, limit, wanted=()):
    entries = state.get("sources", {})
    rows = [s for s in sources if s.get("provider") == kind and s.get("enabled", True)]
    if wanted:
        rows = [s for s in rows if s["username"] in wanted]
    if not wanted:
        rows = [s for s in rows if float(entries.get(s["id"], {}).get("next_due_at", 0)) <= now
                or (kind == "apify_stories" and entries.get(s["id"], {}).get("status") in {"ok", "unconfirmed"}
                    and float(entries.get(s["id"], {}).get("interval_hours") or 0) > 12
                    and entries.get(s["id"], {}).get("last_attempt_at")
                    and float(entries[s["id"]]["last_attempt_at"]) + 12 * 3600 <= now)]
    def priority(source):
        entry = entries.get(source["id"], {})
        # Rotate never-scanned accounts before revisiting them. Within that group,
        # prefer accounts that have announced events before, then accounts that
        # published recently in the site's existing feed.
        last = float(entry.get("last_attempt_at") or 0)
        history = state.get("history", {}).get(source["username"], [])
        events = affinity_of(source, state.get("_affinity", {}))
        return (bool(last), -min(events, 8), cadence(history, now), last, source["username"])
    if kind == "apify_stories" and not wanted:
        # Prefer known active publishers, while retaining one exploration slot
        # per four choices. Old successful-empty accounts must not outrank
        # recently active sources merely because their last scan is older.
        new = sorted((s for s in rows if not entries.get(s["id"], {}).get("last_success_at")), key=priority)
        def known_priority(source):
            entry = entries[source["id"]]
            activity = state.get("history", {}).get(source["username"], []) + entry.get("posts", [])
            events = affinity_of(source, state.get("_affinity", {}))
            return (cadence(activity, now), -min(events, 8), float(entry.get("last_attempt_at") or 0), source["username"])
        known = sorted((s for s in rows if entries.get(s["id"], {}).get("last_success_at")), key=known_priority)
        ordered = []
        # A tiny one-target budget still explores during one of four 3h slots.
        if new and int(now // (3 * 3600)) % 4 == 3:
            ordered.append(new.pop(0))
        while new or known:
            for _ in range(3):
                if known:
                    ordered.append(known.pop(0))
            if new:
                ordered.append(new.pop(0))
        return ordered[:limit]
    return sorted(rows, key=priority)[:limit]


def record_source(state, source, posts, now, *, error="", backend=""):
    entry = state.setdefault("sources", {}).setdefault(source["id"], {})
    entry.update(last_attempt_at=now, backend=backend, error=error, status="error" if error else "ok")
    if error:
        entry["next_due_at"] = now + 24 * 3600
        return
    interval = cadence(posts or state.get("history", {}).get(source["username"], []), now)
    if source.get("provider") == "apify_stories":
        # Stories expire after 24 hours; a weekly successful-empty cadence can
        # miss every later story. Budget allocation still determines actual runs.
        interval = 12
        # Retain cached previews for their full display lifetime, even after IG expiry.
        merged = {p["key"]: p for p in entry.get("posts", [])
                  if (expiry := display_expiry(p)) and expiry.timestamp() > now}
        merged.update({p["key"]: p for p in posts})
        posts = list(merged.values())
    entry.update(last_success_at=iso(now), next_due_at=now + interval * 3600,
                 interval_hours=interval, posts=posts, last_post_count=len(posts))


def post_row(source, ident, caption, url, posted_at, images):
    return {"key": f"{source['id']}:{ident}", "source_id": source["id"],
            "source_name": source["name"], "platform": "instagram", "account": source["username"],
            "post_id": str(ident), "url": url, "posted_at": posted_at,
            "source_profile_url": source.get("source_profile_url") or f"https://www.instagram.com/{source['username']}/",
            "text": caption or "",
            "images": images, "image_url": next(iter(images), ""),
            "include_without_keywords": bool(source.get("include_without_keywords"))}


def cache_story_media(item):
    from generate_rss_feeds import cache_image, FEED_IMAGE_DIR
    url = str(item.get("media_url") or "")
    if not url.startswith("https://"):
        raise ValueError("Story has no HTTPS media URL")
    if item.get("media_type") != "video":
        local = cache_image(url)
        if not local.startswith("/assets/"):
            raise ValueError("Story image download failed")
        return local
    digest = hashlib.sha256(url.encode()).hexdigest()[:20]
    destination = FEED_IMAGE_DIR / (digest + ".webp")
    if not destination.exists():
        ffmpeg = shutil.which("ffmpeg") or str(Path.home() / ".local/bin/ffmpeg")
        with tempfile.TemporaryDirectory(prefix="harmonica-story-") as directory:
            video = Path(directory) / "story.mp4"
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as response:
                content = response.read(30_000_001)
            if len(content) > 30_000_000:
                raise ValueError("Story video exceeds download limit")
            video.write_bytes(content)
            frame = Path(directory) / "frame.webp"
            result = subprocess.run([ffmpeg, "-loglevel", "error", "-y", "-i", str(video),
                                     "-frames:v", "1", "-vf", "scale='min(720,iw)':-2", str(frame)],
                                    capture_output=True, timeout=40)
            if result.returncode or not frame.exists():
                raise ValueError("Story video thumbnail extraction failed")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(frame.read_bytes())
    return f"/assets/feed-images/{destination.name}"


def story_row(source, item, now):
    ident = str(item.get("story_pk") or "")
    posted = timestamp(item.get("taken_at"))
    expires = timestamp(item.get("expiring_at"))
    if item.get("is_private") or not ident.isdigit() or not posted or expires <= now or now - posted > 86400:
        return None
    image = cache_story_media(item)
    post = post_row(source, ident, item.get("caption") or f"Instagram story @{source['username']}",
                    f"https://www.instagram.com/stories/{source['username']}/{ident}/", iso(posted), [image])
    post.update(story=True, ephemeral=True, include_without_keywords=True, media_type="instagram_story", story_provider="apify_stories",
                story_fetched_at=iso(now), story_expires_at=iso(expires))
    return post


class PublicWebError(OSError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def is_rate_limited(exc):
    return getattr(exc, "code", None) in {401, 429} or "please wait a few minutes" in str(exc).casefold()


class PublicWebClient:
    """Logged-out instagram.com client; needs no cookie or Instagram login.

    The profile page hands every anonymous visitor an LSD token plus
    ``csrftoken``/``mid`` cookies. With them, the web app's own profile-posts
    GraphQL query answers without an account. The older ``web_profile_info``
    API now answers logged-out server IPs with 401 ``require_login``.
    """

    def __init__(self, base="https://www.instagram.com", doc_id=None):
        self.base = base.rstrip("/")
        self.doc_id = doc_id or os.environ.get("HARMONICA_IG_PROFILE_POSTS_DOC_ID") or PROFILE_POSTS_DOC_ID
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.lsd = None

    def _cookie(self, name):
        return next((cookie.value for cookie in self.cookies if cookie.name == name), "")

    def _open(self, request, label):
        try:
            with self.opener.open(request, timeout=30) as response:
                return response.read(5_000_000).decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            with exc:
                body = exc.read(500).decode("utf-8", "replace")
            raise PublicWebError(f"Instagram public web HTTP {exc.code} for {label}: {body[:120]}", exc.code) from None

    def _bootstrap(self, username):
        page = self._open(urllib.request.Request(f"{self.base}/{username}/", headers={
            "Accept": "text/html", "Accept-Language": "en", "User-Agent": PUBLIC_USER_AGENT}), f"@{username} page")
        match = re.search(r'"LSD",\[\],\{"token":"([^"]+)"', page)
        if not match or not self._cookie("csrftoken"):
            raise ValueError("Instagram public web page carried no anonymous LSD/csrf token")
        self.lsd = match.group(1)

    def fetch(self, source, limit=5):
        username = source["username"]
        if self.lsd is None:
            self._bootstrap(username)
        variables = {"data": {"count": max(12, limit), "include_reel_media_seen_timestamp": True,
                              "include_relationship_info": True, "latest_besties_reel_media": True,
                              "latest_reel_media": True},
                     "username": username,
                     "__relay_internal__pv__PolarisIsLoggedInrelayprovider": False,
                     "__relay_internal__pv__PolarisShareSheetV3relayprovider": True}
        body = urllib.parse.urlencode({"lsd": self.lsd, "doc_id": self.doc_id, "variables": json.dumps(variables)}).encode()
        text = self._open(urllib.request.Request(f"{self.base}/graphql/query", body, {
            "Accept": "*/*", "Content-Type": "application/x-www-form-urlencoded", "Origin": self.base,
            "Referer": f"{self.base}/{username}/", "Sec-Fetch-Site": "same-origin", "User-Agent": PUBLIC_USER_AGENT,
            "X-CSRFToken": self._cookie("csrftoken"), "X-FB-LSD": self.lsd, "X-IG-App-ID": PUBLIC_APP_ID},
            method="POST"), f"@{username}")
        try:
            payload = json.loads(text)
        except ValueError:
            raise ValueError(f"Instagram public web returned no JSON for @{username}") from None
        connection = (payload.get("data") or {}).get("xdt_api__v1__feed__user_timeline_graphql_connection")
        if connection is None:
            errors = "; ".join(str(e.get("message")) for e in payload.get("errors") or [])
            raise ValueError(f"Instagram public web query failed for @{username}: "
                             f"{errors or payload.get('message') or 'no timeline'}")
        return parse_public_timeline(source, connection, limit)


def _best_image(media):
    candidates = (media.get("image_versions2") or {}).get("candidates") or []
    if candidates and candidates[0].get("url"):
        return candidates[0]["url"]
    return media.get("display_uri")


def parse_public_timeline(source, connection, limit=5):
    """Return (avatar, posts) from the logged-out timeline; pinned posts are flagged."""
    nodes = [edge.get("node") or {} for edge in connection.get("edges") or []]
    user = next((node.get("user") for node in nodes if node.get("user")), None) or {}
    if user.get("is_private"):
        raise ValueError("Public Instagram profile unavailable")
    posts = []
    for node in sorted(nodes, key=lambda node: node.get("taken_at") or 0, reverse=True)[:limit]:
        ident = str(node.get("pk") or str(node.get("id") or "").split("_")[0])
        if not node.get("code") or not ident or not node.get("taken_at"):
            continue
        images = [url for url in map(_best_image, (node.get("carousel_media") or [node])[:2]) if url]
        post = post_row(source, ident, (node.get("caption") or {}).get("text") or "",
                        f"https://www.instagram.com/p/{node['code']}/", iso(node["taken_at"]), images)
        post["is_pinned"] = bool(node.get("timeline_pinned_user_ids"))
        posts.append(post)
    avatar = (user.get("hd_profile_pic_url_info") or {}).get("url") or user.get("profile_pic_url")
    return avatar, posts


def fetch_public_profile(source, client=None):
    return (client or PublicWebClient()).fetch(source)[1]


def normalize_profile(source, item):
    if item.get("isPrivate") or "latestPosts" not in item or item.get("error"):
        raise ValueError("Apify did not return a public profile")
    posts = []
    for raw in (item.get("latestPosts") or [])[:5]:
        shortcode = raw.get("shortCode") or raw.get("shortcode")
        if not shortcode or not raw.get("id") or not timestamp(raw.get("timestamp")):
            continue
        images = raw.get("images") or ([raw["displayUrl"]] if raw.get("displayUrl") else [])
        post = post_row(source, raw["id"], raw.get("caption"), f"https://www.instagram.com/p/{shortcode}/",
                        raw["timestamp"], images[:2])
        post["is_pinned"] = bool(raw.get("isPinned"))
        posts.append(post)
    return posts


def run_actor(state, token, actor, body, max_results, budget, now, save):
    # Reserve and persist BEFORE the billable POST. Unknown outcomes never trigger
    # blind paid retries, and a crash cannot silently restore the spend allowance.
    reservation = None
    if state.get("_use_pool"):
        apify_pool.verify_actor_cap(actor, budget)
        reservation = apify_pool.reserve_run(
            "instagram_stories" if actor == STORY_ACTOR else "instagram", budget,
            source_count=len(body.get("usernames", [])), result_count=max_results if actor == STORY_ACTOR else 0)
        token = reservation["token"]
    receipt = {"at": iso(now), "actor": actor, "reserved_usd": budget,
               "reserved_results": max_results, "status": "starting"}
    if reservation:
        receipt["pool_reservation_id"] = reservation["id"]
    state.setdefault("runs", []).append(receipt)
    save()
    run = api("POST", "/acts/" + actor.replace("/", "~") + "/runs", token, body=body,
              query={"memory": 4096 if actor == STORY_ACTOR else 1024, "timeout": 300,
                     "maxTotalChargeUsd": budget, "restartOnError": "false"}).get("data", {})
    if not run.get("id"):
        raise RuntimeError("Apify run id missing; budget remains reserved")
    receipt.update(id=run["id"], status=run.get("status"))
    if reservation:
        apify_pool.record_run_started(reservation["id"], run["id"])
    save()
    deadline = time.monotonic() + 345
    while run.get("status") not in {"SUCCEEDED", "FAILED", "TIMED-OUT", "ABORTED"}:
        if time.monotonic() > deadline:
            raise RuntimeError("Apify run has not finished; budget remains reserved")
        time.sleep(3)
        run = api("GET", "/actor-runs/" + run["id"], token).get("data", {})
    receipt["status"] = run.get("status")
    if isinstance(run.get("usageTotalUsd"), (float, int)):
        receipt["cost_usd"] = run["usageTotalUsd"]
    save()
    if reservation:
        apify_pool.finish_run(reservation["id"], status=run.get("status"),
                              actual_cost_usd=run.get("usageTotalUsd"), actor_run_id=run.get("id"))
    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"Apify run ended with {run.get('status')}")
    items = api("GET", f"/datasets/{run['defaultDatasetId']}/items", token,
                query={"format": "json", "clean": "true", "limit": max_results})
    outcome = api("GET", f"/key-value-stores/{run['defaultKeyValueStoreId']}/records/OUTPUT", token) if actor == STORY_ACTOR else {}
    receipt["delivered"] = max(len(items), int(outcome.get("delivered") or 0))
    # A denied/free-tier OUTPUT can still incur actor-start or delayed charges.
    # Keep the full persisted cap even when usageTotalUsd is initially zero.
    save()
    return items, outcome


def pool_story_plan(options, target_count):
    """Plan against one account's money AND remaining daily result slots."""
    plans = [story_plan(float(option.get("maxRunBudgetUsd") or 0), target_count,
                        40 - max(0, min(40, int(option.get("resultsLeft") or 0))))
             for option in options]
    return max(plans, key=lambda plan: (plan[0], plan[1], -plan[2]), default=(0, 0, 0.0))


def paced_story_runs(options):
    """Spread currently affordable complete batches over eight daily slots."""
    runs = 0
    for option in options:
        credit = max(0.0, float(option.get("maxRunBudgetUsd") or 0))
        results = max(0, min(40, int(option.get("resultsLeft") or 0)))
        if credit + 1e-9 >= .0095 and results:
            runs += min(math.ceil(results / 10), max(1, math.floor((credit + 1e-9) / .05)))
    return max(1, min(8, math.ceil(runs / 8)))


def collect_stories(state, sources, token, limits, cap, now, save, wanted):
    section = state.setdefault("story", {})
    if not wanted and float(section.get("next_run_at") or 0) > now:
        return
    options = apify_pool.story_run_options(now=now) if state.get("_use_pool") else []
    max_runs = paced_story_runs(options) if state.get("_use_pool") and not wanted else 1
    attempted = set()
    for index in range(max_runs):
        selected = select_due([s for s in sources if s["id"] not in attempted], state,
                              "apify_stories", now, 10, wanted)
        if not selected:
            if not index:
                section.update(status="ok", reason="no_sources_due")
            break
        section.update(checked_at=iso(now))
        if not wanted:
            section["next_run_at"] = now + 3 * 3600
        today = iso(now)[:10]
        delivered = sum(int(r.get("delivered", r.get("reserved_results", 0))) for r in state.get("runs", [])
                        if r.get("actor") == STORY_ACTOR and r.get("at", "").startswith(today))
        if state.get("_use_pool"):
            # Re-read after each successful run; never combine one account's
            # monetary capacity with a different account's result allowance.
            if index:
                options = apify_pool.story_run_options(now=now)
            targets, results, budget = pool_story_plan(options, len(selected))
            available = max((float(o.get("maxRunBudgetUsd") or 0) for o in options), default=0.0)
        else:
            available = daily_budget(state, limits, cap, now) if token and limits else 0
            targets, results, budget = story_plan(available, len(selected), delivered)
        section.update(available_usd=round(available, 6), daily_results=delivered)
        if not targets:
            if not index:
                section.update(status="paused", reason="daily_result_limit" if not state.get("_use_pool") and delivered >= 40 else "credit_budget", scanned=0)
            break
        selected = selected[:targets]
        # Unknown or failed outcomes propagate without another paid attempt.
        items, outcome = run_actor(state, token, STORY_ACTOR, {"usernames": [s["username"] for s in selected],
                                      "maxResults": results}, results, budget, now, save)
        ingest_story_results(state, selected, items, outcome, results, now, save)
        attempted.update(s["id"] for s in selected)
        if outcome.get("outcome") == "denied":
            break  # A free-tier refusal does not prove this run was free.


def ingest_story_results(state, selected, items, outcome, results, now, save):
    """Import one verified story actor outcome; never launch or retry an actor."""
    section = state.setdefault("story", {})
    section["checked_at"] = iso(now)
    if outcome.get("outcome") == "denied":
        reason = outcome.get("reason") or "provider_denied"
        retry = (math.floor(now / 86400) + 1) * 86400 if reason == "user_daily_exhausted" else now + 3600
        section.update(status="paused", reason=reason, scanned=0, next_run_at=retry)
        return
    if outcome.get("outcome") != "ok" or not isinstance(outcome.get("granted_targets"), int):
        raise RuntimeError("Story actor omitted scan outcome; empty results are not success")
    granted = outcome["granted_targets"]
    if not 0 <= granted <= len(selected):
        raise RuntimeError("Story actor returned invalid scan count")
    failed = {str(username).casefold() for username in (outcome.get("failed_targets") or [])}
    confirmed = selected[:granted]
    if len(items) >= results:
        # granted_targets is permission, not evidence of a scan. The actor can
        # stop on maxResults before reaching the later usernames. When capped,
        # only returned/failed usernames have an unambiguous outcome.
        observed = {str(item.get("username", "")).casefold() for item in items} | {u.casefold() for u in failed}
        confirmed = [s for s in confirmed if s["username"].casefold() in observed]
    success = media_errors = 0
    for source in confirmed:
        username = source["username"]
        if username.casefold() in failed:
            record_source(state, source, [], now, error="Story provider: " + str((outcome.get("failed_target_reasons") or {}).get(username, {})), backend="apify_stories")
            continue
        posts = []
        error = ""
        for item in items:
            if str(item.get("username", "")).casefold() != username.casefold():
                continue
            try:
                post = story_row(source, item, now)
                if post:
                    posts.append(post)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                error = f"Story media unavailable: {type(exc).__name__}"
                media_errors += 1
        if posts or not error:
            record_source(state, source, posts, now, backend="apify_stories")
        if error:
            record_source(state, source, [], now, error=error, backend="apify_stories")
        else:
            success += 1
    section.update(status="degraded" if failed or media_errors or not granted else "ok", reason="partial_scan" if failed or media_errors or not granted else "",
                   scanned=len(confirmed), granted_targets=granted, successful=success, delivered=len(items),
                   last_success_at=iso(now) if success else section.get("last_success_at"))
    save()


def collect_profiles(state, sources, token, limits, cap, now, save, wanted):
    section = state.setdefault("profile", {})
    if float(section.get("next_run_at") or 0) > now:
        return
    selected = select_due(sources, state, "instagram_public", now, 5, wanted)
    if not selected:
        return
    section.update(checked_at=iso(now), next_run_at=now + 3 * 3600)
    fallback = []
    success = 0
    for source in selected:
        if float(section.get("direct_cooldown_until") or 0) > now:
            fallback.append(source)
            continue
        try:
            posts = fetch_public_profile(source)
            record_source(state, source, posts, now, backend="instagram_public")
            success += 1
        except (OSError, ValueError) as exc:
            # A refused logged-out request only cools this backend down.
            section["direct_cooldown_until"] = now + 86400
            section["direct_error"] = f"Public Instagram unavailable ({getattr(exc, 'code', type(exc).__name__)})"
            fallback.append(source)
    available = daily_budget(state, limits, cap, now) if token and limits else 0
    # Protect one dollar for Stories and Facebook; never buy more credit.
    if fallback and available >= 0.03 and remaining_credit(limits, cap) > 1:
        items, _ = run_actor(state, token, PROFILE_ACTOR, {"usernames": [s["username"] for s in fallback],
                                "includeAboutSection": False}, len(fallback), min(0.03, available), now, save)
        found = {str(item.get("username", "")).casefold(): item for item in items}
        for source in fallback:
            item = found.get(source["username"].casefold())
            if item:
                try:
                    posts = normalize_profile(source, item)
                    record_source(state, source, posts, now, backend="apify_public")
                    success += 1
                except ValueError as exc:
                    record_source(state, source, [], now, error=str(exc), backend="apify_public")
    section.update(status="ok" if success == len(selected) else "paused", scanned=len(selected), successful=success,
                   reason="" if success == len(selected) else "public_unavailable_credit_reserve")
    if success:
        section["last_success_at"] = iso(now)
    save()



def collect_profiles_pool(state, sources, token, limits, cap, now, save, wanted):
    """Logged-out web first, paced host-wide; Apify takes what it cannot serve."""
    section = state.setdefault("profile", {})
    if not wanted and float(section.get("next_run_at") or 0) > now:
        return
    selected = select_due(sources, state, "instagram_public", now, 5, wanted)
    if not selected:
        section.update(status="ok", reason="no_sources_due")
        return
    section.update(checked_at=iso(now), scanned=0, successful=0)
    if not wanted:
        section["next_run_at"] = now + 3 * 3600
    section.pop("direct_cooldown_until", None)  # superseded by the host-wide block
    direct_enabled = os.environ.get("HARMONICA_INSTAGRAM_PUBLIC_DIRECT", "1") != "0"
    direct = direct_enabled
    client = PublicWebClient() if direct else None
    success = failures = 0
    attempted = set()
    fallback, direct_failed = [], {}
    for source in selected:
        if not direct or not ig_public_host.wait_turn():
            direct = False
            fallback.append(source)
            continue
        try:
            posts = fetch_public_profile(source, client)
            record_source(state, source, posts, now, backend="instagram_public")
            attempted.add(source["id"])
            success += 1
            failures = 0
        except (OSError, ValueError) as exc:
            fallback.append(source)
            failures += 1
            section["direct_error"] = f"Public Instagram unavailable ({getattr(exc, 'code', None) or type(exc).__name__})"
            if is_rate_limited(exc):
                # Every collector on this host stops until the block should lift.
                ig_public_host.report_block("harmonica")
                direct = False
            else:
                direct_failed[source["id"]] = str(exc)[:240]
                # Repeated failures point at the query itself (e.g. a rotated doc id).
                direct = failures < DIRECT_MAX_CONSECUTIVE_FAILURES
    available = apify_pool.available_budget("instagram", now=now)
    count = min(len(fallback), max(0, math.floor((available + 1e-9) / 0.006)))
    if count:
        batch = fallback[:count]
        items, _ = run_actor(state, "", PROFILE_ACTOR,
                             {"usernames": [s["username"] for s in batch], "includeAboutSection": False},
                             count, round(count * 0.006, 6), now, save)
        found = {str(item.get("username", "")).casefold(): item for item in items if isinstance(item, dict)}
        for source in batch:
            attempted.add(source["id"])
            item = found.get(source["username"].casefold())
            try:
                if not item:
                    raise ValueError("Apify profile result unavailable")
                posts = normalize_profile(source, item)
                record_source(state, source, posts, now, backend="apify_public")
                success += 1
            except ValueError as exc:
                record_source(state, source, [], now, error=str(exc), backend="apify_public")
    for source in fallback[count:]:
        # Rate-limited or never-tried sources stay due for the next round.
        if source["id"] in direct_failed:
            attempted.add(source["id"])
            record_source(state, source, [], now, error=direct_failed[source["id"]], backend="instagram_public")
    section.update(status="ok" if success == len(selected) else "paused" if not attempted else "degraded",
                   scanned=len(attempted), successful=success, available_usd=available,
                   reason="" if success == len(selected) else "pool_budget_pacing" if len(fallback) > count else "partial_scan",
                   primary_backend="instagram_public", direct_enabled=direct_enabled,
                   direct_served=len(selected) - len(fallback))
    section.pop("direct_fallback_enabled", None)
    if success:
        section["last_success_at"] = iso(now)
    save()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accounts", default="", help="Check only these usernames now, bypassing polling delay but retaining all budget limits")
    parser.add_argument("--kind", choices=("all", "story", "profile"), default="all")
    parser.add_argument("--pipeline-lock-held", action="store_true")
    args = parser.parse_args()
    load_dotenv(PROJECT_ROOT / ".env")
    lock = PROJECT_ROOT / "state/run_pipeline.lock"
    if not args.pipeline_lock_held and not acquire_lock(lock, stale_after_minutes=240):
        return 0
    try:
        now = time.time()
        state = load_json(STATE, {"version": 1, "sources": {}, "runs": []})
        state["history"] = {}
        for post in load_json(PROJECT_ROOT / "site/api/latest.json", {}).get("updates", []):
            if post.get("platform") == "instagram":
                state["history"].setdefault(post.get("account", ""), []).append(post)
        sources = load_json(CONFIG, {}).get("sources", [])
        state["_affinity"] = event_affinity()
        state["_use_pool"] = True
        token, limits, cap = "", {}, 0
        quota = apify_pool.pool_status(refresh=True, now=now)
        state["quota"] = {"remaining_usd": quota.get("remainingUsd"), "monthly_cap_usd": None,
                          "checked_at": iso(now), "pool": quota}
        state.pop("quota_error", None)
        def save():
            state["updated_at"] = iso()
            save_json(STATE, {k: v for k, v in state.items() if k not in {"history", "_use_pool", "_affinity"}})
        wanted = {s.strip().lstrip("@").lower() for s in args.accounts.split(",") if s.strip()}
        for kind, collector in (("story", collect_stories), ("profile", collect_profiles_pool)):
            if args.kind not in ("all", kind):
                continue
            try:
                collector(state, sources, token, limits, cap, now, save, wanted)
            except (OSError, ValueError, RuntimeError) as exc:
                state.setdefault(kind, {}).update(status="degraded", reason=str(exc)[:240], checked_at=iso(now))
                if not wanted:
                    state[kind]["next_run_at"] = now + 3 * 3600
            save()
            print(json.dumps({kind: state.get(kind, {})}, ensure_ascii=False))
            state["quota"]["pool"] = apify_pool.pool_status(now=time.time())
            state["quota"]["remaining_usd"] = state["quota"]["pool"].get("remainingUsd")
            save()
        return 0
    finally:
        if not args.pipeline_lock_held:
            release_lock(lock)


if __name__ == "__main__":
    raise SystemExit(main())
