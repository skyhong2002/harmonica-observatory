#!/usr/bin/env python3
"""Isolated Apify capacity pool, shared reservations and conservative pacing.

Only internal credential functions return secrets. Public views are explicit
allowlists. The ledger reserves the full actor charge cap before a paid request;
unknown outcomes never release money or trigger a retry on another account.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(os.environ.get("HARMONICA_OBSERVE_HOME", Path(__file__).resolve().parents[1])).expanduser()
STATE_PATH = ROOT / "state/apify_pool.json"
QUOTA_TTL = 3600
MIN_RESERVE_USD = 0.02
# Each platform is guaranteed an equal third of the evenly paced daily amount.
# An unspent share expires gradually over the UTC day, so the others may use
# what a platform no longer needs, but never what it could still claim.
PLATFORM_SHARES = {"facebook": 1 / 3, "instagram": 1 / 3, "instagram_stories": 1 / 3}
COST_PER_SOURCE = {"facebook": 0.025, "instagram": 0.006, "instagram_stories": 0.005}
BATCH_SIZES = {"facebook": 24, "instagram": 5, "instagram_stories": 10}
MIN_RUN_BUDGET = {"facebook": 0.031, "instagram": 0.006, "instagram_stories": 0.0095}
_KEYCHAIN_CACHE = {"loaded": False, "token": "", "checkedAt": 0.0}


def _number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) and result >= 0 else default
    except (TypeError, ValueError):
        return default


def _timestamp(value):
    if isinstance(value, (int, float)):
        return _number(value)
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _read():
    try:
        value = json.loads(STATE_PATH.read_text())
        if not isinstance(value, dict):
            raise ValueError("invalid pool state")
        return value
    except FileNotFoundError:
        return {"version": 1, "accounts": {}, "runs": []}
    except (ValueError, OSError):
        # Never replace a damaged financial ledger with an empty allowance.
        raise RuntimeError("Apify pool ledger is unreadable; collection paused") from None


@contextmanager
def _locked():
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_PATH.with_suffix(".lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(fd, "a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        state = _read()
        yield state
        temporary = STATE_PATH.with_name(STATE_PATH.name + "." + uuid.uuid4().hex + ".tmp")
        fd = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as output:
            json.dump(state, output, ensure_ascii=False, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, STATE_PATH)


def _community():
    try:
        import community
        return community
    except ModuleNotFoundError as exc:
        if exc.name == "community":
            return None
        raise RuntimeError("Community credential support is unavailable; use the project virtual environment") from None


def token_accounts(env=None):
    """Internal only: distinct owner and active contributed credentials.

    No Bamboo/Chumei env, Keychain account, DB or credential is consulted.
    A duplicate contributed token always retains its contributor authorization.
    """
    values = dict(os.environ if env is None else env)
    keys = sorted(k for k in values if k in {"HARMONICA_APIFY_API_TOKEN", "APIFY_TOKEN", "APIFY_API_TOKEN"}
                  or k.startswith("APIFY_TOKEN_"))
    tokens = [str(values[k]).strip() for k in keys if str(values[k]).strip()]
    if env is None and not tokens and values.get("HARMONICA_APIFY_USE_KEYCHAIN", "1") == "1":
        cached = _KEYCHAIN_CACHE
        # Do not repeatedly prompt/retry a missing or inaccessible Keychain item
        # from anonymous page requests. Successful values refresh once/minute.
        if not cached["loaded"] or cached["token"] and time.time() - cached["checkedAt"] > 60:
            cached.update(loaded=True, token="", checkedAt=time.time())
            try:
                result = subprocess.run(["security", "find-generic-password", "-s",
                                         values.get("HARMONICA_APIFY_KEYCHAIN_SERVICE", "harmonica-observe-apify"),
                                         "-a", values.get("HARMONICA_APIFY_KEYCHAIN_ACCOUNT", "harmonica"), "-w"],
                                        capture_output=True, text=True, timeout=3, check=False)
                if result.returncode == 0 and result.stdout.strip():
                    cached["token"] = result.stdout.strip()
            except (OSError, subprocess.SubprocessError):
                pass
        if cached["token"]:
            tokens.append(cached["token"])
    cap = _number(values.get("HARMONICA_APIFY_MONTHLY_BUDGET_USD", "4"))
    result = {token: {"token": token, "budgetUsd": cap, "community": False} for token in tokens}
    provider = _community() if env is None else None
    if provider:
        registered = provider.registered_token_hashes()
        result = {token: row for token, row in result.items()
                  if hashlib.sha256(token.encode()).hexdigest() not in registered}
        for row in provider.active_tokens():
            token = str(row.get("token") or "").strip()
            if token:
                result[token] = {**row, "token": token, "community": True}
    accounts = []
    for token, row in result.items():
        accounts.append({**row, "key": hashlib.sha256(token.encode()).hexdigest()})
    return accounts



class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_request(request, *, timeout=20):
    """Apify credentials must never follow a redirect to another destination."""
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)


def verify_actor_cap(actor, maximum, *, now=None):
    """Fail closed if an actor's current pricing no longer supports the USD cap."""
    now = time.time() if now is None else now
    if actor not in {"apify/facebook-posts-scraper", "apify/instagram-profile-scraper", "intropix/instagram-stories-scraper"}:
        raise ValueError("Unsupported pooled Apify actor")
    try:
        request = urllib.request.Request("https://api.apify.com/v2/acts/" + actor.replace("/", "~"),
                                         headers={"Accept": "application/json"})
        with open_request(request, timeout=20) as response:
            data = json.loads(response.read(1_000_000)).get("data", {})
        prices = [p for p in data.get("pricingInfos", []) if isinstance(p, dict)
                  and 0 < _timestamp(p.get("startedAt")) <= now]
        latest = max(prices, key=lambda p: _timestamp(p["startedAt"]))
        if latest.get("pricingModel") != "PAY_PER_EVENT":
            raise ValueError("USD charge cap not supported")
        if _number(latest.get("minimalMaxTotalChargeUsd")) > maximum:
            raise ValueError("budget below actor minimum")
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("Apify actor pricing cannot be verified within the authorized charge cap") from None

