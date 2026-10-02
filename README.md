# Harmonica Observatory

[English](README.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

**Explore harmonica events, artists and score resources around the world, all in one place.**

Harmonica information is scattered across social platforms, websites and languages. Harmonica Observatory brings together public events, posts, artists, ensembles, clubs, teaching resources and score sources, helping performers, teachers, students and enthusiasts discover information and follow it back to the original source.

**[Visit Harmonica Observatory](https://harmonica.observe.tw/)** · [GitHub](https://github.com/skyhong2002/harmonica-observatory) · [Browse events](https://harmonica.observe.tw/events/) · [Explore sources](https://harmonica.observe.tw/source/) · [Find scores](https://harmonica.observe.tw/scores/)

The interface is available in **English, 繁體中文, 日本語 and 한국어**. Browse content from different countries and regions in your preferred interface language; language selection and country filters are independent.

## What can you find?

| What you want to do | Where to start |
| --- | --- |
| Find performances, competitions, classes and online events | [Events](https://harmonica.observe.tw/events/): check dates, venues and original announcements. The homepage also includes Google Calendar. |
| Follow public updates from the harmonica community | [Posts](https://harmonica.observe.tw/post/): search public posts and view original text, images, videos and source links. The homepage also previews stories within their display period. |
| Discover artists, ensembles, clubs and educators | [Source directory](https://harmonica.observe.tw/source/): explore listed sources by keyword, country and region. |
| Find competition repertoire, publishers and score collections | [Scores](https://harmonica.observe.tw/scores/) and [publication sources](https://harmonica.observe.tw/scores/sources/): search by school year, instrumentation, competition category and other criteria, with links to announcements, publishers or inquiry pages. |
| Subscribe to future updates | [Subscriptions](https://harmonica.observe.tw/feeds/): add updates and events to your reader or calendar using RSS or ICS. |

## About the data

- **Original sources stay accessible.** Posts retain their original text and links. Reference translations of source names and descriptions are available alongside the recorded original names and text.
- **Information reflects available data.** Events retain their original time zones. The [status page](https://harmonica.observe.tw/status/) shows data update times and platform status. Coverage and update frequency depend on source availability.
- **Scores are indexed, not necessarily downloadable.** Entries include competition repertoire, official references and publication leads. Not every entry provides a complete score download, and unauthorized files are not provided.
- **Stories have a display period.** Cached stories are displayed for 48 hours from their original publication time, with an expiry shown on each card. The original Instagram story may expire earlier. The page updates every minute and when you return to the tab.

## Help grow the directory

Know an artist, group, event or score source that is missing, or spot something that needs correcting? Use [submissions and corrections](https://harmonica.observe.tw/submit/) to share a public URL and description. Content pages also have contextual reporting links that prefill known details. Submissions are reviewed before public data changes.

To support ongoing collection of social updates, you can [contribute Apify capacity](https://harmonica.observe.tw/contribute/), set a cumulative spending limit and withdraw your authorization at any time. The page estimates capacity and update frequency; actual updates still depend on sources and collection results.

You can link contributions and submissions to your Google account for management across devices. Signing in transfers unlinked records from the current browser to your account. Without signing in, you can still manage records through a secure cookie in the original browser. If you clear that cookie before linking an account, revoke the original token in Apify. Google sign-in does not request Google Calendar permissions.

Developers can contribute code, interface translations and public source data. Local setup, data structures and validation commands are below. Before adding a source, read the [source submission rules](.agents/AGENTS.md); follow the [local hosting guide](deploy/local-hosting.md) for deployment.

## Run locally

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/build_local.py
.venv/bin/python scripts/serve.py --host 127.0.0.1 --port 8330
```

Open **http://localhost:8330/**. If built data is already available, you can start `serve.py` directly.

`build_local.py` builds site data from local CSV files and existing collection snapshots. It does not fetch new data, run paid actors, call AI or push to Git. A fresh clone without private runtime snapshots initially provides the CSV source directory and score index; the pipeline collects posts later.

Install the background service on macOS:

```bash
.venv/bin/python scripts/install_local_service.py --install \
  --public-origin https://harmonica.observe.tw
```

See [local hosting](deploy/local-hosting.md) for Caddy, DNS, HTTPS, backups, scheduling and recovery. The maintainer manages DNS changes; the application does not modify DNS.

## Architecture

```text
web/                       Four-language UI, shared components, views and locales
scripts/global_catalog.py  Normalize existing data into a global public model
scripts/serve.py           Local HTTP routes, public API, same-origin and CSRF checks
scripts/community.py       Encrypted Apify tokens, budgets, browser identity and reports
scripts/apify_pool.py      Shared collection budgets, atomic reservations and account rotation
scripts/llm_backend.py     AI gateway structured inference and invocation limits
data/sources/              Tracked public CSV files with stable public_id identifiers
site/                      Generated JSON, RSS, ICS, legacy pages and cached images
state/                     Private SQLite, keys and classification caches (not in Git)
data/feeds/                Local collection inbox and candidate posts (not in Git)
```

HTTP requests read snapshots only. Changing the interface language does not invoke the AI gateway or Apify. Collection and web serving run separately, so existing data remains available during temporary third-party failures.

Story collection prioritizes active sources and uses paced batches, following the approach in Chumei. Each batch is planned against one Apify account's spending and result capacity, preserving budget limits and atomic reservations. After collection, `scripts/publish_story_cache.py` immediately performs targeted processing and offline RSS/JSON publication, without waiting for profile, YouTube, Facebook or the full post-processing cycle. See the [Apify collection and budget contract](deploy/apify-pool.md).

### Data and URLs

- `data/sources/harmonica-source-watchlist-public.csv`: primary public source list.
- `data/sources/harmonica-clubs-public.csv`: student clubs.
- `data/sources/harmonica-score-publications.csv`: competition repertoire and official references.
- `data/sources/harmonica-score-sources.csv`: publication and score purchase leads.
- `data/sources/harmonica-public-calendar-overrides.csv`: event corrections backed by public evidence.
- `data/sources/source-url-aliases.csv`: aliases for existing source URLs.
- `data/sources/source-name-translations.json`: reviewed reference names in four languages, retaining recorded names and sources; these are not claims of official names.
- `data/sources/source-description-translations.json`: source descriptions and tags in four languages. `event-description-translations.json` holds translations of event summaries. Translations are used only when they exactly match the original record. Detail pages, SSR and SEO follow the interface language, and original text can be expanded. Run `scripts/validate_description_translations.py` to check new data for missing translations; browsing does not invoke translation services.
- `data/sources/score-source-media.json`: individually verified book covers, announcement images and original pages. Explicitly run `.venv/bin/python scripts/cache_score_source_images.py` to rebuild local previews; browsing and offline builds do not fetch these images.

A `public_id` does not change when records are sorted or inserted. `country` is the primary country or territory; `region` provides more specific geographic information. Unknown locations do not receive a default country. Follow `.agents/AGENTS.md` when adding sources to obtain official avatars and public bios and validate the output.

### Collection and Apify

Facebook posts, Instagram posts and stories share Harmonica Observatory's own Apify pool. YouTube, websites and RSS/RSSHub continue to use their existing public channels independently of interface changes. Available budgets, per-actor limits and reservations across processes jointly constrain spending. Unconfirmed results retain their reservations; retries must not bypass budget limits.

```bash
# Refresh capacity without running an actor
.venv/bin/python scripts/apify_pool.py --refresh

# Run collection and builds (may consume configured Apify/AI gateway capacity)
.venv/bin/python scripts/run_pipeline.py
```

See the [Apify pool](deploy/apify-pool.md) and [Instagram collection details](deploy/instagram-public-ingestion.md). The local deployment does not require `--publish-pages`; the [legacy Pages workflow](deploy/github-pages.md) remains as a fallback reference.

### AI gateway inference

The default is `HARMONICA_LLM_PROVIDER=gateway`: maintainer jobs (classification, calendar review, directory tags, form submission review) send OpenAI-compatible requests to the local AI gateway (`http://127.0.0.1:8317/v1`) using semantic aliases only — `sky-fast` for classification and `sky-quality` for submission review. The gateway decides the concrete model; the resolved model it reports is stored next to the requested alias. The client key comes from `HARMONICA_LLM_API_KEY` or the Keychain item `harmonica-ai-gateway` / `harmonica`.

- The four-language UI uses static locale files, with no visitor-triggered AI translation costs.
- All jobs share one in-flight request and an hourly budget (`HARMONICA_LLM_MAX_CALLS_PER_HOUR`, default 120); when it is exhausted, cached results are retained.
- `HARMONICA_LLM_PROVIDER=disabled` disables new inference entirely.

Visitors cannot reach gateway keys or an arbitrary inference endpoint.

## Public API

| Path | Purpose |
| --- | --- |
| `/api/v1/health` | Local service health |
| `/api/v1/catalog` | Complete global data snapshot |
| `/api/v1/sources` | Source directory |
| `/api/v1/posts` | Original posts |
| `/api/v1/events` | Events with explicit dates and time zones |
| `/api/v1/scores` | Competition repertoire |
| `/api/v1/community` | Community-authorized capacity and collection frequency estimates |

List APIs support `q`, `country` (for example, `JP` or `KR`), `limit` (1–200) and `offset`. Existing endpoints such as `/api/sources.json`, `latest.json` and `scores.json` remain readable. Public data includes only public information and permitted aggregate status; tokens are never returned.

RSS/ICS feeds remain available under `/feeds/`: `updates.xml`, `events.xml`, `posts-videos.xml`, `sources.xml`, `student-clubs.xml`, `opportunities.xml`, `public-calendar.ics`, `overseas-calendar.ics` and `online-calendar.ics`.

## Validation

```bash
.venv/bin/python -m unittest discover -s tests
npm --prefix web ci --ignore-scripts
npm --prefix web test
.venv/bin/python scripts/validate_public_outputs.py
.venv/bin/python scripts/check_source_coverage.py
.venv/bin/python scripts/validate_legacy_redirects.py
```

Commit only source code, locale files, public source CSV files and deployment documentation. Do not commit `site/api`, generated HTML, collection snapshots, image caches, tokens, SQLite databases, keys or logs.

## Maintainer documentation

- [Interface and interaction specifications](web/CHUMEI_UI_HANDOFF.md): current layout requirements and historical design notes.
- [Layout acceptance](deploy/original-layout-acceptance-2026-09-23.md), [usability evaluation](deploy/heuristic-evaluation-2026-09-23.md) and [multilingual directory and information density](deploy/density-multilingual-acceptance-2026-09-23.md): validation records for individual changes. Test counts describe the versions tested at the time.

## License and acknowledgments

MIT License · Sky Hong.

Public data browsing and Apify capacity contributions draw on the MIT-licensed implementation of [Chumei Observatory](https://github.com/skyhong2002/chumei). Harmonica Observatory manages its own data, authentication and service credentials independently.
