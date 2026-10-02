"""Isolated, encrypted community Apify pool, adapted from Chumei's quota model.

This service has no access to Chumei identities, databases, or encryption keys.
A contribution authorizes a cumulative USD budget; reservations are atomic and
remain charged against it until the crawler records a final conservative cost.
"""
from __future__ import annotations

import hashlib
import fcntl
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import secrets
import sqlite3
import threading
import time
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
SESSION_AGE = 180 * 86400
_SCHEMA_LOCK = threading.Lock()


class CommunityError(ValueError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.status = code, status


def state_path() -> Path:
    return Path(os.environ.get('HARMONICA_COMMUNITY_STATE', ROOT / 'state/community')).expanduser().resolve()


def _secure_state() -> Path:
    path = state_path()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _fernet() -> Fernet:
    path = _secure_state() / 'encryption.key'
    lock_fd = os.open(path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(lock_fd, 'r+') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'wb') as stream:
                stream.write(Fernet.generate_key())
                stream.flush()
                os.fsync(stream.fileno())
        path.chmod(0o600)
        return Fernet(path.read_bytes().strip())


@contextmanager
def connect():
    path = _secure_state() / 'community.sqlite3'
    # Create with private permissions before SQLite opens it; WAL files inherit.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    path.chmod(0o600)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    with _SCHEMA_LOCK:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS sessions (
          hash TEXT PRIMARY KEY, owner TEXT NOT NULL, csrf TEXT NOT NULL, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS contributions (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
          ciphertext TEXT NOT NULL, name TEXT NOT NULL, status TEXT NOT NULL,
          budget REAL NOT NULL, spent REAL NOT NULL DEFAULT 0,
          quota TEXT NOT NULL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS reservations (
          run_id TEXT PRIMARY KEY, contribution_id TEXT NOT NULL REFERENCES contributions(id),
          amount REAL NOT NULL, cost REAL, created REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS submissions (
          id TEXT PRIMARY KEY, owner TEXT NOT NULL, url TEXT NOT NULL, note TEXT NOT NULL,
          country TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS submissions_owner ON submissions(owner,created);
        CREATE TABLE IF NOT EXISTS google_accounts (
          subject TEXT PRIMARY KEY, owner TEXT NOT NULL UNIQUE,
          email TEXT NOT NULL, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS oauth_flows (
          state_hash TEXT PRIMARY KEY, binding_hash TEXT NOT NULL,
          session_hash TEXT NOT NULL, nonce TEXT NOT NULL, verifier TEXT NOT NULL,
          redirect_uri TEXT NOT NULL, return_to TEXT NOT NULL, expires REAL NOT NULL);
        ''')
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session(cookie: str | None, *, create: bool = False) -> tuple[dict | None, str | None]:
    with connect() as conn:
        now = time.time()
        conn.execute('DELETE FROM sessions WHERE expires < ?', (now,))
        if cookie and re.fullmatch(r'[A-Za-z0-9_-]{40,100}', cookie):
            row = conn.execute('SELECT * FROM sessions WHERE hash=?', (_hash(cookie),)).fetchone()
            if row:
                return dict(row), None
        if not create:
            return None, None
        cookie = secrets.token_urlsafe(32)
        result = {'hash': _hash(cookie), 'owner': secrets.token_urlsafe(24),
                  'csrf': secrets.token_urlsafe(32), 'expires': now + SESSION_AGE}
        conn.execute('INSERT INTO sessions VALUES(:hash,:owner,:csrf,:expires)', result)
        return result, cookie


def normalize_token(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{20,512}', value.strip()):
        raise CommunityError('invalid_token', 'Enter a valid Apify API token.')
    return value.strip()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_token(token: str) -> dict:
    token = normalize_token(token)
    request = Request('https://api.apify.com/v2/users/me/limits',
                      headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
    try:
        with build_opener(_NoRedirect).open(request, timeout=15) as response:
            data = json.loads(response.read(1024 * 1024))['data']
        identity_request = Request('https://api.apify.com/v2/users/me', headers={'Authorization': 'Bearer ' + token, 'Accept': 'application/json'})
        with build_opener(_NoRedirect).open(identity_request, timeout=15) as response:
            identity = json.loads(response.read(1024 * 1024))['data'].get('id')
        if not isinstance(identity, str) or not identity:
            raise ValueError('identity')
        configured, current, cycle = data.get('limits', {}), data.get('current', {}), data.get('monthlyUsageCycle', {})
        start = datetime.fromisoformat(str(cycle.get('startAt')).replace('Z', '+00:00'))
        end = datetime.fromisoformat(str(cycle.get('endAt')).replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        if not start.tzinfo or not end.tzinfo or not start <= now < end:
            raise ValueError('cycle')
        limit, used = float(configured.get('maxMonthlyUsageUsd') or 0), float(current.get('monthlyUsageUsd') or 0)
        if not math.isfinite(limit) or not math.isfinite(used) or limit <= 0 or used < 0:
            raise ValueError('quota')
        return {'limitUsd': limit, 'usedUsd': used, 'remainingUsd': max(0, limit-used),
                'cycleStart': cycle.get('startAt'), 'cycleEnd': cycle.get('endAt'), 'checkedAt': time.time(),
                'accountId': _hash('apify-account:' + identity)}
    except HTTPError as exc:
        code = 'invalid_token' if exc.code in (401, 403) else 'provider_unavailable'
        raise CommunityError(code, 'Apify could not verify this account.', 422 if code == 'invalid_token' else 502) from None
    except (URLError, TimeoutError, ValueError, KeyError, TypeError):
        raise CommunityError('provider_unavailable', 'Apify quota verification is unavailable. Try again later.', 502) from None


def _quota_state(quota: dict) -> str:
    try:
        now = time.time()
        checked = float(quota.get('checkedAt') or 0)
        start = datetime.fromisoformat(str(quota.get('cycleStart')).replace('Z', '+00:00'))
        end = datetime.fromisoformat(str(quota.get('cycleEnd')).replace('Z', '+00:00'))
        if not start.tzinfo or not end.tzinfo:
            return 'unavailable'
        if checked < now - 3600 or checked > now + 60 or not start.timestamp() <= now < end.timestamp():
            return 'stale'
        return 'verified'
    except (ValueError, TypeError):
        return 'unavailable'


def _account(conn, row) -> dict:
    reserved = conn.execute('SELECT COALESCE(SUM(amount),0) FROM reservations WHERE contribution_id=? AND cost IS NULL', (row['id'],)).fetchone()[0]
    quota = {key: value for key, value in json.loads(row['quota']).items() if key != 'accountId'}
    return {'id': row['id'], 'name': row['name'], 'status': row['status'],
            'budgetUsd': row['budget'], 'spentUsd': row['spent'], 'reservedUsd': reserved,
            'budgetRemainingUsd': round(max(0, row['budget'] - row['spent'] - reserved), 6),
            **quota, 'quotaState': _quota_state(quota)}


def owner_contributions(owner: str) -> list[dict]:
    with connect() as conn:
        return [_account(conn, row) for row in conn.execute('SELECT * FROM contributions WHERE owner=? ORDER BY created DESC', (owner,))]


def register(owner: str, data: dict) -> dict:
    if data.get('consent') is not True:
        raise CommunityError('consent_required', 'Explicit consent is required.')
    token = normalize_token(data.get('token'))
    name = re.sub(r'\s+', ' ', str(data.get('name') or '')).strip()
    if not name or len(name) > 40 or any(ord(c) < 32 for c in name):
        raise CommunityError('invalid_name', 'Choose a public account label of 1 to 40 characters.')
    try:
        budget = float(data.get('budgetUsd'))
    except (TypeError, ValueError):
        budget = 0
    if isinstance(data.get('budgetUsd'), bool) or not math.isfinite(budget) or not 0.01 <= budget <= 100:
        raise CommunityError('invalid_budget', 'Choose a cumulative budget between USD 0.01 and USD 100.')
    quota = verify_token(token)
    if quota['remainingUsd'] < 0.01:
        raise CommunityError('quota_exhausted', 'This Apify account has no usable remaining quota.', 422)
    ciphertext = _fernet().encrypt(token.encode()).decode()
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        old = conn.execute('SELECT * FROM contributions WHERE token_hash=?', (_hash(token),)).fetchone()
        if old:
            raise CommunityError('already_registered', 'This token is already registered. Use a new token for a new contribution.', 409)
        if conn.execute("SELECT COUNT(*) FROM contributions WHERE owner=? AND status='active'", (owner,)).fetchone()[0] >= 5:
            raise CommunityError('account_limit', 'A browser may manage up to five active contributions.', 409)
        identifier = 'apy_' + secrets.token_hex(10)
        conn.execute('INSERT INTO contributions VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (identifier, owner, _hash(token), ciphertext, name, 'active', round(budget, 6), 0, json.dumps(quota), time.time()))
        return _account(conn, conn.execute('SELECT * FROM contributions WHERE id=?', (identifier,)).fetchone())


def revoke(owner: str, identifier: str) -> bool:
    with connect() as conn:
        result = conn.execute("UPDATE contributions SET status='revoked',ciphertext='' WHERE id=? AND owner=?", (identifier, owner))
        return bool(result.rowcount)


def public_status() -> dict:
    accounts, identities = [], {}
    if (state_path() / 'community.sqlite3').exists():
        with connect() as conn:
            for row in conn.execute("SELECT * FROM contributions WHERE status='active' ORDER BY created"):
                account = _account(conn, row)
                accounts.append(account)
                identities[account['id']] = json.loads(row['quota']).get('accountId') or row['id']
    usable = [a for a in accounts if a['quotaState'] == 'verified' and a['budgetRemainingUsd'] >= 0.001 and a.get('remainingUsd', 0) >= 0.001]
    grouped = {}
    for account in usable:
        group = grouped.setdefault(identities[account['id']], {'remaining': account['remainingUsd'], 'budget': 0})
        group['remaining'] = min(group['remaining'], account['remainingUsd'])
        group['budget'] += account['budgetRemainingUsd']
    return {'accounts': accounts, 'activeAccounts': len(grouped),
            'remainingUsd': round(sum(a['remaining'] for a in grouped.values()), 6),
            'budgetRemainingUsd': round(sum(min(a['budget'], a['remaining']) for a in grouped.values()), 6),
            'staleAccounts': sum(a['quotaState'] != 'verified' for a in accounts),
            'budgetPolicy': 'cumulative', 'management': 'browser',
            'revocationPolicy': 'Stops new reservations immediately; already reserved actor runs may finish.'}


def registered_token_hashes() -> set[str]:
    """Prevent any registered credential from falling back to owner authorization."""
    if not (state_path() / 'community.sqlite3').exists():
        return set()
    with connect() as conn:
        return {row[0] for row in conn.execute('SELECT token_hash FROM contributions')}


def active_tokens() -> list[dict]:
    if not (state_path() / 'community.sqlite3').exists():
        return []
    cipher = _fernet()
    with connect() as conn:
        result = []
        for row in conn.execute("SELECT * FROM contributions WHERE status='active'"):
            account = _account(conn, row)
            if account['budgetRemainingUsd'] <= 0:
                continue
            result.append({**account, 'token': cipher.decrypt(row['ciphertext'].encode()).decode(),
                           'verifiedQuota': json.loads(row['quota'])})
        return result


def reserve_budget(identifier: str, run_id: str, max_cost_usd: float) -> bool:
    amount = float(max_cost_usd)
    if not run_id or not math.isfinite(amount) or amount <= 0:
        return False
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT 1 FROM reservations WHERE run_id=?', (run_id,)).fetchone():
            return False
        row = conn.execute("SELECT * FROM contributions WHERE id=? AND status='active'", (identifier,)).fetchone()
        if not row:
            return False
        account = _account(conn, row)
        if amount > account['budgetRemainingUsd'] + 1e-9 or amount > account.get('remainingUsd', 0) + 1e-9:
            return False
        conn.execute('INSERT INTO reservations VALUES(?,?,?,NULL,?)', (run_id, identifier, amount, time.time()))
        return True


def settle_budget(run_id: str, actual_cost_usd: float) -> bool:
    cost = float(actual_cost_usd)
    if not math.isfinite(cost) or cost < 0:
        return False
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT * FROM reservations WHERE run_id=? AND cost IS NULL', (run_id,)).fetchone()
        if not row:
            return False
        conn.execute('UPDATE reservations SET cost=? WHERE run_id=?', (cost, run_id))
        conn.execute('UPDATE contributions SET spent=spent+? WHERE id=?', (cost, row['contribution_id']))
        return True


def mark_quota(identifier: str, quota: dict) -> None:
    allowed = {key: quota.get(key) for key in ('limitUsd', 'usedUsd', 'remainingUsd', 'cycleStart', 'cycleEnd', 'checkedAt', 'accountId')}
    for key in ('limitUsd', 'usedUsd', 'remainingUsd', 'checkedAt'):
        value = float(allowed.get(key) or 0)
        if not math.isfinite(value) or value < 0:
            raise ValueError('invalid quota')
        allowed[key] = value
    with connect() as conn:
        if not allowed.get('accountId'):
            old = conn.execute('SELECT quota FROM contributions WHERE id=?', (identifier,)).fetchone()
            if old:
                allowed['accountId'] = json.loads(old['quota']).get('accountId')
        conn.execute('UPDATE contributions SET quota=? WHERE id=?', (json.dumps(allowed), identifier))


def owner_submissions(owner: str) -> list[dict]:
    with connect() as conn:
        return [{'id': r['id'], 'url': r['url'], 'note': r['note'], 'countryCode': r['country'],
                 'status': r['status'], 'createdAt': r['created']} for r in
                conn.execute('SELECT * FROM submissions WHERE owner=? ORDER BY created DESC LIMIT 100', (owner,))]


def submit(owner: str, data: dict) -> dict:
    raw = str(data.get('url') or '').strip()
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ''
        if parts.scheme not in ('https', 'http') or not host or parts.username or parts.password or len(raw) > 2000:
            raise ValueError()
        if any(ord(c) <= 32 for c in raw) or host in ('localhost',) or '.' not in host:
            raise ValueError()
        url = urlunsplit((parts.scheme, parts.netloc, parts.path or '/', parts.query, ''))
    except ValueError:
        raise CommunityError('invalid_url', 'Enter a public http or https source URL.') from None
    note = str(data.get('note') or '').strip()
    country = str(data.get('countryCode') or '').strip().upper()
    if len(note) > 2000 or not re.fullmatch('[A-Z]{2}|', country):
        raise CommunityError('invalid_submission', 'Use a two-letter country code and a note under 2,000 characters.')
    now, identifier = time.time(), 'sub_' + secrets.token_hex(10)
    with connect() as conn:
        conn.execute('BEGIN IMMEDIATE')
        if conn.execute('SELECT COUNT(*) FROM submissions WHERE owner=? AND created>?', (owner, now - 86400)).fetchone()[0] >= 10:
            raise CommunityError('daily_limit', 'You can submit up to 10 links per day.', 429)
        existing = conn.execute("SELECT id FROM submissions WHERE owner=? AND url=? AND status='pending'", (owner, url)).fetchone()
        if existing:
            raise CommunityError('duplicate_submission', 'This link is already waiting for review.', 409)
        conn.execute('INSERT INTO submissions VALUES(?,?,?,?,?,?,?)', (identifier, owner, url, note, country, 'pending', now))
    return {'id': identifier, 'url': url, 'note': note, 'countryCode': country, 'status': 'pending', 'createdAt': now}
