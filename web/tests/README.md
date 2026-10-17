# Frontend verification

From the repository root:

```sh
npm --prefix web ci --ignore-scripts
npm --prefix web test
```

The application itself has no Node runtime or bundling dependency. `jsdom` is a
pinned development dependency used only for DOM integration tests.

- `catalog_contract.test.mjs` reads the real local public snapshots through
  `scripts/global_catalog.py` (requires `python3`) and checks all four locales,
  original text and links, archive state, event time zones and accounting views.
- `app_dom.test.mjs` runs the actual application modules against jsdom and fully
  mocked API responses. It covers language and history routing, source metadata,
  IME input, search, country and follow filters, contribution/submission forms,
  withdrawal cancellation/errors/success, and delayed refresh preserving drafts
  and focus. No provider tokens, network requests, paid actors, or community
  database writes occur. The only jsdom platform adapters are scrolling and
  dialog open/close, which have no native layout/top-layer implementation there.

- `river.test.mjs` checks independent column facets, storage, IME, add/remove,
  wheel/touch axis handling and scroll restoration after re-rendering.
- `shell.test.mjs` checks four-language navigation, light/dark/system appearance,
  legacy preferences and delayed cross-page search focus.
- `views.test.mjs` checks real-count sorting, complete original text expansion,
  avatar fallback and explicitly linked events.

These tests do not validate CSS layout or a browser's native dialog rendering.
Use the separately authorized browser acceptance workflow for those checks.

`stories.test.mjs` also checks that empty story surfaces explain paused and
budget-deferred collection in all four languages, and update that explanation
after a snapshot refresh. `views.test.mjs` distinguishes build timestamps from
successful source checks and keeps paused status visible at zero coverage.

Run Python fixtures with `.venv/bin/python tests/run_offline.py`. The offline CI
workflow uses this guarded runner and the same frontend tests, without ingestion,
inference, credentials, calendar synchronization or deployment.
