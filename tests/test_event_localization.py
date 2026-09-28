import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from event_localization import display_translations


class EventLocalizationTests(unittest.TestCase):
    def setUp(self):
        self.event = {'title': '音樂會', 'location': '音樂廳', 'sourceUrl': 'https://example.org/event', 'description': '說明'}
        self.record = {'title': '音樂會', 'sourceLocation': '音樂廳', 'sourceUrl': 'https://example.org/event', 'sourceDescription': '說明', 'titles': {'en': 'Concert', 'ja': 'コンサート'}, 'locations': {'en': 'Concert hall'}}

    def test_translations_preserve_original_record(self):
        result = display_translations(self.event, self.record)
        self.assertEqual(result['titles']['en'], 'Concert')
        self.assertEqual(result['locations']['en'], 'Concert hall')
        self.assertEqual(self.event['title'], '音樂會')
        self.assertEqual(self.event['location'], '音樂廳')

    def test_changed_identity_or_content_rejects_translation(self):
        for field in ['title', 'sourceUrl', 'description']:
            with self.subTest(field=field):
                self.assertEqual(display_translations(dict(self.event, **{field: 'changed'}), self.record), {'titles': {}, 'locations': {}})

    def test_venue_change_drops_only_venue_translation(self):
        result = display_translations(dict(self.event, location='別館'), self.record)
        self.assertEqual(result['titles']['en'], 'Concert')
        self.assertEqual(result['locations'], {})

    def test_invalid_or_unsupported_values_are_ignored(self):
        record = dict(self.record, titles={'en': ' ', 'ja': 1, 'xx': 'No'}, locations=[])
        self.assertEqual(display_translations(self.event, record), {'titles': {}, 'locations': {}})
