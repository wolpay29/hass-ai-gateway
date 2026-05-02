"""Tiny i18n helper.

Loads core/strings_<LANGUAGE>.yaml once and exposes t(key, **kwargs).
Falls back to German if the requested file is missing or a key is absent.
"""
from pathlib import Path

import yaml

from core.config import LANGUAGE

_data: dict = {}
_fallback: dict = {}


def _load() -> dict:
    global _data, _fallback
    if not _data:
        base = Path(__file__).parent
        target = base / f"strings_{LANGUAGE}.yaml"
        if not target.exists():
            target = base / "strings_de.yaml"
        _data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        if LANGUAGE != "de":
            _fallback = yaml.safe_load(
                (base / "strings_de.yaml").read_text(encoding="utf-8")
            ) or {}
    return _data


def t(key: str, **kwargs) -> str:
    s = _load().get(key) or _fallback.get(key) or key
    return s.format(**kwargs) if kwargs else s
