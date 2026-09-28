import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_public_data as data

class ProfileIdentityTests(unittest.TestCase):
    def test_facebook_numeric_profiles_retain_identity_query(self):
        left = 'https://www.facebook.com/profile.php?id=100085232439912'
        right = 'https://www.facebook.com/profile.php?id=100070499919459'
        self.assertNotEqual(data.canonical_link_key(left), data.canonical_link_key(right))
        self.assertEqual(data.canonical_link_key(left + '&mibextid=tracking'), data.canonical_link_key(left))
        self.assertEqual(data.canonical_link_key(left.replace('www.', 'm.')), data.canonical_link_key(left))
        self.assertEqual(data.canonical_link_key('https://facebook.com/profile.php'), '')

    def test_different_performers_with_profile_php_do_not_merge(self):
        def row(name, number):
            return {'id':name,'name':name,'type':'個人','category':'演奏者','summary':'口琴教學與影音來源', 'links':[{'url':f'https://www.facebook.com/profile.php?id={number}'}]}
        left,right=row('Timothy Yip','100085232439912'),row('Mariano Massolo','100070499919459')
        self.assertFalse(data.duplicate_entries(left,right))
        self.assertEqual(len(data.merge_duplicate_entries([left,right])),2)
