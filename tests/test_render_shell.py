import html
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import render_shell

TEMPLATE = '<!doctype html><html lang="en"><head><title>Harmonica Observatory</title><meta name="description" content="old"><link rel="canonical" href="https://old.example/"></head><body><!--SERVER_CONTENT--></body></html>'
ORIGIN = 'https://harmonica.observe.tw'


class RenderShellTests(unittest.TestCase):
    def catalog(self, name='Tokyo ensemble'):
        return {'sources': [{'id': 'watchlist-42', 'name': name, 'url': '/source/tokyo-42/',
                            'summary': 'Original public description & notes', 'countryCode': 'JP', 'country': 'Japan', 'region': 'Tokyo',
                            'links': [{'url': 'https://example.org/ensemble?a=1&b=2', 'label': 'Official website'}]}],
                'posts': [{'sourceId': 'watchlist-42', 'title': 'Concert & workshop', 'url': 'https://example.org/concert'}]}

    def test_localized_biography_and_metadata_keep_original_in_closed_details(self):
        catalog = self.catalog('原名')
        source = catalog['sources'][0]
        source.update(summary='原文 <script>literal</script>', summaryLanguage='zh-Hant',
                      names={'en': 'Localized <name>', 'ja': '日本語名', 'ko': '한국어 이름'},
                      summaries={'en': 'Biography <em>text</em>', 'zh-Hant': '原文 <script>literal</script>',
                                 'ja': '日本語の紹介', 'ko': '한국어 소개'})
        for locale in ('en', 'ja', 'ko'):
            with self.subTest(locale=locale):
                document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, locale)
                summary = html.escape(source['summaries'][locale], quote=True)
                self.assertIn('<h1>' + html.escape(source['names'][locale]) + '</h1>', document)
                self.assertIn('<meta name="description" content="' + summary + '">', document)
                self.assertIn('<meta property="og:description" content="' + summary + '">', document)
                self.assertIn('<p>' + summary + '</p>', document)
                self.assertIn('<details class="source-original-summary"><summary>', document)
                self.assertIn('<p lang="zh-Hant">原文 &lt;script&gt;literal&lt;/script&gt;</p>', document)
                self.assertNotIn('<script>', document)
                self.assertNotIn('<em>', document)
        original = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, 'zh-Hant')
        self.assertNotIn('<details', original)
        source['summaries'] = {}
        fallback = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, 'en')
        self.assertIn('<p>原文 &lt;script&gt;literal&lt;/script&gt;</p>', fallback)
        self.assertNotIn('<details', fallback)

    def test_score_guide_has_its_own_localized_title_and_score_links(self):
        for locale, (title, _) in render_shell.SCORE_GUIDE.items():
            catalog = self.catalog()
            catalog['scoreSources'] = [{'title': 'Original book title', 'name': 'Provider', 'sourceUrl': 'https://example.org/book'}]
            document = render_shell.render_document(TEMPLATE, '/scores/sources/', catalog, ORIGIN, locale)
            self.assertIn(html.escape(title), document)
            self.assertIn('Original book title', document)
            self.assertIn('https://example.org/book', document)

    def test_four_locales_have_localized_metadata_and_alternate_links(self):
        for locale in render_shell.LOCALES:
            document = render_shell.render_document(TEMPLATE, '/source/', self.catalog(), ORIGIN, locale)
            self.assertIn('<html lang="' + locale + '">', document)
            self.assertIn(html.escape(render_shell.WORDS[locale]['source']), document)
            self.assertEqual(document.count('hreflang='), 4)
            self.assertNotIn('https://old.example/', document)
            self.assertNotIn('content="old"', document)
            self.assertIn('rel="canonical" href="' + ORIGIN + '/source/?lang=' + locale + '"', document)

    def test_brand_is_localized_consistently_in_page_and_open_graph_titles(self):
        brands = {'en': 'Harmonica Observatory', 'zh-Hant': '口琴觀測站',
                  'ja': 'ハーモニカ観測所', 'ko': '하모니카 관측소'}
        for locale, brand in brands.items():
            with self.subTest(locale=locale):
                document = render_shell.render_document(TEMPLATE, '/', self.catalog(), ORIGIN, locale)
                title = render_shell.WORDS[locale]['home'] + ' · ' + brand
                self.assertIn('<title>' + title + '</title>', document)
                self.assertIn('<meta property="og:title" content="' + title + '">', document)
                self.assertIn('<meta property="og:site_name" content="' + brand + '">', document)
                for other in brands.values():
                    if other != brand:
                        self.assertNotIn(other, document)

    def test_known_source_retains_original_content_without_javascript(self):
        document = render_shell.render_document(TEMPLATE, '/source/tokyo-42/', self.catalog(), ORIGIN, 'ja')
        self.assertIn('<h1>Tokyo ensemble</h1>', document)
        self.assertIn('Official website', document)
        self.assertIn('Concert &amp; workshop', document)
        self.assertIn('<p>日本</p>', document)
        self.assertNotIn('Japan · Tokyo', document)
        self.assertNotIn('<!--SERVER_CONTENT-->', document)

    def test_source_country_and_generic_website_label_follow_locale(self):
        catalog = self.catalog()
        source = catalog['sources'][0]
        source.update(countryCode='KR', country='韓國', region='韓國')
        source['links'] = [{'url': 'https://example.org/site', 'label': '網站'},
                           {'url': 'https://example.org/social', 'label': 'Instagram'}]
        expected = {'en': ('South Korea', 'Website'), 'zh-Hant': ('韓國', '網站'),
                    'ja': ('韓国', 'ウェブサイト'), 'ko': ('대한민국', '웹사이트')}
        for locale, (country, website) in expected.items():
            with self.subTest(locale=locale):
                document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, locale)
                self.assertIn('<p>' + country + '</p>', document)
                self.assertIn('rel="noreferrer">' + website + '</a>', document)
                self.assertIn('rel="noreferrer">Instagram</a>', document)
                self.assertNotIn('韓國 · 韓國', document)
                if locale != 'zh-Hant':
                    self.assertNotIn('>網站<', document)
        # Region is deliberately not duplicated in the compact country facet;
        # proper names in the actual description and original links remain intact.
        source.update(countryCode='BR', country='巴西', region='Curitiba',
                      summary='Based in Curitiba <Centro>',
                      links=[{'url': 'https://example.org/local', 'label': 'Curitiba <Centro>'}])
        document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, 'en')
        self.assertIn('<p>Brazil</p>', document)
        self.assertIn('Based in Curitiba &lt;Centro&gt;', document)
        self.assertIn('rel="noreferrer">Curitiba &lt;Centro&gt;</a>', document)
        self.assertNotIn('<Centro>', document)

    def test_new_source_countries_render_localized_in_all_four_languages(self):
        catalog = self.catalog()
        source = catalog['sources'][0]
        countries = {'CA': ('加拿大', 'Canada', 'カナダ', '캐나다'),
                     'IN': ('印度', 'India', 'インド', '인도'),
                     'IT': ('義大利', 'Italy', 'イタリア', '이탈리아'),
                     'ZA': ('南非', 'South Africa', '南アフリカ', '남아프리카 공화국')}
        for code, names in countries.items():
            source.update(countryCode=code, country=names[0])
            for locale, name in zip(render_shell.LOCALES, names):
                with self.subTest(code=code, locale=locale):
                    document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, locale)
                    self.assertIn('<p>' + name + '</p>', document)

    def test_unknown_and_non_geographic_countries_are_not_assigned_taiwan(self):
        catalog = self.catalog()
        source = catalog['sources'][0]
        expected = {'WORLD': ('International', '國際', '国際', '국제'),
                    'ONLINE': ('Online', '線上', 'オンライン', '온라인'),
                    'UNKNOWN': ('Not specified', '尚未標示', '未指定', '미지정')}
        for code, names in expected.items():
            source.update(countryCode=code, country='原始地區', region='原始地區')
            for locale, name in zip(('en', 'zh-Hant', 'ja', 'ko'), names):
                with self.subTest(code=code, locale=locale):
                    document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, locale)
                    self.assertIn('<p>' + name + '</p>', document)
                    self.assertNotIn('<p>原始地區', document)
                    self.assertNotIn('<p>Taiwan</p>', document)
        source.pop('countryCode')
        self.assertEqual(render_shell.source_country(source, 'en'), 'Not specified')
        source.update(countryCode='ZZ', country='Unlisted <region>')
        document = render_shell.render_document(TEMPLATE, source['url'], catalog, ORIGIN, 'en')
        self.assertIn('<p>Unlisted &lt;region&gt;</p>', document)

    def test_directory_source_names_follow_locale_and_preserve_literal_names(self):
        catalog = self.catalog('原名 <literal>')
        source = catalog['sources'][0]
        source['names'] = {'en': 'Ensemble <One>', 'ja': '楽団 <一>', 'ko': '악단 <하나>'}
        for locale in render_shell.LOCALES:
            name = source['names'].get(locale, source['name'])
            document = render_shell.render_document(TEMPLATE, '/source/', catalog, ORIGIN, locale)
            self.assertIn('href="/source/tokyo-42/?lang=' + locale + '">' + html.escape(name) + '</a>', document)
            self.assertNotIn('<literal>', document)

    def test_only_synthetic_instagram_story_titles_are_localized(self):
        catalog = self.catalog()
        post = {'sourceId': 'watchlist-42', 'url': 'https://example.org/story',
                'platform': 'instagram', 'isStory': True, 'title': 'Instagram story @_player.one'}
        catalog['posts'] = [post]
        for locale, label in render_shell.STORY_LABEL.items():
            document = render_shell.render_document(TEMPLATE, '/source/tokyo-42/', catalog, ORIGIN, locale)
            self.assertIn('>' + label + ' @_player.one</a>', document)
        for title in ('Instagram story @player: Original concert note',
                      'Instagram story @<literal>', '演奏會原文'):
            post['title'] = title
            document = render_shell.render_document(TEMPLATE, '/source/tokyo-42/', catalog, ORIGIN, 'ja')
            self.assertIn('>' + html.escape(title) + '</a>', document)
        post.update(title='Instagram story @player', isStory=False)
        self.assertEqual(render_shell.post_title(post, 'ja'), post['title'])
        post.update(isStory=True, platform='website')
        self.assertEqual(render_shell.post_title(post, 'ja'), post['title'])

    def test_source_names_and_descriptions_are_escaped_as_text(self):
        catalog = self.catalog('Duo <North> & "South"')
        catalog['sources'][0]['summary'] = 'Description <em>literal markup</em>'
        document = render_shell.render_document(TEMPLATE, '/source/tokyo-42/', catalog, ORIGIN)
        self.assertIn('Duo &lt;North&gt; &amp; &quot;South&quot;', document)
        self.assertNotIn('<em>literal markup</em>', document)
        self.assertIn('&lt;em&gt;literal markup&lt;/em&gt;', document)

    def test_literal_backslash_in_source_name_does_not_become_regex_replacement(self):
        catalog = self.catalog(r'Ensemble \1')
        document = render_shell.render_document(TEMPLATE, '/source/tokyo-42/', catalog, ORIGIN)
        self.assertIn(r'<h1>Ensemble \1</h1>', document)
        self.assertIn(r'<title>Ensemble \1', document)

    def test_post_source_alias_resolves_the_same_canonical_source(self):
        document = render_shell.render_document(TEMPLATE, '/post/source/tokyo-42/', self.catalog(), ORIGIN, 'ko')
        self.assertIn('<h1>Tokyo ensemble</h1>', document)
        self.assertIn('rel="canonical" href="' + ORIGIN + '/source/tokyo-42/?lang=ko"', document)
        for locale in render_shell.LOCALES:
            self.assertIn('hreflang="' + locale + '" href="' + ORIGIN + '/source/tokyo-42/?lang=' + locale, document)

    def test_unrecognized_locale_falls_back_to_english(self):
        document = render_shell.render_document(TEMPLATE, '/', self.catalog(), ORIGIN, 'fr-CA')
        self.assertIn('<html lang="en">', document)
        self.assertIn('<h1>Home</h1>', document)


if __name__ == '__main__':
    unittest.main()
