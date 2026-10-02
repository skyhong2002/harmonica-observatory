"""Operator-only JSON inference; never reachable from the public HTTP API.

Default: the sky-mini AI gateway (OpenAI-compatible HTTP) with semantic model
aliases, so the gateway policy decides the concrete model. Existing content
caches remain authoritative, and every request is bounded by a shared hourly
call ledger.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GATEWAY_BASE_URL = 'http://127.0.0.1:8317/v1'
# Gateway aliases, never concrete upstream models (see ~/Projects/ai-gateway).
CLASSIFIER_MODEL = 'sky-fast'
REVIEW_MODEL = 'sky-quality'
DEFAULT_KEYCHAIN_SERVICE = 'harmonica-ai-gateway'
DEFAULT_KEYCHAIN_ACCOUNT = 'harmonica'
HTTP_PROVIDERS = ('gateway', 'openai')
SAMPLING_PARAMETERS = ('temperature', 'top_p', 'top_logprobs', 'logprobs')


def provider() -> str:
    """gateway (default) | openai (any other OpenAI-compatible endpoint) | disabled."""
    value = os.environ.get('HARMONICA_LLM_PROVIDER', 'gateway').strip().lower()
    if value not in (*HTTP_PROVIDERS, 'disabled'):
        raise ValueError('HARMONICA_LLM_PROVIDER must be gateway, openai, or disabled')
    return value


def uses_http() -> bool:
    return provider() in HTTP_PROVIDERS


def base_url() -> str:
    return os.environ.get('HARMONICA_LLM_BASE_URL', '').strip() or DEFAULT_GATEWAY_BASE_URL


def model_name() -> str:
    """Classifier model: an explicit override or the fast gateway alias."""
    return os.environ.get('HARMONICA_LLM_MODEL', '').strip() or CLASSIFIER_MODEL


def review_model_name() -> str:
    """Submission review asks for the quality gateway alias."""
    return os.environ.get('HARMONICA_INTAKE_AI_MODEL', '').strip() or REVIEW_MODEL


def compatible_chat_body(body: dict) -> dict:
    """Apply the configured request capabilities without mutating the caller.

    Aliases can resolve to reasoning models that reject sampling parameters, so
    they are omitted unless HARMONICA_LLM_SEND_SAMPLING=1 says the configured
    endpoint/model accepts them. Model names are never inspected.
    """
    result = dict(body)
    if os.environ.get('HARMONICA_LLM_SEND_SAMPLING', '').strip().lower() not in ('1', 'true', 'yes', 'on'):
        for name in SAMPLING_PARAMETERS:
            result.pop(name, None)
    return result


def resolved_model(response: dict, requested_model: str) -> str:
    """Use provider response provenance; never relabel old cache entries."""
    actual = response.get("model")
    if isinstance(actual, str) and actual.strip():
        return actual.strip()
    return requested_model


def runtime_metadata(requested_model: str, base_url: str) -> dict:
    selected = provider()
    if selected == 'disabled':
        return {"provider": selected, "model": "", "base_url": ""}
    return {"provider": selected, "model": requested_model, "base_url": base_url}


def retry_policy(requested_model: str) -> tuple[int, list[str]]:
    if not uses_http():
        return 1, [requested_model]
    attempts = max(1, int(os.environ.get("HARMONICA_LLM_RETRIES", "3") or "3"))
    fallback = [item.strip() for item in os.environ.get("HARMONICA_LLM_FALLBACK_MODELS", "").split(",") if item.strip()]
    return attempts, list(dict.fromkeys([requested_model, *fallback]))


def read_token(service: str = '', account: str = '') -> tuple[str, str]:
    """Return (token, source) for the HTTP provider."""
    selected = provider()
    if selected == "disabled":
        return "", "disabled"
    for key in ("HARMONICA_LLM_API_KEY", "HARMONICA_OPENAI_API_KEY", "OPENAI_API_KEY"):
        value = os.environ.get(key)
        if value:
            return value.strip(), f"env:{key}"
    candidates = [
        (service, account),
        (service, DEFAULT_KEYCHAIN_ACCOUNT),
        (DEFAULT_KEYCHAIN_SERVICE, DEFAULT_KEYCHAIN_ACCOUNT),
    ]
    seen_pairs: set[tuple[str, str]] = set()
    for keychain_service, keychain_account in candidates:
        if not keychain_service or not keychain_account or (keychain_service, keychain_account) in seen_pairs:
            continue
        seen_pairs.add((keychain_service, keychain_account))
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", keychain_service, "-a", keychain_account, "-w"],
                capture_output=True, text=True, timeout=10, check=False,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), f"keychain:{keychain_service}/{keychain_account}"
    return "", ""


def _state_dir(name: str = 'llm') -> Path:
    path = Path(os.environ.get('HARMONICA_STATE_DIR', str(ROOT / 'state'))) / name
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_status(path: Path, value: dict) -> None:
    target = path.with_suffix('.tmp')
    target.write_text(json.dumps(value, sort_keys=True) + '\n', encoding='utf-8')
    target.chmod(0o600)
    target.replace(path)


def _reserve_call(status_path: Path, limit: int, label: str) -> dict:
    """Count one call in the hourly ledger; caller must hold the ledger lock."""
    try:
        status = json.loads(status_path.read_text())
    except FileNotFoundError:
        status = {}
    except (OSError, ValueError):
        raise RuntimeError(f'{label} usage ledger is unreadable; inference paused') from None
    if not isinstance(status, dict) or not isinstance(status.get('calls', 0), int) or status.get('calls', 0) < 0:
        raise RuntimeError(f'{label} usage ledger is invalid; inference paused')
    hour = int(time.time() // 3600)
    calls = int(status.get('calls', 0)) if status.get('hour') == hour else 0
    if calls >= limit:
        status.update(status='paused', pauseReason='hourly_limit', hour=hour, calls=calls,
                      limit=limit, lastSkippedAt=time.time())
        _write_status(status_path, status)
        raise RuntimeError(f'Configured {label} hourly call limit reached; reuse cached data')
    status = {'hour': hour, 'calls': calls + 1, 'limit': limit, 'lastStartedAt': time.time(), 'status': 'running'}
    _write_status(status_path, status)
    return status


@contextmanager
def _http_slot() -> Iterator[None]:
    """One in-flight HTTP request across all Harmonica jobs, within an hourly budget.

    Waits (bounded) for the slot, because gateway calls are short and pipeline, social-fast and intake legitimately overlap.
    """
    limit = max(0, min(10000, int(os.environ.get('HARMONICA_LLM_MAX_CALLS_PER_HOUR', '120'))))
    wait = max(0.0, float(os.environ.get('HARMONICA_LLM_LOCK_WAIT', '120')))
    state = _state_dir('llm')
    with (state / 'inference.lock').open('a+') as lock:
        deadline = time.monotonic() + wait
        while True:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError('LLM gateway slot is busy; reuse cached data') from None
                time.sleep(0.5)
        status_path = state / 'usage.json'
        status = _reserve_call(status_path, limit, 'LLM gateway')
        try:
            yield
        except BaseException as exc:
            status.update(status='error', lastFinishedAt=time.time(), errorType=type(exc).__name__)
            _write_status(status_path, status)
            raise
        status.update(status='ok', lastFinishedAt=time.time())
        _write_status(status_path, status)


def http_chat(url: str, token: str, body: dict, timeout: int) -> str:
    """POST a Chat Completions request through curl and return the raw body."""
    if not token:
        raise RuntimeError("HTTP LLM mode requires an API key")
    body = compatible_chat_body(body)
    body_path = ""
    with _http_slot():
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
                json.dump(body, handle, ensure_ascii=False)
                body_path = handle.name
            config = "\n".join(
                [
                    f'url = "{url}"',
                    'request = "POST"',
                    f"max-time = {max(1, int(timeout or 1))}",
                    "silent",
                    "show-error",
                    "fail-with-body",
                    f'header = "Authorization: Bearer {token}"',
                    'header = "Content-Type: application/json"',
                    'header = "Accept: application/json"',
                    'header = "User-Agent: HarmonicaObserveLLMTagger/1.0"',
                    f'data-binary = "@{body_path}"',
                    "",
                ]
            )
            result = subprocess.run(
                ["curl", "--config", "-"],
                input=config,
                capture_output=True,
                text=True,
                timeout=max(2, int(timeout or 1) + 5),
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(f"LLM curl timed out after {timeout}s") from exc
        finally:
            if body_path:
                try:
                    Path(body_path).unlink()
                except OSError:
                    pass
        if result.returncode != 0:
            detail = (result.stdout or result.stderr or "").strip()[:500]
            raise RuntimeError(f"LLM curl exited {result.returncode}: {detail}")
    return result.stdout


def chat_endpoint(url: str) -> str:
    base = (url or base_url()).rstrip("/")
    return base if base.endswith("/chat/completions") else f"{base}/chat/completions"


def chat(body: dict, *, token: str, url: str = '', timeout: int = 180) -> str:
    """Dispatch one JSON chat request to the selected provider; returns a chat envelope."""
    selected = provider()
    if selected == "disabled":
        raise RuntimeError("LLM inference is disabled")
    return http_chat(chat_endpoint(url), token, body, timeout)
