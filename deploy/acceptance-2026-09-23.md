> 最新修正：使用者否決手刻月曆，已恢復 Google Calendar 官方嵌入、放大限動／貼文圖片並修復竹韻限動匯入。[最新驗收](media-home-acceptance-2026-09-23.md) 優先於以下原生月曆版本的歷史紀錄。

# Harmonica Observatory acceptance — 2026-09-23

## Latest feature follow-up — verified

The following implementation supersedes the earlier UI checkpoints below. The deployment and test counts in the historical sections remain evidence of those earlier snapshots. This follow-up was verified together against localhost and the existing public HTTPS runtime on 2026-09-23.

- **One localized wordmark per interface language:** English `Harmonica Observatory`, Traditional Chinese `口琴觀測站`, Japanese `ハーモニカ観測所`, Korean `하모니카 관측소`. Navigation branding, the footer, browser titles, SSR SEO and OG use the selected name without an additional Chinese or English wordmark subtitle. Public source names, bios and posts remain in their original language.
- **Distinct homepage and full feed:** `/` restores the original composition of active stories, an interactive native event calendar, then an embedded multicolumn post feed. The homepage scrolls as a page. `/post/` remains the dedicated full feed, with independently scrolling desktop columns and a horizontally scrolling deck; mobile has a readable single feed. The original cream `#f6f4ed` background and green `#244c3e` identity remain, while layout and controls follow Chumei.
- **Functional native calendar:** month/year selection, previous/next month, today, day selection and agenda, keyboard date navigation, and a country/region facet independent of UI language and post filters. Dates retain event-local timezone semantics, including civil all-day dates, exclusive end dates and DST handling. An empty day or month is shown honestly.
- **Scores with provenance and facets:** competition repertoire and publisher/collection views retain original titles and notes. Search, country, academic year, instrumentation, division, publisher and sorting use actual catalog fields and counts. Original evidence and publishing/enquiry links remain distinct and deduplicated. A repertoire index entry does not promise a downloadable full score.
- **Contextual reporting:** source rows/profiles, posts, events and scores link to `/submit/` with public URL, name and known country context. The form prefills these values safely, accepts legacy report-link parameters, converts local source links to absolute public URLs and leaves unknown countries unset. Reports enter the existing review queue; public records are not changed automatically. Existing session, CSRF, token handling and draft-preserving background refresh behavior remain in place.

The native calendar reads the site's public snapshot. It does **not** add an external Calendar synchronization service, cross-device OAuth, push notifications or a dedicated `/calendar/` route. Existing event lists and ICS subscriptions remain available. No fake login or inactive navigation control is introduced.

Earlier Chumei-layout and cream/green evidence is preserved in [ui-acceptance-2026-09-23.md](ui-acceptance-2026-09-23.md). Its earlier statement that Japanese/Korean use the English brand and its earlier feature/test snapshot are superseded by this follow-up.

## Follow-up acceptance results

- Python: **225 tests passed**; Node/DOM: **54 tests passed**. New coverage includes localized branding, calendar event-local days/DST/exclusive ends, home versus full-feed composition, contextual reporting, score facets/evidence, source-aware event following and mobile column control synchronization.
- Public HTTPS: **92 read-only checks passed**, using normal TLS validation; routes, four-language SSR metadata, new assets, JSON/RSS/ICS, session cookie properties, true 404s and legacy redirects checked.
- Public Chromium: **112 route/locale/viewport checks passed** (14 routes including both source-detail URL forms × 4 languages × desktop/mobile), with no JavaScript errors, CSP violations, failed assets, console errors or horizontal document overflow.
- Homepage interaction matrix: **24 combinations passed** (1440×900, 850×900, 390×844 × four languages × light/dark). Verified month/day/today controls, country independence from the river, history restoration, desktop independent column scrolling and mobile single-feed behavior. Desktop embedded deck measured 760 px tall; the page itself scrolls normally.
- Scores: 16 desktop/mobile locale/view combinations plus keyboard, filtering, sorting, reload, tab/history, language and contextual-report navigation passed. Filters use live data counts, not fixture numbers.
- Contribution forms were tested with intercepted mock mutations only: error, success, cancellation, withdrawal and background-refresh draft/focus preservation all passed. No real token or public submission was sent.
- Public outputs, source coverage, legacy redirects and sitemap SEO validators passed; **400 sitemap URLs checked, zero errors** at this snapshot.
- The existing web LaunchAgent was restarted for localized SSR changes; Caddy and other sites were unchanged. No paid ingestion, external Calendar write or GitHub Pages publication was invoked for this follow-up.

