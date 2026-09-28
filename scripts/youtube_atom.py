"""Read public YouTube Atom metadata, including videos omitted by /videos.

No video downloads or date inference are performed. Invalid feed identity raises
ValueError; invalid individual entries are omitted. Transport errors propagate so
callers can record a failure and fall back to their existing fetcher.
"""

from __future__ import annotations

import datetime as dt
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Callable


MAX_FEED_BYTES = 2 * 1024 * 1024
NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
CHANNEL_ID = re.compile(r"UC[A-Za-z0-9_-]{22}\Z")
VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
PUBLISHED = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z"
)
THUMBNAIL_HOSTS = {"i.ytimg.com", "img.youtube.com", *(f"i{number}.ytimg.com" for number in range(1, 5))}


def _text(element: ET.Element, path: str) -> str:
    return (element.findtext(path, default="", namespaces=NS) or "").strip()


def _video_url(entry: ET.Element, video_id: str) -> str:
    for link in entry.findall("atom:link", NS):
        if link.get("rel", "alternate") != "alternate":
            continue
        raw = link.get("href", "")
        try:
            url = urllib.parse.urlsplit(raw)
            if url.scheme != "https" or url.netloc not in {"www.youtube.com", "youtube.com"}:
                continue
            if url.fragment:
                continue
            if url.path == "/watch" and urllib.parse.parse_qs(url.query).get("v") == [video_id]:
                return raw
            if url.path == f"/shorts/{video_id}" and not url.query:
                return raw
        except ValueError:
            continue
    return ""


def _thumbnail(entry: ET.Element) -> str:
    for node in entry.findall("media:group/media:thumbnail", NS):
        raw = node.get("url", "")
        try:
            url = urllib.parse.urlsplit(raw)
            if url.scheme == "https" and url.netloc in THUMBNAIL_HOSTS:
                return raw
        except ValueError:
            continue
    return ""


def fetch_entries(
    channel_id: str,
    *,
    timeout: float = 10,
    limit: int = 3,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> list[dict[str, Any]]:
    """Return validated Atom entries in feed order as yt-dlp-compatible metadata.

    ``timestamp`` comes only from each entry's timezone-aware ``published`` field,
    never ``updated`` or the current clock. ``limit`` counts valid unique entries.
    Invalid parameters/feed structure raise ValueError, while an empty valid feed
    returns an empty list. The injected opener uses urlopen's request/timeout API.
    """
    if not isinstance(channel_id, str) or not CHANNEL_ID.fullmatch(channel_id):
        raise ValueError("Invalid YouTube channel ID")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ValueError("limit must be a non-negative integer")
    if not limit:
        return []

    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/atom+xml", "User-Agent": "HarmonicaObservatory/1.0"},
    )
    with opener(request, timeout=timeout) as response:
        final_url = response.geturl() if hasattr(response, "geturl") else url
        if final_url != url:
            raise ValueError("Unexpected YouTube Atom response URL")
        payload = response.read(MAX_FEED_BYTES + 1)
    if len(payload) > MAX_FEED_BYTES:
        raise ValueError("YouTube Atom feed exceeds size limit")
    if b"<!doctype" in payload.lower() or b"<!entity" in payload.lower():
        raise ValueError("YouTube Atom feed must not declare XML entities")
    try:
        feed = ET.fromstring(payload)
    except ET.ParseError as exc:
        raise ValueError("Malformed YouTube Atom feed") from exc
    feed_channel_id = _text(feed, "yt:channelId")
    # YouTube also emits the 22-character channel suffix at feed level. Verify
    # its full author URI as well; entry-level channel IDs always remain full.
    matching_channel = feed_channel_id == channel_id or (
        feed_channel_id == channel_id[2:]
        and _text(feed, "atom:author/atom:uri") == f"https://www.youtube.com/channel/{channel_id}"
    )
    if feed.tag != f"{{{NS['atom']}}}feed" or not matching_channel:
        raise ValueError("YouTube Atom feed channel does not match requested channel")

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    channel_name = _text(feed, "atom:author/atom:name")
    for entry in feed.findall("atom:entry", NS):
        video_id = _text(entry, "yt:videoId")
        published = _text(entry, "atom:published")
        title = _text(entry, "atom:title")
        if (
            not VIDEO_ID.fullmatch(video_id)
            or video_id in seen
            or _text(entry, "yt:channelId") != channel_id
            or not title
            or not PUBLISHED.fullmatch(published)
        ):
            continue
        atom_id = _text(entry, "atom:id")
        if atom_id and atom_id != f"yt:video:{video_id}":
            continue
        webpage_url = _video_url(entry, video_id)
        if not webpage_url:
            continue
        try:
            timestamp = dt.datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
        except (ValueError, OverflowError, OSError):
            continue
        rows.append(
            {
                "id": video_id,
                "title": title,
                "description": _text(entry, "media:group/media:description"),
                "timestamp": timestamp,
                "webpage_url": webpage_url,
                "thumbnail": _thumbnail(entry),
                "channel": _text(entry, "atom:author/atom:name") or channel_name,
                "channel_id": channel_id,
                "channel_url": f"https://www.youtube.com/channel/{channel_id}",
            }
        )
        seen.add(video_id)
        if len(rows) >= limit:
            break
    return rows
