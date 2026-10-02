import json
from datetime import datetime, timezone
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import global_catalog as catalog


class CatalogTests(unittest.TestCase):
    def test_event_translations_are_bound_to_exact_record_and_preserve_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'events-translated.json'
            event = {'id': 'concert', 'title': '演出', 'start': '2026-10-01',
                     'sourceUrl': 'https://example.org/concert', 'description': '活動說明'}
            translation = {'title': '演出', 'sourceUrl': event['sourceUrl'], 'sourceDescription': '活動說明',
                           'descriptionLanguage': 'zh-Hant', 'descriptions': {'en': 'Concert details', 'zh-Hant': 'Do not overwrite', 'fr': 'Unsupported'}}
            manifest.write_text(json.dumps({'events': {'concert': translation}}))
            snapshot = root / 'public-calendar-events.json'
            snapshot.write_text(json.dumps({'events': [event]}))
            with patch.object(catalog, 'EVENT_TRANSLATIONS', manifest):
                result = catalog.build_catalog(root)['events'][0]
                self.assertEqual(result['description'], '活動說明')
                self.assertEqual(result['descriptions'], {'en': 'Concert details', 'zh-Hant': '活動說明'})
                for key in ('title', 'sourceUrl', 'description'):
                    with self.subTest(key=key):
                        changed = dict(event, **{key: 'https://example.org/changed' if key == 'sourceUrl' else 'changed'})
                        snapshot.write_text(json.dumps({'events': [changed]}))
                        result = catalog.build_catalog(root)['events'][0]
                        self.assertEqual(result['descriptions'], {})
                        self.assertEqual(result['descriptionLanguage'], '')

    def test_biography_translations_keep_original_and_reject_stale_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'descriptions.json'
            source = {'id': 'a', 'name': '原名', 'nameEn': 'Name', 'summary': '原文說明', 'sourceTags': ['演奏者']}
            translation = {'sourceName': '原名', 'sourceNameEn': 'Name', 'sourceSummary': '原文說明',
                           'summaryLanguage': 'zh-Hant', 'sourceTags': ['演奏者'],
                           'summaries': {'en': 'Biography <literal>', 'zh-Hant': 'Do not replace original', 'fr': 'Unsupported'},
                           'tags': {'en': ['Performer'], 'ja': ['演奏家'], 'ko': [''], 'fr': ['Unsupported']}}
            manifest.write_text(json.dumps({'sources': {'a': translation}}))
            def write_source():
                (root / 'sources.json').write_text(json.dumps({'entries': [source]}))
            write_source()
            with patch.object(catalog, 'DESCRIPTION_TRANSLATIONS', manifest):
                result = catalog.build_catalog(root)['sources'][0]
                self.assertEqual(result['summary'], '原文說明')
                self.assertEqual(result['tags'], ['演奏者'])
                self.assertEqual(result['summaries'], {'en': 'Biography <literal>', 'zh-Hant': '原文說明'})
                self.assertEqual(result['summaryLanguage'], 'zh-Hant')
                self.assertEqual(result['tagsLocalized'], {'en': ['Performer'], 'ja': ['演奏家']})
                self.assertIn('Biography <literal>', result['searchText'])
                source['sourceTags'].append('教育')
                write_source()
                self.assertEqual(catalog.build_catalog(root)['sources'][0]['tagsLocalized'], {})
                for field in ('name', 'nameEn', 'summary'):
                    with self.subTest(field=field):
                        original = source[field]
                        source[field] = 'Changed content'
                        write_source()
                        result = catalog.build_catalog(root)['sources'][0]
                        self.assertEqual(result['summaries'], {})
                        self.assertEqual(result['summaryLanguage'], '')
                        self.assertEqual(result['tagsLocalized'], {})
                        source[field] = original

    def test_biography_manifest_invalidates_cache_and_missing_translation_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = root / 'descriptions.json'
            (root / 'sources.json').write_text(json.dumps({'entries': [{'id': 'a', 'name': 'Artist', 'summary': 'Original'}]}))
            with patch.object(catalog, 'DESCRIPTION_TRANSLATIONS', manifest), patch.object(catalog.time, 'time', return_value=1000):
                before = catalog.snapshot_version(root)
                manifest.write_text('{')
                self.assertNotEqual(before, catalog.snapshot_version(root))
                source = catalog.build_catalog(root)['sources'][0]
                self.assertEqual(source['summary'], 'Original')
                self.assertEqual(source['summaries'], {})
                self.assertEqual(source['tagsLocalized'], {})

    def test_reference_names_keep_original_and_invalidate_stale_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = root / 'translations.json'
            names.write_text(json.dumps({'sources': {'a': {'sourceName': '原名', 'sourceNameEn': 'Name',
                'names': {'zh-Hant': '中文譯名', 'en': 'English Name', 'ja': '日本語名', 'ko': '한국어 이름'}}}}))
            source = {'id': 'a', 'name': '原名', 'nameEn': 'Name', 'type': 'artist', 'originalType': '演奏者'}
            (root / 'sources.json').write_text(json.dumps({'entries': [source]}))
            with patch.object(catalog, 'NAME_TRANSLATIONS', names):
                result = catalog.build_catalog(root)['sources'][0]
                self.assertEqual(result['names']['original'], '原名')
                self.assertEqual(result['names']['ko'], '한국어 이름')
                self.assertIn('日本語名', result['searchText'])
                self.assertEqual(result['originalType'], '演奏者')
                self.assertEqual(result['namesMeta']['ko']['kind'], 'reference')
                source['name'] = 'Changed identity'
                (root / 'sources.json').write_text(json.dumps({'entries': [source]}))
                self.assertNotIn('ko', catalog.build_catalog(root)['sources'][0]['names'])

    def test_media_and_score_references_use_safe_exact_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'latest.json').write_text(json.dumps({'updates': [
                {'key': 'post', 'link': 'https://example.org/post/1', 'text': 'Original',
                 'images': ['/assets/real.webp', 'javascript:bad'], 'videos': ['https://example.org/video.mp4']},
                {'key': 'profile', 'link': 'https://example.org/profile', 'text': 'Unrelated profile'}]}))
            (root / 'score-sources.json').write_text(json.dumps({'scoreSources': [
                {'id': 'yes', 'url': 'https://example.org/profile', 'evidenceUrl': 'https://example.org/post/1',
                 'format': '紙本教材', 'purchaseMethod': '分類頁查詢', 'lastSeenAt': '2026-07-03', 'availability': '待確認'},
                {'id': 'no', 'url': 'https://example.org/profile', 'evidenceUrl': 'https://example.org/profile'}]}))
            result = catalog.build_catalog(root)
            self.assertEqual(result['posts'][0]['images'], ['/assets/real.webp'])
            self.assertEqual(result['posts'][0]['videoUrl'], 'https://example.org/video.mp4')
            self.assertEqual(result['scoreSources'][0]['relatedPosts'][0]['text'], 'Original')
            self.assertEqual(result['scoreSources'][1]['relatedPosts'], [])
            self.assertEqual(result['scoreSources'][0]['format'], '紙本教材')
            self.assertEqual(result['scoreSources'][0]['purchaseMethod'], '分類頁查詢')
            self.assertEqual(result['scoreSources'][0]['lastSeenAt'], '2026-07-03')
            self.assertEqual(result['scoreSources'][0]['availability'], '待確認')

    def test_reviewed_score_covers_keep_provenance_and_reject_stale_or_mismatched_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = [{'id': 'book', 'scoreTitle': 'Book', 'sourceName': 'Shop', 'url': 'https://example.org/',
                     'evidenceUrl': 'https://example.org/category'},
                    {'id': 'notice', 'scoreTitle': 'Notice', 'sourceName': 'Band', 'url': 'https://facebook.com/band/',
                     'evidenceUrl': 'https://facebook.com/band/photos/123/',
                     'images': ['https://example.org/unrelated.jpg'],
                     'links': [{'label': 'bad', 'url': 'https://facebook.com/band/photos/123/'}]}]
            (root / 'score-sources.json').write_text(json.dumps({'scoreSources': rows}))
            media = root / 'media.json'
            media.write_text(json.dumps({'sources': {
                'book': {'title': 'Book', 'sourceName': 'Shop', 'imageUrl': 'https://example.org/cover.jpg',
                         'sourcePage': 'https://example.org/product/book', 'localImage': '/assets/feed-images/missing-cover.webp'},
                'notice': {'title': 'Notice', 'sourceName': 'Band', 'evidenceStatus': 'mismatch',
                           'invalidEvidenceUrl': rows[1]['evidenceUrl'], 'replacementSourceUrl': rows[1]['url']}}}))
            with patch.object(catalog, 'SCORE_MEDIA', media):
                result = catalog.build_catalog(root)['scoreSources']
                self.assertEqual(result[0]['images'], ['https://example.org/cover.jpg'])
                self.assertEqual(result[0]['imageSourceUrl'], 'https://example.org/product/book')
                self.assertEqual(result[1]['id'], 'notice')
                self.assertEqual(result[1]['referenceStatus'], 'unverified')
                self.assertEqual(result[1]['sourceUrl'], rows[1]['url'])
                self.assertEqual(result[1]['images'], [])
                self.assertEqual(result[1]['links'], [])
                rows[0]['scoreTitle'] = 'Different book'
                (root / 'score-sources.json').write_text(json.dumps({'scoreSources': rows}))
                self.assertEqual(catalog.build_catalog(root)['scoreSources'][0]['images'], [])

    def test_profile_urls_are_not_publication_evidence(self):
        for url in ['https://www.instagram.com/band/', 'https://facebook.com/band/',
                    'https://x.com/band', 'https://youtube.com/@band', 'https://threads.net/@band']:
            self.assertEqual(catalog._evidence_url(url), '')
        for url in ['https://facebook.com/band/photos/post/123/', 'https://facebook.com/photo.php?fbid=123',
                    'https://instagram.com/p/abc/', 'https://youtube.com/watch?v=abc',
                    'https://example.org/music/score.pdf']:
            self.assertEqual(catalog._evidence_url(url), url)

    def test_geography_never_defaults_unknown_to_taiwan(self):
        self.assertEqual(catalog.country_code('韓國'), 'KR')
        self.assertEqual(catalog.country_code('jp'), 'JP')
        self.assertEqual(catalog.country_code(''), 'UNKNOWN')
        self.assertEqual(catalog.country_code('unverified'), 'UNKNOWN')

    def test_website_observation_is_not_a_publication_date(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rows = [{'key': 'web-old', 'platform': 'website', 'media_type': 'webpage_update',
                     'posted_at': '2026-09-22T14:00:00Z', 'seen_at': '2026-09-22T14:01:00Z',
                     'text': 'Original archived page text', 'link': 'https://example.org/2018/'}]
            (path / 'latest.json').write_text(json.dumps({'updates': rows}))
            post = catalog.build_catalog(path)['posts'][0]
            self.assertIsNone(post['publishedAt'])
            self.assertEqual(post['contentKind'], 'website_snapshot')
            self.assertEqual(post['observedAt'], rows[0]['seen_at'])
            self.assertEqual(post['text'], rows[0]['text'])

    def test_unsafe_links_are_not_exposed(self):
        for url in ['javascript:alert(1)', '//host/path', '/\\host', 'https://user:password@example.org', 'https://example.org\n/path']:
            self.assertEqual(catalog.public_url(url), '')
        self.assertEqual(catalog.public_url('/source/42-test/'), '/source/42-test/')

    def test_empty_install_and_malformed_snapshot_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'sources.json').write_text('{')
            result = catalog.build_catalog(path)
            self.assertEqual(result['stats']['sources'], 0)
            self.assertIsNone(result['generatedAt'])
            self.assertFalse(result['dataAvailability']['sources.json'])

    def test_sources_posts_dates_and_public_status_are_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            def put(name, value):
                (path / name).write_text(json.dumps(value))
            put('sources.json', {'entries': [{'id': 'watchlist-9', 'publicId': '9', 'slug': '9-seoul', 'name': '서울', 'country': '韓國', 'monitorSources': [{'id': 'ig_seoul'}]}]})
            put('latest.json', {'generatedAt': '2026-09-23T00:00:00Z', 'updates': [{'source_id': 'ig_seoul', 'link': 'https://example.org/post', 'text': 'Original 한국어', 'posted_at': '2026-09-20T12:00:00+09:00'}]})
            event = {'id': 'concert', 'title': '공연', 'start': '2026-10-01T19:00:00+09:00', 'timezone': 'Asia/Seoul', 'calendarReview': {'country': '韓國'}, 'evidenceUrl': 'https://example.org/event'}
            put('overseas-calendar-events.json', {'events': [event]})
            put('online-calendar-events.json', {'events': [dict(event, id='stream', calendarType='online')]})
            put('status.json', {'runtime': {'secret': 'NEVER-EXPOSE'}, 'metrics': {'watchSources': 1, 'secret': 'NEVER-EXPOSE'}, 'watchSources': {'platformRows': [{'platform': 'instagram', 'status': 'paused', 'sources': 1}]}})
            result = catalog.build_catalog(path)
            self.assertEqual(result['posts'][0]['countryCode'], 'KR')
            self.assertEqual(result['posts'][0]['sourceId'], 'watchlist-9')
            self.assertEqual(result['posts'][0]['text'], 'Original 한국어')
            self.assertEqual(result['sources'][0]['url'], '/source/9-seoul/')
            self.assertEqual(result['events'][0]['start'], event['start'])
            self.assertEqual(result['events'][1]['countryCode'], 'ONLINE')
            self.assertNotIn('NEVER-EXPOSE', json.dumps(result))
            self.assertEqual(result['status']['services'][0]['status'], 'paused')

    def test_calendar_embed_metadata_is_allowlisted_and_tracks_snapshot_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            before = catalog.snapshot_version(path)
            rows = [
                {'calendarId': 'public@group.calendar.google.com', 'calendarKey': 'taiwan', 'status': 'ok', 'credentials': 'PRIVATE'},
                {'calendarId': 'bad@example.org', 'calendarKey': 'overseas'},
                {'calendarId': 'public@group.calendar.google.com', 'calendarKey': 'online'},
                {'calendarId': 'another@group.calendar.google.com', 'calendarKey': 'untrusted'},
            ]
            (path / 'public-calendar-sync.json').write_text(json.dumps({'calendars': rows, 'generatedAt': '2026-09-23T00:00:00Z', 'lockFile': 'PRIVATE'}))
            result = catalog.build_catalog(path)
            self.assertEqual(result['calendars'], [{'id': 'public@group.calendar.google.com', 'key': 'taiwan', 'status': 'ok', 'updatedAt': '2026-09-23T00:00:00Z'}])
            self.assertNotIn('PRIVATE', json.dumps(result))
            self.assertNotEqual(before, catalog.snapshot_version(path))

    def test_synthetic_source_backfills_never_become_posts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rows = [{'id': 'page', 'media_type': 'source_page'},
                    {'id': 'directory', 'media_type': 'directory_source_page'},
                    {'id': 'raw', 'raw_source': 'public-link-backfill'},
                    {'key': 'fb_test:source_page:digest'},
                    {'post_id': 'source_page:digest'}, {'id': 'real', 'text': 'Actual post'}]
            (path / 'latest.json').write_text(json.dumps({'updates': rows}))
            result = catalog.build_catalog(path)
            self.assertEqual([row['id'] for row in result['posts']], ['real'])
            self.assertEqual(result['stats']['posts'], 1)

    def test_stories_display_for_48_hours_from_publication_preserving_provider_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rows = [{'id': name, 'story': True, 'posted_at': published,
                     'story_expires_at': '2026-09-22T12:00:00Z', 'link': 'https://example.org/story'}
                    for name, published in [('past', '2026-09-20T00:00:00Z'),
                                            ('boundary', '2026-09-21T00:00:00Z'),
                                            ('cached', '2026-09-21T12:00:00Z'),
                                            ('recent', '2026-09-22T18:00:00Z'),
                                            ('unknown', None), ('naive', '2026-09-22T00:00:00')]]
            (path / 'latest.json').write_text(json.dumps({'updates': rows}))
            result = catalog.build_catalog(path, now=datetime(2026, 9, 23, tzinfo=timezone.utc))
            self.assertEqual(len(result['posts']), 6)
            self.assertEqual([row['id'] for row in result['stories']], ['recent', 'cached'])
            by_id = {r['id']: r for r in result['posts']}
            self.assertEqual(by_id['cached']['expiresAt'], '2026-09-23T12:00:00+00:00')
            self.assertEqual(by_id['cached']['sourceExpiresAt'], '2026-09-22T12:00:00Z')
            self.assertEqual(by_id['boundary']['storyState'], 'expired')
            self.assertFalse(by_id['past']['sourceAvailable'])
            self.assertEqual(by_id['unknown']['storyState'], 'unknown')
            self.assertFalse(by_id['naive']['sourceAvailable'])
            later = catalog.build_catalog(path, now=datetime(2026, 9, 23, 12, tzinfo=timezone.utc))
            self.assertEqual([row['id'] for row in later['stories']], ['recent'])

    def test_incomplete_valid_json_does_not_break_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'sources.json').write_text(json.dumps({'entries': [{'id': 'a', 'sourceTags': None, 'monitorSources': None}]}))
            (path / 'latest.json').write_text(json.dumps({'updates': None}))
            (path / 'status.json').write_text(json.dumps({'watchSources': [], 'metrics': []}))
            result = catalog.build_catalog(path)
            self.assertEqual(result['sources'][0]['tags'], [])
            self.assertEqual(result['posts'], [])
            self.assertEqual(result['status']['overall'], 'unknown')

    def test_timezone_offsets_sort_by_actual_time(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            rows = [{'id': 'older', 'posted_at': '2026-09-23T01:00:00+09:00'},
                    {'id': 'newer', 'posted_at': '2026-09-22T20:00:00Z'}]
            (path / 'latest.json').write_text(json.dumps({'updates': rows}))
            self.assertEqual([row['id'] for row in catalog.build_catalog(path)['posts']], ['newer', 'older'])

    def test_stale_status_is_last_known_not_current_health(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'status.json').write_text(json.dumps({'generatedAt': '2026-09-20T00:00:00Z', 'overall': {'status': 'ok'}}))
            status = catalog.build_catalog(path, now=datetime(2026, 9, 23, tzinfo=timezone.utc))['status']
            self.assertEqual(status['overall'], 'unknown')
            self.assertEqual(status['lastKnownOverall'], 'ok')
            self.assertEqual(status['snapshotState'], 'stale')
            self.assertEqual(status['provider'], 'mixed')
            self.assertFalse(status['schedulerVerified'])


if __name__ == '__main__':
    unittest.main()
