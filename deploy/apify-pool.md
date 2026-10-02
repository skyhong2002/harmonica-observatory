# Apify collection and contributed capacity

The collector integration adapts Chumei's pooled quota, conservative pacing and
contribution model, with an independent Harmonica database, key and run ledger.
It never reads the Chumei or Bamboo project's credentials, database or state.

## Providers

| Content | Default provider | Fallback |
| --- | --- | --- |
| Facebook public posts | `apify/facebook-posts-scraper` | None |
| Instagram public profiles/posts | `apify/instagram-profile-scraper` | Logged-out Instagram only when `HARMONICA_INSTAGRAM_PUBLIC_FALLBACK=1` |
| Instagram stories | `intropix/instagram-stories-scraper` | Opt-in InstaStoriesViewer pilot; see rollout below |
| Threads / RSS sources | Existing RSSHub/RSS adapters | Existing configured public fallbacks |
| YouTube | Existing public YouTube adapter | Existing configured behavior |

This does not claim that every upstream is Apify. Existing source identifiers,
feed inbox shapes, story expiry, cached assets and archive deduplication remain
compatible. Only public content is collected; private Instagram profiles are
rejected.

## Credentials and storage

Use the project's `.venv/bin/python` for the service **and all collectors**;
community tokens require the `cryptography` dependency in `requirements.txt`.

Owner credentials are `HARMONICA_APIFY_API_TOKEN`, `APIFY_TOKEN`,
`APIFY_API_TOKEN`, or `APIFY_TOKEN_*` from this project's environment. Duplicate
tokens are deduplicated. When no environment credential exists, the existing
`harmonica-observe-apify` / `harmonica` Keychain entry can be used on macOS.
`HARMONICA_APIFY_USE_KEYCHAIN=0` disables that fallback. No Bamboo credential
fallback is retained. Credentials once registered as contributions never fall
back to owner authorization after exhaustion or revocation, even if an identical
token remains in the owner environment.

Community contributions use `scripts/community.py` and the local service API.
Each contributor explicitly authorizes a **cumulative lifetime budget**, not an
automatically renewed monthly budget. Tokens are encrypted in
`state/community/community.sqlite3` with a separate local key. The browser can
revoke its own contribution; revocation stops new reservations immediately.
Already authorized remote runs may finish. Never put tokens in public source
files, URL parameters, log messages, generated pages or Git.

`state/apify_pool.json` is a private, mode-0600 accounting file containing hashed
credential/provider identifiers and sanitized reservations, never tokens. Its
adjacent lock serializes all collector decisions. Both files stay outside the
served `site/` root. A corrupt ledger pauses collection instead of silently
resetting spending limits. Preserve the ledger when moving the service.

Multiple API tokens for the same Apify user are recognized through a hashed
provider account ID. They share provider headroom and daily usage; they do not
multiply the account's capacity. For conservative public planning only the
largest remaining authorization for that provider is counted at a time.

## Spending policy

1. GET `/v2/users/me/limits` and `/v2/users/me` verifies quota and account identity.
   A quota must have a valid current cycle and be at most one hour old before a
   new reservation. Missing, stale, failed or unverified quota cannot fund a run.
2. The owner monthly cap defaults to `HARMONICA_APIFY_MONTHLY_BUDGET_USD=4`, per
   provider account, including provider-wide reported monthly usage. Community
   contributions retain their explicit lifetime caps. The old global Facebook
   owner-only cap does not erase capacity added by contributors.
3. US$0.02 per provider account remains protected. Available capacity is spread
   across remaining cycle days, with 50% for Facebook, 25% for Instagram posts
   and 25% for stories. Unused daily portions are not borrowed by another
   platform. This avoids one collector consuming another's entire allowance.
4. Under one file lock, the pool rechecks quota, shared reservations, daily
   allowance, and the contributor's atomic SQLite authorization. It reserves
   the full request charge cap **before** making any billable POST.
5. Before reservation, a read-only actor metadata query confirms current
   `PAY_PER_EVENT` pricing and that the planned cap meets its minimum. An unknown
   pricing model pauses collection. Every paid actor request supplies `maxTotalChargeUsd`, a finite timeout and
   `restartOnError=false`. Selection rotates eligible credentials. An ambiguous
   POST is never retried using another token.
