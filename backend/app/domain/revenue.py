"""Versioned revenue-estimate models. Every figure is an ESTIMATE of gross revenue, not sales."""

from __future__ import annotations

LEGACY_MODEL_ID = "legacy_reviews_x45_price"
LEGACY_REVIEWS_TO_SALES_MULTIPLIER = 45
LEGACY_MODEL_LABEL = "Estimated gross revenue (total reviews x 45 x listed price)"


def legacy_estimate_usd(total_reviews: int, price_usd: float) -> int:
    """The legacy formula: round(total_reviews * 45 * price).

    Only used to *validate* imported values. Imported values are stored as-is, never replaced.
    Python's round() is banker's rounding; the legacy data contains no .5 ties (verified by the
    import data-quality check, which flags any mismatch rather than altering the value).
    """
    return round(total_reviews * LEGACY_REVIEWS_TO_SALES_MULTIPLIER * price_usd)


def usd_to_minor_units(amount_usd: float) -> int:
    return round(amount_usd * 100)