Local evidence: `state/ui-acceptance-2026-09-23/followup/` contains the current HTTP/browser reports, test logs and selected screenshots (ignored runtime artifacts, not committed). The public snapshot during acceptance contained 322 sources, 788 posts, 19 events, 797 repertoire rows, 39 score-source collections and 0 active stories. These values are observations only; the UI derives counts from the catalog.

Known limits: dates reflect supplied public records, so a source lacking structured time can remain an all-day entry even when prose mentions a time. Scores are a provenance index rather than a promise of full-score files. Account ownership remains the original browser cookie; OAuth/push and external calendar synchronization were not added. The homepage calendar and all controls introduced in this follow-up are functional.

## Historical deployment and baseline evidence

The remaining sections preserve the previous deployment and validation checkpoints. Their counts, data snapshots and pending-review statements are historical, not the current feature follow-up's final status.

## Runtime and deployment

The local application listens on `127.0.0.1:8330` as the user LaunchAgent `tw.observe.harmonica.web`. It uses this checkout's `.venv/bin/python`. Its environment declares `HARMONICA_PUBLIC_ORIGIN=https://harmonica.observe.tw` and `HARMONICA_TRUST_PROXY=1`; only a loopback HTTPS reverse proxy is trusted. Browser sessions and encrypted contribution records are isolated under `state/community/`.

The service installer was exercised with mocked launchctl calls in three tests. The actual web LaunchAgent was installed and started during this deployment. `GET /api/v1/health`, `/api/v1/catalog`, `/api/v1/community` and `/api/v1/session` responded successfully on localhost. The ingestion LaunchAgents were temporarily unloaded while the migration was being checked, then restored; their verified final configuration is recorded below.

Install and start on this Mac:

```bash
.venv/bin/python scripts/install_local_service.py --install --public-origin https://harmonica.observe.tw
```

Inspect or restart after Python changes:

```bash
launchctl print gui/$(id -u)/tw.observe.harmonica.web
launchctl kickstart -k gui/$(id -u)/tw.observe.harmonica.web
curl --fail http://127.0.0.1:8330/api/v1/health
```

Logs are `logs/web.log` and `logs/web.err.log`. Request bodies, tokens and request paths are not logged by the application. An early community endpoint failure was traced to a running process holding an older imported module; restarting after the coordinated changes resolved it.

## TLS and DNS evidence

Both the local resolver and Cloudflare's `1.1.1.1` resolver returned `A 140.113.240.11` for `harmonica.observe.tw`, with no AAAA answer. The Mac's interface is `10.113.240.11`, behind the public address. No DNS records were changed by this deployment.

The previous certificate had expired. Recent Caddy renewal errors showed ACME validation reaching the old Cloudflare IPv6 destination and receiving 404. Once DNS pointed to the Mac, public HTTP requests reached Caddy. The existing active JSON configuration was force-reloaded through the admin API, with `Cache-Control: must-revalidate`, without modifying any site's configuration. The next normal certificate maintenance pass successfully completed ACME validation and renewed the Harmonica certificate. The force-reload procedure follows the [Caddy administration API](https://caddyserver.com/docs/api#post-load).

Verified using the system certificate trust store and hostname validation, with no TLS bypass:

- Issuer: Let's Encrypt YE1.
- Valid from: **2026-09-22 17:01:16 UTC**.
- Valid until: **2026-12-21 17:01:15 UTC**.
- Public HTTPS homepage returned 200 after renewal.
- The entire active Caddy configuration compared equal before and after certificate renewal.

A private `0600` backup is stored at `state/caddy-before-harmonica-tls-1790099539.json`. This runtime backup may contain configuration credentials and is not part of the repository or public site. Caddy's root LaunchDaemon passes macOS `plutil -lint`; Python's stricter plist XML parser rejected a harmless nonstandard DOCTYPE spelling, so no privileged daemon repair was required.

## Reverse proxy acceptance

