"""Keep reviewed public profiles and portraits reproducible without private caches."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE_FILE = ROOT / 'data/sources/source-profile-overrides.json'
ASSET_DIR = ROOT / 'assets/source-avatars-curated'
PUBLIC_DIR = ROOT / 'site/assets/source-avatars'


def load_profiles(path: Path = PROFILE_FILE) -> dict:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding='utf-8'))
    profiles = payload.get('sources', {})
    if not isinstance(profiles, dict):
        raise ValueError('Reviewed source profiles must be keyed by stable source ID')
    return profiles


def apply_profile(entry: dict, profiles: dict, asset_dir: Path = ASSET_DIR,
                  public_dir: Path = PUBLIC_DIR) -> None:
    profile = profiles.get(str(entry.get('id') or ''))
    if not isinstance(profile, dict):
        return
    if profile.get('name') != entry.get('name') or profile.get('nameEn') != entry.get('nameEn'):
        raise ValueError(f"Reviewed profile identity changed: {entry.get('id')}")
    filename = str(profile.get('avatarFilename') or '')
    if not re.fullmatch(r'[0-9a-f]{20}\.webp', filename):
        raise ValueError(f"Invalid reviewed portrait filename: {entry.get('id')}")
    source = asset_dir / filename
    if not source.is_file():
        raise ValueError(f"Reviewed portrait is missing: {filename}")
    public_dir.mkdir(parents=True, exist_ok=True)
    target = public_dir / filename
    if not target.exists() or source.read_bytes() != target.read_bytes():
        shutil.copy2(source, target)
    entry['avatarUrl'] = '/assets/source-avatars/' + filename
    summary = str(profile.get('summary') or '').strip()
    if summary:
        entry['summary'] = entry['sourceSummary'] = summary

    tags = profile.get('tags')
    if isinstance(tags, list) and all(isinstance(tag, str) and tag.strip() for tag in tags):
        entry['sourceTags'] = list(tags)
