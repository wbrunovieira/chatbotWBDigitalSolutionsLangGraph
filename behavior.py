"""Behavioral context → lead enrichment, scoring, and light personalization (#8b).

The Next.js server sends a compact, optional `behavior` object with /chat:
`{pages_visited: [...], journey_score: float?, geo_country: str?}`. It's a signal about
how engaged the visitor is — used to score the lead by journey depth, enrich the CRM
description, and subtly tailor the answer. It is NEVER surfaced to the user (we don't
announce tracking), and consent for AI profiling is a product/LGPD decision upstream.

Pure helpers only — no I/O — so they're trivially testable.
"""

from typing import Any, Optional

# Pages that signal high buying intent; a visit to any of these weighs extra in the score.
_HOT_PAGE_HINTS = ("/contact", "/contato", "/pricing", "/precos", "/orcamento",
                   "/automation", "/ai", "/schedule", "/agenda")


def _pages(behavior: Optional[dict]) -> list:
    pages = (behavior or {}).get("pages_visited") or []
    return [p for p in pages if isinstance(p, str) and p.strip()]


def score_lead(behavior: Optional[dict]) -> int:
    """Score a lead 0–100 by journey depth, weighting high-intent pages.

    Depth (how many pages they browsed) is the base signal; a visit to a hot page
    (pricing/contact/…) adds more; an explicit upstream `journey_score` contributes up to
    40 points (accepted both as a 0–1 fraction and as an absolute 0–40 value).
    """
    if not behavior:
        return 0
    pages = _pages(behavior)
    depth_points = min(len(pages) * 8, 50)
    hot_hits = sum(1 for p in pages if any(h in p.lower() for h in _HOT_PAGE_HINTS))
    hot_points = min(hot_hits * 12, 40)

    journey = behavior.get("journey_score")
    journey_points = 0
    if isinstance(journey, (int, float)) and journey > 0:
        journey_points = journey * 40 if journey <= 1 else min(journey, 40)

    return int(max(0, min(depth_points + hot_points + journey_points, 100)))


def summarize_behavior(behavior: Optional[dict]) -> str:
    """A compact, human-readable one-liner for the CRM description / team notify."""
    if not behavior:
        return ""
    parts = []
    pages = _pages(behavior)
    if pages:
        # Truncate each path so one very long URL can't bloat the CRM description / prompt.
        shown = ", ".join(p[:120] for p in pages[:8])
        more = f" (+{len(pages) - 8} more)" if len(pages) > 8 else ""
        parts.append(f"visited {len(pages)} pages: {shown}{more}")
    geo = behavior.get("geo_country")
    if isinstance(geo, str) and geo.strip():
        parts.append(f"country={geo.strip()}")
    journey = behavior.get("journey_score")
    if isinstance(journey, (int, float)):
        parts.append(f"journey_score={journey}")
    return "; ".join(parts)


def personalization_hint(behavior: Optional[dict]) -> str:
    """A system-prompt line that tailors the answer WITHOUT ever revealing we track browsing."""
    summary = summarize_behavior(behavior)
    if not summary:
        return ""
    return (
        "Visitor context (INTERNAL — never reveal or mention that we track browsing, and "
        f"never list their history back to them): {summary}. Subtly tailor your answer to "
        "their apparent interest."
    )


def as_dict(behavior: Any) -> Optional[dict]:
    """Coerce an incoming behavior value (pydantic model or dict) to a plain dict, or None."""
    if behavior is None:
        return None
    if hasattr(behavior, "model_dump"):
        return behavior.model_dump()
    return behavior if isinstance(behavior, dict) else None
