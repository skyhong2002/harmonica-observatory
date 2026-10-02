#!/usr/bin/env python3
"""Build structured public calendar event candidates from public feed posts."""

from __future__ import annotations

import datetime as dt
import argparse
import csv
import hashlib
import json
import re
import os
import sys
from pathlib import Path
from typing import Any

import llm_backend
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import social_feed_watchdog as watchdog


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
API_DIR = SITE_ROOT / "api"
DATA_DIR = SITE_ROOT / "data"
FEEDS_DIR = SITE_ROOT / "feeds"
SOURCE_PATH = API_DIR / "events.json"
SOCIAL_CANDIDATES_PATH = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
OVERRIDES_PATH = PROJECT_ROOT / "data" / "sources" / "harmonica-public-calendar-overrides.csv"
JSON_PATH = API_DIR / "public-calendar-events.json"
JS_PATH = DATA_DIR / "public-calendar-events.js"
ICS_PATH = FEEDS_DIR / "public-calendar.ics"
OVERSEAS_JSON_PATH = API_DIR / "overseas-calendar-events.json"
ONLINE_JSON_PATH = API_DIR / "online-calendar-events.json"
OVERSEAS_ICS_PATH = FEEDS_DIR / "overseas-calendar.ics"
ONLINE_ICS_PATH = FEEDS_DIR / "online-calendar.ics"
TIMEZONE = "Asia/Taipei"
TAIWAN_TZ = dt.timezone(dt.timedelta(hours=8))
DEFAULT_LLM_CACHE = PROJECT_ROOT / "state" / "public_calendar_llm_events.json"
CALENDAR_REVIEW_POLICY_VERSION = 6
TAIWAN_PHYSICAL = "taiwan_physical"
OVERSEAS_PHYSICAL = "overseas_physical"
ONLINE = "online"
EVENT_MODES = {TAIWAN_PHYSICAL, OVERSEAS_PHYSICAL, ONLINE}
SUBMITTED_PLATFORM = "public-form"
COUNTRY_TIMEZONES = {
    "台灣": "Asia/Taipei",
    "臺灣": "Asia/Taipei",
    "Taiwan": "Asia/Taipei",
    "日本": "Asia/Tokyo",
    "Japan": "Asia/Tokyo",
    "香港": "Asia/Hong_Kong",
    "Hong Kong": "Asia/Hong_Kong",
    "新加坡": "Asia/Singapore",
    "Singapore": "Asia/Singapore",
    "馬來西亞": "Asia/Kuala_Lumpur",
    "Malaysia": "Asia/Kuala_Lumpur",
    "韓國": "Asia/Seoul",
    "南韓": "Asia/Seoul",
    "South Korea": "Asia/Seoul",
    "中國": "Asia/Shanghai",
    "China": "Asia/Shanghai",
}
PLACE_COUNTRIES = {
    "日本": "日本",
    "東京": "日本",
    "東京都": "日本",
    "大阪": "日本",
    "和歌山": "日本",
    "名古屋": "日本",
    "橫濱": "日本",
    "横浜": "日本",
    "Yokohama": "日本",
    "Japan": "日本",
    "Tokyo": "日本",
    "Osaka": "日本",
    "香港": "香港",
    "Hong Kong": "香港",
    "新加坡": "新加坡",
    "Singapore": "新加坡",
    "馬來西亞": "馬來西亞",
    "Malaysia": "馬來西亞",
    "韓國": "韓國",
    "South Korea": "韓國",
    "中國": "中國",
    "中国": "中國",
    "江陰": "中國",
    "江阴": "中國",
    "China": "中國",
}

HARMONICA_TERMS = [
    "口琴",
    "harmonica",
    "ハーモニカ",
    "クロマチック",
    "複音",
    "半音階",
]

EVENT_TERMS = [
    "演出",
    "音樂會",
    "音乐会",
    "公演",
    "成發",
    "成果展",
    "講座",
    "工作坊",
    "音樂節",
    "音楽祭",
    "concert",
    "recital",
    "live",
    "festival",
    "コンサート",
    "ライブ",
    "開演",
    "開場",
    "場次",
    "活動時間",
    "日時",
    "論壇",
    "论坛",
    "forum",
    "webinar",
]

DATE_RANGE_RE = re.compile(
    r"(?P<left>(?:\d{2,4}[./-])?\d{1,2}\s*(?:[./-]|月)\s*\d{1,2}\s*(?:日)?)"
    r"\s*(?:→|~|～|〜|–|-|至|到)\s*"
    r"(?P<right>(?:\d{2,4}[./-])?\d{1,2}\s*(?:[./-]|月)\s*\d{1,2}\s*(?:日)?)"
)
FULL_DATE_RE = re.compile(r"(?P<year>\d{2,4})\s*(?:年|[./-])\s*(?P<month>\d{1,2})\s*(?:月|[./-])\s*(?P<day>\d{1,2})\s*(?:日)?")
MONTH_DAY_RE = re.compile(r"(?<!\d)(?P<month>\d{1,2})\s*(?:月|[./])\s*(?P<day>\d{1,2})\s*(?:日)?(?!\d)")
SLASH_DATE_RE = re.compile(r"(?<!\d)(?P<first>\d{1,2})\s*/\s*(?P<second>\d{1,2})(?!\d)")
ENGLISH_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_ENGLISH_MONTH_PART = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
ENGLISH_DATE_RE = re.compile(
    r"(?<![A-Za-z\d])(?:"
    rf"(?P<day_first>\d{{1,2}})(?:st|nd|rd|th)?\s+(?P<month_after>{_ENGLISH_MONTH_PART})"
    r"|"
    rf"(?P<month_before>{_ENGLISH_MONTH_PART})\.?\s+(?P<day_second>\d{{1,2}})(?:st|nd|rd|th)?"
    r")"
    r"(?:,?\s*(?P<year>\d{4}))?(?![A-Za-z\d])",
    re.IGNORECASE,
)
COMPACT_RANGE_RE = re.compile(r"(?<!\d)(?P<year>\d{2})(?P<month>\d{2})(?P<day>\d{2})\s*[-~〜]\s*(?P<end_month>\d{2})(?P<end_day>\d{2})(?!\d)")
TIME_RE = re.compile(r"(?<!\d)(?P<hour>[01]?\d|2[0-3])[:：](?P<minute>[0-5]\d)(?!\d)")
AMPM_TIME_RE = re.compile(
    r"(?<!\d)(?P<hour>1[0-2]|0?[1-9])(?:[:：](?P<minute>[0-5]\d))?\s*(?P<ampm>[AaPp])\.?[Mm]\b"
)
TIME_WITH_UNIT_RE = re.compile(r"(?P<prefix>上午|早上|中午|下午|晚上|夜|午前|午後)?\s*(?P<hour>[01]?\d|2[0-3])\s*(?:時|点|點)(?:\s*(?P<minute>[0-5]\d)\s*分?)?")
CHINESE_TIME_RE = re.compile(
    r"(?P<prefix>上午|早上|中午|下午|晚上|夜)?\s*"
    r"(?P<hour>[一二兩三四五六七八九十]{1,3})\s*(?:點|時)(?P<half>半)?(?!點)"
)
LOCATION_RE = re.compile(r"(?:地點|地点|場地|會場|会場|場所|上課地點|活動地點|舉辦地點)\s*[｜|:：]?\s*(?P<place>[^\n。；;，,]{2,48})")
PIN_LOCATION_RE = re.compile(
    r"📍\s*(?!時間|时间|日期|日時|日时|\d{1,4}\s*[./-])"
    r"(?P<place>[^\n。；;，,]{2,48})"
)
NARRATIVE_LOCATION_RE = re.compile(
    r"(?:在|於(?!\s*(?:\d{1,4}\s*(?:年|[./-])|\d{1,2}\s*月)))\s*"
    r"(?P<place>[^\n。；;，,]{2,80}?)"
    r"(?=(?:熱鬧)?(?:登場|舉行|舉辦|開演|展開))"
)
TAIWAN_PLACE_RE = re.compile(
    r"台灣|臺灣|台北|臺北|新北|基隆|桃園|新竹|苗栗|台中|臺中|彰化|南投|雲林|嘉義|台南|臺南|高雄|屏東|宜蘭|花蓮|台東|臺東|澎湖|金門|馬祖|陽明交通大學|陽明交大|衛武營|武陵|臺北生技園區|台北生技園區|大墩文化中心"
)
OVERSEAS_PLACE_RE = re.compile(
    r"日本|東京|東京都|大阪|和歌山|名古屋|香港|新加坡|Singapore|Japan|Tokyo|Osaka|Hong Kong|Malaysia|馬來西亞|恵比寿|BLUE NOTE PLACE|アーク栄"
)
ONLINE_EVENT_RE = re.compile(r"線上|直播|live\s*stream|livestream|streaming|online|YouTube\s*Live|IG\s*Live|Facebook\s*Live|zoom|webinar|google\s*meet", re.IGNORECASE)
ONLINE_PLATFORM_LABEL_RE = re.compile(
    r"(?:platform|平台|平臺)\s*[｜|:：]\s*(?:facebook|youtube|instagram|ig|zoom|google\s*meet|線上|直播)",
    re.IGNORECASE,
)
NON_LIVE_ONLINE_RE = re.compile(r"回顧|重播|隨選|archive|archived|アーカイブ|配信中|影片發布|影片回放", re.IGNORECASE)
ONLINE_LOGISTICS_RE = re.compile(
    r"(?:線上|網路|online\s+)(?:報名|購票|登記|申請|registration|tickets?)",
    re.IGNORECASE,
)
GENERIC_ONLINE_VENUE_RE = re.compile(r"^(?:線上|線上直播|網路直播|online|livestream)$", re.IGNORECASE)
GENERIC_COUNTRY_VENUE_RE = re.compile(r"^(?:台灣|臺灣|Taiwan|其他國家/地區|其他國家地區)$", re.IGNORECASE)
CANCELLED_EVENT_RE = re.compile(r"停辦|取消(?:活動|演出|場次|音樂會|音乐会|公演|講座|工作坊)?|中止|開催中止", re.IGNORECASE)
NON_EVENT_ANNOUNCEMENT_RE = re.compile(r"服務異動|門市服務時間|暫停(?:門市|營業|服務)", re.IGNORECASE)


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


