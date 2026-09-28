import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import build_social_sources as sources

class ReviewedYoutubeChannelsTests(unittest.TestCase):
    def test_channel_identity_is_bound_to_reviewed_name_and_url(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'profiles.json'
            channel='UCxVgtJO8QFgykIFEmt2dsjw'
            row={'public_id':'324','name':'Jason Ricci','youtube_url':'https://www.youtube.com/@jasonricci'}
            path.write_text(json.dumps({'sources':{'watchlist-324':{'name':'Jason Ricci','youtubeUrl':row['youtube_url'],'youtubeChannelId':channel}}}))
            with patch.object(sources,'REVIEWED_PROFILES',path):
                self.assertEqual(sources.parse_youtube_source(row)['channel_id'],channel)
                self.assertNotIn('channel_id',sources.parse_youtube_source(dict(row,name='Other')))
                self.assertNotIn('channel_id',sources.parse_youtube_source(dict(row,youtube_url='https://youtube.com/@other')))

    def test_missing_review_keeps_existing_fetch_behavior(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(sources,'REVIEWED_PROFILES',Path(tmp)/'missing'):
            row=sources.parse_youtube_source({'name':'Channel','youtube_url':'https://youtube.com/@artist'})
            self.assertEqual(row['type'],'youtube_ytdlp')
            self.assertNotIn('channel_id',row)
