#!/usr/bin/env python3
"""Serve the multilingual application, legacy public data and local community API.

Run: .venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8330
Set HARMONICA_PUBLIC_ORIGIN=https://your.domain and HARMONICA_TRUST_PROXY=1
when a loopback reverse proxy terminates HTTPS. No other forwarded headers are
trusted. The repository, state directory and credentials are never served.
"""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
import gzip
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import mimetypes
import os
from pathlib import Path
import re
import threading
import time
from urllib.parse import unquote, urlsplit, parse_qs

import community
import google_login

ROOT = Path(__file__).resolve().parents[1]
SHELL_ROUTES = {'/', '/events/', '/post/', '/source/', '/scores/', '/scores/sources/',
                '/feeds/', '/status/', '/contribute/', '/submit/', '/about/', '/privacy/'}
COOKIE_NAME = 'harmonica_owner'
FLOW_COOKIE = 'harmonica_google_flow'
MAX_BODY = 12 * 1024
_CATALOG_LOCK = threading.Lock()
_CATALOG_CACHE = {}
_RATE_LOCK = threading.Lock()
_RATE = defaultdict(deque)


def catalog():
    from global_catalog import build_catalog, snapshot_version
    version = snapshot_version()
    with _CATALOG_LOCK:
        if _CATALOG_CACHE.get('version') != version:
            _CATALOG_CACHE.update(version=version, value=build_catalog())
        return _CATALOG_CACHE['value']


def crawl_snapshot(*, now=None):
    try:
        from apify_pool import crawl_schedule_snapshot
        return crawl_schedule_snapshot(now=now)
    except (ImportError, OSError, ValueError, RuntimeError):
        return {'available': False, 'estimate': True, 'platforms': {}}


def _loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value == 'localhost'


def _rate(key: str, limit: int, period: int) -> bool:
    now = time.monotonic()
    with _RATE_LOCK:
        # Bounded memory even when many distinct clients visit.
        if len(_RATE) > 10000:
            for stale in list(_RATE):
                if not _RATE[stale] or _RATE[stale][-1] < now - 3600:
                    del _RATE[stale]
            if len(_RATE) > 10000:
                return False
        queue = _RATE[key]
        while queue and queue[0] < now - period:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler=None, *, root=ROOT, public_origin=None, trust_proxy=None):
        self.root = Path(root).resolve()
        self.public_origin = (public_origin if public_origin is not None else os.environ.get('HARMONICA_PUBLIC_ORIGIN', '')).rstrip('/')
        self.trust_proxy = trust_proxy if trust_proxy is not None else os.environ.get('HARMONICA_TRUST_PROXY') == '1'
        if self.public_origin:
            parsed = urlsplit(self.public_origin)
            if parsed.scheme != 'https' or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
                raise ValueError('HARMONICA_PUBLIC_ORIGIN must be an https origin without a path')
        super().__init__(address, handler or Handler)

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(20)
        return connection, address


