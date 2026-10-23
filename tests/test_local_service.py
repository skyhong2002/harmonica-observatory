import gzip
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import community
import serve


class LocalServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / 'web/assets').mkdir(parents=True)
        (root / 'site/detail').mkdir(parents=True)
        (root / 'web/index.html').write_text('<html><head></head><body>multilingual shell</body></html>')
        (root / 'data/sources').mkdir(parents=True)
        (root / 'data/sources/source-url-aliases.csv').write_text(
            'source_path,target_path,status_code,target_source_id,match_basis,notes,last_verified_at\n'
            '/source/club-8-fcu-harmonica/,/source/189-fcu-harmonica/,301,189,sameAs,,\n'
            '/source/club-8/,/source/189-fcu-harmonica/,301,189,sameAs,,\n'
            '/source/watchlist-2%2Bwatchlist-75-thmf/,/source/2-thmf/,301,2,sameAs,,\n'
            '/source/watchlist-9-renamed/,/source/9-old-name/,301,9,sameAs,,\n')
        (root / 'data/sources/source-url-aliases-served.csv').write_text(
            'source_path,evidence,verified_at\n/source/club-8-fcu-harmonica/,,\n'
            '/source/watchlist-2+watchlist-75-thmf/,,\n/source/watchlist-9-renamed/,,\n')
        (root / 'web/assets/app.js').write_text('console.log("app")')
        (root / 'site/detail/index.html').write_text('<script>legacy()</script>')
        (root / 'secret.txt').write_text('must never be public')
        self.env = patch.dict(os.environ, {'HARMONICA_COMMUNITY_STATE': str(root / 'state')})
        self.env.start()
        self.server = serve.Server(('127.0.0.1', 0), root=root, public_origin='https://atlas.example', trust_proxy=True)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        sources = [{'id': 'real', 'countryCode': 'JP'},
                   {'id': 'watchlist-189', 'publicId': '189', 'url': '/source/189-fcu-harmonica/'},
                   {'id': 'watchlist-2', 'publicId': '2', 'url': '/source/2-thmf/'},
                   {'id': 'watchlist-9', 'publicId': '9', 'url': '/source/9-new-name/'}]
        self.catalog = patch.object(serve, 'catalog', return_value={'sources': sources, 'posts': [], 'events': [], 'padding': 'X' * 2000})
        self.catalog.start()
        self.schedule = patch.object(serve, 'crawl_snapshot', return_value={'available': False})
        self.schedule.start()
        serve._RATE.clear()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.schedule.stop()
        self.catalog.stop()
        self.env.stop()
        self.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        headers = dict(headers or {})
        if isinstance(body, dict):
            body = json.dumps(body)
            headers.setdefault('Content-Type', 'application/json')
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        raw = response.read()
        result = response.status, dict(response.getheaders()), raw
        conn.close()
        return result

    def session_headers(self):
        status, headers, raw = self.request('GET', '/api/v1/session')
        self.assertEqual(status, 200)
        data = json.loads(raw)
        return {'Cookie': headers['Set-Cookie'].split(';')[0], 'X-CSRF-Token': data['csrfToken'],
                'Origin': f'http://127.0.0.1:{self.server.server_port}'}

    def test_shell_static_and_genuine_missing_routes(self):
        for path in ('/', '/events', '/contribute/', '/source/real/', '/post/source/real/'):
            self.assertEqual(self.request('GET', path)[0], 200, path)
        for path in ('/missing/', '/source/nonexistent/', '/../../secret.txt', '/%2e%2e/secret.txt', '/state/community.sqlite3', '/.git/config'):
            self.assertEqual(self.request('GET', path)[0], 404, path)
        status, headers, raw = self.request('GET', '/web/assets/app.js')
        self.assertEqual(status, 200)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", headers['Content-Security-Policy'])
        status, headers, _ = self.request('GET', '/detail/')
        self.assertEqual(status, 200)
        self.assertIn("script-src 'self' 'unsafe-inline'", headers['Content-Security-Policy'])

    def test_catalog_gzip_and_pagination(self):
        status, headers, raw = self.request('GET', '/api/v1/catalog', headers={'Accept-Encoding': 'gzip'})
        self.assertEqual(headers['Content-Encoding'], 'gzip')
        self.assertEqual(json.loads(gzip.decompress(raw))['sources'][0]['id'], 'real')
        status, _, raw = self.request('GET', '/api/v1/sources?country=JP&limit=10')
        self.assertEqual(json.loads(raw)['total'], 1)
        self.assertEqual(self.request('GET', '/api/v1/sources?limit=oops')[0], 400)

    def test_legacy_navigation_preserves_language_and_filters(self):
        for old, new in (('/directory/', '/source/'), ('/score-sources', '/scores/sources/')):
            status, headers, raw = self.request('GET', old + '?lang=ja&country=JP')
            self.assertEqual(status, 308)
            self.assertEqual(headers['Location'], new + '?lang=ja&country=JP')
            self.assertEqual(raw, b'')

    def test_served_source_aliases_move_permanently_and_others_stay_missing(self):
        for old, new in (('/source/club-8-fcu-harmonica/', '/source/189-fcu-harmonica/'),
                         ('/source/club-8-fcu-harmonica', '/source/189-fcu-harmonica/'),
                         ('/source/watchlist-2%2Bwatchlist-75-thmf/', '/source/2-thmf/'),
                         ('/source/watchlist-2+watchlist-75-thmf/', '/source/2-thmf/')):
            status, headers, raw = self.request('GET', old)
            self.assertEqual((status, headers.get('Location')), (301, 'https://atlas.example' + new), old)
            self.assertEqual(raw, b'')
        status, headers, _ = self.request('HEAD', '/source/club-8-fcu-harmonica/?lang=ja')
        self.assertEqual((status, headers['Location']), (301, 'https://atlas.example/source/189-fcu-harmonica/?lang=ja'))
        # Registry rows not listed as served, and served rows whose target is
        # no longer that ID's page, are not guessed.
        for path in ('/source/club-8/', '/source/watchlist-9-renamed/', '/feeds/sources/84728e2c079cfc9a'):
            self.assertEqual(self.request('GET', path)[0], 404, path)

    def test_bare_url_is_english_regardless_of_accept_language(self):
        status, _, raw = self.request('GET', '/source/189-fcu-harmonica/', headers={'Accept-Language': 'zh-TW,zh;q=0.9'})
        self.assertEqual(status, 200)
        self.assertIn(b'<html lang="en">', raw)
        self.assertIn(b'<link rel="canonical" href="https://atlas.example/source/189-fcu-harmonica/">', raw)
        status, _, raw = self.request('GET', '/source/189-fcu-harmonica/?lang=zh-Hant')
        self.assertIn(b'<link rel="canonical" href="https://atlas.example/source/189-fcu-harmonica/?lang=zh-Hant">', raw)
        status, _, raw = self.request('GET', '/source/189-fcu-harmonica/?lang=en')
        self.assertIn(b'<link rel="canonical" href="https://atlas.example/source/189-fcu-harmonica/">', raw)

    def test_host_origin_and_csrf_checks(self):
        self.assertEqual(self.request('GET', '/', headers={'Host': 'attacker.example'})[0], 421)
        headers = self.session_headers()
        body = {'url': 'https://example.org'}
        self.assertEqual(self.request('POST', '/api/v1/submissions', body, {**headers, 'Origin': 'https://attacker.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/v1/submissions', body, {**headers, 'X-CSRF-Token': 'bad'})[0], 403)
        self.assertEqual(self.request('POST', '/api/v1/submissions', body, headers)[0], 201)
        self.assertEqual(self.request('POST', '/api/v1/submissions', 'x' * 13000, {**headers, 'Content-Type': 'application/json'})[0], 413)

    def test_https_proxy_and_cookie(self):
        status, _, raw = self.request('GET', '/api/v1/session', headers={'Host': 'atlas.example'})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)['code'], 'https_required')
        status, headers, _ = self.request('GET', '/api/v1/session', headers={'Host': 'atlas.example', 'X-Forwarded-Proto': 'https'})
        self.assertEqual(status, 200)
        for attribute in ('HttpOnly', 'SameSite=Strict', 'Secure'):
            self.assertIn(attribute, headers['Set-Cookie'])
        self.server.trust_proxy = False
        self.assertEqual(self.request('GET', '/api/v1/session', headers={'Host': 'atlas.example', 'X-Forwarded-Proto': 'https'})[0], 403)

    def test_registration_and_owner_only_revocation(self):
        first = self.session_headers()
        quota = {'limitUsd': 5, 'usedUsd': 0, 'remainingUsd': 5, 'checkedAt': 123, 'accountId': 'private'}
        token = 'apify_api_' + 'X' * 40
        with patch.object(community, 'verify_token', return_value=quota):
            status, _, raw = self.request('POST', '/api/v1/contributions', {'token': token, 'name': 'Test', 'budgetUsd': 0.5, 'consent': True}, first)
        self.assertEqual(status, 201)
        self.assertNotIn(token.encode(), raw)
        identifier = json.loads(raw)['contribution']['id']
        other = self.session_headers()
        self.assertEqual(self.request('DELETE', '/api/v1/contributions/' + identifier, headers=other)[0], 404)
        self.assertEqual(self.request('DELETE', '/api/v1/contributions/' + identifier, headers=first)[0], 200)
        self.assertEqual(community.public_status()['activeAccounts'], 0)


if __name__ == '__main__':
    unittest.main()
