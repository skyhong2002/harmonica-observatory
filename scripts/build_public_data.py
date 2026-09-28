#!/usr/bin/env python3
"""Build the public data bundle for harmonica.observe.tw."""

from __future__ import annotations

import csv
import email.utils
import hashlib
import itertools
import json
import re
import shutil
import urllib.parse
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from source_slugs import make_slug
from curated_source_profiles import load_profiles, apply_profile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
DATA_OUT = SITE_ROOT / "data" / "site-data.js"
CANDIDATES = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
SOURCE_PROFILES_CACHE = PROJECT_ROOT / "data" / "feeds" / "source_profiles.json"
SOCIAL_SOURCES = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
SOURCE_TAG_CACHE = PROJECT_ROOT / "state" / "source_llm_tags.json"
SOURCE_AVATAR_DIR = SITE_ROOT / "assets" / "source-avatars"
CURATED_SOURCE_AVATAR_DIR = PROJECT_ROOT / "assets" / "source-avatars-curated"
CURATED_SOURCE_AVATARS = {
    "中國大眾音樂協會口琴專業委員會": "china-popular-music-harmonica-committee.png",
    "中國大眾音樂協會口琴考級網": "china-popular-music-harmonica-committee.png",
    "東方口琴博物館": "easttop-harmonica-museum.jpg",
    "東方口琴樂團": "easttop-harmonica-ensemble.jpg",
    "雲林縣二崙國中藝才班口琴隊": "erhlun-junior-high-harmonica.jpg",
    "遼陽白塔口琴藝術周暨第三屆「白塔杯」口琴大賽": "liaoyang-baita-harmonica-week.jpg",
    "Mundharmonika-Live 口琴節": "mundharmonika-live-2026.jpg",
    "華中師範大學學生知音口琴社": "ccnu-zhiyin-harmonica-club.png",
    "太平國小口琴隊": "taiping-elementary-harmonica.jpg",
    "萬興國小口琴隊": "wanxing-elementary-harmonica.jpg",
    "Brendan Power": "brendan-power.jpg",
    "Steve Baker": "steve-baker.jpg",
    "Deak Harp": "deak-harp.jpg",
    "Fata Morgana 口琴四重奏": "fata-morgana.jpg",
    "Dror Adler / Adler Trio": "dror-adler.jpg",
    "吳詠隆": "wu-yung-lung.jpg",
    "藍波口琴教室": "bluebo-harmonica.jpg",
    "狂響口琴樂團 Rhapsody Harmonica Ensemble": "rhapsody-harmonica.jpg",
    "桃園玩口琴": "taoyuan-harmonica.jpg",
    "臺北黃石口琴樂團": "taipei-yellowstone.jpg",
    "狂響逗嘴鼓口琴樂坊": "rhapsody-drum-studio.jpg",
    "英皇書院同學會小學口琴隊": "kcobaps-harmonica.jpg",
    "黃志榮 Wesley Wong": "wesley-wong.jpg",
    "香港中華基督教青年會口琴樂團": "hk-chinese-ymca-harmonica.jpg",
    "海南會館口琴樂團": "hnhk-harmonica.jpg",
    "林家靖 Rolabo Lin": "rolabo-lin.jpg",
    "唐雪婷 Sharene Tang": "sharene-tang.jpg",
    "Boris Plotnikov": "boris-plotnikov.jpg",
    "Perfect Fourth": "perfect-fourth.jpg",
    "Reyharp and Balawan Project": "reyharp.jpg",
    "陳軍凱 Kif Valentine": "kif-valentine.jpg",
    "Orchestra Hohnerklang": "orchestra-hohnerklang.jpg",
    "Spring Harp Fest": "spring-harp-fest.jpg",
    "Hohner 音樂院（特羅辛根）": "hohner-konservatorium.jpg",
    "蔡明勳": "minghsun-tsai.jpg",
    "口琴音樂賽事中心": "aphfhx-events-center.jpg",
    "何東中學口琴隊": "hotung-secondary-harmonica.jpg",
    "莊庭皓 Ivan Chong": "ivan-chong.jpg",
    "Yotam Ben-Or": "yotam-ben-or.jpg",
    "Rivet 口琴重奏": "rivet-harmonica.png",
    "Jens Bunge": "jens-bunge.jpg",
    "黃啟書 Openbook Huang": "openbook-huang.jpg",
    "Veloz Harmonica Quartet": "veloz-harmonica.jpg",
    "第二屆海峽兩岸（蕉城）口琴文化週": "jiaocheng-harmonica-week.jpg",
    "「天鵝自由呼吸」寧波口琴節": "ningbo-harmonica-festival.jpg",
    "Federico Linari": "federico-linari.jpg",
    "Indiara Sfair": "indiara-sfair.jpg",
    "Tony Eyers": "tony-eyers.jpg",
    "Julien Cormier": "julien-cormier.jpg",
    "王元懋": "yuanmao-wang.jpg",
    "龍登杰": "long-deng-jie.jpg",
    "Tian Long Li": "tian-long-li.jpg",
    "中國大眾音協口琴樂團": "cpma-harmonica-ensemble.png",
    "劉銘澤": "liu-mingze.png",
    "林津鋒": "lin-jinfeng.jpg",
    "藍饃饃": "bunmonica-du.jpg",
    "TOMBO ハーモニカ・ソサイエティ": "tombo-harmonica-society.png",
    "Korea Harmonica Orchestra": "korea-harmonica-orchestra.png",
    "武漢理工大學學生星一口琴協會": "wuhan-university-technology.png",
    "Ivan Marcio": "ivan-marcio.jpg",
    "Ian Lofamia": "ian-lofamia.jpg",
    "Michał Kielak": "michal-kielak.jpg",
    "SUZUKI Harmonica": "suzuki-harmonica.png",
    "C.A. SEYDEL SÖHNE": "seydel-harmonica.png",
    "SHG Hering Harmonicas": "hering-harmonica.png",
    "香港兒童合唱團口琴課程": "hkcc-harmonica.png",
    "基隆社區大學就是吹口琴": "keelung-community-harmonica.jpg",
    "류선웅 Sunwoong Ryu": "sunwoong-ryu.jpg",
    "梁栢渝 Ramiel Leung": "ramiel-leung.jpg",
    "白燕生": "bai-yansheng.png",
    "陳詩霖": "chen-shilin.png",
    "張雅誥": "chong-ah-kow.png",
    "黃浚宇": "wong-chun-yu.png",
    "楊樂": "le-yang.jpg",
    "張錫範": "seokbeom-jang.png",
    "Into The Harmonica 口琴學院": "into-the-harmonica.jpg",
    "韓國口琴領袖協會": "korea-harmonica-leaders.jpg",
}
TAIPEI_TZ = timezone(timedelta(hours=8))
AVATAR_PLATFORM_PRIORITY = {
    "instagram": 0,
    "facebook": 1,
    "youtube": 2,
}
DEFAULT_AVATAR_PLATFORM_PRIORITY = 99
PROFILE_ID_ALIASES = {
    "ig_hkharmonica": ("Breathe with the Harmonica",),
    "web_matthew_yip_thmf": ("葉梓翀",),
    "web_liu_mingze_aphf": ("劉銘澤",),
    "ig_ntubluesound": ("臺灣口琴樂團",),
    "ig_taiwanharmonica": (
        "BBG 口琴三重奏",
        "Miss H. 口琴樂團",
        "Orion 口琴樂團",
        "Golden Bird Harmonica",
        "Don't Cry Ensemble",
        "Comet Harmonica Ensemble",
        "AcousTek Harmonica Ensemble",
        "自由的口琴樂團",
        "巴國聯軍",
        "龍騎士口琴樂團",
        "海豚星樂團",
    ),
    "yt_sihf_uv5mk": (
        "Choi Suhong 최수홍",
        "Crossover Harmonica Ensemble",
        "Chishu Huang",
        "Project X",
    ),
    "yt_seoulharmonicaorchestra": (
        "Seoul BLUE Harmonica Ensemble",
        "Seoul RED Harmonica Ensemble",
        "Seoul THE DREAM Harmonica Orchestra",
    ),
    "ig_whf_world_harmonica_festival": (
        "Kitauji Sextet",
        "Resonance Storm",
        "Heartstrings in Harmony",
        "Paskho Harmonica Ensemble",
        "Kyber Harmonica Ensemble",
    ),
    "manual_aphf_2026": (
        "第五屆華夏（寧德）口琴藝術周",
        "第二屆「敦煌杯」線上口琴大賽",
        "「琴溯伏羲・律動天水」口琴藝術展演",
        "「琴韻東坡・簧鳴西南」口琴藝術展演",
        "濟南大眾口琴樂團",
        "鄭州大眾口琴樂團",
        "上海豫園口琴樂團",
        "傅泓亮",
        "中國大眾音協口琴樂團",
        "無錫市人民政府（亞太口琴藝術週資訊）",
        "Tony Eyers",
        "Angelberto Pibe Árcega",
        "Julien Cormier",
    ),
    "ig_ivanmarciogaita": ("Ivan Marcio",),
    "web_michal_kielak": ("Michał Kielak",),
    "web_ian_lofamia_giliw": ("Ian Lofamia",),
    "web_suzuki_harmonica": ("SUZUKI Harmonica",),
    "web_seydel_harmonica": ("C.A. SEYDEL SÖHNE",),
    "web_shg_hering_harmonica": ("SHG Hering Harmonicas",),
    "manual_china_harmonica_committee": (
        "中國大眾音樂協會口琴考級網",
        "東方口琴博物館",
        "東方口琴樂團",
    ),
}
TAG_VALUE_SPLIT_RE = re.compile(r"\s*(?:[,，、/／+&]|\band\b|\s+)\s*", re.IGNORECASE)
TAG_FORBIDDEN_CHARS_RE = re.compile(r"[,，、/／+&\s]")
TEXT_PART_SPLIT_RE = re.compile(r"\s*(?:[/／；;、,，+&]|\band\b)\s*", re.IGNORECASE)
LEGACY_TAI = "\u53f0"
TAIWAN_ORTHOGRAPHY_REPLACEMENTS = (
    (f"{LEGACY_TAI}灣", "臺灣"),
    (f"{LEGACY_TAI}北", "臺北"),
    (f"{LEGACY_TAI}中", "臺中"),
    (f"{LEGACY_TAI}南", "臺南"),
)
TAG_CANONICAL_REPLACEMENTS = {
    "學校社團": "學生社團",
    "學校": "學生社團",
    "青年": "學生社團",
    "學校青年": "學生社團",
    "學校正式課程": "課程",
    "學校教學平台": "課程",
    "個人": "演奏者",
    "團體": "團體樂團",
    "樂團": "團體樂團",
    "協會團體": "協會",
    "活動": "活動資訊",
    "活動入口": "活動資訊",
    "資訊入口": "活動資訊",
    "資料來源": "活動資訊",
    "參考來源": "活動資訊",
    "比賽入口": "比賽",
    "國際活動": "國際交流",
    "國際交流活動": "國際交流",
    "國際團體": "國際交流",
    "教學工作室": "教學",
    "教學影片來源": "教學",
    "影片來源": "教學",
    "教學維修影片來源": "教學器材",
    "維修": "教學器材",
    "樂器行": "教學器材",
    "樂器商": "教學器材",
    "口琴專賣店": "教學器材",
    "場館": "場館平台",
    "文化局": "場館平台",
    "藝文中心": "場館平台",
    "文化平台": "場館平台",
    "教育入口": "課程",
    "教育機構": "課程",
    "演出企劃": "演出",
}
DISCARDED_SOURCE_TAGS = {"其他來源", "口琴"}
SOURCE_TYPE_TAGS = {
    "個人": "演奏者",
    "學校社團": "學生社團",
    "團體": "團體樂團",
    "活動與比賽": "活動資訊",
    "樂器與器材": "教學器材",
    "品牌": "品牌",
    "協會": "協會",
    "場館與平台": "場館平台",
}

