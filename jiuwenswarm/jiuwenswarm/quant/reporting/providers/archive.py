"""Offline evidence archive: immutable, write-once storage with SHA-256 verification.

Stores raw provider responses so every ``MetricFact`` evidence_id can be
resolved to archived content without network access.  The archive is
directory-based::

    <root>/
      manifest.json          # evidence_id → EvidenceRef index
      ab/
        ab3f...8c.json      # one file per evidence item

Write-once contract
    Same ``(evidence_id, content_sha256)`` → idempotent success.
    Same ``evidence_id`` with *different* ``content_sha256`` → ``ValueError``.
    Writes use temp-file + fsync + atomic rename.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

from jiuwenswarm.quant.reporting.models import EvidenceRef

# evidence_id must only contain safe filename characters
_SAFE_ID = re.compile(r"^[a-zA-Z0-9_\-\.]+$")
_MAX_ID_LEN = 255


class EvidenceArchive:
    """Immutable, write-once, file-based storage for provider evidence.

    Thread-safe for reads after writes; not safe for concurrent writes.
    """

    def __init__(self, root: Path):
        self._root = Path(root)
        self._manifest_path = self._root / "manifest.json"
        self._manifest: Dict[str, EvidenceRef] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def root(self) -> Path:
        return self._root

    def ensure_root(self) -> None:
        """Create the archive directory if it doesn't exist."""
        self._root.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        evidence_id: str,
        raw_content: str | bytes,
        ref: EvidenceRef,
    ) -> Path:
        """Store raw content with write-once semantics.

        Args:
            evidence_id: Unique evidence identifier.  Must match
                ``[a-zA-Z0-9_\-\.]+`` and be ≤ 255 chars (no path traversal).
            raw_content: The raw provider response (JSON string or bytes).
            ref: The ``EvidenceRef`` whose ``content_sha256`` MUST match.

        Returns:
            Path to the written archive file.

        Raises:
            ValueError: If *evidence_id* contains unsafe characters,
                if the content hash does not match *ref.content_sha256*,
                or if the same *evidence_id* already exists with a
                different hash.
        """
        self._validate_evidence_id(evidence_id)
        self.ensure_root()

        content_bytes = (
            raw_content.encode("utf-8") if isinstance(raw_content, str)
            else raw_content
        )
        actual_hash = hashlib.sha256(content_bytes).hexdigest()

        if ref.content_sha256 and actual_hash != ref.content_sha256:
            raise ValueError(
                f"Content hash mismatch for {evidence_id}: "
                f"computed={actual_hash[:16]}..., "
                f"expected={ref.content_sha256[:16]}..."
            )

        file_path = self._file_path(evidence_id)

        # -- Write-once check ------------------------------------------
        existing_ref = self._load_manifest().get(evidence_id)
        if existing_ref is not None:
            if existing_ref.content_sha256 == ref.content_sha256:
                # Idempotent: same ID, same hash → no-op (success)
                return file_path
            raise ValueError(
                f"Evidence '{evidence_id}' already archived with a different "
                f"hash: existing={existing_ref.content_sha256[:16]}..., "
                f"attempted={ref.content_sha256[:16]}..."
            )

        # -- Atomic write: temp file → fsync → rename ------------------
        subdir = self._root / _prefix(evidence_id)
        subdir.mkdir(parents=True, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(
                suffix=".json", prefix=f"{evidence_id}-", dir=str(subdir),
            )
            try:
                os.write(fd, content_bytes)
                os.fsync(fd)
            finally:
                os.close(fd)
            os.replace(tmp_path, str(file_path))
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

        # -- Update manifest -------------------------------------------
        manifest = self._load_manifest()
        manifest[evidence_id] = ref
        self._save_manifest(manifest)

        return file_path

    def read(self, evidence_id: str) -> bytes | None:
        """Read raw archived content, verifying SHA-256 integrity.

        Returns None if the evidence_id is not in the manifest or the file
        is missing/corrupted.
        """
        self._validate_evidence_id(evidence_id)
        manifest = self._load_manifest()
        ref = manifest.get(evidence_id)
        if ref is None:
            return None

        file_path = self._file_path(evidence_id)
        if not file_path.exists():
            return None

        content = file_path.read_bytes()
        actual_hash = hashlib.sha256(content).hexdigest()
        if ref.content_sha256 and actual_hash != ref.content_sha256:
            return None  # tampered or corrupted

        return content

    def exists(self, evidence_id: str) -> bool:
        """Check whether an evidence_id is archived and its file is intact."""
        return self.read(evidence_id) is not None

    def build_manifest(self) -> Dict[str, EvidenceRef]:
        """Return the full evidence_id → EvidenceRef mapping.

        Only entries whose files exist and pass hash verification are included.
        """
        raw = self._load_manifest()
        verified: Dict[str, EvidenceRef] = {}
        for eid, ref in raw.items():
            if self.exists(eid):
                verified[eid] = ref
        return verified

    def list_ids(self) -> list[str]:
        """List all evidence_ids with intact archive files."""
        return sorted(self.build_manifest().keys())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_evidence_id(evidence_id: str) -> None:
        if not evidence_id or not _SAFE_ID.match(evidence_id):
            raise ValueError(
                f"Invalid evidence_id {evidence_id!r}: must match "
                f"[a-zA-Z0-9_\\-\\.]+ and be non-empty"
            )
        if len(evidence_id) > _MAX_ID_LEN:
            raise ValueError(
                f"evidence_id too long ({len(evidence_id)} > {_MAX_ID_LEN})"
            )
        # Path traversal check: no directory separators or parent refs
        if ".." in evidence_id or "/" in evidence_id or "\\" in evidence_id:
            raise ValueError(
                f"evidence_id contains path traversal: {evidence_id!r}"
            )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _file_path(self, evidence_id: str) -> Path:
        return self._root / _prefix(evidence_id) / f"{evidence_id}.json"

    def _load_manifest(self) -> Dict[str, EvidenceRef]:
        if self._manifest is not None:
            return self._manifest
        if not self._manifest_path.exists():
            return {}
        raw = json.loads(self._manifest_path.read_text(encoding="utf-8"))
        result: Dict[str, EvidenceRef] = {}
        for eid, data in raw.items():
            result[eid] = _evidence_ref_from_dict(data)
        self._manifest = result
        return result

    def _save_manifest(self, manifest: Dict[str, EvidenceRef]) -> None:
        serialised = {
            eid: _evidence_ref_to_dict(ref) for eid, ref in manifest.items()
        }
        self._manifest_path.write_text(
            json.dumps(serialised, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._manifest = manifest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _prefix(evidence_id: str) -> str:
    return evidence_id[:2] if len(evidence_id) >= 2 else "xx"


def _evidence_ref_to_dict(ref: EvidenceRef) -> dict:
    return {
        "evidence_id": ref.evidence_id,
        "source_type": ref.source_type,
        "source_name": ref.source_name,
        "source_url": ref.source_url,
        "period_end": ref.period_end.isoformat() if ref.period_end else None,
        "published_at": ref.published_at.isoformat() if ref.published_at else None,
        "available_at": ref.available_at.isoformat() if ref.available_at else None,
        "retrieved_at": ref.retrieved_at.isoformat() if ref.retrieved_at else None,
        "content_sha256": ref.content_sha256,
    }


def _evidence_ref_from_dict(data: dict) -> EvidenceRef:
    def _dt(key: str) -> datetime | None:
        val = data.get(key)
        return datetime.fromisoformat(val) if val else None

    return EvidenceRef(
        evidence_id=data["evidence_id"],
        source_type=data.get("source_type", ""),
        source_name=data.get("source_name", ""),
        source_url=data.get("source_url"),
        period_end=_dt("period_end"),
        published_at=_dt("published_at"),
        available_at=_dt("available_at") or datetime.now(timezone.utc),
        retrieved_at=_dt("retrieved_at") or datetime.now(timezone.utc),
        content_sha256=data.get("content_sha256", ""),
    )
