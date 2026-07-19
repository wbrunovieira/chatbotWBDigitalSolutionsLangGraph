"""Resolve and normalize the request language on ingest.

The site widget doesn't always send `language` — button clicks like "Ver serviços" post
none, and some builds send an empty string. Left unresolved these logged as language=None
and the bot answered in the wrong language. This canonicalizes whatever the widget sends
and, when it's missing/blank/unrecognized, derives the language from the page's locale
segment (e.g. /en/, /es/) before falling back to Brazilian Portuguese.
"""

import re

DEFAULT_LANGUAGE = "pt-BR"
# The languages the answer prompts actually support (see nodes.generation).
SUPPORTED_LANGUAGES = ("pt-BR", "en", "es", "it")

# Common variants/aliases (compared lowercased) mapped to a supported code.
_ALIASES = {
    "pt": "pt-BR", "pt-br": "pt-BR", "pt_br": "pt-BR", "br": "pt-BR",
    "portuguese": "pt-BR", "português": "pt-BR", "portugues": "pt-BR",
    "en": "en", "en-us": "en", "en-gb": "en", "english": "en",
    "es": "es", "es-es": "es", "es-419": "es", "spanish": "es",
    "español": "es", "espanol": "es",
    "it": "it", "it-it": "it", "italian": "it", "italiano": "it",
}

# A locale segment standing on its own in a URL path: /en, /es/, /pt-BR/ ... The lookahead
# requires a real boundary so "/entretenimento" or "/digital" don't false-match "en"/"it".
_PATH_LOCALE = re.compile(r"/(pt-br|pt|en|es|it)(?=[/?#_-]|$)", re.IGNORECASE)


def _canonical(value):
    """Map a raw language string to a supported code, or None if unrecognized."""
    if not value:
        return None
    token = str(value).strip().lower()
    if token in _ALIASES:
        return _ALIASES[token]
    # Fall back to the primary subtag: "en-AU" -> "en".
    primary = re.split(r"[-_]", token, maxsplit=1)[0]
    return _ALIASES.get(primary)


def _from_path(path):
    """Derive a language from a URL/path locale segment, or None."""
    if not path:
        return None
    match = _PATH_LOCALE.search(str(path))
    return _ALIASES.get(match.group(1).lower()) if match else None


def resolve_language(raw_language, page_url="", current_page=""):
    """Best-effort language for a request: explicit value, else page locale, else pt-BR."""
    return (
        _canonical(raw_language)
        or _from_path(page_url)
        or _from_path(current_page)
        or DEFAULT_LANGUAGE
    )
