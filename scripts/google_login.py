"""Google OpenID Connect login; credentials and provider tokens stay server-side."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, build_opener

from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2 import id_token

import community

FLOW_AGE = 600
LOGIN_AGE = 30 * 86400
CALLBACK = '/auth/google/callback'


def credentials():
    return (os.environ.get('HARMONICA_LOGIN_GOOGLE_CLIENT_ID', '').strip(),
            os.environ.get('HARMONICA_LOGIN_GOOGLE_CLIENT_SECRET', '').strip())


def enabled():
    return all(credentials())


def account(owner):
    with community.connect() as conn:
        row = conn.execute('SELECT email,name FROM google_accounts WHERE owner=?', (owner,)).fetchone()
        return dict(row) if row else None


def safe_return(value):
    if not isinstance(value, str) or len(value) > 3000:
        return '/contribute/'
    try:
        url = urlsplit(value)
    except ValueError:
        return '/contribute/'
    if url.scheme or url.netloc or url.path not in ('/', '/contribute/', '/submit/'):
        return '/contribute/'
    # Rebuild the URL rather than accepting redirect targets from the browser.
    params = parse_qs(url.query)
    language = params.get('lang', ['en'])[0]
    result = {'lang': language if language in ('en', 'zh-Hant', 'ja', 'ko') else 'en'}
    if url.path == '/submit/':
        for key in ('reportUrl', 'reportName', 'reportCountry', 'source', 'url', 'name', 'countryCode'):
            if key in params:
                result[key] = params[key][0]
    return url.path + '?' + urlencode(result)


def begin(session, origin, return_to):
    if not enabled():
        raise community.CommunityError('login_unavailable', 'Google login is unavailable.', 503)
    state, binding, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    redirect = origin + CALLBACK
    with community.connect() as conn:
        conn.execute('DELETE FROM oauth_flows WHERE expires < ? OR session_hash=?', (time.time(), session['hash']))
        conn.execute('INSERT INTO oauth_flows VALUES (?,?,?,?,?,?,?,?)',
                     (community._hash(state), community._hash(binding), session['hash'], nonce,
                      verifier, redirect, safe_return(return_to), time.time() + FLOW_AGE))
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    url = 'https://accounts.google.com/o/oauth2/v2/auth?' + urlencode({
        'client_id': credentials()[0], 'redirect_uri': redirect, 'response_type': 'code',
        'scope': 'openid email profile', 'state': state, 'nonce': nonce,
        'code_challenge': challenge, 'code_challenge_method': 'S256', 'prompt': 'select_account',
    })
    return url, binding


def consume(state, binding, origin):
    if not state or not binding or len(state) > 200 or len(binding) > 200:
        raise community.CommunityError('invalid_oauth_state', 'Restart Google login.', 400)
    with community.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM oauth_flows WHERE state_hash=?', (community._hash(state),)).fetchone()
        if (not row or row['expires'] < time.time() or row['redirect_uri'] != origin + CALLBACK
                or not hmac.compare_digest(row['binding_hash'], community._hash(binding))):
            raise community.CommunityError('invalid_oauth_state', 'Restart Google login.', 400)
        conn.execute('DELETE FROM oauth_flows WHERE state_hash=?', (row['state_hash'],))
        return dict(row)


class _CertificateRequest(GoogleRequest):
    def __call__(self, *args, **kwargs):
        kwargs['timeout'] = 15
        return super().__call__(*args, **kwargs)


def exchange(code, flow):
    client_id, client_secret = credentials()
    body = urlencode({'code': code, 'client_id': client_id, 'client_secret': client_secret,
                      'redirect_uri': flow['redirect_uri'], 'grant_type': 'authorization_code',
                      'code_verifier': flow['verifier']}).encode()
    request = Request('https://oauth2.googleapis.com/token', data=body,
                      headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with build_opener(community._NoRedirect).open(request, timeout=15) as response:
            token = json.loads(response.read(128 * 1024))['id_token']
        # Verifies Google's signature, issuer, audience and token lifetime.
        transport = _CertificateRequest()
        try:
            claims = id_token.verify_oauth2_token(token, transport, client_id)
        finally:
            transport.session.close()
        if (not isinstance(claims.get('nonce'), str)
                or not hmac.compare_digest(claims['nonce'], flow['nonce'])
                or not isinstance(claims.get('sub'), str) or not 1 <= len(claims['sub']) <= 255
                or claims.get('email_verified') is not True
                or not isinstance(claims.get('email'), str) or not claims['email']
                or claims.get('azp', client_id) != client_id):
            raise ValueError('Invalid identity claims')
        return claims
    except Exception:
        # Provider responses may contain credentials; never log or return them.
        raise community.CommunityError('google_login_failed', 'Google login failed. Try again.', 502) from None


def sign_in(flow, claims):
    """Atomically migrate only anonymous ownership and rotate the session."""
    now = time.time()
    token = secrets.token_urlsafe(32)
    with community.connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        previous = conn.execute('SELECT * FROM sessions WHERE hash=? AND expires>?',
                                (flow['session_hash'], now)).fetchone()
        if not previous:
            raise community.CommunityError('invalid_session', 'Restart Google login.', 403)
        existing = conn.execute('SELECT owner FROM google_accounts WHERE subject=?', (claims['sub'],)).fetchone()
        owner = existing['owner'] if existing else secrets.token_urlsafe(24)
        conn.execute('INSERT INTO google_accounts VALUES (?,?,?,?) ON CONFLICT(subject) DO UPDATE SET email=excluded.email,name=excluded.name',
                     (claims['sub'], owner, claims['email'][:320], str(claims.get('name', ''))[:200]))
        was_account = conn.execute('SELECT 1 FROM google_accounts WHERE owner=?', (previous['owner'],)).fetchone()
        if not was_account:
            for table in ('contributions', 'submissions'):
                conn.execute(f'UPDATE {table} SET owner=? WHERE owner=?', (owner, previous['owner']))
            conn.execute('DELETE FROM sessions WHERE owner=?', (previous['owner'],))
        else:
            # Switching Google accounts never transfers another account's data.
            conn.execute('DELETE FROM sessions WHERE hash=?', (previous['hash'],))
        conn.execute('INSERT INTO sessions VALUES (?,?,?,?)',
                     (community._hash(token), owner, secrets.token_urlsafe(32), now + LOGIN_AGE))
    return token


def logout(session):
    with community.connect() as conn:
        conn.execute('DELETE FROM sessions WHERE hash=?', (session['hash'],))
        conn.execute('DELETE FROM oauth_flows WHERE session_hash=?', (session['hash'],))
