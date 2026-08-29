"""Immutable, publication-local glossary revisions and safe resolution."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import re
import tempfile

from ._json import JsonValue, canonical_json_bytes, freeze_json, strict_json_loads, thaw_json
from .resolver import RevisionDiagnostic


GLOSSARY_REVISION_SCHEMA = "alc.render.glossary_revision.v1"
GLOSSARY_MENTIONS_SCHEMA = "alc.render.glossary_mentions.v1"
GLOSSARY_PROPAGATION_SCHEMA = "alc.render.glossary_propagation.v1"
GLOSSARY_REVISION_DIRECTORY = "glossary"
GLOSSARY_FRONT_MATTER_BEGIN = "<!-- ALC:GLOSSARY-JSON:BEGIN -->"
GLOSSARY_FRONT_MATTER_END = "<!-- ALC:GLOSSARY-JSON:END -->"
_FILENAME_RE = re.compile(
    r"revision-(?P<revision>[0-9]{6,})-(?P<digest>[0-9a-f]{64})"
    r"[.](?P<extension>md|json)"
)
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_IDENTIFIER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]*")


def _require_identifier(value: object, description: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{description} must be a portable identifier")
    return value


def _require_digest(value: object, description: str) -> str:
    if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
        raise ValueError(f"{description} must be a SHA-256 digest")
    return value


def _require_string(value: object, description: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value):
        qualifier = "" if empty else " non-empty"
        raise ValueError(f"{description} must be a{qualifier} string")
    return value


def _entry_id(entry: Mapping[str, object]) -> str:
    return _require_identifier(entry.get("entry_id"), "glossary entry_id")


def _translated_key(entry: Mapping[str, object]) -> str | None:
    if "translated_term" in entry:
        return "translated_term"
    if "translation" in entry:
        return "translation"
    return None


def glossary_entry_is_editable(entry: Mapping[str, object]) -> bool:
    """Return whether an existing entry has the stable edit contract."""

    try:
        _entry_id(entry)
    except ValueError:
        return False
    source = entry.get("term") or entry.get("source_term")
    translated_key = _translated_key(entry)
    return (
        isinstance(source, str)
        and bool(source.strip())
        and translated_key is not None
        and isinstance(entry.get(translated_key), str)
        and isinstance(entry.get("definition"), str)
    )


def _glossary_propagation_members(
    provenance: Mapping[str, object],
) -> tuple[
    tuple[Mapping[str, object], ...],
    tuple[Mapping[str, object], ...],
]:
    if "propagation" not in provenance:
        return (), ()
    propagation = provenance.get("propagation")
    legacy_fields = {
        "schema_version",
        "batch_id",
        "fragments",
    }
    extended_fields = {*legacy_fields, "glossary_revisions"}
    if (
        not isinstance(propagation, Mapping)
        or set(propagation) not in (legacy_fields, extended_fields)
    ):
        raise ValueError("glossary propagation has invalid fields")
    if propagation.get("schema_version") != GLOSSARY_PROPAGATION_SCHEMA:
        raise ValueError("unsupported glossary propagation schema")
    batch_id = _require_identifier(
        propagation.get("batch_id"), "glossary propagation batch_id"
    )
    raw_fragments = propagation.get("fragments")
    raw_glossary = propagation.get("glossary_revisions", ())
    if not isinstance(raw_fragments, (list, tuple)) or not isinstance(
        raw_glossary, (list, tuple)
    ):
        raise ValueError("glossary propagation members must be arrays")
    if not raw_fragments and not raw_glossary:
        raise ValueError("glossary propagation must reference at least one member")
    fragment_ids: set[str] = set()
    paths: set[str] = set()
    fragments: list[Mapping[str, object]] = []
    for raw in raw_fragments:
        if not isinstance(raw, Mapping) or set(raw) != {
            "path",
            "fragment_id",
            "revision",
            "parent_semantic_digest",
            "semantic_digest",
        }:
            raise ValueError("glossary propagation fragment has invalid fields")
        fragment_id = _require_identifier(
            raw.get("fragment_id"), "glossary propagation fragment_id"
        )
        revision = raw.get("revision")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 2
        ):
            raise ValueError("glossary propagation revision must be at least 2")
        parent = _require_digest(
            raw.get("parent_semantic_digest"),
            "glossary propagation parent_semantic_digest",
        )
        digest = _require_digest(
            raw.get("semantic_digest"),
            "glossary propagation semantic_digest",
        )
        path = _require_string(raw.get("path"), "glossary propagation path")
        expected = (
            f"glossary-batches/{batch_id}/fragments/"
            f"revision-{revision:06d}-{digest}.md"
        )
        if PurePosixPath(path).as_posix() != path or path != expected:
            raise ValueError("glossary propagation path does not match its identity")
        if fragment_id in fragment_ids or path in paths:
            raise ValueError("glossary propagation repeats a Fragment")
        fragment_ids.add(fragment_id)
        paths.add(path)
        fragments.append(
            {
                "path": path,
                "fragment_id": fragment_id,
                "revision": revision,
                "parent_semantic_digest": parent,
                "semantic_digest": digest,
            }
        )
    entry_ids: set[str] = set()
    glossary_paths: set[str] = set()
    glossary_revisions: list[Mapping[str, object]] = []
    for raw in raw_glossary:
        if not isinstance(raw, Mapping) or set(raw) != {
            "path",
            "entry_id",
            "revision",
            "parent_semantic_digest",
            "semantic_digest",
        }:
            raise ValueError(
                "glossary propagation glossary revision has invalid fields"
            )
        entry_id = _require_identifier(
            raw.get("entry_id"),
            "glossary propagation dependent entry_id",
        )
        revision = raw.get("revision")
        if (
            isinstance(revision, bool)
            or not isinstance(revision, int)
            or revision < 2
        ):
            raise ValueError(
                "glossary propagation dependent revision must be at least 2"
            )
        parent = _require_digest(
            raw.get("parent_semantic_digest"),
            "glossary propagation dependent parent_semantic_digest",
        )
        digest = _require_digest(
            raw.get("semantic_digest"),
            "glossary propagation dependent semantic_digest",
        )
        path = _require_string(
            raw.get("path"), "glossary propagation dependent path"
        )
        expected = (
            f"glossary-batches/{batch_id}/glossary/"
            f"revision-{revision:06d}-{digest}.md"
        )
        if PurePosixPath(path).as_posix() != path or path != expected:
            raise ValueError(
                "glossary propagation dependent path does not match its identity"
            )
        if entry_id in entry_ids or path in glossary_paths:
            raise ValueError(
                "glossary propagation repeats a dependent glossary entry"
            )
        entry_ids.add(entry_id)
        glossary_paths.add(path)
        glossary_revisions.append(
            {
                "path": path,
                "entry_id": entry_id,
                "revision": revision,
                "parent_semantic_digest": parent,
                "semantic_digest": digest,
            }
        )
    return tuple(fragments), tuple(glossary_revisions)


def glossary_propagation_fragments(
    provenance: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Validate and return optional all-or-none Fragment batch members."""

    return _glossary_propagation_members(provenance)[0]


