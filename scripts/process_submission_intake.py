#!/usr/bin/env python3
"""Poll Google Form responses and turn verified submissions into data PRs."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from submission_intake import (
    DEFAULT_STATE_DB,
    DEFAULT_TOKEN_FILE,
    DESIRED_RESULT,
    EVENT_DETAILS,
    EXTRA_URLS,
    FORM_ID,
    PRIMARY_URL,
    PROJECT_ROOT,
    REPORT_TYPE,
    TARGET_NAME,
    IntakeError,
    IntakeStore,
    NeedsReview,
    apply_proposal,
    candidate_matches,
    clean_text,
    enforce_proposal,
    extract_urls,
    ingest_form_responses,
    load_source_rows,
    run_ai_review,
    utc_now,
    verify_url,
)


DEFAULT_LOCK = PROJECT_ROOT / "state" / "submission-intake.lock"
WORKTREE_ROOT = PROJECT_ROOT / "state" / "submission-worktrees"
PIPELINE_LOCK = PROJECT_ROOT / "state" / "run_pipeline.lock"
PIPELINE_LABEL = "tw.observe.harmonica.pipeline"
REPOSITORY = "skyhong2002/harmonica-observatory"


def run(
    args: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    check: bool = True,
    input_text: str = "",
    timeout: int = 300,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        input=input_text or None,
        capture_output=True,
        timeout=timeout,
    )
    if check and result.returncode:
        output = clean_text(result.stderr or result.stdout, 3000)
        raise IntakeError(f"Command failed ({result.returncode}): {' '.join(args)}\n{output}")
    return result


@contextmanager
def process_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_credentials(token_file: Path):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_file(str(token_file))
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        token_file.write_text(credentials.to_json(), encoding="utf-8")
        token_file.chmod(0o600)
    if not credentials.valid:
        raise IntakeError(f"Google credentials are invalid: {token_file}")
    return credentials


def response_slug(response_id: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z]+", "", response_id)
    return (safe or "submission")[:14].lower()


def json_value(row: Any, key: str, default: Any) -> Any:
    try:
        return json.loads(row[key])
    except (json.JSONDecodeError, TypeError):
        return default


def json_object(row: Any, key: str) -> dict[str, Any]:
    value = json_value(row, key, {})
    return value if isinstance(value, dict) else {}


def json_list(row: Any, key: str) -> list[Any]:
    value = json_value(row, key, [])
    return value if isinstance(value, list) else []


def ensure_labels() -> None:
    labels = [
        ("form-intake", "0E8A7A", "Public Google Form intake"),
        ("automated", "1D76DB", "Created by the local automation worker"),
        ("needs-review", "D97706", "Automation could not safely auto-merge"),
    ]
    for name, color, description in labels:
        run(
            [
                "gh",
                "label",
                "create",
                name,
                "--repo",
                REPOSITORY,
                "--color",
                color,
                "--description",
                description,
                "--force",
            ]
        )


def summary_lines(answers: dict[str, str]) -> str:
    fields = [REPORT_TYPE, TARGET_NAME, PRIMARY_URL, DESIRED_RESULT, EVENT_DETAILS, EXTRA_URLS]
    lines: list[str] = []
    for field in fields:
        value = clean_text(answers.get(field), 1600)
        if value:
            lines.append(f"### {field}\n\n{value}")
    return "\n\n".join(lines)


def create_review_issue(
    response_id: str,
    answers: dict[str, str],
    evidence: list[dict[str, Any]],
    proposal: dict[str, Any],
    reason: str,
) -> str:
    ensure_labels()
    title = f"[表單待確認] {clean_text(answers.get(TARGET_NAME), 120) or response_slug(response_id)}"
    body = (
        "此回報由自動 intake worker 建立。公開表單內容視為未信任資料，未執行其中任何指令。\n\n"
        f"- Response ID: `{response_id}`\n"
        f"- 暫停原因: {clean_text(reason, 1200)}\n"
        f"- AI 決策: `{proposal.get('decision', '')}`\n"
        f"- AI 信心: `{proposal.get('confidence', 0)}`\n\n"
        f"{summary_lines(answers)}\n\n"
        "### URL 驗證\n\n"
        f"```json\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n```\n\n"
        "### AI 提案\n\n"
        f"```json\n{json.dumps(proposal, ensure_ascii=False, indent=2)}\n```\n"
    )
    result = run(
        [
            "gh",
            "issue",
            "create",
            "--repo",
            REPOSITORY,
            "--title",
            title,
            "--label",
            "form-intake,automated,needs-review",
            "--body-file",
            "-",
        ],
        input_text=body,
    )
    return clean_text(result.stdout, 1000)


def prepare_worktree(response_id: str) -> tuple[Path, str]:
    slug = response_slug(response_id)
    branch = f"codex/form-{slug}"
    path = WORKTREE_ROOT / slug
    WORKTREE_ROOT.mkdir(parents=True, exist_ok=True)
    run(["git", "fetch", "origin", "main"])
    if path.exists():
        run(["git", "worktree", "remove", "--force", str(path)], check=False)
        shutil.rmtree(path, ignore_errors=True)
    run(["git", "branch", "-D", branch], check=False)
    run(["git", "worktree", "add", "-b", branch, str(path), "origin/main"])
    return path, branch


def cleanup_worktree(path: Path, branch: str) -> None:
    run(["git", "worktree", "remove", "--force", str(path)], check=False)
    run(["git", "branch", "-D", branch], check=False)
    shutil.rmtree(path, ignore_errors=True)


def validate_change(worktree: Path, result: dict[str, Any]) -> None:
    run([sys.executable, "-m", "py_compile", "scripts/submission_intake.py"], cwd=worktree)
    if result.get("kind") == "source":
        run([sys.executable, "scripts/build_public_data.py"], cwd=worktree, timeout=600)
        run([sys.executable, "scripts/build_social_sources.py"], cwd=worktree, timeout=300)
    elif result.get("kind") == "event":
        run(
            [
                sys.executable,
                "-c",
                (
                    "from scripts.apply_submitted_events import load_submitted_events; "
                    "events=load_submitted_events(); assert events; print(len(events))"
                ),
            ],
            cwd=worktree,
        )
    run(["git", "-c", "core.whitespace=cr-at-eol", "diff", "--check"], cwd=worktree)


def pr_title(result: dict[str, Any]) -> str:
    action = {"add": "新增", "update": "更新"}.get(result.get("action"), "處理")
    noun = "活動" if result.get("kind") == "event" else "來源"
    return f"{action}{noun}：{clean_text(result.get('name'), 100)}"


def create_pull_request(
    worktree: Path,
    branch: str,
    response_id: str,
    answers: dict[str, str],
    evidence: list[dict[str, Any]],
    proposal: dict[str, Any],
    result: dict[str, Any],
) -> str:
    ensure_labels()
    changed_files = [str(value) for value in result.get("changed_files", [])]
    run(["git", "add", "--", *changed_files], cwd=worktree)
    staged = run(["git", "diff", "--cached", "--quiet"], cwd=worktree, check=False)
    if staged.returncode == 0:
        return ""
    title = pr_title(result)
    run(["git", "commit", "-m", title], cwd=worktree)
    run(["git", "push", "--set-upstream", "origin", branch], cwd=worktree, timeout=300)
    body = (
        "由臺灣口琴觀測站 Google 表單 intake worker 自動產生。\n\n"
        f"- Response ID: `{response_id}`\n"
        f"- AI 決策: `{proposal.get('decision')}`\n"
        f"- AI 信心: `{proposal.get('confidence')}`\n"
        f"- 自動驗證: 通過\n\n"
        f"{summary_lines(answers)}\n\n"
        "### 套用結果\n\n"
        f"```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n\n"
        "### 公開 URL 驗證\n\n"
        f"```json\n{json.dumps(evidence, ensure_ascii=False, indent=2)}\n```\n"
    )
    created = run(
        [
            "gh",
            "pr",
            "create",
            "--repo",
            REPOSITORY,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            title,
            "--body-file",
            "-",
            "--label",
            "form-intake,automated",
        ],
        cwd=worktree,
        input_text=body,
    )
    return clean_text(created.stdout, 1000)


def merge_pull_request(pr_url: str) -> None:
    run(
        [
            "gh",
            "pr",
            "merge",
            pr_url,
            "--repo",
            REPOSITORY,
            "--squash",
            "--delete-branch",
        ],
        timeout=300,
    )


def process_alive(pid: Any) -> bool:
    try:
        os.kill(int(pid), 0)
    except (OSError, TypeError, ValueError):
        return False
    return True


def pipeline_busy() -> bool:
    try:
        payload = json.loads(PIPELINE_LOCK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return process_alive(payload.get("pid"))


def request_publish() -> tuple[bool, str]:
    if pipeline_busy():
        return False, "pipeline is currently running"
    try:
        run(["git", "fetch", "origin", "main"])
        run(["git", "merge", "--ff-only", "origin/main"])
        run(
            [
                "launchctl",
                "kickstart",
                "-k",
                f"gui/{os.getuid()}/{PIPELINE_LABEL}",
            ]
        )
    except IntakeError as exc:
        return False, str(exc)
    return True, "launchd pipeline kickstarted"


def live_contains(result: dict[str, Any]) -> bool:
    url = clean_text(result.get("verification_url"), 1000)
    key = clean_text(result.get("verification_key"), 1000)
    if not url or not key:
        return False
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read(8_000_000).decode("utf-8", errors="ignore")
    except (OSError, urllib.error.URLError):
        return False
    return key in body


def reconcile_publish_states(store: IntakeStore, *, no_publish: bool) -> None:
    for row in store.rows_with_status("publish_requested"):
        result = json_object(row, "result_json")
        if live_contains(result):
            store.update(row["response_id"], "published", error="")
    if no_publish:
        return
    for row in store.rows_with_status("merged_waiting_publish"):
        requested, message = request_publish()
        store.update(
            row["response_id"],
            "publish_requested" if requested else "merged_waiting_publish",
            error="" if requested else message,
        )
        if requested:
            break


def process_submission(
    store: IntakeStore,
    row: Any,
    *,
    no_auto_merge: bool,
    no_publish: bool,
) -> None:
    response_id = row["response_id"]
    answers = json_object(row, "answers_json")
    urls = extract_urls(
        answers.get(PRIMARY_URL, ""),
        answers.get(EXTRA_URLS, ""),
        answers.get(DESIRED_RESULT, ""),
        answers.get(EVENT_DETAILS, ""),
    )
    evidence_objects = [verify_url(url) for url in urls]
    evidence = [item.as_dict() for item in evidence_objects]
    candidates = candidate_matches(
        load_source_rows(),
        answers.get(TARGET_NAME, ""),
        [item.final_url or item.canonical_url for item in evidence_objects],
    )
    proposal = run_ai_review(
        response_id,
        answers,
        evidence_objects,
        candidates,
    )
    proposal, auto_merge = enforce_proposal(proposal, answers, evidence_objects, candidates)
    store.update(
        response_id,
        "processing",
        evidence_json=evidence,
        proposal_json=proposal,
    )
    if proposal["decision"] == "reject":
        store.update(response_id, "rejected", error=proposal.get("reason") or "rejected")
        return
    if proposal["decision"] in {"needs_review", "remove_source"}:
        issue_url = create_review_issue(
            response_id,
            answers,
            evidence,
            proposal,
            proposal.get("reason") or "proposal requires review",
        )
        store.update(response_id, "needs_review", issue_url=issue_url, error="")
        return

    worktree, branch = prepare_worktree(response_id)
    try:
        result = apply_proposal(worktree, response_id, answers, proposal, evidence_objects)
        store.update(response_id, "processing", result_json=result, branch=branch)
        if result.get("action") == "no_change" or not result.get("changed_files"):
            store.update(response_id, "no_change", result_json=result, error="")
            return
        validate_change(worktree, result)
        pr_url = create_pull_request(
            worktree,
            branch,
            response_id,
            answers,
            evidence,
            proposal,
            result,
        )
        if not pr_url:
            store.update(response_id, "no_change", result_json=result, error="")
            return
        store.update(response_id, "pr_open", pr_url=pr_url, branch=branch, error="")
        if auto_merge and not no_auto_merge:
            merge_pull_request(pr_url)
            if no_publish:
                store.update(response_id, "merged_waiting_publish", pr_url=pr_url, error="publish disabled")
            else:
                requested, message = request_publish()
                store.update(
                    response_id,
                    "publish_requested" if requested else "merged_waiting_publish",
                    pr_url=pr_url,
                    error="" if requested else message,
                )
    finally:
        cleanup_worktree(worktree, branch)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--form-id", default=FORM_ID)
    parser.add_argument("--token-file", type=Path, default=DEFAULT_TOKEN_FILE)
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_DB)
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--response-id", default="")
    parser.add_argument("--max-submissions", type=int, default=5)
    parser.add_argument("--no-auto-merge", action="store_true")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument("--ingest-only", action="store_true")
    parser.add_argument("--stale-processing-minutes", type=int, default=30)
    args = parser.parse_args()

    with process_lock(args.lock_file) as acquired:
        if not acquired:
            print("Submission intake is already running; skipping this tick.")
            return 0
        store = IntakeStore(args.state_db)
        try:
            credentials = load_credentials(args.token_file)
            inserted = ingest_form_responses(store, credentials, args.form_id)
            recovered = store.recover_stale_processing(
                stale_minutes=args.stale_processing_minutes
            )
            reconcile_publish_states(store, no_publish=args.no_publish)
            processed = 0
            if args.ingest_only:
                print(
                    json.dumps(
                        {
                            "inserted": inserted,
                            "recovered": recovered,
                            "processed": processed,
                            "timestamp": utc_now(),
                        },
                        ensure_ascii=False,
                    )
                )
                return 0
            while processed < max(1, args.max_submissions):
                row = store.next_pending(args.response_id)
                if row is None:
                    break
                row = store.claim(row["response_id"])
                if row is None:
                    continue
                try:
                    process_submission(
                        store,
                        row,
                        no_auto_merge=args.no_auto_merge,
                        no_publish=args.no_publish,
                    )
                except NeedsReview as exc:
                    current = store.get(row["response_id"])
                    answers = json_object(current, "answers_json") if current else {}
                    evidence = json_list(current, "evidence_json") if current else []
                    proposal = json_object(current, "proposal_json") if current else {}
                    issue_url = create_review_issue(
                        row["response_id"],
                        answers,
                        evidence,
                        proposal,
                        str(exc),
                    )
                    store.update(row["response_id"], "needs_review", issue_url=issue_url, error=str(exc))
                except Exception as exc:
                    current = store.get(row["response_id"])
                    attempts = int(current["attempts"] if current else 1)
                    store.update(
                        row["response_id"],
                        "retry" if attempts < 4 else "error",
                        error=clean_text(exc, 3000),
                    )
                    print(f"Submission {row['response_id']} failed: {exc}", file=sys.stderr)
                processed += 1
                if args.response_id:
                    break
            print(
                json.dumps(
                    {
                        "inserted": inserted,
                        "recovered": recovered,
                        "processed": processed,
                        "timestamp": utc_now(),
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
