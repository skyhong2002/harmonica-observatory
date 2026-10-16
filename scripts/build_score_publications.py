#!/usr/bin/env python3
"""Build public score-publication data for harmonica.observe.tw."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from output_files import write_text_if_changed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = PROJECT_ROOT / "data" / "sources" / "harmonica-score-publications.csv"
SITE_ROOT = PROJECT_ROOT / "site"
API_OUT = SITE_ROOT / "api" / "scores.json"
DATA_OUT = SITE_ROOT / "data" / "score-data.js"
TAIPEI_TZ = timezone(timedelta(hours=8))
TAG_SPLIT_RE = re.compile(r"\s*(?:[/／；;、,，+&]|\band\b)\s*", re.IGNORECASE)
PUBLISHER_PREFIX_RE = re.compile(r"^(?:限定版本(?:出版社)?|建議出版社|出版社|出版者|建議出版者)[:：\s]*")
VERSION_DATE_RE = re.compile(r"(?:\d{2,4}年\d{1,2}月\d{1,2}日(?:版|編)?|\d{1,2}月\d{1,2}日修)")
BLANK_PUBLISHER_VALUES = {"", "-", "　", "限定版本", "不限版本"}
PUBLISHER_ALIASES = [
    (("獨特音樂", "theduet"), "獨特音樂（The Duet）"),
    (("judy", "茱蒂", "盧怡臻"), "Judy's 口琴樂團"),
    (("台北黃石", "臺北黃石", "台北市黃石", "黃石口琴"), "臺北黃石口琴樂團"),
    (("黃石樂器",), "黃石樂器"),
    (("林家靖", "rolabo"), "林家靖／Rolabo 工作室"),
    (("狂響",), "狂響口琴樂團／狂響逗嘴鼓"),
    (("丸玩琴",), "丸玩琴音樂"),
    (("高雄市口琴協會",), "高雄市口琴協會"),
    (("高雄天韻", "天韻口琴"), "高雄天韻口琴樂團"),
    (("高雄口琴藝術合奏",), "高雄口琴藝術合奏團"),
    (("台灣口琴藝術促進", "臺灣口琴藝術促進"), "臺灣口琴藝術促進會"),
    (("中華民國口琴藝術促進",), "中華民國口琴藝術促進會"),
    (("台灣口琴樂團", "臺灣口琴樂團"), "臺灣口琴樂團"),
    (("台中市中華口琴會", "臺中市中華口琴會"), "臺中市中華口琴會"),
    (("博凱愛樂",), "博凱愛樂口琴交響樂團"),
    (("天狼星",), "天狼星口琴樂團"),
    (("好魔力",), "好魔力口琴樂團"),
    (("花影",), "花影樂團"),
    (("音和樂器",), "音和樂器"),
    (("dm ing", "dming"), "DMing Studio"),
    (("鴿友",), "鴿友口琴樂團"),
    (("quarter",), "Quarter Harmonica Ensemble"),
    (("寶島口琴",), "寶島口琴樂團"),
    (("簧格",), "簧格藝創工作室"),
    (("口琴家雜誌", "口琴雜誌"), "口琴雜誌社"),
    (("hapa",), "HAPA"),
    (("doremi",), "Doremi Music Publishing"),
    (("ケイ", "km p"), "ケイ・エム・ピー"),
    (("廖訓禎",), "廖訓禎"),
    (("張甫行",), "張甫行"),
    (("高雄市兒童口琴",), "高雄市兒童口琴樂團"),
    (("作者授權",), "作者授權大會使用"),
]


def clean(value: str | None) -> str:
    return (value or "").strip()


def compact(value: str | None) -> str:
    return re.sub(r"\s+", " ", clean(value))


def alias_key(value: str | None) -> str:
    text = compact(value).lower()
    text = text.replace("（", "(").replace("）", ")")
    return re.sub(r"[\s:：/／()（）._-]+", "", text)


def clean_publisher_text(value: str | None) -> str:
    text = compact(value)
    for _ in range(3):
        next_text = PUBLISHER_PREFIX_RE.sub("", text).strip()
        if next_text == text:
            break
        text = next_text
    return VERSION_DATE_RE.sub("", text.replace("出版", "")).strip(" ：:/／")


def match_publisher_alias(*values: str | None) -> str:
    normalized_values = [alias_key(value) for value in values if clean(value)]
    for needles, label in PUBLISHER_ALIASES:
        for value in normalized_values:
            if any(alias_key(needle) in value for needle in needles):
                return label
    return ""


def publisher_lead(row: dict[str, str]) -> str:
    raw_publisher = clean(row.get("publisher"))
    purchase_note = clean(row.get("purchase_note"))
    cleaned = clean_publisher_text(raw_publisher)
    raw_alias = match_publisher_alias(raw_publisher)
    if raw_alias:
        return raw_alias
    if cleaned and cleaned not in BLANK_PUBLISHER_VALUES and not VERSION_DATE_RE.fullmatch(cleaned):
        return cleaned
    note_alias = match_publisher_alias(purchase_note)
    if note_alias:
        return note_alias
    if "代訂譜商" in purchase_note:
        return "原出版單位／代訂譜商"
    if raw_publisher == "不限版本":
        return "不限版本"
    return "未標示"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def split_values(value: str | None, *, limit: int = 12) -> list[str]:
    values: list[str] = []
    for part in TAG_SPLIT_RE.split(clean(value)):
        if part and part not in values:
            values.append(part)
        if len(values) >= limit:
            break
    return values


def stable_id(row: dict[str, str]) -> str:
    explicit = clean(row.get("id"))
    if explicit:
        return explicit
    digest = hashlib.sha1(
        "|".join(
            [
                clean(row.get("school_year")),
                clean(row.get("program")),
                clean(row.get("division")),
                clean(row.get("title")),
                clean(row.get("publisher")),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"score-{digest}"


def link(label: str, url: str) -> dict[str, str]:
    return {"label": label, "url": url}


def row_links(row: dict[str, str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    source_url = clean(row.get("source_url"))
    publisher_url = clean(row.get("publisher_url"))
    if source_url:
        links.append(link(clean(row.get("source_label")) or "官方來源", source_url))
    if publisher_url and publisher_url != source_url:
        links.append(link("出版／洽詢來源", publisher_url))
    return links


def searchable_text(item: dict[str, Any]) -> str:
    values = [
        item.get("title"),
        item.get("titleAlt"),
        item.get("schoolYear"),
        item.get("program"),
        item.get("category"),
        item.get("division"),
        item.get("composer"),
        item.get("arranger"),
        item.get("publisher"),
        item.get("publisherRaw"),
        item.get("scoreName"),
        item.get("performanceNote"),
        item.get("purchaseNote"),
        item.get("notes"),
        " ".join(item.get("tags", [])),
    ]
    return " ".join(clean(str(value or "")) for value in values)


def normalize_row(row: dict[str, str]) -> dict[str, Any] | None:
    title = clean(row.get("title"))
    if not title:
        return None
    publisher = publisher_lead(row)
    item: dict[str, Any] = {
        "id": stable_id(row),
        "title": title,
        "titleAlt": clean(row.get("title_alt")),
        "schoolYear": clean(row.get("school_year")),
        "program": clean(row.get("program")),
        "category": clean(row.get("category")),
        "division": clean(row.get("division")),
        "composer": clean(row.get("composer")),
        "arranger": clean(row.get("arranger")),
        "publisher": publisher,
        "publisherRaw": clean(row.get("publisher")),
        "scoreName": clean(row.get("score_name")),
        "performanceNote": clean(row.get("performance_note")),
        "purchaseNote": clean(row.get("purchase_note")),
        "sourceUrl": clean(row.get("source_url")),
        "sourceLabel": clean(row.get("source_label")),
        "publisherUrl": clean(row.get("publisher_url")),
        "verificationStatus": clean(row.get("verification_status")),
        "lastVerifiedAt": clean(row.get("last_verified_at")),
        "notes": clean(row.get("notes")),
        "tags": split_values(row.get("tags")),
        "links": row_links(row),
    }
    item["searchText"] = searchable_text(item)
    return item


def year_sort_value(value: str) -> int:
    try:
        return int(value)
    except ValueError:
        return -1


def sort_key(item: dict[str, Any]) -> tuple[int, str, str, str]:
    return (
        -year_sort_value(str(item.get("schoolYear") or "")),
        str(item.get("program") or ""),
        str(item.get("division") or ""),
        str(item.get("title") or ""),
    )


def counts(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = clean(str(item.get(field) or ""))
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda pair: (-pair[1], pair[0])))


def distinct_sorted(items: list[dict[str, Any]], field: str, *, reverse_numeric: bool = False) -> list[str]:
    values = sorted({clean(str(item.get(field) or "")) for item in items if clean(str(item.get(field) or ""))})
    if reverse_numeric:
        values.sort(key=year_sort_value, reverse=True)
    return values


def build_payload() -> dict[str, Any]:
    items = [item for row in read_csv(SOURCE_CSV) if (item := normalize_row(row))]
    items.sort(key=sort_key)
    now = datetime.now(TAIPEI_TZ).replace(microsecond=0).isoformat()
    stats = {
        "totalScores": len(items),
        "schoolYears": distinct_sorted(items, "schoolYear", reverse_numeric=True),
        "programs": distinct_sorted(items, "program"),
        "publishers": distinct_sorted(items, "publisher"),
        "programCounts": counts(items, "program"),
        "publisherCounts": counts(items, "publisher"),
    }
    return {
        "version": 1,
        "generatedAt": now,
        "count": len(items),
        "stats": stats,
        "scores": items,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    API_OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_text_if_changed(API_OUT, json_text)
    write_text_if_changed(DATA_OUT, "window.HARMONICA_OBSERVE_SCORES = "
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + ";\n")


def main() -> int:
    payload = build_payload()
    write_outputs(payload)
    print(f"Wrote {payload['count']} score-publication rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
