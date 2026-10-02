#!/usr/bin/env python3
"""Build social watcher sources from the public source CSV files."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import urllib.parse
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
UPDATE_URL_OVERRIDES = PROJECT_ROOT / "data" / "sources" / "source-update-url-overrides.json"
PROGRAM_CRAWLS = PROJECT_ROOT / "data" / "sources" / "source-program-crawls.json"
REVIEWED_PROFILES = PROJECT_ROOT / "data" / "sources" / "source-profile-overrides.json"
DEFAULT_RSSHUB_BASE = "https://rss.observe.tw"
GENERATED_BY = "scripts/build_social_sources.py"
LOCAL_RSSHUB_BASES = {"http://127.0.0.1:1200", "http://localhost:1200"}

SOURCE_FILES = [
    PROJECT_ROOT / "data" / "sources" / "harmonica-source-watchlist-public.csv",
]

DEFAULT_KEYWORDS = [
    "口琴",
    "成發",
    "成果發表",
    "音樂會",
    "演出",
    "校慶",
    "社博",
    "迎新",
    "招生",
    "交流",
    "寒訓",
    "暑訓",
    "影片",
    "新片",
    "首播",
    "上架",
    "發布",
    "發佈",
    "直播",
    "補助",
    "獎助",
    "徵件",
    "徵選",
    "甄選",
    "比賽",
    "競賽",
    "指定曲",
    "報名",
    "截止",
    "全國學生音樂比賽",
    "學生音樂比賽",
    "harmonica",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp.replace(path)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def clean(value: str | None) -> str:
    return (value or "").strip()


def normalize_url(value: str) -> str:
    url = clean(value)
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.IGNORECASE):
        if "." in url or url.startswith("@"):
            url = "https://" + url.lstrip("@")
    return url


def canonical_url(value: str) -> str:
    url = normalize_url(value)
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold().removeprefix("www.")
    decoded_path = urllib.parse.unquote(parsed.path).rstrip("/")
    path = urllib.parse.quote(decoded_path, safe="/@")
    query = ""
    if parsed.query and path.endswith("/profile.php"):
        query = urllib.parse.urlencode(sorted(urllib.parse.parse_qsl(parsed.query)))
    return urllib.parse.urlunparse((parsed.scheme or "https", host, path, "", query, ""))


def canonical_webpage_url(value: str) -> str:
    """Normalize a webpage URL without discarding identity-bearing queries."""
    url = normalize_url(value)
    if not url:
        return ""
    parsed = urllib.parse.urlparse(url)
    # Unlike social profiles, arbitrary official websites can have DNS and TLS
    # configured only for the exact www/non-www hostname.  Preserve it.
    host = parsed.netloc.casefold()
    decoded_path = urllib.parse.unquote(parsed.path).rstrip("/") or "/"
    path = urllib.parse.quote(decoded_path, safe="/@")
    return urllib.parse.urlunparse((parsed.scheme or "https", host, path, "", parsed.query, ""))


def safe_slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if slug:
        return slug[:64]
    return fallback


def url_hash(value: str, size: int = 10) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:size]


def source_name(row: dict[str, str]) -> str:
    return clean(row.get("name")) or clean(row.get("name_en")) or "Public harmonica source"


def parse_facebook_source(row: dict[str, str]) -> dict[str, Any] | None:
    raw_url = normalize_url(clean(row.get("fb_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.casefold().removeprefix("www.")
    if host not in {"facebook.com", "m.facebook.com", "fb.com"}:
        return None

    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        return None

    first = parts[0].strip()
    skip_first = {
        "groups",
        "events",
        "watch",
        "reel",
        "reels",
        "story",
        "stories",
        "photo",
        "photos",
        "permalink.php",
        "sharer.php",
        "login",
    }
    if first in skip_first:
        return None

    page = ""
    if first == "profile.php":
        page = ""
    elif first in {"p", "people", "pages"}:
        page = ""
    else:
        page = first

    canonical = canonical_url(raw_url)
    key_part = page or url_hash(canonical)
    return {
        "enabled": True,
        "id": "fb_" + safe_slug(key_part, url_hash(canonical)),
        "limit": 5,
        "name": source_name(row),
        "page": page,
        "url": canonical,
        "platform": "facebook",
        "type": "facebook_page_posts",
        "generated_by": GENERATED_BY,
    }


def parse_youtube_source(row: dict[str, str]) -> dict[str, Any] | None:
    raw_url = normalize_url(clean(row.get("youtube_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.casefold().removeprefix("www.").removeprefix("m.")
    if host not in {"youtube.com", "youtu.be"}:
        return None

    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        return None
    if parts[0] in {"watch", "shorts", "playlist"}:
        return None

    if parts[0] == "channel" and len(parts) > 1:
        key_part = parts[1]
    elif parts[0].startswith("@"):
        key_part = parts[0].lstrip("@")
    elif parts[0] in {"c", "user"} and len(parts) > 1:
        key_part = parts[1]
    else:
        key_part = parts[0]

    canonical = canonical_url(raw_url)
    profiles = load_json(REVIEWED_PROFILES, {}).get("sources", {})
    reviewed = profiles.get("watchlist-" + clean(row.get("public_id")), {})
    channel_id = str(reviewed.get("youtubeChannelId") or "")
    verified_feed = {}
    if (re.fullmatch(r"UC[A-Za-z0-9_-]{22}", channel_id)
            and canonical_url(str(reviewed.get("youtubeUrl") or "")) == canonical
            and reviewed.get("name") == clean(row.get("name"))):
        verified_feed = {"channel_id": channel_id}
    return {
        **verified_feed,
        "enabled": True,
        "id": "yt_" + safe_slug(key_part, url_hash(canonical)),
        "include_without_keywords": True,
        "limit": 3,
        "name": source_name(row),
        "platform": "youtube",
        "type": "youtube_ytdlp",
        "url": canonical,
        "generated_by": GENERATED_BY,
    }


def instagram_account(row: dict[str, str]) -> tuple[str, str] | None:
    raw_url = normalize_url(clean(row.get("ig_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.casefold().removeprefix("www.")
    if host != "instagram.com":
        return None

    parts = [urllib.parse.unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if not parts or parts[0] in {"p", "reel", "reels", "tv", "stories", "explore"}:
        return None

    username = parts[0].strip("@")
    if not username:
        return None
    canonical = canonical_url(raw_url)
    return username, canonical


def parse_instagram_source(row: dict[str, str]) -> dict[str, Any] | None:
    account = instagram_account(row)
    if not account:
        return None
    username, canonical = account
    return {
        "enabled": True,
        "id": "ig_" + safe_slug(username, url_hash(canonical)),
        "limit": 5,
        "name": source_name(row),
        "platform": "instagram",
        "provider": "instagram_public",
        "source_profile_url": f"https://www.instagram.com/{username}/",
        "type": "rsshub_instagram_profile",
        "username": username,
        "generated_by": GENERATED_BY,
    }


def parse_instagram_story_source(row: dict[str, str]) -> dict[str, Any] | None:
    account = instagram_account(row)
    if not account:
        return None
    username, canonical = account
    return {
        "enabled": True,
        "ephemeral": True,
        "id": "ig_story_" + safe_slug(username, url_hash(canonical)),
        "include_without_keywords": True,
        "limit": 5,
        "media_type": "instagram_story",
        "name": source_name(row),
        "platform": "instagram",
        "provider": "apify_stories",
        "source_profile_url": f"https://www.instagram.com/{username}/",
        "story_provider": "apify_stories",
        "type": "rsshub_instagram_story",
        "username": username,
        "generated_by": GENERATED_BY,
    }


def parse_x_source(row: dict[str, str]) -> dict[str, Any] | None:
    raw_url = normalize_url(clean(row.get("x_url")) or clean(row.get("twitter_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.casefold().removeprefix("www.")
    if host not in {"x.com", "twitter.com"}:
        return None

    parts = [urllib.parse.unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if not parts or parts[0] in {"home", "i", "intent", "search", "share", "hashtag", "explore"}:
        return None

    username = parts[0].strip("@")
    if not username:
        return None
    canonical = canonical_url(f"https://x.com/{username}")
    return {
        "enabled": True,
        "id": "x_" + safe_slug(username, url_hash(canonical)),
        "limit": 5,
        "name": source_name(row),
        "platform": "x",
        "profile_url": f"https://x.com/{username}",
        "route": "/twitter/user/{username}",
        "rsshub_base": DEFAULT_RSSHUB_BASE,
        "type": "rss",
        "username": username,
        "generated_by": GENERATED_BY,
    }


def parse_threads_source(row: dict[str, str]) -> dict[str, Any] | None:
    raw_url = normalize_url(clean(row.get("threads_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    host = parsed.netloc.casefold().removeprefix("www.")
    if host != "threads.net":
        return None

    parts = [urllib.parse.unquote(part).strip() for part in parsed.path.split("/") if part.strip()]
    if not parts:
        return None

    username = parts[0].strip("@")
    if not username:
        return None
    canonical = canonical_url(f"https://www.threads.net/@{username}")
    return {
        "enabled": True,
        "id": "threads_" + safe_slug(username, url_hash(canonical)),
        "limit": 5,
        "name": source_name(row),
        "platform": "threads",
        "profile_url": f"https://www.threads.net/@{username}",
        "route": "/threads/{username}",
        "rsshub_base": DEFAULT_RSSHUB_BASE,
        "type": "rss",
        "username": username,
        "generated_by": GENERATED_BY,
    }


def parse_webpage_source(row: dict[str, str]) -> dict[str, Any] | None:
    """Build a change-detection watcher when an entry has no social feed.

    The public registry intentionally keeps authoritative profile/program pages.
    A webpage watcher fingerprints the published page on a schedule, baselines
    its current contents, and emits a new candidate only after the page changes.
    """
    overrides = load_json(UPDATE_URL_OVERRIDES, {})
    override_url = clean(overrides.get(clean(row.get("public_id")))) if isinstance(overrides, dict) else ""
    raw_url = normalize_url(override_url or clean(row.get("update_url")) or clean(row.get("website_url")))
    if not raw_url:
        return None
    parsed = urllib.parse.urlparse(raw_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    public_id = safe_slug(clean(row.get("public_id")), url_hash(raw_url, 8))
    canonical = canonical_webpage_url(raw_url)
    return {
        "enabled": True,
        "id": f"web_{public_id}",
        "include_without_keywords": True,
        "interval_hours": 12,
        "limit": 1,
        "name": source_name(row),
        "platform": "website",
        "profile_url": canonical,
        "type": "webpage_watch",
        "url": canonical,
        "generated_by": GENERATED_BY,
    }


def parse_program_crawl_source(row: dict[str, str]) -> dict[str, Any] | None:
    """Build a lineup crawler for festivals and venues listed in PROGRAM_CRAWLS.

    Each entry names lineup index pages and a regex for their detail links; only
    detail pages that mention harmonica become candidates.
    """
    crawls = load_json(PROGRAM_CRAWLS, {})
    crawl = crawls.get(clean(row.get("public_id"))) if isinstance(crawls, dict) else None
    if not isinstance(crawl, dict) or not crawl.get("index_urls") or not crawl.get("follow_links"):
        return None
    index_urls = [normalize_url(clean(url)) for url in crawl["index_urls"] if clean(url)]
    public_id = safe_slug(clean(row.get("public_id")), url_hash(index_urls[0], 8))
    return {
        "enabled": True,
        "id": f"web_{public_id}",
        "include_without_keywords": True,
        "interval_hours": float(crawl.get("interval_hours") or 24),
        "limit": int(crawl.get("max_pages") or 80),
        "max_pages": int(crawl.get("max_pages") or 80),
        "name": source_name(row),
        "platform": "website",
        "profile_url": canonical_webpage_url(normalize_url(clean(row.get("website_url"))) or index_urls[0]),
        "type": "webpage_watch",
        "url": index_urls[0],
        "index_urls": index_urls[1:],
        "follow_links": str(crawl["follow_links"]),
        "generated_by": GENERATED_BY,
    }


def source_key(source: dict[str, Any]) -> str:
    platform = str(source.get("platform") or source.get("type") or "").casefold()
    source_type = str(source.get("type") or "").casefold()
    if platform == "facebook" or source.get("type") == "facebook_page_posts":
        page = clean(str(source.get("page") or ""))
        if page and not page.startswith("http"):
            return "facebook:page:" + page.strip("/").casefold()
        return "facebook:url:" + canonical_url(str(source.get("url") or page))
    if platform == "youtube" or source.get("type") == "youtube_ytdlp":
        return "youtube:url:" + canonical_url(str(source.get("url") or ""))
    if source_type == "rsshub_instagram_story":
        return "instagram:story:" + clean(str(source.get("username") or "")).strip("@").casefold()
    if platform == "instagram" or source_type == "rsshub_instagram_profile":
        return "instagram:profile:" + clean(str(source.get("username") or "")).strip("@").casefold()
    if platform in {"x", "twitter"}:
        return "x:username:" + clean(str(source.get("username") or "")).strip("@").casefold()
    if platform == "threads":
        return "threads:username:" + clean(str(source.get("username") or "")).strip("@").casefold()
    if source_type == "webpage_watch":
        # Multiple people or ensembles may deliberately share one official
        # festival/program page.  Keep an entry-specific watcher so each
        # directory row remains independently monitored and attributable.
        return "website:id:" + str(source.get("id") or "")
    return str(source.get("id") or "")


def generated_sources() -> list[dict[str, Any]]:
    generated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in SOURCE_FILES:
        for row in read_csv(path):
            row_sources: list[dict[str, Any]] = []
            for parser in (
                parse_facebook_source,
                parse_instagram_source,
                parse_instagram_story_source,
                parse_youtube_source,
                parse_x_source,
                parse_threads_source,
            ):
                source = parser(row)
                if not source:
                    continue
                row_sources.append(source)
            crawl_source = parse_program_crawl_source(row)
            if crawl_source:
                row_sources.append(crawl_source)
            elif not row_sources:
                webpage_source = parse_webpage_source(row)
                if webpage_source:
                    row_sources.append(webpage_source)
            for source in row_sources:
                key = source_key(source)
                if key in seen:
                    continue
                seen.add(key)
                generated.append(source)
    return generated


def merge_sources(existing: list[dict[str, Any]], generated: list[dict[str, Any]]) -> list[dict[str, Any]]:
    kept = [source for source in existing if source.get("generated_by") != GENERATED_BY]
    seen = {source_key(source) for source in kept if source_key(source)}
    merged = list(kept)
    for source in generated:
        key = source_key(source)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged


def ensure_unique_ids(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for source in sources:
        source_id = str(source.get("id") or "").strip()
        if not source_id:
            source_id = "source_" + url_hash(json.dumps(source, ensure_ascii=False, sort_keys=True), 8)
        if source_id in seen:
            base = source_id
            suffix = url_hash(source_key(source) or json.dumps(source, ensure_ascii=False, sort_keys=True), 8)
            source_id = f"{base}_{suffix}"
            counter = 2
            while source_id in seen:
                source_id = f"{base}_{suffix}_{counter}"
                counter += 1
            source = {**source, "id": source_id}
        seen.add(source_id)
        unique.append(source)
    return unique


def normalize_rsshub_bases(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for source in sources:
        rsshub_base = str(source.get("rsshub_base") or "").rstrip("/")
        if rsshub_base in LOCAL_RSSHUB_BASES:
            source = {**source, "rsshub_base": DEFAULT_RSSHUB_BASE}
        normalized.append(source)
    return normalized


def normalize_instagram_providers(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for source in sources:
        if str(source.get("type") or "") == "rsshub_instagram_profile":
            source = {**source, "provider": "instagram_public"}
            source.pop("rsshub_base", None)
            source.pop("route", None)
        if str(source.get("type") or "") == "rsshub_instagram_story":
            source = {**source, "provider": "apify_stories", "story_provider": "apify_stories"}
            source.pop("rsshub_base", None)
            source.pop("route", None)
        normalized.append(source)
    return normalized


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    config = load_json(args.config, {"keywords": DEFAULT_KEYWORDS, "sources": []})
    generated = generated_sources()
    merged = normalize_instagram_providers(
        normalize_rsshub_bases(ensure_unique_ids(merge_sources(list(config.get("sources") or []), generated)))
    )
    output = {
        "keywords": config.get("keywords") or DEFAULT_KEYWORDS,
        "sources": merged,
    }

    if not args.check:
        save_json(args.config, output)

    print(
        json.dumps(
            {
                "config": str(args.config),
                "written": not args.check,
                "sources_total": len(merged),
                "generated_candidates": len(generated),
                "generated_added": sum(1 for source in merged if source.get("generated_by") == GENERATED_BY),
                "facebook_sources": sum(1 for source in merged if source.get("type") == "facebook_page_posts"),
                "instagram_sources": sum(1 for source in merged if source.get("type") == "rsshub_instagram_profile"),
                "instagram_story_sources": sum(1 for source in merged if source.get("type") == "rsshub_instagram_story"),
                "x_sources": sum(1 for source in merged if source.get("platform") == "x"),
                "threads_sources": sum(1 for source in merged if source.get("platform") == "threads"),
                "youtube_sources": sum(1 for source in merged if source.get("type") == "youtube_ytdlp"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
