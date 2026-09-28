"""Attach reviewed event display translations without changing source records."""
from __future__ import annotations

LOCALES = {'zh-Hant', 'en', 'ja', 'ko'}


def display_translations(event: dict, record: dict) -> dict:
    """Reject stale identity/content; venue translations also bind to the venue."""
    valid = (record.get('title') == event.get('title')
             and record.get('sourceUrl') == event.get('sourceUrl')
             and record.get('sourceDescription') == event.get('description'))
    result = {'titles': {}, 'locations': {}}
    if not valid:
        return result
    for field in ('titles', 'locations'):
        if field == 'locations' and record.get('sourceLocation') != event.get('location'):
            continue
        values = record.get(field)
        if isinstance(values, dict):
            result[field] = {locale: value.strip() for locale, value in values.items()
                             if locale in LOCALES and isinstance(value, str) and value.strip()}
    return result
