# Instagram monitoring

Instagram profile and story sources use Instaloader. The installed
`tw.observe.harmonica.social-fast` LaunchAgent runs the social watcher, and
`scripts/build_status_page.py` reports Instagram errors, throttling, and login
backoff separately from RSSHub service health.

The legacy `tw.observe.harmonica.rsshub-ig-probe` LaunchAgent was retired on
2026-09-12. It requested `/instagram/2/user/ntubluesound` from local RSSHub every
hour, even after all Instagram sources had migrated to Instaloader. RSSHub
returned 503 because its upstream Instagram GraphQL request returned 401.
This check no longer represented the configured Instagram provider.

The installed plist was backed up under
`~/Library/Application Support/Harmonica-in-Taiwan/retired-launchagents/`, unloaded
with `launchctl bootout`, and removed from `~/Library/LaunchAgents/` so login
does not restart it. Existing logs remain in
`~/Library/Logs/Harmonica-in-Taiwan/rsshub-ig-probe*.log`.

Do not reinstall this obsolete probe or use RSSHub's root HTTP 200 response as
evidence that Instagram fetching works. Check the Instagram component of
`site/api/status.json` and the current social watcher state for actual provider
errors; retiring this job does not resolve Instaloader authentication or rate
limits.
