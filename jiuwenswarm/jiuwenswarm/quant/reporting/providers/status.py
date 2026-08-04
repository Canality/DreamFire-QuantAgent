"""Provider status and category enums — single source of truth.

These enums replace raw strings in provider return values and registry
queries so that status semantics cannot drift between providers.
"""

from __future__ import annotations

from enum import Enum


class ProviderStatus(str, Enum):
    """Outcome of a single ``fetch_for_ticker`` call."""

    COMPLETE = "complete"
    """Every requested metric was successfully retrieved."""

    PARTIAL = "partial"
    """At least one metric was retrieved, but some are missing or stale."""

    AVAILABLE_NO_EVENT = "available_no_event"
    """Provider responded successfully but there are no relevant events
    for this ticker / as_of_time.  Distinct from UNAVAILABLE, which means
    the provider itself could not be reached."""

    UNAVAILABLE = "unavailable"
    """No metrics could be retrieved — provider is unreachable, timed out,
    or returned an error."""


class ProviderCategory(str, Enum):
    """Semantic category of a data provider.

    Used by the registry for discovery and by the quality gate for
    coverage checks.
    """

    MARKET = "market_data"
    """Price, volume, turnover — already covered by the quant pipeline."""

    FUNDAMENTAL = "financial_statement"
    """PE, PB, ROE, revenue, etc. from periodic reports."""

    DISCLOSURE = "disclosure"
    """Exchange announcements, filings, regulatory disclosures."""

    NEWS = "news"
    """Media reports, analyst notes, unstructured text."""

    MACRO = "macro"
    """Index levels, interest rates, macro indicators."""
