import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_rss_feeds


class SourceProfileAvatarRetryTests(unittest.TestCase):
    def run_profiles(self, root: Path, fetched_avatar: str = '') -> int:
        calls = []

        def fake_fetch(source):
            calls.append(source['id'])
            return {'id': source['id'], 'avatar_source_url': fetched_avatar}

        with patch.object(generate_rss_feeds, 'SOCIAL_SOURCES', root / 'sources.json'), \
                patch.object(generate_rss_feeds, 'SOURCE_PROFILES_CACHE', root / 'profiles.json'), \
                patch.object(generate_rss_feeds, 'fetch_source_profile', fake_fetch), \
                patch.object(generate_rss_feeds, 'ensure_profile_avatar_url', lambda profile: False):
            generate_rss_feeds.build_source_profiles([{'source_id': 'ig_blocked'}])
        return len(calls)

    def test_source_without_avatar_is_fetched_again_only_after_retry_delay(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'sources.json').write_text(json.dumps({'sources': [{'id': 'ig_blocked', 'name': 'Blocked'}]}), encoding='utf-8')

            self.assertEqual(self.run_profiles(root), 1)
            self.assertEqual(self.run_profiles(root), 0)

            cache = json.loads((root / 'profiles.json').read_text(encoding='utf-8'))
            stale = dt.datetime.now(dt.timezone.utc) - generate_rss_feeds.PROFILE_AVATAR_RETRY_AFTER - dt.timedelta(minutes=1)
            cache['avatarAttempts']['ig_blocked'] = stale.isoformat()
            (root / 'profiles.json').write_text(json.dumps(cache), encoding='utf-8')

            self.assertEqual(self.run_profiles(root, 'https://example.com/avatar.jpg'), 1)
            cache = json.loads((root / 'profiles.json').read_text(encoding='utf-8'))
            self.assertNotIn('ig_blocked', cache['avatarAttempts'])
            self.assertEqual(cache['profiles']['ig_blocked']['avatar_source_url'], 'https://example.com/avatar.jpg')
            self.assertEqual(self.run_profiles(root), 0)


if __name__ == '__main__':
    unittest.main()
