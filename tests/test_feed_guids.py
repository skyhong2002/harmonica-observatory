import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import generate_rss_feeds as feeds


class FeedGuidTests(unittest.TestCase):
    def test_source_and_update_guids_are_identifiers_not_crawlable_urls(self):
        data = {'entries': [{'name': 'FCU Harmonica', 'links': [{'url': 'https://www.facebook.com/FCUharmonica/'}]}]}
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(feeds, 'parse_site_data', return_value=data), \
                patch.object(feeds, 'SOURCES_OUT', Path(directory) / 'sources.xml'), \
                patch.object(feeds, 'API_DIR', Path(directory) / 'api'):
            feeds.generate_sources(0)
            guid = ET.parse(Path(directory) / 'sources.xml').find('channel/item/guid')
        self.assertTrue(guid.text.startswith(feeds.PUBLIC_BASE_URL + '/feeds/sources/'))
        self.assertEqual(guid.get('isPermaLink'), 'false')

        channel = ET.Element('channel')
        feeds.add_update_item(channel, {'title': 'Concert', 'link': 'https://example.org/a', 'key': 'web_1:abc'})
        self.assertEqual(channel.find('item/guid').get('isPermaLink'), 'false')


if __name__ == '__main__':
    unittest.main()
