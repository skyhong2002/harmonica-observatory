"""Avoid filesystem churn when generated UTF-8 output has not changed."""

from pathlib import Path


def write_text_if_changed(path: Path, text: str, *, temp_path: Path | None = None) -> bool:
    """Write exact UTF-8 bytes only when different; return whether a write occurred.

    Callers retain responsibility for creating parent directories. Supplying the
    existing temporary path preserves a caller's atomic replace behavior.
    """
    content = text.encode("utf-8")
    try:
        if path.read_bytes() == content:
            return False
    except FileNotFoundError:
        pass
    if temp_path is None:
        path.write_bytes(content)
    else:
        temp_path.write_bytes(content)
        temp_path.replace(path)
    return True
