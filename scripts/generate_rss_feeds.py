#!/usr/bin/env python3
"""Generate public RSS feeds for harmonica.observe.tw."""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from output_files import write_text_if_changed

import public_tags
import report_links
import site_chrome


OFFLINE = False

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
SITE_DATA = SITE_ROOT / "data" / "site-data.js"
CANDIDATES = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
SOCIAL_SOURCES = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
SOURCE_PROFILES_CACHE = PROJECT_ROOT / "data" / "feeds" / "source_profiles.json"
# Sources whose feed and page expose no usable avatar (blocked Instagram routes,
# pages without og:image) are fetched again only after this delay, not every run.
PROFILE_AVATAR_RETRY_AFTER = dt.timedelta(hours=24)
UPDATES_OUT = SITE_ROOT / "feeds" / "updates.xml"
SOURCES_OUT = SITE_ROOT / "feeds" / "sources.xml"
UPDATES_JSON_OUT = SITE_ROOT / "feeds" / "updates.json"
FEED_DATA_JS = SITE_ROOT / "data" / "feed-data.js"
HOME_PAGE = SITE_ROOT / "index.html"
API_DIR = SITE_ROOT / "api"
FEED_IMAGE_DIR = SITE_ROOT / "assets" / "feed-images"
SOURCE_AVATAR_DIR = SITE_ROOT / "assets" / "source-avatars"
# Remote images that answered with a client error. Kept in state/ rather than
# beside the images because everything under site/ is published.
IMAGE_FETCH_FAILURES = PROJECT_ROOT / "state" / "remote_image_failures.json"
IMAGE_FAILURE_RETRY_AFTER = dt.timedelta(days=7)
PUBLIC_BASE_URL = "https://harmonica.observe.tw"
ASSET_VERSION = site_chrome.ASSET_VERSION
HOME_FEED_BATCH_SIZE = 12
DEFAULT_UPDATE_WINDOW_DAYS = 30
HOME_FEED_DEFAULT_COUNTRIES = ("臺灣",)
HOME_FEED_DEFAULT_TAGS = ("口琴",)
SOCIAL_CAPTION_PLATFORMS = {"facebook", "instagram", "threads", "x"}
PLATFORM_FILTER_ORDER = ("Facebook", "Instagram", "RSS", "Threads", "X", "YouTube")
PLATFORM_FILTER_RANK = {label.casefold(): index for index, label in enumerate(PLATFORM_FILTER_ORDER)}
WEBP_QUALITY = "82"
TAG_VALUE_SPLIT_RE = re.compile(r"\s*(?:[,，、/／+&]|\band\b|\s+)\s*", re.IGNORECASE)
TAG_FORBIDDEN_CHARS_RE = re.compile(r"[,，、/／+&\s]")
LOCATION_VALUE_SPLIT_RE = re.compile(r"\s*(?:[/／；;、,，+&]|\band\b)\s*", re.IGNORECASE)
NON_LOCATION_LABELS = {"國際", "臺灣交流", "臺灣爵士圈"}
LEGACY_TAI = "\u53f0"
TAIWAN_ORTHOGRAPHY_REPLACEMENTS = (
    (f"{LEGACY_TAI}灣", "臺灣"),
    (f"{LEGACY_TAI}北", "臺北"),
    (f"{LEGACY_TAI}中", "臺中"),
    (f"{LEGACY_TAI}南", "臺南"),
)
BRAND_LOGO_HTML = site_chrome.BRAND_LOGO_HTML
FOOTER_HTML = """<footer class="site-footer">
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
    </footer>"""

TAIPEI_TZ = dt.timezone(dt.timedelta(hours=8))
SOURCE_PROFILE_BY_ID: dict[str, dict[str, str]] = {}
SOURCE_PROFILE_BY_ACCOUNT: dict[str, dict[str, str]] = {}
DIRECTORY_ENTRY_BY_KEY: dict[str, dict[str, str]] = {}
GENERIC_SOURCE_NAMES = {
    "apify facebook posts",
    "apify/facebook-posts-scraper",
    "apify_facebook_posts",
    "external public social feed inbox",
    "external_social_feed_inbox",
    "facebook",
    "people",
}

FEED_CATEGORIES = [
    {
        "id": "events",
        "title": "Harmonica Observatory · 口琴觀測站：口琴公開活動",
        "short_title": "公開活動",
        "description": "世界各地的公開口琴活動，以及有明確時間的線上口琴直播、講座與音樂會。",
        "page_title": "口琴公開活動",
        "page_intro": "國內口琴演出、成發、音樂會、講座、工作坊、音樂節，以及國內外有明確時間的線上口琴直播、講座與音樂會。",
        "rss_path": "feeds/events.xml",
        "json_path": "feeds/events.json",
        "page_path": "feeds/events/index.html",
    },
    {
        "id": "posts-videos",
        "title": "Harmonica Observatory · 口琴觀測站：口琴貼文與影片發布",
        "short_title": "貼文影片",
        "description": "世界各地的公開口琴社群貼文、影片發布與公開更新。",
        "page_title": "世界口琴貼文與影片發布",
        "page_intro": "公開社群貼文、YouTube 或影片發布、活動倒數、花絮、演奏內容與其他口琴圈公開更新。",
        "rss_path": "feeds/posts-videos.xml",
        "json_path": "feeds/posts-videos.json",
        "page_path": "feeds/posts-videos/index.html",
    },
    {
        "id": "student-clubs",
        "title": "Harmonica Observatory · 口琴觀測站：口琴學生社團動態",
        "short_title": "學生社團",
        "description": "全臺灣大專與高中職口琴社團公開動態。",
        "page_title": "全臺灣口琴學生社團動態",
        "page_intro": "大專與高中職口琴社團的成發、招生、社博、迎新、交流、寒暑訓與公開社群更新。",
        "rss_path": "feeds/student-clubs.xml",
        "json_path": "feeds/student-clubs.json",
        "page_path": "feeds/student-clubs/index.html",
    },
    {
        "id": "opportunities",
        "title": "Harmonica Observatory · 口琴觀測站：補助與比賽資訊",
        "short_title": "補助比賽",
        "description": "口琴社團需要知道的補助、徵件、甄選、比賽、報名與截止資訊。",
        "page_title": "口琴社團需要知道的補助與比賽資訊",
        "page_intro": "適合社團幹部追蹤的補助、競賽、徵件、報名期限、指定曲、計畫申請與甄選資訊。",
        "rss_path": "feeds/opportunities.xml",
        "json_path": "feeds/opportunities.json",
        "page_path": "feeds/opportunities/index.html",
    },
]

CATEGORY_LABELS = {category["id"]: category["short_title"] for category in FEED_CATEGORIES}

CATALOG_JSON_OUT = SITE_ROOT / "feeds" / "catalog.json"
FEED_INDEX_OUT = SITE_ROOT / "feeds" / "index.html"

EVENT_KEYWORDS = [
    "實體",
    "現場",
    "入場",
    "免費入場",
    "售票",
    "購票",
    "報名",
    "演出",
    "音樂會",
    "成發",
    "成果發表",
    "公演",
    "講座",
    "工作坊",
    "大師班",
    "音樂節",
    "校慶",
    "社博",
    "迎新",
    "招生",
    "交流",
    "寒訓",
    "暑訓",
]

OPPORTUNITY_KEYWORDS = [
    "補助",
    "獎助",
    "申請",
    "計畫",
    "徵件",
    "徵選",
    "徵求",
    "甄選",
    "比賽",
    "競賽",
    "指定曲",
    "報名",
    "截止",
    "期限",
    "全國學生音樂比賽",
    "學生音樂比賽",
    "口琴合奏",
    "口琴四重奏",
]

VIDEO_KEYWORDS = [
    "影片",
    "新片",
    "首播",
    "上架",
    "發布",
    "發佈",
    "直播",
    "演奏影片",
    "youtube",
    "video",
    "premiere",
    "cover",
]

STUDENT_SOURCE_MARKERS = [
    "club",
    "harmonica club",
    "hmc",
    "ntubluesound",
    "ntnu",
    "nthu",
    "ncku",
    "fcu",
    "nutc",
    "ncue",
    "npust",
    "csmu",
    "nkust",
    "mcu",
    "ckhc",
    "hsnu",
    "tcfsh",
    "chgsh",
    "tnfsh",
    "kshs",
    "大學",
    "高中",
    "高職",
    "高工",
    "高商",
    "一中",
    "女中",
    "師大",
    "清大",
    "清華",
    "交大",
    "成大",
    "臺大",
    "台大",
    "學生",
    "社團",
    "口琴社",
]


