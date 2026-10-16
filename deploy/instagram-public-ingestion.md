# Account-independent Instagram collection

The scheduled pipeline uses `scripts/instagram_public_fetcher.py`, following
[Chumei's Instagram ingestion design](https://github.com/skyhong2002/chumei/blob/main/docs/instagram-ingestion.md).
It does not read an Instagram cookie or call the old Instaloader helpers.
Profile and Story source IDs remain unchanged, preserving deduplication.

- Stories: `intropix/instagram-stories-scraper`, using only this site's configured
  Apify credential. Only the public organization and professional creator accounts
  already in the directory are targets; mentions are never added as targets.
- Profiles: the free logged-out web GraphQL query first (the same one Chumei
  uses; `HARMONICA_IG_PROFILE_POSTS_DOC_ID` overrides a rotated doc id). From
  this host Instagram answers very few logged-out queries, often only one before
  401 "Please wait a few minutes", so `apify/instagram-profile-scraper` remains
  the workhorse for every source the direct query does not serve.
  `HARMONICA_INSTAGRAM_PUBLIC_DIRECT=0` disables the direct query.
- Both collectors run at most once per three hours, even when the fast pipeline
  runs every 30 minutes. Individual sources have adaptive 12–336 hour intervals
  (Stories capped at 168 hours). Never-checked accounts rotate first, ordered by
  their observed publishing cadence. A limited budget cannot cover every account
  within 24 hours; the status page reports actual coverage.

The state is `state/instagram_public.json`. Successful network attempts are
recorded there. The social watchdog reads that cache without making new IG
requests or claiming another successful fetch. Retired Instaloader state stays
on disk as history and does not govern the new collectors.

## Credit and execution guards

`HARMONICA_APIFY_MONTHLY_BUDGET_USD` limits total remote account usage, including
Facebook. The limit defaults to US$4; the operator approved US$5 from existing
free credit on 2026-09-18. The effective ceiling never exceeds the account's
reported limit. No code purchases credit or changes the Apify subscription.
Only this project's configured credential is read; Chumei contributor tokens
are not imported.

Instagram posts and Stories each receive a third of the pool's evenly paced
daily credit, shared with Facebook as described in
[the Apify pool policy](apify-pool.md#spending-policy). Each Story run
scans at most 10 accounts, returns at most 10 items and observes a 40-item daily
limit. A billable request reserves its worst-case cost and result count on disk
before submission and sets Apify's `maxTotalChargeUsd`. Unknown outcomes keep
their reservation. Apify balance failures stop paid work. Manual runs use the
same pipeline lock; `--pipeline-lock-held` is reserved for the pipeline child.

The actor's `OUTPUT` record distinguishes genuinely empty results from denial
and partial scans. Unattempted accounts remain due. Daily allowance denial
retries after UTC midnight; provider capacity denial retries after one hour.
Images are cached immediately; videos receive a cached first-frame preview.
Expired Stories are filtered before ingest and again by the homepage.

## Host-wide Instagram pacing

Chumei and Harmonica share this server's IP, so logged-out queries from both
take turns through `scripts/ig_public_host.py` (state in
`~/.cache/observe-instagram-public.json`; Chumei keeps an identical copy).
Queries are spaced at least 10 seconds apart. On the first refusal (HTTP
401/429 or "Please wait a few minutes") the collector records a host block and
every collector on the host stops direct queries for `BLOCK_SECONDS` (two
hours), so neither project keeps the IP blocked. Three consecutive other
failures stop the direct query for the current run only.

## Operations

```sh
python3 scripts/build_social_sources.py
python3 scripts/instagram_public_fetcher.py --kind story
python3 scripts/run_pipeline.py --skip-youtube --skip-facebook --skip-llm-tags --publish-pages
```

Use `--accounts username1,username2` to select directory accounts for a smoke
test. This does not bypass credit limits, source due times or provider cooldowns.
Use `--skip-instagram` on the pipeline when only rebuilding an existing cache.
The Instaloader/bootstrap scripts remain available for historical diagnostics;
refreshing a maintainer login is no longer a recovery step for scheduled work.

Verify `api/status.json` → `components[id=instagram].stories` and `profiles`
separately, then `api/latest.json` for current `story_expires_at` values and
cached `/assets/feed-images/` URLs. A zero error count alone is not evidence of
successful collection.
