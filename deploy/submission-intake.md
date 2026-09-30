# Google Form Submission Intake

`https://harmonica.observe.tw/submit/` embeds the public Google Form. The local
worker polls the Forms Responses API every five minutes; the form is not linked
to a Google Sheet.

## Processing Flow

1. `process_submission_intake.py` stores each new Forms response in
   `state/submission-intake.sqlite` with a stable Google `response_id`.
2. Submitted URLs are canonicalized, checked for public DNS addresses, and
   fetched with bounded redirects and response sizes.
3. Existing source names and canonical URLs are compared deterministically for
   duplicate candidates.
4. Codex reviews only the untrusted JSON payload through the same read-only,
   no-tools `llm_backend.codex_chat` path (and `HARMONICA_CODEX_MODEL`) as the
   pipeline classifier, sharing its hourly limit. There is no paid-API fallback.
5. Deterministic Python applies the proposed source or event change in a clean
   worktree, validates generated data, and opens a labeled pull request.
6. A high-confidence add or update with no risk flags is squash-merged and the
   existing `tw.observe.harmonica.pipeline` publisher is started.
7. Removal, conflicting URLs, ambiguous duplicates, unreachable evidence, and
   low-confidence results create a `needs-review` issue instead of changing
   public data.

Form text is always treated as untrusted data. It is never executed as a prompt,
shell command, repository path, or GitHub argument.

## State Values

- `pending`, `retry`: eligible for processing.
- `processing`: currently claimed by one worker attempt.
- `needs_review`, `rejected`, `error`, `no_change`: terminal without publishing.
- `pr_open`: PR created but auto-merge was disabled for an operator test.
- `merged_waiting_publish`, `publish_requested`, `published`: merged and moving
  through the site publisher.

A processing attempt that is interrupted for more than 30 minutes is returned
to `retry`. At most four AI/processing attempts are made per response.

## Manual Commands

Create the dedicated system-Python environment used by launchd. Keeping this
worker off the Homebrew Python executable avoids launchd code-signing failures
when Homebrew replaces that executable during an upgrade:

```bash
/usr/bin/python3 -m venv ~/.hermes/harmonica-intake-venv
uv pip install --python ~/.hermes/harmonica-intake-venv/bin/python \
  google-api-python-client google-auth-oauthlib requests
```

Fetch responses without AI, GitHub, or publishing side effects:

```bash
~/.hermes/harmonica-intake-venv/bin/python \
  scripts/process_submission_intake.py --ingest-only
```

Process at most one response but leave its PR unmerged and do not publish:

```bash
~/.hermes/harmonica-intake-venv/bin/python \
  scripts/process_submission_intake.py --max-submissions 1 --no-auto-merge --no-publish
```

Inspect recent state without printing OAuth credentials:

```bash
sqlite3 -header -column state/submission-intake.sqlite \
  'select response_id, status, attempts, pr_url, issue_url, error, updated_at from submissions order by created_at desc limit 20;'
```

Retry a corrected operational failure:

```bash
sqlite3 state/submission-intake.sqlite \
  "update submissions set status='retry', error='' where response_id='<response_id>' and status='error';"
launchctl kickstart -k gui/$(id -u)/tw.observe.harmonica.submission-intake
```

## LaunchAgent

Validate and install:

```bash
plutil -lint deploy/tw.observe.harmonica.submission-intake.plist
mkdir -p ~/Library/Logs/Harmonica-in-Taiwan
cp deploy/tw.observe.harmonica.submission-intake.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/tw.observe.harmonica.submission-intake 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/tw.observe.harmonica.submission-intake.plist
launchctl kickstart -k gui/$(id -u)/tw.observe.harmonica.submission-intake
```

Runtime checks:

```bash
launchctl print gui/$(id -u)/tw.observe.harmonica.submission-intake
tail -n 100 ~/Library/Logs/Harmonica-in-Taiwan/submission-intake.log
tail -n 100 ~/Library/Logs/Harmonica-in-Taiwan/submission-intake.err.log
```

The OAuth token stays outside the repository at
`~/.hermes/profiles/bamboo/harmonica-observe-google-token.json` with mode `0600`.