SOURCE_TYPE_OVERRIDES = {
    "theduet獨特音樂": "品牌",
    "theduet": "品牌",
    "簧格音樂有限公司": "品牌",
    "林家靖rolabolin": "個人",
    "anafternoonwithharmonica": "品牌",
    "fromharmonicatomusic": "品牌",
    "吹出好心琴oufrog": "品牌",
    "oufrog": "品牌",
    "巴巴口琴坊": "品牌",
    "babaharmonicastudio": "品牌",
    "蔡明憲dmingstudio": "品牌",
    "dmingstudio": "品牌",
    "口袋琴房pocketharmonic": "品牌",
    "pocketharmonic": "品牌",
    "韋笙堡口琴weissenbergharmonicas": "樂器與器材",
    "weissenbergharmonicas": "樂器與器材",
    "upsidedown": "團體",
    "臺中市中華口琴會": "協會",
    "高雄市口琴協會": "協會",
    "高雄市兒童口琴樂團高雄市口琴協會": "協會",
}

SOURCE_FILES = [
    ("watchlist", PROJECT_ROOT / "data" / "sources" / "harmonica-source-watchlist-public.csv"),
]

LINK_FIELDS = [
    ("website_url", "網站"),
    ("fb_url", "Facebook"),
    ("ig_url", "Instagram"),
    ("youtube_url", "YouTube"),
    ("x_url", "X"),
    ("threads_url", "Threads"),
    ("tiktok_url", "TikTok"),
    ("contact_public_url", "公開聯絡"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    malformed = [index for index, row in enumerate(rows, start=2) if None in row]
    if malformed:
        joined = ", ".join(str(index) for index in malformed[:10])
        suffix = " ..." if len(malformed) > 10 else ""
        raise ValueError(f"CSV rows contain extra columns in {path}: {joined}{suffix}")
    return rows


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def clean(value: str | None) -> str:
    return (value or "").strip()


def normalize_taiwan_orthography(value: str | None) -> str:
    text = clean(value)
    for source, target in TAIWAN_ORTHOGRAPHY_REPLACEMENTS:
        text = text.replace(source, target)
    return text


def legacy_taiwan_orthography(value: str | None) -> str:
    text = clean(value)
    for source, target in TAIWAN_ORTHOGRAPHY_REPLACEMENTS:
        text = text.replace(target, source)
    return text


def normalize_tag_value(value: str | None) -> list[str]:
    tag = normalize_taiwan_orthography(value)
    if tag in DISCARDED_SOURCE_TAGS:
        return []
    key = normalize_key(tag)
    replacement = TAG_CANONICAL_REPLACEMENTS.get(tag) or TAG_CANONICAL_REPLACEMENTS.get(key)
    if isinstance(replacement, list):
        return [item for item in replacement if item]
    if isinstance(replacement, tuple):
        return [item for item in replacement if item]
    if replacement:
        return [replacement]
    return [tag] if tag else []


def normalize_tag_values(value: Any, *, limit: int = 8) -> list[str]:
    if isinstance(value, str):
        raw_values: list[Any] = [value]
    elif isinstance(value, list):
        raw_values = value
    else:
        raw_values = []

    tags: list[str] = []
    for raw in raw_values:
        text = normalize_taiwan_orthography(str(raw or ""))
        if not text:
            continue
        for tag in TAG_VALUE_SPLIT_RE.split(text):
            for normalized_tag in normalize_tag_value(tag.strip()):
                if normalized_tag and normalized_tag not in tags:
                    tags.append(normalized_tag)
                if len(tags) >= limit:
                    return tags
    return tags


def merge_source_tags(entry: dict[str, object], tags: list[str], *, limit: int = 8) -> list[str]:
    merged = [tag for tag in tags if tag and tag not in DISCARDED_SOURCE_TAGS]
    type_tag = SOURCE_TYPE_TAGS.get(str(entry.get("type") or ""))
    if type_tag and type_tag not in merged:
        merged.insert(0, type_tag)
    return merged[:limit]


def text_parts(value: str | None, *, limit: int = 6) -> list[str]:
    parts: list[str] = []
    for part in TEXT_PART_SPLIT_RE.split(normalize_taiwan_orthography(value)):
        part = part.strip()
        if part and part not in parts:
            parts.append(part)
        if len(parts) >= limit:
            break
    return parts


def human_join(parts: list[str]) -> str:
    parts = [part for part in parts if part]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]}與{parts[1]}"
    return "、".join(parts[:-1]) + f"與{parts[-1]}"


