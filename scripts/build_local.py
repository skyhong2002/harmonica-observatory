#!/usr/bin/env python3
"""Rebuild a local installation from public CSVs and already collected snapshots.

No network fetches, paid actors, LLM inference, external calendar writes or Git pushes run here.
Use run_pipeline.py for scheduled ingestion; serve.py serves this same dataset.
"""
from __future__ import annotations
import os
import json
import html
import re
from datetime import datetime, timezone
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ['build_social_sources.py'],
    ['build_public_data.py'],
    ['backfill_public_source_pages.py', '--skip-fetch'],
    ['build_public_data.py'],
    ['build_score_publications.py'],
    ['build_score_sources.py'],
    ['generate_rss_feeds.py', '--offline'],
    ['build_public_calendar_events.py', '--no-llm'],
    ['apply_submitted_events.py'],
    ['build_status_page.py', '--offline'],
    ['build_submit_page.py'],
    ['generate_seo_pages.py'],
    ['generate_cloudflare_redirects.py'],
    ['check_source_coverage.py'],
    ['validate_public_outputs.py'],
]


def seed_missing_artifacts(root: Path = ROOT) -> None:
    """Bootstrap ignored historical HTML and an honest unconfigured sync marker.

    Existing installations keep their generated pages and real sync history.
    The HTTP application always serves web/index.html for its primary routes.
    """
    site = root / 'site'
    template_path = root / 'web/index.html'
    if template_path.exists():
        template = template_path.read_text(encoding='utf-8')
    else:
        # Allows data-only installations to build before UI assets are deployed.
        template = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Harmonica Observatory</title></head><body><main>'
                    '<h1>Harmonica Observatory</h1><p>Public harmonica sources, events and scores.</p>'
                    '<a href="/api/v1/catalog">Public catalog</a></main></body></html>')
    origin = 'https://harmonica.observe.tw'
    for route in ('/', '/post/', '/post/source/', '/directory/', '/source/', '/scores/',
                  '/scores/sources/', '/score-sources/', '/events/', '/contribute/', '/about/', '/privacy/'):
        target = site / route.strip('/') / 'index.html'
        if target.exists():
            continue
        document = re.sub(r'<link\b[^>]*\brel=["\']canonical["\'][^>]*>', '', template, flags=re.I)
        additions = '<link rel="canonical" href="' + html.escape(origin + route, quote=True) + '">'
        if route == '/scores/':
            dataset = {'@context': 'https://schema.org', '@type': 'Dataset',
                       '@id': origin + '/scores/#dataset', 'url': origin + '/scores/',
                       'name': 'Harmonica competition score publications',
                       'description': 'A public index of harmonica competition score publications, with original publisher evidence, years, divisions and source links.'}
            additions += '<script type="application/ld+json">' + json.dumps(dataset) + '</script>'
        document = document.replace('</head>', additions + '</head>')
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(document, encoding='utf-8')
    sync = site / 'api/public-calendar-sync.json'
    if not sync.exists():
        sync.parent.mkdir(parents=True, exist_ok=True)
        sync.write_text(json.dumps({
            'status': 'not_configured', 'enabled': False,
            'generatedAt': datetime.now(timezone.utc).isoformat(),
            'summary': 'External calendar synchronization is not configured. Local JSON and ICS calendars are available.',
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    env = dict(os.environ, HARMONICA_LLM_PROVIDER='disabled')
    seed_missing_artifacts()
    for step in STEPS:
        print('Building: ' + step[0], flush=True)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts' / step[0]), *step[1:]], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    print('Local data ready. Start: .venv/bin/python scripts/serve.py')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