**Deployed:** public Caddy now reverse-proxies Harmonica to the localhost application. The active route was changed with a scoped ETag-protected admin PATCH, which returned 200. The same Harmonica-only change was persisted to `/usr/local/etc/caddy/Caddyfile`. The full active configuration compared equal to the expected single-route change; all unrelated virtual hosts, TLS policies and credential expansions were preserved.

The prepared persistent target is the existing Harmonica block in `/usr/local/etc/caddy/Caddyfile`:

```caddyfile
harmonica.observe.tw {
    encode zstd gzip
    reverse_proxy 127.0.0.1:8330
}
```

The candidate was successfully adapted by Caddy. Only this site's block changed; every other Caddyfile byte remained identical. The scoped admin API preserved existing credential expansions and unrelated services. `deploy/Caddyfile.snippet` contains the same target configuration.

Public acceptance verified actual JSON responses, not only status 200. Repeat the checks with:

```bash
curl --fail https://harmonica.observe.tw/api/v1/health
curl --fail --compressed https://harmonica.observe.tw/api/v1/community
curl --fail --compressed https://harmonica.observe.tw/api/v1/sources?limit=1
```

**37 public HTTPS checks passed** with normal certificate and hostname validation:

- JSON health returned `{"ok":true,"service":"harmonica","version":1}`; catalog, community and session APIs also returned JSON.
- The browser session cookie included Secure, HttpOnly and SameSite=Strict.
- English, Traditional Chinese, Japanese and Korean homepage, directory, contribution and known-source SSR pages returned the requested language.
- Application JavaScript, stylesheet and language/community modules loaded successfully.
- Source/update RSS and Taiwan/international/online ICS feeds were intact.
- Missing URLs and private `.env`/state paths returned real 404 responses.
- `/directory/` and `/score-sources/` redirected to the new equivalents while preserving locale queries.
- A cross-origin write was rejected with 403, without creating a submission.
- Same-origin CSRF-authenticated contribution/submission requests reached their validators and rejected missing consent/invalid URL with the expected 400 error codes. No real tokens, actor spend or public test submissions were created.

The live public catalog at this check contained **322 sources, 789 posts, 12 events, 797 score entries and 39 score collections**. Browser visual acceptance remains pending; native browser automation required an approval step unavailable at this checkpoint.

## Scheduler acceptance

Both `tw.observe.harmonica.pipeline` and `tw.observe.harmonica.social-fast` are loaded again in the current user's launchd domain. Readback verified:

- `StartInterval=1800` seconds on both jobs.
- `RunAtLoad=false`, so reloading their configuration did not initiate an extra paid crawl.
- Both execute this checkout's `.venv/bin/python` and set `HARMONICA_LLM_PROVIDER=codex`.
- Neither passes `--publish-pages`; generated outputs are served directly from this installation.
- Both were idle with `runs=0` and `last exit code=(never exited)` after restoration. Launchd exposed the interval but did not provide an exact next-fire timestamp. A new paid collection cycle was not forced for acceptance.

The last completed historical pipeline snapshot was `status=ok`, `Pipeline completed`, at **2026-09-23 00:58:58 Asia/Taipei** in `site/api/pipeline-runtime.json`. The last social-fetch snapshot completed successfully at **00:57:00**. These timestamps are distinguished from the newer offline rebuild; no fresh crawl success is inferred from rebuilding public pages.

A stale **empty** `state/social-fast.lock` directory, dated September 18, was preventing the fast scheduler from getting past its outer shell lock. Its historical log repeatedly reported `social-fast already running; skip`. With no pipeline process running, that stale empty directory was removed. No job was started as part of this cleanup. The redundant outer directory lock was removed from both the source and installed fast-scheduler plist. The job now uses `exec` and relies on `run_pipeline.py`'s existing PID/staleness-aware lock. The installed environment, arguments and 1800-second schedule were preserved; both plist files passed `plutil -lint`. The fast scheduler was re-bootstrapped with `RunAtLoad=false`, and readback again showed all three services loaded, the web service running, and both ingestion jobs idle with zero runs. Three focused scheduler tests pass, including regression coverage for the stale outer lock and preventing an extra crawl at configuration load.

Read-only follow-up:

```bash
launchctl print gui/$(id -u)/tw.observe.harmonica.pipeline
launchctl print gui/$(id -u)/tw.observe.harmonica.social-fast
curl --fail https://harmonica.observe.tw/api/pipeline-runtime.json
```


