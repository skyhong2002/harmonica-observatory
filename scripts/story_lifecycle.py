"""Shared display lifetime for cached Instagram story previews."""
from datetime import datetime, timedelta, timezone

STORY_DISPLAY_HOURS = 48


def display_expiry(row):
    """Expire 48 hours after publication, never 48 hours after a refresh."""
    try:
        published = datetime.fromisoformat(str(row.get('posted_at')).replace('Z', '+00:00'))
        if published.tzinfo is None:
            return None
        return published.astimezone(timezone.utc) + timedelta(hours=STORY_DISPLAY_HOURS)
    except (TypeError, ValueError, OverflowError):
        return None