def fetch_quota(token, *, now=None):
    """Read-only limits query; response and exceptions never contain credentials."""
    now = time.time() if now is None else now
    request = urllib.request.Request("https://api.apify.com/v2/users/me/limits",
                                     headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    try:
        with open_request(request, timeout=20) as response:
            data = json.load(response).get("data", {})
        identity = urllib.request.Request("https://api.apify.com/v2/users/me", headers=request.headers)
        with open_request(identity, timeout=20) as response:
            account_id = str(json.load(response).get("data", {}).get("id") or "")
        if not account_id:
            raise ValueError("missing provider identity")
        limit = float(data["limits"]["maxMonthlyUsageUsd"])
        used = float(data["current"]["monthlyUsageUsd"])
        if not math.isfinite(limit) or not math.isfinite(used) or limit < 0 or used < 0:
            raise ValueError("invalid quota")
        cycle = data["monthlyUsageCycle"]
        if not _timestamp(cycle.get("startAt")) or _timestamp(cycle.get("endAt")) <= now:
            raise ValueError("unknown quota cycle")
        return {"checkedAt": now, "accountId": hashlib.sha256(("apify-account:" + account_id).encode()).hexdigest(), "limitUsd": limit, "usedUsd": used,
                "remainingUsd": max(0.0, limit - used), "cycleStart": cycle["startAt"],
                "cycleEnd": cycle["endAt"], "available": True}
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Apify quota HTTP {exc.code}") from None
    except (OSError, ValueError, KeyError, TypeError):
        raise RuntimeError("Apify quota verification unavailable") from None


def refresh_quota(*, now=None):
    now = time.time() if now is None else now
    accounts = token_accounts()
    results = {}
    for account in accounts:
        try:
            results[account["key"]] = fetch_quota(account["token"], now=now)
            if account.get("community"):
                _community().mark_quota(account["id"], results[account["key"]])
        except RuntimeError as exc:
            results[account["key"]] = {"available": False, "error": str(exc), "attemptedAt": now}
    with _locked() as state:
        for key, quota in results.items():
            state.setdefault("accounts", {}).setdefault(key, {})["quota"] = quota
    return pool_status(now=now)


def _account_view(account, state, now, all_accounts=()):
    entry = state.get("accounts", {}).get(account["key"], {})
    quota = entry.get("quota", {})
    verified = account.get("verifiedQuota") or {}
    if _timestamp(verified.get("checkedAt")) > _timestamp(quota.get("checkedAt")) and not quota.get("attemptedAt", 0) > _timestamp(verified.get("checkedAt")):
        quota = verified
    # A newer limits reading on a second token for the same provider account
    # supersedes older balance data. Keep each credential's own freshness/auth
    # state so another credential cannot make an invalid token appear verified.
    if quota.get("accountId"):
        related = [e.get("quota", {}) for e in state.get("accounts", {}).values()]
        related += [a.get("verifiedQuota") or {} for a in all_accounts]
        newer = [q for q in related if q.get("accountId") == quota["accountId"]
                 and _timestamp(q.get("checkedAt")) > _timestamp(quota.get("checkedAt"))]
        if newer:
            latest = max(newer, key=lambda q: _timestamp(q.get("checkedAt")))
            quota = {**quota, "remainingUsd": latest.get("remainingUsd"), "usedUsd": latest.get("usedUsd")}
    checked = _timestamp(quota.get("checkedAt"))
    cycle_start, cycle_end = _timestamp(quota.get("cycleStart")), _timestamp(quota.get("cycleEnd"))
    fresh = bool(checked and quota.get("accountId") and cycle_start and -60 <= now - checked <= QUOTA_TTL and cycle_start <= now < cycle_end
                 and quota.get("available", True) and "remainingUsd" in quota)
    billing_account = quota.get("accountId") or account["key"]
    runs = [r for r in state.get("runs", []) if r.get("billingAccount", r.get("account")) == billing_account]
    cycle_runs = [r for r in runs if _number(r.get("at")) >= cycle_start]
    local_spend = sum(_number(r.get("reservedUsd")) for r in cycle_runs)
    # Billing may lag terminal completion. Outstanding and last-day reservations
    # remain deducted even following a successful metadata refresh.
    unreconciled = sum(_number(r.get("reservedUsd")) for r in runs
                       if not r.get("finishedAt") or _number(r.get("finishedAt")) + 86400 > checked)
    remote = max(0.0, _number(quota.get("remainingUsd")) - unreconciled - MIN_RESERVE_USD)
    if account.get("community"):
        authorized = _number(account.get("budgetRemainingUsd"))
    else:
        # Owner monthly cap includes provider-wide use, retaining historical guard.
        authorized = max(0.0, _number(account.get("budgetUsd")) - max(local_spend, _number(quota.get("usedUsd"))))
    remaining = min(remote, authorized) if fresh else 0.0
    day_start = math.floor(now / 86400) * 86400
    today = [r for r in runs if _number(r.get("at")) >= day_start]
    spent_today = sum(_number(r.get("reservedUsd")) for r in today)
    days_left = max(1, math.ceil((cycle_end - now) / 86400))
    daily = (remaining + spent_today) / days_left if fresh else 0.0
    share = daily / len(PLATFORM_SHARES)
    elapsed = min(1.0, max(0.0, (now - day_start) / 86400))
    spent = {p: sum(_number(r.get("reservedUsd")) for r in today if r.get("platform") == p) for p in PLATFORM_SHARES}
    held = {p: max(0.0, min(share - spent[p], share * (1 - elapsed))) for p in PLATFORM_SHARES}
    unspent = max(0.0, daily - sum(spent.values()))
    budgets = {p: max(0.0, min(remaining, unspent - sum(v for o, v in held.items() if o != p)))
               for p in PLATFORM_SHARES}
    story_results = sum(int(r.get("reservedResults") or 0) for r in today if r.get("platform") == "instagram_stories")
    if story_results >= 40:
        budgets["instagram_stories"] = 0.0
    return {"key": account["key"], "billingAccount": billing_account, "available": fresh, "stale": not fresh,
            "checkedAt": checked or None, "remainingUsd": remaining,
            "dailyBudgetUsd": daily, "budgets": budgets, "storyResultsLeft": max(0, 40 - story_results),
            "lastSelectedAt": entry.get("lastSelectedAt", 0), "community": bool(account.get("community")),
            "cycleEnd": quota.get("cycleEnd"), "cycleStart": quota.get("cycleStart")}


def pool_status(*, refresh=False, now=None):
    """Public aggregate only; default never performs an Apify network request."""
    if refresh:
        return refresh_quota(now=now)
    now = time.time() if now is None else now
    state = _read()
    accounts = token_accounts()
    rows = [_account_view(a, state, now, accounts) for a in accounts]
    # Multiple tokens for the same provider account do not create more credit.
    # Pick the credential with the greatest remaining authorization for planning;
    # all credentials share the same provider reservation and daily usage ledger.
    by_account = {}
    for row in rows:
        if row["available"] and row["remainingUsd"] > by_account.get(row["billingAccount"], {}).get("remainingUsd", -1):
            by_account[row["billingAccount"]] = row
    verified = list(by_account.values())
    return {"available": bool(verified), "accountCount": len(rows),
            "communityAccountCount": sum(r["community"] for r in rows),
            "verifiedAccountCount": len(verified), "unknownAccountCount": sum(not r["available"] for r in rows),
            "usableAccountCount": sum(any(r["dailyBudgetUsd"] * PLATFORM_SHARES[p] + 1e-9 >= MIN_RUN_BUDGET[p] for p in PLATFORM_SHARES) for r in verified),
            "remainingUsd": round(sum(r["remainingUsd"] for r in verified), 6) if verified else None,
            "dailyBudgetUsd": round(sum(r["dailyBudgetUsd"] for r in verified), 6) if verified else None,
            "checkedAt": min((r["checkedAt"] for r in verified), default=None),
            "stale": any(not r["available"] for r in rows), "exhausted": bool(verified) and not any(r["remainingUsd"] > 0 for r in verified),
            "platforms": {p: {"availableTodayUsd": round(sum(r["budgets"][p] for r in verified), 6),
                               "maxRunBudgetUsd": round(max((r["budgets"][p] for r in verified), default=0.0), 6),
                               "dailyShare": PLATFORM_SHARES[p],
                               "minimumRunBudgetUsd": MIN_RUN_BUDGET[p],
                               "estimatedSourcesPerDay": sum(_daily_source_capacity(p, r["dailyBudgetUsd"] * PLATFORM_SHARES[p]) for r in verified)} for p in PLATFORM_SHARES},
            "budgetPolicy": "verified-provider-limit-and-authorized-cap", "billingPolicy": "full-run-cap-reserved"}


public_status = pool_status


def available_budget(platform, *, refresh=False, now=None):
    status = pool_status(refresh=refresh, now=now)
    return status["platforms"].get(platform, {}).get("maxRunBudgetUsd", 0.0)


def story_run_options(*, now=None):
    """Pair each distinct account's dollars and result allowance for planning.

    Never combine one account's money with another account's result slots.
    These are only hints: reserve_run rechecks authorization atomically before
    any actor POST. Unknown/failed runs continue to consume their full reserve.
    No credential or provider identity leaves this helper.
    """
    now = time.time() if now is None else now
    state, accounts = _read(), token_accounts()
    providers = {}
    for account in accounts:
        row = _account_view(account, state, now, accounts)
        budget = row["budgets"]["instagram_stories"]
        if not row["available"] or row["storyResultsLeft"] <= 0 or budget + 1e-9 < MIN_RUN_BUDGET["instagram_stories"]:
            continue
        # Aliases of the same provider share result counters. Keep the greatest
        # still-authorized credential's capacity, never add their credit twice.
        previous = providers.get(row["billingAccount"])
        if previous is None or budget > previous["maxRunBudgetUsd"]:
            providers[row["billingAccount"]] = {
                "maxRunBudgetUsd": math.floor((budget + 1e-12) * 1_000_000) / 1_000_000,
                "resultsLeft": row["storyResultsLeft"],
            }
    return sorted(providers.values(), key=lambda row: (row["resultsLeft"], row["maxRunBudgetUsd"]), reverse=True)


def reserve_run(platform, max_cost_usd, *, source_count=0, result_count=0, refresh=False, now=None):
    """Atomically authorize one bounded POST. Returned token is internal only."""
    now = time.time() if now is None else now
    amount = _number(max_cost_usd)
    if platform not in PLATFORM_SHARES or amount <= 0:
        raise ValueError("Invalid Apify reservation")
    if refresh:
        refresh_quota(now=now)
    with _locked() as state:
        accounts = token_accounts()
        candidates = [(a, _account_view(a, state, now, accounts)) for a in accounts]
        candidates = [(a, v) for a, v in candidates if v["available"] and v["budgets"][platform] + 1e-9 >= amount
                      and (platform != "instagram_stories" or 0 < result_count <= min(10, v["storyResultsLeft"]))]
        candidates.sort(key=lambda pair: (pair[1]["lastSelectedAt"], pair[1]["cycleEnd"] or ""))
        for account, view in candidates:
            run_id = uuid.uuid4().hex
            if account.get("community") and not _community().reserve_budget(account["id"], run_id, amount):
                continue
            receipt = {"id": run_id, "account": account["key"], "billingAccount": view["billingAccount"], "at": now, "platform": platform,
                       "sourceCount": max(0, int(source_count)), "reservedUsd": amount,
                       "reservedResults": max(0, int(result_count)), "status": "reserved"}
            if account.get("community"):
                receipt["contributionId"] = account["id"]
            state.setdefault("runs", []).append(receipt)
            state.setdefault("accounts", {}).setdefault(account["key"], {})["lastSelectedAt"] = now
            return {"id": run_id, "token": account["token"], "maxCostUsd": amount}
    raise RuntimeError("Apify pool paused: verified quota, pacing or authorized budget unavailable")



def record_run_started(reservation_id, actor_run_id):
    """Persist the provider run ID before polling so interrupted runs are auditable."""
    with _locked() as state:
        row = next((r for r in state.get("runs", []) if r.get("id") == reservation_id), None)
        if not row:
            raise ValueError("Unknown Apify reservation")
        row.update(actorRunId=str(actor_run_id)[:100], status="RUNNING")

def finish_run(reservation_id, *, status, actual_cost_usd=None, actor_run_id=None, now=None):
    """Store sanitized telemetry; keep the full cap charged to authorization.

    Actor usageTotalUsd is preliminary. Conservatively settling at the cap avoids
    accidentally restoring a contributor's budget when event billing arrives late.
    """
    now = time.time() if now is None else now
    with _locked() as state:
        row = next((r for r in state.get("runs", []) if r.get("id") == reservation_id), None)
        if not row:
            raise ValueError("Unknown Apify reservation")
        row.update(status=str(status) if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT", "UNKNOWN"} else "UNKNOWN")
        if actor_run_id:
            row["actorRunId"] = str(actor_run_id)[:100]
        if actual_cost_usd is not None:
            row["reportedCostUsd"] = _number(actual_cost_usd)
            if row["reportedCostUsd"] > row["reservedUsd"]:
                row["budgetOverrun"] = True
                row["reservedUsd"] = row["reportedCostUsd"]
        if status in {"SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"}:
            row["finishedAt"] = now
            if row.get("contributionId"):
                _community().settle_budget(row["id"], row["reservedUsd"])



def _daily_source_capacity(platform, allowance):
    """Model complete source batches; sub-minimum account budgets add no capacity."""
    total = 0
    for _ in range(8):
        if allowance + 1e-9 < MIN_RUN_BUDGET[platform]:
            break
        if platform == "facebook":
            count = min(24, max(0, math.floor((min(allowance, .25) - .006 + 1e-9) / .025)))
            cost = .006 + .025 * count
        elif platform == "instagram":
            count = min(5, max(0, math.floor((allowance + 1e-9) / .006)))
            cost = .006 * count
        else:
            # One current story per source is a planning assumption; accounts
            # with many stories can exhaust a result cap before later targets.
            count = min(10, max(0, math.floor((allowance - .005 + 1e-9) / .0045)), 40 - total)
            cost = .005 + .0045 * count
        if not count:
            break
        total += count
        allowance -= cost
    return total

def crawl_schedule_snapshot(*, now=None, sources=None):
    """Capacity estimate, never a claimed last-fetch time or delivery promise."""
    now = time.time() if now is None else now
    status = pool_status(now=now)
    if sources is None:
        try:
            sources = json.loads((ROOT / "data/feeds/social_sources.json").read_text()).get("sources", [])
        except (OSError, ValueError):
            sources = []
    counts = {p: 0 for p in PLATFORM_SHARES}
    for source in sources:
        if not source.get("enabled", True):
            continue
        kind, provider = source.get("type"), source.get("provider")
        platform = ("facebook" if kind == "facebook_page_posts" else
                    "instagram_stories" if provider == "apify_stories" else
                    "instagram" if provider == "instagram_public" else None)
        if platform:
            counts[platform] += 1
    platforms = {}
    daily = status.get("dailyBudgetUsd")
    # Collector executes every three hours at most (eight batches/day). This is
    # a capacity ceiling; real scheduler cadence can be lower or disabled.
    for platform, count in counts.items():
        capacity = status["platforms"][platform]["estimatedSourcesPerDay"]
        days = round(max(0.125, count / capacity), 2) if capacity > 0 and count else None
        platforms[platform] = {"sourceCount": count, "estimatedDays": days,
                               "estimatedSourcesPerDay": round(capacity, 2) if daily is not None else None,
                               "costPerSourceUsd": COST_PER_SOURCE[platform], "estimate": True,
                               "state": "no_sources" if not count else "unknown" if daily is None else "paced" if capacity else "insufficient_daily_budget"}
    return {"generatedAt": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
            "available": status["available"], "pool": status, "platforms": platforms,
            "estimate": True, "assumptions": {"costBasis": "conservative-planning-model-not-provider-price",
                                              "collectorRunsPerDayMaximum": 8, "facebookPostsPerSource": 5, "storiesPerSource": 1,
                                              "schedulerVerified": False}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="GET Apify limits only; never starts an actor")
    args = parser.parse_args()
    from run_pipeline import load_dotenv
    load_dotenv(ROOT / ".env")
    if args.refresh:
        refresh_quota()
    print(json.dumps(crawl_schedule_snapshot(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
