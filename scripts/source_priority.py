"""Rank sources by how often they have announced events.

Paid collectors can only visit a few accounts per day, so accounts whose past
posts were classified as events are visited first. Counts are keyed by source
name so one artist's Facebook history also promotes their Instagram account.
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

CANDIDATES = Path(__file__).resolve().parents[1] / "data/feeds/social_candidates.jsonl"


def event_affinity(path: Path = CANDIDATES) -> dict[str, int]:
    """Return {casefolded source name: number of event-classified posts}."""
    counts: collections.Counter[str] = collections.Counter()
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return {}
    with handle:
        for line in handle:
            if '"events"' not in line:  # skip most of the 70+ MB without parsing
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = str(item.get("source_name") or "").strip().casefold()
            if name and "events" in (item.get("llm_categories") or []):
                counts[name] += 1
    return dict(counts)


def affinity_of(source: dict, affinity: dict[str, int]) -> int:
    return affinity.get(str(source.get("name") or "").strip().casefold(), 0)