6. Apify event billing can lag the terminal result. The complete run charge cap
   remains charged against local authorization even if preliminary reported
   usage is smaller. Reported cost is separate telemetry. Outstanding runs and
   runs completed less than 24 hours before a verified quota snapshot also
   reduce provider headroom.
7. Story result reservations enforce at most 10 results/run and 40 results/day
   per provider account, across all credentials. Unknown outcomes retain their
   result allowance and spending reservation.

Apify's `maxMonthlyUsageUsd` is an account **spending limit**, not proof of free
prepaid credit. This service does not purchase a plan or raise a provider limit,
but an authorized run can charge the contributor's Apify account up to the
specified run cap. The UI must describe remaining *authorized capacity*, not
promise that all collection is free. Set the account's own Apify billing limit
as appropriate before contributing a token.

The conservative policy can underuse authorized funds. There is deliberately no
automatic release for a timed-out or ambiguous run. An operator must first
verify the provider's final billing and execution outcome before any manual
ledger correction; deleting the state file to resume collection is unsafe.

## Status and validation

Read cached, sanitized aggregate status without launching actors:

```sh
.venv/bin/python scripts/apify_pool.py
```

Refresh read-only provider metadata and print the aggregate (still no actors):

```sh
.venv/bin/python scripts/apify_pool.py --refresh
```

Collector commands `scripts/apify_facebook_fetcher.py --run` and
`scripts/instagram_public_fetcher.py` can spend authorized funds and should run
only through the configured pipeline after quota review.

`pool_status()`/`public_status()` returns only aggregate counts/capacity and
per-platform available daily budgets. Unknown capacity is `null`, never an
invented zero or reset. `crawl_schedule_snapshot()` calculates a current
per-platform estimate from verified capacity and enabled sources; registration
quota is usable immediately and revocation removes it immediately.

The estimated days are a planning model, not a delivery promise. They use
conservative complete-batch costs (not a fetched vendor price quote), actual
source counts, and a maximum of eight collector batches/day. Facebook reserves
five posts per source, including a startup allowance; Instagram profiles reserve
US$0.006 each; the story model assumes one result per source. Contributions below
a minimum viable daily batch add no estimated collection capacity. The modeled
minimum budgets are US$0.031 for Facebook, US$0.006 for an Instagram profile and
US$0.0095 for a story source; runtime actor minimums are checked separately. Existing adaptive source
cadence, provider outages, batch minimum charges and a disabled/slower scheduler
can reduce achieved collection frequency. The API exposes these assumptions and
`schedulerVerified: false`; last successful observations remain separate data.

