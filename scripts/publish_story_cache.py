#!/usr/bin/env python3
"""Publish newly cached, unexpired Instagram stories without collecting anything.

Standalone calls use run_pipeline's native lock. --pipeline-lock-held is only for
an orchestrator already holding that lock (the same convention as the collector).
The helper reads existing enabled apify_stories sources, imports only their cache
through the watchdog with LLM tagging disabled, then rebuilds RSS/JSON offline.
It does not run an actor, profile fetch, LLM inference, or external calendar write.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from run_pipeline import PROJECT_ROOT, acquire_lock, release_lock, write_json_atomic
from story_lifecycle import display_expiry


def read_json(path: Path, default=None):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else (default or {})
    except (OSError, ValueError):
        return default or {}


def candidate_keys(path: Path) -> set[str]:
    keys = set()
    try:
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get('key'):
                    keys.add(str(row['key']))
    except FileNotFoundError:
        pass
    return keys


def publish_cached_stories(root: Path = PROJECT_ROOT, *, now: dt.datetime | None = None, runner=None) -> dict:
    """Called while the pipeline lock is held; unchanged caches are a no-op."""
    now = now or dt.datetime.now(dt.timezone.utc)
    config = read_json(root / 'data/feeds/social_sources.json')
    cache = read_json(root / 'state/instagram_public.json').get('sources', {})
    published = {str(row.get('key')) for row in read_json(root / 'site/api/latest.json').get('updates', [])
                 if isinstance(row, dict) and row.get('key')}
    selected, pending = [], set()
    for source in config.get('sources', []):
        if not isinstance(source, dict) or not source.get('enabled', True) or source.get('provider') != 'apify_stories':
            continue
        sid = str(source.get('id') or '')
        source_pending = {str(post['key']) for post in cache.get(sid, {}).get('posts', [])
                          if isinstance(post, dict) and post.get('key') and str(post['key']) not in published
                          and (expiry := display_expiry(post)) and expiry > now}
        if sid and source_pending:
            selected.append(sid)
            pending.update(source_pending)
    if not pending:
        return {'status': 'unchanged', 'sources': 0, 'pendingStories': 0}

    seen_path = root / 'state/social_seen.json'
    # Never turn an existing unreadable seen file into a new empty history.
    seen = json.loads(seen_path.read_text(encoding='utf-8')) if seen_path.exists() else {'seen': {}}
    if not isinstance(seen, dict) or not isinstance(seen.get('seen'), dict):
        raise ValueError('Invalid existing story seen state')
    seen_map = dict(seen['seen'])
    candidates = candidate_keys(root / 'data/feeds/social_candidates.jsonl')
    # A baseline or interruption before append_candidates can mark a key seen
    # without ever writing its candidate. Repair only this valid, pending set.
    for key in pending - candidates:
        seen_map.pop(key, None)
    temporary_seen = {**seen, 'seen': seen_map}
    env = {**os.environ, 'HARMONICA_OBSERVE_HOME': str(root), 'HARMONICA_LLM_PROVIDER': 'disabled', 'HARMONICA_ENABLE_LLM_TAGS': '0'}
    invoke = runner or subprocess.run
    with tempfile.TemporaryDirectory(prefix='harmonica-story-publish-') as temporary:
        working_seen = Path(temporary) / 'seen.json'
        write_json_atomic(working_seen, temporary_seen)
        args = [sys.executable, str(root / 'scripts/social_feed_watchdog.py'),
                '--no-llm-tags', '--emit-initial', '--seen', str(working_seen),
                '--progress', str(Path(temporary) / 'progress.json')]
        for sid in selected:
            args.extend(['--source-id', sid])
        invoke(args, cwd=root, env=env, check=True, capture_output=True, text=True)
        # Retain every unrelated entry and metadata field from the original
        # snapshot; only the normal successful watchdog state is committed.
        updated_seen = read_json(working_seen)
        if not isinstance(updated_seen.get('seen'), dict):
            raise RuntimeError('Story publisher received invalid watchdog state')
        write_json_atomic(seen_path, updated_seen)
        invoke([sys.executable, str(root / 'scripts/generate_rss_feeds.py'), '--offline'],
               cwd=root, env=env, check=True, capture_output=True, text=True)
    after = {str(row.get('key')) for row in read_json(root / 'site/api/latest.json').get('updates', [])
             if isinstance(row, dict) and row.get('key')}
    return {'status': 'published' if pending <= after else 'incomplete', 'sources': len(selected),
            'pendingStories': len(pending), 'publishedStories': len(pending & after)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pipeline-lock-held', action='store_true')
    args = parser.parse_args(argv)
    lock = PROJECT_ROOT / 'state/run_pipeline.lock'
    if not args.pipeline_lock_held and not acquire_lock(lock, stale_after_minutes=240):
        return 0
    try:
        result = publish_cached_stories(PROJECT_ROOT)
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result['status'] == 'incomplete' else 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        # Subprocess output may contain public post text; keep scheduler logs small.
        print(json.dumps({'status': 'failed', 'error': type(exc).__name__}))
        return 1
    finally:
        if not args.pipeline_lock_held:
            release_lock(lock)


if __name__ == '__main__':
    raise SystemExit(main())
