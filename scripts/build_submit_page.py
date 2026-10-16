#!/usr/bin/env python3
"""Build the public /submit/ page from its checked-in template."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path

from output_files import write_text_if_changed


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.configure_submission_form import FORM_TITLE, RESPONDER_URI
import site_chrome


TEMPLATE_PATH = PROJECT_ROOT / "templates" / "submit.html"
OUTPUT_PATH = PROJECT_ROOT / "site" / "submit" / "index.html"
PUBLIC_CONFIG_PATH = PROJECT_ROOT / "data" / "submission-form-public.json"


def render_submit_page() -> str:
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    public_config = json.loads(PUBLIC_CONFIG_PATH.read_text(encoding="utf-8"))
    if public_config.get("responderUri") != RESPONDER_URI:
        raise ValueError("Submission form responder URI differs from public configuration")
    rendered = template.replace("__GOOGLE_FORM_URL__", RESPONDER_URI)
    rendered = rendered.replace("__GOOGLE_FORM_TITLE__", FORM_TITLE)
    rendered = rendered.replace("__ASSET_VERSION__", site_chrome.ASSET_VERSION)
    rendered = rendered.replace("__SITE_HEADER__", site_chrome.render_header())
    rendered = rendered.replace(
        "__GOOGLE_FORM_PUBLIC_CONFIG__",
        html.escape(json.dumps(public_config, ensure_ascii=False), quote=False),
    )
    if "__GOOGLE_FORM_" in rendered or "__ASSET_VERSION__" in rendered or "__SITE_HEADER__" in rendered:
        raise ValueError("Unresolved placeholder in submit template")
    return rendered


def main() -> int:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_text_if_changed(OUTPUT_PATH, render_submit_page())
    print(f"Built {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