def parse_datetime(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", text):
        text = text.replace(" ", "T") + ":00+08:00"
    try:
        parsed = dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = dt.datetime.strptime(text, "%a, %d %b %Y %H:%M:%S %Z").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TAIWAN_TZ)
    return parsed.astimezone(TAIWAN_TZ)


def normalized_year(year: int, reference_year: int) -> int:
    if year < 100:
        return 2000 + year
    if 100 <= year < 200:
        return year + 1911
    if year < 1000:
        return reference_year
    return year


def safe_date(year: int, month: int, day: int) -> dt.date | None:
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def infer_month_day(month: int, day: int, posted_at: dt.datetime | None) -> dt.date | None:
    reference = posted_at.date() if posted_at else dt.datetime.now(TAIWAN_TZ).date()
    candidate = safe_date(reference.year, month, day)
    if candidate is None:
        return None
    if candidate < reference - dt.timedelta(days=45):
        next_year = safe_date(reference.year + 1, month, day)
        return next_year or candidate
    return candidate


def english_date_from_match(match: re.Match, posted_at: dt.datetime | None) -> dt.date | None:
    month_name = (match.group("month_after") or match.group("month_before") or "")[:3].lower()
    month = ENGLISH_MONTHS.get(month_name)
    day_raw = match.group("day_first") or match.group("day_second")
    if not month or not day_raw:
        return None
    day = int(day_raw)
    year_raw = match.group("year")
    if year_raw:
        return safe_date(normalized_year(int(year_raw), (posted_at or dt.datetime.now(TAIWAN_TZ)).year), month, day)
    return infer_month_day(month, day, posted_at)


