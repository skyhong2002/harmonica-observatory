# Harmonica Observatory - Workspace Rules

Whenever adding a new entry to the public watchlist (`data/sources/harmonica-source-watchlist-public.csv`):

1. **Avatar/Logo Retrieval**:
   - Extract the official profile picture/avatar of the added entry from their social media profiles (Facebook, Instagram, Threads, YouTube, etc.).
   - If direct graph API or CDN URLs are rate-limited or forbidden (e.g., 403), try scraping public pages (such as Threads profile `og:image` tags or unescaped HTML content).
   - Convert the extracted photo to WebP format, name it using the first 20 characters of the SHA-256 hash of the remote URL, and save it in `site/assets/source-avatars/`.
   - For reviewed additions, also track that WebP in `assets/source-avatars-curated/` and record the image and profile URLs in `data/sources/source-profile-overrides.json`. The build copies these portraits into the public site, so a fresh checkout does not depend on private caches.

2. **Custom Description Integration**:
   - Retrieve the self-written bio/description (about section) from the entry's social media pages.
   - Cache this custom description and the WebP avatar path in `data/feeds/source_profiles.json` under keys matching the entry's platforms (e.g. `ig_username`, `threads_username`, `fb_page_id`).
   - Add the custom description under the computed fingerprints in `state/source_llm_tags.json` as `sourceSummary` so it overrides the default template description on the landing page.
   - Keep the reviewed English summary, evidence and any short original-bio excerpt in the profile override manifest, with matching four-language name/description records. Distinguish editorial summaries from self-written bios; do not invent a quotation or full-time employment claim.
   - Verify YouTube account identity before recording `youtubeChannelId` and `youtubeUrl`; official Atom feeds are preferred when this reviewed identity still matches the registry. Distinguish upload dates, other activity dates and advertised future events.

3. **Festival and Venue Lineups**:
   - When harmonica appears only on a festival's or venue's per-show detail pages, add an entry keyed by `public_id` to `data/sources/source-program-crawls.json` (`index_urls`, a `follow_links` regex for detail links, optional `interval_hours`/`max_pages`). The crawler emits only detail pages that mention harmonica, so do not also register the organizer's general social accounts; they would spend collection budget on unrelated posts.
   - Year-specific lineup URLs must be updated when the next edition's site goes live.

4. **Build & Validation**:
   - Use `.venv/bin/python scripts/build_local.py` to rebuild already collected snapshots without paid collection, inference or calendar writes. Avoid simultaneous scheduled builds by acquiring the pipeline lock; use the full ingestion pipeline only when new collection is needed.
   - Run verification scripts (`validate_public_outputs.py`, `check_source_coverage.py`, `validate_legacy_redirects.py`) to ensure no build errors.
   - Run `validate_description_translations.py` and `validate_sitemap_seo.py`, and verify the new entry pages and images over HTTP.

5. **Deployment**:
   - Commit and push source files to the `main` branch.
   - Production uses the local Python service described in `deploy/local-hosting.md`; `gh-pages` is a historical snapshot and is not the current deployment target.
   - Rebuild local outputs, restart `tw.observe.harmonica.web` after Python changes, and verify `https://harmonica.observe.tw/` source pages, images and API. Preserve unrelated worktree changes when staging.