def glossary_propagation_glossary_revisions(
    provenance: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    """Validate and return dependent glossary revision batch members."""

    return _glossary_propagation_members(provenance)[1]


def _entry_document(entry: Mapping[str, object]) -> dict[str, JsonValue]:
    frozen = freeze_json(entry, "glossary entry")
    if not isinstance(frozen, Mapping):
        raise ValueError("glossary entry must be an object")
    return thaw_json(frozen)


def _validate_surface_anchors(entry: Mapping[str, object]) -> None:
    anchors = entry.get("surface_anchors")
    if anchors is None:
        return
    if not isinstance(anchors, list):
        raise ValueError("glossary surface_anchors must be an array")
    ranges: dict[tuple[str, str, str], list[tuple[int, int]]] = defaultdict(list)
    for anchor in anchors:
        if not isinstance(anchor, Mapping) or set(anchor) != {
            "block_id",
            "fragment_id",
            "fragment_semantic_digest",
            "markdown_start",
            "markdown_end",
            "surface",
        }:
            raise ValueError("glossary surface anchor has invalid fields")
        block_id = _require_identifier(anchor.get("block_id"), "surface anchor block_id")
        fragment_id = _require_identifier(
            anchor.get("fragment_id"), "surface anchor fragment_id"
        )
        fragment_digest = _require_digest(
            anchor.get("fragment_semantic_digest"),
            "surface anchor fragment_semantic_digest",
        )
        start = anchor.get("markdown_start")
        end = anchor.get("markdown_end")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or start < 0
            or isinstance(end, bool)
            or not isinstance(end, int)
            or end <= start
        ):
            raise ValueError("glossary surface anchor range is invalid")
        surface = anchor.get("surface")
        if not isinstance(surface, str) or not surface:
            raise ValueError("glossary surface anchor surface must be non-empty")
        key = (block_id, fragment_id, fragment_digest)
        ranges[key].append((start, end))
    for values in ranges.values():
        values.sort()
        if any(left[1] > right[0] for left, right in zip(values, values[1:])):
            raise ValueError("glossary surface anchors overlap")


