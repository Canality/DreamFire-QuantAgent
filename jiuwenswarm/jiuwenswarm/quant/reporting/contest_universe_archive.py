"""Audit the immutable contest-universe workbook without treating it as PIT data.

The workbook is evidence for the current competition's fixed 49-name reporting
universe and six custom presentation groups.  It does not declare an industry
taxonomy, publication/effective time, or historical applicability, so this
module intentionally exposes ``CONTEST_FIXED_METADATA`` only.  Its output must
never satisfy the factor research ``PIT_SECTOR`` capability.

Only the repository's fixed path and audited SHA-256 are accepted.  The parser
uses the Python standard library and validates the OOXML cells themselves so a
matching filename or a caller-supplied hash cannot self-attest different
contract semantics.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree


CONTEST_UNIVERSE_REL_PATH = "赛题文档/上市公司列表.xlsx"
CONTEST_UNIVERSE_SHA256 = (
    "C021D69B5C3BF3EA0C4626811DF5ED9A02CD4C67E1068AD2F0CE35D759210617"
)
CONTEST_FIXED_METADATA = "CONTEST_FIXED_METADATA"
CONTEST_UNIVERSE_AUTHORITY = "CCF_BDCI_2026_COMPETITION_WORKBOOK"
CONTEST_UNIVERSE_SOURCE_VERSION = f"sha256:{CONTEST_UNIVERSE_SHA256.lower()}"
# Independent semantic anchor for the exact 49 code/name/group mapping.  A new
# workbook version must deliberately migrate both its byte identity and this
# contract identity; changing the byte hash alone cannot redefine the universe.
CONTEST_UNIVERSE_EVIDENCE_SHA256 = (
    "b490612174fc0b79554e7ca3d04b9a14e14d4b8b5b6c9c50983330e94fdbdc12"
)

_EXPECTED_SHEETS = ("Sheet1", "Sheet2", "Sheet3")
_EXPECTED_SHEET_TARGETS = (
    "xl/worksheets/sheet1.xml",
    "xl/worksheets/sheet2.xml",
    "xl/worksheets/sheet3.xml",
)
_EXPECTED_HEADERS = (
    "金融板块",
    "消费板块",
    "新能源/电力板块",
    "科技/AI/半导体板块",
    "周期/资源板块",
    "高端制造/基建板块",
)
_EXPECTED_GROUPS = tuple(header.removesuffix("板块") for header in _EXPECTED_HEADERS)
_EXPECTED_COUNTS = (8, 9, 8, 12, 8, 4)
_CELL_PATTERN = re.compile(r"^([A-Z]+)([1-9]\d*)$")
_MEMBER_PATTERN = re.compile(r"^(\d{6}) ([^\s].*)$")

_MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_DC_NS = "http://purl.org/dc/elements/1.1/"
_DCTERMS_NS = "http://purl.org/dc/terms/"


@dataclass(frozen=True)
class ContestUniverseMember:
    """One exact code/name/group observation from the contest workbook."""

    ticker: str
    company_name: str
    group_name: str
    cell: str


@dataclass(frozen=True)
class ContestUniverseAudit:
    """Fail-closed audit result for the fixed contest metadata artifact."""

    capability: str
    authority: str
    source_path: str
    source_sha256: str
    source_version: str
    workbook_created: str | None
    workbook_modified: str | None
    group_names: tuple[str, ...]
    group_counts: tuple[int, ...]
    members: tuple[ContestUniverseMember, ...]
    evidence_hash: str
    verified: bool
    issues: tuple[str, ...]
    pit_sector_eligible: bool = False

    @property
    def company_codes(self) -> tuple[str, ...]:
        return tuple(sorted(member.ticker for member in self.members))

    @property
    def company_names(self) -> dict[str, str]:
        return {member.ticker: member.company_name for member in self.members}

    @property
    def sectors(self) -> dict[str, str]:
        return {member.ticker: member.group_name for member in self.members}


def _resolve_project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def _has_symlink_component(root: Path, relative_path: str) -> bool:
    current = root
    for part in Path(relative_path).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _xml(archive: zipfile.ZipFile, member: str) -> ElementTree.Element:
    return ElementTree.fromstring(archive.read(member))


def _relationship_targets(archive: zipfile.ZipFile) -> dict[str, str]:
    root = _xml(archive, "xl/_rels/workbook.xml.rels")
    targets: dict[str, str] = {}
    for relationship in root.findall(f"{{{_PKG_REL_NS}}}Relationship"):
        rel_id = relationship.get("Id")
        target = relationship.get("Target")
        if not rel_id or not target or rel_id in targets:
            raise ValueError("workbook relationships contain a missing or duplicate Id")
        normalized = posixpath.normpath(posixpath.join("xl", target))
        if normalized.startswith("../") or normalized.startswith("/"):
            raise ValueError(f"unsafe workbook relationship target: {target!r}")
        targets[rel_id] = normalized
    return targets


def _sheet_manifest(archive: zipfile.ZipFile) -> tuple[tuple[str, str], ...]:
    root = _xml(archive, "xl/workbook.xml")
    relationships = _relationship_targets(archive)
    manifest: list[tuple[str, str]] = []
    sheets = root.find(f"{{{_MAIN_NS}}}sheets")
    if sheets is None:
        raise ValueError("workbook is missing its sheets manifest")
    for sheet in sheets.findall(f"{{{_MAIN_NS}}}sheet"):
        name = sheet.get("name")
        rel_id = sheet.get(f"{{{_REL_NS}}}id")
        if not name or not rel_id or rel_id not in relationships:
            raise ValueError("workbook sheet has no resolvable relationship")
        manifest.append((name, relationships[rel_id]))
    return tuple(manifest)


def _shared_strings(archive: zipfile.ZipFile) -> tuple[str, ...]:
    root = _xml(archive, "xl/sharedStrings.xml")
    values: list[str] = []
    for item in root.findall(f"{{{_MAIN_NS}}}si"):
        values.append("".join(node.text or "" for node in item.iter(f"{{{_MAIN_NS}}}t")))
    return tuple(values)


def _sheet_cells(
    archive: zipfile.ZipFile,
    member: str,
    shared_strings: tuple[str, ...],
) -> dict[str, str]:
    root = _xml(archive, member)
    cells: dict[str, str] = {}
    for cell in root.iter(f"{{{_MAIN_NS}}}c"):
        reference = cell.get("r")
        if not reference or reference in cells:
            raise ValueError(f"{member} contains a missing or duplicate cell reference")
        if cell.find(f"{{{_MAIN_NS}}}f") is not None:
            raise ValueError(f"formula cells are not allowed: {member}:{reference}")
        if cell.get("t") != "s":
            raise ValueError(f"only shared-string cells are allowed: {member}:{reference}")
        value = cell.find(f"{{{_MAIN_NS}}}v")
        if value is None or value.text is None:
            raise ValueError(f"cell has no shared-string index: {member}:{reference}")
        try:
            index = int(value.text)
            cells[reference] = shared_strings[index]
        except (ValueError, IndexError) as exc:
            raise ValueError(
                f"invalid shared-string index at {member}:{reference}"
            ) from exc
    return cells


def _expected_cell_references() -> set[str]:
    return {
        f"{column}{row}"
        for column in "ABCDEF"
        for row in range(1, 14)
    }


def _ticker(code: str) -> str:
    if code.startswith(("0", "3")):
        return f"{code}.SZ"
    if code.startswith("6"):
        return f"{code}.SH"
    raise ValueError(f"unsupported exchange prefix for contest code {code}")


def _core_properties(archive: zipfile.ZipFile) -> tuple[str | None, str | None]:
    root = _xml(archive, "docProps/core.xml")
    created = root.find(f"{{{_DCTERMS_NS}}}created")
    modified = root.find(f"{{{_DCTERMS_NS}}}modified")
    return (
        created.text if created is not None else None,
        modified.text if modified is not None else None,
    )


def _evidence_hash(members: tuple[ContestUniverseMember, ...]) -> str:
    payload = {
        "authority": CONTEST_UNIVERSE_AUTHORITY,
        "capability": CONTEST_FIXED_METADATA,
        "source_sha256": CONTEST_UNIVERSE_SHA256.lower(),
        "source_version": CONTEST_UNIVERSE_SOURCE_VERSION,
        "groups": list(_EXPECTED_GROUPS),
        "members": [
            {
                "ticker": member.ticker,
                "company_name": member.company_name,
                "group_name": member.group_name,
            }
            for member in sorted(members, key=lambda item: item.ticker)
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _failed_audit(actual_sha256: str, issue: str) -> ContestUniverseAudit:
    return ContestUniverseAudit(
        capability=CONTEST_FIXED_METADATA,
        authority=CONTEST_UNIVERSE_AUTHORITY,
        source_path=CONTEST_UNIVERSE_REL_PATH,
        source_sha256=actual_sha256,
        source_version=CONTEST_UNIVERSE_SOURCE_VERSION,
        workbook_created=None,
        workbook_modified=None,
        group_names=(),
        group_counts=(),
        members=(),
        evidence_hash="",
        verified=False,
        issues=(issue,),
    )


def _inspect_at_root(root: Path) -> ContestUniverseAudit:
    """Inspect the fixed archive below ``root``; private seam for isolated tests."""

    root = Path(root).resolve()
    path = root / CONTEST_UNIVERSE_REL_PATH
    if _has_symlink_component(root, CONTEST_UNIVERSE_REL_PATH):
        return _failed_audit("", "contest workbook path contains a symlink")
    if not path.is_file():
        return _failed_audit("", "contest workbook is missing or is not a regular file")

    try:
        actual_sha256 = _sha256(path)
    except OSError as exc:
        return _failed_audit("", f"contest workbook cannot be hashed: {exc}")
    if actual_sha256 != CONTEST_UNIVERSE_SHA256:
        return _failed_audit(
            actual_sha256,
            "contest workbook hash mismatch: "
            f"expected {CONTEST_UNIVERSE_SHA256}, got {actual_sha256}",
        )

    try:
        with zipfile.ZipFile(path) as archive:
            names = [item.filename for item in archive.infolist()]
            if len(names) != len(set(names)):
                raise ValueError("OOXML archive contains duplicate member names")
            if any(
                name.startswith("/") or ".." in Path(name).parts
                for name in names
            ):
                raise ValueError("OOXML archive contains an unsafe member path")

            manifest = _sheet_manifest(archive)
            expected_manifest = tuple(zip(_EXPECTED_SHEETS, _EXPECTED_SHEET_TARGETS))
            if manifest != expected_manifest:
                raise ValueError(
                    f"unexpected workbook sheets: expected {expected_manifest}, got {manifest}"
                )

            strings = _shared_strings(archive)
            primary = _sheet_cells(archive, manifest[0][1], strings)
            if set(primary) != _expected_cell_references():
                missing = sorted(_expected_cell_references() - set(primary))
                extra = sorted(set(primary) - _expected_cell_references())
                raise ValueError(
                    f"Sheet1 must contain exactly A1:F13; missing={missing}, extra={extra}"
                )
            for name, member in manifest[1:]:
                cells = _sheet_cells(archive, member, strings)
                if cells:
                    raise ValueError(f"{name} must be empty, found cells {sorted(cells)}")

            headers = tuple(primary[f"{column}1"] for column in "ABCDEF")
            if headers != _EXPECTED_HEADERS:
                raise ValueError(
                    f"contest group headers changed: expected {_EXPECTED_HEADERS}, got {headers}"
                )

            members: list[ContestUniverseMember] = []
            group_counts: list[int] = []
            for column, group_name in zip("ABCDEF", _EXPECTED_GROUPS):
                count = 0
                for row in range(2, 14):
                    reference = f"{column}{row}"
                    raw_value = primary[reference]
                    if raw_value == "-":
                        continue
                    match = _MEMBER_PATTERN.fullmatch(raw_value)
                    if not match:
                        raise ValueError(
                            f"invalid contest member syntax at {reference}: {raw_value!r}"
                        )
                    code, company_name = match.groups()
                    members.append(
                        ContestUniverseMember(
                            ticker=_ticker(code),
                            company_name=company_name,
                            group_name=group_name,
                            cell=reference,
                        )
                    )
                    count += 1
                group_counts.append(count)

            members_tuple = tuple(members)
            tickers = [member.ticker for member in members_tuple]
            if len(tickers) != 49 or len(set(tickers)) != 49:
                raise ValueError(
                    "contest workbook must contain exactly 49 unique company codes; "
                    f"found {len(tickers)} rows and {len(set(tickers))} unique codes"
                )
            if tuple(group_counts) != _EXPECTED_COUNTS:
                raise ValueError(
                    f"contest group counts changed: expected {_EXPECTED_COUNTS}, "
                    f"got {tuple(group_counts)}"
                )
            semantic_hash = _evidence_hash(members_tuple)
            if semantic_hash != CONTEST_UNIVERSE_EVIDENCE_SHA256:
                raise ValueError(
                    "contest semantic identity changed: expected evidence hash "
                    f"{CONTEST_UNIVERSE_EVIDENCE_SHA256}, got {semantic_hash}; "
                    "a legitimate revision requires an explicit versioned contract migration"
                )
            created, modified = _core_properties(archive)
    except (
        ElementTree.ParseError,
        KeyError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
    ) as exc:
        return _failed_audit(actual_sha256, f"contest workbook semantic audit failed: {exc}")

    return ContestUniverseAudit(
        capability=CONTEST_FIXED_METADATA,
        authority=CONTEST_UNIVERSE_AUTHORITY,
        source_path=CONTEST_UNIVERSE_REL_PATH,
        source_sha256=actual_sha256,
        source_version=CONTEST_UNIVERSE_SOURCE_VERSION,
        workbook_created=created,
        workbook_modified=modified,
        group_names=_EXPECTED_GROUPS,
        group_counts=tuple(group_counts),
        members=members_tuple,
        evidence_hash=semantic_hash,
        verified=True,
        issues=(),
    )


def inspect_contest_universe_archive() -> ContestUniverseAudit:
    """Return an audit of the one repository-owned contest workbook.

    The no-argument API is deliberate: production callers cannot substitute a
    path, hash, taxonomy name, or timestamp.  Tests use the private root seam.
    """

    return _inspect_at_root(_resolve_project_root())


__all__ = [
    "CONTEST_FIXED_METADATA",
    "CONTEST_UNIVERSE_AUTHORITY",
    "CONTEST_UNIVERSE_EVIDENCE_SHA256",
    "CONTEST_UNIVERSE_REL_PATH",
    "CONTEST_UNIVERSE_SHA256",
    "CONTEST_UNIVERSE_SOURCE_VERSION",
    "ContestUniverseAudit",
    "ContestUniverseMember",
    "inspect_contest_universe_archive",
]
