#!/usr/bin/env python3
"""Build public score-source metadata for harmonica.observe.tw."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from output_files import write_text_if_changed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CSV = PROJECT_ROOT / "data" / "sources" / "harmonica-score-sources.csv"
SITE_ROOT = PROJECT_ROOT / "site"
API_OUT = SITE_ROOT / "api" / "score-sources.json"
DATA_OUT = SITE_ROOT / "data" / "score-source-data.js"
TAIPEI_TZ = timezone(timedelta(hours=8))


def clean(value: str | None) -> str:
    return (value or "").strip()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def stable_id(row: dict[str, str]) -> str:
    digest = hashlib.sha1(
        "|".join(
            [
                clean(row.get("source_name")),
                clean(row.get("source_type")),
                clean(row.get("score_title")),
                clean(row.get("evidence_url")),
            ]
        ).encode("utf-8")
    ).hexdigest()[:12]
    return f"score-source-{digest}"


def link(label: str, url: str) -> dict[str, str]:
    return {"label": label, "url": url}


def row_links(row: dict[str, str]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    url = clean(row.get("url"))
    evidence_url = clean(row.get("evidence_url"))
    if evidence_url:
        links.append(link("公開佐證", evidence_url))
    if url and url != evidence_url:
        links.append(link("來源入口", url))
    return links


def searchable_text(item: dict[str, Any]) -> str:
    values = [
        item.get("sourceName"),
        item.get("sourceType"),
        item.get("platform"),
        item.get("scoreTitle"),
        item.get("composer"),
        item.get("arranger"),
        item.get("instrumentation"),
        item.get("format"),
        item.get("purchaseMethod"),
        item.get("price"),
        item.get("availability"),
        item.get("rightsNote"),
    ]
    return " ".join(clean(str(value or "")) for value in values)


def normalize_row(row: dict[str, str]) -> dict[str, Any] | None:
    source_name = clean(row.get("source_name"))
    score_title = clean(row.get("score_title"))
    evidence_url = clean(row.get("evidence_url"))
    if not source_name or not evidence_url:
        return None
    item: dict[str, Any] = {
        "id": stable_id(row),
        "sourceName": source_name,
        "sourceType": clean(row.get("source_type")),
        "url": clean(row.get("url")),
        "platform": clean(row.get("platform")),
        "scoreTitle": score_title,
        "composer": clean(row.get("composer")),
        "arranger": clean(row.get("arranger")),
        "instrumentation": clean(row.get("instrumentation")),
        "format": clean(row.get("format")),
        "purchaseMethod": clean(row.get("purchase_method")),
        "price": clean(row.get("price")),
        "availability": clean(row.get("availability")),
        "evidenceUrl": evidence_url,
        "lastSeenAt": clean(row.get("last_seen_at")),
        "rightsNote": clean(row.get("rights_note")),
        "links": row_links(row),
    }
    item["searchText"] = searchable_text(item)
    return item


def counts(items: list[dict[str, Any]], field: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for item in items:
        value = clean(str(item.get(field) or ""))
        if not value:
            continue
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items(), key=lambda pair: (-pair[1], pair[0])))


def distinct_sorted(items: list[dict[str, Any]], field: str) -> list[str]:
    return sorted({clean(str(item.get(field) or "")) for item in items if clean(str(item.get(field) or ""))})


def sort_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("sourceName") or ""),
        str(item.get("sourceType") or ""),
        str(item.get("scoreTitle") or ""),
    )


def build_payload() -> dict[str, Any]:
    items = [item for row in read_csv(SOURCE_CSV) if (item := normalize_row(row))]
    items.sort(key=sort_key)
    now = datetime.now(TAIPEI_TZ).replace(microsecond=0).isoformat()
    source_names = distinct_sorted(items, "sourceName")
    titled_items = [item for item in items if clean(str(item.get("scoreTitle") or ""))]
    stats = {
        "totalScoreSources": len(items),
        "sourceNames": source_names,
        "sourceTypes": distinct_sorted(items, "sourceType"),
        "platforms": distinct_sorted(items, "platform"),
        "formats": distinct_sorted(items, "format"),
        "availability": distinct_sorted(items, "availability"),
        "sourceTypeCounts": counts(items, "sourceType"),
        "platformCounts": counts(items, "platform"),
        "formatCounts": counts(items, "format"),
        "availabilityCounts": counts(items, "availability"),
        "distinctSources": len(source_names),
        "titledItems": len(titled_items),
    }
    return {
        "version": 1,
        "generatedAt": now,
        "count": len(items),
        "stats": stats,
        "scoreSources": items,
    }


def write_outputs(payload: dict[str, Any]) -> None:
    API_OUT.parent.mkdir(parents=True, exist_ok=True)
    DATA_OUT.parent.mkdir(parents=True, exist_ok=True)
    json_text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    write_text_if_changed(API_OUT, json_text)
    write_text_if_changed(DATA_OUT, "window.HARMONICA_OBSERVE_SCORE_SOURCES = "
        + json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        + ";\n")


def main() -> int:
    payload = build_payload()
    write_outputs(payload)
    print(f"Wrote {payload['count']} score-source rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
