#!/usr/bin/env python3
"""Validate legacy source URL redirects for SEO cleanup."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from source_slugs import make_slug, source_public_id


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
ALIASES_CSV = PROJECT_ROOT / "data" / "sources" / "source-url-aliases.csv"
SOURCES_JSON = SITE_ROOT / "api" / "sources.json"
SITEMAP_XML = SITE_ROOT / "sitemap.xml"
REDIRECTS_CSV = SITE_ROOT / "redirects" / "cloudflare-bulk-redirects.csv"
PUBLIC_BASE_URL = "https://harmonica.observe.tw"
EXPECTED_FIELDS = [
    "source_path",
    "target_path",
    "status_code",
    "target_source_id",
    "match_basis",
    "notes",
    "last_verified_at",
]
# Rows the local service answers with 301 (scripts/serve.py). The registry
# also records Cloudflare-era aliases that are not served; some old watchlist-N
# IDs now belong to different sources, so each served row is checked first.
SERVED_CSV = PROJECT_ROOT / "data" / "sources" / "source-url-aliases-served.csv"


def clean(value: str | None) -> str:
    return (value or "").strip()


def read_aliases() -> tuple[list[dict[str, str]], list[str]]:
    if not ALIASES_CSV.exists():
        return [], [f"missing alias registry: {ALIASES_CSV.relative_to(PROJECT_ROOT)}"]
    with ALIASES_CSV.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fields = list(reader.fieldnames or [])
    errors = []
    if fields != EXPECTED_FIELDS:
        errors.append(
            "alias registry header mismatch: "
            f"expected {EXPECTED_FIELDS!r}, got {fields!r}"
        )
    return rows, errors


def read_sources() -> tuple[dict[str, str], set[str], list[str]]:
    if not SOURCES_JSON.exists():
        return {}, set(), [f"missing sources JSON: {SOURCES_JSON.relative_to(PROJECT_ROOT)}"]
    payload = json.loads(SOURCES_JSON.read_text(encoding="utf-8"))
    entries = payload.get("entries") if isinstance(payload, dict) else []
    if not isinstance(entries, list):
        return {}, set(), ["sources JSON does not contain an entries array"]
    id_to_path: dict[str, str] = {}
    canonical_paths: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        public_id = source_public_id(entry)
        path = f"/source/{make_slug(entry)}/"
        id_to_path[public_id] = path
        canonical_paths.add(path)
    return id_to_path, canonical_paths, []


def sitemap_locs() -> set[str]:
    if not SITEMAP_XML.exists():
        return set()
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    root = ET.parse(SITEMAP_XML).getroot()
    return {
        clean(loc.text)
        for loc in root.findall("sm:url/sm:loc", ns)
        if loc.text
    }


def local_file_for_path(path: str) -> Path:
    decoded = urllib.parse.unquote(path.lstrip("/"))
    return SITE_ROOT / decoded / "index.html"


def read_served() -> list[str]:
    if not SERVED_CSV.exists():
        return []
    with SERVED_CSV.open(newline="", encoding="utf-8") as handle:
        return [clean(row.get("source_path")) for row in csv.DictReader(handle)]


def validate_local() -> list[str]:
    rows, errors = read_aliases()
    id_to_path, canonical_paths, source_errors = read_sources()
    errors.extend(source_errors)
    locs = sitemap_locs()
    seen: set[str] = set()
    redirects_expected = 0

    for index, row in enumerate(rows, start=2):
        source_path = clean(row.get("source_path"))
        target_path = clean(row.get("target_path"))
        status_code = clean(row.get("status_code"))
        target_source_id = clean(row.get("target_source_id"))
        if not source_path.startswith("/source/") or not source_path.endswith("/"):
            errors.append(f"line {index}: source_path must be a /source/ path ending with /")
        if source_path in seen:
            errors.append(f"line {index}: duplicate source_path {source_path!r}")
        seen.add(source_path)
        if status_code not in {"301", "410"}:
            errors.append(f"line {index}: status_code must be 301 or 410")
        if source_path in canonical_paths:
            errors.append(f"line {index}: source_path collides with a current canonical path: {source_path}")
        if PUBLIC_BASE_URL + source_path in locs:
            errors.append(f"line {index}: alias source appears in sitemap: {source_path}")
        if status_code == "301":
            redirects_expected += 1
            if not target_path:
                errors.append(f"line {index}: 301 row missing target_path")
            elif target_path not in canonical_paths:
                errors.append(f"line {index}: target_path is not a current canonical source path: {target_path}")
            if target_source_id and id_to_path.get(target_source_id) != target_path:
                errors.append(
                    f"line {index}: target_source_id {target_source_id!r} maps to "
                    f"{id_to_path.get(target_source_id)!r}, not {target_path!r}"
                )
            target_file = local_file_for_path(target_path)
            if target_path and not target_file.exists():
                errors.append(f"line {index}: target file missing for {target_path}")
        if status_code == "410" and target_path:
            errors.append(f"line {index}: 410 row must leave target_path empty")

    registry = {urllib.parse.unquote(clean(row.get("source_path"))): row for row in rows}
    for source_path in read_served():
        row = registry.get(urllib.parse.unquote(source_path))
        if not row or clean(row.get("status_code")) != "301":
            errors.append(f"served alias is not a 301 row in the registry: {source_path}")
        elif urllib.parse.quote(urllib.parse.unquote(source_path), safe="/") in canonical_paths:
            errors.append(f"served alias collides with a current canonical path: {source_path}")

    if rows and not REDIRECTS_CSV.exists():
        errors.append(f"missing generated Cloudflare bulk redirects: {REDIRECTS_CSV.relative_to(PROJECT_ROOT)}")
    elif REDIRECTS_CSV.exists():
        with REDIRECTS_CSV.open(newline="", encoding="utf-8") as handle:
            generated_redirects = sum(1 for row in csv.reader(handle) if row)
        if generated_redirects != redirects_expected:
            errors.append(
                "Cloudflare redirect count mismatch: "
                f"expected {redirects_expected}, generated {generated_redirects}"
            )
    return errors


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_no_redirect(path: str) -> tuple[int | str, str]:
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(
        PUBLIC_BASE_URL + path,
        headers={"User-Agent": "Harmonica SEO redirect validator"},
    )
    try:
        with opener.open(request, timeout=20) as response:
            return response.status, response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Location", "")
    except Exception as exc:
        return "ERR", str(exc)


def validate_live() -> list[str]:
    rows, errors = read_aliases()
    alias_by_path = {urllib.parse.unquote(clean(row.get("source_path"))): row for row in rows}
    for source_path in read_served():
        row = alias_by_path.get(urllib.parse.unquote(source_path))
        if not row:
            errors.append(f"served alias missing from alias registry: {source_path}")
            continue
        target_path = clean(row.get("target_path"))
        status, location = fetch_no_redirect(urllib.parse.quote(urllib.parse.unquote(source_path), safe="/"))
        expected_location = PUBLIC_BASE_URL + target_path
        if status != 301 or location != expected_location:
            errors.append(
                f"{source_path}: expected 301 -> {expected_location}, got {status} -> {location or '-'}"
            )
        elif fetch_no_redirect(target_path)[0] != 200:
            errors.append(f"{source_path}: redirect target {target_path} is not 200")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--local", action="store_true", help="Validate local alias registry and generated files.")
    parser.add_argument("--live", action="store_true", help="Validate live 301 responses for served aliases.")
    args = parser.parse_args()

    run_local = args.local or not args.live
    errors: list[str] = []
    if run_local:
        errors.extend(validate_local())
    if args.live:
        errors.extend(validate_live())

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print("Legacy source redirects validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