def _base_material(entry: Mapping[str, object]) -> dict[str, object]:
    return {
        "schema_version": GLOSSARY_REVISION_SCHEMA,
        "entry_id": _entry_id(entry),
        "revision": 1,
        "entry": _entry_document(entry),
    }


def glossary_base_semantic_digest(entry: Mapping[str, object]) -> str:
    """Return the digest of the immutable Publication glossary baseline."""

    return hashlib.sha256(canonical_json_bytes(_base_material(entry))).hexdigest()


@dataclass(frozen=True)
class GlossaryRevision:
    """One immutable edit of one Publication glossary entry."""

    entry_id: str
    revision: int
    parent_semantic_digest: str
    entry: Mapping[str, JsonValue]
    provenance: Mapping[str, JsonValue]
    schema_version: str = GLOSSARY_REVISION_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != GLOSSARY_REVISION_SCHEMA:
            raise ValueError("unsupported glossary revision schema")
        entry_id = _require_identifier(self.entry_id, "glossary entry_id")
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 2
        ):
            raise ValueError("glossary revision must be at least 2")
        parent = _require_digest(
            self.parent_semantic_digest, "glossary parent_semantic_digest"
        )
        entry = freeze_json(self.entry, "glossary revision entry")
        provenance = freeze_json(self.provenance, "glossary revision provenance")
        if not isinstance(entry, Mapping):
            raise ValueError("glossary revision entry must be an object")
        if not isinstance(provenance, Mapping):
            raise ValueError("glossary revision provenance must be an object")
        _fragment_references, dependent_references = (
            _glossary_propagation_members(provenance)
        )
        if any(
            reference["entry_id"] == entry_id
            for reference in dependent_references
        ):
            raise ValueError(
                "glossary propagation cannot rewrite its initiating entry"
            )
        if entry.get("entry_id") != entry_id:
            raise ValueError("glossary revision entry_id does not match its entry")
        object.__setattr__(self, "entry_id", entry_id)
        object.__setattr__(self, "parent_semantic_digest", parent)
        object.__setattr__(self, "entry", entry)
        object.__setattr__(self, "provenance", provenance)

    @property
    def semantic_digest(self) -> str:
        return glossary_revision_semantic_digest(self)


def _revision_material(revision: GlossaryRevision) -> dict[str, object]:
    return {
        "schema_version": revision.schema_version,
        "entry_id": revision.entry_id,
        "revision": revision.revision,
        "parent_semantic_digest": revision.parent_semantic_digest,
        "entry": thaw_json(revision.entry),
        "provenance": thaw_json(revision.provenance),
    }


def glossary_revision_semantic_digest(revision: GlossaryRevision) -> str:
    return hashlib.sha256(
        canonical_json_bytes(_revision_material(revision))
    ).hexdigest()


def validate_glossary_revision(
    base_entry: Mapping[str, object], revision: GlossaryRevision
) -> None:
    """Reject source/identity/unknown-field changes in a glossary revision."""

    if not glossary_entry_is_editable(base_entry):
        raise ValueError("glossary entry does not have an editable contract")
    if revision.entry_id != _entry_id(base_entry):
        raise ValueError("glossary revision targets another entry")
    base = _entry_document(base_entry)
    candidate = thaw_json(revision.entry)
    _validate_surface_anchors(base)
    _validate_surface_anchors(candidate)
    if set(candidate) != set(base):
        raise ValueError("glossary revision changed entry fields")
    editable = {_translated_key(base), "definition"}
    for key in set(base) - editable:
        if candidate.get(key) != base.get(key):
            raise ValueError(f"glossary revision changed immutable field: {key}")
    for key in editable:
        if key is not None and not isinstance(candidate.get(key), str):
            raise ValueError(f"glossary field must remain a string: {key}")


