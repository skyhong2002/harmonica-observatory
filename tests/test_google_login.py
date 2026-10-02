import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import community
import google_login
from test_local_service import LocalServiceTests


class GoogleLoginTests(unittest.TestCase):
    request = LocalServiceTests.request
    session_headers = LocalServiceTests.session_headers
    tearDown = LocalServiceTests.tearDown

    def setUp(self):
        LocalServiceTests.setUp(self)
        env = patch.dict(os.environ, {'HARMONICA_LOGIN_GOOGLE_CLIENT_ID': 'test.apps.googleusercontent.com',
                                     'HARMONICA_LOGIN_GOOGLE_CLIENT_SECRET': 'private-test-secret'})
        env.start()
        self.addCleanup(env.stop)

    def start(self, headers=None, return_to='/contribute/?lang=ja'):
        headers = headers or self.session_headers()
        status, response, raw = self.request('POST', '/auth/google/start', {'returnTo': return_to}, headers)
        self.assertEqual(status, 200, raw)
        self.assertNotIn(b'private-test-secret', raw)
        query = parse_qs(urlsplit(json.loads(raw)['url']).query)
        binding = response['Set-Cookie'].split(';')[0]
        with community.connect() as conn:
            flow = dict(conn.execute('SELECT * FROM oauth_flows WHERE state_hash=?', (community._hash(query['state'][0]),)).fetchone())
        return headers, query, binding, flow

    def finish(self, query, binding, subject='person-a', extra=None):
        params = {'state': query['state'][0], 'code': 'temporary-code', **(extra or {})}
        with patch.object(google_login, 'exchange', return_value={'sub': subject, 'email': subject+'@example.org', 'name': 'Name'}) as exchange:
            result = self.request('GET', '/auth/google/callback?' + urlencode(params), headers={'Cookie': binding})
        return result, exchange

    def owned_session(self, response):
        token = response[1]['Set-Cookie'].split(';')[0].split('=', 1)[1]
        value, _ = community.session(token)
        self.assertIsNotNone(value)
        return value, token

    def test_login_protocol_and_binding(self):
        original, query, binding, flow = self.start(return_to='https://evil.example/')
        self.assertEqual(query['scope'], ['openid email profile'])
        self.assertEqual(query['redirect_uri'], [f'http://127.0.0.1:{self.server.server_port}/auth/google/callback'])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(query['code_challenge'][0], base64.urlsafe_b64encode(hashlib.sha256(flow['verifier'].encode()).digest()).rstrip(b'=').decode())
        self.assertEqual(flow['return_to'], '/contribute/')
        # The Strict owner cookie is deliberately absent on Google's callback.
        bad, exchange = self.finish(query, 'harmonica_google_flow=wrong')
        self.assertIn('auth_error=failed', bad[1]['Location'])
        exchange.assert_not_called()
        good, _ = self.finish(query, binding)
        self.assertEqual(good[0], 303)
        self.assertEqual(good[1]['Location'], '/contribute/')
        owner, token = self.owned_session(good)
        self.assertIsNone(community.session(original['Cookie'].split('=', 1)[1])[0])
        self.assertEqual(google_login.account(owner['owner'])['email'], 'person-a@example.org')
        self.assertIn('SameSite=Strict', good[1]['Set-Cookie'])
        self.assertEqual(good[1]['Referrer-Policy'], 'no-referrer')
        replay, exchange = self.finish(query, binding)
        exchange.assert_not_called()
        self.assertIn('auth_error=failed', replay[1]['Location'])

    def test_return_target_keeps_public_report_context_without_open_redirect(self):
        self.assertEqual(google_login.safe_return('/?lang=zh-Hant'), '/?lang=zh-Hant')
        for value in ('//evil.example/', 'http://[', '/auth/logout', '/submit/\\evil', None):
            self.assertEqual(google_login.safe_return(value), '/contribute/')
        value = '/submit/?' + urlencode({'lang': 'zh-Hant', 'reportUrl': 'https://example.org/post', 'reportName': 'A & B', 'next': 'https://evil.example', 'auth_error': 'failed'})
        result = google_login.safe_return(value)
        self.assertEqual(urlsplit(result).path, '/submit/')
        self.assertEqual(parse_qs(urlsplit(result).query), {'lang': ['zh-Hant'], 'reportUrl': ['https://example.org/post'], 'reportName': ['A & B']})

    def test_anonymous_records_migrate_and_other_browser_restores_them(self):
        headers = self.session_headers()
        self.assertEqual(self.request('POST', '/api/v1/submissions', {'url': 'https://example.org/source'}, headers)[0], 201)
        token = 'apify_api_' + 'X' * 40
        quota = {'limitUsd': 5, 'usedUsd': 0, 'remainingUsd': 5, 'checkedAt': 123, 'accountId': 'private'}
        with patch.object(community, 'verify_token', return_value=quota):
            response = self.request('POST', '/api/v1/contributions', {'token': token, 'name': 'Mine', 'budgetUsd': 0.5, 'consent': True}, headers)
        contribution = json.loads(response[2])['contribution']['id']
        _, query, binding, _ = self.start(headers)
        result, _ = self.finish(query, binding)
        owner, first_token = self.owned_session(result)
        self.assertEqual(len(community.owner_submissions(owner['owner'])), 1)
        self.assertEqual(community.owner_contributions(owner['owner'])[0]['id'], contribution)
        _, query, binding, _ = self.start()
        result, _ = self.finish(query, binding)
        other, second_token = self.owned_session(result)
        self.assertEqual(owner['owner'], other['owner'])
        self.assertNotEqual(first_token, second_token)
        self.assertIsNotNone(community.session(first_token)[0])
        status, _, raw = self.request('GET', '/api/v1/session', headers={'Cookie': 'harmonica_owner='+second_token})
        data = json.loads(raw)
        self.assertEqual(data['identity'], 'google')
        self.assertTrue(data['googleLoginEnabled'])
        self.assertEqual(len(data['submissions']), 1)
        self.assertEqual(len(data['contributions']), 1)
        self.assertNotIn(token.encode(), raw)
        headers = {'Cookie': 'harmonica_owner='+second_token, 'Origin': f'http://127.0.0.1:{self.server.server_port}', 'X-CSRF-Token': data['csrfToken']}
        self.assertEqual(self.request('DELETE', '/api/v1/contributions/'+contribution, headers=headers)[0], 200)

    def test_existing_account_merges_anonymous_records_but_switching_never_merges_accounts(self):
        headers, query, binding, _ = self.start()
        result, _ = self.finish(query, binding)
        person_a, token_a = self.owned_session(result)
        community.submit(person_a['owner'], {'url': 'https://example.org/a'})
        headers = {**headers, 'Cookie': 'harmonica_owner='+token_a, 'X-CSRF-Token': person_a['csrf']}
        _, query, binding, _ = self.start(headers)
        result, _ = self.finish(query, binding, subject='person-b')
        person_b, _ = self.owned_session(result)
        self.assertEqual(len(community.owner_submissions(person_a['owner'])), 1)
        self.assertEqual(len(community.owner_submissions(person_b['owner'])), 0)
        anonymous, anon_token = community.session(None, create=True)
        community.submit(anonymous['owner'], {'url': 'https://example.org/new'})
        flow = {'session_hash': anonymous['hash']}
        google_login.sign_in(flow, {'sub': 'person-a', 'email': 'updated@example.org'})
        self.assertEqual(len(community.owner_submissions(person_a['owner'])), 2)
        self.assertIsNone(community.session(anon_token)[0])

    def test_logout_invalidates_session_and_pending_login(self):
        headers, query, binding, _ = self.start()
        self.assertEqual(self.request('POST', '/auth/logout', headers={**headers, 'X-CSRF-Token': 'wrong'})[0], 403)
        self.assertEqual(self.request('POST', '/auth/logout', headers=headers)[0], 200)
        self.assertIsNone(community.session(headers['Cookie'].split('=', 1)[1])[0])
        result, exchange = self.finish(query, binding)
        exchange.assert_not_called()
        self.assertIn('auth_error=failed', result[1]['Location'])

    def test_cancel_expiry_duplicate_state_and_provider_failure(self):
        headers, query, binding, flow = self.start()
        result, exchange = self.finish(query, binding, extra={'error': 'access_denied'})
        exchange.assert_not_called()
        self.assertEqual(result[1]['Location'], '/contribute/?lang=ja&auth_error=cancelled')
        self.assertIsNotNone(community.session(headers['Cookie'].split('=', 1)[1])[0])
        _, query, binding, flow = self.start(headers)
        with community.connect() as conn:
            conn.execute('UPDATE oauth_flows SET expires=0')
        result, exchange = self.finish(query, binding)
        exchange.assert_not_called()
        self.assertIn('auth_error=failed', result[1]['Location'])
        _, query, binding, flow = self.start(headers)
        path = '/auth/google/callback?' + urlencode({'state': query['state'][0], 'code': 'one-use-code'})
        with patch.object(google_login, 'exchange', side_effect=community.CommunityError('google_login_failed', 'private provider error', 502)):
            result = self.request('GET', path, headers={'Cookie': binding})
        self.assertNotIn('private', str(result))
        self.assertIn('auth_error=failed', result[1]['Location'])
        _, query, binding, _ = self.start(headers)
        result = self.request('GET', '/auth/google/callback?state='+query['state'][0]+'&state=duplicate&code=foo', headers={'Cookie': binding})
        self.assertIn('auth_error=failed', result[1]['Location'])

    def test_login_requires_csrf_and_trusted_https_and_config(self):
        headers = self.session_headers()
        for changed in ({'Origin': 'https://attacker.example'}, {'X-CSRF-Token': 'bad'}, {'Host': 'atlas.example'}):
            self.assertEqual(self.request('POST', '/auth/google/start', {}, {**headers, **changed})[0], 403)
        with patch.dict(os.environ, {'HARMONICA_LOGIN_GOOGLE_CLIENT_SECRET': ''}):
            self.assertEqual(self.request('POST', '/auth/google/start', {}, headers)[0], 503)
        self.assertEqual(self.request('HEAD', '/auth/google/callback')[0], 404)
        status, response, raw = self.request('GET', '/api/v1/session', headers={'Host': 'atlas.example', 'X-Forwarded-Proto': 'https'})
        secure_headers = {'Host': 'atlas.example', 'X-Forwarded-Proto': 'https', 'Origin': 'https://atlas.example', 'Cookie': response['Set-Cookie'].split(';')[0], 'X-CSRF-Token': json.loads(raw)['csrfToken']}
        status, response, raw = self.request('POST', '/auth/google/start', {}, secure_headers)
        for attr in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Max-Age=600'):
            self.assertIn(attr, response['Set-Cookie'])
        self.assertEqual(parse_qs(urlsplit(json.loads(raw)['url']).query)['redirect_uri'], ['https://atlas.example/auth/google/callback'])

    def test_signed_google_token_validation(self):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        from google.auth import crypt, jwt
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        public = key.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        signer = crypt.RSASigner.from_string(pem, key_id='test')
        flow = {'redirect_uri': 'https://atlas.example/auth/google/callback', 'nonce': 'expected', 'verifier': 'pkce'}
        claims = {'iss': 'https://accounts.google.com', 'sub': '123', 'aud': google_login.credentials()[0], 'iat': int(time.time())-10, 'exp': int(time.time())+300, 'nonce': 'expected', 'email': 'a@example.org', 'email_verified': True}
        transport = Mock(return_value=Mock(data=json.dumps({'test': public}).encode(), status=200))
        for changed, valid in [({}, True), ({'nonce': 'wrong'}, False), ({'aud': 'other-app'}, False), ({'iss': 'https://attacker.example'}, False), ({'exp': 1}, False), ({'email_verified': False}, False), ({'azp': 'other-app'}, False)]:
            with self.subTest(changed=changed):
                token = jwt.encode(signer, {**claims, **changed}).decode()
                response = Mock()
                response.__enter__ = Mock(return_value=Mock(read=Mock(return_value=json.dumps({'id_token': token}).encode())))
                response.__exit__ = Mock(return_value=False)
                with patch.object(google_login, 'build_opener') as opener, patch.object(google_login, '_CertificateRequest', return_value=transport):
                    opener.return_value.open.return_value = response
                    if valid:
                        self.assertEqual(google_login.exchange('code', flow)['sub'], '123')
                        request = opener.return_value.open.call_args.args[0]
                        self.assertEqual(parse_qs(request.data.decode())['code_verifier'], ['pkce'])
                    else:
                        with self.assertRaises(community.CommunityError):
                            google_login.exchange('code', flow)


if __name__ == '__main__':
    unittest.main()
