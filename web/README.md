# Frontend

The interface at https://harmonica.observe.tw/ is a single page served from
`web/index.html` by `scripts/serve.py`. `scripts/render_shell.py` fills in the
title, description, canonical and hreflang links and a plain-HTML summary of the
page for crawlers; `web/assets/app.js` then renders the page in the browser.
There is no build step and no runtime Node dependency.

The redesigned interface (PR #35, #36) is the only UI. The earlier "restore the
original layout" and Chumei migration notes are retired; they remain in Git
history (`web/CHUMEI_UI_HANDOFF.md` at commit `b6f6797`) and the deployment
rollback tag.

## Layout

- Top navigation on every page: Home, Updates, Events, Sources, Scores and
  More. More groups participation and feeds, language and appearance
  (light, dark, system), and status, about and privacy.
- Home: intro and counts; active stories (`catalog.stories` only, never
  expired posts) beside the next upcoming events; the public Google Calendar
  embed; then the latest posts.
- Four interface languages (zh-Hant, en, ja, ko). The interface language and
  the country filter are independent, and original text, links and event time
  zones are kept.

## Modules

| File | Role |
|---|---|
| `app.js` | Routing, catalog loading, rendering and page-level events |
| `shell.js` | Header, navigation, More menu, footer, appearance |
| `home.js`, `stories.js`, `google-calendar.js` | Home page sections |
| `timeline.js`, `river.js` | Post feed on Home and `/post/` |
| `views.js`, `directory-columns.js`, `source-names.js` | Source directory, source pages, post and event cards |
| `events.js`, `event-localization.js` | `/events/` |
| `scores.js` | `/scores/` and `/scores/sources/` |
| `community.js`, `reporting.js` | Session, Google sign-in, Apify contributions, source submissions |
| `i18n.js`, `utils.js`, `page-notes.js` | Strings in four languages and shared helpers |

## Styles

Two stylesheets, loaded in this order:

1. `base.css`: design tokens (light and dark), base elements, components,
   header and navigation, and shared type and contrast fixes.
2. `interface.css`: the interface layer. Every rule is scoped under `:root`,
   so it wins over `base.css` at the same selector without `!important`.

Change a component where its final rule lives; search both files for the
selector first. Keep navigation, labels and footer text at 0.8125rem (13px) or
larger.

## Catalog loading

- `index.html` preloads `/api/v1/catalog`; `load()` in `app.js` makes the same
  request, so the browser reuses that download.
- The home page refreshes stories from the catalog at most every five minutes
  (polling, tab return or navigating back home). Expired stories leave the
  strip locally without a request.
- Refreshes use `cache: "no-cache"`, so they become conditional requests as
  soon as the API sends an `ETag`.

## Verification

- Unit and DOM tests: see [tests/README.md](tests/README.md).
- Screenshots and design review: [docs/design-review](../docs/design-review/)
  has the state list, the frozen-catalog preview server and the capture script.
