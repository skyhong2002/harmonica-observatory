#!/usr/bin/env python3
"""Versioned, provider-independent public model for Harmonica Observatory.

Adapters read the existing generated snapshots. No network, credentials or paid
inference happens on a visitor request. Language never filters geographic scope.
"""
from __future__ import annotations
from story_lifecycle import display_expiry

import hashlib
import json
import re
import time
from collections import Counter
from datetime import datetime, timezone
from event_localization import display_translations
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / 'site' / 'api'
NAME_TRANSLATIONS = ROOT / 'data' / 'sources' / 'source-name-translations.json'
DESCRIPTION_TRANSLATIONS = ROOT / 'data' / 'sources' / 'source-description-translations.json'
EVENT_TRANSLATIONS = ROOT / 'data' / 'sources' / 'event-description-translations.json'
SCORE_MEDIA = ROOT / 'data' / 'sources' / 'score-source-media.json'
COUNTRY_CODES = {
    '臺灣': 'TW', '台灣': 'TW', 'Taiwan': 'TW', '中國': 'CN', '中国': 'CN', 'China': 'CN',
    '香港': 'HK', 'Hong Kong': 'HK', '澳門': 'MO', '日本': 'JP', 'Japan': 'JP',
    '韓國': 'KR', '韩国': 'KR', 'South Korea': 'KR', 'Korea': 'KR',
    '馬來西亞': 'MY', 'Malaysia': 'MY', '德國': 'DE', 'Germany': 'DE',
    '美國': 'US', 'United States': 'US', '新加坡': 'SG', 'Singapore': 'SG',
    '巴西': 'BR', 'Brazil': 'BR', '阿根廷': 'AR', 'Argentina': 'AR',
    '英國': 'GB', 'United Kingdom': 'GB', '波蘭': 'PL', 'Poland': 'PL',
    '西班牙': 'ES', 'Spain': 'ES', '法國': 'FR', 'France': 'FR', '以色列': 'IL',
    '俄羅斯': 'RU', '瑞典': 'SE', '丹麥': 'DK', '印尼': 'ID', '瑞士': 'CH',
    '墨西哥': 'MX', '紐西蘭': 'NZ', '挪威': 'NO', '荷蘭': 'NL', '捷克': 'CZ',
    '菲律賓': 'PH', '澳洲': 'AU', '義大利': 'IT', '印度': 'IN', '泰國': 'TH',
    '越南': 'VN', '南非': 'ZA', '加拿大': 'CA', '奧地利': 'AT', '比利時': 'BE', '葡萄牙': 'PT',
    '國際': 'WORLD', '国际': 'WORLD', 'International': 'WORLD',
    '線上': 'ONLINE', 'Online': 'ONLINE',
}
SNAPSHOTS = ('sources.json', 'latest.json', 'scores.json', 'score-sources.json',
             'public-calendar-events.json', 'overseas-calendar-events.json',
             'online-calendar-events.json', 'status.json', 'public-calendar-sync.json')


def country_code(value: object) -> str:
    label = str(value or '').strip()
    matched = next((code for name, code in COUNTRY_CODES.items() if name.casefold() == label.casefold()), None)
    if matched:
        return matched
    if label.upper() in {'WORLD', 'ONLINE', 'UNKNOWN'}:
        return label.upper()
    if re.fullmatch(r'[A-Za-z]{2}', label):
        return label.upper()
    return 'UNKNOWN'


def public_url(value: object, *, local: bool = True) -> str:
    value = str(value or '').strip()
    if any(ord(c) < 32 for c in value) or '\\' in value:
        return ''
    if local and value.startswith('/') and not value.startswith('//'):
        return value
    try:
        parts = urlsplit(value)
        if parts.scheme in ('https', 'http') and parts.hostname and not parts.username and not parts.password:
            return value
    except ValueError:
        pass
    return ''


