#!/usr/bin/env python3
"""Generate Cloudflare edge artifacts for legacy SEO source URLs."""

from __future__ import annotations

import csv
import json
import io
from pathlib import Path

from output_files import write_text_if_changed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SITE_ROOT = PROJECT_ROOT / "site"
ALIASES_CSV = PROJECT_ROOT / "data" / "sources" / "source-url-aliases.csv"
OUTPUT_DIR = SITE_ROOT / "redirects"
BULK_REDIRECTS_CSV = OUTPUT_DIR / "cloudflare-bulk-redirects.csv"
GONE_WORKER_JS = OUTPUT_DIR / "cloudflare-gone-worker.js"
PUBLIC_BASE_URL = "https://harmonica.observe.tw"


def clean(value: str | None) -> str:
    return (value or "").strip()


def read_aliases() -> list[dict[str, str]]:
    if not ALIASES_CSV.exists():
        return []
    with ALIASES_CSV.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def absolute_url(path: str) -> str:
    if path.startswith("https://"):
        return path
    return PUBLIC_BASE_URL + "/" + path.lstrip("/")


def validate_rows(rows: list[dict[str, str]]) -> None:
    errors: list[str] = []
    for index, row in enumerate(rows, start=2):
        source_path = clean(row.get("source_path"))
        target_path = clean(row.get("target_path"))
        status_code = clean(row.get("status_code"))
        if not source_path.startswith("/source/") or not source_path.endswith("/"):
            errors.append(f"line {index}: source_path must be an absolute /source/ path ending with /")
        if status_code not in {"301", "410"}:
            errors.append(f"line {index}: status_code must be 301 or 410")
        if status_code == "301" and not target_path.startswith("/source/"):
            errors.append(f"line {index}: 301 rows require a /source/ target_path")
        if status_code == "410" and target_path:
            errors.append(f"line {index}: 410 rows must leave target_path empty")
    if errors:
        raise SystemExit("Invalid source URL aliases:\n" + "\n".join(f"- {error}" for error in errors))


def write_bulk_redirects(rows: list[dict[str, str]]) -> int:
    redirect_rows = [row for row in rows if clean(row.get("status_code")) == "301"]
    with io.StringIO(newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for row in redirect_rows:
            writer.writerow(
                [
                    absolute_url(clean(row.get("source_path"))),
                    absolute_url(clean(row.get("target_path"))),
                    "301",
                    "true",
                    "false",
                    "false",
                    "false",
                ]
            )
        write_text_if_changed(BULK_REDIRECTS_CSV, handle.getvalue())
    return len(redirect_rows)


def write_gone_worker(rows: list[dict[str, str]]) -> int:
    gone_paths = sorted(
        clean(row.get("source_path"))
        for row in rows
        if clean(row.get("status_code")) == "410"
    )
    if not gone_paths:
        if GONE_WORKER_JS.exists():
            GONE_WORKER_JS.unlink()
        return 0

    content = f"""const GONE_PATHS = new Set({json.dumps(gone_paths, ensure_ascii=False, indent=2)});

export default {{
  async fetch(request) {{
    const url = new URL(request.url);
    if (GONE_PATHS.has(url.pathname)) {{
      return new Response("410 Gone\\n", {{
        status: 410,
        headers: {{
          "content-type": "text/plain; charset=utf-8",
          "cache-control": "public, max-age=3600"
        }}
      }});
    }}
    return fetch(request);
  }}
}};
"""
    write_text_if_changed(GONE_WORKER_JS, content)
    return len(gone_paths)


def main() -> int:
    rows = read_aliases()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    validate_rows(rows)
    redirect_count = write_bulk_redirects(rows)
    gone_count = write_gone_worker(rows)
    print(
        "Generated Cloudflare SEO redirect artifacts: "
        f"{redirect_count} bulk redirects, {gone_count} gone paths"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
