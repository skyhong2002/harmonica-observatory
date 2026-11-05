#!/usr/bin/env python3
"""Read-only preview server for design review screenshots.

Serves one checkout's `web/` shell with a frozen copy of the public catalog,
so the baseline and the candidate can be photographed against identical data.
Images under /assets/ are fetched once from the public site and cached. No
collection, scheduling, community writes or production service is touched.

  python3 docs/design-review/tools/snapshot_server.py --repo . --port 8401 \
      --catalog /tmp/hc-review/data/catalog.json \
      --community /tmp/hc-review/data/community.json
"""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import mimetypes
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

PUBLIC = 'https://harmonica.observe.tw'
SESSION = {'csrfToken': 'preview', 'identity': 'browser', 'account': None,
           'googleLoginEnabled': True, 'contributions': [], 'submissions': []}


def load_render_shell(repo: Path):
    spec = importlib.util.spec_from_file_location('preview_render_shell', repo / 'scripts/render_shell.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--catalog', required=True, type=Path)
    parser.add_argument('--community', required=True, type=Path)
    parser.add_argument('--cache', default=Path('/tmp/hc-review/asset-cache'), type=Path)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', default=8401, type=int)
    args = parser.parse_args()
    repo = args.repo.resolve()
    shell = load_render_shell(repo)
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    catalog_body = json.dumps(catalog, ensure_ascii=False, separators=(',', ':')).encode()
    community_body = args.community.read_bytes()
    cache_lock = threading.Lock()
    serve_py = repo / 'scripts/serve.py'
    html_404 = serve_py.is_file() and '_missing_page' in serve_py.read_text(encoding='utf-8')
    args.cache.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *a):
            pass

        def send(self, status, ctype, body, cache='no-store'):
            if len(body) > 2048 and 'gzip' in self.headers.get('Accept-Encoding', '') and (ctype.startswith('text/') or 'json' in ctype or 'javascript' in ctype):
                body = gzip.compress(body, 4)
                self.send_response(status)
                self.send_header('Content-Encoding', 'gzip')
            else:
                self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', cache)
            self.end_headers()
            if self.command != 'HEAD':
                self.wfile.write(body)

        def json(self, value, status=200):
            self.send(status, 'application/json; charset=utf-8', json.dumps(value, ensure_ascii=False).encode())

        def file(self, path: Path):
            ctype = mimetypes.guess_type(str(path))[0] or 'application/octet-stream'
            if ctype.startswith('text/') or ctype in ('application/javascript', 'application/json', 'image/svg+xml'):
                ctype += '; charset=utf-8'
            self.send(200, ctype, path.read_bytes(), cache='no-cache')

        def remote(self, path: str):
            target = (args.cache / path.lstrip('/')).resolve()
            if not target.is_relative_to(args.cache.resolve()):
                return self.json({'error': 'Not found.'}, 404)
            with cache_lock:
                missing = target.with_name(target.name + '.404')
                if missing.exists():
                    return self.json({'error': 'Not found.'}, 404)
                if not target.is_file():
                    try:
                        with urllib.request.urlopen(PUBLIC + path, timeout=20) as response:
                            data = response.read()
                    except Exception:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        missing.write_text('')
                        return self.json({'error': 'Not found.'}, 404)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
            return self.file(target)

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            self.json({'error': 'Preview is read-only.', 'code': 'preview_read_only'}, 403)

        do_DELETE = do_POST

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path.startswith('/api/v1/'):
                if path == '/api/v1/catalog':
                    return self.send(200, 'application/json; charset=utf-8', catalog_body)
                if path == '/api/v1/community':
                    return self.send(200, 'application/json; charset=utf-8', community_body)
                if path == '/api/v1/session':
                    return self.json(SESSION)
                if path == '/api/v1/health':
                    return self.json({'ok': True, 'service': 'harmonica-preview'})
                key = path.rsplit('/', 1)[-1]
                if key in ('sources', 'posts', 'events', 'scores'):
                    rows = catalog.get(key, [])
                    q = parse_qs(urlsplit(self.path).query)
                    return self.json({'items': rows[:50], 'total': len(rows), 'limit': 50, 'offset': 0, 'q': q.get('q', [''])[0]})
                return self.json({'error': 'Not found.', 'code': 'not_found'}, 404)
            for prefix in ('/web/assets/', '/web-assets/'):
                if path.startswith(prefix):
                    target = (repo / 'web/assets' / path[len(prefix):]).resolve()
                    if target.is_relative_to(repo / 'web/assets') and target.is_file():
                        return self.file(target)
                    return self.json({'error': 'Not found.'}, 404)
            last = path.rstrip('/').rsplit('/', 1)[-1]
            if '.' in last or path.startswith('/assets/'):
                local = (repo / 'site' / path.lstrip('/')).resolve()
                if local.is_relative_to(repo / 'site') and local.is_file():
                    return self.file(local)
                return self.remote(path)
            page = path if path.endswith('/') else path + '/'
            routes = {'/', '/events/', '/post/', '/source/', '/scores/', '/scores/sources/', '/feeds/',
                      '/status/', '/contribute/', '/submit/', '/about/', '/privacy/'}
            slug = page.rstrip('/').rsplit('/', 1)[-1]
            known = page in routes or (page.startswith(('/source/', '/post/source/')) and any(
                str(s.get('id')) == slug or s.get('url') == page or str(s.get('url') or '').rstrip('/').rsplit('/', 1)[-1] == slug
                for s in catalog.get('sources', [])))
            if not known and not html_404:
                # Mirrors the checkout's scripts/serve.py: older versions answer a JSON 404.
                return self.json({'error': 'Not found.', 'code': 'not_found'}, 404)
            locale = shell.normalize_locale(parse_qs(urlsplit(self.path).query).get('lang', [shell.DEFAULT_LOCALE])[0])
            template = (repo / 'web/index.html').read_text(encoding='utf-8')
            origin = 'http://' + (self.headers.get('Host') or f'{args.host}:{args.port}')
            if known:
                body = shell.render_document(template, page, catalog, origin, locale).encode()
                return self.send(200, 'text/html; charset=utf-8', body)
            body = shell.render_document(template, page, catalog, origin, locale, not_found=True).encode()
            return self.send(404, 'text/html; charset=utf-8', body)

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f'preview {repo} on http://{args.host}:{args.port}/', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
