#!/usr/bin/env python3
"""Rewrite existing social candidate tags with the LLM classifier."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import shutil
import urllib.error
from pathlib import Path
from typing import Any

import llm_backend

import social_feed_watchdog as watchdog


PROJECT_ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
DEFAULT_CANDIDATES = PROJECT_ROOT / "data" / "feeds" / "social_candidates.jsonl"
DEFAULT_CONFIG = PROJECT_ROOT / "data" / "feeds" / "social_sources.json"
DEFAULT_LLM_CACHE = PROJECT_ROOT / "state" / "social_llm_tags.json"
BACKFILL_SOURCE = "public-link-backfill"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
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
                rows.append(row)
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]], *, backup: bool = True) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: Path | None = None
    if backup and path.exists():
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        backup_path = path.with_name(f"{path.name}.bak-{stamp}")
        shutil.copy2(path, backup_path)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    tmp.replace(path)
    return backup_path


def display_labels(llm_result: dict[str, Any]) -> list[str]:
    labels = watchdog.split_tag_values(list(llm_result.get("llm_labels") or []))
    if labels:
        return labels
    return ["公開更新"] if llm_result.get("llm_relevant") else []


def row_should_retag(row: dict[str, Any], include_backfill: bool) -> bool:
    if include_backfill:
        return True
    return row.get("raw_source") != BACKFILL_SOURCE


def retag_row(
    row: dict[str, Any],
    *,
    keywords: list[str],
    cache: dict[str, Any],
    token: str,
    base_url: str,
    model: str,
    timeout: int,
    stats: dict[str, Any],
) -> dict[str, Any]:
    next_row = dict(row)
    keyword_matches = watchdog.match_keywords(str(next_row.get("text") or ""), keywords)
    llm_result = watchdog.cached_llm_classification(
        next_row,
        keyword_matches,
        cache=cache,
        token=token,
        base_url=base_url,
        model=model,
        timeout=timeout,
        stats=stats,
    )
    next_row.update(llm_result or {})
    next_row["keyword_matches"] = keyword_matches
    next_row["matched_keywords"] = display_labels(llm_result or {})
    return next_row


def main() -> int:
    watchdog.load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--llm-cache", type=Path, default=DEFAULT_LLM_CACHE)
    parser.add_argument("--llm-base-url", default=llm_backend.base_url())
    parser.add_argument("--llm-model", default=llm_backend.model_name())
    parser.add_argument("--llm-timeout", type=int, default=int(os.environ.get("HARMONICA_LLM_TIMEOUT", "45")))
    parser.add_argument(
        "--llm-confidence-threshold",
        type=float,
        default=float(os.environ.get("HARMONICA_LLM_CONFIDENCE_THRESHOLD", "0.55")),
    )
    parser.add_argument(
        "--llm-keychain-service",
        default=os.environ.get("HARMONICA_LLM_KEYCHAIN_SERVICE", watchdog.DEFAULT_LLM_KEYCHAIN_SERVICE),
    )
    parser.add_argument(
        "--llm-keychain-account",
        default=os.environ.get("HARMONICA_LLM_KEYCHAIN_ACCOUNT", watchdog.DEFAULT_LLM_KEYCHAIN_ACCOUNT),
    )
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--keep-irrelevant", action="store_true")
    parser.add_argument("--include-backfill", action="store_true")
    parser.add_argument("--allow-errors", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    token, token_source = watchdog.read_llm_token(args.llm_keychain_service, args.llm_keychain_account)
    if not token:
        raise SystemExit("LLM provider is disabled." if llm_backend.provider() == "disabled" else "Missing LLM gateway key. Set HARMONICA_LLM_API_KEY or store it in Keychain (harmonica-ai-gateway/harmonica).")

    config = watchdog.load_json(args.config, {"keywords": []})
    keywords = config.get("keywords") or []
    rows = read_jsonl(args.candidates)
    cache = watchdog.load_json(args.llm_cache, {"version": 1, "items": {}})
    stats: dict[str, Any] = {
        **llm_backend.runtime_metadata(args.llm_model, args.llm_base_url),
        "token_source": token_source,
        "cached": 0,
        "requests": 0,
        "errors": 0,
        "cache_changed": False,
    }

    output_rows: list[dict[str, Any]] = []
    changed = 0
    dropped = 0
    retagged = 0
    skipped_backfill = 0
    errors: list[dict[str, str]] = []

    for row in rows:
        if not row_should_retag(row, args.include_backfill):
            skipped_backfill += 1
            output_rows.append(row)
            continue
        if args.limit and retagged >= args.limit:
            output_rows.append(row)
            continue

        try:
            next_row = retag_row(
                row,
                keywords=keywords,
                cache=cache,
                token=token,
                base_url=args.llm_base_url,
                model=args.llm_model,
                timeout=args.llm_timeout,
                stats=stats,
            )
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            stats["errors"] = int(stats.get("errors") or 0) + 1
            errors.append({"key": str(row.get("key") or row.get("url") or ""), "error": str(exc)})
            output_rows.append(row)
            continue

        retagged += 1
        relevant = bool(next_row.get("llm_relevant")) and float(next_row.get("llm_confidence") or 0) >= args.llm_confidence_threshold
        if not relevant and not args.keep_irrelevant:
            dropped += 1
            changed += 1
            continue
        if next_row != row:
            changed += 1
        output_rows.append(next_row)

    backup_path = None
    out_path = args.output or args.candidates
    write_performed = bool(args.write and (not errors or args.allow_errors))
    if write_performed:
        backup_path = write_jsonl(out_path, output_rows, backup=not args.no_backup and out_path == args.candidates)
        if stats.get("cache_changed"):
            cache["version"] = 1
            cache["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
            watchdog.save_json(args.llm_cache, cache)

    summary = {
        "write_requested": bool(args.write),
        "write_performed": write_performed,
        "write_blocked_reason": "errors" if args.write and errors and not args.allow_errors else "",
        "input": str(args.candidates),
        "output": str(out_path),
        "backup": str(backup_path) if backup_path else "",
        "total_rows": len(rows),
        "output_rows": len(output_rows),
        "retagged_rows": retagged,
        "changed_rows": changed,
        "dropped_irrelevant_rows": dropped,
        "skipped_backfill_rows": skipped_backfill,
        "llm": stats,
        "errors": errors if args.verbose else errors[:5],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