Focused offline checks:

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_apify_pool.py'
.venv/bin/python -m unittest discover -s tests -p 'test_instagram_public_fetcher.py'
```

They exercise concurrent reservations, unknown and stale quota, account
identity deduplication, contributor revocation, lagging billing, story limits,
secret-safe metadata, and reservation-before-POST without a paid actor run.

Official API references: [account limits](https://docs.apify.com/api/v2/users-me-limits-get),
[actor start options](https://docs.apify.com/api/client/js/reference/interface/ActorStartOptions),
[subscription and spending limits](https://docs.apify.com/account/subscriptions).

## Story collection and publication follow-up (2026-09-23)

Stories now become eligible for another check after 12 hours, including older
successful/unconfirmed records with a longer polling interval. Eligibility does
not guarantee a run: the unchanged provider, daily, monthly and reservation
limits still control actual coverage. Due selection interleaves previously
checked accounts and exploration; batches reserve at least one result slot per
target. A run stopped by its result cap never marks an unobserved account as
successfully checked.

An explicit `--kind story --accounts <username>` targets only that account and
bypasses polling delays, while retaining all pool limits. `ingest_story_results`
can import a previously verified completed actor result without starting a new
actor. Actor success alone is not proof of public website publication: cached
source posts must flow through the selected-source `social_feed_watchdog.py`
bridge, then `build_public_data.py` and `generate_rss_feeds.py --offline`. Hold the
normal pipeline lock across this publication sequence. The watchdog reads the
Apify story cache for such a source; disable LLM tagging for this bounded replay.

The NYCU recovery reused a completed run with two still-valid public stories,
downloaded only its existing result/media, and retained the original expiry
instants. No new actor or higher spending cap was needed. Cached video content
is displayed as a preview frame with a link to the original Instagram story.

## Live homepage updates (2026-09-23, #27)

The homepage reads the existing public catalog once per visible minute and
on returning to the foreground or navigating back home. Per the latest user
instruction, the manual refresh button has been removed. These reads never
launch an actor or change provider budgets. Story cards are reconciled without
replacing retained media, the calendar, feed, focused inputs, or form drafts.
Failed refreshes preserve the last available cards until their display deadline.
The displayed “Last retrieved” time comes from stories' `observedAt`.

Harmonica now matches Chumei's **48-hour display window from publication**.
`scripts/story_lifecycle.py` provides the shared deadline for cached media
retention, watchdog import, cache publication and the public catalog. Catalog
`expiresAt` is the display deadline; `sourceExpiresAt` retains the provider's
original expiry. Cards say “Shown until” / “展示至” so the display window does
not imply the original Instagram link remains live. Unknown publication dates
are excluded. Reloading, polling and recollection do not extend the deadline.
No Chumei session, data store, school filters, or budget settings are shared.


## Collector scheduling and immediate publication (2026-09-23, #28)

This follows the user's clarification that the requested Chumei comparison
concerns collection, not just homepage refresh. Both installed pipelines use
`intropix/instagram-stories-scraper`; Chumei's old cookie/Instaloader collector
is not its current scheduled path. Harmonica retains its own tokens and pool.

- Previously checked story accounts now rank by recent public/cached activity
  before the age of the last attempt. Roughly one exploration slot per four
  choices keeps new sources discoverable; the global country-independent list
  and twelve-hour eligibility remain.
- `story_run_options()` pairs each distinct provider account's remaining
  authorization with its remaining daily result slots. Aliases do not multiply
  capacity. The planner never combines one account's dollars with another's
  result slots; `reserve_run()` still rechecks atomically, including revocation.
- Available complete batches are spread across eight daily collector slots,
  capped at eight runs per invocation. Capacity is reread between successful
  runs, and a source is attempted only once per invocation. Explicit accounts
  remain one bounded run. Denied or unknown outcomes stop the invocation;
  account-specific denial rotation is not yet implemented.
- Pipeline order is now story collection → `publish_story_cache.py` → profile
  collection → other collectors. The publisher holds the native pipeline lock,
  selects only enabled sources with unexpired cache entries missing publicly,
  uses the selected-source watchdog with no LLM tags, then generates RSS/JSON
  offline. No new cache means no subprocesses/rebuild. Existing-source updates
  do not require build_public_data or calendar writes.
- The publisher repairs valid pending keys that were marked seen without a
  candidate after baseline/interruption, using a temporary seen copy. Unrelated
  seen state is preserved; unreadable existing seen files fail closed.

A single bounded production check requested five accounts including NYCU,
reserved at most US$0.0275, and confirmed three stories. One new Aiden Soon
story was published immediately; the two NYCU stories were still active.
Collection through publication took about 34 seconds. This is an acceptance
snapshot, not a guaranteed batch yield or coverage frequency.

**Billing correction:** the earlier NYCU run initially reported US$0; a later
read returned US$0.012 with charged events. Another initially-zero run later
reported US$0.005 for actor start. `OUTPUT.reason=free` identifies the provider
tier and does not prove zero cost. Both pooled and legacy paths retain the full
run cap even for denied/initially-zero outcomes. Unknown results never restore
budget. Owner US$4/month, daily shares and contributor cumulative authorization
are unchanged. The observed current one-account pool cannot guarantee daily
coverage of all 179 configured story sources.

## Optional Instagram story backup pilot

`HARMONICA_ISV_ENABLED=1` enables the bounded InstaStoriesViewer step after the
primary story cache publisher. The versioned default is off. The current local
four-account trial, shared pacing, publication proof and rollback commands are in
[the 2026-09-24 rollout](insta-stories-viewer-rollout-2026-09-24.md).
This adapter uses no Apify capacity and preserves the existing paid-provider path.