def parse_loose_date(
    text: str,
    posted_at: dt.datetime | None,
    *,
    slash_day_first: bool = False,
) -> dt.date | None:
    cleaned = text.strip().replace(" ", "")
    full = FULL_DATE_RE.search(cleaned)
    if full:
        year = normalized_year(int(full.group("year")), (posted_at or dt.datetime.now(TAIWAN_TZ)).year)
        return safe_date(year, int(full.group("month")), int(full.group("day")))
    slash = re.fullmatch(r"(?P<first>\d{1,2})/(?P<second>\d{1,2})", cleaned)
    if slash and slash_day_first:
        return infer_month_day(int(slash.group("second")), int(slash.group("first")), posted_at)
    month_day = MONTH_DAY_RE.search(cleaned)
    if month_day:
        return infer_month_day(int(month_day.group("month")), int(month_day.group("day")), posted_at)
    english = ENGLISH_DATE_RE.search(text.strip())
    if english:
        return english_date_from_match(english, posted_at)
    return None


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "是"}


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    overrides: dict[str, dict[str, Any]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            evidence_url = (row.get("evidence_url") or "").strip()
            if not evidence_url:
                continue
            start = (row.get("start") or "").strip()
            end = (row.get("end") or "").strip()
            event_name = (row.get("event_name") or "").strip()
            venue = (row.get("venue") or "").strip()
            city = (row.get("city") or "").strip()
            country = (row.get("country") or "臺灣").strip()
            mode = (row.get("event_mode") or "").strip() or classify_event_mode(
                country, f"{event_name} {venue} {city}"
            )
            timezone = valid_timezone(row.get("timezone")) or infer_timezone(country)
            if not start or not event_name or not venue:
                continue
            overrides[evidence_url] = {
                "sourceName": (row.get("source_name") or "").strip(),
                "platform": (row.get("platform") or "website").strip(),
                "eventName": event_name,
                "title": event_name,
                "start": start,
                "end": end or start,
                "allDay": truthy(row.get("all_day")),
                "venue": venue,
                "city": city,
                "location": venue if not city or city in venue else f"{city} {venue}",
                "details": (row.get("details") or "").strip(),
                "calendarType": mode,
                "timezone": timezone,
                "evidenceUrl": evidence_url,
                "confidence": 1.0,
                "calendarReview": {
                    "include": True,
                    "country": country,
                    "eventMode": mode,
                    "timezone": timezone,
                    "candidateDateMatches": True,
                    "eventName": event_name,
                    "venue": venue,
                    "city": city,
                    "details": (row.get("details") or "").strip(),
                    "reason": "manual override from public calendar overrides CSV",
                    "confidence": 1.0,
                },
            }
    return overrides


def text_has_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def is_online_event_text(text: str) -> bool:
    event_text = ONLINE_LOGISTICS_RE.sub("", text)
    if NON_LIVE_ONLINE_RE.search(event_text):
        return False
    return bool(ONLINE_EVENT_RE.search(event_text)) or bool(ONLINE_PLATFORM_LABEL_RE.search(event_text))


def valid_timezone(value: Any) -> str:
    timezone = str(value or "").strip()
    if not timezone:
        return ""
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return ""
    return timezone


def infer_timezone(country: str) -> str:
    return COUNTRY_TIMEZONES.get(str(country or "").strip(), "")


def infer_country(text: str) -> str:
    for marker, country in PLACE_COUNTRIES.items():
        if marker.casefold() in text.casefold():
            return country
    return ""


def classify_event_mode(country: str, text: str, requested_mode: str = "") -> str:
    country = str(country or "").strip()
    requested_mode = str(requested_mode or "").strip()
    has_taiwan_place = bool(TAIWAN_PLACE_RE.search(text))
    has_overseas_place = bool(OVERSEAS_PLACE_RE.search(text))
    is_taiwan = country in {"台灣", "臺灣", "Taiwan"} or has_taiwan_place
    is_online = country == "線上" or is_online_event_text(text)
    is_overseas = bool(country and country not in {"台灣", "臺灣", "Taiwan", "線上"}) or bool(
        has_overseas_place
    )
    if requested_mode == ONLINE and is_online:
        return ONLINE
    if country == "線上" and is_online:
        return ONLINE
    if requested_mode == OVERSEAS_PHYSICAL and is_overseas and not is_taiwan:
        return OVERSEAS_PHYSICAL
    if requested_mode == TAIWAN_PHYSICAL and is_taiwan and not is_overseas:
        return TAIWAN_PHYSICAL
    if has_overseas_place and not has_taiwan_place:
        return OVERSEAS_PHYSICAL
    if country and country not in {"台灣", "臺灣", "Taiwan", "線上"}:
        return OVERSEAS_PHYSICAL
    if country in {"台灣", "臺灣", "Taiwan"}:
        return TAIWAN_PHYSICAL
    if is_overseas:
        return OVERSEAS_PHYSICAL
    if is_taiwan:
        return TAIWAN_PHYSICAL
    if is_online:
        return ONLINE
    return ""


def review_event_modes(country: str, text: str) -> tuple[bool, bool]:
    mode = classify_event_mode(country, text)
    return mode == ONLINE, mode == TAIWAN_PHYSICAL


def nearby_context(text: str, start: int, end: int, radius: int = 60) -> str:
    return text[max(0, start - radius): min(len(text), end + radius)]


def line_context(text: str, start: int, end: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    return text[line_start:line_end].strip()


def schedule_line_context(text: str, start: int, end: int) -> str:
    """Keep only the current city segment when a caption line lists many dates."""
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    line = text[line_start:line_end]
    dates = list(SLASH_DATE_RE.finditer(line))
    if len(dates) < 2:
        return line.strip()
    relative_start = start - line_start
    current_index = next(
        (index for index, match in enumerate(dates) if match.start() <= relative_start < match.end()),
        0,
    )
    segment_start = dates[current_index].start()
    segment_end = dates[current_index + 1].start() if current_index + 1 < len(dates) else len(line)
    return line[segment_start:segment_end].strip(" ,;|")


TOUR_SCHEDULE_PLACES = (
    ("Hong Kong", "香港", "香港", "Asia/Hong_Kong"),
    ("Taipei", "臺北市", "臺北", "Asia/Taipei"),
    ("Singapore", "Singapore", "Singapore", "Asia/Singapore"),
    ("Penang", "檳城", "Penang", "Asia/Kuala_Lumpur"),
    ("Seoul", "首爾", "Seoul", "Asia/Seoul"),
)


def tour_schedule_place(text: str) -> tuple[str, str, str, str] | None:
    lowered = text.casefold()
    for marker, country, city, timezone in TOUR_SCHEDULE_PLACES:
        if marker.casefold() in lowered:
            return country, city, city, timezone
    return None


def is_explicit_tour_schedule(item: dict[str, Any], context: str) -> bool:
    text = f"{item.get('title') or ''}\n{item.get('text') or ''}"
    return bool(re.search(r"\b(?:asia\s+)?tour\b|巡演|巡迴", text, re.IGNORECASE)) and bool(
        tour_schedule_place(context)
    )


def tour_schedule_review(item: dict[str, Any], title: str, start: str, context: str) -> dict[str, Any] | None:
    place = tour_schedule_place(context)
    if not place or not is_explicit_tour_schedule(item, context):
        return None
    country, city, venue, timezone = place
    event_name = tour_schedule_event_name(item, title)
    return {
        "include": True,
        "country": "臺灣" if country == "臺北市" else country,
        "eventMode": TAIWAN_PHYSICAL if country == "臺北市" else OVERSEAS_PHYSICAL,
        "timezone": timezone,
        "candidateDateMatches": True,
        "eventName": event_name,
        "venue": venue,
        "city": city,
        "details": f"亞洲巡演場次：{start[:10]}，地點為 {city}。貼文未提供更具體的場館或演出時間。",
        "reason": "貼文明確列出巡演日期與城市，收錄為該城市的全天活動。",
        "confidence": 0.9,
    }


def tour_schedule_event_name(item: dict[str, Any], fallback: str) -> str:
    text = str(item.get("text") or item.get("title") or "")
    match = re.search(r"「([^」]{2,80})」", text)
    if not match:
        return fallback
    return f"{event_source_label(item)}｜{match.group(1)} 亞洲巡演"


def date_match_is_truncated(text: str, end: int) -> bool:
    return bool(re.match(r"\s*(?:…|\\.\\.\\.)", text[end:end + 6]))


def extract_time(text: str) -> str:
    match = AMPM_TIME_RE.search(text)
    if match:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        if match.group("ampm").lower() == "p" and hour < 12:
            hour += 12
        elif match.group("ampm").lower() == "a" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"
    match = TIME_RE.search(text)
    if match:
        return f"{int(match.group('hour')):02d}:{match.group('minute')}"
    match = TIME_WITH_UNIT_RE.search(text)
    if match:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        prefix = match.group("prefix") or ""
        if prefix in {"下午", "晚上", "夜", "午後"} and hour < 12:
            hour += 12
        if prefix == "中午" and hour < 11:
            hour += 12
        return f"{hour:02d}:{minute:02d}"
    match = CHINESE_TIME_RE.search(text)
    if not match:
        return ""
    numerals = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    raw_hour = match.group("hour")
    if raw_hour == "十":
        hour = 10
    elif raw_hour.startswith("十"):
        hour = 10 + numerals.get(raw_hour[-1], 0)
    elif raw_hour.endswith("十"):
        hour = numerals.get(raw_hour[0], 0) * 10
    elif "十" in raw_hour:
        left, right = raw_hour.split("十", 1)
        hour = numerals.get(left, 0) * 10 + numerals.get(right, 0)
    else:
        hour = numerals.get(raw_hour, 0)
    if hour <= 0 or hour > 23:
        return ""
    prefix = match.group("prefix") or ""
    if prefix in {"下午", "晚上", "夜"} and hour < 12:
        hour += 12
    if prefix == "中午" and hour < 11:
        hour += 12
    minute = 30 if match.group("half") else 0
    return f"{hour:02d}:{minute:02d}"


def explicit_time_range(text: str) -> tuple[str, str] | None:
    """Recognize an announced range, not two unrelated clock times."""
    match = re.search(
        r"(?<![\d:：])(?P<h1>[01]?\d|2[0-3])[:：](?P<m1>[0-5]\d)\s*"
        r"(?P<p1>[ap]\.?m\.?)?\s*(?:～|〜|~|–|—|-|至|到|to)\s*"
        r"(?P<h2>[01]?\d|2[0-3])[:：](?P<m2>[0-5]\d)(?!\d)\s*(?P<p2>[ap]\.?m\.?)?",
        text, re.IGNORECASE,
    )
    if not match:
        return None
    prefix = re.search(r"(上午|早上|下午|晚上|午後|午前|오후|오전)\s*$", text[:match.start()])
    inferred = ('pm' if prefix[1] in {'下午', '晚上', '午後', '오후'} else 'am') if prefix else ''
    periods = [match['p1'] or match['p2'] or inferred, match['p2'] or match['p1'] or inferred]
    result = []
    for index, period in enumerate(periods, 1):
        hour = int(match[f'h{index}'])
        if period and 1 <= hour <= 12:
            hour = hour % 12 + (12 if period.lower().startswith('p') else 0)
        result.append(f"{hour:02d}:{match[f'm{index}']}")
    if not match['p1'] and match['p2'] and not inferred and int(match['h1']) <= 12 and int(match['h2']) <= 12:
        start_minutes = int(result[0][:2]) * 60 + int(result[0][3:])
        end_minutes = int(result[1][:2]) * 60 + int(result[1][3:])
        if (end_minutes - start_minutes) % (24 * 60) > 12 * 60:
            result[0] = f"{(int(result[0][:2]) + 12) % 24:02d}:{result[0][3:]}"
    return result[0], result[1]


def explicit_daily_candidates(text: str, posted_at: dt.datetime | None) -> list[tuple[dt.date, dt.date, str]]:
    """Expand only an explicit daily schedule with one bounded date range."""
    date_lines = [line for line in text.splitlines() if re.search(r"(?:【日期】|^\s*(?:日期|日程|Dates?)\s*[:：])", line, re.IGNORECASE)]
    time_lines = [line for line in text.splitlines() if re.search(r"(?:【時間】|^\s*(?:時間|时间|Time)\s*[:：])", line, re.IGNORECASE)]
    if len(date_lines) != 1 or len(time_lines) != 1:
        return []
    schedule_time = time_lines[0]
    if not re.search(r"每天|每晚|每日|毎日|매일|\bdaily\b|\bevery (?:day|evening|night)\b", schedule_time, re.IGNORECASE):
        return []
    if re.search(r"早餐|午餐|晚餐|住宿|營業|营业|breakfast|lunch|dinner|accommodation|opening hours", schedule_time, re.IGNORECASE):
        return []
    if not explicit_time_range(schedule_time) or len(TIME_RE.findall(schedule_time)) != 2:
        return []
    other_lines = "\n".join(line for line in text.splitlines() if line not in date_lines + time_lines)
    if FULL_DATE_RE.search(other_lines) or MONTH_DAY_RE.search(other_lines) or TIME_RE.search(other_lines):
        return []
    normalized = re.sub(r"[（(](?:[一二三四五六日天月火水木金土]|(?:星期|週)[一二三四五六日天]|Mon|Tue|Wed|Thu|Fri|Sat|Sun)[）)]", "", date_lines[0], flags=re.IGNORECASE)
    ranges = list(DATE_RANGE_RE.finditer(normalized))
    if len(ranges) != 1:
        return []
    start = parse_loose_date(ranges[0]['left'], posted_at)
    end = parse_loose_date(ranges[0]['right'], posted_at)
    if not start or not end or not 0 <= (end - start).days <= 14:
        return []
    return [(start + dt.timedelta(days=i), start + dt.timedelta(days=i), text)
            for i in range((end - start).days + 1)]


def clean_location(value: str) -> str:
    return re.sub(
        r"^(?:地點|地点|場地|會場|会場|場所|上課地點|活動地點|📍)\s*[｜|:：]?\s*",
        "",
        re.sub(r"\s+", " ", value),
    ).strip(" ｜|:：【】[]")


def extract_location(text: str) -> str:
    match = LOCATION_RE.search(text) or PIN_LOCATION_RE.search(text) or NARRATIVE_LOCATION_RE.search(text)
    if not match:
        return ""
    return clean_location(match.group("place"))


def event_title(item: dict[str, Any], context: str = "") -> str:
    source = str(item.get("source") or "").strip()
    text = str(item.get("text") or item.get("title") or "").strip()
    context_lines = [
        re.sub(r"^[^\w\u3040-\u30ff\u3400-\u9fff]+", "", part).strip()
        for part in context.splitlines()
        if part.strip()
    ]
    info_lines = [
        re.sub(r"(?:資訊|资讯|信息|案内)\s*$", "", line).rstrip("：: |｜")
        for line in context_lines
        if text_has_any(line, EVENT_TERMS)
        and re.search(r"(?:資訊|资讯|信息|案内)\s*$", line)
    ]
    if info_lines:
        core = max(info_lines, key=len)
    else:
        quoted = re.search(r"《([^》]{2,36})》", context or text)
        if quoted:
            core = f"《{quoted.group(1)}》"
        else:
            line = next((part.strip() for part in re.split(r"[\n。]", text) if part.strip()), "")
            core = re.sub(r"\s+", " ", line)[:42].strip()
    source_lead = source.split(maxsplit=1)[0] if source else ""
    if source and core and source not in core and (not source_lead or source_lead not in core):
        return f"{source}｜{core}"
    return core or source or "公開口琴活動"


def event_source_label(item: dict[str, Any]) -> str:
    """Return the human-readable organizer or performer name for calendar details."""
    for key in ("directory_entry_name", "source_system_name", "source_name", "source"):
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return "公開來源"


def details_with_source(item: dict[str, Any], details: str) -> str:
    label = event_source_label(item)
    text = str(details or "").strip()
    if text.startswith("主辦／演出者："):
        return text
    prefix = f"主辦／演出者：{label}。"
    if text.startswith(prefix):
        return text
    return f"{prefix}{text}" if text else prefix


def compact_for_llm(text: str, limit: int = 2200) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return data if isinstance(data, dict) else default


def canonical_evidence_url(value: Any) -> str:
    """Treat X/Twitter host aliases as the same public evidence URL."""
    url = str(value or "").strip().rstrip("/")
    return re.sub(r"^https?://(?:www\.)?(?:twitter\.com|x\.com)/", "https://x.com/", url, flags=re.IGNORECASE)


def load_override_candidate_items(
    overrides: dict[str, dict[str, Any]],
    candidates_path: Path = SOCIAL_CANDIDATES_PATH,
) -> list[dict[str, Any]]:
    """Bring manually confirmed sources into the calendar even outside the rolling feed window."""
    if not overrides:
        return []
    wanted = {canonical_evidence_url(url) for url in overrides}
    found: list[dict[str, Any]] = []
    found_urls: set[str] = set()
    try:
        lines = candidates_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(item, dict):
            continue
        item_url = canonical_evidence_url(item.get("link") or item.get("url") or item.get("post_id"))
        if item_url not in wanted:
            continue
        item = dict(item)
        item["link"] = item.get("link") or item.get("url") or item.get("post_id") or ""
        found.append(item)
        found_urls.add(item_url)

    # Official venue and ticketing pages may never appear in the rolling social
    # feed.  A manual override is already a curated assertion, so synthesize the
    # minimal source item needed to keep that future event durable.
    for evidence_url, override in overrides.items():
        canonical_url = canonical_evidence_url(evidence_url)
        if canonical_url in found_urls:
            continue
        source_name = str(override.get("sourceName") or "").strip()
        if not source_name:
            # Legacy overrides are intentionally anchored to a captured social
            # candidate. Only explicitly named official sources are standalone.
            continue
        found.append(
            {
                "link": evidence_url,
                "url": evidence_url,
                "source": source_name,
                "source_name": source_name,
                "platform": str(override.get("platform") or "website").strip(),
                "text": "\n".join(
                    str(override.get(key) or "").strip()
                    for key in ("eventName", "venue", "details")
                    if str(override.get(key) or "").strip()
                ),
            }
        )
    return found


def atomic_write_text(path: Path, text: str) -> None:
    """Publish in one rename so the calendar sync never reads a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def save_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def candidate_fingerprint(item: dict[str, Any], start: str, end: str, context: str) -> str:
    payload = {
        "policyVersion": CALENDAR_REVIEW_POLICY_VERSION,
        "source": item.get("source") or "",
        "link": item.get("link") or "",
        "start": start,
        "end": end,
        "text": compact_for_llm(str(item.get("text") or item.get("title") or ""), 1200),
        "context": compact_for_llm(context, 500),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def normalize_llm_calendar_review(value: dict[str, Any]) -> dict[str, Any]:
    include = bool(value.get("include"))
    country = str(value.get("country") or "").strip()
    event_name = str(value.get("eventName") or "").strip()
    venue = str(value.get("venue") or "").strip()
    city = str(value.get("city") or "").strip()
    details = str(value.get("details") or "").strip()
    reason = str(value.get("reason") or "").strip()
    requested_mode = str(value.get("eventMode") or "").strip()
    candidate_date_matches = value.get("candidateDateMatches") is True
    confidence = value.get("confidence")
    try:
        confidence_value = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_value = 0.0
    # Venue/city describe the event location; a rationale such as "not Taiwan"
    # or an overseas performer's biography is not positive location evidence.
    location_country = infer_country(city)
    if location_country and requested_mode != ONLINE:
        country = location_country
        mode = classify_event_mode(country, f"{venue} {city}")
        timezone = infer_timezone(country) or valid_timezone(value.get("timezone"))
    else:
        mode = classify_event_mode(country, f"{event_name} {venue} {city} {details}", requested_mode)
        timezone = valid_timezone(value.get("timezone")) or infer_timezone(country)
    if mode == TAIWAN_PHYSICAL:
        country = "臺灣"
        timezone = TIMEZONE
    elif mode == ONLINE:
        country = "線上"
    include = include and bool(mode) and candidate_date_matches
    if confidence_value < 0.5:
        include = False
    if include and (not event_name or (not venue and mode != ONLINE)):
        include = False
    return {
        "include": include,
        "country": country,
        "eventMode": mode,
        "timezone": timezone,
        "candidateDateMatches": candidate_date_matches,
        "eventName": event_name,
        "venue": venue or ("線上直播" if mode == ONLINE else ""),
        "city": city,
        "details": details,
        "reason": reason,
        "confidence": round(confidence_value, 3),
    }


def llm_calendar_prompt(item: dict[str, Any], start: str, end: str, context: str) -> list[dict[str, str]]:
    payload = {
        "source": item.get("source") or "",
        "platform": item.get("platform") or "",
        "postedAt": item.get("posted_at_local") or item.get("posted_at") or "",
        "url": item.get("link") or "",
        "candidateStart": start,
        "candidateEnd": end,
        "dateContext": compact_for_llm(context, 700),
        "text": compact_for_llm(str(item.get("text") or item.get("title") or ""), 2200),
    }
    return [
        {
            "role": "system",
            "content": (
                "你是全球口琴觀測站的公開活動日曆審核器。"
                "只根據公開貼文文字判斷，收錄公開口琴活動；"
                "收錄範圍是：臺灣實體活動、臺灣以外的國外實體活動，以及國內外有明確時間的線上直播/線上講座/線上音樂會。"
                "三種 eventMode 必須互斥；有直播或線上報名資訊的實體活動仍依實際舉辦地點分類。"
                "排除已發生的回顧影片、一般貼文、非口琴活動、沒有明確活動時間的隨選影片。"
                "必須只判斷 candidateStart、candidateEnd 與 dateContext 對應的候選；"
                "如果全文其他段落有不同日期的另一個活動，請忽略它，不要拿來補這個候選。"
                "請只回傳 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "請判斷這個候選是否應加入「口琴公開活動」日曆，並萃取結構化資訊。\n"
                "JSON schema:\n"
                "{\n"
                '  "include": true/false,\n'
                '  "eventMode": "taiwan_physical、overseas_physical 或 online",\n'
                '  "candidateDateMatches": "只有 eventName 與 details 描述的活動日期確實等於 candidateStart 候選日期時才是 true",\n'
                '  "country": "臺灣、其他國家/地區，或線上",\n'
                '  "timezone": "活動公告時間所使用的 IANA timezone，例如 Asia/Taipei、Asia/Tokyo；無法可靠判斷則空字串",\n'
                '  "eventName": "活動名稱，不要放主辦帳號或貼文內文摘要",\n'
                '  "venue": "活動地點/場館名稱；純線上活動可填線上直播或平台名稱；不要放整段內文",\n'
                '  "city": "縣市或城市；純線上可空白",\n'
                '  "details": "一到兩句活動相關資訊，例如演出者、票價、報名、直播平台、場次；不要寫自動抽取說明",\n'
                '  "confidence": 0.0,\n'
                '  "reason": "簡短判斷理由"\n'
                "}\n\n"
                "若貼文同時提到其他日期的活動、旅程或比賽，不能把另一個活動名稱套到 candidateStart；"
                "日期不一致時 include 與 candidateDateMatches 都必須是 false。\n"
                f"候選資料：{json.dumps(payload, ensure_ascii=False)}"
            ),
        },
    ]


def review_candidate_with_llm(
    item: dict[str, Any],
    *,
    start: str,
    end: str,
    context: str,
    cache: dict[str, Any],
    token: str,
    base_url: str,
    model: str,
    timeout: int,
    stats: dict[str, int],
) -> dict[str, Any] | None:
    fingerprint = candidate_fingerprint(item, start, end, context)
    cached = ((cache.get("items") or {}).get(fingerprint))
    if isinstance(cached, dict):
        stats["cached"] = stats.get("cached", 0) + 1
        return normalize_llm_calendar_review(cached)
    if not token:
        return None
    body = {
        "model": model,
        "messages": llm_calendar_prompt(item, start, end, context),
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    response_body = watchdog.curl_json(watchdog.llm_endpoint(base_url), token, body, timeout)
    response = json.loads(response_body)
    parsed = watchdog.extract_json_object(watchdog.chat_response_text(response))
    normalized = normalize_llm_calendar_review(parsed)
    items = cache.setdefault("items", {})
    if isinstance(items, dict):
        items[fingerprint] = {**normalized, "llmModel": llm_backend.resolved_model(response, model),
                              "llmRequestedModel": model}
        cache["version"] = 1
        cache["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    stats["requests"] = stats.get("requests", 0) + 1
    return normalized


def normalized_event_identity(title: str, source: Any, start: dt.date) -> tuple[str, str, str]:
    compact_title = re.sub(r"\s+", "", title)
    compact_title = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", compact_title, flags=re.UNICODE)
    compact_source = re.sub(r"\s+", "", str(source or ""))
    return (compact_source.lower(), compact_title[:48].lower(), start.isoformat())


def date_candidates(text: str, posted_at: dt.datetime | None) -> list[tuple[dt.date, dt.date, str]]:
    candidates: list[tuple[dt.date, dt.date, str]] = []
    seen: set[tuple[dt.date, dt.date]] = set()
    slash_dates = list(SLASH_DATE_RE.finditer(text))
    slash_day_first = any(int(match.group("first")) > 12 for match in slash_dates)
    slash_schedule = slash_day_first and len(slash_dates) >= 2 and text_has_any(text, EVENT_TERMS)

    for match in COMPACT_RANGE_RE.finditer(text):
        year = normalized_year(int(match.group("year")), (posted_at or dt.datetime.now(TAIWAN_TZ)).year)
        start = safe_date(year, int(match.group("month")), int(match.group("day")))
        end = safe_date(year, int(match.group("end_month")), int(match.group("end_day")))
        if start and end and end >= start and (end - start).days <= 7:
            key = (start, end)
            if key not in seen:
                seen.add(key)
                candidates.append((start, end, nearby_context(text, match.start(), match.end())))

    for match in DATE_RANGE_RE.finditer(text):
        start = parse_loose_date(match.group("left"), posted_at, slash_day_first=slash_day_first)
        end = parse_loose_date(match.group("right"), posted_at, slash_day_first=slash_day_first)
        if start and end and end >= start and (end - start).days <= 14:
            key = (start, end)
            if key not in seen:
                seen.add(key)
                candidates.append((start, end, nearby_context(text, match.start(), match.end())))

    occupied = [range(match.start(), match.end()) for match in DATE_RANGE_RE.finditer(text)]
    full_date_spans = [range(match.start(), match.end()) for match in FULL_DATE_RE.finditer(text)]
    for regex in (FULL_DATE_RE, MONTH_DAY_RE):
        for match in regex.finditer(text):
            if any(match.start() in span or match.end() in span for span in occupied):
                continue
            if regex is MONTH_DAY_RE and any(
                match.start() in span or match.end() in span for span in full_date_spans
            ):
                continue
            if date_match_is_truncated(text, match.end()):
                continue
            date = parse_loose_date(match.group(0), posted_at, slash_day_first=slash_day_first)
            if not date:
                continue
            context = (
                schedule_line_context(text, match.start(), match.end())
                if slash_schedule
                else nearby_context(text, match.start(), match.end())
            )
            if not text_has_any(context, EVENT_TERMS) and not slash_schedule:
                continue
            key = (date, date)
            if key not in seen:
                seen.add(key)
                candidates.append((date, date, context))

    for match in ENGLISH_DATE_RE.finditer(text):
        if date_match_is_truncated(text, match.end()):
            continue
        date = english_date_from_match(match, posted_at)
        if not date:
            continue
        context = nearby_context(text, match.start(), match.end())
        if not text_has_any(context, EVENT_TERMS):
            continue
        key = (date, date)
        if key not in seen:
            seen.add(key)
            candidates.append((date, date, context))

    return candidates


def item_key(item: dict[str, Any], start: dt.date) -> str:
    source = str(item.get("source_id") or item.get("source") or "")
    link = str(item.get("link") or "")
    raw = f"{source}|{link}|{start.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def fallback_calendar_review(item: dict[str, Any], title: str, location: str, text: str) -> dict[str, Any] | None:
    combined = f"{title} {location} {text}"
    country = infer_country(f"{title} {location}")
    if not country and TAIWAN_PLACE_RE.search(f"{title} {location}"):
        country = "臺灣"
    requested_mode = ONLINE if not location and is_online_event_text(combined) else ""
    mode = classify_event_mode(country, combined, requested_mode)
    if not mode:
        return None
    if not location and mode != ONLINE:
        return None
    timezone = TIMEZONE if mode == TAIWAN_PHYSICAL else infer_timezone(country)
    return {
        "include": True,
        "country": "線上" if mode == ONLINE else country,
        "eventMode": mode,
        "timezone": timezone,
        "candidateDateMatches": True,
        "eventName": title,
        "venue": location or ("線上直播" if mode == ONLINE else ""),
        "city": "",
        "details": "",
        "reason": "fallback public harmonica event match",
        "confidence": 0.35,
    }


def title_date_conflicts(title: str, start_date: dt.date) -> bool:
    dates = [
        (int(match.group("month")), int(match.group("day")))
        for match in MONTH_DAY_RE.finditer(title)
        if not date_match_is_truncated(title, match.end())
    ]
    if not dates:
        return False
    return all((month, day) != (start_date.month, start_date.day) for month, day in dates)


def event_start_date_key(event: dict[str, Any]) -> str:
    return str(event.get("start") or "")[:10]


def location_signature(location: Any) -> set[str]:
    text = str(location or "").lower()
    tokens = set(re.findall(r"[a-z0-9]{4,}", text))
    compact_cjk = re.sub(r"[^\u3400-\u9fff\u3040-\u30ff]+", "", text)
    for index in range(max(0, len(compact_cjk) - 3)):
        tokens.add(compact_cjk[index:index + 4])
    return tokens


def event_confidence(event: dict[str, Any]) -> float:
    try:
        return float(event.get("confidence") or 0)
    except (TypeError, ValueError):
        return 0.0


def event_has_time(event: dict[str, Any]) -> bool:
    return "T" in str(event.get("start") or "")


def should_replace_similar_event(existing: dict[str, Any], candidate: dict[str, Any]) -> bool:
    # Verified form submissions always beat scraped events, whichever side they land on.
    existing_submitted = existing.get("platform") == SUBMITTED_PLATFORM
    candidate_submitted = candidate.get("platform") == SUBMITTED_PLATFORM
    if existing_submitted != candidate_submitted:
        return candidate_submitted
    existing_confidence = event_confidence(existing)
    candidate_confidence = event_confidence(candidate)
    if candidate_confidence > existing_confidence:
        return True
    if candidate_confidence == existing_confidence:
        return event_has_time(candidate) and not event_has_time(existing)
    return False


GENERIC_TITLE_ANCHORS = {
    "年度音樂會",
    "成果發表會",
    "臺灣口琴音樂節",
    "口琴音樂節",
    "口琴節",
    "演奏會",
    "音樂會",
}
MULTI_DAY_EVENT_RE = re.compile(
    r"(?:節|节|festival|大會|大会|賽|赛|contest|competition|營|营|camp)",
    re.IGNORECASE,
)
TITLE_VARIANT_TRANSLATION = str.maketrans(
    {
        "亚": "亞",
        "会": "會",
        "届": "屆",
        "节": "節",
        "赛": "賽",
    }
)


def normalized_title(value: Any) -> str:
    return re.sub(
        r"[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+",
        "",
        str(value or "").translate(TITLE_VARIANT_TRANSLATION).casefold(),
    )


def leading_cjk_title_anchor(value: Any) -> str:
    match = re.match(r"\s*([\u3400-\u9fff]{4,})", str(value or ""))
    if not match:
        return ""
    anchor = match.group(1)
    if anchor in GENERIC_TITLE_ANCHORS or anchor.endswith(("口琴音樂節", "成果發表會")):
        return ""
    return anchor


def leading_latin_title_anchor(value: Any) -> str:
    """Return a likely Latin-script performer prefix such as ``Cy Leo``.

    Calendar posts often describe the same concert once by its tour name and once
    by its localized program name.  The shared performer prefix is useful only for
    folding an untimed placeholder into a timed record; it is deliberately not a
    general same-day performer dedupe key.
    """
    match = re.match(r"\s*([A-Za-z][A-Za-z0-9.'-]{1,})\s+([A-Za-z][A-Za-z0-9.'-]{2,})", str(value or ""))
    if not match:
        return ""
    return f"{match.group(1)} {match.group(2)}".casefold()


def event_titles_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = left.get("eventName") or left.get("title")
    right_title = right.get("eventName") or right.get("title")
    left_normalized = normalized_title(left_title)
    right_normalized = normalized_title(right_title)
    if left_normalized and left_normalized == right_normalized:
        return True
    # The anchor fallback exists to fold a truncated record into a complete one. Two
    # equally detailed events that merely share an organiser prefix are usually distinct.
    if event_has_time(left) == event_has_time(right):
        return False
    left_anchor = leading_cjk_title_anchor(left_title)
    right_anchor = leading_cjk_title_anchor(right_title)
    if left_anchor and left_anchor == right_anchor:
        return True
    left_latin_anchor = leading_latin_title_anchor(left_title)
    right_latin_anchor = leading_latin_title_anchor(right_title)
    return bool(left_latin_anchor and left_latin_anchor == right_latin_anchor)


def event_times_compatible(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_start = str(left.get("start") or "")
    right_start = str(right.get("start") or "")
    if "T" not in left_start or "T" not in right_start:
        return True
    return left_start[11:16] == right_start[11:16]


def all_day_date_range(event: dict[str, Any]) -> tuple[dt.date, dt.date] | None:
    if not event.get("allDay"):
        return None
    try:
        start = dt.date.fromisoformat(str(event.get("start") or "")[:10])
        end = dt.date.fromisoformat(str(event.get("end") or "")[:10])
    except ValueError:
        return None
    if end <= start:
        end = start + dt.timedelta(days=1)
    return start, end


def multi_day_events_match(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_title = normalized_title(left.get("eventName") or left.get("title"))
    right_title = normalized_title(right.get("eventName") or right.get("title"))
    if not left_title or left_title != right_title or not MULTI_DAY_EVENT_RE.search(left_title):
        return False
    if left.get("calendarType") != right.get("calendarType"):
        return False
    left_range = all_day_date_range(left)
    right_range = all_day_date_range(right)
    if not left_range or not right_range:
        return False
    left_start, left_end = left_range
    right_start, right_end = right_range
    overlap_start = max(left_start, right_start)
    overlap_end = min(left_end, right_end)
    if overlap_start < overlap_end:
        return True
    if overlap_start > overlap_end:
        return False
    # All-day end dates are exclusive, so touching ranges do not really overlap. Fold them
    # together only when one side is short enough to look like a truncated record.
    shortest = min(left_end - left_start, right_end - right_start)
    return shortest <= dt.timedelta(days=2)


def find_similar_event_indices(events: list[dict[str, Any]], candidate: dict[str, Any]) -> list[int]:
    matches: list[int] = []
    candidate_location = location_signature(candidate.get("location"))
    for index, existing in enumerate(events):
        if multi_day_events_match(existing, candidate):
            matches.append(index)
            continue
        if event_start_date_key(existing) != event_start_date_key(candidate):
            continue
        if not event_times_compatible(existing, candidate):
            continue
        existing_url = str(existing.get("evidenceUrl") or "").strip()
        candidate_url = str(candidate.get("evidenceUrl") or "").strip()
        if existing_url and existing_url == candidate_url:
            matches.append(index)
            continue
        if event_titles_match(existing, candidate):
            matches.append(index)
            continue
        if not candidate_location:
            continue
        existing_location = location_signature(existing.get("location"))
        if len(candidate_location & existing_location) >= 2:
            matches.append(index)
    return matches


def find_similar_event_index(events: list[dict[str, Any]], candidate: dict[str, Any]) -> int | None:
    matches = find_similar_event_indices(events, candidate)
    return matches[0] if matches else None


def event_sort_key(event: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(event.get("start") or ""),
        str(event.get("source") or ""),
        str(event.get("title") or ""),
    )


def deduplicate_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped_events: list[dict[str, Any]] = []
    seen_final: set[tuple[str, str, str]] = set()
    for event in sorted(events, key=event_sort_key):
        key = (
            normalized_title(event.get("eventName") or event.get("title")),
            re.sub(r"\s+", "", str(event.get("location") or "")).lower(),
            str(event.get("start") or ""),
        )
        if key in seen_final:
            continue
        similar_indices = find_similar_event_indices(deduped_events, event)
        if similar_indices:
            canonical = event
            for index in similar_indices:
                existing = deduped_events[index]
                if not should_replace_similar_event(existing, canonical):
                    canonical = existing
            first_index = similar_indices[0]
            deduped_events[first_index] = canonical
            # A more complete record can bridge two partial records (for example,
            # a tour announcement and a venue announcement). Remove every matched
            # partial instead of stopping after the first pairwise match.
            for index in reversed(similar_indices[1:]):
                del deduped_events[index]
            continue
        seen_final.add(key)
        deduped_events.append(event)
    # In-place replacements can leave a later event sitting at an earlier index.
    return sorted(deduped_events, key=event_sort_key)


def extract_events(
    items: list[dict[str, Any]],
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
    llm_token: str = "",
    llm_base_url: str = llm_backend.DEFAULT_GATEWAY_BASE_URL,
    llm_model: str = llm_backend.CLASSIFIER_MODEL,
    llm_timeout: int = 45,
    llm_cache: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_links_dates: set[tuple[str, str]] = set()
    seen_event_identity: set[tuple[str, str, str]] = set()
    cache = llm_cache if isinstance(llm_cache, dict) else {"version": 1, "items": {}}
    override_by_url = overrides or {}
    override_by_canonical_url = {
        canonical_evidence_url(url): value for url, value in override_by_url.items()
    }
    used_overrides: set[str] = set()
    llm_stats: dict[str, int] = {"requests": 0, "cached": 0, "errors": 0}
    now_date = dt.datetime.now(TAIWAN_TZ).date()
    min_date = now_date - dt.timedelta(days=2)
    max_date = now_date + dt.timedelta(days=420)

    for item in items:
        text = "\n".join(str(item.get(key) or "") for key in ("source", "title", "text"))
        link = str(item.get("link") or "")
        override_url = canonical_evidence_url(link)
        is_manual_override = override_url in override_by_canonical_url
        if not is_manual_override and not text_has_any(text, HARMONICA_TERMS):
            continue
        if not is_manual_override and not text_has_any(text, EVENT_TERMS):
            continue
        posted_at = parse_datetime(item.get("posted_at_local")) or parse_datetime(item.get("posted_at"))
        if override_url in override_by_canonical_url:
            override = dict(override_by_canonical_url[override_url])
            start_for_id = parse_datetime(override.get("start"))
            start_date = start_for_id.date() if start_for_id else safe_date(*[int(part) for part in str(override.get("start", ""))[:10].split("-")])
            if start_date:
                override["details"] = details_with_source(item, override.get("details") or "")
                override.update(
                    {
                        "id": item_key(item, start_date),
                        "source": item.get("source") or "",
                        "platform": item.get("platform") or "",
                        "postedAt": item.get("posted_at_local") or item.get("posted_at") or "",
                        "images": override.get("images") or item.get("images") or [],
                        "image_url": override.get("image_url") or item.get("image_url") or "",
                    }
                )
                events.append(override)
                used_overrides.add(override_url)
                seen_links_dates.add((link, start_date.isoformat()))
            continue
        daily_candidates = explicit_daily_candidates(str(item.get("text") or ""), posted_at)
        if not daily_candidates and re.search(r"每天|每晚|每日|毎日|매일|\bdaily\b|\bevery (?:day|evening|night)\b", text, re.IGNORECASE) and DATE_RANGE_RE.search(text):
            # A daily service or multiple competing schedules cannot safely be
            # promoted to a continuous or recurring performance by proximity.
            continue
        candidates = daily_candidates or date_candidates(text, posted_at)
        for start_date, end_date, context in candidates:
            if start_date < min_date or start_date > max_date:
                continue
            dedupe_key = (link, start_date.isoformat())
            if dedupe_key in seen_links_dates:
                continue
            seen_links_dates.add(dedupe_key)
            title = event_title(item, context)
            if CANCELLED_EVENT_RE.search(f"{title} {context}") or NON_EVENT_ANNOUNCEMENT_RE.search(text):
                continue
            identity = normalized_event_identity(title, item.get("source"), start_date)
            if identity in seen_event_identity:
                continue
            seen_event_identity.add(identity)
            time_range = explicit_time_range(context)
            time_text = time_range[0] if time_range else extract_time(context)
            if not daily_candidates and title_date_conflicts(title, start_date):
                continue
            start = f"{start_date.isoformat()}T{time_text}:00+08:00" if time_text else start_date.isoformat()
            end = end_date.isoformat()
            if time_text:
                end_dt = dt.datetime.combine(start_date, dt.time.fromisoformat(time_text), TAIWAN_TZ) + dt.timedelta(hours=2)
                if end_date > start_date:
                    end_dt = dt.datetime.combine(end_date, dt.time(23, 59), TAIWAN_TZ)
                end = end_dt.isoformat()
            elif end_date >= start_date:
                end = (end_date + dt.timedelta(days=1)).isoformat()
            location = extract_location(context)
            if not location and len(candidates) == 1:
                location = extract_location(text)
            review: dict[str, Any] | None = None
            if llm_token or cache.get("items"):
                try:
                    review = review_candidate_with_llm(
                        item,
                        start=start,
                        end=end,
                        context=context,
                        cache=cache,
                        token=llm_token,
                        base_url=llm_base_url,
                        model=llm_model,
                        timeout=llm_timeout,
                        stats=llm_stats,
                    )
                except Exception as exc:
                    llm_stats["errors"] = llm_stats.get("errors", 0) + 1
                    print(f"calendar LLM review failed for {link}: {exc}", file=sys.stderr)
            if review is None:
                review = fallback_calendar_review(item, title, location, text)
                if review and daily_candidates:
                    review["details"] = str(item.get("text") or "")
            if is_explicit_tour_schedule(item, context):
                # A listed date/city pair is authoritative; LLM review must not
                # merge it with the first city in a multi-stop tour caption.
                review = tour_schedule_review(item, title, start, context) or review
            if not review or not review.get("include"):
                continue
            if review.get("confidence") == 0.35 and not review.get("country") == "臺灣" and not time_text:
                continue
            event_name = str(review.get("eventName") or title).strip()
            venue = clean_location(str(review.get("venue") or location))
            city = str(review.get("city") or "").strip()
            details = details_with_source(item, review.get("details") or "")
            review["details"] = details
            review_mode = str(review.get("eventMode") or "").strip()
            if review_mode in {TAIWAN_PHYSICAL, OVERSEAS_PHYSICAL} and not city and GENERIC_COUNTRY_VENUE_RE.fullmatch(venue):
                # A post saying someone will visit Taiwan for judging/teaching/
                # guest performance is not enough to identify a public event.
                continue
            country = str(review.get("country") or "").strip()
            location_country = infer_country(city)
            if location_country and review_mode != ONLINE:
                country = location_country
                review["timezone"] = infer_timezone(country) or review.get("timezone")
            mode = classify_event_mode(
                country,
                f"{venue} {city}" if location_country and review_mode != ONLINE else f"{event_name} {venue} {city} {details}",
                "" if location_country and review_mode != ONLINE else str(review.get("eventMode") or ""),
            )
            if not mode:
                continue
            if mode == ONLINE and (not time_text or not is_online_event_text(context)):
                continue
            if mode == TAIWAN_PHYSICAL and GENERIC_ONLINE_VENUE_RE.fullmatch(venue):
                venue = clean_location(location)
                if not venue:
                    continue
            timezone = valid_timezone(review.get("timezone")) or infer_timezone(country)
            if mode == TAIWAN_PHYSICAL:
                country = "臺灣"
                timezone = TIMEZONE
            elif mode == OVERSEAS_PHYSICAL:
                location_country = infer_country(city)
                if location_country:
                    country = location_country
                    timezone = infer_timezone(location_country) or timezone
            elif mode == ONLINE:
                country = "線上"
            if time_text and not timezone:
                continue
            timezone = timezone or TIMEZONE
            event_zone = ZoneInfo(timezone)
            start = start_date.isoformat()
            end = (end_date + dt.timedelta(days=1)).isoformat()
            if time_text:
                start_dt = dt.datetime.combine(start_date, dt.time.fromisoformat(time_text), event_zone)
                end_dt = start_dt + dt.timedelta(hours=2)
                if time_range:
                    end_dt = dt.datetime.combine(end_date, dt.time.fromisoformat(time_range[1]), event_zone)
                    if end_dt <= start_dt:
                        end_dt += dt.timedelta(days=1)
                elif end_date > start_date:
                    end_dt = dt.datetime.combine(end_date, dt.time(23, 59), event_zone)
                start = start_dt.isoformat()
                end = end_dt.isoformat()
            review["country"] = country
            review["eventMode"] = mode
            review["timezone"] = timezone
            display_location = venue if not city or city in venue else f"{city} {venue}"
            events.append(
                {
                    "id": item_key(item, start_date),
                    "title": event_name,
                    "eventName": event_name,
                    "source": item.get("source") or "",
                    "platform": item.get("platform") or "",
                    "start": start,
                    "end": end,
                    "endEstimated": bool(time_text) and not bool(time_range),
                    "allDay": not bool(time_text),
                    "calendarType": mode,
                    "timezone": timezone,
                    "location": display_location,
                    "venue": venue,
                    "city": city,
                    "details": details,
                    "evidenceUrl": link,
                    "confidence": review.get("confidence") or 0,
                    "calendarReview": review,
                    "postedAt": item.get("posted_at_local") or item.get("posted_at") or "",
                    "images": item.get("images") or [],
                    "image_url": item.get("image_url") or "",
                }
            )

    cache["stats"] = llm_stats
    return deduplicate_events(events)


def escape_ics(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold_ics_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line
    parts: list[str] = []
    current = ""
    current_len = 0
    for char in line:
        char_len = len(char.encode("utf-8"))
        if current and current_len + char_len > 75:
            parts.append(current)
            current = " " + char
            current_len = 1 + char_len
        else:
            current += char
            current_len += char_len
    if current:
        parts.append(current)
    return "\r\n".join(parts)


def ics_datetime(value: str, *, all_day: bool, timezone: str = TIMEZONE) -> str:
    if all_day:
        return value.replace("-", "")
    parsed = dt.datetime.fromisoformat(value)
    return parsed.astimezone(ZoneInfo(timezone)).strftime("%Y%m%dT%H%M%S")


def calendar_description(event: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            str(event.get("details") or "").strip(),
            "結束時間未公告；日曆結束時間為估計。End time not announced; calendar end time is estimated." if event.get("endEstimated") else "",
            str(event.get("evidenceUrl") or "").strip(),
        ]
        if part
    )


def write_ics(
    events: list[dict[str, Any]],
    generated_at: str,
    *,
    path: Path = ICS_PATH,
    calendar_name: str = "臺灣口琴實體活動",
) -> None:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Harmonica Observe Taiwan//Public Calendar//ZH-TW",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics(calendar_name)}",
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for event in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:{event['id']}@harmonica.observe.tw")
        lines.append(f"DTSTAMP:{stamp}")
        if event["allDay"]:
            lines.append(f"DTSTART;VALUE=DATE:{ics_datetime(event['start'], all_day=True)}")
            lines.append(f"DTEND;VALUE=DATE:{ics_datetime(event['end'], all_day=True)}")
        else:
            event_timezone = valid_timezone(event.get("timezone")) or TIMEZONE
            lines.append(
                f"DTSTART;TZID={event_timezone}:"
                f"{ics_datetime(event['start'], all_day=False, timezone=event_timezone)}"
            )
            lines.append(
                f"DTEND;TZID={event_timezone}:"
                f"{ics_datetime(event['end'], all_day=False, timezone=event_timezone)}"
            )
        lines.append(f"SUMMARY:{escape_ics(event['title'])}")
        if event.get("location"):
            lines.append(f"LOCATION:{escape_ics(event['location'])}")
        lines.append(f"DESCRIPTION:{escape_ics(calendar_description(event))}")
        if event.get("evidenceUrl"):
            lines.append(f"URL:{escape_ics(event['evidenceUrl'])}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    atomic_write_text(path, "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n")


def calendar_payload(
    events: list[dict[str, Any]],
    *,
    mode: str,
    generated_at: str,
    ics_path: str,
    criteria: str,
    overrides: int,
    llm: dict[str, Any],
) -> dict[str, Any]:
    return {
        "version": 2,
        "generatedAt": generated_at,
        "timezone": TIMEZONE,
        "calendarType": mode,
        "count": len(events),
        "source": "/api/events.json",
        "ics": ics_path,
        "rightsNote": "只整理公開貼文中的活動 metadata、日期與來源連結；請以原始公開貼文或售票/報名頁為準。",
        "criteria": criteria,
        "manualOverrides": overrides,
        "llm": llm,
        "events": events,
    }


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-llm", action="store_true")
    parser.add_argument("--llm-cache", type=Path, default=DEFAULT_LLM_CACHE)
    parser.add_argument("--llm-base-url", default=llm_backend.base_url())
    parser.add_argument("--llm-model", default=llm_backend.model_name())
    parser.add_argument("--llm-timeout", type=int, default=int(os.environ.get("HARMONICA_LLM_TIMEOUT", "45")))
    parser.add_argument("--llm-keychain-service", default=os.environ.get("HARMONICA_LLM_KEYCHAIN_SERVICE", watchdog.DEFAULT_LLM_KEYCHAIN_SERVICE))
    parser.add_argument("--llm-keychain-account", default=os.environ.get("HARMONICA_LLM_KEYCHAIN_ACCOUNT", watchdog.DEFAULT_LLM_KEYCHAIN_ACCOUNT))
    args = parser.parse_args()
    payload = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    llm_cache = load_json(args.llm_cache, {"version": 1, "items": {}})
    llm_token = ""
    llm_token_source = ""
    if not args.no_llm:
        llm_token, llm_token_source = watchdog.read_llm_token(args.llm_keychain_service, args.llm_keychain_account)
    overrides = load_overrides()
    existing_urls = {
        canonical_evidence_url(item.get("link"))
        for item in items
        if isinstance(item, dict) and item.get("link")
    }
    items.extend(
        item
        for item in load_override_candidate_items(overrides)
        if canonical_evidence_url(item.get("link")) not in existing_urls
    )
    generated_at = dt.datetime.now(TAIWAN_TZ).isoformat(timespec="seconds")
    events = extract_events(
        [item for item in items if isinstance(item, dict)],
        overrides=overrides,
        llm_token=llm_token,
        llm_base_url=args.llm_base_url,
        llm_model=args.llm_model,
        llm_timeout=args.llm_timeout,
        llm_cache=llm_cache,
    )
    if llm_token:
        save_json(args.llm_cache, llm_cache)
    llm_metadata = {
        "enabled": bool(llm_token),
        "tokenSource": llm_token_source,
        "model": llm_backend.runtime_metadata(args.llm_model, args.llm_base_url)["model"] if llm_token else "",
        "provider": llm_backend.provider(),
        "stats": llm_cache.get("stats") or {},
    }
    events_by_mode = {
        mode: [event for event in events if event.get("calendarType") == mode]
        for mode in EVENT_MODES
    }
    output = calendar_payload(
        events_by_mode[TAIWAN_PHYSICAL],
        mode=TAIWAN_PHYSICAL,
        generated_at=generated_at,
        ics_path="/feeds/public-calendar.ics",
        criteria="實際舉辦地點在臺灣的公開口琴實體活動。",
        overrides=len(overrides),
        llm=llm_metadata,
    )
    overseas_output = calendar_payload(
        events_by_mode[OVERSEAS_PHYSICAL],
        mode=OVERSEAS_PHYSICAL,
        generated_at=generated_at,
        ics_path="/feeds/overseas-calendar.ics",
        criteria="實際舉辦地點在臺灣以外的公開口琴實體活動。",
        overrides=len(overrides),
        llm=llm_metadata,
    )
    online_output = calendar_payload(
        events_by_mode[ONLINE],
        mode=ONLINE,
        generated_at=generated_at,
        ics_path="/feeds/online-calendar.ics",
        criteria="國內外有明確日期、時間與直播或線上參與方式的公開口琴活動。",
        overrides=len(overrides),
        llm=llm_metadata,
    )
    for path, payload in [
        (JSON_PATH, output),
        (OVERSEAS_JSON_PATH, overseas_output),
        (ONLINE_JSON_PATH, online_output),
    ]:
        atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    atomic_write_text(
        JS_PATH,
        "window.publicCalendarEvents = " + json.dumps(output, ensure_ascii=False, indent=2) + ";\n",
    )
    write_ics(events_by_mode[TAIWAN_PHYSICAL], generated_at)
    write_ics(
        events_by_mode[OVERSEAS_PHYSICAL],
        generated_at,
        path=OVERSEAS_ICS_PATH,
        calendar_name="國外口琴實體活動",
    )
    write_ics(
        events_by_mode[ONLINE],
        generated_at,
        path=ONLINE_ICS_PATH,
        calendar_name="線上口琴活動",
    )
    print(
        "Built public calendar events: "
        f"taiwan={len(events_by_mode[TAIWAN_PHYSICAL])} "
        f"overseas={len(events_by_mode[OVERSEAS_PHYSICAL])} "
        f"online={len(events_by_mode[ONLINE])}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