def readable_text(value: str | None) -> str:
    return human_join(text_parts(value, limit=4))


def normalize_key(value: str | None) -> str:
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", clean(value).casefold())


def is_public_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def parse_time(value: str | None) -> datetime | None:
    raw = clean(value)
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_time_label(value: datetime) -> str:
    return value.astimezone(TAIPEI_TZ).strftime("%Y-%m-%d %H:%M")


def url_handles(url: str) -> set[str]:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold().removeprefix("www.")
    path_parts = [
        urllib.parse.unquote(part).strip("@")
        for part in parsed.path.split("/")
        if part.strip("/")
    ]
    handles: set[str] = set()
    if not path_parts:
        return handles
    first = path_parts[0]
    if "instagram.com" in host or "threads.net" in host:
        if first not in {"p", "reel", "reels", "tv", "stories"}:
            handles.add(first)
    elif "facebook.com" in host:
        if first not in {"p", "people", "pages", "profile.php"}:
            handles.add(first)
    elif host in {"x.com", "twitter.com"}:
        if first not in {"home", "i", "intent", "search", "share", "hashtag", "explore"}:
            handles.add(first)
    elif "tiktok.com" in host:
        if first.startswith("@"):
            handles.add(first)
    elif "youtube.com" in host and first.startswith("@"):
        handles.add(first)
    elif "youtube.com" in host and first not in {"channel", "c", "user"}:
        handles.add(first)
    return {normalize_key(handle) for handle in handles if handle}


