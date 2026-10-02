#!/usr/bin/env python3
"""Watch public harmonica social feeds and write standalone candidate rows."""

from __future__ import annotations
from story_lifecycle import display_expiry

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import http.cookiejar
import json
import os
import re
import signal
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import llm_backend

import public_tags


PROJECT_ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
DEFAULT_SEEN = PROJECT_ROOT / "state" / "social_seen.json"
DEFAULT_CANDIDATES = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
DEFAULT_ERRORS = PROJECT_ROOT / "data" / "feeds" / "social_feed_errors.jsonl"
DEFAULT_INBOX = PROJECT_ROOT / "data" / "feeds" / "social_feed_inbox.jsonl"
DEFAULT_LLM_CACHE = PROJECT_ROOT / "state" / "social_llm_tags.json"
DEFAULT_INSTAGRAM_USER_IDS = PROJECT_ROOT / "state" / "instagram_user_ids.json"
DEFAULT_FETCH_STATE = PROJECT_ROOT / "state" / "social_fetch_state.json"
DEFAULT_PROGRESS = PROJECT_ROOT / "site" / "api" / "social-fetch-progress.json"
DEFAULT_INSTAGRAM_PUBLIC_BACKFILLS = PROJECT_ROOT / "data" / "feeds" / "instagram_public_backfills.jsonl"
DEFAULT_INSTALOADER_PYTHON = Path.home() / ".config" / "harmonica" / "instaloader-venv" / "bin" / "python"
INSTALOADER_STORY_HELPER = PROJECT_ROOT / "scripts" / "instaloader_story_fetcher.py"
INSTALOADER_PROFILE_HELPER = PROJECT_ROOT / "scripts" / "instaloader_profile_fetcher.py"

