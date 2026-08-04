#!/usr/bin/env python3
"""Smoke test: fetch announcements for 2 stocks via the shared service."""
import asyncio
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jiuwenswarm.quant.reporting.providers.announcement import AnnouncementProvider
from jiuwenswarm.quant.reporting.announcement_service import AnnouncementService
from jiuwenswarm.quant.reporting.providers.archive import EvidenceArchive

UTC = timezone.utc


async def main():
    p = AnnouncementProvider()
    with tempfile.TemporaryDirectory() as tmp:
        archive = EvidenceArchive(Path(tmp))
        svc = AnnouncementService(p, archive)
        now = datetime.now(UTC)
        result = await svc.run(["600000.SH", "000001.SZ"], now)

        f1 = result.facts_by_ticker.get("600000.SH", [])
        f2 = result.facts_by_ticker.get("000001.SZ", [])
        s1 = result.statuses.get("600000.SH")
        s2 = result.statuses.get("000001.SZ")

        print(f"600000.SH: {len(f1)} facts, status={s1}")
        print(f"000001.SZ: {len(f2)} facts, status={s2}")
        print(f"Total facts: {result.total_facts}")
        print(f"Tickers with events: {result.tickers_with_events}")
        print(f"Manifest entries: {len(result.manifest)}")

        for eid, ref in list(result.manifest.items())[:2]:
            url = ref.source_url
            print(f"EvidenceRef URL: {url[:120]}...")
            assert "data.eastmoney.com" in url, (
                f"URL should be a detail page, got: {url}"
            )

        assert result.total_facts > 0, "Should have facts for at least one stock"
        assert len(result.manifest) > 0, "Should have manifest entries"
        print("\nSMOKE PASSED")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
