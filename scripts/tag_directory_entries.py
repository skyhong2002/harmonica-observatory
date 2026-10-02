#!/usr/bin/env python3
"""Tag public directory entries with an LLM at the source/person/club level."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import time
import urllib.error
from pathlib import Path
from typing import Any

import llm_backend

import build_public_data
import social_feed_watchdog as watchdog


PROJECT_ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
DEFAULT_OUTPUT = PROJECT_ROOT / "state" / "source_llm_tags.json"

SOURCE_TAGS = {
    "口琴",
    "演奏者",
    "團體樂團",
    "學生社團",
    "大專社團",
    "高中社團",
    "教學器材",
    "活動資訊",
    "場館平台",
    "國際交流",
    "其他來源",
    "半音階",
    "複音",
    "十孔",
    "低音",
    "和弦",
    "重奏",
    "合奏",
    "教學",
    "課程",
    "工作室",
    "器材",
    "品牌",
    "音樂節",
    "比賽",
    "音樂會",
    "成發",
    "招生",
    "交流",
    "演出",
    "場館",
    "售票平台",
    "文化局",
    "公益",
}


def load_cache(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"version": 1, "items": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"version": 1, "items": {}}
    if not isinstance(data.get("items"), dict):
        data["items"] = {}
    return data


def save_cache(path: Path, cache: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def normalize_tags(value: Any) -> list[str]:
    tags: list[str] = []
    for item in build_public_data.normalize_tag_values(value):
        tag = str(item or "").strip()
        if tag in SOURCE_TAGS and tag not in tags:
            tags.append(tag)
    return tags[:8]


def normalize_result(data: dict[str, Any], entry: dict[str, object], model: str) -> dict[str, Any]:
    tags = normalize_tags(data.get("sourceTags") or data.get("tags") or data.get("labels"))
    if not tags:
        tags = [tag for tag in build_public_data.fallback_source_tags(entry) if tag in SOURCE_TAGS][:8]

    confidence = data.get("confidence", 0.6)
    try:
        confidence = float(confidence)
    except (TypeError, ValueError):
        confidence = 0.6
    if confidence > 1 and confidence <= 100:
        confidence = confidence / 100
    confidence = max(0.0, min(confidence, 1.0))

    summary = watchdog.compact_text(str(data.get("summary") or data.get("sourceSummary") or ""), 80)
    reason = watchdog.compact_text(str(data.get("reason") or data.get("sourceTagReason") or ""), 120)
    return {
        "sourceTags": tags,
        "sourceSummary": summary,
        "sourceTagReason": reason,
        "confidence": round(confidence, 3),
        "llm_model": model,
        "llm_tagged_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }


def prompt_for_entry(entry: dict[str, object]) -> list[dict[str, str]]:
    payload = {
        "name": entry.get("name") or "",
        "name_en": entry.get("nameEn") or "",
        "aliases": entry.get("aliases") or [],
        "category": entry.get("category") or "",
        "type": entry.get("type") or "",
        "country": entry.get("country") or "",
        "region": entry.get("region") or "",
        "city_or_focus": entry.get("cityOrFocus") or "",
        "summary": entry.get("summary") or "",
        "keywords": entry.get("keywords") or "",
        "links": entry.get("links") or [],
    }
    return [
        {
            "role": "system",
            "content": (
                "你是全球口琴觀測站的公開來源索引分類器。"
                "任務是替人、演奏者、學生社團、樂團、教學來源、活動平台等來源本身貼 tag。"
                "只根據提供的公開欄位判斷，不要臆測私人資料。只回傳 JSON，不要 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "請替這個公開來源整理 directory-level tags。這不是單篇貼文分類，而是來源本身的分類。"
                "sourceTags 請選 3 到 8 個，必須從白名單挑選；summary 請用 30 字內描述來源定位；"
                "sourceTags 的每一個元素只能是一個 tag，不要用斜線、頓號、逗號、加號或空白合併多個 tag；"
                "reason 請用 60 字內說明判斷依據。"
                "如果是學校或社團，優先標學生社團、大專社團或高中社團；"
                "如果是個人，標演奏者；如果是團體或樂團，標團體樂團；"
                "如果是課程、教學、工作室或器材品牌，標教學、課程、工作室、器材或品牌；"
                "如果是活動、音樂節、比賽、售票或場館，標活動資訊、音樂節、比賽、售票平台或場館。"
                f"白名單：{', '.join(sorted(SOURCE_TAGS))}。"
                '回傳格式：{"sourceTags":[],"summary":"","confidence":0.0,"reason":""}'
                "\n\n來源資料：\n"
                + json.dumps(payload, ensure_ascii=False, indent=2)
            ),
        },
    ]


def classify_entry(
    entry: dict[str, object],
    *,
    token: str,
    base_url: str,
    model: str,
    timeout: int,
) -> dict[str, Any]:
    body = {
        "model": model,
        "messages": prompt_for_entry(entry),
        "temperature": 0,
        "max_completion_tokens": 500,
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    response_body = watchdog.curl_json(watchdog.llm_endpoint(base_url), token, body, timeout)
    response_json = json.loads(response_body)
    response_text = watchdog.chat_response_text(response_json)
    parsed = watchdog.extract_json_object(response_text)
    return {**normalize_result(parsed, entry, llm_backend.resolved_model(response_json, model)),
            "llm_requested_model": model,
            "llm_provider": llm_backend.provider()}


def cached_classify(
    entry: dict[str, object],
    *,
    cache: dict[str, Any],
    token: str,
    base_url: str,
    model: str,
    timeout: int,
    refresh: bool,
    stats: dict[str, Any],
) -> dict[str, Any]:
    items = cache.setdefault("items", {})
    cache_key = build_public_data.entry_tag_fingerprint(entry)
    if not refresh and isinstance(items.get(cache_key), dict):
        stats["cached"] = int(stats.get("cached") or 0) + 1
        return items[cache_key]

    attempts, models = llm_backend.retry_policy(model)
    last_error: Exception | None = None
    result: dict[str, Any] | None = None
    for candidate_model in models:
        for attempt in range(attempts):
            try:
                stats["requests"] = int(stats.get("requests") or 0) + 1
                result = classify_entry(
                    entry,
                    token=token,
                    base_url=base_url,
                    model=candidate_model,
                    timeout=timeout,
                )
                if candidate_model != model:
                    stats["fallback_uses"] = int(stats.get("fallback_uses") or 0) + 1
                break
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                last_error = exc
                stats["retry_errors"] = int(stats.get("retry_errors") or 0) + 1
                if attempt + 1 < attempts:
                    time.sleep(min(2.0, 0.5 * (attempt + 1)))
        if result is not None:
            break
    if result is None:
        raise RuntimeError(f"LLM source tagging failed: {last_error}")

    items[cache_key] = result
    stats["cache_changed"] = True
    return result


def main() -> int:
    watchdog.load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--llm-base-url", default=llm_backend.base_url())
    parser.add_argument("--llm-model", default=llm_backend.model_name())
    parser.add_argument("--llm-timeout", type=int, default=int(os.environ.get("HARMONICA_LLM_TIMEOUT", "45")))
    parser.add_argument("--llm-keychain-service", default=os.environ.get("HARMONICA_LLM_KEYCHAIN_SERVICE", watchdog.DEFAULT_LLM_KEYCHAIN_SERVICE))
    parser.add_argument("--llm-keychain-account", default=os.environ.get("HARMONICA_LLM_KEYCHAIN_ACCOUNT", watchdog.DEFAULT_LLM_KEYCHAIN_ACCOUNT))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--allow-errors", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    token, token_source = watchdog.read_llm_token(args.llm_keychain_service, args.llm_keychain_account)
    if not token:
        raise SystemExit("LLM provider is disabled." if llm_backend.provider() == "disabled" else "Missing LLM gateway key. Set HARMONICA_LLM_API_KEY or store it in Keychain (harmonica-ai-gateway/harmonica).")

    cache = load_cache(args.output)
    entries = build_public_data.build_entries()
    stats: dict[str, Any] = {
        **llm_backend.runtime_metadata(args.llm_model, args.llm_base_url),
        "token_source": token_source,
        "cached": 0,
        "requests": 0,
        "errors": 0,
        "retry_errors": 0,
        "fallback_uses": 0,
        "cache_changed": False,
    }
    tagged = 0
    errors: list[dict[str, str]] = []

    for entry in entries:
        if args.limit and tagged >= args.limit:
            break
        try:
            cached_classify(
                entry,
                cache=cache,
                token=token,
                base_url=args.llm_base_url,
                model=args.llm_model,
                timeout=args.llm_timeout,
                refresh=args.refresh,
                stats=stats,
            )
            tagged += 1
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
            stats["errors"] = int(stats.get("errors") or 0) + 1
            errors.append({"name": str(entry.get("name") or ""), "error": str(exc)})
            if not args.allow_errors:
                break

    write_performed = bool(args.write and (not errors or args.allow_errors))
    if write_performed:
        cache["version"] = 1
        cache["updated_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        save_cache(args.output, cache)

    summary = {
        "write_requested": bool(args.write),
        "write_performed": write_performed,
        "write_blocked_reason": "errors" if args.write and errors and not args.allow_errors else "",
        "output": str(args.output),
        "total_entries": len(entries),
        "processed_entries": tagged,
        "cached_items": len(cache.get("items") or {}),
        "llm": stats,
        "errors": errors if args.verbose else errors[:5],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 1 if errors and not args.allow_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