@dataclass(frozen=True)
class GlossaryRevisionResolution:
    """The latest unambiguous edit; ``None`` means the Publication baseline."""

    entry_id: str
    base_digest: str
    selected: GlossaryRevision | None
    diagnostics: tuple[RevisionDiagnostic, ...]
    revisions: tuple[GlossaryRevision, ...]

    @property
    def selected_digest(self) -> str:
        return self.base_digest if self.selected is None else self.selected.semantic_digest

    @property
    def selected_entry(self) -> Mapping[str, JsonValue] | None:
        return None if self.selected is None else self.selected.entry

    @property
    def has_conflict(self) -> bool:
        return any(item.severity == "conflict" for item in self.diagnostics)


def resolve_glossary_revisions(
    base_entry: Mapping[str, object],
    revisions: Iterable[GlossaryRevision],
    *,
    initial_diagnostics: Iterable[RevisionDiagnostic] = (),
) -> GlossaryRevisionResolution:
    """Resolve one linear history without choosing a fork winner."""

    entry_id = _entry_id(base_entry)
    values = tuple(revisions)
    if any(not isinstance(item, GlossaryRevision) for item in values):
        raise ValueError("glossary revisions must contain GlossaryRevision values")
    if any(item.entry_id != entry_id for item in values):
        raise ValueError("glossary revisions contain a foreign entry")
    diagnostics = list(initial_diagnostics)
    base_digest = glossary_base_semantic_digest(base_entry)
    by_digest: dict[str, GlossaryRevision] = {}
    for revision in values:
        try:
            validate_glossary_revision(base_entry, revision)
        except ValueError as exc:
            diagnostics.append(
                RevisionDiagnostic(
                    code="immutable_glossary_field_changed",
                    message=str(exc),
                    revision=revision.revision,
                )
            )
            continue
        existing = by_digest.get(revision.semantic_digest)
        if existing is not None and existing != revision:
            diagnostics.append(
                RevisionDiagnostic(
                    code="semantic_digest_collision",
                    message="two distinct glossary revisions share a semantic digest",
                    severity="conflict",
                    revision=revision.revision,
                )
            )
        else:
            by_digest[revision.semantic_digest] = revision

    unique = tuple(sorted(by_digest.values(), key=lambda item: (item.revision, item.semantic_digest)))
    eligible: dict[str, list[GlossaryRevision]] = defaultdict(list)
    invalid: set[str] = set()
    for revision in unique:
        parent = revision.parent_semantic_digest
        if parent == base_digest:
            expected = 2
        else:
            parent_revision = by_digest.get(parent)
            if parent_revision is None:
                diagnostics.append(
                    RevisionDiagnostic(
                        code="dangling_revision",
                        message="glossary revision refers to an unavailable parent",
                        revision=revision.revision,
                    )
                )
                invalid.add(revision.semantic_digest)
                continue
            expected = parent_revision.revision + 1
        if revision.revision != expected:
            diagnostics.append(
                RevisionDiagnostic(
                    code="nonlinear_revision",
                    message="glossary revision number is not its parent's successor",
                    revision=revision.revision,
                )
            )
            invalid.add(revision.semantic_digest)
            continue
        eligible[parent].append(revision)

    selected: GlossaryRevision | None = None
    parent_digest = base_digest
    while True:
        children = [
            item
            for item in eligible.get(parent_digest, ())
            if item.semantic_digest not in invalid
        ]
        if not children:
            break
        if len(children) > 1:
            if all(item.entry == children[0].entry for item in children[1:]):
                continued = [
                    item for item in children
                    if eligible.get(item.semantic_digest)
                ]
                if len(continued) <= 1:
                    children = continued or [
                        min(children, key=lambda item: item.semantic_digest)
                    ]
                    diagnostics.append(
                        RevisionDiagnostic(
                            code="equivalent_revision_retry",
                            message=(
                                "equivalent glossary child revisions were "
                                "collapsed using successor lineage"
                            ),
                            revision=children[0].revision,
                        )
                    )
                else:
                    diagnostics.append(
                        RevisionDiagnostic(
                            code="revision_fork",
                            message=(
                                "equivalent glossary retries have multiple "
                                "continued lineages; selected their common parent"
                            ),
                            severity="conflict",
                            revision=children[0].revision,
                        )
                    )
                    break
            else:
                diagnostics.append(
                    RevisionDiagnostic(
                        code="revision_fork",
                        message=(
                            "multiple glossary child revisions conflict; "
                            "selected their common parent"
                        ),
                        severity="conflict",
                        revision=children[0].revision,
                    )
                )
                break
        selected = children[0]
        parent_digest = selected.semantic_digest

    return GlossaryRevisionResolution(
        entry_id=entry_id,
        base_digest=base_digest,
        selected=selected,
        diagnostics=tuple(diagnostics),
        revisions=unique,
    )


