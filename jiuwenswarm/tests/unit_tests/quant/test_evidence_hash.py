"""Tests for SHA-256 hash validation in quality gate."""


from jiuwenswarm.quant.reporting.quality_gate import _SHA256_HEX, _evidence_has_valid_hash
from jiuwenswarm.quant.reporting.models import EvidenceRef
from datetime import datetime, timezone

NOW = datetime.now(timezone.utc)


def _make_ref(hash_val: str) -> EvidenceRef:
    return EvidenceRef(
        evidence_id="e1", source_type="market_data", source_name="Test",
        source_url=None, period_end=None, published_at=None,
        available_at=NOW, retrieved_at=NOW, content_sha256=hash_val,
    )


def test_valid_64_hex_hash_passes():
    h = "a" * 64
    assert _evidence_has_valid_hash(_make_ref(h)) is True
    h2 = "C021D69B5C3BF3EA0C4626811DF5ED9A02CD4C67E1068AD2F0CE35D759210617"
    assert _evidence_has_valid_hash(_make_ref(h2)) is True


def test_short_hash_fails():
    assert _evidence_has_valid_hash(_make_ref("a" * 32)) is False


def test_label_string_fails():
    assert _evidence_has_valid_hash(_make_ref("unarchived")) is False
    assert _evidence_has_valid_hash(_make_ref("extension-generated")) is False
    assert _evidence_has_valid_hash(_make_ref("not-a-real-hash")) is False


def test_empty_hash_fails():
    assert _evidence_has_valid_hash(_make_ref("")) is False


def test_non_hex_hash_fails():
    assert _evidence_has_valid_hash(_make_ref("g" * 64)) is False


def test_regex_pattern():
    assert _SHA256_HEX.match("a" * 64)
    assert not _SHA256_HEX.match("a" * 32)
    assert not _SHA256_HEX.match("unarchived")