class Handler(BaseHTTPRequestHandler):
    server_version = 'Harmonica/1'
    sys_version = ''

    def log_message(self, fmt, *args):
        # Deliberately omit paths, bodies, headers and exception messages.
        pass

    def _headers(self, status, content_type, length, *, cookie=None, encoding=None, cache='no-store', legacy=False):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', cache)
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'strict-origin-when-cross-origin')
        self.send_header('X-Frame-Options', 'SAMEORIGIN')
        script_policy = "'self' 'unsafe-inline'" if legacy else "'self'"
        self.send_header('Content-Security-Policy', f"default-src 'self'; script-src {script_policy}; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; media-src 'self' https:; frame-src https:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'")
        if encoding:
            self.send_header('Content-Encoding', encoding)
            self.send_header('Vary', 'Accept-Encoding')
        if cookie:
            for value in ([cookie] if isinstance(cookie, str) else cookie):
                self.send_header('Set-Cookie', value)
        self.end_headers()

    def _json(self, value, status=200, *, cookie=None):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode()
        encoding = None
        if len(body) > 1024 and 'gzip' in self.headers.get('Accept-Encoding', ''):
            body, encoding = gzip.compress(body, compresslevel=4), 'gzip'
        self._headers(status, 'application/json; charset=utf-8', len(body), cookie=cookie, encoding=encoding)
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _error(self, code, message, status):
        self._json({'error': message, 'code': code}, status)

    def _origin(self):
        raw = self.headers.get('Host', '')
        if not raw or any(c in raw for c in '/\\@,\r\n\t '):
            raise community.CommunityError('invalid_host', 'Unrecognized host.', 421)
        try:
            parsed = urlsplit('http://' + raw)
            hostname, port = parsed.hostname, parsed.port
        except ValueError:
            raise community.CommunityError('invalid_host', 'Unrecognized host.', 421) from None
        public = self.server.public_origin
        if public and raw.lower() == urlsplit(public).netloc.lower():
            if not (self.server.trust_proxy and _loopback(self.client_address[0]) and self.headers.get('X-Forwarded-Proto') == 'https'):
                return public, False
            return public, True
        if hostname in ('localhost', '127.0.0.1', '::1') and port == self.server.server_port and _loopback(self.client_address[0]):
            return 'http://' + raw, True
        raise community.CommunityError('invalid_host', 'Unrecognized host.', 421)

    def _session(self, *, create=False):
        return community.session(self._cookie(COOKIE_NAME), create=create)

    def _cookie(self, name):
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            return cookie[name].value if name in cookie else None
        except Exception:
            return None

    def _set_cookie(self, name, token, age, origin):
        same_site = 'Lax' if name == FLOW_COOKIE else 'Strict'
        return (f'{name}={token}; Path=/; HttpOnly; SameSite={same_site}; Max-Age={age}'
                + ('; Secure' if origin.startswith('https:') else ''))

    def _redirect(self, location, cookies):
        self.send_response(303)
        self.send_header('Location', location)
        self.send_header('Content-Length', '0')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy', 'no-referrer')
        for cookie in cookies:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()

    def _body(self):
        if self.headers.get('Transfer-Encoding'):
            raise community.CommunityError('invalid_body', 'Transfer encoding is not supported.', 400)
        if self.headers.get_content_type() != 'application/json':
            raise community.CommunityError('invalid_content_type', 'Send application/json.', 415)
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            size = -1
        if not 0 < size <= MAX_BODY:
            raise community.CommunityError('invalid_body', 'Request body is missing or too large.', 413)
        try:
            raw = self.rfile.read(size)
            value = json.loads(raw)
            if len(raw) != size or not isinstance(value, dict):
                raise ValueError()
            return value
        except (ValueError, UnicodeError, TimeoutError):
            raise community.CommunityError('invalid_body', 'Send a valid JSON object.', 400) from None

    def _mutating_session(self, origin, secure):
        if not secure:
            raise community.CommunityError('https_required', 'Community accounts require HTTPS or localhost.', 403)
        if self.headers.get('Origin') != origin:
            raise community.CommunityError('invalid_origin', 'Reload this page before submitting.', 403)
        value, _ = self._session()
        if not value or not hmac.compare_digest(self.headers.get('X-CSRF-Token', ''), value['csrf']):
            raise community.CommunityError('invalid_session', 'Reload this page to create a session.', 403)
        return value

    def _static(self, path):
        if path in SHELL_ROUTES:
            return self._shell(path)
        if path.startswith('/source/') or path.startswith('/post/source/'):
            sources = catalog().get('sources', [])
            route_id = path.rstrip('/').rsplit('/', 1)[-1]
            known = any(str(s.get('id')) == route_id or s.get('url') == path or s.get('path') == path or s.get('detailUrl') == path or (path.startswith('/post/source/') and str(s.get('url', '')).rstrip('/').rsplit('/', 1)[-1] == route_id) for s in sources)
            if known:
                return self._shell(path)
        for prefix in ('/web/assets/', '/web-assets/'):
            if path.startswith(prefix):
                return self._safe_file(self.server.root / 'web/assets', path[len(prefix):])
        # Only the generated public site is exposed. Never fall back to repo root.
        return self._safe_file(self.server.root / 'site', path.lstrip('/'))

    def _shell(self, path):
        from render_shell import normalize_locale, render_document
        template_path = self.server.root / 'web/index.html'
        if not template_path.is_file():
            return self._error('not_found', 'Application assets are missing.', 404)
        params = parse_qs(urlsplit(self.path).query)
        language = params.get('lang', [self.headers.get('Accept-Language', 'en').split(',')[0].split(';')[0]])[0]
        locale = normalize_locale(language)
        origin = self.server.public_origin or self._origin()[0]
        document = render_document(template_path.read_text(encoding='utf-8'), path, catalog(), origin, locale)
        body = document.encode('utf-8')
        self._headers(200, 'text/html; charset=utf-8', len(body), cache='no-store')
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _safe_file(self, root, relative):
        if any(piece.startswith('.') for piece in relative.split('/')) or '\\' in relative or '\x00' in relative:
            return self._error('not_found', 'Not found.', 404)
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            return self._error('not_found', 'Not found.', 404)
        if target.is_dir():
            target = (target / 'index.html').resolve()
        if not target.is_relative_to(root.resolve()):
            return self._error('not_found', 'Not found.', 404)
        return self._file(target)

    def _file(self, path, *, cache='public, max-age=60'):
        if not path.is_file():
            return self._error('not_found', 'Not found.', 404)
        content_type = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
        if content_type.startswith('text/') or content_type in ('application/javascript', 'application/json'):
            content_type += '; charset=utf-8'
        size = path.stat().st_size
        self._headers(200, content_type, size, cache=cache, legacy=path.is_relative_to(self.server.root / 'site'))
        if self.command != 'HEAD':
            with path.open('rb') as stream:
                while chunk := stream.read(64 * 1024):
                    self.wfile.write(chunk)

    def _dispatch(self):
        origin, secure = self._origin()
        path = unquote(urlsplit(self.path).path)
        if path.startswith('//') or '\x00' in path:
            return self._error('not_found', 'Not found.', 404)
        if path in {item.rstrip('/') for item in SHELL_ROUTES if item != '/'}:
            path += '/'
        if path == google_login.CALLBACK and self.command == 'GET':
            if not secure:
                raise community.CommunityError('https_required', 'Login requires HTTPS.', 403)
            params = parse_qs(urlsplit(self.path).query)
            clear = self._set_cookie(FLOW_COOKIE, '', 0, origin)
            try:
                if any(len(values) != 1 for values in params.values()):
                    raise community.CommunityError('invalid_oauth_state', 'Restart Google login.', 400)
                flow = google_login.consume(params.get('state', [''])[0], self._cookie(FLOW_COOKIE), origin)
            except community.CommunityError:
                return self._redirect('/contribute/?auth_error=failed', [clear])
            if 'error' in params:
                return self._redirect(flow['return_to'] + ('&' if '?' in flow['return_to'] else '?') + 'auth_error=cancelled', [clear])
            code = params.get('code', [''])[0]
            try:
                if not code or len(code) > 8192:
                    raise community.CommunityError('google_login_failed', 'Missing code.', 400)
                claims = google_login.exchange(code, flow)
                token = google_login.sign_in(flow, claims)
            except community.CommunityError:
                return self._redirect(flow['return_to'] + ('&' if '?' in flow['return_to'] else '?') + 'auth_error=failed', [clear])
            return self._redirect(flow['return_to'], [clear, self._set_cookie(COOKIE_NAME, token, google_login.LOGIN_AGE, origin)])
        if self.command == 'POST' and path in ('/auth/google/start', '/auth/logout'):
            value = self._mutating_session(origin, secure)
            if path == '/auth/logout':
                google_login.logout(value)
                return self._json({'ok': True}, cookie=[self._set_cookie(COOKIE_NAME, '', 0, origin), self._set_cookie(FLOW_COOKIE, '', 0, origin)])
            if not _rate('login:' + value['hash'], 10, 300) or not _rate('login-ip:' + self.client_address[0], 120, 300):
                raise community.CommunityError('rate_limited', 'Try again shortly.', 429)
            url, binding = google_login.begin(value, origin, self._body().get('returnTo'))
            return self._json({'url': url}, cookie=self._set_cookie(FLOW_COOKIE, binding, google_login.FLOW_AGE, origin))
        if self.command in ('GET', 'HEAD'):
            aliases = {'/directory': '/source/', '/score-sources': '/scores/sources/'}
            if path.rstrip('/') in aliases:
                destination = aliases[path.rstrip('/')]
                query = urlsplit(self.path).query
                self.send_response(308)
                self.send_header('Location', destination + ('?' + query if query else ''))
                self.send_header('Content-Length', '0')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                return
            if path == '/api/v1/health':
                return self._json({'ok': True, 'service': 'harmonica', 'version': 1})
            if path == '/api/v1/catalog':
                return self._json(catalog())
            if path in ('/api/v1/sources', '/api/v1/posts', '/api/v1/events', '/api/v1/scores'):
                params = parse_qs(urlsplit(self.path).query)
                key = path.rsplit('/', 1)[1]
                rows = catalog().get(key, [])
                query = params.get('q', [''])[0].strip().casefold()[:200]
                country = params.get('country', [''])[0].upper()
                if country:
                    rows = [r for r in rows if r.get('countryCode') == country]
                if query:
                    rows = [r for r in rows if query in json.dumps(r, ensure_ascii=False).casefold()]
                try:
                    limit = min(200, max(1, int(params.get('limit', ['50'])[0])))
                    offset = max(0, int(params.get('offset', ['0'])[0]))
                except ValueError:
                    raise community.CommunityError('invalid_query', 'Use integer limit and offset.', 400) from None
                return self._json({'items': rows[offset:offset+limit], 'total': len(rows), 'limit': limit, 'offset': offset})
            if path == '/api/v1/community':
                return self._json({**community.public_status(), 'crawlSchedule': crawl_snapshot()})
            if path == '/api/v1/session' and self.command == 'GET':
                if not secure:
                    raise community.CommunityError('https_required', 'Community accounts require HTTPS or localhost.', 403)
                if self.headers.get('Sec-Fetch-Site') == 'cross-site' or self.headers.get('Origin', origin) != origin:
                    raise community.CommunityError('invalid_origin', 'Open this website directly.', 403)
                if not _rate('session:' + self.client_address[0], 120, 60):
                    raise community.CommunityError('rate_limited', 'Too many requests. Try again shortly.', 429)
                value, new = self._session(create=True)
                cookie = None
                if new:
                    cookie = f'{COOKIE_NAME}={new}; Path=/; HttpOnly; SameSite=Strict; Max-Age={community.SESSION_AGE}'
                    if origin.startswith('https:'):
                        cookie += '; Secure'
                account = google_login.account(value['owner'])
                return self._json({'csrfToken': value['csrf'], 'identity': 'google' if account else 'browser',
                                   'account': account, 'googleLoginEnabled': google_login.enabled(),
                                   'contributions': community.owner_contributions(value['owner']),
                                   'submissions': community.owner_submissions(value['owner'])}, cookie=cookie)
            if path.startswith('/api/v1/'):
                return self._error('not_found', 'Not found.', 404)
            return self._static(path)
        if self.command == 'POST' and path in ('/api/v1/contributions', '/api/v1/submissions'):
            value = self._mutating_session(origin, secure)
            if not _rate('write:' + value['owner'], 15, 300) or not _rate('write-ip:' + self.client_address[0], 60, 300):
                raise community.CommunityError('rate_limited', 'Too many requests. Try again shortly.', 429)
            data = self._body()
            if path.endswith('contributions'):
                impact_now = time.time()
                before = crawl_snapshot(now=impact_now)
                result = community.register(value['owner'], data)
                return self._json({'contribution': result, 'crawlImpact': {'before': before, 'after': crawl_snapshot(now=impact_now)}}, 201)
            return self._json({'submission': community.submit(value['owner'], data)}, 201)
        if self.command == 'DELETE' and re.fullmatch(r'/api/v1/contributions/apy_[a-f0-9]{20}', path):
            value = self._mutating_session(origin, secure)
            impact_now = time.time()
            before = crawl_snapshot(now=impact_now)
            if not community.revoke(value['owner'], path.rsplit('/', 1)[1]):
                return self._error('not_found', 'Contribution not found.', 404)
            return self._json({'ok': True, 'crawlImpact': {'before': before, 'after': crawl_snapshot(now=impact_now)}})
        if path.startswith('/api/v1/'):
            return self._error('method_not_allowed', 'Method not allowed.', 405)
        return self._error('not_found', 'Not found.', 404)

    def _handle(self):
        try:
            self._dispatch()
        except community.CommunityError as exc:
            self._error(exc.code, str(exc), exc.status)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception as exc:
            print('Harmonica request failed: ' + type(exc).__name__, flush=True)
            self._error('internal_error', 'The service could not complete this request.', 500)

    do_GET = do_HEAD = do_POST = do_DELETE = do_PUT = do_PATCH = do_OPTIONS = _handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8330)
    args = parser.parse_args()
    from run_pipeline import load_dotenv
    load_dotenv(ROOT / '.env')
    # Initialize storage before accepting traffic; permission failures fail startup.
    with community.connect():
        pass
    community._fernet()
    server = Server((args.host, args.port))
    print(f'Harmonica listening on http://{args.host}:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
