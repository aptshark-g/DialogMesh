"""i18n locale loader."""
from __future__ import annotations
import importlib, os
from typing import Dict


_cache.clear()
        return load_locale(lang)


def load_locale(lang: str = None) -> dict:
    """Load locale strings for a language.

    Priority: DIALOGMESH_LANG env var -> 'en' default.
    Users can add new locales by creating i18n/locales/{lang}.py.

    Returns:
        Dict with locale strings. Always has a t(key, **kwargs) function.
    """
    global _cache

    if lang is None:
        lang = os.environ.get("DIALOGMESH_LANG", "en")

    # Allow cache bypass via env change
    if lang in _cache and os.environ.get("DIALOGMESH_LANG") == lang:
        return _cache[lang]

    try:
        mod = importlib.import_module(f"i18n.locales.{lang}")
        loc = {
            **mod.LOCALE,
            "t": mod.t,
        }
        _cache[lang] = loc
        return loc
    except ImportError:
        # Fallback to English
        if lang != "en":
            return load_locale("en")
        return {"t": lambda key, **kw: key}


def clear_cache():
    """Clear locale cache (for language switch)."""
    global _cache
    _cache = {}


def t(key: str, **kwargs) -> str:
    """Shorthand: translate a key with current locale."""
    loc = load_locale()
    fn = loc.get("t", lambda k, **kw: k)
    return fn(key, **kwargs)
