import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from curated_source_profiles import apply_profile, load_profiles

class CuratedProfileTests(unittest.TestCase):
    def test_reviewed_profile_survives_missing_runtime_caches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); assets = root/'assets'; public = root/'public'; assets.mkdir()
            filename = '0123456789abcdefabcd.webp'
            (assets/filename).write_bytes(b'portrait')
            row = {'id':'watchlist-400', 'name':'Artist', 'nameEn':'Artist'}
            profiles = {row['id']:{'name':'Artist','nameEn':'Artist','summary':'Verified performer.', 'avatarFilename':filename}}
            apply_profile(row, profiles, assets, public)
            self.assertEqual(row['summary'], 'Verified performer.')
            self.assertEqual(row['sourceSummary'], row['summary'])
            self.assertEqual(row['avatarUrl'], '/assets/source-avatars/'+filename)
            self.assertEqual((public/filename).read_bytes(), b'portrait')
            apply_profile(row, profiles, assets, public)

    def test_identity_change_is_not_silently_reassigned(self):
        with self.assertRaisesRegex(ValueError, 'identity changed'):
            apply_profile({'id':'x','name':'Different','nameEn':'Different'}, {'x':{'name':'Artist','nameEn':'Artist'}})

    def test_missing_manifest_leaves_unreviewed_entries_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(load_profiles(Path(tmp)/'missing.json'), {})
        row = {'id':'x', 'summary':'Original'}
        apply_profile(row,{})
        self.assertEqual(row, {'id':'x', 'summary':'Original'})

    def test_missing_or_invalid_portrait_fails_build(self):
        row={'id':'x','name':'Artist','nameEn':'Artist'}
        for filename in ['../portrait.webp','0123456789abcdefabcd.webp']:
            with tempfile.TemporaryDirectory() as tmp, self.assertRaises(ValueError):
                apply_profile(row, {'x':dict(row,avatarFilename=filename)}, Path(tmp), Path(tmp)/'public')
