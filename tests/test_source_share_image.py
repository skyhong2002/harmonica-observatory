import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from render_shell import render_document


TEMPLATE = '<html><head><title>Harmonica Observatory</title></head><body><!--SERVER_CONTENT--></body></html>'
ORIGIN = 'https://harmonica.observe.tw'
AVATAR = '/assets/source-avatars/0123456789abcdef0123.webp'


class Metadata(HTMLParser):
    def __init__(self, document):
        super().__init__()
        self.values = {}
        self.feed(document)

    def handle_starttag(self, tag, attrs):
        if tag == 'meta':
            attrs = dict(attrs)
            if 'property' in attrs:
                self.values[attrs['property']] = attrs.get('content')


class SourceShareImageTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            'id': 'watchlist-42', 'url': '/source/artist-42/', 'name': '原名',
            'nameEn': 'English Artist', 'avatar': AVATAR,
            'names': {'en': 'Artist <One> & "Two"', 'ja': '演奏家'},
            'summary': 'Public biography', 'links': [],
        }
        self.catalog = {'sources': [self.source], 'posts': []}

    def render(self, path='/source/artist-42/', locale='en', origin=ORIGIN):
        return render_document(TEMPLATE, path, self.catalog, origin, locale)

    def test_source_image_is_absolute_and_alt_matches_localized_source_name(self):
        document = self.render(origin=ORIGIN + '/')
        metadata = Metadata(document).values
        self.assertEqual(metadata['og:image'], ORIGIN + AVATAR)
        self.assertEqual(metadata['og:image:alt'], 'Artist <One> & "Two"')
        self.assertIn('content="Artist &lt;One&gt; &amp; &quot;Two&quot;"', document)
        self.assertNotIn('<One>', document)
        self.assertEqual(Metadata(self.render(locale='ja')).values['og:image:alt'], '演奏家')
        self.source['names'] = {}
        self.assertEqual(Metadata(self.render()).values['og:image:alt'], 'English Artist')

    def test_legacy_source_routes_share_the_same_verified_avatar(self):
        for path in ['/source/watchlist-42/', '/post/source/watchlist-42/', '/post/source/artist-42/']:
            with self.subTest(path=path):
                metadata = Metadata(self.render(path)).values
                self.assertEqual(metadata['og:image'], ORIGIN + AVATAR)

    def test_existing_named_jpeg_is_supported_without_guessing_a_webp(self):
        self.source['avatar'] = '/assets/source-avatars/taiping-elementary-harmonica.jpg'
        metadata = Metadata(self.render()).values
        self.assertEqual(metadata['og:image'], ORIGIN + self.source['avatar'])

    def test_missing_external_and_invalid_avatars_have_no_image_metadata(self):
        for avatar in [None, '', 'https://example.org/portrait.jpg', '//example.org/portrait.jpg',
                       '/assets/other/portrait.webp', '/assets/source-avatars/../portrait.webp',
                       '/assets/source-avatars/%2e%2e/portrait.webp',
                       '/assets/source-avatars/portrait.webp?remote=1',
                       '/assets/source-avatars/portrait.webp#fragment',
                       '/assets/source-avatars/<literal>.webp',
                       '/assets/source-avatars/portrait.svg', {'url': AVATAR}]:
            with self.subTest(avatar=avatar):
                self.source['avatar'] = avatar
                metadata = Metadata(self.render()).values
                self.assertNotIn('og:image', metadata)
                self.assertNotIn('og:image:alt', metadata)

    def test_generic_and_unknown_pages_do_not_borrow_a_source_portrait(self):
        for path in ['/', '/source/', '/post/', '/post/source/', '/events/', '/scores/', '/source/unknown/']:
            with self.subTest(path=path):
                metadata = Metadata(self.render(path)).values
                self.assertNotIn('og:image', metadata)
                self.assertNotIn('og:image:alt', metadata)

    def test_image_origin_requires_http_origin_without_credentials(self):
        for origin in ['javascript:alert(1)', 'file:///tmp/site', '//example.org', 'https://user:secret@example.org']:
            with self.subTest(origin=origin):
                self.assertNotIn('og:image', Metadata(self.render(origin=origin)).values)


if __name__ == '__main__':
    unittest.main()