def read_snapshot(name: str, api_root: Path) -> dict:
    try:
        value = json.loads((api_root / name).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def snapshot_version(api_root: Path = API_ROOT) -> tuple:
    result = []
    for name in SNAPSHOTS:
        try:
            st = (api_root / name).stat()
            result.append((name, st.st_mtime_ns, st.st_size))
        except OSError:
            result.append((name, 0, 0))
    for resource in (NAME_TRANSLATIONS, DESCRIPTION_TRANSLATIONS, EVENT_TRANSLATIONS, SCORE_MEDIA):
        try:
            st = resource.stat()
            result.append((resource.name, st.st_mtime_ns, st.st_size))
        except OSError:
            pass
    # Refresh time-sensitive story and stale-status classifications once/minute.
    result.append(('time_bucket', int(time.time() // 60), 0))
    return tuple(result)


def _list(value: object) -> list:
    return value if isinstance(value, list) else []


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _rows(data: dict, key: str) -> list[dict]:
    return [r for r in _list(data.get(key)) if isinstance(r, dict)]


def _timestamp(value: object) -> float | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def _synthetic_source_row(row: dict) -> bool:
    return (row.get('raw_source') == 'public-link-backfill'
            or row.get('media_type') in {'source_page', 'directory_source_page'}
            or ':source_page:' in str(row.get('key') or '')
            or str(row.get('post_id') or '').startswith('source_page:'))


def _links(rows: object) -> list[dict]:
    if not isinstance(rows, list):
        return []
    return [{'label': str(row.get('label') or ''), 'url': public_url(row.get('url'))}
            for row in rows if isinstance(row, dict) and public_url(row.get('url'))]


def _media_urls(values: object) -> list[str]:
    return list(dict.fromkeys(public_url(v) for v in _list(values) if isinstance(v, str) and public_url(v)))


def _evidence_url(value: object) -> str:
    """Exclude social profiles: matching an author is not a publication relationship."""
    url = public_url(value)
    if not url:
        return ''
    parts = urlsplit(url)
    host = re.sub(r'^(www|m|mobile)\.', '', parts.hostname or '')
    path = parts.path.rstrip('/')
    query = parse_qs(parts.query)
    if host == 'instagram.com':
        valid = re.search(r'^/(p|reel|reels|tv)/[^/]+', path)
    elif host in {'twitter.com', 'x.com'}:
        valid = re.search(r'^/[^/]+/status/\d+', path)
    elif host == 'facebook.com':
        valid = re.search(r'/(posts|videos|reel|photos)/.+', path) or query.get('story_fbid') or query.get('fbid') or (path == '/watch' and query.get('v'))
    elif host in {'threads.net', 'threads.com'}:
        valid = re.search(r'^/@[^/]+/post/[^/]+', path)
    elif host in {'youtube.com', 'youtu.be'}:
        valid = (path and host == 'youtu.be') or (path == '/watch' and query.get('v')) or re.search(r'^/(shorts|embed)/[^/]+', path)
    else:
        valid = bool(path)
    return url if valid else ''


def _id(row: dict, *fields: str) -> str:
    for key in fields:
        if row.get(key):
            return str(row[key])
    return hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]


def build_catalog(api_root: Path | str = API_ROOT, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    observed_at = now.timestamp()
    api_root = Path(api_root)
    snapshots = {name: read_snapshot(name, api_root) for name in SNAPSHOTS}
    source_data = snapshots['sources.json']
    translations = read_snapshot(NAME_TRANSLATIONS.name, NAME_TRANSLATIONS.parent).get('sources', {})
    descriptions = read_snapshot(DESCRIPTION_TRANSLATIONS.name, DESCRIPTION_TRANSLATIONS.parent).get('sources', {})
    sources = []
    monitor_map = {}
    for row in _rows(source_data, 'entries'):
        sid = str(row.get('id') or row.get('publicId') or '')
        source = {
            'id': sid, 'publicId': str(row.get('publicId') or ''),
            'name': str(row.get('name') or ''), 'nameEn': str(row.get('nameEn') or ''),
            'country': str(row.get('country') or ''), 'countryCode': country_code(row.get('country')),
            'region': str(row.get('region') or ''), 'type': str(row.get('type') or ''),
            'tags': [str(t) for t in _list(row.get('sourceTags'))],
            'summary': str(row.get('summary') or row.get('structuredSummary') or ''),
            'url': '/source/' + str(row['slug']) + '/' if row.get('slug') else '/source/',
            'avatar': public_url(row.get('avatarUrl')), 'links': _links(row.get('links')),
            'updatedAt': row.get('latestUpdateAt'),
            'searchText': ' '.join(str(row.get(k) or '') for k in ('name', 'nameEn', 'keywords', 'region', 'summary')),
        }
        translated = _dict(_dict(translations).get(sid))
        # Invalidate reference translations when the recorded source identity changes.
        if translated.get('sourceName') != source['name'] or translated.get('sourceNameEn') != source['nameEn']:
            translated = {}
        names = {language: str(value) for language, value in _dict(translated.get('names')).items()
                 if language in {'zh-Hant', 'en', 'ja', 'ko'} and isinstance(value, str) and value.strip()}
        names.setdefault('zh-Hant', source['name'])
        if source['nameEn']:
            names.setdefault('en', source['nameEn'])
        names['original'] = source['name']
        source.update(names=names, namesMeta={language: {'kind': 'reference'} for language in names if language != 'original'},
                      originalType=str(row.get('originalType') or row.get('type') or ''),
                      aliases=[str(value) for value in _list(row.get('aliases')) if isinstance(value, str)])
        description = _dict(_dict(descriptions).get(sid))
        # Translations describe a specific recorded biography, never a newer revision.
        if (description.get('sourceName') != source['name']
                or description.get('sourceNameEn') != source['nameEn']
                or description.get('sourceSummary') != source['summary']):
            description = {}
        summaries = {language: value for language, value in _dict(description.get('summaries')).items()
                     if language in {'zh-Hant', 'en', 'ja', 'ko'} and isinstance(value, str) and value.strip()}
        summary_language = description.get('summaryLanguage', '')
        if summary_language not in {'zh-Hant', 'en', 'ja', 'ko'}:
            summary_language = ''
        if summary_language and source['summary']:
            summaries[summary_language] = source['summary']
        tags_localized = {}
        if description.get('sourceTags') == source['tags']:
            tags_localized = {language: values for language, values in _dict(description.get('tags')).items()
                              if language in {'zh-Hant', 'en', 'ja', 'ko'} and isinstance(values, list)
                              and len(values) == len(source['tags'])
                              and all(isinstance(value, str) and value.strip() for value in values)}
        source.update(summaries=summaries, summaryLanguage=summary_language, tagsLocalized=tags_localized)
        source['searchText'] += ' ' + ' '.join(names.values()) + ' ' + ' '.join(source['aliases'])
        source['searchText'] += ' ' + ' '.join(summaries.values()) + ' ' + ' '.join(tag for tags in tags_localized.values() for tag in tags)
        sources.append(source)
        for monitor in _list(row.get('monitorSources')):
            if isinstance(monitor, dict):
                monitor_map[str(monitor.get('id') or '')] = source
    source_map = {s['id']: s for s in sources}
    latest = snapshots['latest.json']
    posts = []
    for row in _rows(latest, 'updates'):
        if _synthetic_source_row(row):
            continue
        is_story = bool(row.get('story')) or row.get('media_type') == 'instagram_story'
        display_until = display_expiry(row) if is_story else None
        expiry = display_until.timestamp() if display_until else None
        story_state = ('unknown' if expiry is None else 'active' if expiry > observed_at else 'expired') if is_story else None
        source = source_map.get(str(row.get('directory_entry_id') or '')) or monitor_map.get(str(row.get('source_id') or ''), {})
        webpage = row.get('media_type') == 'webpage_update' or row.get('platform') == 'website'
        posts.append({
            'id': _id(row, 'key', 'id', 'link'),
            'title': str(row.get('display_title') or row.get('headline') or row.get('title') or ''),
            'text': str(row.get('text') or ''), 'url': public_url(row.get('link') or row.get('url')),
            'sourceId': source.get('id', str(row.get('source_id') or '')),
            'sourceName': str(row.get('directory_entry_name') or row.get('source') or ''),
            'sourceUrl': source.get('url', ''), 'countryCode': country_code(row.get('country') or source.get('country')),
            'country': str(row.get('country') or source.get('country') or ''),
            'platform': str(row.get('platform') or ''), 'publishedAt': None if webpage else row.get('posted_at'),
            'contentKind': 'website_snapshot' if webpage else 'post',
            'observedAt': row.get('seen_at') or row.get('fetched_at'),
            'image': public_url(row.get('image_url')), 'avatar': public_url(row.get('source_avatar_url') or row.get('avatar_url')),
            'images': _media_urls(row.get('images')), 'videos': _media_urls(row.get('videos')),
            'videoUrl': public_url(row.get('video_url')) or next(iter(_media_urls(row.get('videos'))), ''),
            'isStory': is_story, 'expiresAt': display_until.isoformat() if display_until else None, 'storyState': story_state,
            'sourceExpiresAt': row.get('story_expires_at') if is_story else None,
            'sourceAvailable': bool(public_url(row.get('link') or row.get('url'))) and (not is_story or story_state == 'active'),
            'tags': [str(t) for t in _list(row.get('categories'))],
        })
    posts.sort(key=lambda row: _timestamp(row.get('publishedAt')) or 0, reverse=True)
    events = []
    seen = set()
    for name in ('public-calendar-events.json', 'overseas-calendar-events.json', 'online-calendar-events.json'):
        for row in _rows(snapshots[name], 'events'):
            eid = _id(row, 'id')
            if eid in seen:
                continue
            seen.add(eid)
            review = row.get('calendarReview') if isinstance(row.get('calendarReview'), dict) else {}
            online = row.get('calendarType') == 'online' or name == 'online-calendar-events.json'
            country = review.get('country') or row.get('country') or ('臺灣' if name == 'public-calendar-events.json' else '')
            source_url = public_url(row.get('evidenceUrl') or row.get('sourceUrl'))
            events.append({
                'id': eid, 'title': str(row.get('title') or row.get('eventName') or ''),
                'start': row.get('start'), 'end': row.get('end'), 'allDay': bool(row.get('allDay')),
                'endEstimated': bool(row.get('endEstimated')),
                'timezone': str(row.get('timezone') or snapshots[name].get('timezone') or 'UTC'),
                'location': str(row.get('location') or row.get('venue') or ''),
                'countryCode': 'ONLINE' if online else country_code(country), 'country': str(country),
                'url': source_url, 'sourceUrl': source_url, 'sourceName': str(row.get('sourceName') or row.get('source') or ''),
                'description': str(row.get('details') or row.get('description') or ''),
                'image': public_url(row.get('image_url')), 'images': _media_urls(row.get('images')),
                'videoUrl': public_url(row.get('video_url')) or next(iter(_media_urls(row.get('videos'))), ''), 'online': online,
            })
    events.sort(key=lambda e: str(e.get('start') or ''))
    event_translations = _dict(read_snapshot(EVENT_TRANSLATIONS.name, EVENT_TRANSLATIONS.parent).get('events'))
    for event in events:
        translated = _dict(event_translations.get(event['id']))
        if (translated.get('title') != event['title']
                or translated.get('sourceUrl') != event['sourceUrl']
                or translated.get('sourceDescription') != event['description']):
            translated = {}
        descriptions = {language: value for language, value in _dict(translated.get('descriptions')).items()
                        if language in {'zh-Hant', 'en', 'ja', 'ko'} and isinstance(value, str) and value.strip()}
        original_language = translated.get('descriptionLanguage', '')
        if original_language not in {'zh-Hant', 'en', 'ja', 'ko'}:
            original_language = ''
        if original_language:
            descriptions[original_language] = event['description']
        event.update(descriptions=descriptions, descriptionLanguage=original_language)
        event.update(display_translations(event, translated))
        if event['titles'] or event['locations']:
            event['displayTranslationKind'] = 'reference'
    scores = []
    for row in _rows(snapshots['scores.json'], 'scores'):
        scores.append({
            'id': _id(row, 'id'), 'title': str(row.get('title') or row.get('scoreName') or ''),
            'composer': str(row.get('composer') or ''), 'arranger': str(row.get('arranger') or ''),
            'instrument': str(row.get('program') or row.get('category') or ''),
            'url': public_url(row.get('publisherUrl') or row.get('sourceUrl')),
            'sourceName': str(row.get('publisher') or row.get('sourceLabel') or ''),
            'sourceUrl': public_url(row.get('sourceUrl')), 'year': str(row.get('schoolYear') or ''),
            'countryCode': country_code(row.get('countryCode') or row.get('country') or 'TW'), 'division': str(row.get('division') or ''),
            'links': _links(row.get('links')), 'notes': str(row.get('performanceNote') or row.get('notes') or ''),
        })
    score_sources = []
    score_media = _dict(read_snapshot(SCORE_MEDIA.name, SCORE_MEDIA.parent).get('sources'))
    for row in _rows(snapshots['score-sources.json'], 'scoreSources'):
        media = _dict(score_media.get(_id(row, 'id')))
        if media.get('title') != row.get('scoreTitle') or media.get('sourceName') != row.get('sourceName'):
            media = {}
        cached = str(media.get('localImage') or '')
        # Checked-in provenance survives offline builds; optional local thumbnails are runtime cache.
        local_cover = cached if re.fullmatch(r'/assets/feed-images/[a-zA-Z0-9_-]+\.webp', cached) and (ROOT / 'site' / cached.lstrip('/')).is_file() else ''
        cover = local_cover or public_url(media.get('imageUrl'), local=False)
        evidence_url = public_url(row.get('evidenceUrl'))
        mismatched = media.get('evidenceStatus') == 'mismatch' and media.get('invalidEvidenceUrl') == evidence_url
        if mismatched:
            evidence_url = public_url(media.get('replacementSourceUrl'), local=False) or public_url(row.get('url'))
        links = [item for item in _links(row.get('links')) if not mismatched or item['url'] != media.get('invalidEvidenceUrl')]
        score_sources.append({
            'id': _id(row, 'id'), 'name': str(row.get('sourceName') or row.get('scoreTitle') or ''),
            'title': str(row.get('scoreTitle') or ''), 'url': public_url(row.get('url')),
            **{key: str(row.get(key) or '') for key in ('format', 'instrumentation', 'purchaseMethod',
                'rightsNote', 'sourceType', 'composer', 'arranger', 'price', 'availability', 'lastSeenAt')},
            'summary': ' · '.join(str(row.get(k) or '') for k in ('scoreTitle', 'instrumentation', 'purchaseMethod', 'rightsNote') if row.get(k)),
            'countryCode': country_code(row.get('country')), 'links': links,
            'sourceUrl': evidence_url, 'count': 1,
            'referenceStatus': 'unverified' if mismatched else '',
            'images': [] if mismatched else list(dict.fromkeys(([cover] if cover else []) + _media_urls(row.get('images')))),
            'imageSourceUrl': public_url(media.get('sourcePage'), local=False),
            # Exact evidence only: the publisher profile is not proof of a score announcement.
            'relatedPosts': [post for post in posts if post['url'] and post['url'] == _evidence_url(evidence_url)
                             and post['url'] != public_url(row.get('url'))],
        })
    counts = Counter(s['countryCode'] for s in sources)
    labels = {s['countryCode']: s['country'] for s in sources}
    for event in events:
        counts.setdefault(event['countryCode'], 0)
        labels.setdefault(event['countryCode'], event['country'])
    countries = [{'code': code, 'name': labels.get(code, code), 'count': count}
                 for code, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))]
    feeds = [
        {'id': 'updates', 'title': 'updates', 'url': '/feeds/updates.xml', 'format': 'RSS'},
        {'id': 'events', 'title': 'events', 'url': '/feeds/events.xml', 'format': 'RSS'},
        {'id': 'posts', 'title': 'posts', 'url': '/feeds/posts-videos.xml', 'format': 'RSS'},
        {'id': 'sources', 'title': 'sources', 'url': '/feeds/sources.xml', 'format': 'RSS'},
        {'id': 'opportunities', 'title': 'opportunities', 'url': '/feeds/opportunities.xml', 'format': 'RSS'},
        {'id': 'clubs', 'title': 'clubs', 'url': '/feeds/student-clubs.xml', 'format': 'RSS'},
        {'id': 'taiwanCalendar', 'title': 'taiwanCalendar', 'url': '/feeds/public-calendar.ics', 'format': 'ICS'},
        {'id': 'worldCalendar', 'title': 'worldCalendar', 'url': '/feeds/overseas-calendar.ics', 'format': 'ICS'},
        {'id': 'onlineCalendar', 'title': 'onlineCalendar', 'url': '/feeds/online-calendar.ics', 'format': 'ICS'},
        {'id': 'json', 'title': 'json', 'url': '/api/v1/catalog', 'format': 'JSON'},
    ]
    raw_status = snapshots['status.json']
    # Explicit allowlist: runtime status can contain process args/local paths.
    platform_rows = _list(_dict(raw_status.get('watchSources')).get('platformRows'))
    status_checked = _timestamp(raw_status.get('generatedAt'))
    snapshot_state = 'missing' if not raw_status else 'stale' if status_checked is None or observed_at - status_checked > 6 * 3600 else 'current'
    status = {
        'overall': (raw_status.get('overall') or {}).get('status', 'unknown') if isinstance(raw_status.get('overall'), dict) else str(raw_status.get('overall') or 'unknown'),
        'updatedAt': raw_status.get('generatedAt'),
        'services': [{'id': r.get('platform'), 'name': r.get('platform'),
                      'status': r.get('status', 'unknown'), 'count': r.get('sources', 0),
                      'errors': r.get('currentErrors', 0)} for r in platform_rows if isinstance(r, dict)],
        'provider': 'mixed', 'scheduler': 'unknown', 'schedulerVerified': False,
        'providers': [
            {'id': 'apify', 'platforms': ['facebook', 'instagram']},
            {'id': 'rsshub-public', 'platforms': ['threads', 'x']},
            {'id': 'youtube-public', 'platforms': ['youtube']},
            {'id': 'webpage-public', 'platforms': ['website']},
            {'id': 'rss', 'platforms': ['other']},
        ],
        'snapshotState': snapshot_state,
        'metrics': {k: v for k, v in _dict(raw_status.get('metrics')).items()
                    if k in ('watchSources', 'currentErrors', 'latestDataAt', 'latestSocialObservationAt')},
    }
    if status['overall'] not in {'ok', 'degraded', 'paused', 'error', 'unknown', 'unavailable'}:
        status['overall'] = 'unknown'
    status['lastKnownOverall'] = status['overall']
    if snapshot_state != 'current':
        status['overall'] = 'unknown'
    calendar_sync = snapshots['public-calendar-sync.json']
    calendars = []
    seen_calendars = set()
    for row in _rows(calendar_sync, 'calendars'):
        identifier = str(row.get('calendarId') or '')
        key = row.get('calendarKey')
        if (key not in {'taiwan', 'overseas', 'online'}
                or not re.fullmatch(r'[A-Za-z0-9_.+-]+@group\.calendar\.google\.com', identifier)
                or identifier in seen_calendars):
            continue
        seen_calendars.add(identifier)
        calendars.append({'id': identifier, 'key': key,
                          'status': row.get('status') if row.get('status') in {'ok', 'error', 'skipped'} else 'unknown',
                          'updatedAt': calendar_sync.get('generatedAt')})
    generated = latest.get('generatedAt') or source_data.get('generatedAt')
    return {
        'schemaVersion': 'harmonica-atlas/v1', 'generatedAt': generated, 'evaluatedAt': now.isoformat(),
        'locales': ['zh-Hant', 'en', 'ja', 'ko'],
        'sources': sources, 'posts': posts, 'stories': [post for post in posts if post['storyState'] == 'active'],
        'events': events, 'calendars': calendars, 'scores': scores,
        'scoreSources': score_sources, 'countries': countries, 'feeds': feeds,
        'stats': {'sources': len(sources), 'posts': len(posts), 'events': len(events),
                  'scores': len(scores), 'countries': sum(c not in ('WORLD', 'ONLINE', 'UNKNOWN') for c in counts),
                  'watchSources': status['metrics'].get('watchSources', 0)},
        'status': status,
        'dataAvailability': {name: bool(value) for name, value in snapshots.items()},
    }


if __name__ == '__main__':
    print(json.dumps(build_catalog(), ensure_ascii=False, indent=2))
