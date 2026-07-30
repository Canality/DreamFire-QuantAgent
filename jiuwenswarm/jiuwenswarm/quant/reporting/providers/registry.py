"""Provider registry: manage and query available data providers."""

from __future__ import annotations

from typing import Dict, List

from jiuwenswarm.quant.reporting.providers.base import BaseProvider


class ProviderRegistry:
    """Registry of data providers, queryable by ticker and category."""

    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' already registered")
        self._providers[provider.name] = provider

    def list_all(self) -> List[str]:
        return sorted(self._providers.keys())

    def get(self, name: str) -> BaseProvider:
        p = self._providers.get(name)
        if p is None:
            raise KeyError(f"Provider '{name}' not found. Available: {self.list_all()}")
        return p

    def find_for_ticker(self, ticker: str) -> List[BaseProvider]:
        return [p for p in self._providers.values() if p.supports_ticker(ticker)]