## Validation evidence

- **224 Python unit tests passed**, as reported by the integration runner.
- **114 local HTTP acceptance checks passed**, as reported by the integration runner.
- **13 Node frontend tests passed**, as reported by the frontend/integration runner.
- **37 public HTTPS acceptance checks passed** after the actual Caddy proxy switch.
- Additional targeted coverage includes encrypted storage, owner-only withdrawal, concurrent budget reservations, CSRF/Host/Origin controls, source-local event timezones, contribution revocation, moderation export, installation and server-rendered content.
- The renderer's literal-backslash source-name crash and legacy source-post alias mismatch were found and repaired; all six focused renderer tests pass.
- The moderation workflow has five passing tests. Export preserves original notes/country, creates an idempotent pending intake record, and does not perform inference, fetch URLs, publish content or change the public source registry.
- A completely isolated source copy, including new source files but excluding runtime snapshots, built successfully under macOS's network-denial sandbox. The normal public-output and SEO validators passed. It produced **322 sources, 797 score entries, 39 score collections, zero historical posts and one tracked manual event**. No private state or remote profile cache was created.
- `build_local.py` now passes explicit offline flags. Missing legacy HTML artifacts are seeded without replacing existing outputs. External calendar synchronization is marked `not_configured`; local JSON/ICS still builds normally.
- No real actor runs or new contributor tokens were used in tests. No Chumei database, identity, credentials or running service was modified.

The public proxy and restored scheduler configuration were verified at this checkpoint. Browser visual review was still pending at that point; later review is recorded in the subsequent checkpoint and the linked UI acceptance document.

## Rollback

The previous generated public site remains under `site/`; the migration does not delete it. To roll public traffic back, restore **only** the Harmonica site block and its matching active admin route to static serving:

```caddyfile
harmonica.observe.tw {
    encode zstd gzip
    root * "/Users/skyhong/Documents/Harmonica-in-Taiwan/site"
    try_files {path} {path}/ /index.html
    file_server
}
```

Use `state/Caddyfile.before-atlas` as a reference for that block and the corresponding Harmonica route in the private active-config backup. Patch the current route using its current admin API ETag; do not reload an older whole-server configuration over unrelated live changes. Keep the renewed TLS certificate. The web LaunchAgent can remain running on loopback during rollback.

To stop the new web process after traffic has been rolled back:

```bash
launchctl bootout gui/$(id -u)/tw.observe.harmonica.web
```

Keep `state/community/community.sqlite3` together with `state/community/encryption.key` when backing up or rolling back. These files contain the durable contribution authorization and accounting state; a code rollback should not replace them with an empty database.

## Historical browser and UI handoff checkpoint

- Final checks: 224 Python tests and 26 Node/DOM tests passed; sitemap validation checked 396 URLs with zero errors. Offline local build and public-output validators passed.
- Real public-browser checks covered all 12 primary routes at 390×844, plus 1440×900 desktop and four-language examples. No horizontal document overflow in inspected routes. Country selection survives language changes; follows, source detail links/title/canonical, and enabled session forms were verified. Screenshots were saved by the collaborative browser tool.
- Mocked DOM tests cover contribution success/error/withdraw/cancel, source submissions, CSRF request contracts, IME and delayed session refresh preserving draft values and focus. They do not use actual contributed tokens or paid actors.
- The user explicitly approved Playwright after Computer Use could not obtain native windows. The purpose-built collaborative preview browser was subsequently discovered and successfully used against the public site.
- **At this historical handoff, the editorial hero/globe layout was not accepted; the user required Chumei's deliberately designed structure.** Chumei was opened in a real browser and audited: desktop navigation rail, mobile bottom navigation, active stories and independently scrolling feed columns. That handoff called for a faithful structural adaptation. The later user instruction retained the old cream/green palette; the latest implementation is described above and does not restore the rejected hero/globe layout.
- Full continuation prompt: [next-agent-prompt-2026-09-23.md](next-agent-prompt-2026-09-23.md). Exact UI mapping: [CHUMEI_UI_HANDOFF.md](https://github.com/skyhong2002/harmonica-observatory/blob/b6f6797/web/CHUMEI_UI_HANDOFF.md).