def parse_site_data(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    prefix = "window.HARMONICA_OBSERVE_DATA = "
    if text.startswith(prefix):
        text = text[len(prefix) :]
    return json.loads(text.rstrip(";\n"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def parse_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    raw = str(value).strip()
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


def rss_time(value: str | None, fallback: dt.datetime) -> str:
    parsed = parse_time(value)
    return email.utils.format_datetime(parsed or fallback)


def normalize_taiwan_orthography(value: Any) -> str:
    text = str(value or "").strip()
    for source, target in TAIWAN_ORTHOGRAPHY_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def compact(value: str, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", normalize_taiwan_orthography(value)).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def compact_multiline(value: str, limit: int = 1200) -> str:
    lines = [re.sub(r"[ \t]+", " ", normalize_taiwan_orthography(line)).strip() for line in (value or "").splitlines()]
    clean_lines: list[str] = []
    for line in lines:
        if line and (not clean_lines or clean_lines[-1] != line):
            clean_lines.append(line)
    text = "\n".join(clean_lines).strip()
    return text[: limit - 1] + "…" if len(text) > limit else text


def first_content_line(value: str, limit: int = 120) -> str:
    for line in compact_multiline(value, limit=limit * 4).splitlines():
        if line.strip():
            return compact(line, limit)
    return compact(value, limit)


def image_extension(url: str, content_type: str) -> str:
    if "svg" in content_type:
        return ".svg"
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    if "gif" in content_type:
        return ".gif"
    suffix = Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def find_binary(name: str) -> str:
    for candidate in (
        shutil.which(name),
        f"/opt/homebrew/bin/{name}",
        f"/usr/local/bin/{name}",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return ""


def webp_converter_for(ext: str) -> list[str]:
    if ext == ".gif":
        binary = find_binary("gif2webp")
        return [binary, "-quiet", "-q", WEBP_QUALITY] if binary else []
    binary = find_binary("cwebp")
    return [binary, "-quiet", "-q", WEBP_QUALITY] if binary else []


def convert_image_bytes_to_webp(data: bytes, ext: str, output_path: Path) -> bool:
    command = webp_converter_for(ext)
    if not command:
        return False
    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            input_path = tmp_root / f"input{ext}"
            tmp_output = tmp_root / "output.webp"
            input_path.write_bytes(data)

            # Check if we should resize the image to max width 800
            resize_args = []
            if ext.casefold() in {".jpg", ".jpeg", ".png"}:
                try:
                    ffprobe_result = subprocess.run(
                        [
                            "ffprobe",
                            "-v", "error",
                            "-select_streams", "v:0",
                            "-show_entries", "stream=width",
                            "-of", "csv=p=0",
                            str(input_path)
                        ],
                        capture_output=True,
                        text=True,
                        check=True
                    )
                    width = int(ffprobe_result.stdout.strip())
                    if width > 800:
                        resize_args = ["-resize", "800", "0"]
                except Exception:
                    pass

            try:
                subprocess.run(
                    [*command, *resize_args, str(input_path), "-o", str(tmp_output)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except subprocess.CalledProcessError:
                ffmpeg = find_binary("ffmpeg")
                if not ffmpeg:
                    return False
                png_path = tmp_root / "decoded.png"
                subprocess.run(
                    [
                        ffmpeg,
                        "-hide_banner",
                        "-loglevel",
                        "error",
                        "-y",
                        "-i",
                        str(input_path),
                        "-vf",
                        "scale='min(800,iw)':-1",
                        "-frames:v",
                        "1",
                        "-update",
                        "1",
                        str(png_path),
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    [*webp_converter_for(".png"), str(png_path), "-o", str(tmp_output)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            output_bytes = tmp_output.read_bytes()
            if not output_path.exists() or output_path.read_bytes() != output_bytes:
                output_path.write_bytes(output_bytes)
    except (OSError, subprocess.CalledProcessError):
        return False
    return True


_IMAGE_DIR_INDEX: dict[Path, dict[str, list[str]]] = {}
_IMAGE_FAILURES: dict[Path, dict[str, dict[str, Any]]] = {}


def image_dir_index(image_dir: Path) -> dict[str, list[str]]:
    """Cached file names by digest, listed once per directory per run instead of a glob per image."""
    index = _IMAGE_DIR_INDEX.get(image_dir)
    if index is None:
        index = {}
        try:
            names = sorted(entry.name for entry in image_dir.iterdir())
        except OSError:
            names = []
        for name in names:
            stem, dot, _ = name.partition(".")
            if dot and stem:
                index.setdefault(stem, []).append(name)
        _IMAGE_DIR_INDEX[image_dir] = index
    return index


def signed_url_expired(url: str, now: dt.datetime) -> bool:
    """True when a signed CDN URL's ``oe=`` hex expiry (Instagram, Facebook) has passed."""
    values = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("oe") or []
    try:
        expires_at = int(values[0], 16)
    except (IndexError, ValueError):
        return False
    return expires_at <= now.timestamp()


def image_failures(path: Path) -> dict[str, dict[str, Any]]:
    failures = _IMAGE_FAILURES.get(path)
    if failures is None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        failures = payload.get("failures") if isinstance(payload, dict) else None
        failures = {key: value for key, value in (failures or {}).items() if isinstance(value, dict)}
        _IMAGE_FAILURES[path] = failures
    return failures


def save_image_failures(path: Path) -> None:
    failures = image_failures(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    write_text_if_changed(
        path,
        json.dumps({"version": 1, "failures": failures}, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        temp_path=tmp_path,
    )


def image_failure_blocks_fetch(entry: dict[str, Any] | None, now: dt.datetime) -> bool:
    if not entry:
        return False
    if entry.get("permanent"):
        return True
    try:
        failed_at = dt.datetime.fromisoformat(str(entry.get("failed_at") or ""))
    except ValueError:
        return False
    if failed_at.tzinfo is None:
        failed_at = failed_at.replace(tzinfo=dt.timezone.utc)
    return now - failed_at < IMAGE_FAILURE_RETRY_AFTER


def cache_remote_image(
    url: str,
    image_dir: Path,
    public_prefix: str,
    max_bytes: int = 5_000_000,
    failure_cache: Path | None = None,
) -> str:
    if not url:
        return ""
    if url.startswith("/assets/"):
        return url
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
    webp_path = image_dir / f"{digest}.webp"
    if webp_path.exists():
        return f"{public_prefix}/{webp_path.name}"
    index = image_dir_index(image_dir)
    existing = [image_dir / name for name in index.get(digest, []) if name != webp_path.name]
    if existing:
        existing_path = existing[0]
        ext = existing_path.suffix.casefold() or ".jpg"
        try:
            data = existing_path.read_bytes()
        except OSError:
            data = b""
        if data and convert_image_bytes_to_webp(data, ext, webp_path):
            try:
                existing_path.unlink()
            except OSError:
                pass
            index[digest] = [webp_path.name]
            return f"{public_prefix}/{webp_path.name}"
        return f"{public_prefix}/{existing_path.name}"

    if OFFLINE:
        return ""
    now = dt.datetime.now(dt.timezone.utc)
    failures = image_failures(failure_cache) if failure_cache else None
    if failures is not None and image_failure_blocks_fetch(failures.get(digest), now):
        return ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HarmonicaObserveImageCache/1.0"})
        with urllib.request.urlopen(req, timeout=20) as response:
            content_type = response.headers.get("content-type", "")
            if not content_type.startswith("image/"):
                return ""
            data = response.read(max_bytes)
    except urllib.error.HTTPError as exc:
        # Only a definite client error is remembered; timeouts, server errors and
        # rate limits may pass, so those images are retried on the next run.
        if failures is not None and 400 <= exc.code < 500 and exc.code not in {408, 429}:
            failures[digest] = {
                "failed_at": now.isoformat(),
                "status": exc.code,
                # A signed CDN URL past its expiry never works again.
                "permanent": exc.code in {403, 404} and signed_url_expired(url, now),
            }
            save_image_failures(failure_cache)
        return ""
    except (urllib.error.URLError, TimeoutError, OSError):
        return ""
    if failures is not None and failures.pop(digest, None) is not None:
        save_image_failures(failure_cache)

    image_dir.mkdir(parents=True, exist_ok=True)
    ext = image_extension(url, content_type)
    path = image_dir / f"{digest}.webp"
    if convert_image_bytes_to_webp(data, ext, path):
        index[digest] = [path.name]
        return f"{public_prefix}/{path.name}"

    fallback = image_dir / f"{digest}{ext}"
    if not fallback.exists() or fallback.read_bytes() != data:
        fallback.write_bytes(data)
    index[digest] = [fallback.name]
    return f"{public_prefix}/{fallback.name}"


def request_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(urllib.parse.unquote(parsed.path), safe="/:@")
    query = urllib.parse.quote(urllib.parse.unquote(parsed.query), safe="=&?/:@,+%")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path, query, parsed.fragment))


def cache_image(url: str) -> str:
    return cache_remote_image(url, FEED_IMAGE_DIR, "/assets/feed-images", failure_cache=IMAGE_FETCH_FAILURES)


def cache_avatar(url: str) -> str:
    return cache_remote_image(
        url,
        SOURCE_AVATAR_DIR,
        "/assets/source-avatars",
        max_bytes=2_000_000,
        failure_cache=IMAGE_FETCH_FAILURES,
    )


def parse_png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    return None


def parse_gif_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) >= 10 and data[:6] in {b"GIF87a", b"GIF89a"}:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    return None


def parse_jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 4 or not data.startswith(b"\xff\xd8"):
        return None
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            break
        length = int.from_bytes(data[index:index + 2], "big")
        if length < 2 or index + length > len(data):
            break
        if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF} and length >= 7:
            height = int.from_bytes(data[index + 3:index + 5], "big")
            width = int.from_bytes(data[index + 5:index + 7], "big")
            return width, height
        index += length
    return None


def parse_webp_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30 or not data.startswith(b"RIFF") or data[8:12] != b"WEBP":
        return None
    chunk = data[12:16]
    if chunk == b"VP8 ":
        start = data.find(b"\x9d\x01\x2a", 20)
        if start != -1 and start + 7 <= len(data):
            width_raw = int.from_bytes(data[start + 3:start + 5], "little")
            height_raw = int.from_bytes(data[start + 5:start + 7], "little")
            return width_raw & 0x3FFF, height_raw & 0x3FFF
    if chunk == b"VP8L":
        b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
        width = 1 + (((b1 & 0x3F) << 8) | b0)
        height = 1 + (((b3 & 0x0F) << 10) | (b2 << 2) | ((b1 & 0xC0) >> 6))
        return width, height
    if chunk == b"VP8X":
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    return None


def image_dimensions(public_url: str) -> tuple[int, int] | None:
    path = public_asset_path(public_url)
    if path is None:
        return None
    try:
        data = path.read_bytes()
    except OSError:
        return None
    for parser in (parse_png_dimensions, parse_gif_dimensions, parse_jpeg_dimensions, parse_webp_dimensions):
        dimensions = parser(data)
        if dimensions and dimensions[0] > 0 and dimensions[1] > 0:
            return dimensions
    return None


def public_asset_path(public_url: str) -> Path | None:
    value = str(public_url or "").strip()
    if not value.startswith("/assets/"):
        return None
    return SITE_ROOT / value.lstrip("/").split("?", 1)[0]


def local_image_asset_valid(public_url: str) -> bool:
    path = public_asset_path(public_url)
    if path is None:
        return False
    try:
        header = path.read_bytes()[:256]
    except OSError:
        return False
    if len(header) < 10:
        return False
    stripped = header.lstrip().lower()
    return (
        header.startswith(b"\xff\xd8")
        or header.startswith(b"\x89PNG\r\n\x1a\n")
        or header.startswith(b"GIF8")
        or (header[:4] == b"RIFF" and header[8:12] == b"WEBP")
        or stripped.startswith(b"<svg")
        or stripped.startswith(b"<?xml") and b"<svg" in stripped
    )


def ensure_profile_avatar_url(profile: dict[str, str]) -> bool:
    avatar_url = str(profile.get("avatar_url") or "").strip()
    avatar_source_url = str(profile.get("avatar_source_url") or "").strip()
    if (
        avatar_url
        and local_image_asset_valid(avatar_url)
        and (not avatar_source_url or usable_profile_avatar_source(avatar_source_url))
    ):
        return False

    if avatar_source_url and usable_profile_avatar_source(avatar_source_url):
        cached_avatar = cache_avatar(avatar_source_url)
        if cached_avatar and local_image_asset_valid(cached_avatar):
            if cached_avatar != avatar_url:
                profile["avatar_url"] = cached_avatar
                return True
            return False

    if avatar_url and avatar_url.startswith("/assets/"):
        profile.pop("avatar_url", None)
        return True
    return False


def usable_profile_avatar_source(url: str) -> bool:
    value = str(url or "").strip().casefold()
    if not value:
        return False
    generic_markers = (
        "static.cdninstagram.com/rsrc.php",
        "static.xx.fbcdn.net/rsrc.php",
    )
    return not any(marker in value for marker in generic_markers)


def url_part(value: Any) -> str:
    return urllib.parse.quote(str(value or "").strip(), safe="")


def match_text_key(value: Any) -> str:
    return re.sub(r"\s+", " ", normalize_taiwan_orthography(value)).strip().casefold()


def match_url_key(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw.startswith(("http://", "https://")):
        return ""
    parsed = urllib.parse.urlsplit(raw)
    host = parsed.netloc.casefold().removeprefix("www.")
    path = urllib.parse.unquote(parsed.path or "/").strip("/")
    path = re.sub(r"/+", "/", path).casefold()
    if host in {"instagram.com", "facebook.com", "m.facebook.com", "x.com", "twitter.com", "threads.net", "youtube.com", "youtu.be"}:
        return f"{host}/{path}".rstrip("/")
    return f"{host}/{path}".rstrip("/")


def format_rsshub_route(route: str, source: dict[str, Any]) -> str:
    values = {
        "username": url_part(source.get("username") or ""),
        "page": url_part(source.get("page") or source.get("username") or ""),
        "id": url_part(source.get("account_id") or source.get("page") or source.get("username") or ""),
    }
    for key, value in values.items():
        route = route.replace("{" + key + "}", value)
    return route


def source_feed_url(source: dict[str, Any]) -> str:
    if source.get("provider") in {"instagram_public", "apify_stories"}:
        return str(source.get("source_profile_url") or "")
    base = str(source.get("rsshub_base") or "").rstrip("/")
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
    if kind == "rsshub_instagram_story":
        username = source.get("username")
        if str(source.get("provider") or "") == "instaloader":
            return f"https://www.instagram.com/{url_part(username)}/" if username else ""
        return f"{base}/picuki/profile/{url_part(username)}/story/0" if username else ""
    return str(source.get("url") or "")


def public_profile_url(source: dict[str, Any]) -> str:
    kind = source.get("type")
    for field in ("profile_url", "source_profile_url"):
        url = str(source.get(field) or "").strip()
        if url:
            return url
    url = str(source.get("url") or "").strip()
    if url and not source.get("route"):
        return url
    if kind == "facebook_page_posts":
        page = str(source.get("page") or source.get("username") or "").strip().strip("/")
        return f"https://www.facebook.com/{page}/" if page else ""
    if kind in {"rsshub_instagram_profile", "rsshub_instagram_story"}:
        username = str(source.get("username") or "").strip().strip("/")
        return f"https://www.instagram.com/{username}/" if username else ""
    platform = str(source.get("platform") or "").casefold()
    username = str(source.get("username") or "").strip().strip("/").removeprefix("@")
    if username and (platform in {"x", "twitter"} or "twitter" in platform):
        return f"https://x.com/{username}"
    if username and "threads" in platform:
        return f"https://www.threads.net/@{username}"
    if username and "tiktok" in platform:
        return f"https://www.tiktok.com/@{username}"
    return ""


def html_meta(text: str, property_name: str) -> str:
    patterns = [
        rf'<meta\s+property=["\']{re.escape(property_name)}["\']\s+content=["\']([^"\']+)["\']',
        rf'<meta\s+content=["\']([^"\']+)["\']\s+property=["\']{re.escape(property_name)}["\']',
        rf'<meta\s+name=["\']{re.escape(property_name)}["\']\s+content=["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1)).strip()
    return ""


def fetch_html_profile(source: dict[str, Any]) -> dict[str, str]:
    profile_url = public_profile_url(source)
    profile: dict[str, str] = {
        "id": str(source.get("id") or ""),
        "name": str(source.get("name") or source.get("id") or ""),
        "account": str(source.get("username") or source.get("page") or source.get("url") or ""),
        "platform": str(source.get("platform") or source.get("type") or ""),
        "profile_url": profile_url,
        "avatar_source_url": "",
    }
    if not profile_url or OFFLINE:
        return profile

    try:
        req = urllib.request.Request(
            request_url(profile_url),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/139.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            text = response.read(2_000_000).decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return profile

    title = html_meta(text, "og:title")
    description = html_meta(text, "og:description")
    canonical_url = html_meta(text, "og:url")
    avatar = html_meta(text, "og:image")
    if title:
        profile["title"] = title
    if description:
        profile["description"] = description
    if canonical_url:
        profile["profile_url"] = canonical_url
    if avatar:
        profile["avatar_source_url"] = avatar
    return profile


def fetch_source_profile(source: dict[str, Any]) -> dict[str, str]:
    if OFFLINE:
        return source_profile_from_config(str(source.get("id") or ""), source)
    if source.get("type") in {"youtube_ytdlp", "facebook_page_posts"}:
        return fetch_html_profile(source)

    feed_url = source_feed_url(source)
    profile: dict[str, str] = {
        "id": str(source.get("id") or ""),
        "name": str(source.get("name") or source.get("id") or ""),
        "account": str(source.get("username") or source.get("page") or ""),
        "platform": str(source.get("platform") or source.get("type") or ""),
        "profile_url": "",
        "avatar_source_url": "",
    }
    if feed_url:
        try:
            req = urllib.request.Request(feed_url, headers={"User-Agent": "HarmonicaObserveProfileCache/1.0"})
            with urllib.request.urlopen(req, timeout=12) as response:
                root = ET.fromstring(response.read(2_000_000))
            channel = root.find("channel")
            if channel is not None:
                profile["title"] = channel.findtext("title") or ""
                profile["description"] = (channel.findtext("description") or "").replace(" - Powered by RSSHub", "").strip()
                profile["profile_url"] = channel.findtext("link") or ""
                profile["avatar_source_url"] = channel.findtext("image/url") or ""
            else:
                profile["avatar_source_url"] = root.findtext("{http://www.w3.org/2005/Atom}logo") or ""
        except (urllib.error.URLError, TimeoutError, OSError, ET.ParseError):
            pass

    if not usable_profile_avatar_source(profile.get("avatar_source_url", "")):
        profile = merge_profile(profile, fetch_html_profile(source))
    return profile


def row_source_profile(row: dict[str, Any]) -> dict[str, str]:
    values = {
        "id": row.get("source_id"),
        "name": row.get("source_name") or row.get("source_display_name"),
        "account": row.get("account"),
        "platform": row.get("platform"),
        "profile_url": row.get("source_profile_url") or row.get("profile_url"),
        "avatar_source_url": row.get("source_avatar_url") or row.get("avatar_source_url"),
    }
    return {
        key: str(value).strip()
        for key, value in values.items()
        if str(value or "").strip()
    }


def source_profile_from_config(source_id: str, source: dict[str, Any]) -> dict[str, str]:
    return {
        "id": source_id,
        "name": str(source.get("name") or source_id),
        "account": str(source.get("username") or source.get("page") or source.get("url") or ""),
        "platform": str(source.get("platform") or source.get("type") or ""),
        "profile_url": public_profile_url(source),
    }


def merge_profile(*profiles: dict[str, Any]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for profile in profiles:
        for key, value in profile.items():
            text = str(value or "").strip()
            if text:
                merged[str(key)] = text
    return merged


def build_source_profiles(
    rows: list[dict[str, Any]],
    extra_source_ids: list[str] | None = None,
    avatar_source_overrides: dict[str, str] | None = None,
) -> dict[str, dict[str, str]]:
    needed_ids = {str(row.get("source_id") or "") for row in rows if row.get("source_id")}
    needed_ids.update(str(source_id).strip() for source_id in (extra_source_ids or []) if str(source_id).strip())
    if not needed_ids:
        return {}

    source_config = read_json(SOCIAL_SOURCES, {"sources": []})
    sources = {
        str(source.get("id") or ""): source
        for source in source_config.get("sources", [])
        if isinstance(source, dict)
    }
    cache = read_json(SOURCE_PROFILES_CACHE, {"profiles": {}})
    profiles: dict[str, dict[str, str]] = {
        str(source_id): dict(profile)
        for source_id, profile in (cache.get("profiles") or {}).items()
        if isinstance(profile, dict)
    }
    raw_attempts = cache.get("avatarAttempts") if isinstance(cache.get("avatarAttempts"), dict) else {}
    avatar_attempts: dict[str, str] = {str(key): str(value) for key, value in raw_attempts.items()}
    now = dt.datetime.now(dt.timezone.utc)

    row_profiles: dict[str, dict[str, str]] = {}
    for row in rows:
        source_id = str(row.get("source_id") or "")
        if not source_id:
            continue
        row_profile = row_source_profile(row)
        current = row_profiles.get(source_id) or {}
        row_profiles[source_id] = merge_profile(row_profile, current)

    changed = False
    for source_id in sorted(needed_ids):
        source = sources.get(source_id)
        if not source:
            continue
        cached = profiles.get(source_id) or {}
        configured = source_profile_from_config(source_id, source)
        row_profile = row_profiles.get(source_id) or {}
        profile = merge_profile(configured, row_profile, cached)
        avatar_source_override = (avatar_source_overrides or {}).get(source_id, "").strip()
        if avatar_source_override:
            profile["avatar_source_url"] = avatar_source_override
        if not usable_profile_avatar_source(str(profile.get("avatar_source_url") or "")):
            last_attempt = parse_time(avatar_attempts.get(source_id))
            if last_attempt is None or now - last_attempt >= PROFILE_AVATAR_RETRY_AFTER:
                profile = merge_profile(profile, fetch_source_profile(source))
                if usable_profile_avatar_source(str(profile.get("avatar_source_url") or "")):
                    avatar_attempts.pop(source_id, None)
                else:
                    avatar_attempts[source_id] = now.isoformat()
                changed = True
        elif avatar_attempts.pop(source_id, None) is not None:
            changed = True
        if ensure_profile_avatar_url(profile):
            changed = True
        if profiles.get(source_id) != profile:
            profiles[source_id] = profile
            changed = True

    if changed:
        write_json(
            SOURCE_PROFILES_CACHE,
            {
                "updatedAt": now.isoformat(),
                "profiles": profiles,
                "avatarAttempts": dict(sorted(avatar_attempts.items())),
            },
        )
    return {source_id: profiles.get(source_id, {}) for source_id in needed_ids}


def source_profiles_by_account() -> dict[str, dict[str, str]]:
    cache = read_json(SOURCE_PROFILES_CACHE, {"profiles": {}})
    profiles = cache.get("profiles") if isinstance(cache, dict) else {}
    if not isinstance(profiles, dict):
        return {}

    by_account: dict[str, dict[str, str]] = {}
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        account = str(profile.get("account") or "").strip().removeprefix("@").casefold()
        if not account:
            continue
        current = by_account.get(account) or {}
        if profile_title_display_name(profile) and not profile_title_display_name(current):
            by_account[account] = dict(profile)
        else:
            by_account.setdefault(account, dict(profile))
    return by_account


def persist_source_profiles(profiles: dict[str, dict[str, str]]) -> None:
    if not profiles:
        return
    cache = read_json(SOURCE_PROFILES_CACHE, {"profiles": {}})
    cached_profiles = cache.get("profiles") if isinstance(cache, dict) else {}
    if not isinstance(cached_profiles, dict):
        cached_profiles = {}

    merged: dict[str, dict[str, str]] = {
        str(source_id): dict(profile)
        for source_id, profile in cached_profiles.items()
        if isinstance(profile, dict)
    }
    changed = False
    for source_id, profile in profiles.items():
        if not source_id or not isinstance(profile, dict):
            continue
        current = dict(merged.get(source_id) or {})
        updated = dict(current)
        for key, value in profile.items():
            if value not in ("", None):
                updated[str(key)] = str(value)
        if ensure_profile_avatar_url(updated):
            changed = True
        if updated != current:
            merged[source_id] = updated
            changed = True

    for source_id, profile in list(merged.items()):
        if ensure_profile_avatar_url(profile):
            merged[source_id] = profile
            changed = True

    if changed:
        write_json(
            SOURCE_PROFILES_CACHE,
            {
                "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                "profiles": merged,
            },
        )


def local_date(value: str | None) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return "未標示"
    return parsed.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")


def item_guid(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{PUBLIC_BASE_URL}/feeds/{prefix}/{digest}"


def add_text(parent: ET.Element, tag: str, value: str) -> ET.Element:
    child = ET.SubElement(parent, tag)
    child.text = value
    return child


def build_channel(title: str, description: str, link: str) -> ET.Element:
    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    add_text(channel, "title", title)
    add_text(channel, "link", link)
    add_text(channel, "description", description)
    add_text(channel, "language", "zh-TW")
    add_text(channel, "lastBuildDate", email.utils.format_datetime(dt.datetime.now(dt.timezone.utc)))
    return rss


def write_xml(path: Path, root: ET.Element) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(root, space="  ")
    write_text_if_changed(path, ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8"))


def candidate_sort_key(row: dict[str, Any]) -> dt.datetime:
    return parse_time(str(row.get("posted_at") or row.get("seen_at") or "")) or dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc)


def candidate_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(field) or "")
        for field in [
            "source_id",
            "source_name",
            "platform",
            "account",
            "url",
            "media_type",
            "text",
            "matched_keywords",
            "keyword_matches",
            "llm_labels",
            "llm_categories",
            "llm_reason",
        ]
    )


def has_any_marker(text: str, markers: list[str]) -> bool:
    lowered = text.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def unique_values(values: list[Any], limit: int = 8) -> list[str]:
    items: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in items:
            continue
        items.append(item)
        if len(items) >= limit:
            break
    return items


def normalize_tag_values(value: Any, *, limit: int = 8) -> list[str]:
    return public_tags.normalize_tag_values(value, limit=limit)


def llm_category_ids(row: dict[str, Any]) -> list[str]:
    values = row.get("llm_categories") or []
    if isinstance(values, str):
        values = re.split(r"[,，、\s]+", values)
    categories = unique_values(
        [str(value or "").strip() for value in values if str(value or "").strip() in CATEGORY_LABELS],
        limit=len(FEED_CATEGORIES),
    )
    if not categories:
        return []
    ids = ["posts-videos"]
    for category in categories:
        if category not in ids:
            ids.append(category)
    return ids


def candidate_category_ids(row: dict[str, Any]) -> list[str]:
    llm_ids = llm_category_ids(row)
    if row.get("llm_relevant") is False and not row.get("include_without_keywords"):
        return []

    text = candidate_text(row)
    ids = llm_ids or ["posts-videos"]
    if has_any_marker(text, EVENT_KEYWORDS):
        if "events" not in ids:
            ids.append("events")
    if has_any_marker(text, OPPORTUNITY_KEYWORDS):
        if "opportunities" not in ids:
            ids.append("opportunities")
    if has_any_marker(text, STUDENT_SOURCE_MARKERS):
        if "student-clubs" not in ids:
            ids.append("student-clubs")
    if has_any_marker(text, VIDEO_KEYWORDS) and "posts-videos" not in ids:
        ids.append("posts-videos")
    return ids


def candidate_display_tags(row: dict[str, Any]) -> list[str]:
    labels = row.get("llm_labels") or []
    keywords = row.get("matched_keywords") or []
    tags = normalize_tag_values([*normalize_tag_values(labels), *normalize_tag_values(keywords)], limit=8)
    if row.get("story") or row.get("media_type") == "instagram_story":
        return public_tags.sort_public_tags([*tags, "限時動態"])[:8]
    return tags


def read_candidate_rows() -> list[dict[str, Any]]:
    return sorted(read_jsonl(CANDIDATES), key=candidate_sort_key, reverse=True)


def candidate_dedupe_key(row: dict[str, Any], title: str) -> str:
    return str(row.get("url") or row.get("key") or title).strip().casefold()


def source_initials(source: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", source or "")
    if words:
        return "".join(word[0].upper() for word in words[:3])
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", source or "")
    if chinese_chars:
        return "".join(chinese_chars[:2])
    return "H"


def clean_source_display_name(value: Any) -> str:
    name = compact(str(value or ""), 180)
    if not name:
        return ""
    name = re.sub(r"\s+-\s+(YouTube|Instagram|Facebook)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+\|\s+(YouTube|Instagram|Facebook)\s*$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+\(@[^)]+\)\s*$", "", name)
    if " | " in name:
        name = name.split(" | ", 1)[0].strip()
    return compact(name, 120)


def profile_title_display_name(profile: dict[str, str]) -> str:
    title = str(profile.get("title") or "").strip()
    account = str(profile.get("account") or "").strip().removeprefix("@")
    platform = str(profile.get("platform") or "").casefold()
    if not title or not account:
        return ""
    match = re.match(r"(.+?)\s*\(@([^)]+)\)\s*-\s*(Instagram|Facebook|YouTube|X|Threads)\s*$", title, re.IGNORECASE)
    if match and match.group(2).casefold() == account.casefold():
        return clean_source_display_name(match.group(1))
    if "instagram" in platform:
        match = re.match(r"(.+?)\s*\(@([^)]+)\)", title)
        if match and match.group(2).casefold() == account.casefold():
            return clean_source_display_name(match.group(1))
    return ""


def is_generic_source_name(value: Any) -> bool:
    name = clean_source_display_name(value).casefold()
    return name in GENERIC_SOURCE_NAMES


def is_public_profile_url(value: Any) -> bool:
    url = str(value or "").strip()
    if not url.startswith(("http://", "https://")):
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold()
    if "facebook.com" in host:
        path = urllib.parse.unquote(parsed.path).strip("/")
        if not path and not parsed.query:
            return False
        if path.casefold() == "people":
            return False
        if path.casefold() == "profile.php" and not urllib.parse.parse_qs(parsed.query).get("id"):
            return False
    return True


def account_display_name(row: dict[str, Any], profile: dict[str, str]) -> str:
    account = str(row.get("account") or profile.get("account") or "").strip()
    if not account:
        return ""
    if account.startswith(("http://", "https://")):
        parsed = urllib.parse.urlparse(account)
        account = parsed.path.strip("/")
        if account.startswith("@"):
            account = account[1:]
        elif account.startswith(("people/", "profile.php")):
            return ""
        elif "/" in account:
            account = account.split("/", 1)[0]
    return clean_source_display_name(account.removeprefix("@"))


def public_source_name(row: dict[str, Any], profile: dict[str, str]) -> str:
    source_display_name = clean_source_display_name(row.get("source_display_name"))
    source_name = clean_source_display_name(row.get("source_name"))
    profile_title_name = profile_title_display_name(profile)
    account_name = account_display_name(row, profile)
    if source_display_name and not is_generic_source_name(source_display_name) and not (
        account_name
        and source_display_name == account_name
        and source_name
        and not is_generic_source_name(source_name)
    ):
        return source_display_name

    if profile_title_name and not is_generic_source_name(profile_title_name):
        return profile_title_name

    if source_name and not is_generic_source_name(source_name):
        return source_name

    for value in [
        row.get("profile_name"),
        row.get("page_name"),
        profile.get("title"),
        profile.get("display_name"),
    ]:
        name = clean_source_display_name(value)
        if name:
            return name

    platform = str(row.get("platform") or profile.get("platform") or "").casefold()
    source_id = str(row.get("source_id") or "").casefold()
    if "facebook" in platform and (
        is_generic_source_name(row.get("source_name"))
        or source_id in GENERIC_SOURCE_NAMES
        or str(row.get("raw_source") or "").casefold() in GENERIC_SOURCE_NAMES
    ):
        if account_name:
            return account_name

    for value in [
        row.get("source_name"),
        profile.get("name"),
        row.get("source_id"),
    ]:
        name = clean_source_display_name(value)
        if name and not is_generic_source_name(name):
            return name
    return "公開來源"


def public_source_profile_url(row: dict[str, Any], profile: dict[str, str]) -> str:
    for value in [
        row.get("source_profile_url"),
        row.get("profile_url"),
        profile.get("profile_url"),
        row.get("account"),
    ]:
        url = str(value or "").strip()
        if is_public_profile_url(url):
            return url

    account = str(row.get("account") or profile.get("account") or "").strip().strip("/")
    if not account:
        return ""
    if is_generic_source_name(account):
        return ""
    platform = str(row.get("platform") or profile.get("platform") or "").casefold()
    account = account.removeprefix("@")
    if "instagram" in platform:
        return f"https://www.instagram.com/{url_part(account)}/"
    if "facebook" in platform:
        return f"https://www.facebook.com/{account}/"
    if "youtube" in platform:
        if account.startswith("channel/") or account.startswith("c/") or account.startswith("user/"):
            return f"https://www.youtube.com/{account}"
        return f"https://www.youtube.com/@{url_part(account)}"
    if platform in {"x", "twitter"} or "twitter" in platform:
        return f"https://x.com/{url_part(account)}"
    if "threads" in platform:
        return f"https://www.threads.net/@{url_part(account)}"
    if "tiktok" in platform:
        account = account if account.startswith("@") else f"@{account}"
        return f"https://www.tiktok.com/{url_part(account)}"
    return ""


def public_social_source_profile_url(source: dict[str, Any]) -> str:
    row = dict(source)
    if not row.get("account"):
        row["account"] = row.get("username") or ""
    return public_source_profile_url(row, source)


def public_social_source_feed_url(source: dict[str, Any]) -> str:
    for field in ("feed_url", "rss_url"):
        value = str(source.get(field) or "").strip()
        if value.startswith(("http://", "https://")):
            return value

    rsshub_base = str(source.get("rsshub_base") or "").rstrip("/")
    route = str(source.get("route") or "")
    username = str(source.get("username") or source.get("account") or "").strip()
    if rsshub_base and route and username:
        return f"{rsshub_base}{route.format(username=url_part(username))}"
    return ""


def public_social_sources() -> list[dict[str, str]]:
    config = read_json(SOCIAL_SOURCES, {"sources": []})
    sources: list[dict[str, str]] = []
    for source in config.get("sources", []):
        if not source.get("enabled", True) or source.get("type") == "jsonl":
            continue
        username = normalize_taiwan_orthography(source.get("username") or source.get("account") or "")
        sources.append(
            {
                "id": str(source.get("id") or ""),
                "name": normalize_taiwan_orthography(source.get("name") or source.get("title") or source.get("id") or "公開來源"),
                "platform": str(source.get("platform") or source.get("type") or "unknown"),
                "type": str(source.get("type") or "unknown"),
                "username": username,
                "profileUrl": public_social_source_profile_url(source),
                "feedUrl": public_social_source_feed_url(source),
            }
        )
    return sorted(
        sources,
        key=lambda item: (
            str(item.get("platform") or ""),
            str(item.get("name") or ""),
            str(item.get("id") or ""),
        ),
    )


def directory_entry_lookup() -> dict[str, dict[str, str]]:
    data = parse_site_data(SITE_DATA)
    lookup: dict[str, dict[str, str]] = {}
    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            continue
        info = {
            "directory_entry_id": str(entry.get("id") or ""),
            "directory_entry_name": normalize_taiwan_orthography(entry.get("name") or ""),
            "country": normalize_taiwan_orthography(entry.get("country") or ""),
            "region": normalize_taiwan_orthography(entry.get("region") or ""),
        }
        if not info["country"]:
            continue
        for link in entry.get("links") or []:
            if isinstance(link, dict):
                key = match_url_key(link.get("url"))
                if key:
                    lookup[f"url:{key}"] = info
        for source in entry.get("monitorSources") or []:
            if isinstance(source, dict):
                source_id = str(source.get("id") or "").strip()
                if source_id:
                    lookup[f"source_id:{source_id}"] = info
        for field in ("name", "nameEn"):
            key = match_text_key(entry.get(field))
            if key:
                lookup.setdefault(f"name:{key}", info)
        for alias in entry.get("aliases") or []:
            key = match_text_key(alias)
            if key:
                lookup.setdefault(f"name:{key}", info)
    return lookup


def directory_profile_for_update(row: dict[str, Any], profile: dict[str, str], source_name: str, source_profile_url: str, link: str) -> dict[str, str]:
    source_id = str(row.get("source_id") or "").strip()
    if source_id and f"source_id:{source_id}" in DIRECTORY_ENTRY_BY_KEY:
        return DIRECTORY_ENTRY_BY_KEY[f"source_id:{source_id}"]

    for value in (
        source_profile_url,
        row.get("source_profile_url"),
        row.get("profile_url"),
        profile.get("profile_url"),
        link,
    ):
        key = match_url_key(value)
        if key and f"url:{key}" in DIRECTORY_ENTRY_BY_KEY:
            return DIRECTORY_ENTRY_BY_KEY[f"url:{key}"]

    for value in (
        source_name,
        row.get("source_name"),
        row.get("source_display_name"),
        profile.get("name"),
    ):
        key = match_text_key(value)
        if key and f"name:{key}" in DIRECTORY_ENTRY_BY_KEY:
            return DIRECTORY_ENTRY_BY_KEY[f"name:{key}"]
    return {}


def public_update_title_kind(row: dict[str, Any], story: bool) -> str:
    if story:
        return "caption"
    platform = str(row.get("platform") or "").strip().casefold()
    if platform in SOCIAL_CAPTION_PLATFORMS:
        return "caption"
    return "title"


def public_update_display_title(row: dict[str, Any], headline: str, title_kind: str) -> str:
    if title_kind != "title":
        return ""
    return str(row.get("rsshub_title") or headline or "").strip()


def parse_engagement_count(value: Any) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value) if value >= 0 else None
    if isinstance(value, dict):
        total = 0
        found = False
        for nested_value in value.values():
            count = parse_engagement_count(nested_value)
            if count is None:
                continue
            total += count
            found = True
        return total if found else None
    if isinstance(value, list):
        total = 0
        found = False
        for nested_value in value:
            count = parse_engagement_count(nested_value)
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


def first_engagement_count(row: dict[str, Any], fields: tuple[str, ...]) -> int | None:
    for field in fields:
        value = parse_engagement_count(row.get(field))
        if value is not None:
            return value
    return None


def public_update_row(row: dict[str, Any]) -> dict[str, Any]:
    source_id = str(row.get("source_id") or "")
    account_key = str(row.get("account") or "").strip().removeprefix("@").casefold()
    account_profile = SOURCE_PROFILE_BY_ACCOUNT.get(account_key, {}) if account_key else {}
    profile = merge_profile(SOURCE_PROFILE_BY_ID.get(source_id, {}), account_profile)
    source = public_source_name(row, profile)
    source_system_name = normalize_taiwan_orthography(row.get("source_name") or profile.get("name") or row.get("source_id") or "")
    if is_generic_source_name(source_system_name):
        source_system_name = source
    source_profile_url = public_source_profile_url(row, profile)
    link = str(row.get("url") or PUBLIC_BASE_URL)
    directory_profile = directory_profile_for_update(row, profile, source, source_profile_url, link)

    directory_name = directory_profile.get("directory_entry_name") or ""
    if directory_name and is_generic_source_name(source):
        source = directory_name

    text = compact_multiline(str(row.get("text") or ""), 1200)
    title = compact(f"{source}｜{text}", 120)
    headline = first_content_line(text, 120) or source
    categories = candidate_category_ids(row)
    display_tags = candidate_display_tags(row)
    media_type = str(row.get("media_type") or "")
    story = bool(row.get("story") or media_type == "instagram_story")
    platform_label = "Instagram story" if story else source_platform_label(row.get("platform") or "")
    title_kind = public_update_title_kind(row, story)
    display_title = public_update_display_title(row, headline, title_kind)
    images = [str(url) for url in (row.get("images") or []) if url]
    image_url = str(row.get("image_url") or (images[0] if images else ""))
    videos = [str(url) for url in (row.get("videos") or []) if url]
    local_image_url = cache_image(image_url)
    image_width, image_height = image_dimensions(local_image_url or image_url) or (None, None)
    avatar_source_url = str(
        row.get("source_avatar_url")
        or row.get("avatar_source_url")
        or profile.get("avatar_source_url")
        or ""
    )
    avatar_url = cache_avatar(avatar_source_url)
    if not avatar_url and local_image_asset_valid(str(profile.get("avatar_url") or "")):
        avatar_url = str(profile.get("avatar_url") or "")
        if not avatar_source_url:
            avatar_source_url = str(profile.get("avatar_source_url") or "")
    if source_id and avatar_source_url:
        cached_profile = SOURCE_PROFILE_BY_ID.setdefault(source_id, {})
        if not cached_profile.get("avatar_source_url") or not cached_profile.get("avatar_url"):
            cached_profile["avatar_source_url"] = avatar_source_url
        if avatar_url and cached_profile.get("avatar_url") != avatar_url:
            cached_profile["avatar_url"] = avatar_url
    return {
        "title": title,
        "headline": headline,
        "display_title": display_title,
        "title_kind": title_kind,
        "link": link,
        "source_id": source_id,
        "source": source,
        "source_system_name": source_system_name,
        "source_profile_url": source_profile_url,
        "country": directory_profile.get("country") or "",
        "region": directory_profile.get("region") or "",
        "directory_entry_id": directory_profile.get("directory_entry_id") or "",
        "directory_entry_name": directory_profile.get("directory_entry_name") or "",
        "account": row.get("account") or profile.get("account") or "",
        "platform": row.get("platform") or "",
        "platform_label": platform_label,
        "posted_at": "" if media_type == "webpage_update" or row.get("platform") == "website" else row.get("posted_at") or "",
        "posted_at_local": "" if media_type == "webpage_update" or row.get("platform") == "website" else local_date(str(row.get("posted_at") or "")),
        "like_count": first_engagement_count(row, ("like_count", "likes", "likes_count", "likeCount", "likesCount")),
        "comment_count": first_engagement_count(row, ("comment_count", "comments", "comments_count", "commentCount", "commentsCount")),
        "share_count": first_engagement_count(row, ("share_count", "shares", "shares_count", "shareCount", "sharesCount")),
        "reaction_count": first_engagement_count(row, ("reaction_count", "reactions", "reactions_count", "reactionCount", "reactionsCount", "total_reactions", "totalReactionCount")),
        "view_count": first_engagement_count(row, ("view_count", "views", "viewCount", "play_count", "playCount", "video_view_count", "videoViewCount", "watch_count", "watchCount")),
        "seen_at": row.get("seen_at") or "",
        "media_type": media_type,
        "story": story,
        "story_provider": row.get("story_provider") or "",
        "story_fetched_at": row.get("story_fetched_at") or "",
        "story_expires_at": row.get("story_expires_at") or "",
        "source_feed_url": row.get("source_feed_url") or "",
        "rsshub_guid": row.get("rsshub_guid") or "",
        "rsshub_title": row.get("rsshub_title") or "",
        "instagram_user_id": row.get("instagram_user_id") or "",
        "matched_keywords": display_tags,
        "keyword_matches": row.get("keyword_matches") or [],
        "llm_relevant": row.get("llm_relevant"),
        "llm_confidence": row.get("llm_confidence"),
        "llm_labels": normalize_tag_values(row.get("llm_labels") or []),
        "llm_categories": row.get("llm_categories") or [],
        "llm_reason": normalize_taiwan_orthography(row.get("llm_reason") or ""),
        "text": text,
        "images": images,
        "videos": videos,
        "source_image_url": image_url,
        "image_url": local_image_url or image_url,
        "image_width": image_width,
        "image_height": image_height,
        "source_avatar_url": avatar_source_url,
        "avatar_url": avatar_url,
        "source_initials": source_initials(source),
        "categories": categories,
        "category_labels": [CATEGORY_LABELS.get(category, category) for category in categories],
        "key": row.get("key") or item_guid("updates", link + title),
        "_dedupe_key": candidate_dedupe_key(row, title),
    }


def add_update_item(channel: ET.Element, public_row: dict[str, Any]) -> None:
    item = ET.SubElement(channel, "item")
    add_text(item, "title", str(public_row["title"]))
    add_text(item, "link", str(public_row["link"]))
    add_text(item, "guid", str(public_row["key"]))
    if public_row.get("posted_at"):
        add_text(item, "pubDate", rss_time(str(public_row["posted_at"]), dt.datetime.now(dt.timezone.utc)))
    description = "\n".join(
        part
        for part in [
            f"來源：{public_row.get('source')}",
            f"平台：{public_row.get('platform_label') or public_row.get('platform') or 'public'}",
            f"發布時間：{public_row.get('posted_at') or '未標示'}",
            f"網站頁面快照 · 觀測時間（非發布日期）：{public_row.get('seen_at') or '未標示'}" if public_row.get("media_type") == "webpage_update" or public_row.get("platform") == "website" else "",
            f"標籤：{', '.join(public_row.get('matched_keywords') or [])}" if public_row.get("matched_keywords") else "",
            "",
            str(public_row.get("text") or ""),
        ]
        if part != ""
    )
    add_text(item, "description", description)


def build_update_items(rows: list[dict[str, Any]], limit: int | None = None, category_id: str | None = None) -> list[dict[str, Any]]:
    public_rows: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    max_items = max(0, int(limit or 0))

    for row in rows:
        public_row = public_update_row(row)
        if category_id and category_id not in public_row["categories"]:
            continue
        dedupe_key = str(public_row["_dedupe_key"])
        if dedupe_key in seen_items:
            continue
        seen_items.add(dedupe_key)
        public_row.pop("_dedupe_key", None)
        public_rows.append(public_row)
        if max_items and len(public_rows) >= max_items:
            break

    validate_update_tags(public_rows)
    return public_rows


def validate_update_tags(items: list[dict[str, Any]]) -> None:
    errors: list[str] = []
    for item in items:
        title = str(item.get("headline") or item.get("title") or item.get("key") or "未命名更新")
        for tag in item.get("matched_keywords") or []:
            text = str(tag or "").strip()
            if not text:
                continue
            if TAG_FORBIDDEN_CHARS_RE.search(text) or re.search(r"\band\b", text, re.IGNORECASE):
                errors.append(f"{title}: composite matched_keyword {text!r}")
            if text not in public_tags.PUBLIC_TAG_SET:
                errors.append(f"{title}: unsupported matched_keyword {text!r}")
    if errors:
        formatted = "\n".join(f"- {error}" for error in errors[:40])
        if len(errors) > 40:
            formatted += f"\n- ... and {len(errors) - 40} more"
        raise SystemExit("Invalid public feed tags:\n" + formatted)


def write_update_json(path: Path, items: list[dict[str, Any]], category: dict[str, str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {"items": items}
    if category:
        payload["category"] = {
            "id": category["id"],
            "title": category["page_title"],
            "description": category["description"],
            "rss": f"{PUBLIC_BASE_URL}/{category['rss_path']}",
            "page": f"{PUBLIC_BASE_URL}/{category['page_path'].removesuffix('/index.html')}/",
        }
    write_text_if_changed(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def category_payload(category: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": category["id"],
        "title": category["page_title"],
        "shortTitle": category["short_title"],
        "description": category["description"],
        "page": f"/{category['page_path'].removesuffix('/index.html')}/",
        "rss": f"/{category['rss_path']}",
        "json": f"/{category['json_path']}",
        "items": items,
        "count": len(items),
    }


def write_feed_data_js(public_rows: list[dict[str, Any]], categorized: dict[str, list[dict[str, Any]]], window_days: int) -> None:
    social_sources = public_social_sources()
    payload = {
        "generatedAt": dt.datetime.now(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M"),
        "updatesWindowDays": window_days,
        "updates": public_rows,
        "socialSources": social_sources,
        "feeds": [
            category_payload(category, categorized.get(category["id"], []))
            for category in FEED_CATEGORIES
        ],
    }
    FEED_DATA_JS.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(FEED_DATA_JS, "window.HARMONICA_OBSERVE_FEEDS = "
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + ";\n")


def api_category_payload(category: dict[str, str], items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "id": category["id"],
        "title": category["page_title"],
        "shortTitle": category["short_title"],
        "description": category["description"],
        "page": f"{PUBLIC_BASE_URL}{feed_page_url(category)}",
        "rss": f"{PUBLIC_BASE_URL}/{category['rss_path']}",
        "json": f"{PUBLIC_BASE_URL}/api/{category['id']}.json",
        "sourceJson": f"{PUBLIC_BASE_URL}/{category['json_path']}",
        "count": len(items),
        "items": items,
    }


def write_api_files(public_rows: list[dict[str, Any]], categorized: dict[str, list[dict[str, Any]]], window_days: int) -> None:
    API_DIR.mkdir(parents=True, exist_ok=True)
    social_sources = public_social_sources()
    feeds = [
        api_category_payload(category, categorized.get(category["id"], []))
        for category in FEED_CATEGORIES
    ]
    catalog = [
        {
            "id": feed["id"],
            "title": feed["title"],
            "shortTitle": feed["shortTitle"],
            "description": feed["description"],
            "page": feed["page"],
            "rss": feed["rss"],
            "json": feed["json"],
            "count": feed["count"],
        }
        for feed in feeds
    ]
    payload = {
        "generatedAt": dt.datetime.now(TAIPEI_TZ).isoformat(),
        "updatesWindowDays": window_days,
        "site": PUBLIC_BASE_URL,
        "updates": public_rows,
        "socialSources": social_sources,
        "feeds": feeds,
    }
    write_text_if_changed(API_DIR / "latest.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    write_text_if_changed(API_DIR / "catalog.json", json.dumps({"site": PUBLIC_BASE_URL, "feeds": catalog}, ensure_ascii=False, indent=2) + "\n")
    for feed in feeds:
        write_text_if_changed(API_DIR / f"{feed['id']}.json", json.dumps(feed, ensure_ascii=False, indent=2) + "\n")


def write_update_rss(path: Path, title: str, description: str, link: str, items: list[dict[str, Any]]) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    rss = build_channel(title, description, link)
    channel = rss.find("channel")
    assert channel is not None

    for item in items:
        add_update_item(channel, item)
    if not items:
        add_text(channel, "pubDate", email.utils.format_datetime(now))

    write_xml(path, rss)


def filter_recent_candidate_rows(rows: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    if days <= 0:
        return rows
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    recent_rows: list[dict[str, Any]] = []
    for row in rows:
        timestamp = parse_time(str(row.get("posted_at") or row.get("seen_at") or ""))
        if timestamp and timestamp >= cutoff:
            recent_rows.append(row)
    return recent_rows


def generate_updates(
    window_days: int = DEFAULT_UPDATE_WINDOW_DAYS,
    limit: int | None = None,
    profile_source_ids: list[str] | None = None,
    profile_avatar_sources: dict[str, str] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    global SOURCE_PROFILE_BY_ID, SOURCE_PROFILE_BY_ACCOUNT, DIRECTORY_ENTRY_BY_KEY
    all_rows = read_candidate_rows()
    rows = filter_recent_candidate_rows(all_rows, window_days)
    profile_rows = [
        row for row in all_rows if row.get("raw_source") != "public-link-backfill"
    ]
    SOURCE_PROFILE_BY_ID = build_source_profiles(profile_rows, profile_source_ids, profile_avatar_sources)
    SOURCE_PROFILE_BY_ACCOUNT = source_profiles_by_account()
    DIRECTORY_ENTRY_BY_KEY = directory_entry_lookup()
    public_rows = build_update_items(rows, limit)
    persist_source_profiles(SOURCE_PROFILE_BY_ID)
    write_update_rss(
        UPDATES_OUT,
        "Harmonica Observatory · 口琴觀測站：公開更新",
        "公開口琴活動、貼文與資訊候選更新。",
        f"{PUBLIC_BASE_URL}/feeds/",
        public_rows,
    )
    write_update_json(UPDATES_JSON_OUT, public_rows)

    categorized: dict[str, list[dict[str, Any]]] = {}
    for category in FEED_CATEGORIES:
        items = build_update_items(rows, limit, category["id"])
        categorized[category["id"]] = items
        write_update_rss(
            SITE_ROOT / category["rss_path"],
            category["title"],
            category["description"],
            f"{PUBLIC_BASE_URL}/{category['page_path'].removesuffix('/index.html')}/",
            items,
        )
        write_update_json(SITE_ROOT / category["json_path"], items, category)

    write_feed_data_js(public_rows, categorized, window_days)
    write_api_files(public_rows, categorized, window_days)
    write_feed_pages(categorized)
    write_homepage_latest(public_rows, categorized, window_days)
    return public_rows, categorized


def html_escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def html_lines(value: Any) -> str:
    lines = str(value or "").splitlines()
    if not lines:
        return ""
    return "<br>".join(html_escape(line) for line in lines)


def html_line_list(lines: list[str]) -> str:
    return "<br>".join(html_escape(line) for line in lines if line)


def home_text_lines(value: Any, skip_first: bool = False) -> list[str]:
    lines = [line.strip() for line in str(value or "").strip().splitlines() if line.strip()]
    if skip_first:
        lines = lines[1:]
    return lines


def normalize_source_url(value: Any) -> str:
    text = re.sub(r"[)\]\}>,，。；;.!！?？]+$", "", str(value or "").strip())
    if not text:
        return ""
    parsed = urllib.parse.urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        return text.rstrip("/").casefold()
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return f"{host}{path}{parsed.query and '?' + parsed.query}".casefold()


def line_is_source_link(line: Any, item: dict[str, Any]) -> bool:
    text = str(line or "").strip()
    if not re.fullmatch(r"https?://\S+", text, flags=re.IGNORECASE):
        return False
    source_url = normalize_source_url(item.get("link"))
    if source_url and normalize_source_url(text) == source_url:
        return True
    if str(item.get("platform") or "").strip().casefold() != "facebook":
        return False
    parsed = urllib.parse.urlsplit(text)
    host = parsed.netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    return host == "facebook.com" and (
        path == "/photo"
        or path == "/permalink.php"
        or path.startswith("/reel/")
        or path.startswith("/share/")
        or "/posts/" in path
    )


def normalized_duplicate_line(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.…]+$", "", str(value or ""))).strip()


def trim_leading_duplicate_summary_line(lines: list[str]) -> list[str]:
    if len(lines) < 2:
        return lines
    first = normalized_duplicate_line(lines[0])
    second = normalized_duplicate_line(lines[1])
    if not first or not second:
        return lines
    first_looks_truncated = bool(re.search(r"(?:\.{3}|…)\s*$", lines[0]))
    if first == second or (first_looks_truncated and second.startswith(first)):
        return lines[1:]
    return lines


def display_text_lines(item: dict[str, Any], skip_first: bool = False) -> list[str]:
    lines = home_text_lines(item.get("text"), skip_first=False)
    while lines and line_is_source_link(lines[-1], item):
        lines.pop()
    if skip_first:
        return lines[1:]
    return trim_leading_duplicate_summary_line(lines)


def normalize_compare_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def html_text_with_breaks(value: Any, emphasize_first_line: bool = False) -> str:
    lines = [line.strip() for line in str(value or "").splitlines() if line.strip()]
    if not lines:
        return ""
    if not emphasize_first_line:
        return html_escape("\n".join(lines)).replace("\n", "<br>")
    first_line, *rest = lines
    rest_html = f"<br>{html_escape(chr(10).join(rest)).replace(chr(10), '<br>')}" if rest else ""
    return f'<strong class="feed-caption-lead">{html_escape(first_line)}</strong>{rest_html}'


def home_feed_text_id(item: dict[str, Any], index: int) -> str:
    raw_key = str(item.get("key") or item.get("link") or item.get("source") or "item")
    key = re.sub(r"[^A-Za-z0-9_-]+", "-", raw_key).strip("-")[:48] or "item"
    return f"feed-text-{index}-{key}"


def render_home_text_block(item: dict[str, Any], index: int, display_title: str = "") -> str:
    has_display_title = bool(str(display_title or "").strip())
    full_text = "\n".join(display_text_lines(item, skip_first=False))
    if not full_text:
        return ""
    collapsed_text = compact_multiline("\n".join(display_text_lines(item, skip_first=has_display_title)), 260)
    collapsed_text = "\n".join(line for line in collapsed_text.splitlines()[:4] if line.strip())
    visible_text = "\n".join(text for text in [display_title, collapsed_text] if text)
    expandable = normalize_compare_text(full_text) != normalize_compare_text(visible_text)
    collapsed_html = html_text_with_breaks(collapsed_text, emphasize_first_line=not has_display_title)
    if not collapsed_html and not expandable:
        return ""
    if not expandable:
        return f'<span class="feed-latest-excerpt">{collapsed_html}</span>'
    text_id = home_feed_text_id(item, index)
    full_html = html_text_with_breaks(full_text, emphasize_first_line=not has_display_title)
    return f"""
          <span class="feed-latest-excerpt" id="{html_escape(text_id)}">
            <span data-feed-text-collapsed>{collapsed_html}</span>
            <span data-feed-text-expanded hidden>{full_html}</span>
          </span>
          <button class="feed-text-toggle" type="button" data-feed-text-toggle aria-expanded="false" aria-controls="{html_escape(text_id)}">查看更多</button>
    """


def render_keyword_pills(keywords: list[str]) -> str:
    if not keywords:
        return ""
    return "".join(f'<span class="pill">{html_escape(keyword)}</span>' for keyword in keywords[:6])


def render_home_tag_pills(item: dict[str, Any]) -> str:
    keywords = list(item.get("matched_keywords") or [])[:5]
    return "".join(
        f'<button type="button" class="pill feed-tag-pill feed-option-chip" '
        f'data-feed-tag="{html_escape(keyword)}" aria-pressed="false" data-filter-state="off">'
        f'{html_escape(keyword)}</button>'
        for keyword in keywords
    )


def format_engagement_number(value: Any) -> str:
    count = parse_engagement_count(value)
    if count is None:
        return ""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}".removesuffix(".0") + "M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}".removesuffix(".0") + "K"
    return f"{count:,}"


def render_home_engagement(item: dict[str, Any]) -> str:
    parts = []
    like_count = parse_engagement_count(item.get("like_count"))
    reaction_count = parse_engagement_count(item.get("reaction_count"))
    for field, label in (
        ("view_count", "瀏覽"),
        ("like_count", "按讚"),
        ("comment_count", "留言"),
        ("share_count", "分享"),
        ("reaction_count", "互動"),
    ):
        if field == "reaction_count" and reaction_count is not None and reaction_count == like_count:
            continue
        value = format_engagement_number(item.get(field))
        if value:
            parts.append(f'<span class="feed-engagement-item" title="{label}量">{label} {html_escape(value)}</span>')
    if not parts:
        return ""
    return f'<span class="feed-engagement">{"".join(parts)}</span>'


def image_dimension_attrs(item: dict[str, Any]) -> str:
    width = parse_engagement_count(item.get("image_width"))
    height = parse_engagement_count(item.get("image_height"))
    if not width or not height:
        return ""
    return f' style="--feed-image-aspect: {width} / {height}"'


def image_size_attrs(item: dict[str, Any]) -> str:
    width = parse_engagement_count(item.get("image_width"))
    height = parse_engagement_count(item.get("image_height"))
    if not width or not height:
        return ""
    return f' width="{width}" height="{height}"'


def render_source_avatar(item: dict[str, Any], class_name: str = "source-avatar") -> str:
    avatar = item.get("avatar_url")
    source = item.get("source") or "公開來源"
    initials = item.get("source_initials") or source_initials(str(source))
    if avatar:
        return (
            f'<span class="{class_name}">'
            f'<img src="{html_escape(avatar)}" alt="{html_escape(source)} 頭貼" loading="lazy" referrerpolicy="no-referrer">'
            "</span>"
        )
    return f'<span class="{class_name} source-avatar-fallback" aria-hidden="true">{html_escape(initials)}</span>'


def render_source_identity(item: dict[str, Any], class_name: str = "source-avatar", meta_class: str = "feed-latest-meta") -> str:
    source = item.get("source") or "公開來源"
    platform = item.get("platform_label") or item.get("platform") or "public"
    meta = f"{item.get('posted_at_local') or '未標示'} · {platform}"
    body = (
        f'{render_source_avatar(item, class_name)}'
        "<div>"
        f'<span class="{meta_class}">{html_escape(meta)}</span>'
        f"<strong>{html_escape(source)}</strong>"
        "</div>"
    )
    profile_url = str(item.get("source_profile_url") or "").strip()
    if profile_url:
        return (
            f'<a class="source-identity-link" href="{html_escape(profile_url)}" '
            f'target="_blank" rel="noreferrer" aria-label="開啟 {html_escape(source)} 個人首頁">'
            f"{body}</a>"
        )
    return body


PLATFORM_BADGE_LABELS = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "rss": "RSS",
    "threads": "Threads",
    "x": "X",
    "youtube": "YouTube",
    "public": "Public",
}


def platform_key_from_text(value: Any) -> str:
    text = str(value or "").casefold()
    if not text:
        return ""
    if "facebook" in text or "facebook.com" in text or re.search(r"(^|[\s/_-])fb($|[\s/_-])", text):
        return "facebook"
    if "instagram" in text or "instagram.com" in text or re.search(r"(^|[\s/_-])ig($|[\s/_-])", text):
        return "instagram"
    if "threads" in text or "threads.net" in text:
        return "threads"
    if "youtube" in text or "youtu.be" in text or re.search(r"(^|[\s/_-])yt($|[\s/_-])", text):
        return "youtube"
    if "twitter" in text or "x.com/" in text or re.search(r"(^|[\s/_-])x($|[\s/_-])", text):
        return "x"
    if "rss" in text or "atom" in text or "feed.xml" in text:
        return "rss"
    return ""


def feed_platform_badge_key(item: dict[str, Any]) -> str:
    explicit_platform = " ".join(str(item.get(field) or "") for field in ("platform", "platform_label"))
    platform_key = platform_key_from_text(explicit_platform)
    if platform_key:
        return platform_key
    source_hints = " ".join(
        str(item.get(field) or "")
        for field in ("type", "source_type", "source_id", "source_profile_url", "link")
    )
    return platform_key_from_text(source_hints) or "public"


def platform_icon_svg(key: str) -> str:
    if key == "facebook":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M14 13.5H16.5L17.5 9.5H14V7.5C14 6.47062 14 5.5 16 5.5H17.5V2.1401C17.1743 2.09685 15.943 2 14.6429 2C11.9284 2 10 3.65686 10 6.69971V9.5H7V13.5H10V22H14V13.5Z"/></svg>'
    if key == "instagram":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.001 9C10.3436 9 9.00098 10.3431 9.00098 12C9.00098 13.6573 10.3441 15 12.001 15C13.6583 15 15.001 13.6569 15.001 12C15.001 10.3427 13.6579 9 12.001 9ZM12.001 7C14.7614 7 17.001 9.2371 17.001 12C17.001 14.7605 14.7639 17 12.001 17C9.24051 17 7.00098 14.7629 7.00098 12C7.00098 9.23953 9.23808 7 12.001 7ZM18.501 6.74915C18.501 7.43926 17.9402 7.99917 17.251 7.99917C16.5609 7.99917 16.001 7.4384 16.001 6.74915C16.001 6.0599 16.5617 5.5 17.251 5.5C17.9393 5.49913 18.501 6.0599 18.501 6.74915ZM12.001 4C9.5265 4 9.12318 4.00655 7.97227 4.0578C7.18815 4.09461 6.66253 4.20007 6.17416 4.38967C5.74016 4.55799 5.42709 4.75898 5.09352 5.09255C4.75867 5.4274 4.55804 5.73963 4.3904 6.17383C4.20036 6.66332 4.09493 7.18811 4.05878 7.97115C4.00703 9.0752 4.00098 9.46105 4.00098 12C4.00098 14.4745 4.00753 14.8778 4.05877 16.0286C4.0956 16.8124 4.2012 17.3388 4.39034 17.826C4.5591 18.2606 4.7605 18.5744 5.09246 18.9064C5.42863 19.2421 5.74179 19.4434 6.17187 19.6094C6.66619 19.8005 7.19148 19.9061 7.97212 19.9422C9.07618 19.9939 9.46203 20 12.001 20C14.4755 20 14.8788 19.9934 16.0296 19.9422C16.8117 19.9055 17.3385 19.7996 17.827 19.6106C18.2604 19.4423 18.5752 19.2402 18.9074 18.9085C19.2436 18.5718 19.4445 18.2594 19.6107 17.8283C19.8013 17.3358 19.9071 16.8098 19.9432 16.0289C19.9949 14.9248 20.001 14.5389 20.001 12C20.001 9.52552 19.9944 9.12221 19.9432 7.97137C19.9064 7.18906 19.8005 6.66149 19.6113 6.17318C19.4434 5.74038 19.2417 5.42635 18.9084 5.09255C18.573 4.75715 18.2616 4.55693 17.8271 4.38942C17.338 4.19954 16.8124 4.09396 16.0298 4.05781C14.9258 4.00605 14.5399 4 12.001 4ZM12.001 2C14.7176 2 15.0568 2.01 16.1235 2.06C17.1876 2.10917 17.9135 2.2775 18.551 2.525C19.2101 2.77917 19.7668 3.1225 20.3226 3.67833C20.8776 4.23417 21.221 4.7925 21.476 5.45C21.7226 6.08667 21.891 6.81333 21.941 7.8775C21.9885 8.94417 22.001 9.28333 22.001 12C22.001 14.7167 21.991 15.0558 21.941 16.1225C21.8918 17.1867 21.7226 17.9125 21.476 18.55C21.2218 19.2092 20.8776 19.7658 20.3226 20.3217C19.7668 20.8767 19.2076 21.22 18.551 21.475C17.9135 21.7217 17.1876 21.89 16.1235 21.94C15.0568 21.9875 14.7176 22 12.001 22C9.28431 22 8.94514 21.99 7.87848 21.94C6.81431 21.8908 6.08931 21.7217 5.45098 21.475C4.79264 21.2208 4.23514 20.8767 3.67931 20.3217C3.12348 19.7658 2.78098 19.2067 2.52598 18.55C2.27848 17.9125 2.11098 17.1867 2.06098 16.1225C2.01348 15.0558 2.00098 14.7167 2.00098 12C2.00098 9.28333 2.01098 8.94417 2.06098 7.8775C2.11014 6.8125 2.27848 6.0875 2.52598 5.45C2.78014 4.79167 3.12348 4.23417 3.67931 3.67833C4.23514 3.1225 4.79348 2.78 5.45098 2.525C6.08848 2.2775 6.81348 2.11 7.87848 2.06C8.94514 2.0125 9.28431 2 12.001 2Z"/></svg>'
    if key == "threads":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.1835 1.41016L12.1822 1.41016C9.09012 1.43158 6.70036 2.47326 5.09369 4.51569C3.66581 6.33087 2.93472 8.86436 2.91016 12.0068V12.0082C2.93472 15.1508 3.66586 17.6696 5.09369 19.4847C6.70043 21.5271 9.10257 22.5688 12.1946 22.5902H12.1958C14.944 22.5711 16.8929 21.8504 18.4985 20.2463C20.6034 18.1434 20.5408 15.5048 19.8456 13.8832C19.3163 12.6493 18.2709 11.6618 16.8701 11.0477C16.6891 8.06345 15.0097 6.32178 12.2496 6.30415C10.6191 6.29409 9.14792 7.02378 8.24685 8.39104L9.90238 9.5267C10.4353 8.71818 11.2789 8.32815 12.2371 8.33701C13.6244 8.34586 14.5362 9.11128 14.7921 10.4541C14.02 10.3333 13.1902 10.2982 12.3076 10.3488C9.66843 10.5008 7.9399 12.061 8.05516 14.2244C8.17571 16.4862 10.367 17.7186 12.4476 17.605C14.9399 17.4684 16.4209 15.6292 16.7722 13.2836C17.3493 13.6575 17.7751 14.1344 18.0163 14.6969C18.4559 15.7222 18.4838 17.4132 17.1006 18.7952C15.8838 20.0108 14.4211 20.5407 12.1891 20.5572C9.71428 20.5388 7.85698 19.746 6.65154 18.2136C5.51973 16.7748 4.92843 14.6882 4.90627 12.0002C4.92843 9.31211 5.51973 7.22549 6.65154 5.78673C7.85698 4.25433 9.71424 3.46156 12.189 3.44303C14.6819 3.4617 16.5728 4.25837 17.8254 5.79937C18.5162 6.64934 18.949 7.66539 19.2379 8.71407L21.1776 8.19656C20.8148 6.85917 20.2414 5.58371 19.363 4.50305C17.7098 2.46918 15.2816 1.43166 12.1835 1.41016ZM12.4204 12.3782C13.3044 12.3272 14.1239 12.3834 14.8521 12.5345C14.7114 14.1116 14.0589 15.4806 12.3401 15.575C11.2282 15.6376 10.1031 15.1413 10.0484 14.114C10.0077 13.3503 10.5726 12.4847 12.4204 12.3782Z"/></svg>'
    if key == "youtube":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12.2439 4C12.778 4.00294 14.1143 4.01586 15.5341 4.07273L16.0375 4.09468C17.467 4.16236 18.8953 4.27798 19.6037 4.4755C20.5486 4.74095 21.2913 5.5155 21.5423 6.49732C21.942 8.05641 21.992 11.0994 21.9982 11.8358L21.9991 11.9884L21.9991 11.9991C21.9991 11.9991 21.9991 12.0028 21.9991 12.0099L21.9982 12.1625C21.992 12.8989 21.942 15.9419 21.5423 17.501C21.2878 18.4864 20.5451 19.261 19.6037 19.5228C18.8953 19.7203 17.467 19.8359 16.0375 19.9036L15.5341 19.9255C14.1143 19.9824 12.778 19.9953 12.2439 19.9983L12.0095 19.9991L11.9991 19.9991C11.9991 19.9991 11.9956 19.9991 11.9887 19.9991L11.7545 19.9983C10.6241 19.9921 5.89772 19.941 4.39451 19.5228C3.4496 19.2573 2.70692 18.4828 2.45587 17.501C2.0562 15.9419 2.00624 12.8989 2 12.1625V11.8358C2.00624 11.0994 2.0562 8.05641 2.45587 6.49732C2.7104 5.51186 3.45308 4.73732 4.39451 4.4755C5.89772 4.05723 10.6241 4.00622 11.7545 4H12.2439ZM9.99911 8.49914V15.4991L15.9991 11.9991L9.99911 8.49914Z"/></svg>'
    if key == "x":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M10.4883 14.651L15.25 21H22.25L14.3917 10.5223L20.9308 3H18.2808L13.1643 8.88578L8.75 3H1.75L9.26086 13.0145L2.31915 21H4.96917L10.4883 14.651ZM16.25 19L5.75 5H7.75L18.25 19H16.25Z"/></svg>'
    if key == "rss":
        return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M3 17C5.20914 17 7 18.7909 7 21H3V17ZM3 10C9.07513 10 14 14.9249 14 21H12C12 16.0294 7.97056 12 3 12V10ZM3 3C12.9411 3 21 11.0589 21 21H19C19 12.1634 11.8366 5 3 5V3Z"/></svg>'
    return '<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false"><circle class="platform-icon-stroke" cx="12" cy="12" r="7"/><path class="platform-icon-stroke" d="M5 12h14M12 5c2 2 3 4.3 3 7s-1 5-3 7M12 5c-2 2-3 4.3-3 7s1 5 3 7"/></svg>'


def render_platform_badge(item: dict[str, Any]) -> str:
    key = feed_platform_badge_key(item)
    label = PLATFORM_BADGE_LABELS.get(key) or source_platform_label(
        item.get("platform_label") or item.get("platform") or key
    )
    return (
        f'<span class="platform-badge platform-badge-{html_escape(key)}" role="img" '
        f'aria-label="{html_escape(label)}" title="{html_escape(label)}">'
        f'{platform_icon_svg(key)}'
        f'<span class="sr-only">{html_escape(label)}</span>'
        "</span>"
    )

def render_home_feed_item(item: dict[str, Any], index: int = 0) -> str:
    display_title = homepage_display_title(item)
    image = item.get("image_url")
    thumb_html = (
        f'<span class="home-feed-thumb"{image_dimension_attrs(item)}><img src="{html_escape(image)}" alt="{html_escape(item.get("source", ""))} 貼文圖片" loading="lazy" referrerpolicy="no-referrer"{image_size_attrs(item)}></span>'
        if image
        else ""
    )
    body_classes = [
        "home-feed-body",
        "" if thumb_html else "home-feed-body-no-image",
        "" if display_title else "home-feed-body-no-title",
    ]
    body_class = " ".join(class_name for class_name in body_classes if class_name)
    text_block = render_home_text_block(item, index, display_title)
    tag_html = render_home_tag_pills(item)
    engagement_html = render_home_engagement(item)
    meta_html = f'<div class="entry-meta">{tag_html}{engagement_html}</div>' if tag_html or engagement_html else ""
    title_html = f'<h3 class="home-feed-title">{html_escape(display_title)}</h3>' if display_title else ""
    report_context = "\n".join(
        value
        for value in (
            f"來源：{item.get('source') or '未標示'}",
            f"平台：{item.get('platform_label') or item.get('platform') or '未標示'}",
            f"發布時間：{item.get('posted_at_local') or item.get('posted_at') or '未標示'}",
            f"目前標籤：{'、'.join(item.get('matched_keywords') or [])}" if item.get("matched_keywords") else "",
            "請確認這則公開更新的來源、分類與顯示內容；若包含活動，也請確認日期、地點與日曆資訊。",
        )
        if value
    )
    report_href = report_links.report_url(
        "correct",
        name="｜".join(value for value in (item.get("source"), display_title) if value) or "公開更新",
        source=item.get("link"),
        page=item.get("report_page") or "/post/",
        desired=report_context,
    )
    return f"""
      <article class="home-feed-card">
        <div class="home-feed-source">
          <div class="home-feed-source-main">
            {render_source_identity(item)}
          </div>
          {render_platform_badge(item)}
        </div>
        <div class="{body_class}">
          {title_html}
          {thumb_html}
          {text_block}
        </div>
        <div class="home-feed-footer">
          {meta_html}
          <div class="feed-card-links">
            <a class="context-report-link" href="{html_escape(report_href)}">回報這筆資料</a>
            <a class="feed-open-link" href="{html_escape(item.get("link"))}" target="_blank" rel="noreferrer">開啟來源</a>
          </div>
        </div>
      </article>
    """


def render_home_filter_chip_options(
    values: list[str],
    data_name: str,
    fallback_label: str,
    active_values: list[str] | tuple[str, ...] | None = None,
) -> str:
    active_keys = {normalize_taiwan_orthography(value).strip().casefold() for value in (active_values or [])}
    all_state = "off" if active_keys else "include"
    all_pressed = "false" if active_keys else "true"
    chips = [
        f'<button type="button" class="feed-option-chip" data-feed-{html_escape(data_name)}="all" aria-pressed="{all_pressed}" data-filter-state="{all_state}">{html_escape(fallback_label)}</button>'
    ]
    for value in values:
        active = normalize_taiwan_orthography(value).strip().casefold() in active_keys
        state = "include" if active else "off"
        pressed = "true" if active else "false"
        chips.append(
            f'<button type="button" class="feed-option-chip" data-feed-{html_escape(data_name)}="{html_escape(value)}" aria-pressed="{pressed}" data-filter-state="{state}">{html_escape(value)}</button>'
        )
    return "".join(chips)


def source_platform_label(platform: Any) -> str:
    value = str(platform or "").strip()
    if not value:
        return "public"
    lowered = value.casefold()
    if lowered == "facebook":
        return "Facebook"
    if lowered == "instagram":
        return "Instagram"
    if lowered == "rss":
        return "RSS"
    if lowered == "threads":
        return "Threads"
    if lowered == "x":
        return "X"
    if lowered == "youtube":
        return "YouTube"
    return value


def homepage_title_kind(item: dict[str, Any]) -> str:
    explicit_kind = str(item.get("title_kind") or "").strip().casefold()
    if explicit_kind:
        return explicit_kind
    if is_instagram_story_item(item):
        return "caption"
    platform = str(item.get("platform") or "").strip().casefold()
    if platform in SOCIAL_CAPTION_PLATFORMS:
        return "caption"
    return "title"


def homepage_display_title(item: dict[str, Any]) -> str:
    explicit_title = str(item.get("display_title") or "").strip()
    if explicit_title:
        return explicit_title
    if homepage_title_kind(item) != "title":
        return ""
    return str(item.get("headline") or item.get("rsshub_title") or "").strip()


def platform_filter_sort_key(label: str) -> tuple[int, str]:
    value = str(label or "").strip()
    return (PLATFORM_FILTER_RANK.get(value.casefold(), len(PLATFORM_FILTER_ORDER)), value.casefold())


def source_kind_labels(source: dict[str, Any]) -> list[str]:
    labels = {source_platform_label(source.get("platform") or source.get("type"))}
    if str(source.get("type") or "").casefold() == "rss":
        labels.add("RSS")
    if str(source.get("type") or "").casefold() == "rsshub_instagram_story":
        labels.add("Instagram story")
    return sorted(labels)


def is_instagram_story_item(item: dict[str, Any]) -> bool:
    story_flag = item.get("story") is True or str(item.get("story") or "").casefold() == "true"
    return (
        story_flag
        or str(item.get("media_type") or "").casefold() == "instagram_story"
        or str(item.get("platform_label") or "").casefold() == "instagram story"
    )


def homepage_feed_rows(public_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [item for item in public_rows if not is_instagram_story_item(item)]


def homepage_default_feed_rows(public_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    country_keys = {country.casefold() for country in HOME_FEED_DEFAULT_COUNTRIES}
    tag_keys = {tag.casefold() for tag in HOME_FEED_DEFAULT_TAGS}
    rows: list[dict[str, Any]] = []
    for item in public_rows:
        countries = {value.casefold() for value in feed_country_filter_values(item)}
        tags = {
            value.casefold()
            for value in public_tags.normalize_tag_values(item.get("matched_keywords") or [], limit=20)
        }
        if country_keys and not countries.intersection(country_keys):
            continue
        if tag_keys and not tags.intersection(tag_keys):
            continue
        rows.append(item)
    return rows


def feed_source_filter_label(item: dict[str, Any]) -> str:
    for value in (
        item.get("directory_entry_name"),
        item.get("source"),
        item.get("source_system_name"),
        str(item.get("account") or "").removeprefix("@"),
        item.get("source_id"),
    ):
        label = normalize_taiwan_orthography(value or "").strip()
        if label:
            return label
    return ""


def split_location_filter_values(value: Any) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for part in LOCATION_VALUE_SPLIT_RE.split(str(value or "")):
        label = normalize_taiwan_orthography(part).strip()
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels


def feed_country_filter_values(item: dict[str, Any]) -> list[str]:
    country = normalize_taiwan_orthography(item.get("country") or "").strip()
    if not country or country in NON_LOCATION_LABELS:
        return []
    return [country]


def feed_known_country_values(items: list[dict[str, Any]]) -> list[str]:
    countries: list[str] = []
    seen: set[str] = set()
    for item in items:
        for country in feed_country_filter_values(item):
            key = country.casefold()
            if key in seen:
                continue
            seen.add(key)
            countries.append(country)
    return countries


def directory_country_values() -> list[str]:
    countries: list[str] = []
    seen: set[str] = set()
    try:
        entries = parse_site_data(SITE_DATA).get("entries", [])
    except (OSError, json.JSONDecodeError):
        entries = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        country = normalize_taiwan_orthography(entry.get("country") or "").strip()
        key = country.casefold()
        if not country or country in NON_LOCATION_LABELS or key in seen:
            continue
        seen.add(key)
        countries.append(country)
    return countries


def feed_region_filter_values(item: dict[str, Any], country_values: list[str]) -> list[str]:
    countries = {
        country.casefold()
        for country in [*country_values, *feed_country_filter_values(item)]
        if country
    }
    regions: list[str] = []
    seen: set[str] = set()
    for region in split_location_filter_values(item.get("region")):
        key = region.casefold()
        if region in NON_LOCATION_LABELS or key in countries or key in seen:
            continue
        seen.add(key)
        regions.append(region)
    return regions


def counted_filter_values(items: list[dict[str, Any]], field: str, country_values: list[str] | None = None) -> list[str]:
    counts: dict[str, int] = {}
    for item in items:
        if field == "source":
            values = [feed_source_filter_label(item)]
        elif field == "country":
            values = feed_country_filter_values(item)
        elif field == "region":
            values = feed_region_filter_values(item, country_values or feed_known_country_values(items))
        else:
            values = [normalize_taiwan_orthography(item.get(field) or "").strip()]
        for value in values:
            if value:
                counts[value] = counts.get(value, 0) + 1
    return [
        value
        for value, _count in sorted(
            counts.items(),
            key=lambda pair: (-pair[1], pair[0]),
        )
    ]


def render_home_feed_filters(
    public_rows: list[dict[str, Any]],
    window_days: int,
    filtered_rows: list[dict[str, Any]] | None = None,
) -> str:
    filtered_rows = public_rows if filtered_rows is None else filtered_rows
    platform_values: set[str] = set()
    for item in public_rows:
        for field in ("platform", "platform_label"):
            platform_label = source_platform_label(item.get(field))
            if platform_label and platform_label not in {"public", "Instagram story"}:
                platform_values.add(platform_label)
    for source in public_social_sources():
        for platform_label in source_kind_labels(source):
            if platform_label and platform_label not in {"public", "Instagram story"}:
                platform_values.add(platform_label)
    platforms = sorted(platform_values, key=platform_filter_sort_key)
    sources = counted_filter_values(public_rows, "source")
    countries = counted_filter_values(public_rows, "country")
    country_values = [*directory_country_values(), *feed_known_country_values(public_rows)]
    regions = counted_filter_values(public_rows, "region", country_values)
    tags = public_tags.sort_public_tags(
        keyword for item in public_rows for keyword in (item.get("matched_keywords") or [])
    )
    return f"""
      <div class="feed-river-controls">
        <div class="feed-river-summary">
          <p class="feed-filter-label">河道篩選</p>
          <strong>最近 {window_days} 天 · {len(filtered_rows)} / {len(public_rows)} 筆</strong>
        </div>
        <div class="feed-filter-tools">
          <label class="search-field feed-search-field">
            <span class="sr-only">搜尋河道</span>
            <input id="feed-search-input" type="search" placeholder="搜尋標題、內文、國家、區域、tag 或來源">
          </label>
          <button class="feed-reset-button" type="button">重設</button>
        </div>
        <div class="feed-filter-chip-group">
          <span class="feed-chip-group-label">平台</span>
          <div class="feed-option-chips" aria-label="平台篩選，可複選">{render_home_filter_chip_options(platforms, "platform", "全部平台")}</div>
        </div>
        <div class="feed-filter-chip-group">
          <span class="feed-chip-group-label">國家</span>
          <div class="feed-option-chips" aria-label="國家篩選，可複選">{render_home_filter_chip_options(countries, "country", "全部國家", HOME_FEED_DEFAULT_COUNTRIES)}</div>
        </div>
        <div class="feed-filter-chip-group">
          <span class="feed-chip-group-label">區域</span>
          <div class="feed-option-chips" aria-label="區域篩選，可複選">{render_home_filter_chip_options(regions, "region", "全部區域")}</div>
        </div>
        <div class="feed-filter-chip-group">
          <span class="feed-chip-group-label">Tag</span>
          <div class="feed-option-chips" aria-label="Tag 篩選，可複選">{render_home_filter_chip_options(tags, "tag", "全部 tag", HOME_FEED_DEFAULT_TAGS)}</div>
        </div>
        <details class="feed-filter-chip-group feed-filter-disclosure" data-feed-source-disclosure>
          <summary>
            <span class="feed-chip-group-label">來源</span>
            <span class="feed-disclosure-count">{len(sources)} 個來源</span>
          </summary>
          <div class="feed-option-chips" aria-label="來源篩選，可複選">{render_home_filter_chip_options(sources, "source", "全部來源")}</div>
        </details>
      </div>
    """


def render_home_feed_load_more(total: int, visible: int) -> str:
    if not total or visible >= total:
        return ""
    return f"""
      <div class="feed-load-more-wrap">
        <span class="feed-load-more-status">已顯示 {visible} / {total} 筆</span>
        <button class="feed-load-more-button" type="button">載入更多</button>
      </div>
    """


def estimate_home_feed_height(item: dict[str, Any]) -> int:
    text = " ".join(
        str(value or "")
        for value in [
            item.get("headline"),
            item.get("display_title"),
            item.get("title"),
            item.get("source"),
            item.get("excerpt"),
            " ".join(item.get("matched_keywords") or []),
        ]
    )
    media_weight = 120 if item.get("image_url") else 0
    return 230 + media_weight + min(180, len(text) // 3)


def render_home_feed_columns(rows: list[dict[str, Any]], column_count: int = 3) -> str:
    if not rows:
        return '<div class="empty-state">目前沒有近期待觀測項目。</div>'
    columns: list[list[tuple[int, dict[str, Any]]]] = [[] for _ in range(column_count)]
    heights = [0] * column_count
    for item_index, item in enumerate(rows):
        column_index = min(range(column_count), key=lambda index: heights[index])
        columns[column_index].append((item_index, item))
        heights[column_index] += estimate_home_feed_height(item)
    rendered_columns = []
    for index, column_rows in enumerate(columns, start=1):
        column_html = "\n".join(render_home_feed_item(item, item_index) for item_index, item in column_rows)
        rendered_columns.append(
            f'      <div class="feed-river-column" data-feed-column="{index}">\n'
            f"{column_html}\n"
            "      </div>"
        )
    return "\n".join(rendered_columns)


def render_pagination_nav(current_page: int, total_pages: int) -> str:
    links = []

    if current_page > 1:
        prev_url = "/post/" if current_page == 2 else f"/post/page/{current_page - 1}/"
        links.append(f'<a href="{prev_url}" class="pagination-prev" style="padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: var(--primary, #1a73e8);">上一頁</a>')

    start_p = max(1, current_page - 2)
    end_p = min(total_pages, current_page + 2)

    if start_p > 1:
        links.append('<a href="/post/" style="padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: var(--primary, #1a73e8);">1</a>')
        if start_p > 2:
            links.append('<span style="padding: 6px 12px; color: #666;">...</span>')

    for p in range(start_p, end_p + 1):
        if p == current_page:
            links.append(f'<span class="pagination-current" style="padding: 6px 12px; background: var(--primary, #1a73e8); color: white; border-radius: 4px; font-weight: bold;">{p}</span>')
        else:
            url = "/post/" if p == 1 else f"/post/page/{p}/"
            links.append(f'<a href="{url}" style="padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: var(--primary, #1a73e8);">{p}</a>')

    if end_p < total_pages:
        if end_p < total_pages - 1:
            links.append('<span style="padding: 6px 12px; color: #666;">...</span>')
        links.append(f'<a href="/post/page/{total_pages}/" style="padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: var(--primary, #1a73e8);">{total_pages}</a>')

    if current_page < total_pages:
        next_url = f"/post/page/{current_page + 1}/"
        links.append(f'<a href="{next_url}" class="pagination-next" style="padding: 6px 12px; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: var(--primary, #1a73e8);">下一頁</a>')

    nav_links = " ".join(links)
    return f"""
      <nav class="feed-pagination-wrap" aria-label="分頁導覽" style="display: flex; justify-content: center; align-items: center; gap: 8px; margin-top: 2.5rem; margin-bottom: 2rem; flex-wrap: wrap;">
        <span class="pagination-status" style="font-size: 0.95rem; color: #666; margin-right: 10px;">第 {current_page} / {total_pages} 頁</span>
        {nav_links}
      </nav>
"""


def modernize_submission_links(page: str) -> str:
    updated = page.replace(
        "請先看回報頁整理需要準備的公開來源，再送出 GitHub 表單。",
        "請從內容旁的「回報這筆資料」開始，或直接開啟免登入的 Google 表單。",
    ).replace(
        '<a href="https://github.com/skyhong2002/Harmonica-in-Taiwan/issues" target="_blank" rel="noreferrer">查看處理中的回報</a>',
        '<a href="/submit/?kind=add-source">新增來源或頻道</a>',
    )
    updated = site_chrome.replace_site_headers(updated)
    nav_anchor = '        <a href="/status/">狀態</a>'
    nav_with_report = f'{nav_anchor}\n        <a href="/submit/">資料回報</a>'
    if nav_anchor in updated and nav_with_report not in updated:
        updated = updated.replace(nav_anchor, nav_with_report, 1)
    return updated


def write_homepage_latest(public_rows: list[dict[str, Any]], categorized: dict[str, list[dict[str, Any]]], window_days: int) -> None:
    start = "            <!-- FEED_LATEST_START -->"
    end = "            <!-- FEED_LATEST_END -->"
    public_rows = homepage_feed_rows(public_rows)
    filtered_rows = homepage_default_feed_rows(public_rows)
    visible_rows = filtered_rows[:HOME_FEED_BATCH_SIZE]

    total_posts = len(filtered_rows)
    total_pages = (total_posts + HOME_FEED_BATCH_SIZE - 1) // HOME_FEED_BATCH_SIZE

    # 1. Update site/index.html
    latest_html_home = (
        render_home_feed_filters(public_rows, window_days, filtered_rows)
        + f'\n      <div class="feed-river">\n{render_home_feed_columns(visible_rows)}\n      </div>'
        + render_home_feed_load_more(len(filtered_rows), len(visible_rows))
    )
    latest_html_home = "\n".join(line.rstrip() for line in latest_html_home.splitlines())
    if HOME_PAGE.exists():
        text = HOME_PAGE.read_text(encoding="utf-8")
        if start in text and end in text:
            before, rest = text.split(start, 1)
            _, after = rest.split(end, 1)
            write_text_if_changed(HOME_PAGE, modernize_submission_links(f"{before}{start}\n{latest_html_home}\n            {end}{after}"))

    # 2. Update site/post/index.html
    pagination_nav_p1 = render_pagination_nav(1, total_pages)
    latest_html_post = (
        render_home_feed_filters(public_rows, window_days, filtered_rows)
        + f'\n      <div class="feed-river">\n{render_home_feed_columns(visible_rows)}\n      </div>'
        + render_home_feed_load_more(len(filtered_rows), len(visible_rows))
        + pagination_nav_p1
    )
    latest_html_post = "\n".join(line.rstrip() for line in latest_html_post.splitlines())

    posts_page = SITE_ROOT / "post" / "index.html"
    if posts_page.exists():
        text = posts_page.read_text(encoding="utf-8")
        if start in text and end in text:
            before, rest = text.split(start, 1)
            _, after = rest.split(end, 1)
            write_text_if_changed(posts_page, modernize_submission_links(f"{before}{start}\n{latest_html_post}\n            {end}{after}"))

    # 3. Generate static pagination pages for 2, 3, etc.
    pagination_root = SITE_ROOT / "post" / "page"
    if pagination_root.exists():
        for stale_dir in pagination_root.iterdir():
            if stale_dir.is_dir() and stale_dir.name.isdigit() and int(stale_dir.name) > total_pages:
                shutil.rmtree(stale_dir)
    for p in range(2, total_pages + 1):
        page_dir = SITE_ROOT / "post" / "page" / str(p)
        page_dir.mkdir(parents=True, exist_ok=True)

        visible_rows_p = filtered_rows[(p-1)*HOME_FEED_BATCH_SIZE : p*HOME_FEED_BATCH_SIZE]
        pagination_nav_p = render_pagination_nav(p, total_pages)

        latest_html_p = (
            render_home_feed_filters(public_rows, window_days, filtered_rows)
            + f'\n      <div class="feed-river">\n{render_home_feed_columns(visible_rows_p)}\n      </div>'
            + f'\n      <div class="feed-load-more-wrap">\n        <span class="feed-load-more-status">已顯示 {min(p*HOME_FEED_BATCH_SIZE, total_posts)} / {total_posts} 筆</span>\n      </div>'
            + pagination_nav_p
        )
        latest_html_p = "\n".join(line.rstrip() for line in latest_html_p.splitlines())

        baseline_text = modernize_submission_links(posts_page.read_text(encoding="utf-8"))
        baseline_text = baseline_text.replace(
            '<link rel="canonical" href="https://harmonica.observe.tw/post/">',
            f'<link rel="canonical" href="https://harmonica.observe.tw/post/page/{p}/">'
        )

        if start in baseline_text and end in baseline_text:
            before, rest = baseline_text.split(start, 1)
            _, after = rest.split(end, 1)
            write_text_if_changed(page_dir / "index.html", f"{before}{start}\n{latest_html_p}\n            {end}{after}")


def render_update_cards(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<div class="empty-state">目前沒有符合這個分類的近期待觀測項目。</div>'

    cards = []
    for item in items:
        keywords = render_keyword_pills(list(item.get("matched_keywords") or []))
        image = item.get("image_url")
        display_text = html_line_list(display_text_lines(item))
        image_html = (
            f"""
              <a class="feed-item-image" href="{html_escape(item.get("link"))}" target="_blank" rel="noreferrer">
                <img src="{html_escape(image)}" alt="{html_escape(item.get("source", ""))} 貼文圖片" loading="lazy" referrerpolicy="no-referrer">
              </a>
            """
            if image
            else ""
        )
        report_href = report_links.report_url(
            "correct",
            name="｜".join(
                value
                for value in (item.get("source"), item.get("headline") or item.get("title"))
                if value
            ),
            source=item.get("link"),
            page="/post/",
            desired="請確認這則公開更新的來源、分類與顯示內容；若包含活動，也請確認日期、地點與日曆資訊。",
        )
        cards.append(
            f"""
            <article class="feed-item-card">
              {image_html}
              <div class="feed-item-main">
                <div class="feed-item-source">
                  {render_source_identity(item, "source-avatar source-avatar-small", "feed-item-meta")}
                </div>
                <h2>{html_escape(item.get("headline") or item.get("title"))}</h2>
                <p class="feed-item-text">{display_text}</p>
              </div>
              <div class="feed-item-actions">
                <div class="entry-meta">{keywords}</div>
                <div class="feed-card-links">
                  <a class="context-report-link" href="{html_escape(report_href)}">回報這筆資料</a>
                  <a class="primary-link" href="{html_escape(item.get("link"))}" target="_blank" rel="noreferrer">開啟來源</a>
                </div>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def feed_page_url(category: dict[str, str]) -> str:
    return f"/{category['page_path'].removesuffix('/index.html')}/"


def render_feed_category_card(category: dict[str, str], count: int) -> str:
    return f"""
      <article class="feed-category-card">
        <div>
          <p class="section-kicker">{html_escape(category["id"])}</p>
          <h2>{html_escape(category["page_title"])}</h2>
          <p>{html_escape(category["page_intro"])}</p>
        </div>
        <div class="feed-card-actions">
          <span class="pill">{count} 筆</span>
          <a href="{html_escape(feed_page_url(category))}">網頁版</a>
          <a href="/{html_escape(category["rss_path"])}">RSS</a>
        </div>
      </article>
    """


def render_feed_page(category: dict[str, str], items: list[dict[str, Any]]) -> str:
    rss_url = f"/{category['rss_path']}"
    json_url = f"/{category['json_path']}"
    return f"""<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html_escape(category["page_title"])}｜臺灣口琴觀測站</title>
    <meta name="description" content="{html_escape(category["description"])}">
    <link rel="icon" href="/assets/favicon-20260623.svg?v={ASSET_VERSION}" type="image/svg+xml">
    <link rel="alternate" type="application/rss+xml" title="{html_escape(category["title"])}" href="{html_escape(rss_url)}">
    <link rel="stylesheet" href="/assets/styles.css?v={ASSET_VERSION}">
  </head>
  <body>
{site_chrome.render_header()}

    <main class="feed-page-main">
      <section class="feed-page-hero">
        <div class="band-inner split-layout">
          <div>
            <p class="section-kicker">Hermes RSS</p>
            <h1>{html_escape(category["page_title"])}</h1>
          </div>
          <div class="feed-page-summary">
            <p>{html_escape(category["page_intro"])}</p>
            <div class="feed-links">
              <a href="{html_escape(rss_url)}">RSS 訂閱</a>
              <a href="{html_escape(json_url)}">JSON</a>
              <a href="/feeds/">全部分類</a>
            </div>
          </div>
        </div>
      </section>

      <section class="band">
        <div class="band-inner">
          <div class="section-heading">
            <div>
              <p class="section-kicker">Latest</p>
              <h2>目前項目</h2>
            </div>
            <p class="data-date">{len(items)} 筆</p>
          </div>
          <div class="feed-item-list">
            {render_update_cards(items)}
          </div>
        </div>
      </section>
    </main>

    {FOOTER_HTML}
  </body>
</html>
"""


def render_feed_index(categorized: dict[str, list[dict[str, Any]]]) -> str:
    cards = "\n".join(
        render_feed_category_card(category, len(categorized.get(category["id"], [])))
        for category in FEED_CATEGORIES
    )
    return f"""<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>RSS 訂閱｜臺灣口琴觀測站</title>
    <meta name="description" content="訂閱臺灣口琴觀測站的公開更新 RSS：口琴公開活動、貼文與影片發布、學生社團動態、補助與比賽資訊，另提供 JSON 版本。">
    <link rel="canonical" href="https://harmonica.observe.tw/feeds/">
    <link rel="icon" href="/assets/favicon-20260623.svg?v={ASSET_VERSION}" type="image/svg+xml">
    <link rel="alternate" type="application/rss+xml" title="臺灣口琴觀測站公開更新" href="/feeds/updates.xml">
    <link rel="stylesheet" href="/assets/styles.css?v={ASSET_VERSION}">
  </head>
  <body>
{site_chrome.render_header()}

    <main class="feed-page-main">
      <section class="feed-page-hero">
        <div class="band-inner split-layout">
          <div>
            <p class="section-kicker">RSS</p>
            <h1>公開更新</h1>
          </div>
          <div class="feed-page-summary">
            <p>臺灣口琴觀測站每天整理公開口琴資訊，分成四條 RSS：公開活動、貼文與影片發布、學生社團動態、補助與比賽資訊。用任何 RSS 閱讀器訂閱，或改抓同名的 JSON 檔。</p>
            <div class="feed-links">
              <a href="/feeds/updates.xml">總更新 RSS</a>
              <a href="/feeds/sources.xml">來源索引 RSS</a>
            </div>
          </div>
        </div>
      </section>

      <section class="band">
        <div class="band-inner feed-category-grid">
          {cards}
        </div>
      </section>
    </main>

    {FOOTER_HTML}
  </body>
</html>
"""


def write_feed_pages(categorized: dict[str, list[dict[str, Any]]]) -> None:
    FEED_INDEX_OUT.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(FEED_INDEX_OUT, render_feed_index(categorized))
    catalog = []
    for category in FEED_CATEGORIES:
        page = SITE_ROOT / category["page_path"]
        page.parent.mkdir(parents=True, exist_ok=True)
        items = categorized.get(category["id"], [])
        write_text_if_changed(page, render_feed_page(category, items))
        catalog.append(
            {
                "id": category["id"],
                "title": category["page_title"],
                "description": category["description"],
                "page": f"{PUBLIC_BASE_URL}{feed_page_url(category)}",
                "rss": f"{PUBLIC_BASE_URL}/{category['rss_path']}",
                "json": f"{PUBLIC_BASE_URL}/{category['json_path']}",
                "items": len(items),
            }
        )
    write_text_if_changed(CATALOG_JSON_OUT, json.dumps({"feeds": catalog}, ensure_ascii=False, indent=2) + "\n")


def bump_html_asset_versions() -> None:
    for path in SITE_ROOT.rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        updated = site_chrome.normalize_document(text)
        updated = "\n".join(line.rstrip() for line in updated.splitlines()) + "\n"
        if updated != text:
            write_text_if_changed(path, updated)


def generate_sources(limit: int) -> int:
    data = parse_site_data(SITE_DATA)
    all_entries = data.get("entries", [])
    entries = all_entries[:limit] if limit and limit > 0 else all_entries
    now = dt.datetime.now(dt.timezone.utc)
    rss = build_channel(
        "Harmonica Observatory · 口琴觀測站：來源索引",
        "公開口琴社團、團體、演奏者、教學與場館的來源索引。",
        f"{PUBLIC_BASE_URL}/#directory",
    )
    channel = rss.find("channel")
    assert channel is not None

    for entry in entries:
        name = str(entry.get("name") or "公開來源")
        links = entry.get("links") or []
        first_link = links[0].get("url") if links and isinstance(links[0], dict) else f"{PUBLIC_BASE_URL}/#directory"
        item = ET.SubElement(channel, "item")
        add_text(item, "title", name)
        add_text(item, "link", str(first_link))
        add_text(item, "guid", item_guid("sources", name + str(first_link)))
        add_text(item, "pubDate", rss_time(str(data.get("generatedAt") or ""), now))
        summary = compact(str(entry.get("summary") or entry.get("type") or ""), 500)
        source_tags = "、".join(str(tag) for tag in (entry.get("sourceTags") or []) if str(tag).strip())
        description = "\n".join(
            part
            for part in [
                f"分類：{entry.get('category') or '未分類'}",
                f"Tag：{source_tags}" if source_tags else "",
                f"國家：{entry.get('country') or '未標示'}",
                f"地區：{entry.get('region') or '未標示'}",
                "",
                summary,
            ]
            if part != ""
        )
        add_text(item, "description", html.escape(description))

    write_xml(SOURCES_OUT, rss)
    API_DIR.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(API_DIR / "sources.json", json.dumps(
            {
                "site": PUBLIC_BASE_URL,
                "generatedAt": data.get("generatedAt") or "",
                "count": len(entries),
                "stats": data.get("stats") or {},
                "entries": entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n")
    return len(entries)


def main() -> int:
    global OFFLINE
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Use cached profile/media data only; never fetch remote resources.")
    parser.add_argument("--updates-days", type=int, default=DEFAULT_UPDATE_WINDOW_DAYS)
    parser.add_argument("--updates-limit", type=int, default=0)
    parser.add_argument("--sources-limit", type=int, default=0)
    parser.add_argument(
        "--profile-source-id",
        action="append",
        default=[],
        help="Fetch and cache profile metadata/avatar for this configured source ID; repeat as needed.",
    )
    parser.add_argument(
        "--profile-avatar-source",
        action="append",
        default=[],
        metavar="SOURCE_ID=URL",
        help="Cache an explicitly verified avatar URL for a configured source; repeat as needed.",
    )
    args = parser.parse_args()
    OFFLINE = args.offline

    avatar_source_overrides: dict[str, str] = {}
    for value in args.profile_avatar_source:
        source_id, separator, avatar_url = value.partition("=")
        if not separator or not source_id.strip() or not avatar_url.strip():
            parser.error("--profile-avatar-source must use SOURCE_ID=URL")
        avatar_source_overrides[source_id.strip()] = avatar_url.strip()

    updates, categorized = generate_updates(
        args.updates_days,
        args.updates_limit,
        args.profile_source_id,
        avatar_source_overrides,
    )
    sources_count = generate_sources(args.sources_limit)
    bump_html_asset_versions()
    print(
        json.dumps(
            {
                "updates": len(updates),
                "updates_window_days": args.updates_days,
                "updates_limit": args.updates_limit or None,
                "categorized_updates": {
                    category["id"]: len(categorized.get(category["id"], []))
                    for category in FEED_CATEGORIES
                },
                "sources": sources_count,
                "updates_feed": str(UPDATES_OUT),
                "sources_feed": str(SOURCES_OUT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