GRAPH_VERSION = os.environ.get("HARMONICA_META_API_VERSION", "v25.0")
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"
RSSHUB_BASE = os.environ.get("HARMONICA_RSSHUB_BASE", "").rstrip("/")
REQUEST_TIMEOUT = 10
INSTAGRAM_BASE = "https://www.instagram.com"
TAG_RE = re.compile(r"<[^>]+>")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
IMG_RE = re.compile(r"<img\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
VIDEO_POSTER_RE = re.compile(r"<video\b[^>]*\bposter=[\"']([^\"']+)[\"']", re.IGNORECASE)
VIDEO_SRC_RE = re.compile(r"<video\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
SOURCE_SRC_RE = re.compile(r"<source\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
INSTAGRAM_PERMALINK_RE = re.compile(r"^/(?:p|reel|tv)/([^/?#]+)/?", re.IGNORECASE)
INSTAGRAM_EMBEDDED_MEDIA_IMAGE_RE = re.compile(
    r"<img\b(?=[^>]*\bclass=[\"'][^\"']*EmbeddedMediaImage[^\"']*[\"'])[^>]*\bsrc=[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
INSTAGRAM_EMBED_JSON_URL_RE = re.compile(
    r"(?:\\\"|\")(?P<field>display_url|thumbnail_src|video_url)(?:\\\"|\")\s*:\s*(?:\\\"|\")(?P<url>https:.*?)(?=\\\"|\")",
    re.IGNORECASE,
)
IMAGE_URL_EXT_RE = re.compile(r"\.(?:jpg|jpeg|png|webp|gif)(?:[?#]|$)", re.IGNORECASE)
VIDEO_URL_EXT_RE = re.compile(r"\.(?:mp4|mov|m4v|webm)(?:[?#]|$)", re.IGNORECASE)
TAG_VALUE_SPLIT_RE = re.compile(r"\s*(?:[,，、/／+&]|\band\b|\s+)\s*", re.IGNORECASE)
RSSHUB_ERROR_MESSAGE_RE = re.compile(r"Error Message:\s*<br\s*/?>\s*<code[^>]*>(.*?)</code>", re.IGNORECASE | re.DOTALL)
INSTAGRAM_PROFILE_ID_RE = re.compile(r"\"profile_id\":\"(\d+)\"|profilePage_(\d+)|\"props\":\{\"id\":\"(\d+)\"")
INSTAGRAM_POST_DATE_RE = re.compile(r"\bon\s+([A-Z][a-z]+\s+\d{1,2},\s+\d{4})\s*:", re.IGNORECASE)
INSTAGRAM_POST_LEAD_RE = re.compile(r"^[\d,]+\s+likes?,\s+[\d,]+\s+comments?\s+-\s+[^:]+:\s*", re.IGNORECASE)
STORY_EMPTY_ERROR_PATTERNS = (
    "content does not exist",
    "user has no stories",
    "this route is empty",
    "profile is private",
)
INSTALOADER_AUTH_ERROR_PATTERNS = (
    "401 unauthorized",
    "please wait a few minutes before you try again",
    "session rejected",
    "session missing",
    "login_required",
    "login required",
    "checkpoint_required",
    "challenge_required",
)
INSTALOADER_AUTH_BLOCK_KEY = "instaloader_story_auth_block"
DEFAULT_INSTAGRAM_PROFILE_INTERVAL_HOURS = 12.0
DEFAULT_INSTAGRAM_STORY_INTERVAL_HOURS = 12.0
DEFAULT_INSTAGRAM_DELAY_SECS = 8.0
DEFAULT_INSTAGRAM_BOOTSTRAP_COOLDOWN_HOURS = 6.0
DEFAULT_INSTAGRAM_MAX_ATTEMPTS_PER_RUN = 40
INSTAGRAM_SCHEDULE_EPOCH = dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)
DEFAULT_RSS_DELAY_SECS = 0.25
THREADS_BASE_URL = "https://www.threads.com"
THREADS_GRAPHQL_URL = f"{THREADS_BASE_URL}/graphql/query"
THREADS_GRAPHQL_OPERATION = "BarcelonaProfileThreadsTabRefetchableDirectQuery"
THREADS_GRAPHQL_FALLBACK_DOC_ID = "27422205010763282"
THREADS_WEB_APP_ID = "238260118697367"
THREADS_ASBD_ID = "359341"
THREADS_USER_AGENT = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1"
)
THREADS_LSD_RE = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
THREADS_PROFILE_USER_ID_RE = re.compile(
    r'"initial_thread_count":\d+.*?"user_id":"(\d+)"',
    re.DOTALL,
)
THREADS_SCRIPT_SRC_RE = re.compile(r'<script[^>]+src="(https://static\.cdninstagram\.com/[^"]+\.js)"')
THREADS_QUERY_DOC_ID_RE = re.compile(
    rf'{THREADS_GRAPHQL_OPERATION}_threadsRelayOperation".*?exports="(\d+)"',
    re.DOTALL,
)
THREADS_RELAY_VARIABLE_RE = re.compile(r'name:"(__relay_internal__pv__[A-Za-z0-9_]+)"')
THREADS_RELAY_TRUE_VARIABLES = {
    "__relay_internal__pv__BarcelonaHasCommunitiesrelayprovider",
    "__relay_internal__pv__BarcelonaHasDearAlgoConsumptionrelayprovider",
    "__relay_internal__pv__BarcelonaHasGameScoreSharerelayprovider",
    "__relay_internal__pv__BarcelonaHasMusicrelayprovider",
    "__relay_internal__pv__BarcelonaHasPublicViewCountCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasViewerRepliedrelayprovider",
    "__relay_internal__pv__BarcelonaOptionalCookiesEnabledrelayprovider",
}
THREADS_RELAY_DEFAULT_VARIABLES = THREADS_RELAY_TRUE_VARIABLES | {
    "__relay_internal__pv__BarcelonaCanSeeSponsoredContentrelayprovider",
    "__relay_internal__pv__BarcelonaGenAIRepliesEnabledrelayprovider",
    "__relay_internal__pv__BarcelonaHasCommunityEntityCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasCommunityTopContributorsrelayprovider",
    "__relay_internal__pv__BarcelonaHasDearAlgoWebProductionrelayprovider",
    "__relay_internal__pv__BarcelonaHasEventBadgerelayprovider",
    "__relay_internal__pv__BarcelonaHasGhostPostEmojiActivationrelayprovider",
    "__relay_internal__pv__BarcelonaHasMessagingrelayprovider",
    "__relay_internal__pv__BarcelonaHasNewspaperLinkStylerelayprovider",
    "__relay_internal__pv__BarcelonaHasPodcastTextFragmentsrelayprovider",
    "__relay_internal__pv__BarcelonaHasPrivateRepliesDeprecationrelayprovider",
    "__relay_internal__pv__BarcelonaHasProfileSelfReplyContextrelayprovider",
    "__relay_internal__pv__BarcelonaHasScorecardCommunityrelayprovider",
    "__relay_internal__pv__BarcelonaHasSportTeamAllegianceCardrelayprovider",
    "__relay_internal__pv__BarcelonaHasWebFaviconsrelayprovider",
    "__relay_internal__pv__BarcelonaIsCrawlerrelayprovider",
    "__relay_internal__pv__BarcelonaIsInternalUserrelayprovider",
    "__relay_internal__pv__BarcelonaIsLoggedInrelayprovider",
    "__relay_internal__pv__BarcelonaIsSearchDiscoveryEnabledrelayprovider",
    "__relay_internal__pv__BarcelonaShouldFulfillLightboxQueryrelayprovider",
    "__relay_internal__pv__BarcelonaShouldShowFediverseM075Featuresrelayprovider",
}
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = llm_backend.DEFAULT_API_MODEL
DEFAULT_LLM_KEYCHAIN_SERVICE = "harmonica-openai"
DEFAULT_LLM_KEYCHAIN_ACCOUNT = "harmonica"
LLM_CATEGORIES = {"events", "posts-videos", "student-clubs", "opportunities"}
LLM_LABELS = set(public_tags.PUBLIC_TAGS)
TRUTHY = {"1", "true", "yes", "y", "on"}
_INSTAGRAM_USER_IDS_CACHE: dict[str, Any] | None = None


class InstagramMetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() != "meta":
            return
        values = {str(key).casefold(): str(value or "") for key, value in attrs}
        key = values.get("property") or values.get("name")
        content = values.get("content")
        if key and content:
            self.meta.setdefault(key.casefold(), content)
_THREADS_QUERY_METADATA_CACHE: tuple[str, set[str]] | None = None


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


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


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")
    tmp.replace(path)


def env_float(name: str, default: float, *, minimum: float | None = None) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = float(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def env_int(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        value = default
    else:
        try:
            value = int(raw)
        except ValueError:
            value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def parse_datetime(value: Any) -> dt.datetime | None:
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


def project_path(value: str | os.PathLike[str]) -> Path:
    path = Path(str(value)).expanduser()
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def http_json(url: str, params: dict[str, Any], token: str | None) -> dict[str, Any]:
    query = dict(params)
    if token:
        query["access_token"] = token
    full_url = url + "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(full_url, headers={"User-Agent": "HarmonicaInTaiwanSocialWatcher/1.0"})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def strip_html(value: str) -> str:
    text = BR_RE.sub("\n", value or "")
    text = TAG_RE.sub(" ", text)
    lines = [re.sub(r"[ \t]+", " ", html.unescape(line)).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def rsshub_error_message(body: bytes) -> str:
    text = body.decode("utf-8", "replace")
    match = RSSHUB_ERROR_MESSAGE_RE.search(text)
    if match:
        text = match.group(1)
    return compact_text(strip_html(text), 500)


def is_story_empty_error(message: str) -> bool:
    lowered = (message or "").casefold()
    return any(pattern in lowered for pattern in STORY_EMPTY_ERROR_PATTERNS)


def env_file_value(path: Path, name: str) -> str:
    if not path.exists():
        return ""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").strip()
        key, sep, value = line.partition("=")
        if sep and key.strip() == name:
            return value.strip().strip('"').strip("'")
    return ""


def instagram_cookie() -> str:
    for key in ("HARMONICA_IG_COOKIE", "IG_COOKIE"):
        value = os.environ.get(key)
        if value:
            return value.strip()
    env_paths = [
        Path(path).expanduser()
        for path in os.environ.get("HARMONICA_RSSHUB_ENV", "").split(os.pathsep)
        if path.strip()
    ]
    env_paths.extend(
        [
            Path.home() / ".config" / "harmonica" / "rsshub.env",
            Path.home() / "Documents" / "Bamboo Melody Club" / "ops" / "rsshub" / ".env",
        ]
    )
    for path in env_paths:
        value = env_file_value(path, "IG_COOKIE")
        if value:
            return value
    return ""


def instagram_csrf_token(cookie: str) -> str:
    match = re.search(r"(?:^|;\s*)csrftoken=([^;]+)", cookie or "")
    return match.group(1) if match else ""


def instagram_headers(cookie: str = "", referer: str = "") -> dict[str, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_6_1) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "X-ASBD-ID": "359341",
        "X-IG-App-ID": "936619743392459",
        "X-IG-WWW-Claim": "0",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": referer or INSTAGRAM_BASE + "/",
    }
    if cookie:
        headers["Cookie"] = cookie
        csrf = instagram_csrf_token(cookie)
        if csrf:
            headers["X-CSRFToken"] = csrf
    return headers


def instagram_json(path: str, query: dict[str, Any], cookie: str, referer: str) -> dict[str, Any]:
    url = INSTAGRAM_BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers=instagram_headers(cookie, referer))
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def instagram_user_ids_cache() -> dict[str, Any]:
    global _INSTAGRAM_USER_IDS_CACHE
    if _INSTAGRAM_USER_IDS_CACHE is None:
        _INSTAGRAM_USER_IDS_CACHE = load_json(DEFAULT_INSTAGRAM_USER_IDS, {"version": 1, "users": {}})
        if not isinstance(_INSTAGRAM_USER_IDS_CACHE, dict):
            _INSTAGRAM_USER_IDS_CACHE = {"version": 1, "users": {}}
        if not isinstance(_INSTAGRAM_USER_IDS_CACHE.get("users"), dict):
            _INSTAGRAM_USER_IDS_CACHE["users"] = {}
    return _INSTAGRAM_USER_IDS_CACHE


def save_instagram_user_ids_cache() -> None:
    if _INSTAGRAM_USER_IDS_CACHE is not None:
        save_json(DEFAULT_INSTAGRAM_USER_IDS, _INSTAGRAM_USER_IDS_CACHE)


def instagram_user_id(username: str) -> str:
    clean_username = str(username or "").strip().strip("@/")
    if not clean_username:
        return ""
    cache = instagram_user_ids_cache()
    users = cache.setdefault("users", {})
    cached = users.get(clean_username.casefold())
    if isinstance(cached, dict) and cached.get("id"):
        return str(cached["id"])

    profile_url = f"{INSTAGRAM_BASE}/{urllib.parse.quote(clean_username)}/"
    req = urllib.request.Request(profile_url, headers=instagram_headers(referer=profile_url))
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            text = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return ""
    for match in INSTAGRAM_PROFILE_ID_RE.finditer(text):
        user_id = next((group for group in match.groups() if group), "")
        if user_id:
            users[clean_username.casefold()] = {
                "id": user_id,
                "username": clean_username,
                "resolved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                "source": "instagram_profile_html",
            }
            save_instagram_user_ids_cache()
            return user_id
    return ""


def cached_instagram_user_id(username: str) -> str:
    clean_username = str(username or "").strip().strip("@/").casefold()
    if not clean_username:
        return ""
    cached = instagram_user_ids_cache().get("users", {}).get(clean_username)
    return str(cached.get("id") or "") if isinstance(cached, dict) else ""


def instagram_public_backfill_urls(source: dict[str, Any]) -> list[str]:
    if not DEFAULT_INSTAGRAM_PUBLIC_BACKFILLS.exists():
        return []
    source_id = str(source.get("id") or "")
    urls: list[str] = []
    try:
        rows = DEFAULT_INSTAGRAM_PUBLIC_BACKFILLS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in rows:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("source_id") or "") != source_id:
            continue
        url = instagram_permalink_url(str(row.get("url") or ""))
        if url and url not in urls:
            urls.append(url)
    return urls


def fetch_instagram_public_post(source: dict[str, Any], url: str, *, source_feed_url: str = "") -> dict[str, Any] | None:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 HarmonicaInTaiwanSocialWatcher/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None

    parser = InstagramMetaParser()
    parser.feed(body)
    meta = parser.meta
    description = str(meta.get("og:description") or meta.get("description") or "")
    description = INSTAGRAM_POST_LEAD_RE.sub("", description).strip().strip('"').strip()
    if description.endswith('".'):
        description = description[:-2].rstrip()
    posted_at = ""
    date_match = INSTAGRAM_POST_DATE_RE.search(str(meta.get("og:description") or meta.get("description") or ""))
    if date_match:
        for date_format in ("%B %d, %Y", "%b %d, %Y"):
            try:
                posted_at = dt.datetime.strptime(date_match.group(1), date_format).replace(tzinfo=dt.timezone.utc).isoformat()
                break
            except ValueError:
                continue
    permalink = instagram_permalink_url(str(meta.get("og:url") or url)) or url
    shortcode_match = INSTAGRAM_PERMALINK_RE.match(urllib.parse.urlsplit(permalink).path)
    post_id = shortcode_match.group(1) if shortcode_match else permalink
    images = [str(meta.get("og:image"))] if meta.get("og:image") else []
    videos = [str(meta.get("og:video"))] if meta.get("og:video") else []
    if not description and not images and not videos:
        return None
    return normalize_post(
        source,
        post_id=post_id,
        text=description,
        url=permalink,
        posted_at=posted_at,
        images=images,
        videos=videos,
        source_feed_url=source_feed_url or url,
    )


def fetch_instagram_public_backfill(source: dict[str, Any], *, source_feed_url: str = "") -> list[dict[str, Any]]:
    posts: list[dict[str, Any]] = []
    for url in instagram_public_backfill_urls(source):
        post = fetch_instagram_public_post(source, url, source_feed_url=source_feed_url)
        if post:
            posts.append(post)
    return posts


def unix_time(value: Any) -> str:
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return ""
    return dt.datetime.fromtimestamp(timestamp, dt.timezone.utc).isoformat()


def instagram_story_url(username: str, item_id: str) -> str:
    media_id = str(item_id or "").split("_", 1)[0]
    base = f"{INSTAGRAM_BASE}/stories/{urllib.parse.quote(username)}/"
    return f"{base}{urllib.parse.quote(media_id)}/" if media_id else base


def instagram_story_text(item: dict[str, Any]) -> str:
    parts: list[str] = []
    caption = item.get("caption")
    if isinstance(caption, dict) and caption.get("text"):
        parts.append(str(caption["text"]))
    for sticker in item.get("story_link_stickers") or []:
        link = sticker.get("url") or (sticker.get("link_sticker") or {}).get("url")
        if link:
            parts.append(str(link))
    return "\n".join(parts)


def fetch_instagram_web_story(source: dict[str, Any], *, source_feed_url: str = "") -> list[dict[str, Any]]:
    username = str(source.get("username") or "").strip().strip("@/")
    if not username:
        return []
    cookie = instagram_cookie()
    if not cookie:
        return []
    user_id = str(source.get("instagram_user_id") or instagram_user_id(username) or "")
    if not user_id:
        return []
    referer = f"{INSTAGRAM_BASE}/stories/{urllib.parse.quote(username)}/"
    try:
        data = instagram_json("/api/v1/feed/reels_media/", {"reel_ids": user_id}, cookie, referer)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return []

    reels = data.get("reels") if isinstance(data, dict) else {}
    reel = reels.get(user_id) if isinstance(reels, dict) else {}
    if not reel and isinstance(data.get("reels_media"), list) and data["reels_media"]:
        reel = data["reels_media"][0]
    if not isinstance(reel, dict):
        return []
    items = reel.get("items") or []
    if not isinstance(items, list):
        return []

    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    user = reel.get("user") if isinstance(reel.get("user"), dict) else {}
    avatar_url = str(user.get("profile_pic_url") or "")
    posts: list[dict[str, Any]] = []
    fallback_source = {**source, "story_provider": "instagram_web"}
    for item in items:
        if not isinstance(item, dict):
            continue
        post_id = str(item.get("id") or item.get("pk") or "")
        image_candidates = ((item.get("image_versions2") or {}).get("candidates") or [])
        images = [str(candidate.get("url")) for candidate in image_candidates if candidate.get("url")]
        videos = [str(video.get("url")) for video in (item.get("video_versions") or []) if video.get("url")]
        post = normalize_post(
            fallback_source,
            post_id=post_id or (images + videos + [fetched_at])[0],
            text=instagram_story_text(item),
            url=instagram_story_url(username, post_id),
            posted_at=unix_time(item.get("taken_at")) or fetched_at,
            images=images,
            videos=videos,
            source_avatar_url=avatar_url,
            source_feed_url=source_feed_url or referer,
            rsshub_guid=post_id,
            rsshub_title=f"Instagram story @{username}",
            story_fetched_at=fetched_at,
        )
        if item.get("expiring_at"):
            post["story_expires_at"] = unix_time(item.get("expiring_at"))
        post["instagram_user_id"] = user_id
        posts.append(post)
    return posts


def fetch_instaloader_story(source: dict[str, Any]) -> list[dict[str, Any]]:
    username = str(source.get("username") or "").strip().strip("@/")
    if not username:
        raise ValueError("Instaloader story source is missing username")
    python = Path(
        os.environ.get("HARMONICA_INSTALOADER_PYTHON", str(DEFAULT_INSTALOADER_PYTHON))
    ).expanduser()
    if not python.exists():
        raise ValueError(f"Instaloader Python not found: {python}")
    command = [
        str(python),
        str(INSTALOADER_STORY_HELPER),
        "--username",
        username,
        "--limit",
        str(max(1, int(source.get("limit") or 5))),
    ]
    user_id = str(source.get("instagram_user_id") or cached_instagram_user_id(username) or "")
    if user_id:
        command.extend(["--user-id", user_id])
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=75,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Instaloader story fetch timed out for @{username}") from exc
    if result.returncode != 0:
        detail = compact_text(result.stderr or result.stdout or "Instaloader failed", 500)
        raise ValueError(f"Instaloader story fetch failed for @{username}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Instaloader returned invalid JSON for @{username}") from exc
    rows = payload.get("stories") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Instaloader returned no stories list for @{username}")
    fetched_at = str(payload.get("fetched_at") or dt.datetime.now(dt.timezone.utc).isoformat())
    posts: list[dict[str, Any]] = []
    normalized_source = {**source, "story_provider": "instaloader"}
    for row in rows:
        if not isinstance(row, dict):
            continue
        images = [str(value) for value in row.get("images") or [] if value]
        videos = [str(value) for value in row.get("videos") or [] if value]
        post_id = str(row.get("id") or row.get("url") or "")
        if not post_id or not images and not videos:
            continue
        post = normalize_post(
            normalized_source,
            post_id=post_id,
            text=str(row.get("caption") or ""),
            url=str(row.get("url") or instagram_story_url(username, post_id)),
            posted_at=str(row.get("posted_at") or fetched_at),
            images=images,
            videos=videos,
            source_feed_url=str(source.get("source_profile_url") or f"{INSTAGRAM_BASE}/{username}/"),
            rsshub_guid=post_id,
            rsshub_title=f"Instagram story @{username}",
            story_fetched_at=fetched_at,
        )
        if row.get("expires_at"):
            post["story_expires_at"] = str(row["expires_at"])
        posts.append(post)
    return posts


def fetch_instaloader_profile(source: dict[str, Any]) -> list[dict[str, Any]]:
    username = str(source.get("username") or "").strip().strip("@/")
    if not username:
        raise ValueError("Instaloader profile source is missing username")
    python = Path(
        os.environ.get("HARMONICA_INSTALOADER_PYTHON", str(DEFAULT_INSTALOADER_PYTHON))
    ).expanduser()
    if not python.exists():
        raise ValueError(f"Instaloader Python not found: {python}")
    command = [
        str(python),
        str(INSTALOADER_PROFILE_HELPER),
        "--username",
        username,
        "--limit",
        str(max(1, int(source.get("limit") or 5))),
    ]
    user_id = str(source.get("instagram_user_id") or cached_instagram_user_id(username) or "")
    if user_id:
        command.extend(["--user-id", user_id])
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=75,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"Instaloader profile fetch timed out for @{username}") from exc
    if result.returncode != 0:
        detail = compact_text(result.stderr or result.stdout or "Instaloader failed", 500)
        raise ValueError(f"Instaloader profile fetch failed for @{username}: {detail}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Instaloader returned invalid profile JSON for @{username}") from exc
    rows = payload.get("posts") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError(f"Instaloader returned no posts list for @{username}")
    posts: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        images = [str(value) for value in row.get("images") or [] if value]
        videos = [str(value) for value in row.get("videos") or [] if value]
        post_id = str(row.get("id") or row.get("url") or "")
        if not post_id:
            continue
        posts.append(
            normalize_post(
                source,
                post_id=post_id,
                text=str(row.get("caption") or ""),
                url=str(row.get("url") or ""),
                posted_at=str(row.get("posted_at") or ""),
                images=images,
                videos=videos,
                source_feed_url=str(source.get("source_profile_url") or f"{INSTAGRAM_BASE}/{username}/"),
            )
        )
    return posts


def image_urls(value: str) -> list[str]:
    urls: list[str] = []
    for raw in [*IMG_RE.findall(value or ""), *VIDEO_POSTER_RE.findall(value or "")]:
        url = html.unescape(raw)
        if url and url not in urls:
            urls.append(url)
    return urls


def video_urls(value: str) -> list[str]:
    urls: list[str] = []
    for raw in [*VIDEO_SRC_RE.findall(value or ""), *SOURCE_SRC_RE.findall(value or "")]:
        url = html.unescape(raw)
        if url and url not in urls:
            urls.append(url)
    return urls


def append_unique(urls: list[str], url: str) -> None:
    clean = html.unescape(str(url or "")).strip()
    if clean and clean not in urls:
        urls.append(clean)


def decode_instagram_embed_url(raw: str) -> str:
    value = html.unescape(raw or "")
    for _ in range(2):
        try:
            decoded = json.loads(f'"{value}"')
        except json.JSONDecodeError:
            break
        if decoded == value:
            break
        value = decoded
    return html.unescape(value.replace("\\/", "/")).strip()


def instagram_permalink_url(value: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(value or "")
    except ValueError:
        return ""
    if not parsed.netloc.endswith("instagram.com"):
        return ""
    match = INSTAGRAM_PERMALINK_RE.match(parsed.path or "")
    if not match:
        return ""
    kind = parsed.path.strip("/").split("/", 1)[0].lower()
    shortcode = match.group(1)
    return f"{INSTAGRAM_BASE}/{kind}/{url_part(shortcode)}/"


def instagram_embed_media(value: str) -> tuple[list[str], list[str]]:
    permalink = instagram_permalink_url(value)
    if not permalink:
        return [], []
    req = urllib.request.Request(
        permalink + "embed/",
        headers={"User-Agent": "Mozilla/5.0 HarmonicaInTaiwanSocialWatcher/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            body = response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return [], []

    images: list[str] = []
    videos: list[str] = []
    for raw in INSTAGRAM_EMBEDDED_MEDIA_IMAGE_RE.findall(body):
        append_unique(images, decode_instagram_embed_url(raw))
    for match in INSTAGRAM_EMBED_JSON_URL_RE.finditer(body):
        url = decode_instagram_embed_url(match.group("url"))
        if match.group("field").casefold() == "video_url":
            append_unique(videos, url)
        else:
            append_unique(images, url)
    return images, videos


def xml_media_urls(element: ET.Element) -> tuple[list[str], list[str]]:
    images: list[str] = []
    videos: list[str] = []
    for child in element.iter():
        url = child.attrib.get("url") or child.attrib.get("href")
        if not url:
            continue
        local_name = child.tag.rsplit("}", 1)[-1].casefold()
        media_type = str(child.attrib.get("type") or "").casefold()
        medium = str(child.attrib.get("medium") or "").casefold()
        if (
            local_name == "thumbnail"
            or medium == "image"
            or media_type.startswith("image/")
            or IMAGE_URL_EXT_RE.search(url)
        ):
            append_unique(images, url)
        elif (
            local_name == "player"
            or medium == "video"
            or media_type.startswith("video/")
            or VIDEO_URL_EXT_RE.search(url)
        ):
            append_unique(videos, url)
    return images, videos


def merge_media_urls(primary: list[str], fallback: list[str]) -> list[str]:
    merged = list(primary)
    for url in fallback:
        append_unique(merged, url)
    return merged


def enrich_instagram_profile_media(
    source: dict[str, Any],
    link: str,
    images: list[str],
    videos: list[str],
) -> tuple[list[str], list[str]]:
    if source.get("type") != "rsshub_instagram_profile" or source.get("platform") != "instagram" or images:
        return images, videos
    embed_images, embed_videos = instagram_embed_media(link)
    return merge_media_urls(images, embed_images), merge_media_urls(videos, embed_videos)


def text_of(element: ET.Element, name: str) -> str:
    child = element.find(name)
    return (child.text or "").strip() if child is not None else ""


def atom_text(element: ET.Element, name: str) -> str:
    child = element.find(f"{{http://www.w3.org/2005/Atom}}{name}")
    return (child.text or "").strip() if child is not None else ""


def url_part(value: Any) -> str:
    return urllib.parse.quote(str(value or ""), safe="")


def format_rsshub_route(route: str, source: dict[str, Any]) -> str:
    values = {
        "username": url_part(source.get("username") or ""),
        "page": url_part(source.get("page") or source.get("username") or ""),
        "id": url_part(source.get("account_id") or source.get("page") or source.get("username") or ""),
    }
    if not route.startswith("/"):
        route = "/" + route
    for key, value in values.items():
        route = route.replace("{" + key + "}", value)
    return route


def rsshub_url(source: dict[str, Any]) -> str:
    base = str(RSSHUB_BASE or source.get("rsshub_base") or "").rstrip("/")
    if not base:
        return ""

    route = source.get("route")
    if route:
        return base + format_rsshub_route(str(route), source)

    kind = source.get("type")
    if kind == "rsshub_facebook_page":
        page = source.get("page") or source.get("username")
        return f"{base}/facebook/page/{url_part(page)}" if page else ""

    if kind == "rsshub_instagram_profile":
        username = source.get("username")
        if not username:
            return ""
        provider = str(source.get("provider") or "picuki")
        if provider in {"cookie", "instagram_cookie"}:
            return f"{base}/instagram/2/user/{url_part(username)}"
        if provider == "picnob":
            return f"{base}/picnob/profile/{url_part(username)}"
        if provider in {"private_api", "instagram"}:
            return f"{base}/instagram/user/{url_part(username)}"
        return f"{base}/picuki/profile/{url_part(username)}"

    return ""


def compact_text(text: str, limit: int = 1600) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in (text or "").splitlines()]
    clean_lines: list[str] = []
    for line in lines:
        if line and (not clean_lines or clean_lines[-1] != line):
            clean_lines.append(line)
    cleaned = "\n".join(clean_lines).strip()
    return cleaned[:limit]


def is_story_source(source: dict[str, Any]) -> bool:
    return str(source.get("type") or "") == "rsshub_instagram_story" or str(source.get("media_type") or "") == "instagram_story"


def instagram_source_kind(source: dict[str, Any]) -> str:
    kind = str(source.get("type") or "")
    if kind == "rsshub_instagram_profile":
        return "profile"
    if kind == "rsshub_instagram_story" or str(source.get("media_type") or "") == "instagram_story":
        return "story"
    return ""


def source_identity(source: dict[str, Any]) -> str:
    return str(source.get("id") or source.get("url") or source.get("username") or source.get("page") or "").strip()


def progress_source_summary(source: dict[str, Any]) -> dict[str, str]:
    name = (
        source.get("name")
        or source.get("title")
        or source.get("handle")
        or source.get("username")
        or source.get("url")
        or source.get("feed_url")
        or ""
    )
    return {
        "id": source_identity(source),
        "type": str(source.get("type") or ""),
        "platform": str(source.get("platform") or ""),
        "name": compact_text(str(name), 160),
    }


def utc_iso(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def stable_offset_seconds(value: str, interval_seconds: float) -> float:
    if interval_seconds <= 0:
        return 0.0
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return (int(digest[:12], 16) / float(0xFFFFFFFFFFFF)) * interval_seconds


def instagram_interval_hours(source: dict[str, Any], args: argparse.Namespace) -> float:
    kind = instagram_source_kind(source)
    if kind == "story":
        return max(0.0, float(args.instagram_story_interval_hours))
    if kind == "profile":
        return max(0.0, float(args.instagram_profile_interval_hours))
    return 0.0


def scheduled_instagram_due_at(
    source: dict[str, Any],
    *,
    anchor: dt.datetime,
    interval_hours: float,
) -> dt.datetime:
    source_id = source_identity(source)
    kind = instagram_source_kind(source)
    interval_seconds = max(0.0, interval_hours * 3600.0)
    anchor_utc = anchor.astimezone(dt.timezone.utc)
    offset = stable_offset_seconds(f"{kind}:{source_id}", interval_seconds)
    if interval_seconds <= 0:
        return anchor_utc
    elapsed = (anchor_utc - INSTAGRAM_SCHEDULE_EPOCH).total_seconds()
    cycles = int((elapsed - offset) // interval_seconds)
    due_at = INSTAGRAM_SCHEDULE_EPOCH + dt.timedelta(seconds=(cycles * interval_seconds) + offset)
    if due_at < anchor_utc:
        due_at += dt.timedelta(seconds=interval_seconds)
    return due_at


def next_scheduled_instagram_due_at(
    source: dict[str, Any],
    *,
    after: dt.datetime,
    interval_hours: float,
) -> dt.datetime:
    interval_seconds = max(0.0, interval_hours * 3600.0)
    after_utc = after.astimezone(dt.timezone.utc)
    due_at = scheduled_instagram_due_at(source, anchor=after_utc, interval_hours=interval_hours)
    if interval_seconds > 0 and due_at <= after_utc:
        due_at += dt.timedelta(seconds=interval_seconds)
    return due_at


def normalize_fetch_state(value: Any) -> dict[str, Any]:
    state = value if isinstance(value, dict) else {}
    sources = state.get("sources")
    if not isinstance(sources, dict):
        sources = {}
    return {
        **state,
        "version": 1,
        "sources": sources,
    }


def is_instaloader_source(source: dict[str, Any]) -> bool:
    return (
        bool(instagram_source_kind(source))
        and str(source.get("story_provider") or source.get("provider") or "") == "instaloader"
    )


def externally_collected_instagram(source: dict[str, Any]) -> bool:
    return str(source.get("provider") or "") in {"instagram_public", "apify_stories"}


def cached_instagram_posts(source: dict[str, Any]) -> list[dict[str, Any]]:
    state = load_json(PROJECT_ROOT / "state" / "instagram_public.json", {})
    posts = state.get("sources", {}).get(source["id"], {}).get("posts", [])
    now = dt.datetime.now(dt.timezone.utc)
    return [p for p in posts if not is_story_source(source) or
            ((expiry := display_expiry(p)) is not None and expiry > now)]


def is_instaloader_auth_error(error: str) -> bool:
    message = str(error or "").casefold()
    return any(pattern in message for pattern in INSTALOADER_AUTH_ERROR_PATTERNS)


def instaloader_auth_block_reason(
    fetch_state: dict[str, Any],
    *,
    now: dt.datetime,
) -> str:
    block = fetch_state.get(INSTALOADER_AUTH_BLOCK_KEY)
    if not isinstance(block, dict):
        return ""
    blocked_until = parse_datetime(block.get("blocked_until"))
    if blocked_until is None or blocked_until <= now:
        fetch_state.pop(INSTALOADER_AUTH_BLOCK_KEY, None)
        return ""
    return f"Instaloader auth blocked until {utc_iso(blocked_until)}"


def set_instaloader_auth_block(
    fetch_state: dict[str, Any],
    *,
    now: dt.datetime,
    cooldown_hours: float,
    error: str,
) -> None:
    fetch_state[INSTALOADER_AUTH_BLOCK_KEY] = {
        "detected_at": utc_iso(now),
        "blocked_until": utc_iso(now + dt.timedelta(hours=max(0.25, cooldown_hours))),
        "error": compact_text(error, 500),
    }


def clear_instaloader_auth_block(fetch_state: dict[str, Any]) -> None:
    fetch_state.pop(INSTALOADER_AUTH_BLOCK_KEY, None)


def instagram_bootstrap_anchor(
    fetch_state: dict[str, Any],
    seen: dict[str, Any],
    sources: list[dict[str, Any]],
    args: argparse.Namespace,
) -> dt.datetime | None:
    entries = fetch_state.get("sources") if isinstance(fetch_state.get("sources"), dict) else {}
    has_instagram_entries = any(
        source_identity(source) in entries
        for source in sources
        if instagram_source_kind(source)
    )
    if has_instagram_entries:
        return None
    observed_at = parse_datetime(seen.get("updated_at") or seen.get("initialized_at"))
    if observed_at is None:
        return None
    cooldown = max(0.0, float(args.instagram_bootstrap_cooldown_hours))
    return observed_at + dt.timedelta(hours=cooldown)


def instagram_due_info(
    source: dict[str, Any],
    fetch_state: dict[str, Any],
    *,
    now: dt.datetime,
    args: argparse.Namespace,
    bootstrap_anchor: dt.datetime | None,
) -> tuple[bool, str, bool]:
    kind = instagram_source_kind(source)
    if not kind or args.instagram_force:
        return True, "", False

    interval_hours = instagram_interval_hours(source, args)
    if interval_hours <= 0:
        return True, "", False

    source_id = source_identity(source)
    if not source_id:
        return True, "", False

    entries = fetch_state.setdefault("sources", {})
    entry = entries.setdefault(source_id, {})
    changed = False
    next_due_at = parse_datetime(entry.get("next_due_at"))
    try:
        previous_interval_hours = float(entry.get("interval_hours"))
    except (TypeError, ValueError):
        previous_interval_hours = None
    interval_changed = previous_interval_hours is None or abs(previous_interval_hours - interval_hours) > 0.001
    if next_due_at is None or interval_changed:
        last_attempt_at = parse_datetime(entry.get("last_attempt_at") or entry.get("last_success_at"))
        if next_due_at is None:
            anchor = bootstrap_anchor or now
        elif last_attempt_at is not None:
            anchor = last_attempt_at + dt.timedelta(hours=interval_hours)
        else:
            anchor = now
        next_due_at = scheduled_instagram_due_at(source, anchor=anchor, interval_hours=interval_hours)
        entry.update(
            {
                "source_type": str(source.get("type") or ""),
                "interval_hours": interval_hours,
                "next_due_at": utc_iso(next_due_at),
            }
        )
        if bootstrap_anchor is not None:
            entry.setdefault("last_status", "bootstrap_scheduled")
        else:
            entry.setdefault("last_status", "scheduled")
        changed = True

    if next_due_at > now:
        return False, f"scheduled until {utc_iso(next_due_at)}", changed
    return True, "", changed


def record_instagram_attempt(
    fetch_state: dict[str, Any],
    source: dict[str, Any],
    *,
    now: dt.datetime,
    args: argparse.Namespace,
    status: str,
    post_count: int = 0,
    error: str = "",
) -> None:
    if not instagram_source_kind(source):
        return
    source_id = source_identity(source)
    if not source_id:
        return
    interval_hours = instagram_interval_hours(source, args)
    entry = fetch_state.setdefault("sources", {}).setdefault(source_id, {})
    next_due_at = next_scheduled_instagram_due_at(source, after=now, interval_hours=interval_hours) if interval_hours > 0 else None
    entry.update(
        {
            "source_type": str(source.get("type") or ""),
            "interval_hours": interval_hours,
            "last_attempt_at": utc_iso(now),
            "last_status": status,
            "last_post_count": int(post_count),
            "next_due_at": utc_iso(next_due_at) if next_due_at is not None else "",
        }
    )
    if status == "ok":
        entry["last_success_at"] = utc_iso(now)
        entry["consecutive_errors"] = 0
        entry.pop("last_error", None)
    elif error:
        entry["last_error_at"] = utc_iso(now)
        entry["last_error"] = compact_text(error, 500)
        entry["consecutive_errors"] = int(entry.get("consecutive_errors") or 0) + 1


def record_instagram_skip(fetch_state: dict[str, Any], source: dict[str, Any], *, now: dt.datetime, reason: str) -> None:
    if not instagram_source_kind(source):
        return
    source_id = source_identity(source)
    if not source_id:
        return
    entry = fetch_state.setdefault("sources", {}).setdefault(source_id, {})
    entry.update(
        {
            "source_type": str(source.get("type") or ""),
            "last_skipped_at": utc_iso(now),
            "last_skip_reason": reason,
        }
    )


def webpage_due_info(
    source: dict[str, Any],
    fetch_state: dict[str, Any],
    *,
    now: dt.datetime,
    force: bool = False,
) -> tuple[bool, str, bool, bool]:
    """Return due state plus whether this is the watcher's first baseline."""
    if str(source.get("type") or "") != "webpage_watch":
        return True, "", False, False
    source_id = source_identity(source)
    entries = fetch_state.setdefault("sources", {})
    entry = entries.setdefault(source_id, {})
    # Lineup crawls emit only harmonica pages, so even the first scan is reported.
    initial_baseline = not bool(entry.get("last_success_at")) and not source.get("follow_links")
    interval_hours = max(0.5, float(source.get("interval_hours") or 12.0))
    next_due_at = parse_datetime(entry.get("next_due_at"))
    changed = False
    if next_due_at is None:
        entry.update(
            {
                "source_type": "webpage_watch",
                "interval_hours": interval_hours,
                "next_due_at": utc_iso(now),
            }
        )
        next_due_at = now
        changed = True
    if next_due_at > now and not force:
        return False, f"scheduled until {utc_iso(next_due_at)}", changed, initial_baseline
    return True, "", changed, initial_baseline


def record_webpage_attempt(
    fetch_state: dict[str, Any],
    source: dict[str, Any],
    *,
    now: dt.datetime,
    status: str,
    post_count: int = 0,
    error: str = "",
) -> None:
    if str(source.get("type") or "") != "webpage_watch":
        return
    source_id = source_identity(source)
    interval_hours = max(0.5, float(source.get("interval_hours") or 12.0))
    retry_hours = min(interval_hours, 1.0) if status != "ok" else interval_hours
    entry = fetch_state.setdefault("sources", {}).setdefault(source_id, {})
    entry.update(
        {
            "source_type": "webpage_watch",
            "interval_hours": interval_hours,
            "last_attempt_at": utc_iso(now),
            "last_status": status,
            "last_post_count": int(post_count),
            "next_due_at": utc_iso(now + dt.timedelta(hours=retry_hours)),
        }
    )
    if status == "ok":
        entry["last_success_at"] = utc_iso(now)
        entry["consecutive_errors"] = 0
        entry.pop("last_error", None)
    elif error:
        entry["last_error_at"] = utc_iso(now)
        entry["last_error"] = compact_text(error, 500)
        entry["consecutive_errors"] = int(entry.get("consecutive_errors") or 0) + 1


def source_delay_secs(source: dict[str, Any], token: str | None, args: argparse.Namespace) -> float:
    if externally_collected_instagram(source):
        return 0.0
    if instagram_source_kind(source):
        return max(0.0, float(args.instagram_delay_secs))
    return DEFAULT_RSS_DELAY_SECS if should_throttle_source(source, token) else 0.0


def normalize_post(
    source: dict[str, Any],
    *,
    post_id: str,
    text: str,
    url: str,
    posted_at: str,
    media_type: str = "",
    images: list[str] | None = None,
    videos: list[str] | None = None,
    source_avatar_url: str = "",
    source_feed_url: str = "",
    rsshub_guid: str = "",
    rsshub_title: str = "",
    story_fetched_at: str = "",
) -> dict[str, Any]:
    source_id = source["id"]
    account = source.get("username") or source.get("page") or source.get("url") or ""
    story_source = is_story_source(source)
    normalized_text = compact_text(text)
    if story_source and not normalized_text:
        normalized_text = f"Instagram story @{account}" if account else "Instagram story"
    post = {
        "key": f"{source_id}:{post_id or url}",
        "source_id": source_id,
        "source_name": source.get("name") or source_id,
        "platform": source.get("platform") or source.get("type"),
        "account": account,
        "post_id": post_id,
        "posted_at": posted_at,
        "url": url,
        "source_profile_url": source.get("profile_url") or source.get("source_profile_url") or "",
        "media_type": media_type or source.get("media_type") or "",
        "images": images or [],
        "image_url": (images or [""])[0],
        "videos": videos or [],
        "source_avatar_url": source_avatar_url,
        "text": normalized_text,
    }
    if source.get("include_without_keywords"):
        post["include_without_keywords"] = True
    if source.get("ephemeral"):
        post["ephemeral"] = True
    if source_feed_url:
        post["source_feed_url"] = source_feed_url
    if story_source:
        post.update(
            {
                "include_without_keywords": True,
                "media_type": "instagram_story",
                "story": True,
                "story_provider": source.get("story_provider") or "rsshub_picuki",
                "story_fetched_at": story_fetched_at,
                "source_feed_url": source_feed_url,
                "rsshub_guid": rsshub_guid,
                "rsshub_title": rsshub_title,
            }
        )
    return post


def threads_query_metadata(opener: urllib.request.OpenerDirector, profile_html: str) -> tuple[str, set[str]]:
    global _THREADS_QUERY_METADATA_CACHE
    if _THREADS_QUERY_METADATA_CACHE is not None:
        return _THREADS_QUERY_METADATA_CACHE

    script_urls = list(dict.fromkeys(html.unescape(url) for url in THREADS_SCRIPT_SRC_RE.findall(profile_html)))
    for script_url in reversed(script_urls):
        try:
            request = urllib.request.Request(script_url, headers={"User-Agent": THREADS_USER_AGENT})
            with opener.open(request, timeout=REQUEST_TIMEOUT) as response:
                script = response.read().decode("utf-8", "replace")
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            continue
        match = THREADS_QUERY_DOC_ID_RE.search(script)
        if not match:
            continue
        relay_variables = set(THREADS_RELAY_VARIABLE_RE.findall(script))
        _THREADS_QUERY_METADATA_CACHE = (match.group(1), relay_variables)
        return _THREADS_QUERY_METADATA_CACHE

    return THREADS_GRAPHQL_FALLBACK_DOC_ID, set(THREADS_RELAY_DEFAULT_VARIABLES)


def threads_media_urls(post: dict[str, Any]) -> tuple[list[str], list[str]]:
    images: list[str] = []
    videos: list[str] = []
    media_rows = post.get("carousel_media") if isinstance(post.get("carousel_media"), list) else [post]
    for media in media_rows:
        if not isinstance(media, dict):
            continue
        candidates = (media.get("image_versions2") or {}).get("candidates") or []
        if candidates and isinstance(candidates[0], dict):
            append_unique(images, str(candidates[0].get("url") or ""))
        video_versions = media.get("video_versions") or []
        if video_versions and isinstance(video_versions[0], dict):
            append_unique(videos, str(video_versions[0].get("url") or ""))
    return images, videos


def normalize_threads_graphql_posts(
    source: dict[str, Any],
    payload: dict[str, Any],
    *,
    source_feed_url: str,
) -> list[dict[str, Any]]:
    media_data = (payload.get("data") or {}).get("mediaData") or {}
    edges = media_data.get("edges") if isinstance(media_data, dict) else []
    username = str(source.get("username") or "").strip().strip("@")
    posts: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for edge in edges or []:
        node = edge.get("node") if isinstance(edge, dict) else {}
        for thread_item in (node or {}).get("thread_items") or []:
            post = thread_item.get("post") if isinstance(thread_item, dict) else {}
            if not isinstance(post, dict):
                continue
            post_user = post.get("user") if isinstance(post.get("user"), dict) else {}
            post_username = str(post_user.get("username") or username)
            if username and post_username.casefold() != username.casefold():
                continue
            code = str(post.get("code") or "")
            post_id = str(post.get("pk") or post.get("id") or code)
            if not post_id or post_id in seen_ids:
                continue
            seen_ids.add(post_id)
            caption = post.get("caption")
            text = str(caption.get("text") or "") if isinstance(caption, dict) else str(caption or "")
            images, videos = threads_media_urls(post)
            try:
                posted_at = dt.datetime.fromtimestamp(int(post.get("taken_at")), dt.timezone.utc).isoformat()
            except (TypeError, ValueError, OSError):
                posted_at = ""
            post_url = (
                f"{THREADS_BASE_URL}/@{urllib.parse.quote(post_username)}/post/{urllib.parse.quote(code)}"
                if code
                else source_feed_url
            )
            posts.append(
                normalize_post(
                    source,
                    post_id=post_id,
                    text=text,
                    url=post_url,
                    posted_at=posted_at,
                    images=images,
                    videos=videos,
                    source_avatar_url=str(post_user.get("profile_pic_url") or ""),
                    source_feed_url=source_feed_url,
                )
            )
    limit = max(1, int(source.get("limit") or 5))
    return posts[:limit]


def fetch_threads_graphql(source: dict[str, Any]) -> list[dict[str, Any]]:
    username = str(source.get("username") or "").strip().strip("@")
    if not username:
        return []

    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    profile_url = f"{THREADS_BASE_URL}/@{urllib.parse.quote(username)}"
    profile_request = urllib.request.Request(
        profile_url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "User-Agent": THREADS_USER_AGENT,
        },
    )
    with opener.open(profile_request, timeout=REQUEST_TIMEOUT) as response:
        profile_html = response.read().decode("utf-8", "replace")

    lsd_match = THREADS_LSD_RE.search(profile_html)
    user_id_match = THREADS_PROFILE_USER_ID_RE.search(profile_html)
    if not lsd_match or not user_id_match:
        raise ValueError(f"Threads profile metadata unavailable for @{username}")

    doc_id, relay_variable_names = threads_query_metadata(opener, profile_html)
    variables: dict[str, Any] = {
        "after": None,
        "allow_page_info_for_lox_user": True,
        "before": None,
        "first": max(1, min(int(source.get("limit") or 5), 15)),
        "last": None,
        "userID": user_id_match.group(1),
    }
    for name in relay_variable_names:
        variables[name] = name in THREADS_RELAY_TRUE_VARIABLES
    variables["__relay_internal__pv__BarcelonaHasProfileSelfReplyContextrelayprovider"] = False

    lsd = lsd_match.group(1)
    csrf = next((cookie.value for cookie in cookie_jar if cookie.name == "csrftoken"), "")
    body = urllib.parse.urlencode(
        {
            "lsd": lsd,
            "doc_id": doc_id,
            "fb_api_req_friendly_name": THREADS_GRAPHQL_OPERATION,
            "fb_api_caller_class": "RelayModern",
            "server_timestamps": "true",
            "variables": json.dumps(variables, separators=(",", ":")),
        }
    ).encode("utf-8")
    graphql_request = urllib.request.Request(
        THREADS_GRAPHQL_URL,
        data=body,
        headers={
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": THREADS_BASE_URL,
            "Referer": profile_url,
            "User-Agent": THREADS_USER_AGENT,
            "X-ASBD-ID": THREADS_ASBD_ID,
            "X-CSRFToken": csrf,
            "X-FB-Friendly-Name": THREADS_GRAPHQL_OPERATION,
            "X-FB-LSD": lsd,
            "X-IG-App-ID": THREADS_WEB_APP_ID,
            "X-LOGGED-OUT-THREADS-MIGRATED-REQUEST": "true",
            "X-Root-Field-Name": "xdt_api__v1__text_feed__user_id__profile__connection",
        },
        method="POST",
    )
    with opener.open(graphql_request, timeout=REQUEST_TIMEOUT) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if payload.get("errors"):
        message = compact_text(str(payload["errors"][0].get("message") or "Threads GraphQL failed"), 300)
        raise ValueError(message)
    if (payload.get("data") or {}).get("mediaData") is None:
        raise ValueError(f"Threads timeline unavailable for @{username}")
    return normalize_threads_graphql_posts(source, payload, source_feed_url=profile_url)


def fetch_rss(source: dict[str, Any]) -> list[dict[str, Any]]:
    if is_story_source(source) and str(source.get("provider") or "") == "instaloader":
        return fetch_instaloader_story(source)
    if (
        str(source.get("type") or "") == "rsshub_instagram_profile"
        and str(source.get("provider") or "") == "instaloader"
    ):
        return fetch_instaloader_profile(source)
    url = source.get("url") or rsshub_url(source)
    if not url:
        return []
    req = urllib.request.Request(url, headers={"User-Agent": "HarmonicaInTaiwanSocialWatcher/1.0"})
    story_source = is_story_source(source)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            root = ET.fromstring(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        public_bases = {"https://rss.observe.tw", "http://rss.observe.tw"}
        is_public_rsshub = any(url.startswith(base) for base in public_bases)
        root = None
        if is_public_rsshub:
            local_url = url
            for base in public_bases:
                if local_url.startswith(base):
                    local_url = local_url.replace(base, "http://127.0.0.1:1200", 1)
                    break
            try:
                print(f"Public RSSHub failed for {url}. Trying local fallback {local_url}...", flush=True)
                local_req = urllib.request.Request(local_url, headers={"User-Agent": "HarmonicaInTaiwanSocialWatcher/1.0"})
                with urllib.request.urlopen(local_req, timeout=min(10, REQUEST_TIMEOUT)) as response:
                    root = ET.fromstring(response.read())
                url = local_url
            except Exception:
                pass
        
        if root is None:
            message = ""
            if isinstance(exc, urllib.error.HTTPError):
                message = rsshub_error_message(exc.read())
                if story_source and exc.code in {404, 503} and is_story_empty_error(message):
                    posts = fetch_instagram_web_story(source, source_feed_url=url)
                    if posts:
                        return posts
                    return []
            if str(source.get("platform") or "").casefold() == "instagram" and not story_source:
                fallback_posts = fetch_instagram_public_backfill(source, source_feed_url=url)
                if fallback_posts:
                    return fallback_posts
            if str(source.get("platform") or "").casefold() == "threads":
                try:
                    return fetch_threads_graphql(source)
                except (
                    urllib.error.HTTPError,
                    urllib.error.URLError,
                    TimeoutError,
                    OSError,
                    ValueError,
                    json.JSONDecodeError,
                ):
                    pass
            if message:
                raise ValueError(f"RSSHub HTTP {exc.code}: {message}") from exc
            raise

    posts: list[dict[str, Any]] = []
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat()
    channel_avatar = root.findtext("channel/image/url") or ""
    for item in root.findall(".//item"):
        title = text_of(item, "title")
        link = text_of(item, "link")
        desc = text_of(item, "description")
        xml_images, xml_videos = xml_media_urls(item)
        images = merge_media_urls(image_urls(desc), xml_images)
        videos = merge_media_urls(video_urls(desc), xml_videos)
        images, videos = enrich_instagram_profile_media(source, link, images, videos)
        published = text_of(item, "pubDate") or (fetched_at if story_source else "")
        guid = text_of(item, "guid") or link or title
        post_id = guid or (images + videos + [fetched_at])[0]
        posts.append(
            normalize_post(
                source,
                post_id=post_id,
                text="\n".join(part for part in [title, strip_html(desc)] if part),
                url=link,
                posted_at=published,
                images=images,
                videos=videos,
                source_avatar_url=channel_avatar,
                source_feed_url=url,
                rsshub_guid=guid,
                rsshub_title=title,
                story_fetched_at=fetched_at if story_source else "",
            )
        )

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    atom_avatar = atom_text(root, "logo") or atom_text(root, "icon")
    for entry in root.findall(".//atom:entry", ns):
        title = atom_text(entry, "title")
        content = atom_text(entry, "content") or atom_text(entry, "summary")
        xml_images, xml_videos = xml_media_urls(entry)
        images = merge_media_urls(image_urls(content), xml_images)
        videos = merge_media_urls(video_urls(content), xml_videos)
        posted_at = atom_text(entry, "updated") or atom_text(entry, "published") or (fetched_at if story_source else "")
        link = ""
        for link_el in entry.findall("atom:link", ns):
            if link_el.attrib.get("href"):
                link = link_el.attrib["href"]
                break
        images, videos = enrich_instagram_profile_media(source, link, images, videos)
        post_id = atom_text(entry, "id") or link or title
        if not post_id:
            post_id = (images + videos + [fetched_at])[0]
        posts.append(
            normalize_post(
                source,
                post_id=post_id,
                text="\n".join(part for part in [title, strip_html(content)] if part),
                url=link,
                posted_at=posted_at,
                images=images,
                videos=videos,
                source_avatar_url=atom_avatar,
                source_feed_url=url,
                rsshub_guid=post_id,
                rsshub_title=title,
                story_fetched_at=fetched_at if story_source else "",
            )
        )

    if story_source and not posts:
        fallback_posts = fetch_instagram_web_story(source, source_feed_url=url)
        if fallback_posts:
            return fallback_posts

    return posts


def normalize_external_post(source: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    source_id = str(row.get("source_id") or source["id"])
    source_name = row.get("source_name") or source.get("name") or source_id
    account = row.get("account") or row.get("username") or row.get("page") or source.get("username") or source.get("page") or ""
    url = row.get("url") or row.get("link") or row.get("permalink") or ""
    post_id = row.get("post_id") or row.get("id") or row.get("guid") or url
    text_parts = [
        row.get("text"),
        row.get("caption"),
        row.get("message"),
        row.get("title"),
        row.get("description"),
        row.get("body"),
    ]
    post = normalize_post(
        {
            "id": source_id,
            "name": source_name,
            "platform": row.get("platform") or source.get("platform") or "external",
            "username": account,
        },
        post_id=str(post_id or ""),
        text="\n".join(str(part) for part in text_parts if part),
        url=str(url or ""),
        posted_at=str(row.get("posted_at") or row.get("published_at") or row.get("created_time") or row.get("date") or ""),
        media_type=str(row.get("media_type") or ""),
        images=[
            str(url)
            for url in (
                row.get("images")
                or row.get("image_urls")
                or ([row.get("image_url")] if row.get("image_url") else [])
            )
            if url
        ],
        videos=[str(url) for url in (row.get("videos") or row.get("video_urls") or []) if url],
        source_avatar_url=str(row.get("source_avatar_url") or row.get("avatar_url") or row.get("profile_image_url") or ""),
    )
    for field in (
        "source_display_name",
        "source_profile_url",
        "profile_name",
        "page_name",
        "raw_source",
        "source_feed_url",
        "story_provider",
        "story_fetched_at",
        "story_expires_at",
        "rsshub_guid",
        "rsshub_title",
    ):
        if row.get(field):
            post[field] = row[field]
    if row.get("story"):
        post["story"] = True
    if row.get("ephemeral"):
        post["ephemeral"] = True
    if row.get("raw_source"):
        post["raw_source"] = str(row["raw_source"])
    if row.get("include_without_keywords"):
        post["include_without_keywords"] = True
    return post


def fetch_jsonl(source: dict[str, Any]) -> list[dict[str, Any]]:
    path = project_path(source.get("path") or DEFAULT_INBOX)
    if not path.exists():
        return []
    posts: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_no}: invalid JSONL row: {exc}") from exc
            if isinstance(row, dict):
                posts.append(normalize_external_post(source, row))
    return posts


def fetch_facebook_page(source: dict[str, Any], token: str) -> list[dict[str, Any]]:
    page = source.get("page") or source.get("username")
    if not page:
        return []
    if str(page).startswith(("http://", "https://")):
        return []
    limit = int(source.get("limit") or 5)
    path = urllib.parse.quote(str(page), safe="")
    data = http_json(
        f"{GRAPH_BASE}/{path}/published_posts",
        {
            "limit": min(max(limit, 1), 25),
            "fields": "id,message,created_time,permalink_url,attachments{title,description,url}",
        },
        token,
    )
    posts: list[dict[str, Any]] = []
    for item in data.get("data", []):
        attachment_text = ""
        attachments = item.get("attachments", {}).get("data", [])
        if attachments:
            attachment_text = "\n".join(
                part
                for attachment in attachments
                for part in [attachment.get("title") or "", attachment.get("description") or ""]
                if part
            )
        posts.append(
            normalize_post(
                source,
                post_id=item.get("id") or item.get("permalink_url") or "",
                text="\n".join(part for part in [item.get("message") or "", attachment_text] if part),
                url=item.get("permalink_url") or "",
                posted_at=item.get("created_time") or "",
            )
        )
    return posts


HARMONICA_TERMS = ("口琴", "harmonica", "ハーモニカ", "하모니카", "harmonika", "armónica")
HREF_RE = re.compile(r"""href\s*=\s*["']([^"'#]+)""", re.IGNORECASE)
PROGRAM_PAGE_LIMIT = 80


def read_webpage(url: str) -> tuple[str, str, bytes]:
    """Return (final URL, lowercased content type, body) for one public page."""
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "text/html,application/xhtml+xml,application/pdf,image/*,*/*;q=0.8",
            "User-Agent": "Mozilla/5.0 HarmonicaInTaiwanWebpageWatcher/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        body = response.read(5_000_000)
        content_type = str(response.headers.get("Content-Type") or "").casefold()
        return response.geturl() or url, content_type, body


def is_html(content_type: str, body: bytes) -> bool:
    return "html" in content_type or body.lstrip().lower().startswith((b"<!doctype", b"<html"))


def decode_markup(content_type: str, body: bytes) -> str:
    charset_match = re.search(r"charset=([\w.-]+)", content_type)
    try:
        return body.decode(charset_match.group(1) if charset_match else "utf-8", "replace")
    except LookupError:
        return body.decode("utf-8", "replace")


def webpage_text(markup: str) -> tuple[str, str]:
    """Return the page title and its visible text."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", markup, re.IGNORECASE | re.DOTALL)
    title = compact_text(html.unescape(TAG_RE.sub(" ", title_match.group(1))), 300) if title_match else ""
    content = re.sub(r"<(?:script|style|noscript|svg)\b[^>]*>.*?</(?:script|style|noscript|svg)>", " ", markup, flags=re.IGNORECASE | re.DOTALL)
    return title, compact_text(html.unescape(TAG_RE.sub(" ", content)), 20_000)


def fetch_webpage(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Fingerprint an authoritative public page and emit a row when it changes."""
    if source.get("follow_links"):
        return fetch_program_pages(source)
    url = str(source.get("url") or source.get("profile_url") or "").strip()
    if not url:
        return []
    final_url, content_type, body = read_webpage(url)

    title = str(source.get("name") or "官方網站更新")
    summary = title
    fingerprint_payload = body
    if is_html(content_type, body):
        page_title, content = webpage_text(decode_markup(content_type, body))
        title = page_title or title
        summary = compact_text(f"{title}\n{content}", 12_000)
        fingerprint_payload = content.encode("utf-8")
    elif content_type:
        summary = f"{title}（{content_type.split(';', 1)[0]}）"

    digest = hashlib.sha256(fingerprint_payload).hexdigest()
    # A page fingerprint records an observation, not an article publication.
    # Neither HTTP Last-Modified nor the fetch time establishes a publication date.
    posted_at = ""
    return [
        normalize_post(
            source,
            post_id=digest,
            text=summary,
            url=final_url,
            posted_at=posted_at,
            media_type="webpage_update",
        )
    ]


def fetch_program_pages(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Crawl a festival or venue lineup and emit each detail page that mentions harmonica.

    Lineup index pages list performer names only; the instrumentation that makes a
    show relevant usually appears on the linked detail page.
    """
    pattern = re.compile(str(source["follow_links"]))
    index_urls = [str(source.get("url") or ""), *(str(url) for url in source.get("index_urls") or [])]
    links: list[str] = []
    for index_url in filter(None, index_urls):
        final_url, content_type, body = read_webpage(index_url)
        host = urllib.parse.urlparse(final_url).netloc
        for href in HREF_RE.findall(decode_markup(content_type, body)):
            link = urllib.parse.urljoin(final_url, html.unescape(href.strip()))
            if urllib.parse.urlparse(link).netloc == host and pattern.search(link) and link not in links:
                links.append(link)
    posts: list[dict[str, Any]] = []
    for index, link in enumerate(links[: int(source.get("max_pages") or PROGRAM_PAGE_LIMIT)]):
        if index:
            time.sleep(0.5)
        try:
            final_url, content_type, body = read_webpage(link)
        except (urllib.error.URLError, TimeoutError, OSError):
            continue  # one retired detail page must not hide the rest of the lineup
        if not is_html(content_type, body):
            continue
        title, content = webpage_text(decode_markup(content_type, body))
        folded = content.casefold()
        mention = min((folded.find(term) for term in HARMONICA_TERMS if term in folded), default=-1)
        if mention < 0:
            continue
        # normalize_post keeps 1,600 characters: retain the page opening (date,
        # venue, title) and the passage that actually mentions the harmonica.
        excerpt = content if len(content) <= 1_200 else (
            content[:500] + " … " + content[max(500, mention - 300):mention + 400]
        )
        posts.append(
            normalize_post(
                source,
                post_id=hashlib.sha256(f"{final_url}\n{content}".encode("utf-8")).hexdigest(),
                text=f"{title}\n{excerpt}",
                url=final_url,
                posted_at="",
                media_type="program_page",
            )
        )
    return posts


def fetch_source(source: dict[str, Any], token: str | None) -> list[dict[str, Any]]:
    if externally_collected_instagram(source):
        return cached_instagram_posts(source)
    kind = source.get("type")
    if kind in {"rss", "rsshub_facebook_page", "rsshub_instagram_profile", "rsshub_instagram_story", "rsshub_twitter_user", "rsshub_threads_user"}:
        return fetch_rss(source)
    if kind in {"jsonl", "external_jsonl", "n8n_jsonl"}:
        return fetch_jsonl(source)
    if kind == "facebook_page_posts":
        return fetch_facebook_page(source, token) if token else []
    if kind == "webpage_watch":
        return fetch_webpage(source)
    return []


def should_throttle_source(source: dict[str, Any], token: str | None) -> bool:
    if externally_collected_instagram(source):
        return False
    kind = source.get("type")
    if kind in {"rss", "rsshub_facebook_page", "rsshub_instagram_profile", "rsshub_instagram_story", "rsshub_twitter_user", "rsshub_threads_user", "jsonl", "external_jsonl", "n8n_jsonl"}:
        return True
    if kind == "facebook_page_posts" and token:
        return True
    if kind == "webpage_watch":
        return True
    return False


def match_keywords(text: str, keywords: list[str]) -> list[str]:
    haystack = (text or "").lower()
    return [keyword for keyword in keywords if keyword.lower() in haystack]


def env_truthy(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().casefold() in TRUTHY


def unique_limited(values: list[Any], *, allowed: set[str] | None = None, limit: int = 8) -> list[str]:
    items: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item:
            continue
        if allowed is not None and item not in allowed:
            continue
        if item not in items:
            items.append(item)
        if len(items) >= limit:
            break
    return items


def split_tag_values(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw_values: list[Any] = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    tags: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        for tag in TAG_VALUE_SPLIT_RE.split(text):
            tag = tag.strip()
            if tag and tag not in tags:
                tags.append(tag)
            if len(tags) >= limit:
                return tags
    return tags


def normalize_category(value: Any) -> str:
    raw = str(value or "").strip().casefold()
    aliases = {
        "event": "events",
        "events": "events",
        "活動": "events",
        "實體活動": "events",
        "post": "posts-videos",
        "posts": "posts-videos",
        "video": "posts-videos",
        "videos": "posts-videos",
        "posts-videos": "posts-videos",
        "貼文": "posts-videos",
        "影片": "posts-videos",
        "student": "student-clubs",
        "student-clubs": "student-clubs",
        "club": "student-clubs",
        "學生社團": "student-clubs",
        "opportunity": "opportunities",
        "opportunities": "opportunities",
        "補助": "opportunities",
        "比賽": "opportunities",
    }
    return aliases.get(raw, raw)


def normalize_label(value: Any) -> str:
    raw = str(value or "").strip()
    canonical = public_tags.normalize_tag_value(raw)
    if canonical:
        return canonical
    aliases = {
        "活動": "演出",
        "實體活動": "演出",
        "concert": "音樂會",
        "event": "演出",
        "lesson": "課程",
        "workshop": "課程",
        "course": "課程",
        "competition": "比賽",
        "grant": "補助",
        "funding": "補助",
        "video": "影片",
        "student club": "學生社團",
    }
    return aliases.get(raw.casefold(), raw)


def normalize_label_values(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw_values: list[Any] = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    labels: list[str] = []
    for raw in raw_values:
        text = str(raw or "").strip()
        if not text:
            continue
        normalized = normalize_label(text)
        candidates = [normalized] if normalized in LLM_LABELS else [normalize_label(tag) for tag in split_tag_values(text)]
        for label in candidates:
            if label in LLM_LABELS and label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                return labels
    return labels


def normalize_llm_result(value: Any) -> dict[str, Any]:
    data = value if isinstance(value, dict) else {}
    relevant_value = data.get("is_relevant", data.get("relevant", False))
    if isinstance(relevant_value, bool):
        relevant = relevant_value
    else:
        relevant = str(relevant_value or "").strip().casefold() in TRUTHY

    try:
        confidence = float(data.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1 and confidence <= 100:
        confidence = confidence / 100
    confidence = max(0.0, min(confidence, 1.0))

    raw_labels = data.get("labels") or data.get("tags") or []
    labels = unique_limited(
        normalize_label_values(raw_labels),
        allowed=LLM_LABELS,
        limit=8,
    )

    raw_categories = data.get("categories") or data.get("category_ids") or []
    if isinstance(raw_categories, str):
        raw_categories = re.split(r"[,，、\s]+", raw_categories)
    categories = unique_limited(
        [normalize_category(category) for category in raw_categories if str(category or "").strip()],
        allowed=LLM_CATEGORIES,
        limit=4,
    )
    if relevant and not categories:
        categories = ["posts-videos"]
    if not relevant:
        categories = []
        labels = []

    reason = compact_text(str(data.get("reason") or data.get("summary") or ""), 160)
    return {
        "llm_relevant": relevant,
        "llm_confidence": round(confidence, 3),
        "llm_labels": labels,
        "llm_categories": categories,
        "llm_reason": reason,
    }


def merge_tags(primary: list[Any], fallback: list[Any], *, limit: int = 8) -> list[str]:
    return unique_limited(split_tag_values([*primary, *fallback], limit=limit), limit=limit)


def read_llm_token(service: str, account: str) -> tuple[str, str]:
    import llm_backend
    if llm_backend.provider() == "disabled":
        return "", "disabled"
    if llm_backend.provider() == "codex":
        return "codex-cli-session", "codex-cli"
    for key in ("HARMONICA_LLM_API_KEY", "HARMONICA_OPENAI_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(key)
        if value:
            return value.strip(), f"env:{key}"

    candidates = [
        (service, account),
        (service, DEFAULT_LLM_KEYCHAIN_ACCOUNT),
        (DEFAULT_LLM_KEYCHAIN_SERVICE, DEFAULT_LLM_KEYCHAIN_ACCOUNT),
    ]
    seen_pairs: set[tuple[str, str]] = set()
    for keychain_service, keychain_account in candidates:
        if not keychain_service or not keychain_account or (keychain_service, keychain_account) in seen_pairs:
            continue
        seen_pairs.add((keychain_service, keychain_account))
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", keychain_service, "-a", keychain_account, "-w"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), f"keychain:{keychain_service}/{keychain_account}"
    return "", ""


def llm_endpoint(base_url: str) -> str:
    base = (base_url or OPENAI_BASE_URL).rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


class RequestDeadline:
    def __init__(self, seconds: int) -> None:
        self.seconds = max(1, int(seconds or 1))
        self.previous_handler: Any = None

    def __enter__(self) -> None:
        if not hasattr(signal, "SIGALRM"):
            return
        self.previous_handler = signal.getsignal(signal.SIGALRM)
        signal.signal(signal.SIGALRM, self.raise_timeout)
        signal.setitimer(signal.ITIMER_REAL, self.seconds)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if not hasattr(signal, "SIGALRM"):
            return
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, self.previous_handler)

    def raise_timeout(self, signum: int, frame: Any) -> None:
        raise TimeoutError(f"LLM request timed out after {self.seconds}s")


def post_fingerprint(post: dict[str, Any]) -> str:
    payload = {
        "key": post.get("key") or "",
        "source_id": post.get("source_id") or "",
        "source_name": post.get("source_name") or "",
        "posted_at": post.get("posted_at") or "",
        "url": post.get("url") or "",
        "text": post.get("text") or "",
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def extract_json_object(text: str) -> dict[str, Any]:
    body = (text or "").strip()
    if body.startswith("```"):
        body = re.sub(r"^```(?:json)?\s*", "", body, flags=re.IGNORECASE)
        body = re.sub(r"\s*```$", "", body).strip()
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(body[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM response was not a JSON object")
    return parsed


def chat_response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices") or []
    if not choices:
        raise ValueError("LLM response did not include choices")
    message = choices[0].get("message") or {}
    content = message.get("content") or choices[0].get("text") or ""
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
            else:
                parts.append(str(part))
        return "\n".join(part for part in parts if part).strip()
    return str(content).strip()


def curl_json(url: str, token: str, body: dict[str, Any], timeout: int) -> str:
    import llm_backend
    selected_provider = llm_backend.provider()
    if selected_provider == "disabled":
        raise RuntimeError("LLM inference is disabled")
    if selected_provider == "codex":
        return llm_backend.codex_chat(body, timeout)
    if token == "codex-cli-session":
        raise RuntimeError("Explicit OpenAI API mode requires an API key")
    body = llm_backend.compatible_chat_body(body)
    body_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            json.dump(body, handle, ensure_ascii=False)
            body_path = handle.name

        config = "\n".join(
            [
                f'url = "{url}"',
                'request = "POST"',
                f"max-time = {max(1, int(timeout or 1))}",
                "silent",
                "show-error",
                "fail-with-body",
                f'header = "Authorization: Bearer {token}"',
                'header = "Content-Type: application/json"',
                'header = "Accept: application/json"',
                'header = "User-Agent: HarmonicaObserveLLMTagger/1.0"',
                f'data-binary = "@{body_path}"',
                "",
            ]
        )
        result = subprocess.run(
            ["curl", "--config", "-"],
            input=config,
            capture_output=True,
            text=True,
            timeout=max(2, int(timeout or 1) + 5),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"LLM curl timed out after {timeout}s") from exc
    finally:
        if body_path:
            try:
                Path(body_path).unlink()
            except OSError:
                pass

    if result.returncode != 0:
        detail = (result.stdout or result.stderr or "").strip()[:500]
        raise RuntimeError(f"LLM curl exited {result.returncode}: {detail}")
    return result.stdout


def llm_prompt(post: dict[str, Any], keyword_matches: list[str]) -> list[dict[str, str]]:
    source = post.get("source_name") or post.get("source_id") or "公開來源"
    user_payload = {
        "source": source,
        "source_id": post.get("source_id") or "",
        "platform": post.get("platform") or "",
        "account": post.get("account") or "",
        "posted_at": post.get("posted_at") or "",
        "url": post.get("url") or "",
        "keyword_matches": keyword_matches,
        "text": compact_text(str(post.get("text") or ""), 1800),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是全球口琴觀測站的多語社群貼文分類器。"
                "只根據公開貼文文字、來源與 URL 判斷。只回傳 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "判斷這篇公開貼文是否值得收進全球口琴公開更新。不論國家或語言，相關的公開口琴資訊都可收錄。"
                "只要是口琴演出、音樂會、成發、課程、招生、社博、迎新、交流、"
                "比賽、報名、甄選、補助、指定曲、口琴影片、限時動態、口琴社團或口琴演奏者公開更新，就算相關。"
                "如果只是一般音樂、班多鈕/手風琴、一般藝文活動，或來源名稱含 harmonica 但貼文內容無關，請標成不相關。"
                "categories 只能使用 events, posts-videos, student-clubs, opportunities；"
                "相關但無更精準分類時用 posts-videos。labels 只能使用："
                + ", ".join(public_tags.PUBLIC_TAGS)
                + "。"
                "回傳格式："
                '{"is_relevant":true,"confidence":0.0,"labels":[],"categories":[],"reason":"80字內理由"}'
                "\n\n貼文資料：\n"
                + json.dumps(user_payload, ensure_ascii=False, indent=2)
            ),
        },
    ]


def classify_with_llm(
    post: dict[str, Any],
    keyword_matches: list[str],
    *,
    token: str,
    base_url: str,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": llm_prompt(post, keyword_matches),
        "temperature": 0,
        "max_completion_tokens": 500,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response_body = curl_json(llm_endpoint(base_url), token, body, timeout)
    try:
        response_json = json.loads(response_body)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response was not JSON: {response_body[:300]!r}") from exc
    response_text = chat_response_text(response_json)
    try:
        parsed = extract_json_object(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM message content was not JSON: {response_text[:300]!r}") from exc
    normalized = normalize_llm_result(parsed)
    return {
        **normalized,
        "llm_model": llm_backend.resolved_model(response_json, model),
        "llm_provider": llm_backend.provider(),
        "llm_tagged_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def cached_llm_classification(
    post: dict[str, Any],
    keyword_matches: list[str],
    *,
    cache: dict[str, Any],
    token: str,
    base_url: str,
    model: str,
    timeout: int,
    stats: dict[str, Any],
) -> dict[str, Any] | None:
    items = cache.setdefault("items", {})
    if not isinstance(items, dict):
        items = {}
        cache["items"] = items
    cache_key = post_fingerprint(post)
    cached = items.get(cache_key)
    if isinstance(cached, dict):
        stats["cached"] = int(stats.get("cached") or 0) + 1
        return cached

    stats["requests"] = int(stats.get("requests") or 0) + 1
    attempts, models = llm_backend.retry_policy(model)
    last_error: Exception | None = None
    result: dict[str, Any] | None = None
    for candidate_model in models:
        for attempt in range(attempts):
            try:
                result = classify_with_llm(
                    post,
                    keyword_matches,
                    token=token,
                    base_url=base_url,
                    model=candidate_model,
                    timeout=timeout,
                )
                if candidate_model != model:
                    stats["fallback_uses"] = int(stats.get("fallback_uses") or 0) + 1
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                last_error = exc
                stats["retry_errors"] = int(stats.get("retry_errors") or 0) + 1
                if attempt + 1 < attempts:
                    time.sleep(min(2.0, 0.5 * (attempt + 1)))
        if result is not None:
            break
    if result is None:
        raise RuntimeError(f"LLM classification failed: {last_error}")
    items[cache_key] = result
    stats["cache_changed"] = True
    return result


def parse_post_time(value: str) -> dt.datetime | None:
    if not value:
        return None
    raw = value.strip()
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


def too_old(posted_at: str, max_age_days: int | None, now: dt.datetime) -> bool:
    if not max_age_days:
        return False
    posted = parse_post_time(posted_at)
    if posted is None:
        return False
    return posted < now - dt.timedelta(days=max_age_days)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def append_candidates(path: Path, posts: list[dict[str, Any]]) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    append_jsonl(path, [{**post, "seen_at": now} for post in posts])


def append_errors(path: Path, errors: list[dict[str, str]]) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    append_jsonl(path, [{**error, "seen_at": now} for error in errors])


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--seen", type=Path, default=DEFAULT_SEEN)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--errors", type=Path, default=DEFAULT_ERRORS)
    parser.add_argument("--fetch-state", type=Path, default=DEFAULT_FETCH_STATE)
    parser.add_argument("--progress", type=Path, default=DEFAULT_PROGRESS)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--baseline", action="store_true")
    parser.add_argument("--emit-initial", action="store_true")
    parser.add_argument("--include-all-new", action="store_true")
    parser.add_argument("--max-post-age-days", type=int, default=0)
    parser.add_argument(
        "--instagram-profile-interval-hours",
        type=float,
        default=env_float(
            "HARMONICA_IG_PROFILE_INTERVAL_HOURS",
            DEFAULT_INSTAGRAM_PROFILE_INTERVAL_HOURS,
            minimum=0.0,
        ),
    )
    parser.add_argument(
        "--instagram-story-interval-hours",
        type=float,
        default=env_float(
            "HARMONICA_IG_STORY_INTERVAL_HOURS",
            DEFAULT_INSTAGRAM_STORY_INTERVAL_HOURS,
            minimum=0.0,
        ),
    )
    parser.add_argument(
        "--instagram-delay-secs",
        type=float,
        default=env_float("HARMONICA_IG_DELAY_SECS", DEFAULT_INSTAGRAM_DELAY_SECS, minimum=0.0),
    )
    parser.add_argument(
        "--instagram-bootstrap-cooldown-hours",
        type=float,
        default=env_float(
            "HARMONICA_IG_BOOTSTRAP_COOLDOWN_HOURS",
            DEFAULT_INSTAGRAM_BOOTSTRAP_COOLDOWN_HOURS,
            minimum=0.0,
        ),
    )
    parser.add_argument(
        "--instagram-max-attempts-per-run",
        type=int,
        default=env_int(
            "HARMONICA_IG_MAX_ATTEMPTS_PER_RUN",
            DEFAULT_INSTAGRAM_MAX_ATTEMPTS_PER_RUN,
            minimum=0,
        ),
        help="Maximum due Instagram sources to fetch in one run; 0 disables the cap.",
    )
    parser.add_argument("--instagram-force", action="store_true")
    parser.add_argument("--llm-tags", dest="llm_tags", action="store_true", default=env_truthy("HARMONICA_ENABLE_LLM_TAGS", True))
    parser.add_argument("--no-llm-tags", dest="llm_tags", action="store_false")
    parser.add_argument("--llm-cache", type=Path, default=DEFAULT_LLM_CACHE)
    parser.add_argument("--llm-base-url", default=os.environ.get("HARMONICA_LLM_BASE_URL", OPENAI_BASE_URL))
    parser.add_argument("--llm-model", default=__import__("llm_backend").model_name())
    parser.add_argument("--llm-timeout", type=int, default=int(os.environ.get("HARMONICA_LLM_TIMEOUT", "45")))
    parser.add_argument(
        "--llm-confidence-threshold",
        type=float,
        default=float(os.environ.get("HARMONICA_LLM_CONFIDENCE_THRESHOLD", "0.55")),
    )
    parser.add_argument(
        "--llm-keychain-service",
        default=os.environ.get("HARMONICA_LLM_KEYCHAIN_SERVICE", DEFAULT_LLM_KEYCHAIN_SERVICE),
    )
    parser.add_argument(
        "--llm-keychain-account",
        default=os.environ.get("HARMONICA_LLM_KEYCHAIN_ACCOUNT", DEFAULT_LLM_KEYCHAIN_ACCOUNT),
    )
    parser.add_argument("--rsshub-base", default=os.environ.get("HARMONICA_RSSHUB_BASE", ""))
    parser.add_argument("--request-timeout", type=int, default=10)
    parser.add_argument(
        "--source-type",
        action="append",
        default=[],
        help="Only process the selected source type; may be repeated.",
    )
    parser.add_argument(
        "--source-id",
        action="append",
        default=[],
        help="Only process the selected source id; may be repeated.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    global RSSHUB_BASE, REQUEST_TIMEOUT
    RSSHUB_BASE = args.rsshub_base.rstrip("/") if args.rsshub_base else RSSHUB_BASE
    REQUEST_TIMEOUT = args.request_timeout

    config = load_json(args.config, {"sources": [], "keywords": []})
    sources = [source for source in config.get("sources", []) if source.get("enabled", True)]
    if args.source_type:
        selected_types = {str(value).strip() for value in args.source_type if str(value).strip()}
        sources = [source for source in sources if str(source.get("type") or "") in selected_types]
    if args.source_id:
        selected_ids = {str(value).strip() for value in args.source_id if str(value).strip()}
        sources = [source for source in sources if str(source.get("id") or "") in selected_ids]
    keywords = config.get("keywords") or []
    token = os.environ.get("HARMONICA_META_ACCESS_TOKEN")
    progress_path = args.progress if args.progress.is_absolute() else PROJECT_ROOT / args.progress

    if args.check:
        by_type: dict[str, int] = {}
        for source in sources:
            by_type[str(source.get("type") or "unknown")] = by_type.get(str(source.get("type") or "unknown"), 0) + 1
        print(
            json.dumps(
                {
                    "config": str(args.config),
                    "sources_enabled": len(sources),
                    "source_types": by_type,
                    "rsshub_sources": sum(1 for source in sources if str(source.get("type") or "").startswith("rsshub_")),
                    "jsonl_sources": sum(1 for source in sources if source.get("type") in {"jsonl", "external_jsonl", "n8n_jsonl"}),
                    "facebook_sources": sum(1 for source in sources if source.get("type") == "facebook_page_posts"),
                    "has_meta_token": bool(token),
                    "llm_tags_requested": bool(args.llm_tags),
                    "llm_base_url": llm_backend.runtime_metadata(args.llm_model, args.llm_base_url)["base_url"],
                    "llm_model": llm_backend.runtime_metadata(args.llm_model, args.llm_base_url)["model"],
                    "llm_provider": llm_backend.provider(),
                    "llm_cache": str(args.llm_cache),
                    "llm_keychain_service": args.llm_keychain_service,
                    "llm_keychain_account": args.llm_keychain_account,
                    "has_llm_env_token": any(
                        bool(os.environ.get(key))
                        for key in ("HARMONICA_LLM_API_KEY", "HARMONICA_OPENAI_API_KEY", "OPENAI_API_KEY")
                    ),
                    "instagram_profile_interval_hours": args.instagram_profile_interval_hours,
                    "instagram_story_interval_hours": args.instagram_story_interval_hours,
                    "instagram_delay_secs": args.instagram_delay_secs,
                    "instagram_bootstrap_cooldown_hours": args.instagram_bootstrap_cooldown_hours,
                    "instagram_max_attempts_per_run": args.instagram_max_attempts_per_run,
                    "instagram_force": bool(args.instagram_force),
                    "fetch_state_file": str(args.fetch_state),
                    "progress_file": str(args.progress),
                    "default_inbox": str(DEFAULT_INBOX),
                    "seen_file": str(args.seen),
                    "candidates_file": str(args.candidates),
                    "errors_file": str(args.errors),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    first_run = not args.seen.exists()
    seen = load_json(args.seen, {"seen": {}, "initialized_at": None})
    seen_map: dict[str, str] = dict(seen.get("seen") or {})
    fetch_state = normalize_fetch_state(load_json(args.fetch_state, {"version": 1, "sources": {}}))
    fetch_state_changed = False
    new_posts: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    fetched_count = 0
    skipped_old = 0
    now_utc = dt.datetime.now(dt.timezone.utc)
    run_started_at = now_utc
    bootstrap_anchor = instagram_bootstrap_anchor(fetch_state, seen, sources, args)
    schedule_stats: dict[str, Any] = {
        "profile_interval_hours": float(args.instagram_profile_interval_hours),
        "story_interval_hours": float(args.instagram_story_interval_hours),
        "delay_secs": float(args.instagram_delay_secs),
        "max_attempts_per_run": int(args.instagram_max_attempts_per_run),
        "attempted": 0,
        "skipped": 0,
        "scheduled": 0,
        "deferred": 0,
        "errors": 0,
        "profile_attempted": 0,
        "profile_skipped": 0,
        "profile_deferred": 0,
        "story_attempted": 0,
        "story_skipped": 0,
        "story_deferred": 0,
    }
    if bootstrap_anchor is not None:
        observed_at = parse_datetime(seen.get("updated_at") or seen.get("initialized_at")) or now_utc
        fetch_state["bootstrapped_from_social_seen_at"] = utc_iso(observed_at)
        fetch_state["bootstrap_anchor_at"] = utc_iso(bootstrap_anchor)
        fetch_state_changed = True
    llm_token, llm_token_source = read_llm_token(args.llm_keychain_service, args.llm_keychain_account) if args.llm_tags else ("", "")
    llm_should_tag = bool(args.llm_tags and llm_token and not args.baseline and (not first_run or args.emit_initial))
    llm_cache = load_json(args.llm_cache, {"version": 1, "items": {}}) if llm_should_tag else {"version": 1, "items": {}}
    llm_stats: dict[str, Any] = {
        "requested": bool(args.llm_tags),
        "enabled": llm_should_tag,
        **llm_backend.runtime_metadata(args.llm_model, args.llm_base_url),
        "token_source": llm_token_source,
        "cached": 0,
        "requests": 0,
        "errors": 0,
        "cache_changed": False,
    }
    if args.llm_tags and not llm_token:
        llm_stats["disabled_reason"] = "provider_disabled" if llm_backend.provider() == "disabled" else "missing_api_key"
    elif args.llm_tags and args.baseline:
        llm_stats["disabled_reason"] = "baseline"
    elif args.llm_tags and first_run and not args.emit_initial:
        llm_stats["disabled_reason"] = "initial_baseline_without_emit_initial"

    def publish_progress(
        *,
        status: str = "running",
        phase: str = "",
        processed_sources: int = 0,
        current_source: dict[str, Any] | None = None,
        message: str = "",
    ) -> None:
        save_json(
            progress_path,
            {
                "version": 1,
                "status": status,
                "pid": os.getpid(),
                "startedAt": utc_iso(run_started_at),
                "heartbeatAt": utc_iso(dt.datetime.now(dt.timezone.utc)),
                "finishedAt": utc_iso(dt.datetime.now(dt.timezone.utc)) if status in {"ok", "failed"} else "",
                "phase": phase,
                "message": message,
                "processedSources": processed_sources,
                "totalSources": len(sources),
                "currentSource": current_source or {},
                "fetchedPosts": fetched_count,
                "newRelevantPosts": len(new_posts),
                "skippedOldPosts": skipped_old,
                "errors": len(errors),
                "instagram": schedule_stats,
                "llmTags": {
                    "enabled": bool(llm_stats.get("enabled")),
                    "requests": int(llm_stats.get("requests") or 0),
                    "errors": int(llm_stats.get("errors") or 0),
                    "cached": int(llm_stats.get("cached") or 0),
                },
            },
        )

    publish_progress(phase="starting", processed_sources=0)

    for source_index, source in enumerate(sources, start=1):
        publish_progress(
            phase="source",
            processed_sources=source_index - 1,
            current_source=progress_source_summary(source),
        )
        webpage_watch = str(source.get("type") or "") == "webpage_watch"
        webpage_initial_baseline = False
        if webpage_watch:
            due, skip_reason, schedule_changed, webpage_initial_baseline = webpage_due_info(
                source,
                fetch_state,
                now=now_utc,
                force=bool(args.baseline),
            )
            fetch_state_changed = fetch_state_changed or schedule_changed
            if not due:
                publish_progress(
                    phase="source skipped",
                    processed_sources=source_index,
                    current_source=progress_source_summary(source),
                    message=skip_reason,
                )
                continue
        # The independent collector owns attempts, cooldowns and health. Reading
        # its cache must not record a new successful network fetch.
        instagram_kind = "" if externally_collected_instagram(source) else instagram_source_kind(source)
        if instagram_kind:
            due, skip_reason, schedule_changed = instagram_due_info(
                source,
                fetch_state,
                now=now_utc,
                args=args,
                bootstrap_anchor=bootstrap_anchor,
            )
            fetch_state_changed = fetch_state_changed or schedule_changed
            if not due:
                schedule_stats["skipped"] += 1
                schedule_stats["scheduled"] += 1
                schedule_stats[f"{instagram_kind}_skipped"] = int(schedule_stats.get(f"{instagram_kind}_skipped") or 0) + 1
                record_instagram_skip(fetch_state, source, now=now_utc, reason=skip_reason)
                fetch_state_changed = True
                publish_progress(
                    phase="source skipped",
                    processed_sources=source_index,
                    current_source=progress_source_summary(source),
                    message=skip_reason,
                )
                continue
            if is_instaloader_source(source):
                auth_skip_reason = instaloader_auth_block_reason(fetch_state, now=now_utc)
                if auth_skip_reason:
                    schedule_stats["skipped"] += 1
                    schedule_stats["deferred"] += 1
                    schedule_stats[f"{instagram_kind}_skipped"] = int(schedule_stats.get(f"{instagram_kind}_skipped") or 0) + 1
                    schedule_stats[f"{instagram_kind}_deferred"] = int(schedule_stats.get(f"{instagram_kind}_deferred") or 0) + 1
                    record_instagram_skip(fetch_state, source, now=now_utc, reason=auth_skip_reason)
                    fetch_state_changed = True
                    publish_progress(
                        phase="source deferred",
                        processed_sources=source_index,
                        current_source=progress_source_summary(source),
                        message=auth_skip_reason,
                    )
                    continue
            max_instagram_attempts = max(0, int(args.instagram_max_attempts_per_run))
            if max_instagram_attempts and int(schedule_stats["attempted"]) >= max_instagram_attempts:
                skip_reason = f"run attempt limit reached ({max_instagram_attempts})"
                schedule_stats["skipped"] += 1
                schedule_stats["deferred"] += 1
                schedule_stats[f"{instagram_kind}_skipped"] = int(schedule_stats.get(f"{instagram_kind}_skipped") or 0) + 1
                schedule_stats[f"{instagram_kind}_deferred"] = int(schedule_stats.get(f"{instagram_kind}_deferred") or 0) + 1
                record_instagram_skip(fetch_state, source, now=now_utc, reason=skip_reason)
                fetch_state_changed = True
                publish_progress(
                    phase="source deferred",
                    processed_sources=source_index,
                    current_source=progress_source_summary(source),
                    message=skip_reason,
                )
                continue
            schedule_stats["attempted"] += 1
            schedule_stats[f"{instagram_kind}_attempted"] = int(schedule_stats.get(f"{instagram_kind}_attempted") or 0) + 1
        try:
            posts = fetch_source(source, token)
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            ET.ParseError,
            json.JSONDecodeError,
            ValueError,
            TimeoutError,
            socket.timeout,
        ) as exc:
            error_text = str(exc)
            errors.append(
                {
                    "source_id": str(source.get("id") or ""),
                    "source_type": str(source.get("type") or ""),
                    "error": error_text,
                }
            )
            if instagram_kind:
                schedule_stats["errors"] += 1
                if is_instaloader_source(source) and is_instaloader_auth_error(error_text):
                    set_instaloader_auth_block(
                        fetch_state,
                        now=dt.datetime.now(dt.timezone.utc),
                        cooldown_hours=float(args.instagram_bootstrap_cooldown_hours),
                        error=error_text,
                    )
                record_instagram_attempt(
                    fetch_state,
                    source,
                    now=dt.datetime.now(dt.timezone.utc),
                    args=args,
                    status="error",
                    error=error_text,
                )
                fetch_state_changed = True
            if webpage_watch:
                record_webpage_attempt(
                    fetch_state,
                    source,
                    now=dt.datetime.now(dt.timezone.utc),
                    status="error",
                    error=error_text,
                )
                fetch_state_changed = True
            delay_secs = source_delay_secs(source, token, args)
            if delay_secs:
                publish_progress(
                    phase="source sleep",
                    processed_sources=source_index,
                    current_source=progress_source_summary(source),
                    message=f"sleeping {delay_secs:.1f}s after error",
                )
                time.sleep(delay_secs)
            publish_progress(
                phase="source error",
                processed_sources=source_index,
                current_source=progress_source_summary(source),
                message=error_text,
            )
            continue
        if instagram_kind:
            if is_instaloader_source(source):
                clear_instaloader_auth_block(fetch_state)
            record_instagram_attempt(
                fetch_state,
                source,
                now=dt.datetime.now(dt.timezone.utc),
                args=args,
                status="ok",
                post_count=len(posts),
            )
            fetch_state_changed = True
        if webpage_watch:
            record_webpage_attempt(
                fetch_state,
                source,
                now=dt.datetime.now(dt.timezone.utc),
                status="ok",
                post_count=len(posts),
            )
            fetch_state_changed = True
        fetched_count += len(posts)
        for post in posts:
            key = post.get("key")
            if not key or key in seen_map:
                continue
            if webpage_initial_baseline:
                seen_map[key] = dt.datetime.now(dt.timezone.utc).isoformat()
                continue
            matched = match_keywords(post.get("text", ""), keywords)
            post["keyword_matches"] = matched
            post["matched_keywords"] = public_tags.normalize_tag_values(matched)
            if too_old(post.get("posted_at", ""), args.max_post_age_days, now_utc):
                skipped_old += 1
                seen_map[key] = dt.datetime.now(dt.timezone.utc).isoformat()
                continue
            llm_result: dict[str, Any] | None = None
            if llm_should_tag:
                try:
                    llm_result = cached_llm_classification(
                        post,
                        matched,
                        cache=llm_cache,
                        token=llm_token,
                        base_url=args.llm_base_url,
                        model=args.llm_model,
                        timeout=args.llm_timeout,
                        stats=llm_stats,
                    )
                except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
                    llm_stats["errors"] = int(llm_stats.get("errors") or 0) + 1
                    errors.append(
                        {
                            "source_id": str(post.get("source_id") or source.get("id") or ""),
                            "source_type": "llm_tagger",
                            "error": f"{key}: {exc}",
                        }
                    )
                    llm_result = None
                if llm_result:
                    post.update(llm_result)
                    labels = public_tags.normalize_tag_values(list(llm_result.get("llm_labels") or []))
                    post["matched_keywords"] = labels or (["公開更新"] if llm_result.get("llm_relevant") else [])

            if llm_result is not None:
                llm_relevant = bool(post.get("llm_relevant")) and float(post.get("llm_confidence") or 0) >= args.llm_confidence_threshold
                include_post = bool(args.include_all_new or post.get("include_without_keywords") or llm_relevant)
            else:
                include_post = bool(args.include_all_new or matched or post.get("include_without_keywords"))
            if not args.baseline and include_post:
                new_posts.append(post)
            seen_map[key] = dt.datetime.now(dt.timezone.utc).isoformat()
        delay_secs = source_delay_secs(source, token, args)
        if delay_secs:
            publish_progress(
                phase="source sleep",
                processed_sources=source_index,
                current_source=progress_source_summary(source),
                message=f"sleeping {delay_secs:.1f}s",
            )
            time.sleep(delay_secs)
        publish_progress(
            phase="source done",
            processed_sources=source_index,
            current_source=progress_source_summary(source),
        )

    if llm_stats.get("cache_changed"):
        llm_cache["version"] = 1
        llm_cache["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_json(args.llm_cache, llm_cache)

    run_finished_at = dt.datetime.now(dt.timezone.utc)
    fetch_state["updated_at"] = utc_iso(run_finished_at)
    fetch_state["settings"] = {
        "instagram_profile_interval_hours": float(args.instagram_profile_interval_hours),
        "instagram_story_interval_hours": float(args.instagram_story_interval_hours),
        "instagram_delay_secs": float(args.instagram_delay_secs),
        "instagram_bootstrap_cooldown_hours": float(args.instagram_bootstrap_cooldown_hours),
        "instagram_max_attempts_per_run": int(args.instagram_max_attempts_per_run),
    }
    fetch_state["last_run"] = {
        "started_at": utc_iso(run_started_at),
        "finished_at": utc_iso(run_finished_at),
        "instagram": schedule_stats,
    }
    if fetch_state_changed or schedule_stats["attempted"] or schedule_stats["skipped"]:
        save_json(args.fetch_state, fetch_state)

    seen["seen"] = seen_map
    seen.setdefault("initialized_at", utc_iso(run_started_at))
    seen["updated_at"] = utc_iso(run_finished_at)
    seen["last_watchdog_run"] = {
        "started_at": utc_iso(run_started_at),
        "finished_at": utc_iso(run_finished_at),
        "fetched_posts": fetched_count,
        "skipped_old_posts": skipped_old,
        "errors": len(errors),
        "instagram": schedule_stats,
    }
    save_json(args.seen, seen)

    if args.baseline:
        append_errors(args.errors, errors)
        publish_progress(status="ok", phase="baseline complete", processed_sources=len(sources))
        if args.verbose:
            print(
                json.dumps(
                    {
                        "baseline": True,
                        "fetched_posts": fetched_count,
                        "skipped_old_posts": skipped_old,
                        "instagram": schedule_stats,
                        "llm_tags": llm_stats,
                        "errors": errors,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    if first_run and not args.emit_initial:
        append_errors(args.errors, errors)
        publish_progress(status="ok", phase="initial baseline complete", processed_sources=len(sources))
        if args.verbose:
            print(
                json.dumps(
                    {
                        "baseline": True,
                        "fetched_posts": fetched_count,
                        "skipped_old_posts": skipped_old,
                        "instagram": schedule_stats,
                        "llm_tags": llm_stats,
                        "errors": errors,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        return 0

    append_candidates(args.candidates, new_posts)
    append_errors(args.errors, errors)
    publish_progress(status="ok", phase="complete", processed_sources=len(sources))

    if new_posts or args.verbose:
        print(
            json.dumps(
                {
                    "new_relevant_posts": new_posts,
                    "skipped_old_posts": skipped_old,
                    "instagram": schedule_stats,
                    "llm_tags": llm_stats,
                    "errors": errors if args.verbose else [],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