def glossary_revision_to_document(revision: GlossaryRevision) -> dict[str, object]:
    return _revision_material(revision)


def glossary_revision_from_document(value: object) -> GlossaryRevision:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version",
        "entry_id",
        "revision",
        "parent_semantic_digest",
        "entry",
        "provenance",
    }:
        raise ValueError("glossary revision has invalid fields")
    entry = value["entry"]
    provenance = value["provenance"]
    if not isinstance(entry, Mapping) or not isinstance(provenance, Mapping):
        raise ValueError("glossary revision entry and provenance must be objects")
    return GlossaryRevision(
        schema_version=_require_string(value["schema_version"], "schema_version"),
        entry_id=_require_identifier(value["entry_id"], "entry_id"),
        revision=value["revision"],  # type: ignore[arg-type]
        parent_semantic_digest=_require_digest(
            value["parent_semantic_digest"], "parent_semantic_digest"
        ),
        entry=entry,
        provenance=provenance,
    )


def glossary_revision_filename(revision: GlossaryRevision) -> str:
    return f"revision-{revision.revision:06d}-{revision.semantic_digest}.md"


def parse_glossary_revision_filename(filename: str) -> tuple[int, str]:
    match = _FILENAME_RE.fullmatch(Path(filename).name)
    if match is None:
        raise ValueError("invalid glossary revision filename")
    revision = int(match.group("revision"))
    if revision < 2:
        raise ValueError("glossary revision filename must be at least v2")
    return revision, match.group("digest")


def encode_glossary_revision(revision: GlossaryRevision) -> bytes:
    document = glossary_revision_to_document(revision)
    entry = document["entry"]
    if not isinstance(entry, dict) or not isinstance(entry.get("definition"), str):
        raise ValueError("glossary revision definition must be a string")
    definition = entry.pop("definition")
    metadata = canonical_json_bytes(document).decode("utf-8")
    return (
        f"{GLOSSARY_FRONT_MATTER_BEGIN}\n"
        f"{metadata}\n"
        f"{GLOSSARY_FRONT_MATTER_END}\n"
        f"{definition}"
    ).encode("utf-8")


def _decode_markdown_glossary_revision(value: str) -> GlossaryRevision:
    prefix = f"{GLOSSARY_FRONT_MATTER_BEGIN}\n"
    separator = f"\n{GLOSSARY_FRONT_MATTER_END}\n"
    payload = value[len(prefix) :]
    metadata_text, marker, definition = payload.partition(separator)
    if not marker:
        raise ValueError("glossary revision has unterminated JSON front matter")
    try:
        raw = strict_json_loads(metadata_text)
    except ValueError as exc:
        raise ValueError("glossary revision front matter is not valid JSON") from exc
    if canonical_json_bytes(raw) != metadata_text.encode("utf-8"):
        raise ValueError("glossary revision front matter is not canonical")
    if not isinstance(raw, Mapping) or not isinstance(raw.get("entry"), Mapping):
        raise ValueError("glossary revision front matter entry is invalid")
    entry = dict(raw["entry"])
    if "definition" in entry:
        raise ValueError("glossary revision front matter duplicates the Markdown body")
    entry["definition"] = definition
    document = dict(raw)
    document["entry"] = entry
    return glossary_revision_from_document(document)


def _decode_legacy_json_glossary_revision(value: str) -> GlossaryRevision:
    if not value.endswith("\n"):
        raise ValueError("legacy glossary revision JSON must end with a newline")
    try:
        raw = strict_json_loads(value[:-1])
    except (UnicodeError, ValueError) as exc:
        raise ValueError("glossary revision JSON is invalid") from exc
    if canonical_json_bytes(raw) != value[:-1].encode("utf-8"):
        raise ValueError("glossary revision JSON is not canonical")
    return glossary_revision_from_document(raw)