def source_initials(source: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", source or "")
    if words:
        return "".join(word[0].upper() for word in words[:3])
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", source or "")
    if chinese_chars:
        return "".join(chinese_chars[:2])
    return "H"


def entry_match_keys(entry: dict[str, object]) -> set[str]:
    keys = {
        normalize_key(str(entry.get("name") or "")),
        normalize_key(str(entry.get("nameEn") or "")),
    }
    for alias in entry.get("aliases", []):
        keys.add(normalize_key(str(alias or "")))
    keywords = str(entry.get("keywords") or "")
    if keywords:
        keys.add(normalize_key(keywords))
    for link in entry.get("links", []):
        if isinstance(link, dict):
            keys.update(url_handles(str(link.get("url") or "")))
    return {key for key in keys if key}


def profile_match_keys(profile: dict[str, Any]) -> set[str]:
    keys = {
        normalize_key(str(profile.get("name") or "")),
        normalize_key(str(profile.get("title") or "")),
        normalize_key(str(profile.get("account") or "")),
        normalize_key(str(profile.get("username") or "")),
    }
    # Some monitored profiles deliberately carry two public names (for
    # example, an ensemble and its parent association).  Treat each explicit
    # slash-delimited name as an alias so both directory entries can reuse the
    # verified profile and avatar without a duplicate override.
    for field in ("name", "title"):
        value = str(profile.get(field) or "")
        for alias in re.split(r"\s*[/／]\s*", value):
            keys.add(normalize_key(alias))
    for alias in profile.get("aliases") or []:
        keys.add(normalize_key(str(alias or "")))
    for alias in PROFILE_ID_ALIASES.get(str(profile.get("id") or ""), ()):
        keys.add(normalize_key(alias))
    source_id = str(profile.get("id") or "")
    for prefix in ("ig_", "fb_", "yt_", "youtube_", "x_", "twitter_", "threads_", "tiktok_"):
        if source_id.startswith(prefix):
            keys.add(normalize_key(source_id[len(prefix) :]))
    for field in ("account", "username", "profile_url", "url"):
        value = str(profile.get(field) or "")
        if is_public_url(value):
            keys.update(url_handles(value))
    return {key for key in keys if key}


def monitor_source_profile_url(source: dict[str, Any]) -> str:
    for field in ("profile_url", "source_profile_url", "url"):
        value = str(source.get(field) or "").strip()
        if is_public_url(value):
            return value

    account = str(source.get("account") or source.get("username") or "").strip().strip("/")
    if not account:
        return ""
    platform = str(source.get("platform") or source.get("type") or "").casefold()
    account = account.removeprefix("@")
    if "instagram" in platform:
        return f"https://www.instagram.com/{urllib.parse.quote(account)}/"
    if "facebook" in platform:
        return f"https://www.facebook.com/{account}/"
    if "youtube" in platform:
        if account.startswith(("channel/", "c/", "user/")):
            return f"https://www.youtube.com/{account}"
        return f"https://www.youtube.com/@{urllib.parse.quote(account)}"
    if platform in {"x", "twitter"} or "twitter" in platform:
        return f"https://x.com/{urllib.parse.quote(account)}"
    if "threads" in platform:
        return f"https://www.threads.net/@{urllib.parse.quote(account)}"
    if "tiktok" in platform:
        tiktok_account = account if account.startswith("@") else f"@{account}"
        return f"https://www.tiktok.com/{urllib.parse.quote(tiktok_account)}"
    return ""


def monitor_source_feed_url(source: dict[str, Any]) -> str:
    for field in ("feed_url", "rss_url"):
        value = str(source.get(field) or "").strip()
        if is_public_url(value):
            return value

    rsshub_base = str(source.get("rsshub_base") or "").rstrip("/")
    route = str(source.get("route") or "")
    username = str(source.get("username") or source.get("account") or "").strip()
    if rsshub_base and route and username:
        return f"{rsshub_base}{route.format(username=urllib.parse.quote(username))}"
    return ""


def public_monitor_source(source: dict[str, Any]) -> dict[str, str]:
    username = normalize_taiwan_orthography(str(source.get("username") or source.get("account") or ""))
    return {
        "id": str(source.get("id") or ""),
        "name": normalize_taiwan_orthography(str(source.get("name") or source.get("title") or source.get("id") or "公開來源")),
        "platform": str(source.get("platform") or source.get("type") or "unknown"),
        "type": str(source.get("type") or "unknown"),
        "username": username,
        "profileUrl": monitor_source_profile_url(source),
        "feedUrl": monitor_source_feed_url(source),
    }


def monitor_sources_by_key() -> dict[str, list[dict[str, str]]]:
    config = read_json(SOCIAL_SOURCES, {"sources": []})
    keyed: dict[str, list[dict[str, str]]] = {}
    seen: set[tuple[str, str]] = set()
    for source in config.get("sources", []):
        if not source.get("enabled", True) or source.get("type") == "jsonl":
            continue
        public_source = public_monitor_source(source)
        source_id = public_source["id"]
        for key in profile_match_keys(source):
            identity = (key, source_id)
            if identity in seen:
                continue
            keyed.setdefault(key, []).append(public_source)
            seen.add(identity)
    return keyed


def apply_monitor_sources(entry: dict[str, object], keyed_sources: dict[str, list[dict[str, str]]]) -> None:
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for key in entry_match_keys(entry):
        for source in keyed_sources.get(key, []):
            source_id = source.get("id") or ""
            if not source_id or source_id in seen:
                continue
            sources.append(source)
            seen.add(source_id)
    if sources:
        entry["monitorSources"] = sorted(
            sources,
            key=lambda item: (
                str(item.get("platform") or ""),
                str(item.get("name") or ""),
                str(item.get("id") or ""),
            ),
        )


def candidate_match_keys(row: dict[str, Any]) -> set[str]:
    keys = {
        normalize_key(str(row.get("source_name") or "")),
        normalize_key(str(row.get("account") or "")),
    }
    source_id = str(row.get("source_id") or "")
    for prefix in ("ig_", "fb_", "yt_", "youtube_", "x_", "twitter_", "threads_", "tiktok_"):
        if source_id.startswith(prefix):
            keys.add(normalize_key(source_id[len(prefix) :]))
    if row.get("url"):
        keys.update(url_handles(str(row.get("url"))))
    return {key for key in keys if key}


def entry_tag_fingerprint(entry: dict[str, object]) -> str:
    payload = {
        "name": entry.get("name") or "",
        "nameEn": entry.get("nameEn") or "",
        "aliases": entry.get("aliases") or [],
        "category": entry.get("category") or "",
        "type": entry.get("type") or "",
        "region": entry.get("region") or "",
        "cityOrFocus": entry.get("cityOrFocus") or "",
        "summary": entry.get("structuredSummary") or entry.get("summary") or "",
        "keywords": entry.get("keywords") or "",
        "links": entry.get("links") or [],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def entry_tag_fingerprint_variants(entry: dict[str, object]) -> list[str]:
    text_fields = [
        "name",
        "nameEn",
        "category",
        "type",
        "region",
        "cityOrFocus",
        "summary",
        "keywords",
    ]
    field_values: list[list[str]] = []
    for field in text_fields:
        current = str((entry.get("structuredSummary") if field == "summary" else entry.get(field)) or "")
        legacy = legacy_taiwan_orthography(current)
        field_values.append([current] if legacy == current else [current, legacy])

    aliases = [str(value or "") for value in entry.get("aliases", [])]
    legacy_aliases = [legacy_taiwan_orthography(value) for value in aliases]
    alias_variants = [aliases] if legacy_aliases == aliases else [aliases, legacy_aliases]

    fingerprints: list[str] = []
    seen: set[str] = set()
    for alias_values in alias_variants:
        for variant_values in itertools.product(*field_values):
            payload = dict(zip(text_fields, variant_values))
            payload["aliases"] = alias_values
            payload["links"] = entry.get("links") or []
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if fingerprint not in seen:
                fingerprints.append(fingerprint)
                seen.add(fingerprint)
    return fingerprints


def canonical_link_key(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.casefold().removeprefix("www.")
    path = "/".join(
        urllib.parse.unquote(part).strip().strip("@").casefold()
        for part in parsed.path.split("/")
        if part.strip("/")
    )
    if host in {"facebook.com", "m.facebook.com"} and path == "profile.php":
        profile_id = urllib.parse.parse_qs(parsed.query).get("id", [""])[0]
        return f"facebook.com/profile.php?id={profile_id}" if profile_id.isdigit() else ""
    if any(
        domain in host
        for domain in ("facebook.com", "instagram.com", "youtube.com", "x.com", "twitter.com", "threads.net", "tiktok.com")
    ):
        handles = sorted(url_handles(url))
        if handles:
            return f"{host}:{handles[0]}"
    return f"{host}/{path}".rstrip("/")


def entry_identity_keys(entry: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for link in entry.get("links", []):
        if isinstance(link, dict):
            key = canonical_link_key(str(link.get("url") or ""))
            if key:
                keys.add(key)
    return keys


def social_identity_keys(entry: dict[str, object]) -> set[str]:
    keys: set[str] = set()
    for link in entry.get("links", []):
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "")
        host = urllib.parse.urlparse(url).netloc.casefold()
        if any(
            domain in host
            for domain in ("facebook.com", "instagram.com", "youtube.com", "x.com", "twitter.com", "threads.net", "tiktok.com")
        ):
            key = canonical_link_key(url)
            if key:
                keys.add(key)
    return keys


def entry_text(entry: dict[str, object]) -> str:
    return " ".join(
        str(entry.get(field) or "")
        for field in (
            "name",
            "nameEn",
            "category",
            "type",
            "country",
            "region",
            "cityOrFocus",
            "summary",
            "structuredSummary",
            "keywords",
        )
    )


def source_like(entry: dict[str, object]) -> bool:
    text = entry_text(entry)
    return any(word in text for word in ("來源", "教學", "工作室", "教室", "專賣店", "品牌", "器材", "平台"))


def person_like(entry: dict[str, object]) -> bool:
    return "個人" in entry_text(entry)


def individually_branded_source_pair(left: dict[str, object], right: dict[str, object]) -> bool:
    left_is_person = "個人" in str(left.get("type") or "")
    right_is_person = "個人" in str(right.get("type") or "")
    if left_is_person == right_is_person:
        return False
    if normalize_key(str(left.get("name") or "")) == normalize_key(str(right.get("name") or "")):
        return False
    return source_like(right if left_is_person else left)


def duplicate_entries(left: dict[str, object], right: dict[str, object]) -> bool:
    if normalize_key(str(left.get("name") or "")) == normalize_key(str(right.get("name") or "")):
        return True

    if individually_branded_source_pair(left, right):
        return False

    left_keys = entry_identity_keys(left)
    right_keys = entry_identity_keys(right)
    shared_keys = left_keys & right_keys
    if len(shared_keys) >= 2:
        return True

    left_social = social_identity_keys(left)
    right_social = social_identity_keys(right)
    shared_social = left_social & right_social
    if shared_social and ((person_like(left) and source_like(right)) or (person_like(right) and source_like(left))):
        return True

    return False


def entry_score(entry: dict[str, object]) -> tuple[int, int, int, int]:
    name = str(entry.get("name") or "")
    generic_penalty = sum(word in name for word in ("相關", "子來源", "新團體", "參考來源"))
    return (
        len(entry.get("links", []) or []),
        -generic_penalty,
        1 if source_like(entry) and not person_like(entry) else 0,
        -len(name),
    )


def best_entry(entries: list[dict[str, object]]) -> dict[str, object]:
    return max(entries, key=entry_score)


def summary_score(entry: dict[str, object], primary: dict[str, object]) -> tuple[int, int, int, int, int, int]:
    summary = str(entry.get("structuredSummary") or entry.get("summary") or "")
    noisy_words = ("相關來源", "監看", "觀察", "線索", "資料來源", "參考來源")
    generic_name_words = ("相關", "子來源", "新團體", "參考來源")
    parts = [part for part in summary.split(" / ") if part]
    return (
        1 if entry.get("source") == "club" and entry.get("category") == "學校社團" else 0,
        1 if entry is primary else 0,
        -sum(word in summary for word in noisy_words),
        -sum(word in str(entry.get("name") or "") for word in generic_name_words),
        -abs(len(parts) - 3),
        -len(summary),
    )


def best_summary_entry(entries: list[dict[str, object]], primary: dict[str, object]) -> dict[str, object]:
    return max(entries, key=lambda entry: summary_score(entry, primary))


def merge_unique_strings(values: list[str]) -> list[str]:
    merged: list[str] = []
    for value in values:
        text = clean(value)
        if text and text not in merged:
            merged.append(text)
    return merged


def merge_links(entries: list[dict[str, object]]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in sorted(entries, key=lambda item: -len(item.get("links", []) or [])):
        for link in entry.get("links", []):
            if not isinstance(link, dict):
                continue
            url = str(link.get("url") or "")
            key = canonical_link_key(url)
            if not url or key in seen:
                continue
            links.append({"label": str(link.get("label") or "公開連結"), "url": url})
            seen.add(key)
    return links


def merge_group(entries: list[dict[str, object]]) -> dict[str, object]:
    primary = best_entry(entries)
    summary_entry = best_summary_entry(entries, primary)
    aliases = merge_unique_strings(
        [
            str(value)
            for entry in entries
            for value in (entry.get("name"), entry.get("nameEn"))
            if value and value != primary.get("name") and value != primary.get("nameEn")
        ]
    )
    summaries = merge_unique_strings([str(entry.get("structuredSummary") or "") for entry in entries])
    descriptions = merge_unique_strings([str(entry.get("summary") or "") for entry in entries])
    keywords = merge_unique_strings([str(entry.get("keywords") or "") for entry in entries])
    types = merge_unique_strings([str(entry.get("type") or "") for entry in entries])
    original_types = merge_unique_strings([str(entry.get("originalType") or "") for entry in entries])
    countries = merge_unique_strings([str(entry.get("country") or "") for entry in entries])
    regions = merge_unique_strings([str(entry.get("region") or "") for entry in entries])
    focuses = merge_unique_strings([str(entry.get("cityOrFocus") or "") for entry in entries])

    merged = dict(primary)
    merged["id"] = "+".join(str(entry.get("id") or "") for entry in entries if entry.get("id"))
    merged["aliases"] = aliases
    merged["links"] = merge_links(entries)
    merged["type"] = " / ".join(types[:3])
    merged["originalType"] = " / ".join(original_types[:3])
    merged["country"] = str(primary.get("country") or (countries[0] if countries else ""))
    merged["region"] = " / ".join(regions[:3])
    merged["cityOrFocus"] = " / ".join(focuses[:3])
    merged["structuredSummary"] = str(summary_entry.get("structuredSummary") or " / ".join(summaries[:1]))
    merged["summary"] = str(summary_entry.get("summary") or (descriptions[0] if descriptions else "公開口琴來源。"))
    merged["keywords"] = " ".join(keywords)
    merged["source"] = "+".join(sorted({str(entry.get("source") or "") for entry in entries if entry.get("source")}))
    return merged


def merge_duplicate_entries(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    parent = list(range(len(entries)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left: int, right: int) -> None:
        root_left = find(left)
        root_right = find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    for left_index, left in enumerate(entries):
        for right_index in range(left_index + 1, len(entries)):
            if duplicate_entries(left, entries[right_index]):
                union(left_index, right_index)

    groups: dict[int, list[dict[str, object]]] = {}
    for index, entry in enumerate(entries):
        groups.setdefault(find(index), []).append(entry)
    return [merge_group(group) for group in groups.values()]


def fallback_source_tags(entry: dict[str, object]) -> list[str]:
    text = " ".join(
        str(entry.get(field) or "")
        for field in ("name", "nameEn", "category", "type", "country", "region", "cityOrFocus", "summary", "structuredSummary", "keywords")
    )
    tags: list[str] = []
    category = str(entry.get("category") or "")
    if category:
        tags.append(category)
    if category == "學校社團":
        tags.append("學生社團")
        if any(word in text for word in ("大學", "大專")):
            tags.append("大專社團")
        if any(word in text for word in ("高中", "高級中學")):
            tags.append("高中社團")
    for needle, tag in [
        ("樂團", "團體樂團"),
        ("團體", "團體樂團"),
        ("個人", "演奏者"),
        ("教學", "教學"),
        ("課程", "課程"),
        ("工作室", "工作室"),
        ("音樂節", "音樂節"),
        ("比賽", "比賽"),
        ("成發", "成發"),
        ("半音階", "半音階"),
        ("複音", "複音"),
        ("十孔", "十孔"),
        ("重奏", "重奏"),
        ("國際", "國際交流"),
    ]:
        if needle in text:
            tags.append(tag)
    return normalize_tag_values(tags)


def source_tag_cache() -> dict[str, dict[str, Any]]:
    if not SOURCE_TAG_CACHE.exists():
        return {}
    data = json.loads(SOURCE_TAG_CACHE.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else {}
    return items if isinstance(items, dict) else {}


def apply_source_tags(entry: dict[str, object], cache: dict[str, dict[str, Any]]) -> None:
    cached: dict[str, Any] = {}
    for fingerprint in entry_tag_fingerprint_variants(entry):
        cached = cache.get(fingerprint) or {}
        if cached:
            break
    tags = cached.get("sourceTags") or cached.get("tags") or []
    source_tags = normalize_tag_values(tags)
    entry["sourceTags"] = merge_source_tags(entry, source_tags if source_tags else fallback_source_tags(entry))

    summary = normalize_taiwan_orthography(str(cached.get("sourceSummary") or cached.get("summary") or ""))
    if summary:
        entry["sourceSummary"] = summary
        entry["summary"] = summary

    reason = normalize_taiwan_orthography(str(cached.get("sourceTagReason") or cached.get("reason") or ""))
    if reason:
        entry["sourceTagReason"] = reason


def cached_avatar_url(avatar_source_url: str) -> str:
    if not avatar_source_url:
        return ""
    if avatar_source_url.startswith("/assets/"):
        return avatar_source_url
    digest = hashlib.sha256(avatar_source_url.encode("utf-8")).hexdigest()[:20]
    existing = sorted(SOURCE_AVATAR_DIR.glob(f"{digest}.*"))
    if not existing:
        return ""
    return f"/assets/source-avatars/{existing[0].name}"


def sync_curated_source_avatars() -> None:
    SOURCE_AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    for filename in CURATED_SOURCE_AVATARS.values():
        source = CURATED_SOURCE_AVATAR_DIR / filename
        if not source.exists():
            raise SystemExit(f"Missing curated source avatar: {source.relative_to(PROJECT_ROOT)}")
        target = SOURCE_AVATAR_DIR / filename
        if not target.exists() or target.read_bytes() != source.read_bytes():
            shutil.copy2(source, target)


def profile_platform(profile: dict[str, Any]) -> str:
    platform = str(profile.get("platform") or "").casefold()
    if platform:
        return platform

    source_id = str(profile.get("id") or "").casefold()
    if source_id.startswith("ig_"):
        return "instagram"
    if source_id.startswith("fb_"):
        return "facebook"
    if source_id.startswith(("yt_", "youtube_")):
        return "youtube"

    profile_url = str(profile.get("profile_url") or profile.get("account") or "").casefold()
    if "instagram.com" in profile_url:
        return "instagram"
    if "facebook.com" in profile_url:
        return "facebook"
    if "youtube.com" in profile_url or "youtu.be" in profile_url:
        return "youtube"
    return platform


def avatar_platform_priority(platform: str) -> int:
    return AVATAR_PLATFORM_PRIORITY.get(platform, DEFAULT_AVATAR_PLATFORM_PRIORITY)


def avatar_payload_rank(payload: dict[str, Any]) -> tuple[int, int, str]:
    priority = payload.get("avatarPriority")
    if priority in (None, ""):
        priority = DEFAULT_AVATAR_PLATFORM_PRIORITY
    return (
        0 if payload.get("avatarUrl") else 1,
        int(priority),
        str(payload.get("avatarSource") or ""),
    )


def avatar_profiles_by_key() -> dict[str, dict[str, Any]]:
    if not SOURCE_PROFILES_CACHE.exists():
        return {}
    data = json.loads(SOURCE_PROFILES_CACHE.read_text(encoding="utf-8"))
    profiles = data.get("profiles") if isinstance(data, dict) else {}
    if not isinstance(profiles, dict):
        return {}

    by_key: dict[str, dict[str, Any]] = {}
    for profile_id, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        # The cache is keyed by source ID, while older cached payloads do not
        # repeat that ID inside the value.  Restore it before alias matching so
        # durable PROFILE_ID_ALIASES work for both old and new cache records.
        profile = {"id": str(profile_id), **profile}
        platform = profile_platform(profile)
        source_name = str(profile.get("name") or profile.get("title") or "")
        avatar = cached_avatar_url(
            str(profile.get("avatar_url") or profile.get("avatar_source_url") or "")
        )
        payload = {
            "avatarUrl": avatar,
            "sourceInitials": source_initials(source_name),
            "avatarSource": source_name,
            "avatarPlatform": platform,
            "avatarPriority": avatar_platform_priority(platform),
        }
        for key in profile_match_keys(profile):
            existing = by_key.get(key)
            if existing and avatar_payload_rank(existing) <= avatar_payload_rank(payload):
                continue
            by_key[key] = payload
    return by_key


def apply_avatar(entry: dict[str, object], avatars: dict[str, dict[str, Any]]) -> None:
    matches = [
        avatars[key]
        for key in sorted(entry_match_keys(entry))
        if key in avatars
    ]
    best = min(matches, key=avatar_payload_rank) if matches else {}
    entry["avatarUrl"] = str(best.get("avatarUrl") or "")
    curated_filename = CURATED_SOURCE_AVATARS.get(str(entry.get("name") or ""))
    if curated_filename:
        entry["avatarUrl"] = f"/assets/source-avatars/{curated_filename}"
    entry["sourceInitials"] = source_initials(str(entry.get("name") or best.get("avatarSource") or ""))


def read_candidates() -> list[dict[str, Any]]:
    if not CANDIDATES.exists():
        return []
    rows: list[dict[str, Any]] = []
    with CANDIDATES.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def is_source_page_backfill(row: dict[str, Any]) -> bool:
    if row.get("raw_source") == "public-link-backfill":
        return True
    media_type = str(row.get("media_type") or "")
    post_id = str(row.get("post_id") or "")
    return media_type in {"source_page", "directory_source_page"} or post_id.startswith("source_page:")


def latest_updates_by_key() -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in read_candidates():
        if is_source_page_backfill(row):
            continue
        posted = parse_time(str(row.get("posted_at") or row.get("seen_at") or ""))
        if posted is None:
            continue
        update = {
            "dt": posted,
            "source": normalize_taiwan_orthography(str(row.get("source_name") or row.get("source_id") or "")),
            "source_id": str(row.get("source_id") or ""),
            "account": str(row.get("account") or ""),
            "url": row.get("url") or "",
            "title": normalize_taiwan_orthography(str(row.get("text") or "")),
        }
        for key in candidate_match_keys(row):
            existing = latest.get(key)
            if existing is None or posted > existing["dt"]:
                latest[key] = update
    return latest


def apply_latest_update(entry: dict[str, object], latest: dict[str, dict[str, Any]]) -> None:
    matches = [latest[key] for key in entry_match_keys(entry) if key in latest]
    if not matches:
        entry["latestUpdateAt"] = ""
        entry["latestUpdateLocal"] = ""
        entry["latestUpdateSource"] = ""
        entry["latestUpdateUrl"] = ""
        return

    update = max(matches, key=lambda item: item["dt"])
    dt = update["dt"]
    update_source = normalize_taiwan_orthography(str(update.get("source") or ""))
    entry_name = normalize_taiwan_orthography(str(entry.get("name") or ""))
    update_keys = {
        normalize_key(update_source),
        normalize_key(str(update.get("account") or "")),
    }
    source_id = str(update.get("source_id") or "")
    for prefix in ("ig_", "fb_", "yt_", "youtube_", "x_", "twitter_", "threads_", "tiktok_"):
        if source_id.startswith(prefix):
            update_keys.add(normalize_key(source_id[len(prefix) :]))
    update_keys = {key for key in update_keys if key}
    display_source = entry_name if entry_name and update_keys.intersection(entry_match_keys(entry)) else update_source
    entry["_latestUpdateSort"] = dt.timestamp()
    entry["latestUpdateAt"] = dt.isoformat()
    entry["latestUpdateLocal"] = local_time_label(dt)
    entry["latestUpdateSource"] = display_source
    entry["latestUpdateUrl"] = str(update.get("url") or "")


def link_bundle(row: dict[str, str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for field, label in LINK_FIELDS:
        url = clean(row.get(field))
        if is_public_url(url) and url not in seen:
            links.append({"label": label, "url": url})
            seen.add(url)

    opentix_query = clean(row.get("opentix_query"))
    if is_public_url(opentix_query) and opentix_query not in seen:
        links.append({"label": "OPENTIX", "url": opentix_query})

    return links


def category_for(row: dict[str, str], source: str) -> str:
    raw_type = clean(row.get("type"))
    raw_region = clean(row.get("region"))
    raw_role = clean(row.get("role"))
    raw_focus = clean(row.get("focus"))
    text = " ".join(
        clean(row.get(field))
        for field in ("type", "role", "focus", "school_or_org", "region")
    )
    if (
        source == "club"
        or "學校社團" in raw_type
        or "學校/青年" in raw_type
        or raw_role == "學校團隊"
        or "學生團隊" in raw_focus
        or "口琴社" in raw_focus
    ):
        return "學校社團"
    if "活動" in raw_type or "售票" in raw_type or "音樂節" in text or "比賽" in raw_type:
        return "活動資訊"
    if "個人" in raw_type:
        return "演奏者"
    if "團體" in raw_type or "樂團" in raw_type:
        return "團體樂團"
    if "教學" in text or "樂器" in text or "工作室" in text or "品牌" in text:
        return "教學器材"
    if "場館" in text or "文化局" in text or "平台" in text:
        return "場館平台"
    if raw_region and "臺灣" not in normalize_taiwan_orthography(raw_region):
        return "國際交流"
    return "其他來源"


def public_description(row: dict[str, str], source: str, category: str) -> str:
    country = normalize_taiwan_orthography(row.get("country"))
    school_or_org = normalize_taiwan_orthography(row.get("school_or_org"))
    focus_parts = text_parts(row.get("focus"), limit=5)
    instrument_parts = text_parts(row.get("instruments"), limit=4)
    role_parts = text_parts(row.get("role"), limit=3)
    type_parts = text_parts(row.get("type"), limit=3)

    instrument_label = human_join(instrument_parts)
    role_label = human_join(role_parts) or human_join(type_parts) or "公開來源"
    focus_without_instrument = [part for part in focus_parts if part not in instrument_parts]
    country_prefix = f"{country}的" if country else ""

    if category == "學校社團":
        org = readable_text(school_or_org) or country or "公開學校"
        if instrument_label and role_label:
            return normalize_taiwan_orthography(f"{org}的{instrument_label}{role_label}。")
        return normalize_taiwan_orthography(f"{org}的口琴學校社團。")

    if category == "活動資訊":
        focus_label = human_join(focus_without_instrument or focus_parts[:4])
        if focus_label:
            return normalize_taiwan_orthography(f"{country_prefix}{role_label}，涵蓋{focus_label}。")
        return normalize_taiwan_orthography(f"{country_prefix}{role_label}。")

    if category in {"團體樂團", "演奏者"}:
        focus_label = human_join(focus_without_instrument[:3])
        core = f"{country_prefix}{instrument_label}{role_label}" if instrument_label else f"{country_prefix}{role_label}"
        if category == "團體樂團" and len(focus_without_instrument) == 1 and focus_without_instrument[0].endswith("團體"):
            descriptor = focus_without_instrument[0].removesuffix("團體")
            return normalize_taiwan_orthography(f"{country_prefix}{descriptor}{instrument_label}{role_label}。")
        if focus_label:
            return normalize_taiwan_orthography(f"{core}，活動脈絡包含{focus_label}。")
        return normalize_taiwan_orthography(f"{core}。")

    if category == "教學器材":
        focus_label = human_join(focus_without_instrument or focus_parts[:4])
        core = f"{country_prefix}{instrument_label}{role_label}" if instrument_label else f"{country_prefix}{role_label}"
        if focus_label:
            return normalize_taiwan_orthography(f"{core}，關注{focus_label}。")
        return normalize_taiwan_orthography(f"{core}。")

    if category == "場館平台":
        focus_label = human_join(focus_without_instrument or focus_parts[:3])
        if focus_label:
            return normalize_taiwan_orthography(f"{country_prefix}{role_label}，提供{focus_label}相關資訊。")
        return normalize_taiwan_orthography(f"{country_prefix}{role_label}。")

    focus_label = human_join(focus_without_instrument or focus_parts[:3])
    if focus_label:
        return normalize_taiwan_orthography(f"{country_prefix}{role_label}，關注{focus_label}。")
    return normalize_taiwan_orthography(f"{country_prefix}{role_label}。")


def source_type_group(row: dict[str, str], category: str) -> str:
    name = normalize_taiwan_orthography(row.get("name"))
    name_en = clean(row.get("name_en"))
    override_keys = {normalize_key(value) for value in (name, name_en, f"{name}{name_en}")}
    for override_key in override_keys:
        if override_key in SOURCE_TYPE_OVERRIDES:
            return SOURCE_TYPE_OVERRIDES[override_key]

    original_type = normalize_taiwan_orthography(row.get("type"))
    role = normalize_taiwan_orthography(row.get("role"))
    focus = normalize_taiwan_orthography(row.get("focus"))
    instruments = normalize_taiwan_orthography(row.get("instruments"))
    keywords = normalize_taiwan_orthography(row.get("keywords"))
    text = " ".join([name, name_en, original_type, role, focus, instruments, keywords])
    text = f"{category} {text}"
    if any(word in text for word in ("品牌", "有限公司", "公司")):
        return "品牌"
    if "個人" in original_type or any(word in role for word in ("演出人員", "音樂家", "合作音樂家")):
        return "個人"
    if "團體" in original_type or "樂團" in original_type or any(word in role for word in ("演出團體", "樂團")):
        return "團體"
    if any(word in original_type for word in ("學校社團", "學校/青年")) or any(word in text for word in ("口琴社", "口琴隊", "校園")):
        return "學校社團"
    if any(word in text for word in ("樂器", "器材", "專賣店", "樂器商")):
        return "樂器與器材"
    if any(word in text for word in ("場館", "文化局", "藝文中心", "平台", "教育機構")):
        return "場館與平台"
    if any(word in text for word in ("協會", "口琴會", "聯盟", "連盟", "Society", "Association", "Federation")):
        return "協會"
    if any(word in text for word in ("活動", "音樂節", "比賽", "工作坊", "售票", "講座", "演出企劃", "文化平台")):
        return "活動與比賽"
    if any(word in text for word in ("樂團", "團體", "重奏", "合奏", "社群")):
        return "團體"
    if any(word in text for word in ("教學", "教室", "工作室", "課程", "教育機構", "維修", "影片來源")):
        return "樂器與器材"
    if any(word in text for word in ("資訊入口", "資料來源", "參考來源")):
        return "場館與平台"
    return "團體"


def entry_from_row(row: dict[str, str], source: str, row_number: int) -> dict[str, object] | None:
    links = link_bundle(row)
    if not links:
        return None

    name = normalize_taiwan_orthography(row.get("name"))
    if not name:
        return None

    category = category_for(row, source)
    original_type = normalize_taiwan_orthography(row.get("type"))
    city_or_focus = normalize_taiwan_orthography(row.get("city")) or normalize_taiwan_orthography(row.get("focus"))
    public_summary_parts = [
        normalize_taiwan_orthography(row.get("school_or_org")),
        normalize_taiwan_orthography(row.get("focus")),
        normalize_taiwan_orthography(row.get("instruments")),
        normalize_taiwan_orthography(row.get("role")),
    ]
    structured_summary = " / ".join(part for part in public_summary_parts if part)
    public_id = clean(row.get("public_id")) or str(row_number)
    public_id = re.sub(r"[^0-9A-Za-z_-]+", "-", public_id).strip("-")
    if not public_id:
        public_id = str(row_number)

    return {
        "id": f"{source}-{public_id}",
        "publicId": public_id,
        "name": name,
        "nameEn": normalize_taiwan_orthography(row.get("name_en")),
        "category": category,
        "type": source_type_group(row, category),
        "originalType": original_type,
        "country": normalize_taiwan_orthography(row.get("country")),
        "region": normalize_taiwan_orthography(row.get("region")),
        "cityOrFocus": city_or_focus,
        "structuredSummary": structured_summary,
        "summary": public_description(row, source, category),
        "keywords": normalize_taiwan_orthography(row.get("keywords")),
        "links": links,
        "source": source,
    }


def validate_public_entries(entries: list[dict[str, object]]) -> None:
    errors: list[str] = []
    seen_ids: set[str] = set()
    for entry in entries:
        name = str(entry.get("name") or entry.get("id") or "未命名來源")
        entry_id = str(entry.get("id") or "")
        if not entry_id:
            errors.append(f"{name}: missing public id")
        elif entry_id in seen_ids:
            errors.append(f"{name}: duplicate public id {entry_id!r}")
        seen_ids.add(entry_id)
        if not clean(str(entry.get("country") or "")):
            errors.append(f"{name}: missing country")
        summary = clean(str(entry.get("summary") or ""))
        if not summary:
            errors.append(f"{name}: missing reader summary")
        if "/" in summary or "／" in summary:
            errors.append(f"{name}: slash-style reader summary {summary!r}")
        for tag in entry.get("sourceTags") or []:
            text = str(tag or "").strip()
            if not text:
                continue
            if TAG_FORBIDDEN_CHARS_RE.search(text) or re.search(r"\band\b", text, re.IGNORECASE):
                errors.append(f"{name}: composite sourceTag {text!r}")
    if errors:
        formatted = "\n".join(f"- {error}" for error in errors[:40])
        if len(errors) > 40:
            formatted += f"\n- ... and {len(errors) - 40} more"
        raise SystemExit("Invalid public source entries:\n" + formatted)


def build_entries() -> list[dict[str, object]]:
    sync_curated_source_avatars()
    entries: list[dict[str, object]] = []
    for source, path in SOURCE_FILES:
        for row_number, row in enumerate(read_csv(path), start=2):
            entry = entry_from_row(row, source, row_number)
            if entry:
                entries.append(entry)

    merged_entries = merge_duplicate_entries(entries)

    latest = latest_updates_by_key()
    avatars = avatar_profiles_by_key()
    tag_cache = source_tag_cache()
    reviewed_profiles = load_profiles()
    monitor_sources = monitor_sources_by_key()
    for entry in merged_entries:
        entry["slug"] = make_slug(entry)
        apply_latest_update(entry, latest)
        apply_avatar(entry, avatars)
        apply_source_tags(entry, tag_cache)
        apply_profile(entry, reviewed_profiles)
        apply_monitor_sources(entry, monitor_sources)

    sorted_entries = sorted(
        merged_entries,
        key=lambda item: (
            -float(item.get("_latestUpdateSort") or 0),
            str(item.get("category", "")),
            str(item.get("name", "")),
        ),
    )
    for entry in sorted_entries:
        entry.pop("_latestUpdateSort", None)
    validate_public_entries(sorted_entries)
    return sorted_entries


def count_by(entries: list[dict[str, object]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in entries:
        value = str(entry.get(field) or "未分類")
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[0]))


def social_source_stats() -> dict[str, object]:
    config = read_json(SOCIAL_SOURCES, {"sources": []})
    sources = [
        source
        for source in config.get("sources", [])
        if source.get("enabled", True) and source.get("type") != "jsonl"
    ]
    platforms: dict[str, int] = {}
    types: dict[str, int] = {}
    for source in sources:
        platform = str(source.get("platform") or source.get("type") or "unknown")
        source_type = str(source.get("type") or "unknown")
        platforms[platform] = platforms.get(platform, 0) + 1
        types[source_type] = types.get(source_type, 0) + 1

    rsshub_sources = [
        source
        for source in sources
        if str(source.get("type") or "").startswith("rsshub_") or bool(source.get("rsshub_base"))
    ]
    facebook_sources = sum(1 for source in sources if source.get("type") == "facebook_page_posts")
    return {
        "totalSources": len(sources),
        "rsshubSources": len(rsshub_sources),
        "apifySources": facebook_sources,
        "facebookSources": facebook_sources,
        "youtubeSources": sum(1 for source in sources if source.get("type") == "youtube_ytdlp"),
        "platforms": dict(sorted(platforms.items(), key=lambda item: item[0])),
        "types": dict(sorted(types.items(), key=lambda item: item[0])),
    }


def main() -> None:
    entries = build_entries()
    payload = {
        "generatedAt": date.today().isoformat(),
        "entries": entries,
        "stats": {
            "totalEntries": len(entries),
            "categories": count_by(entries, "category"),
            "countries": count_by(entries, "country"),
            "watchSources": social_source_stats(),
        },
    }

    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, ensure_ascii=False, indent=2)
    DATA_OUT.write_text(
        "window.HARMONICA_OBSERVE_DATA = " + data + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {DATA_OUT.relative_to(PROJECT_ROOT)} with {len(entries)} public entries")


if __name__ == "__main__":
    main()
