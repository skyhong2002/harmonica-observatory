import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import community
import review_community_submissions as moderation
import submission_intake as intake


class CommunityModerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {'HARMONICA_COMMUNITY_STATE': str(self.root / 'community')})
        self.env.start()
        self.database = self.root / 'intake.sqlite'
        self.item = community.submit('private-browser-owner', {'url': 'https://example.org/event', 'note': 'Concert in Tokyo, 20:00 Japan time.', 'countryCode': 'JP'})

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_export_is_idempotent_preserves_geography_and_never_processes(self):
        with patch('urllib.request.urlopen', side_effect=AssertionError('network forbidden')), patch('submission_intake.llm_backend.chat', side_effect=AssertionError('inference forbidden')):
            first = moderation.export_submission(self.item['id'], 'Tokyo ensemble', 'event', intake_path=self.database)
            second = moderation.export_submission(self.item['id'], 'Tokyo ensemble', 'event', intake_path=self.database)
        self.assertTrue(first['inserted'])
        self.assertFalse(second['inserted'])
        self.assertEqual(community.owner_submissions('private-browser-owner')[0]['status'], 'reviewing')
        store = intake.IntakeStore(self.database)
        try:
            row = store.get(first['intakeId'])
            self.assertEqual(row['status'], 'pending')
            self.assertEqual(row['attempts'], 0)
            answers = json.loads(row['answers_json'])
            self.assertEqual(answers[intake.PRIMARY_URL], self.item['url'])
            self.assertEqual(answers[intake.EVENT_DETAILS], self.item['note'])
            self.assertIn('Country code: JP', answers[intake.DESIRED_RESULT])
            self.assertNotIn('private-browser-owner', row['answers_json'])
        finally:
            store.close()
        self.assertFalse((self.root / 'data/sources').exists())

    def test_operator_marks_status_visible_to_original_browser(self):
        for status in ('reviewing', 'accepted', 'rejected', 'pending'):
            self.assertEqual(moderation.mark_submission(self.item['id'], status)['status'], status)
            self.assertEqual(community.owner_submissions('private-browser-owner')[0]['status'], status)
        listed = moderation.list_submissions()
        self.assertEqual(listed[0]['id'], self.item['id'])
        self.assertNotIn('owner', listed[0])
        self.assertNotIn('private-browser-owner', json.dumps(listed))

    def test_terminal_status_cannot_be_accidentally_reexported(self):
        moderation.mark_submission(self.item['id'], 'rejected')
        with self.assertRaisesRegex(ValueError, 'pending or reviewing'):
            moderation.export_submission(self.item['id'], 'Rejected', 'source', intake_path=self.database)
        self.assertFalse(self.database.exists())

    def test_invalid_names_and_ids_fail_without_changing_status(self):
        for name in ('', ' ', 'x' * 501):
            with self.assertRaises(ValueError):
                moderation.export_submission(self.item['id'], name, 'source', intake_path=self.database)
        with self.assertRaises(ValueError):
            moderation.mark_submission('missing', 'accepted')
        with self.assertRaises(ValueError):
            moderation.mark_submission(self.item['id'], 'invented-status')
        self.assertEqual(community.owner_submissions('private-browser-owner')[0]['status'], 'pending')

    def test_cli_lists_safe_rows_as_json(self):
        stream = io.StringIO()
        with patch.object(sys, 'argv', ['review_community_submissions.py', 'list']), patch('sys.stdout', stream):
            self.assertEqual(moderation.main(), 0)
        result = json.loads(stream.getvalue())
        self.assertEqual(result[0]['url'], self.item['url'])
        self.assertNotIn('private-browser-owner', stream.getvalue())


if __name__ == '__main__':
    unittest.main()