def decode_glossary_revision(
    value: str | bytes, *, filename: str | None = None
) -> GlossaryRevision:
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if not isinstance(value, str):
        raise ValueError("glossary revision must be text")
    markdown_envelope = value.startswith(f"{GLOSSARY_FRONT_MATTER_BEGIN}\n")
    revision = (
        _decode_markdown_glossary_revision(value)
        if markdown_envelope
        else _decode_legacy_json_glossary_revision(value)
    )
    if filename is not None:
        extension = Path(filename).suffix
        expected_extension = ".md" if markdown_envelope else ".json"
        if extension != expected_extension:
            raise ValueError(
                "glossary revision filename has the wrong format extension"
            )
        claimed_revision, claimed_digest = parse_glossary_revision_filename(filename)
        if claimed_revision != revision.revision:
            raise ValueError("glossary revision filename has the wrong revision")
        if claimed_digest != revision.semantic_digest:
            raise ValueError("glossary revision filename digest does not match")
    return revision


def read_glossary_revision(path: str | Path) -> GlossaryRevision:
    target = Path(path)
    try:
        return decode_glossary_revision(target.read_bytes(), filename=target.name)
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"cannot read glossary revision: {target}") from exc


def glossary_revision_storage_path(revision: GlossaryRevision) -> str:
    return f"{GLOSSARY_REVISION_DIRECTORY}/{glossary_revision_filename(revision)}"


def write_glossary_revision(project_root: str | Path, revision: GlossaryRevision) -> Path:
    """Create one immutable revision below ``glossary/``."""

    root = Path(project_root).resolve()
    target = root.joinpath(*glossary_revision_storage_path(revision).split("/"))
    payload = encode_glossary_revision(revision)
    if target.exists():
        if target.read_bytes() != payload:
            raise ValueError(f"immutable glossary revision already exists with other bytes: {target}")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor: int | None = None
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=target.parent
        )
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = None
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary_name, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ValueError(
                    "concurrent glossary publication produced conflicting bytes"
                )
        return target
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def resolve_glossary_revision_files(
    paths: Iterable[str | Path], *, base_entry: Mapping[str, object]
) -> GlossaryRevisionResolution:
    revisions: list[GlossaryRevision] = []
    diagnostics: list[RevisionDiagnostic] = []
    for raw_path in paths:
        path = Path(raw_path)
        claimed_revision: int | None = None
        try:
            claimed_revision, _ = parse_glossary_revision_filename(path.name)
        except ValueError:
            diagnostics.append(
                RevisionDiagnostic(
                    code="malformed_revision_filename",
                    message="ignored a file whose name is not a glossary revision filename",
                    paths=(str(path),),
                )
            )
            continue
        try:
            revision = read_glossary_revision(path)
        except ValueError as exc:
            diagnostics.append(
                RevisionDiagnostic(
                    code="malformed_revision",
                    message=f"ignored malformed glossary revision: {exc}",
                    revision=claimed_revision,
                    paths=(str(path),),
                )
            )
            continue
        if revision.entry_id != _entry_id(base_entry):
            diagnostics.append(
                RevisionDiagnostic(
                    code="foreign_glossary_entry",
                    message="ignored a glossary revision for another entry",
                    revision=revision.revision,
                    paths=(str(path),),
                )
            )
            continue
        revisions.append(revision)
    return resolve_glossary_revisions(
        base_entry, revisions, initial_diagnostics=diagnostics
    )


__all__ = [
    "GLOSSARY_FRONT_MATTER_BEGIN",
    "GLOSSARY_FRONT_MATTER_END",
    "GLOSSARY_REVISION_DIRECTORY",
    "GLOSSARY_REVISION_SCHEMA",
    "GLOSSARY_MENTIONS_SCHEMA",
    "GLOSSARY_PROPAGATION_SCHEMA",
    "GlossaryRevision",
    "GlossaryRevisionResolution",
    "decode_glossary_revision",
    "encode_glossary_revision",
    "glossary_base_semantic_digest",
    "glossary_entry_is_editable",
    "glossary_propagation_fragments",
    "glossary_propagation_glossary_revisions",
    "glossary_revision_filename",
    "glossary_revision_from_document",
    "glossary_revision_semantic_digest",
    "glossary_revision_storage_path",
    "glossary_revision_to_document",
    "parse_glossary_revision_filename",
    "read_glossary_revision",
    "resolve_glossary_revision_files",
    "resolve_glossary_revisions",
    "validate_glossary_revision",
    "write_glossary_revision",
]
