"""Data providers for report evidence layer (R4).

These providers populate CompanyFactBundle with fundamental, disclosure,
and news facts. They NEVER modify portfolio weights or stock selection.
"""

from jiuwenswarm.quant.reporting.providers.base import BaseProvider
from jiuwenswarm.quant.reporting.providers.registry import ProviderRegistry
from jiuwenswarm.quant.reporting.providers.status import ProviderCategory, ProviderStatus

__all__ = [
    "BaseProvider",
    "ProviderCategory",
    "ProviderRegistry",
    "ProviderStatus",
]