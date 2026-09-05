"""Reusable translation tasks that run inside an existing ``RunContext``."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from ac_document import RichBlockKind, literal_term_occurs, rich_block_to_document
from ac_jobs import (
    ArtifactRef,
    Awaiting,
    Failed,
    JsonValue,
    Paused,
    ResumeReason,
    RunContext,
    RunError,
    StoppedError,
    canonical_json_bytes,
    decode_artifact_ref,
    encode_artifact_ref,
)
from ac_llm import (
    RESUME_SCHEMA_VERSION,
    JsonOutput,
    LLMCompleted,
    LLMExecutionOptions,
    LLMFailed,
    LLMPaused,
    LLMRequest,
    LLMStopped,
    LLMTaskService,
    ModelSelection,
    ResumeInput,
    awaiting_from_pause,
    decode_resume_input,
    execute_or_resume_matching,
    run_error_from_failure,
)
from alc_render import (
    AnchorKind,
    FragmentAnchor,
    FragmentRevision,
    FragmentRevisionRef,
    Layer,
    anchor_block_from_rich_block,
    block_text_to_markdown,
    decode_fragment_revision,
    encode_fragment_revision,
    fragment_revision_ref,
    fragment_revision_ref_from_document,
    fragment_revision_ref_to_document,
    fragment_revision_storage_path,
    layer_from_document,
    layer_to_document,
    normalize_markdown,
    source_identity_from_rich_document,
)

from .atoms import (
    PROTECTED_ATOM_RESULT_SCHEMA,
    TEXT_SLOT_RESULT_SCHEMA,
    ProtectedAtomError,
    assemble_model_protected_translation,
    assemble_protected_translation,
    assemble_text_slot_translation,
    protected_atom_ids,
    protected_atom_part_groups,
    protected_atom_subplan,
    protected_result_document,
    source_protected_parts,
    text_slot_prompt_block,
    text_slot_values_from_parts,
)
from .contracts import (
    GLOSSARY_FALLBACK_SUMMARY_SCHEMA,
    GLOSSARY_RESULT_SCHEMA,
    LANGUAGE_RESULT_SCHEMA,
    LEGACY_GLOSSARY_RESULT_SCHEMA,
    TRANSLATION_RESULT_SCHEMA,
    TranslationSource,
)
from .prompts import (
    GLOSSARY_PROMPT_VERSION,
    GLOSSARY_SCHEMA,
    LANGUAGE_PROMPT_VERSION,
    LANGUAGE_SCHEMA,
    PROTECTED_ATOM_REVIEW_RESULT_SCHEMA,
    REVIEW_PROMPT_VERSION,
    TEXT_SLOT_REVIEW_RESULT_SCHEMA,
    TRANSLATION_PROMPT_VERSION,
    glossary_prompt,
    language_prompt,
    review_prompt,
    review_schema,
    translation_prompt,
    translation_schema,
)
from .source import (
    STRUCTURAL_FIGURE_PLACEHOLDER,
    TranslationSourceError,
    block_text,
    deterministic_language_samples,
    formula_identity_diagnostics,
    prompt_block,
    restore_translation_identity,
    same_primary_language,
    source_blocks,
    source_note_blocks,
    source_note_link_markdown,
    validate_translation_text,
)

REVIEW_SUPERVISION_SCHEMA = "alc.translate.review_supervision.v1"
OUTPUT_SUPERVISION_SCHEMA = "alc.translate.output_supervision.v1"
REVIEW_ACCEPTED_WINDOW_SCHEMA = "alc.translate.review_accepted_window.v1"
_TRANSLATION_FALLBACK_DIAGNOSTIC_SCHEMA = (
    "alc.translate.fallback_diagnostic.v1"
)
_TRANSLATION_PROVIDER_FALLBACK_DIAGNOSTIC_SCHEMA = (
    "alc.translate.provider_fallback_diagnostic.v1"
)
_PROVIDER_FALLBACK_MARKERS = frozenset(
    {
        "provider_transport",
        "transport",
        "provider_timeout",
        "timeout",
        "provider_unavailable",
        "unavailable",
        "provider_quota",
        "quota",
        "provider_rate_limit",
        "rate_limit",
        "provider_crash_retry_exhausted",
        "provider_circuit_open",
    }
)
_PROVIDER_HARD_STOP_MARKERS = frozenset(
    {
        "provider_authentication",
        "authentication",
        "provider_invalid_request",
        "invalid_request",
        "invalid_schema",
        "schema",
        "local_io",
        "local_io_error",
        "permission_denied",
        "host_authority_required",
        "corrupt_state",
        "stopped",
    }
)
_PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT = 2
_PROVIDER_FALLBACK_REASON_ORDER = (
    "provider_circuit_open",
    "provider_crash_retry_exhausted",
    "provider_timeout",
    "provider_transport",
    "provider_unavailable",
    "provider_quota",
    "provider_rate_limit",
    "timeout",
    "transport",
    "unavailable",
    "quota",
    "rate_limit",
)


class KeywordProvider(Protocol):
    def extract_keywords(
        self,
        context: RunContext,
        source: Any,
        *,
        structure: Any | None = None,
        section_ids: Sequence[str] | None = None,
        approx_count: int = 50,
        model: ModelSelection = ModelSelection(tier="medium"),
        resume_input: Mapping[str, JsonValue] | None = None,
        options: LLMExecutionOptions = LLMExecutionOptions(),
    ) -> Any: ...


@dataclass(frozen=True)
class LanguageResult:
    document_digest: str
    source_digest: str
    language_tag: str
    classification: str
    confidence: float
    target_language: str
    mode: str
    schema_version: str = LANGUAGE_RESULT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != LANGUAGE_RESULT_SCHEMA:
            raise ValueError("unsupported language result schema")
        if self.classification not in {"known", "mixed", "unknown"}:
            raise ValueError("language classification is invalid")
        if (
            not isinstance(self.confidence, (int, float))
            or isinstance(self.confidence, bool)
            or not 0 <= float(self.confidence) <= 1
        ):
            raise ValueError("language confidence is invalid")
        if self.mode not in {"enabled", "skipped"}:
            raise ValueError("translation mode is invalid")
        if any(
            not isinstance(item, str) or not item.strip()
            for item in (
                self.document_digest,
                self.source_digest,
                self.language_tag,
                self.target_language,
            )
        ):
            raise ValueError("language result contains an empty identity")

    def to_document(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "document_digest": self.document_digest,
            "source_digest": self.source_digest,
            "language_tag": self.language_tag,
            "classification": self.classification,
            "confidence": float(self.confidence),
            "target_language": self.target_language,
            "mode": self.mode,
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> "LanguageResult":
        _require_fields(
            value,
            {
                "schema_version",
                "document_digest",
                "source_digest",
                "language_tag",
                "classification",
                "confidence",
                "target_language",
                "mode",
            },
            "language result",
        )
        confidence = value["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(
            confidence, bool
        ):
            raise ValueError("language confidence must be a number")
        return cls(
            document_digest=_string(value, "document_digest"),
            source_digest=_string(value, "source_digest"),
            language_tag=_string(value, "language_tag"),
            classification=_string(value, "classification"),
            confidence=float(confidence),
            target_language=_string(value, "target_language"),
            mode=_string(value, "mode"),
            schema_version=_string(value, "schema_version"),
        )


@dataclass(frozen=True)
class GlossaryFallbackSummary:
    """Closed public accounting for recovered or omitted glossary entries."""

    recovered_term_ids: tuple[str, ...] = ()
    dropped_term_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    schema_version: str = GLOSSARY_FALLBACK_SUMMARY_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != GLOSSARY_FALLBACK_SUMMARY_SCHEMA:
            raise ValueError("unsupported glossary fallback summary schema")
        values = (
            ("recovered_term_ids", self.recovered_term_ids),
            ("dropped_term_ids", self.dropped_term_ids),
            ("reason_codes", self.reason_codes),
        )
        for name, items in values:
            if isinstance(items, (str, bytes)) or not isinstance(
                items, Sequence
            ):
                raise TypeError(f"{name} must be a string sequence")
            normalized = tuple(items)
            if (
                any(not isinstance(item, str) or not item for item in normalized)
                or len(set(normalized)) != len(normalized)
            ):
                raise ValueError(f"{name} must contain unique non-empty strings")
            object.__setattr__(self, name, normalized)
        if set(self.recovered_term_ids) & set(self.dropped_term_ids):
            raise ValueError("glossary fallback term IDs cannot overlap")
        if (
            bool(self.recovered_term_ids or self.dropped_term_ids)
            != bool(self.reason_codes)
        ):
            raise ValueError(
                "glossary fallback reasons must be present exactly for fallbacks"
            )

    @property
    def is_empty(self) -> bool:
        return not (
            self.recovered_term_ids
            or self.dropped_term_ids
            or self.reason_codes
        )

    def to_document(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "recovered_term_ids": list(self.recovered_term_ids),
            "dropped_term_ids": list(self.dropped_term_ids),
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_document(cls, value: Any) -> GlossaryFallbackSummary:
        document = _object(value, "glossary fallback summary")
        _require_fields(
            document,
            {
                "schema_version",
                "recovered_term_ids",
                "dropped_term_ids",
                "reason_codes",
            },
            "glossary fallback summary",
        )
        return cls(
            recovered_term_ids=_string_items(
                document["recovered_term_ids"], "recovered glossary term IDs"
            ),
            dropped_term_ids=_string_items(
                document["dropped_term_ids"], "dropped glossary term IDs"
            ),
            reason_codes=_string_items(
                document["reason_codes"], "glossary fallback reason codes"
            ),
            schema_version=_string(document, "schema_version"),
        )


@dataclass(frozen=True)
class GlossaryResult:
    document_digest: str
    source_digest: str
    target_language: str
    approx_count: int
    inventory_digest: str
    entries: tuple[Mapping[str, JsonValue], ...]
    schema_version: str = GLOSSARY_RESULT_SCHEMA
    fallback_summary: GlossaryFallbackSummary = dataclasses.field(
        default_factory=GlossaryFallbackSummary
    )

    def __post_init__(self) -> None:
        if self.schema_version != GLOSSARY_RESULT_SCHEMA:
            raise ValueError("unsupported glossary result schema")
        if (
            isinstance(self.approx_count, bool)
            or not isinstance(self.approx_count, int)
            or not 1 <= self.approx_count <= 200
        ):
            raise ValueError("glossary approx_count is invalid")
        if any(
            not isinstance(item, str) or not item
            for item in (
                self.document_digest,
                self.source_digest,
                self.target_language,
                self.inventory_digest,
            )
        ) or not _is_sha256(self.inventory_digest):
            raise ValueError("glossary identity is invalid")
        entries = tuple(dict(item) for item in self.entries)
        _validate_glossary_entries(entries)
        if not isinstance(self.fallback_summary, GlossaryFallbackSummary):
            raise TypeError("fallback_summary must be a GlossaryFallbackSummary")
        entry_ids = {str(item["term_id"]) for item in entries}
        if not set(self.fallback_summary.recovered_term_ids).issubset(entry_ids):
            raise ValueError("recovered glossary fallback entries are absent")
        if entry_ids & set(self.fallback_summary.dropped_term_ids):
            raise ValueError("dropped glossary fallback entries are present")
        object.__setattr__(self, "entries", entries)

    def to_document(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "document_digest": self.document_digest,
            "source_digest": self.source_digest,
            "target_language": self.target_language,
            "approx_count": self.approx_count,
            "inventory_digest": self.inventory_digest,
            "entries": [dict(item) for item in self.entries],
            "fallback_summary": self.fallback_summary.to_document(),
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> GlossaryResult:
        schema_version = _string(value, "schema_version")
        fields = {
            "schema_version",
            "document_digest",
            "source_digest",
            "target_language",
            "approx_count",
            "inventory_digest",
            "entries",
        }
        if schema_version == GLOSSARY_RESULT_SCHEMA:
            _require_fields(value, {*fields, "fallback_summary"}, "glossary result")
            fallback_summary = GlossaryFallbackSummary.from_document(
                value["fallback_summary"]
            )
        elif schema_version == LEGACY_GLOSSARY_RESULT_SCHEMA:
            _require_fields(value, fields, "legacy glossary result")
            fallback_summary = GlossaryFallbackSummary()
        else:
            raise ValueError("unsupported glossary result schema")
        entries = _mapping_list(value["entries"], "glossary entries")
        return cls(
            document_digest=_string(value, "document_digest"),
            source_digest=_string(value, "source_digest"),
            target_language=_string(value, "target_language"),
            approx_count=_integer(value, "approx_count"),
            inventory_digest=_string(value, "inventory_digest"),
            entries=tuple(entries),
            fallback_summary=fallback_summary,
        )


@dataclass(frozen=True)
class TranslationRevisionArtifact:
    revision: FragmentRevisionRef
    artifact: ArtifactRef

    def __post_init__(self) -> None:
        if not isinstance(self.revision, FragmentRevisionRef):
            raise ValueError("revision must be a FragmentRevisionRef")
        if not isinstance(self.artifact, ArtifactRef):
            raise ValueError("artifact must be an ArtifactRef")
        if self.artifact.media_type != "text/markdown":
            raise ValueError("translation revision artifact must be Markdown")

    def to_document(self) -> dict[str, JsonValue]:
        return {
            "revision": fragment_revision_ref_to_document(self.revision),
            "artifact": encode_artifact_ref(self.artifact),
        }

    @classmethod
    def from_document(
        cls, value: Mapping[str, Any]
    ) -> "TranslationRevisionArtifact":
        _require_fields(
            value, {"revision", "artifact"}, "translation revision artifact"
        )
        return cls(
            fragment_revision_ref_from_document(value["revision"]),
            decode_artifact_ref(value["artifact"]),
        )


@dataclass(frozen=True)
class TranslationResult:
    source_language: str
    target_language: str
    mode: str
    coverage: str
    layer: Layer
    revision_artifacts: tuple[TranslationRevisionArtifact, ...]
    schema_version: str = TRANSLATION_RESULT_SCHEMA

    def __post_init__(self) -> None:
        if self.schema_version != TRANSLATION_RESULT_SCHEMA:
            raise ValueError("unsupported translation result schema")
        if self.mode not in {"enabled", "skipped"}:
            raise ValueError("translation result mode is invalid")
        if self.coverage not in {"document", "selection"}:
            raise ValueError("translation result coverage is invalid")
        if not isinstance(self.source_language, str) or not self.source_language:
            raise ValueError("source_language must be non-empty")
        if not isinstance(self.target_language, str) or not self.target_language:
            raise ValueError("target_language must be non-empty")
        if not isinstance(self.layer, Layer):
            raise ValueError("layer must be an alc-render Layer")
        artifacts = tuple(self.revision_artifacts)
        if any(
            not isinstance(item, TranslationRevisionArtifact)
            for item in artifacts
        ):
            raise ValueError("revision_artifacts contains an invalid item")
        refs = tuple(item.revision for item in artifacts)
        if refs != self.layer.initial_revisions:
            raise ValueError(
                "revision artifacts must exactly match the ordered layer"
            )
        if self.mode == "skipped" and artifacts:
            raise ValueError("skipped translation result must have no revisions")
        object.__setattr__(self, "revision_artifacts", artifacts)

    def to_document(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "source_language": self.source_language,
            "target_language": self.target_language,
            "mode": self.mode,
            "coverage": self.coverage,
            "layer": layer_to_document(self.layer),
            "revision_artifacts": [
                item.to_document() for item in self.revision_artifacts
            ],
        }

    @classmethod
    def from_document(cls, value: Mapping[str, Any]) -> "TranslationResult":
        _require_fields(
            value,
            {
                "schema_version",
                "source_language",
                "target_language",
                "mode",
                "coverage",
                "layer",
                "revision_artifacts",
            },
            "translation result",
        )
        artifacts = _mapping_list(
            value["revision_artifacts"], "translation revision artifacts"
        )
        return cls(
            source_language=_string(value, "source_language"),
            target_language=_string(value, "target_language"),
            mode=_string(value, "mode"),
            coverage=_string(value, "coverage"),
            layer=layer_from_document(value["layer"]),
            revision_artifacts=tuple(
                TranslationRevisionArtifact.from_document(item)
                for item in artifacts
            ),
            schema_version=_string(value, "schema_version"),
        )


WorkflowResult: TypeAlias = (
    LanguageResult | GlossaryResult | TranslationResult | Paused | RunError
)


class TranslationWorkflowService:
    """Run replay-safe language, glossary, and translation tasks in a parent run."""

    def __init__(
        self,
        task_service: Any | None = None,
        keyword_provider: KeywordProvider | None = None,
    ) -> None:
        self.task_service = task_service or LLMTaskService()
        self.keyword_provider = keyword_provider

    def detect_language(
        self,
        context: RunContext,
        source: TranslationSource,
        *,
        target_language: str,
        model: ModelSelection = ModelSelection(),
        execution: LLMExecutionOptions = LLMExecutionOptions(),
        resume_input: ResumeInput | None = None,
        artifact_prefix: str = "language",
    ) -> LanguageResult | Paused | RunError:
        artifact_id = f"{artifact_prefix}/result"
        existing = context.artifacts.find(artifact_id)
        if existing is not None:
            return LanguageResult.from_document(
                _read_json_artifact(context, existing, "language result")
            )
        request = LLMRequest(
            _task_id(
                "language",
                {
                    "document_digest": source.document_digest,
                    "target_language": target_language,
                    "prompt_contract": LANGUAGE_PROMPT_VERSION,
                },
            ),
            language_prompt(deterministic_language_samples(source)),
            JsonOutput(LANGUAGE_SCHEMA, repair="format"),
            model,
        )
        generated = _validated_generation(
            self.task_service,
            context,
            request,
            validator=_validate_language_output,
            candidate_id=f"language/{artifact_prefix}/result.json",
            resume_input=resume_input,
            options=execution,
            stopped_message="language detection stopped",
        )
        if isinstance(generated, (Paused, RunError)):
            return generated
        if isinstance(generated, _InvalidGeneratedOutput):
            return _output_supervision(
                context,
                artifact_prefix=artifact_prefix,
                stage="language",
                error=generated.error,
                candidate_path=generated.candidate_path,
            )
        value = generated
        classification = str(value["classification"])
        language_tag = str(value["language_tag"])
        mode = (
            "skipped"
            if classification == "known"
            and same_primary_language(language_tag, target_language)
            else "enabled"
        )
        result = LanguageResult(
            document_digest=source.document_digest,
            source_digest=source.source_digest,
            language_tag=language_tag,
            classification=classification,
            confidence=float(value["confidence"]),
            target_language=target_language,
            mode=mode,
        )
        context.artifacts.publish_json(artifact_id, result.to_document())
        return result

    def build_glossary(
        self,
        context: RunContext,
        source: TranslationSource,
        *,
        language: LanguageResult,
        target_language: str,
        keyword_structure: Any | None = None,
        keyword_section_ids: Sequence[str] | None = None,
        approx_count: int = 50,
        model: ModelSelection = ModelSelection(),
        execution: LLMExecutionOptions = LLMExecutionOptions(),
        resume_input: ResumeInput | None = None,
        term_input_budget_bytes: int = 32_000,
        artifact_prefix: str = "glossary",
    ) -> GlossaryResult | Paused | RunError:
        _validate_language_binding(language, source, target_language)
        artifact_id = f"{artifact_prefix}/result"
        existing = context.artifacts.find(artifact_id)
        if existing is not None:
            document = _read_json_artifact(
                context, existing, "glossary result"
            )
            result = GlossaryResult.from_document(document)
            if document.get("schema_version") == LEGACY_GLOSSARY_RESULT_SCHEMA:
                result = dataclasses.replace(
                    result,
                    fallback_summary=_load_legacy_glossary_fallback_summary(
                        context,
                        source=source,
                        approx_count=approx_count,
                        target_language=target_language,
                        term_input_budget_bytes=term_input_budget_bytes,
                        artifact_prefix=artifact_prefix,
                    ),
                )
            return result
        inventory_id = f"{artifact_prefix}/keyword-inventory"
        inventory_ref = context.artifacts.find(inventory_id)
        if inventory_ref is None:
            if self.keyword_provider is None:
                return RunError(
                    "keyword_provider_missing",
                    "glossary generation requires an ac-document keyword provider",
                )
            try:
                keyword_options: dict[str, Any] = {}
                if keyword_structure is not None:
                    keyword_options["structure"] = keyword_structure
                    keyword_options["section_ids"] = keyword_section_ids
                keyword_outcome = self.keyword_provider.extract_keywords(
                    context,
                    source.rich,
                    approx_count=approx_count,
                    model=model,
                    resume_input=(
                        context.resume_input
                        if context.resume_input is not None
                        else None
                    ),
                    options=execution,
                    **keyword_options,
                )
                if isinstance(keyword_outcome, Paused):
                    return keyword_outcome
                if isinstance(keyword_outcome, Failed):
                    return keyword_outcome.error
                raw_inventory = keyword_outcome
                inventory = _keyword_inventory_document(raw_inventory)
                _validate_keyword_inventory(
                    inventory, source=source, approx_count=approx_count
                )
            except StoppedError:
                raise
            except Exception as exc:
                code = getattr(exc, "code", "keyword_extraction_failed")
                return RunError(str(code), str(exc))
            inventory_ref = context.artifacts.publish_json(
                inventory_id, inventory
            )
        else:
            inventory = _read_json_artifact(
                context, inventory_ref, "keyword inventory"
            )
            _validate_keyword_inventory(
                inventory, source=source, approx_count=approx_count
            )
        terms = _mapping_list(inventory["terms"], "keyword terms")
        try:
            windows = _glossary_windows(
                terms,
                target_language=target_language,
                budget_bytes=term_input_budget_bytes,
            )
        except TranslationWorkflowError as exc:
            return RunError(exc.code, str(exc))
        entries: list[dict[str, JsonValue]] = []
        for ordinal, window in enumerate(windows):
            window_id = f"{artifact_prefix}/windows/{ordinal:04d}"
            fallback_id = f"{artifact_prefix}/fallbacks/{ordinal:04d}"
            candidate_id = f"glossary/{window_id}.json"
            candidate_path = context.working.find_candidate(candidate_id)
            window_ref = context.artifacts.find(window_id)
            if candidate_path is None and window_ref is not None:
                window_output = _read_json_artifact(
                    context, window_ref, "glossary window"
                )
            else:
                request = LLMRequest(
                    _task_id(
                        "glossary",
                        {
                            "inventory_digest": inventory["inventory_digest"],
                            "term_ids": [item["term_id"] for item in window],
                            "target_language": target_language,
                            "window_ordinal": ordinal,
                            "prompt_contract": GLOSSARY_PROMPT_VERSION,
                            "input_budget_bytes": term_input_budget_bytes,
                        },
                    ),
                    glossary_prompt(
                        terms=window,
                        target_language=target_language,
                        window_ordinal=ordinal,
                    ),
                    JsonOutput(GLOSSARY_SCHEMA, repair="format"),
                    model,
                )
                generated = _validated_generation(
                    self.task_service,
                    context,
                    request,
                    validator=lambda value, window=window: _validated_glossary_document(
                        value, window
                    ),
                    candidate_id=candidate_id,
                    resume_input=resume_input,
                    options=execution,
                    stopped_message="glossary generation stopped",
                )
                if isinstance(generated, (Paused, RunError)):
                    return generated
                if isinstance(generated, _InvalidGeneratedOutput):
                    if generated.error.code in {
                        "glossary_control_character_invalid",
                        "glossary_translation_math_markup_invalid",
                    }:
                        try:
                            fallback, recovered_term_ids, dropped_term_ids = (
                                _salvaged_glossary_fallback(
                                    generated.candidate, window
                                )
                            )
                        except TranslationWorkflowError as exc:
                            return _output_supervision(
                                context,
                                artifact_prefix=artifact_prefix,
                                stage=f"glossary-{ordinal:04d}",
                                error=exc,
                                candidate_path=generated.candidate_path,
                            )
                        _publish_glossary_fallback(
                            context,
                            fallback_id,
                            recovered_term_ids=recovered_term_ids,
                            dropped_term_ids=dropped_term_ids,
                            reason_codes=[generated.error.code],
                        )
                        entries.extend(fallback)
                        continue
                    return _output_supervision(
                        context,
                        artifact_prefix=artifact_prefix,
                        stage=f"glossary-{ordinal:04d}",
                        error=generated.error,
                        candidate_path=generated.candidate_path,
                    )
                window_output = generated
                context.artifacts.publish_json(window_id, window_output)
            try:
                entries.extend(
                    _validate_glossary_window(window_output, window)
                )
            except TranslationWorkflowError as exc:
                error_path = candidate_path or (
                    context.run_directory / window_ref.relative_path
                )
                if exc.code in {
                    "glossary_control_character_invalid",
                    "glossary_translation_math_markup_invalid",
                }:
                    try:
                        fallback, recovered_term_ids, dropped_term_ids = (
                            _salvaged_glossary_fallback(
                                window_output, window
                            )
                        )
                    except TranslationWorkflowError as fallback_error:
                        return _candidate_run_error(fallback_error, error_path)
                    _publish_glossary_fallback(
                        context,
                        fallback_id,
                        recovered_term_ids=recovered_term_ids,
                        dropped_term_ids=dropped_term_ids,
                        reason_codes=[exc.code],
                    )
                    entries.extend(fallback)
                    continue
                return _candidate_run_error(exc, error_path)
        result = GlossaryResult(
            document_digest=source.document_digest,
            source_digest=source.source_digest,
            target_language=target_language,
            approx_count=approx_count,
            inventory_digest=_string(inventory, "inventory_digest"),
            entries=tuple(entries),
            fallback_summary=_load_glossary_fallback_summary(
                context,
                terms=terms,
                window_count=len(windows),
                artifact_prefix=artifact_prefix,
            ),
        )
        context.artifacts.publish_json(artifact_id, result.to_document())
        return result

    def translate_blocks(
        self,
        context: RunContext,
        source: TranslationSource,
        *,
        language: LanguageResult,
        glossary: GlossaryResult,
        target_language: str,
        model: ModelSelection = ModelSelection(),
        execution: LLMExecutionOptions = LLMExecutionOptions(),
        resume_input: ResumeInput | None = None,
        input_budget_bytes: int = 32_000,
        block_ids: Sequence[str] | None = None,
        artifact_prefix: str = "translation",
    ) -> TranslationResult | Paused | RunError:
        _validate_language_binding(language, source, target_language)
        _validate_glossary_binding(glossary, source, target_language)
        all_blocks = source_blocks(source)
        try:
            blocks = _select_blocks(all_blocks, block_ids)
        except TranslationWorkflowError as exc:
            return RunError(exc.code, str(exc))
        units = _translation_units(source, blocks)
        coverage = "document" if block_ids is None else "selection"
        artifact_id = f"{artifact_prefix}/result"
        existing = context.artifacts.find(artifact_id)
        if existing is not None:
            result = TranslationResult.from_document(
                _read_json_artifact(context, existing, "translation result")
            )
            _validate_translation_result(
                context,
                result,
                source,
                language,
                target_language,
                units,
                expected_coverage=coverage,
            )
            return result
        if language.mode == "skipped":
            result = TranslationResult(
                source_language=language.language_tag,
                target_language=target_language,
                mode="skipped",
                coverage=coverage,
                layer=Layer(
                    source_identity_from_rich_document(source.rich),
                    "alc-translate",
                    (),
                ),
                revision_artifacts=(),
            )
            context.artifacts.publish_json(artifact_id, result.to_document())
            return result
        model_blocks = _model_translation_blocks(units)
        try:
            model_units, unit_plans = _bounded_model_translation_units(
                model_blocks,
                glossary=glossary.entries,
                target_language=target_language,
                language=language,
                budget_bytes=input_budget_bytes,
            )
            windows = _translation_windows(
                model_units,
                glossary=glossary.entries,
                target_language=target_language,
                language=language,
                budget_bytes=input_budget_bytes,
            )
        except TranslationWorkflowError as exc:
            return RunError(exc.code, str(exc))
        translations: list[dict[str, Any]] = []
        fallback_units: dict[str, str] = {}
        consecutive_provider_window_failures = 0
        global_provider_fallback_reason: str | None = None
        accepted_documents: dict[int, Mapping[str, Any]] = {}
        for accepted_ordinal in range(len(model_units)):
            accepted_id = (
                f"{artifact_prefix}/windows/{accepted_ordinal:04d}/accepted"
            )
            accepted_ref = context.artifacts.find(accepted_id)
            if accepted_ref is None:
                break
            accepted_documents[accepted_ordinal] = _read_json_artifact(
                context, accepted_ref, "accepted translation window"
            )
        accepted_documents = _migrate_legacy_accepted_list_windows(
            accepted_documents,
            windows,
            unit_plans,
        )
        for ordinal, window in enumerate(windows):
            draft_id = f"{artifact_prefix}/windows/{ordinal:04d}/draft"
            accepted_id = f"{artifact_prefix}/windows/{ordinal:04d}/accepted"
            fallback_id = f"{artifact_prefix}/windows/{ordinal:04d}/fallback"
            accepted_doc = accepted_documents.get(ordinal)
            if (
                accepted_doc is None
                and global_provider_fallback_reason is not None
            ):
                fallback, source_fallback_ids = _persist_source_fallback_window(
                    context,
                    window,
                    accepted_id=accepted_id,
                    fallback_id=fallback_id,
                    reason_code=global_provider_fallback_reason,
                )
                fallback_units.update(
                    (block_id, "source_text")
                    for block_id in source_fallback_ids
                )
                translations.extend(fallback)
                continue
            if accepted_doc is not None:
                (
                    accepted_payload,
                    accepted_fallback_document,
                    accepted_provider_document,
                ) = _unpack_review_accepted_window(accepted_doc)
                try:
                    accepted = _validate_accepted_window(
                        accepted_payload, window
                    )
                except TranslationWorkflowError as exc:
                    if exc.code == "translation_coverage_invalid":
                        return RunError(exc.code, str(exc))
                    fallback, source_fallback_ids = (
                        _salvaged_translation_fallback(
                            window, candidate=accepted_payload
                        )
                    )
                    _publish_translation_fallback(
                        context,
                        fallback_id,
                        source_text_block_ids=source_fallback_ids,
                        review_skipped_block_ids=[],
                        reason_codes=[exc.code],
                    )
                    fallback_units.update(
                        (block_id, "source_text")
                        for block_id in source_fallback_ids
                    )
                    translations.extend(fallback)
                    consecutive_provider_window_failures = 0
                    continue
                if accepted_fallback_document is None:
                    fallback_reason_codes = _load_translation_fallback(
                        context, fallback_id, fallback_units
                    )
                else:
                    fallback_reason_codes = _apply_translation_fallback_document(
                        accepted_fallback_document, fallback_units
                    )
                    _publish_translation_fallback_document(
                        context, fallback_id, accepted_fallback_document
                    )
                if accepted_provider_document is not None:
                    _publish_translation_provider_failure_document(
                        context,
                        f"{fallback_id}-provider",
                        accepted_provider_document,
                    )
                translations.extend(accepted)
                replayed_provider_reason = _provider_reason_from_codes(
                    fallback_reason_codes
                )
                if replayed_provider_reason is None:
                    consecutive_provider_window_failures = 0
                else:
                    consecutive_provider_window_failures += 1
                    if (
                        consecutive_provider_window_failures
                        >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                    ):
                        global_provider_fallback_reason = (
                            replayed_provider_reason
                        )
                continue
            candidate_id = f"translation/{draft_id}.json"
            candidate_path = context.working.find_candidate(candidate_id)
            draft_ref = context.artifacts.find(draft_id)
            if candidate_path is None and draft_ref is not None:
                draft_doc = _read_json_artifact(
                    context, draft_ref, "translation draft"
                )
            else:
                prompt_blocks = [
                    text_slot_prompt_block(item) for item in window
                ]
                request = LLMRequest(
                    _task_id(
                        "translation",
                        {
                            "document_digest": source.document_digest,
                            "block_ids": [item["block_id"] for item in window],
                            "target_language": target_language,
                            "glossary_digest": _digest(
                                glossary.to_document()
                            ),
                            "window_ordinal": ordinal,
                            "prompt_contract": TRANSLATION_PROMPT_VERSION,
                            "input_budget_bytes": input_budget_bytes,
                        },
                    ),
                    translation_prompt(
                        blocks=prompt_blocks,
                        glossary=_window_glossary(window, glossary.entries),
                        target_language=target_language,
                        language_result=language.to_document(),
                        window_ordinal=ordinal,
                    ),
                    JsonOutput(
                        translation_schema(prompt_blocks), repair="format"
                    ),
                    model,
                )
                generated = _validated_generation(
                    self.task_service,
                    context,
                    request,
                    validator=(
                        lambda value, window=window: (
                            _validated_protected_draft_document(value, window)
                        )
                    ),
                    candidate_id=candidate_id,
                    resume_input=resume_input,
                    options=execution,
                    stopped_message="block translation stopped",
                    retry_request_factory=(
                        lambda original, error, candidate, window=window,
                        window_ordinal=ordinal: (
                            _protected_translation_retry_request(
                                original,
                                error,
                                candidate,
                                window,
                                glossary=_window_glossary(
                                    window, glossary.entries
                                ),
                                target_language=target_language,
                                language=language,
                                window_ordinal=window_ordinal,
                            )
                        )
                    ),
                    retry_candidate_merger=(
                        lambda first, second, window=window: (
                            _merge_protected_translation_candidates(
                                first, second, window
                            )
                        )
                    ),
                )
                if isinstance(generated, Paused):
                    provider_reason = _provider_fallback_reason(generated)
                    if provider_reason is None:
                        return generated
                    consecutive_provider_window_failures += 1
                    if (
                        consecutive_provider_window_failures
                        >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                    ):
                        global_provider_fallback_reason = provider_reason
                    _publish_translation_provider_failure(
                        context,
                        f"{fallback_id}-provider",
                        outcome=generated,
                        model=model,
                        reason_code=provider_reason,
                        stage="translation",
                        window_ordinal=ordinal,
                        consecutive_window_failures=(
                            consecutive_provider_window_failures
                        ),
                        global_fallback_triggered=(
                            global_provider_fallback_reason is not None
                        ),
                        remaining_windows_skipped=(
                            len(windows) - ordinal - 1
                            if global_provider_fallback_reason is not None
                            else 0
                        ),
                    )
                    fallback, source_fallback_ids = (
                        _persist_source_fallback_window(
                            context,
                            window,
                            accepted_id=accepted_id,
                            fallback_id=fallback_id,
                            reason_code=provider_reason,
                        )
                    )
                    fallback_units.update(
                        (block_id, "source_text")
                        for block_id in source_fallback_ids
                    )
                    translations.extend(fallback)
                    continue
                if isinstance(generated, RunError):
                    provider_reason = _provider_fallback_reason(generated)
                    if provider_reason is None:
                        return generated
                    consecutive_provider_window_failures += 1
                    if (
                        consecutive_provider_window_failures
                        >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                    ):
                        global_provider_fallback_reason = provider_reason
                    _publish_translation_provider_failure(
                        context,
                        f"{fallback_id}-provider",
                        outcome=generated,
                        model=model,
                        reason_code=provider_reason,
                        stage="translation",
                        window_ordinal=ordinal,
                        consecutive_window_failures=(
                            consecutive_provider_window_failures
                        ),
                        global_fallback_triggered=(
                            global_provider_fallback_reason is not None
                        ),
                        remaining_windows_skipped=(
                            len(windows) - ordinal - 1
                            if global_provider_fallback_reason is not None
                            else 0
                        ),
                    )
                    fallback, source_fallback_ids = (
                        _persist_source_fallback_window(
                            context,
                            window,
                            accepted_id=accepted_id,
                            fallback_id=fallback_id,
                            reason_code=provider_reason,
                        )
                    )
                    fallback_units.update(
                        (block_id, "source_text")
                        for block_id in source_fallback_ids
                    )
                    translations.extend(fallback)
                    continue
                if isinstance(generated, _InvalidGeneratedOutput):
                    fallback, source_fallback_ids = (
                        _salvaged_translation_fallback(
                            window, candidate=generated.candidate
                        )
                    )
                    _publish_translation_fallback(
                        context,
                        fallback_id,
                        source_text_block_ids=source_fallback_ids,
                        review_skipped_block_ids=[],
                        reason_codes=[generated.error.code],
                    )
                    fallback_units.update(
                        (block_id, "source_text")
                        for block_id in source_fallback_ids
                    )
                    context.artifacts.publish_json(
                        accepted_id, _translation_result_document(fallback)
                    )
                    translations.extend(fallback)
                    continue
                draft_doc = generated
                context.artifacts.publish_json(draft_id, draft_doc)
            # A draft artifact proves provider delivery for this window. A
            # later review failure may count the window again below.
            consecutive_provider_window_failures = 0
            window_provider_failure_reason: str | None = None
            window_provider_failure_document: dict[str, Any] | None = None
            try:
                draft = _validate_draft_window(draft_doc, window)
            except TranslationWorkflowError as exc:
                fallback, source_fallback_ids = (
                    _salvaged_translation_fallback(
                        window, candidate=draft_doc
                    )
                )
                _publish_translation_fallback(
                    context,
                    fallback_id,
                    source_text_block_ids=source_fallback_ids,
                    review_skipped_block_ids=[],
                    reason_codes=[exc.code],
                )
                fallback_units.update(
                    (block_id, "source_text")
                    for block_id in source_fallback_ids
                )
                context.artifacts.publish_json(
                    accepted_id, _translation_result_document(fallback)
                )
                translations.extend(fallback)
                continue
            if any(
                item.get("schema_version") != PROTECTED_ATOM_RESULT_SCHEMA
                for item in draft
            ):
                # Drafts were never accepted model artifacts. Replay a valid
                # pre-v13 draft only as explicit legacy input, skip a new
                # protected-atom review, and record that review did not run.
                fallback, source_fallback_ids = _salvaged_translation_fallback(
                    window, candidate=draft_doc
                )
                legacy_ids = [str(item["block_id"]) for item in window]
                _publish_translation_fallback(
                    context,
                    fallback_id,
                    source_text_block_ids=source_fallback_ids,
                    review_skipped_block_ids=legacy_ids,
                    reason_codes=["translation_legacy_draft_replay"],
                )
                fallback_units.update(
                    (block_id, "source_text")
                    for block_id in source_fallback_ids
                )
                fallback_units.update(
                    (block_id, "review_skipped")
                    for block_id in legacy_ids
                    if block_id not in source_fallback_ids
                )
                context.artifacts.publish_json(
                    accepted_id, _translation_result_document(fallback)
                )
                translations.extend(fallback)
                continue
            try:
                review_windows = _translation_review_windows(
                    window,
                    draft,
                    glossary=glossary.entries,
                    target_language=target_language,
                    window_ordinal=ordinal,
                    budget_bytes=input_budget_bytes,
                )
            except TranslationWorkflowError as exc:
                return RunError(exc.code, str(exc))
            else:
                reviewed = []
                review_skipped_ids: list[str] = []
                review_reason_codes: list[str] = []
                split_review = len(review_windows) > 1
                for review_ordinal, (
                    review_blocks,
                    review_draft,
                ) in enumerate(review_windows):
                    review_draft_digest = _digest(review_draft)[:24]
                    review_accepted_id = (
                        f"{artifact_prefix}/windows/{ordinal:04d}/reviews/"
                        f"{review_ordinal:04d}/{review_draft_digest}/accepted"
                    )
                    if split_review:
                        review_accepted_ref = context.artifacts.find(
                            review_accepted_id
                        )
                        if review_accepted_ref is not None:
                            review_accepted_doc = _read_json_artifact(
                                context,
                                review_accepted_ref,
                                "accepted translation review subwindow",
                            )
                            try:
                                (
                                    review_accepted_payload,
                                    review_fallback_document,
                                    review_provider_document,
                                ) = _unpack_review_accepted_window(
                                    review_accepted_doc
                                )
                                accepted_review = _validate_accepted_window(
                                    review_accepted_payload,
                                    review_blocks,
                                )
                            except TranslationWorkflowError as exc:
                                review_ids = [
                                    str(item["block_id"])
                                    for item in review_blocks
                                ]
                                reviewed.extend(review_draft)
                                review_skipped_ids.extend(review_ids)
                                review_reason_codes.append(exc.code)
                                fallback_units.update(
                                    (block_id, "review_skipped")
                                    for block_id in review_ids
                                )
                            else:
                                if review_fallback_document is not None:
                                    review_reason_codes.extend(
                                        _apply_translation_fallback_document(
                                            review_fallback_document,
                                            fallback_units,
                                        )
                                    )
                                    review_skipped_ids.extend(
                                        _translation_fallback_entries(
                                            review_fallback_document
                                        )[1]
                                    )
                                if review_provider_document is not None:
                                    window_provider_failure_document = (
                                        review_provider_document
                                    )
                                    window_provider_failure_reason = str(
                                        review_provider_document["reason_code"]
                                    )
                                reviewed.extend(accepted_review)
                            continue
                    review_error: tuple[str, str] | None = None
                    reviewed_window: list[dict[str, str]] | None = None
                    model_review_blocks = [
                        text_slot_prompt_block(item)
                        for item in review_blocks
                    ]
                    try:
                        review_translations = [
                            _review_text_slot_projection(block, item)
                            for block, item in zip(
                                review_blocks, review_draft, strict=True
                            )
                        ]
                    except TranslationWorkflowError as exc:
                        review_error = (exc.code, str(exc))
                        review_text = ""
                    else:
                        review_text = review_prompt(
                            blocks=model_review_blocks,
                            translations=review_translations,
                            glossary=_window_glossary(
                                review_blocks, glossary.entries
                            ),
                            target_language=target_language,
                            window_ordinal=ordinal,
                        )
                    if review_error is not None:
                        pass
                    elif len(review_text.encode("utf-8")) > input_budget_bytes:
                        block_id = review_blocks[0].get(
                            "block_id", "<unknown>"
                        )
                        review_error = (
                            "translation_review_exceeds_input_budget",
                            f"review block {block_id} exceeds the "
                            f"{input_budget_bytes}-byte translation input "
                            "budget",
                        )
                    else:
                        task_identity = {
                            "document_digest": source.document_digest,
                            "block_ids": [
                                item["block_id"] for item in review_blocks
                            ],
                            "draft_digest": _digest(review_draft),
                            "target_language": target_language,
                            "window_ordinal": ordinal,
                            "prompt_contract": REVIEW_PROMPT_VERSION,
                        }
                        if split_review:
                            task_identity["review_subwindow_ordinal"] = (
                                review_ordinal
                            )
                        review_request = LLMRequest(
                            _task_id("translation-review", task_identity),
                            review_text,
                            JsonOutput(
                                review_schema(model_review_blocks),
                                repair="format",
                            ),
                            model,
                        )
                        review_candidate = (
                            f"translation/{artifact_prefix}/windows/"
                            f"{ordinal:04d}/review.json"
                            if not split_review
                            else (
                                f"translation/{artifact_prefix}/windows/"
                                f"{ordinal:04d}/reviews/"
                                f"{review_ordinal:04d}.json"
                            )
                        )
                        review_generated = _validated_generation(
                            self.task_service,
                            context,
                            review_request,
                            validator=lambda value, draft=review_draft,
                            blocks=review_blocks: _apply_text_slot_review(
                                value, draft, blocks
                            ),
                            candidate_id=review_candidate,
                            resume_input=resume_input,
                            options=execution,
                            stopped_message="translation review stopped",
                        )
                        if isinstance(review_generated, (Paused, RunError)):
                            provider_reason = _provider_fallback_reason(
                                review_generated
                            )
                            if provider_reason is None:
                                return review_generated
                            window_provider_failure_reason = provider_reason
                            window_provider_failure_document = (
                                _translation_provider_failure_document(
                                    outcome=review_generated,
                                    model=model,
                                    reason_code=provider_reason,
                                    stage="review",
                                    window_ordinal=ordinal,
                                    consecutive_window_failures=(
                                        consecutive_provider_window_failures
                                        + 1
                                    ),
                                    global_fallback_triggered=(
                                        consecutive_provider_window_failures
                                        + 1
                                        >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                                    ),
                                    remaining_windows_skipped=(
                                        len(windows) - ordinal - 1
                                        if consecutive_provider_window_failures
                                        + 1
                                        >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                                        else 0
                                    ),
                                )
                            )
                            review_error = (
                                provider_reason,
                                "translation review provider delivery is "
                                "unavailable",
                            )
                        elif isinstance(
                            review_generated, _InvalidGeneratedOutput
                        ):
                            review_error = (
                                review_generated.error.code,
                                str(review_generated.error),
                            )
                        else:
                            reviewed_window = review_generated
                    if review_error is not None:
                        reviewed_window = list(review_draft)
                        review_ids = [
                            str(item["block_id"]) for item in review_blocks
                        ]
                        review_skipped_ids.extend(review_ids)
                        review_reason_codes.append(review_error[0])
                        fallback_units.update(
                            (block_id, "review_skipped")
                            for block_id in review_ids
                        )
                    assert reviewed_window is not None
                    if split_review:
                        review_fallback_document = (
                            _translation_fallback_document(
                                source_text_block_ids=[],
                                review_skipped_block_ids=review_ids,
                                reason_codes=review_reason_codes[-1:],
                            )
                            if review_error is not None
                            else None
                        )
                        context.artifacts.publish_json(
                            review_accepted_id,
                            _review_accepted_window_document(
                                _translation_result_document(reviewed_window),
                                fallback_document=review_fallback_document,
                                provider_failure_document=(
                                    window_provider_failure_document
                                    if review_error is not None
                                    else None
                                ),
                            ),
                        )
                    reviewed.extend(reviewed_window)
            fallback_document = (
                _translation_fallback_document(
                    source_text_block_ids=[],
                    review_skipped_block_ids=review_skipped_ids,
                    reason_codes=review_reason_codes,
                )
                if review_skipped_ids
                else None
            )
            accepted_doc = _review_accepted_window_document(
                _translation_result_document(reviewed),
                fallback_document=fallback_document,
                provider_failure_document=window_provider_failure_document,
            )
            context.artifacts.publish_json(accepted_id, accepted_doc)
            if review_skipped_ids:
                assert fallback_document is not None
                _publish_translation_fallback_document(
                    context, fallback_id, fallback_document
                )
            translations.extend(reviewed)
            if window_provider_failure_reason is not None:
                consecutive_provider_window_failures += 1
                if (
                    consecutive_provider_window_failures
                    >= _PROVIDER_CONSECUTIVE_WINDOW_FAILURE_LIMIT
                ):
                    global_provider_fallback_reason = (
                        window_provider_failure_reason
                    )
                assert window_provider_failure_document is not None
                _publish_translation_provider_failure_document(
                    context,
                    f"{fallback_id}-provider",
                    window_provider_failure_document,
                )
        (
            collapsed_translations,
            post_collapse_fallback_ids,
        ) = _collapse_model_translation_units_with_fallback(
            model_blocks,
            unit_plans,
            translations,
        )
        fallback_blocks = _collapse_translation_fallbacks(
            unit_plans, fallback_units
        )
        if post_collapse_fallback_ids:
            _publish_translation_fallback(
                context,
                f"{artifact_prefix}/post-collapse/fallback",
                source_text_block_ids=post_collapse_fallback_ids,
                review_skipped_block_ids=[],
                reason_codes=["translation_source_identity_invalid"],
            )
            fallback_blocks.update(
                (block_id, "source_text")
                for block_id in post_collapse_fallback_ids
            )
        merged_translations = _merge_programmatic_translations(
            units,
            collapsed_translations,
        )
        protected_atom_block_ids = _protected_original_block_ids(
            unit_plans, translations
        )
        result = _publish_translation_result(
            context,
            source,
            translations=merged_translations,
            units=units,
            source_language=language.language_tag,
            target_language=target_language,
            artifact_prefix=artifact_prefix,
            coverage=coverage,
            fallback_kinds=fallback_blocks,
            protected_atom_block_ids=protected_atom_block_ids,
        )
        _validate_translation_result(
            context,
            result,
            source,
            language,
            target_language,
            units,
            expected_coverage=coverage,
        )
        context.artifacts.publish_json(artifact_id, result.to_document())
        return result


class TranslationWorkflowError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        details: Mapping[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = dict(details or {})


@dataclass(frozen=True)
class _InvalidGeneratedOutput:
    error: TranslationWorkflowError
    candidate_path: Path
    candidate: Mapping[str, Any]


def _candidate_run_error(
    error: TranslationWorkflowError, path: Path
) -> RunError:
    return RunError(
        error.code,
        f"{error}; editable candidate: {path}",
        {**error.details, "candidate_path": str(path)},
    )


def _validated_generation(
    service: Any,
    context: RunContext,
    request: LLMRequest,
    *,
    validator: Callable[[Any], Any],
    candidate_id: str,
    resume_input: ResumeInput | None,
    options: LLMExecutionOptions,
    stopped_message: str,
    retry_request_factory: Callable[
        [LLMRequest, TranslationWorkflowError, Mapping[str, Any]], LLMRequest
    ]
    | None = None,
    retry_candidate_merger: Callable[
        [Mapping[str, Any], Any], Mapping[str, Any]
    ]
    | None = None,
) -> Any | Paused | RunError | _InvalidGeneratedOutput:
    """Retry one model-correctable identity/coverage failure, then pause."""

    candidate_path = context.working.find_candidate(candidate_id)
    if candidate_path is not None:
        candidate = context.working.read_candidate_json(candidate_id)
        try:
            return validator(candidate)
        except TranslationWorkflowError as exc:
            return _InvalidGeneratedOutput(exc, candidate_path, candidate)

    first_candidate_id = _attempt_candidate_id(candidate_id)
    first_candidate_path = context.working.find_candidate(first_candidate_id)
    first_candidate: Mapping[str, Any] | None = None
    feedback: TranslationWorkflowError | None = None
    if first_candidate_path is not None:
        first_candidate = context.working.read_candidate_json(first_candidate_id)
        try:
            validated = validator(first_candidate)
            context.working.write_candidate_json(
                candidate_id, first_candidate
            )
            return validated
        except TranslationWorkflowError as exc:
            feedback = exc

    attempt = 2 if feedback is not None else 1
    current_request = (
        (
            retry_request_factory(request, feedback, first_candidate)
            if retry_request_factory is not None and first_candidate is not None
            else _semantic_retry_request(request, feedback)
        )
        if feedback is not None
        else request
    )
    while True:
        outcome = _execute(
            service,
            context,
            current_request,
            resume_input=resume_input,
            options=options,
        )
        if isinstance(outcome, LLMPaused):
            return Paused(_awaiting(outcome))
        if isinstance(outcome, LLMFailed):
            return _run_error(outcome)
        if isinstance(outcome, LLMStopped):
            raise StoppedError(stopped_message)
        assert isinstance(outcome, LLMCompleted)
        candidate_value = outcome.value
        if (
            attempt == 2
            and first_candidate is not None
            and retry_candidate_merger is not None
        ):
            candidate_value = retry_candidate_merger(
                first_candidate, candidate_value
            )
        try:
            validated = validator(candidate_value)
        except TranslationWorkflowError as exc:
            document = _generated_candidate_document(candidate_value)
            if attempt == 1:
                context.working.write_candidate_json(
                    first_candidate_id, document
                )
                first_candidate = document
                feedback = exc
                attempt = 2
                current_request = (
                    retry_request_factory(request, exc, document)
                    if retry_request_factory is not None
                    else _semantic_retry_request(request, exc)
                )
                continue
            path = context.working.write_candidate_json(
                candidate_id, document
            )
            return _InvalidGeneratedOutput(exc, path, document)
        persisted = (
            validated if isinstance(validated, Mapping) else candidate_value
        )
        context.working.write_candidate_json(
            candidate_id, _generated_candidate_document(persisted)
        )
        return validated


def _attempt_candidate_id(candidate_id: str) -> str:
    if candidate_id.endswith(".json"):
        return f"{candidate_id[:-5]}-attempt-1.json"
    return f"{candidate_id}-attempt-1"


def _semantic_retry_request(
    request: LLMRequest, error: TranslationWorkflowError
) -> LLMRequest:
    message = str(error)
    details = json.dumps(
        error.details,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    bounded_message = message[:500]
    bounded_details = details[:1500]
    error_digest = hashlib.sha256(
        f"{message}\n{details}".encode()
    ).hexdigest()
    prompt = request.prompt
    marker = "\n\nInput JSON:\n"
    if marker in prompt:
        prefix, payload = prompt.split(marker, 1)
        prompt = (
            f"{prefix}\n\nRetry after a machine-checkable output-contract "
            f"failure ({error.code}): {bounded_message}. Exact diagnostics: "
            f"{bounded_details}. Generate the "
            "complete output "
            "again; do not narrow or change the scientific content."
            f"{marker}{payload}"
        )
    else:
        prompt = (
            f"{prompt}\n\nRetry after a machine-checkable output-contract "
            f"failure ({error.code}): {bounded_message}. Exact diagnostics: "
            f"{bounded_details}. Generate the "
            "complete output "
            "again; do not narrow or change the scientific content."
        )
    return LLMRequest(
        _task_id(
            "semantic-retry",
            {
                "task_id": request.task_id,
                "error_code": error.code,
                "error_message": bounded_message,
                "error_digest": error_digest,
            },
        ),
        prompt,
        request.output,
        request.model,
        request.session,
        request.inputs,
    )


def _generated_candidate_document(value: Any) -> dict[str, JsonValue]:
    public = _public_value(value)
    if isinstance(public, Mapping):
        return dict(public)
    return {"generated_value": public}


def _output_supervision(
    context: RunContext,
    *,
    artifact_prefix: str,
    stage: str,
    error: TranslationWorkflowError,
    candidate_path: Path,
) -> Paused:
    digest = _digest(
        {
            "stage": stage,
            "candidate_path": str(candidate_path),
            "error_code": error.code,
            "error_message": str(error),
        }
    )[:24]
    resume_key = f"output-{digest}"
    request_id = (
        f"{artifact_prefix}/output-supervision/{stage}-{digest}"
    )
    request_ref = context.artifacts.find(request_id)
    if request_ref is None:
        request_ref = context.artifacts.publish_json(
            request_id,
            {
                "schema_version": OUTPUT_SUPERVISION_SCHEMA,
                "resume_key": resume_key,
                "reason": error.code,
                "message": str(error),
                "candidate_path": str(candidate_path),
                "details": error.details,
                "automatic_retry_exhausted": True,
                "output_attempts": 2,
            },
        )
    return Paused(
        Awaiting(
            ResumeReason.SUPERVISION_REQUIRED,
            resume_key,
            False,
            request_ref,
            None,
            {
                "stage": stage,
                "code": error.code,
                "candidate_path": str(candidate_path),
                "automatic_retry_exhausted": True,
                "output_attempts": 2,
            },
        )
    )


def outer_resume_input(context: RunContext) -> ResumeInput | None:
    if context.resume_input is None:
        return None
    try:
        return decode_resume_input(context.resume_input)
    except Exception as exc:
        if context.resume_input.get("schema_version") == RESUME_SCHEMA_VERSION:
            raise TranslationWorkflowError(
                "llm_resume_input_invalid", "Malformed ac-llm resume input"
            ) from exc
        return None


_execute = execute_or_resume_matching


def _validate_language_output(value: Any) -> dict[str, Any]:
    document = _object(value, "language output")
    _require_fields(
        document,
        {"language_tag", "classification", "confidence"},
        "language output",
    )
    tag = _string(document, "language_tag").strip()
    classification = _string(document, "classification")
    confidence = document["confidence"]
    if not tag or classification not in {"known", "mixed", "unknown"}:
        raise TranslationWorkflowError(
            "language_result_invalid", "language classification is invalid"
        )
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not 0 <= float(confidence) <= 1
    ):
        raise TranslationWorkflowError(
            "language_result_invalid", "language confidence is invalid"
        )
    return {
        "language_tag": tag,
        "classification": classification,
        "confidence": float(confidence),
    }


_TERM_IDENTITY_FIELDS = (
    "term_id",
    "term",
    "aliases",
    "occurrence_count",
    "source_refs",
    "matched_sentences",
)
_GLOSSARY_ENTRY_FIELDS = {
    *_TERM_IDENTITY_FIELDS,
    "preferred_translation",
    "target_definition",
}
_ALLOWED_GLOSSARY_CONTROL_CHARACTERS = frozenset({"\t", "\n", "\r"})
_ANSI_SGR_RE = re.compile(
    r"(?:\x1b\[|\x9b)[0-9:;]{0,32}m"
)
_TRUNCATED_UNICODE_RE = re.compile(
    r"(?P<high>[\x01-\x08\x0b\x0c\x0e-\x1f])"
    r"(?P<suffix>[0-9a-f]{2})(?![0-9a-f])",
    re.IGNORECASE,
)
_GLOSSARY_TRANSLATED_TERM_MATH_MARKERS = (
    "$",
    r"\(",
    r"\)",
    r"\[",
    r"\]",
)


def _has_forbidden_glossary_control(value: str) -> bool:
    return any(
        (
            ord(character) < 0x20
            and character not in _ALLOWED_GLOSSARY_CONTROL_CHARACTERS
        )
        or 0x7F <= ord(character) <= 0x9F
        for character in value
    )


def _has_glossary_translated_term_math_markup(value: str) -> bool:
    return any(
        marker in value
        for marker in _GLOSSARY_TRANSLATED_TERM_MATH_MARKERS
    )


def _recover_glossary_control_text(value: str) -> str:
    """Remove terminal controls and reconstruct deterministic Unicode damage."""

    without_terminal_controls = _ANSI_SGR_RE.sub("", value)

    def reconstruct(match: re.Match[str]) -> str:
        return chr(
            ord(match.group("high")) * 0x100
            + int(match.group("suffix"), 16)
        )

    return _TRUNCATED_UNICODE_RE.sub(
        reconstruct, without_terminal_controls
    )


def _keyword_inventory_document(value: Any) -> dict[str, JsonValue]:
    raw = _public_value(value)
    if not isinstance(raw, Mapping):
        raise TranslationWorkflowError(
            "keyword_inventory_invalid", "keyword inventory must be an object"
        )
    document = dict(raw)
    return document  # type: ignore[return-value]


def _public_value(value: Any) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _public_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_public_value(item) for item in value]
    if dataclasses.is_dataclass(value):
        return _public_value(dataclasses.asdict(value))
    to_document = getattr(value, "to_document", None)
    if callable(to_document):
        return _public_value(to_document())
    raise TranslationWorkflowError(
        "keyword_inventory_invalid",
        f"keyword value is not JSON-compatible: {type(value).__name__}",
    )


def _validate_keyword_inventory(
    value: Mapping[str, Any],
    *,
    source: TranslationSource,
    approx_count: int,
) -> None:
    fields = {
        "schema_version",
        "document_digest",
        "source_digest",
        "approx_count",
        "planned_count",
        "returned_count",
        "terms",
        "inventory_digest",
        "warnings",
    }
    _require_fields(value, fields, "keyword inventory")
    if (
        _string(value, "schema_version") != "ac.document.keyword_result.v1"
        or _string(value, "document_digest") != source.document_digest
        or _string(value, "source_digest") != source.source_digest
        or _integer(value, "approx_count") != approx_count
        or _integer(value, "planned_count")
        != (3 * approx_count + 1) // 2
    ):
        raise TranslationWorkflowError(
            "keyword_inventory_binding_mismatch",
            "keyword inventory does not match the translation source",
        )
    terms = _mapping_list(value["terms"], "keyword terms")
    warnings = value["warnings"]
    if not isinstance(warnings, list) or any(
        not isinstance(item, str) for item in warnings
    ):
        raise TranslationWorkflowError(
            "keyword_inventory_invalid",
            "keyword warnings must be an array of strings",
        )
    if _integer(value, "returned_count") != len(terms):
        raise TranslationWorkflowError(
            "keyword_inventory_invalid",
            "keyword returned_count does not match terms",
        )
    term_ids: set[str] = set()
    for item in terms:
        _require_fields(item, set(_TERM_IDENTITY_FIELDS), "keyword term")
        term_id = _string(item, "term_id")
        if (
            not term_id
            or term_id in term_ids
            or not _string(item, "term").strip()
            or not isinstance(item["aliases"], list)
            or any(not isinstance(alias, str) for alias in item["aliases"])
            or isinstance(item["occurrence_count"], bool)
            or not isinstance(item["occurrence_count"], int)
            or item["occurrence_count"] < 0
            or not isinstance(item["source_refs"], list)
            or any(
                not isinstance(source_ref, str)
                for source_ref in item["source_refs"]
            )
            or not isinstance(item["matched_sentences"], list)
        ):
            raise TranslationWorkflowError(
                "keyword_inventory_invalid", "keyword term identity is invalid"
            )
        term_ids.add(term_id)
        for sentence in item["matched_sentences"]:
            if (
                not isinstance(sentence, Mapping)
                or set(sentence)
                != {
                    "text",
                    "section_id",
                    "page_number",
                    "matched_surface",
                    "clipped",
                }
                or not isinstance(sentence["text"], str)
                or not isinstance(sentence["section_id"], str)
                or not isinstance(sentence["matched_surface"], str)
                or not isinstance(sentence["clipped"], bool)
                or (
                    sentence["page_number"] is not None
                    and (
                        isinstance(sentence["page_number"], bool)
                        or not isinstance(sentence["page_number"], int)
                        or sentence["page_number"] < 1
                    )
                )
            ):
                raise TranslationWorkflowError(
                    "keyword_inventory_invalid",
                    "matched sentence grounding is invalid",
                )
    inventory_digest = _string(value, "inventory_digest")
    if not _is_sha256(inventory_digest):
        raise TranslationWorkflowError(
            "keyword_inventory_invalid", "inventory_digest is invalid"
        )


def _glossary_windows(
    terms: Sequence[Mapping[str, Any]],
    *,
    target_language: str,
    budget_bytes: int,
) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    windows: list[tuple[Mapping[str, Any], ...]] = []
    current: list[Mapping[str, Any]] = []
    for term in terms:
        candidate = [*current, term]
        if (
            len(
                glossary_prompt(
                    terms=candidate,
                    target_language=target_language,
                    window_ordinal=len(windows),
                ).encode("utf-8")
            )
            <= budget_bytes
        ):
            current = candidate
            continue
        if current:
            windows.append(tuple(current))
            current = [term]
        else:
            current = [term]
        if (
            len(
                glossary_prompt(
                    terms=current,
                    target_language=target_language,
                    window_ordinal=len(windows),
                ).encode("utf-8")
            )
            > budget_bytes
        ):
            raise TranslationWorkflowError(
                "glossary_term_exceeds_input_budget",
                f"term {term.get('term_id', '<unknown>')} exceeds the "
                f"{budget_bytes}-byte glossary input budget",
            )
    if current:
        windows.append(tuple(current))
    return tuple(windows)


def _validate_glossary_window(
    value: Mapping[str, Any], terms: Sequence[Mapping[str, Any]]
) -> list[dict[str, JsonValue]]:
    _require_fields(value, {"entries"}, "glossary window")
    entries = _mapping_list(value["entries"], "glossary window entries")
    if len(entries) != len(terms):
        raise TranslationWorkflowError(
            "glossary_coverage_invalid",
            "glossary window must cover every supplied term",
        )
    output: list[dict[str, JsonValue]] = []
    for entry, term in zip(entries, terms, strict=True):
        _require_fields(
            entry,
            {"term_id", "preferred_translation", "target_definition"},
            "glossary entry",
        )
        if entry["term_id"] != term["term_id"]:
            raise TranslationWorkflowError(
                "glossary_term_identity_invalid",
                "glossary changed term coverage, order, or identity",
            )
        if (
            not isinstance(entry["preferred_translation"], str)
            or not entry["preferred_translation"].strip()
            or not isinstance(entry["target_definition"], str)
            or not entry["target_definition"].strip()
        ):
            raise TranslationWorkflowError(
                "glossary_content_invalid",
                "glossary translations and target definitions must be non-empty",
            )
        if _has_forbidden_glossary_control(
            entry["preferred_translation"]
        ) or _has_forbidden_glossary_control(entry["target_definition"]):
            raise TranslationWorkflowError(
                "glossary_control_character_invalid",
                "glossary translations and target definitions cannot contain "
                "control characters",
            )
        if _has_glossary_translated_term_math_markup(
            entry["preferred_translation"]
        ):
            raise TranslationWorkflowError(
                "glossary_translation_math_markup_invalid",
                "glossary preferred_translation must be plain text",
            )
        output.append(
            {
                **dict(term),
                "preferred_translation": entry["preferred_translation"],
                "target_definition": entry["target_definition"],
            }
        )  # type: ignore[arg-type]
    return output


def _salvaged_glossary_fallback(
    value: Mapping[str, Any], terms: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, JsonValue]], list[str], list[str]]:
    _require_fields(value, {"entries"}, "glossary window")
    raw_entries = _mapping_list(value["entries"], "glossary window entries")
    if len(raw_entries) != len(terms):
        raise TranslationWorkflowError(
            "glossary_coverage_invalid",
            "glossary window must cover every supplied term",
        )
    accepted: list[dict[str, JsonValue]] = []
    recovered_term_ids: list[str] = []
    dropped_term_ids: list[str] = []
    for entry, term in zip(raw_entries, terms, strict=True):
        candidate = dict(entry)
        recovered = False
        for field in ("preferred_translation", "target_definition"):
            raw_text = candidate.get(field)
            if not isinstance(raw_text, str):
                continue
            recovered_text = _recover_glossary_control_text(raw_text)
            if recovered_text != raw_text:
                candidate[field] = recovered_text
                recovered = True
        preferred = candidate.get("preferred_translation")
        if (
            isinstance(preferred, str)
            and _has_glossary_translated_term_math_markup(preferred)
        ):
            candidate["preferred_translation"] = str(term["term"])
            recovered = True
        try:
            validated = _validate_glossary_window(
                {"entries": [candidate]}, [term]
            )
        except TranslationWorkflowError as exc:
            if exc.code not in {
                "glossary_content_invalid",
                "glossary_control_character_invalid",
                "glossary_translation_math_markup_invalid",
            }:
                raise
            dropped_term_ids.append(str(term["term_id"]))
            continue
        accepted.extend(validated)
        if recovered:
            recovered_term_ids.append(str(term["term_id"]))
    if not recovered_term_ids and not dropped_term_ids:
        raise TranslationWorkflowError(
            "glossary_fallback_invalid",
            "glossary control fallback did not identify an unsafe entry",
        )
    return accepted, recovered_term_ids, dropped_term_ids


def _publish_glossary_fallback(
    context: RunContext,
    artifact_id: str,
    *,
    recovered_term_ids: Sequence[str] = (),
    dropped_term_ids: Sequence[str],
    reason_codes: Sequence[str],
) -> None:
    document = {
        "schema_version": "alc.translate.glossary_fallback_diagnostic.v2",
        "recovered_term_ids": list(dict.fromkeys(recovered_term_ids)),
        "dropped_term_ids": list(dict.fromkeys(dropped_term_ids)),
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }
    expected = _glossary_fallback_summary_from_diagnostic(document)
    existing = context.artifacts.find(artifact_id)
    if existing is not None:
        actual = _glossary_fallback_summary_from_diagnostic(
            _read_json_artifact(context, existing, "glossary fallback diagnostic")
        )
        if actual != expected:
            raise TranslationWorkflowError(
                "glossary_fallback_mismatch",
                "glossary fallback diagnostic differs on replay",
            )
        return
    context.artifacts.publish_json(artifact_id, document)
    event = {
        "glossary_entry_count": len(document["dropped_term_ids"]),
        "reason_codes": document["reason_codes"],
    }
    if recovered_term_ids:
        event["glossary_recovered_entry_count"] = len(
            document["recovered_term_ids"]
        )
    context.events.emit("translation_fallback", event)


def _load_legacy_glossary_fallback_summary(
    context: RunContext,
    *,
    source: TranslationSource,
    approx_count: int,
    target_language: str,
    term_input_budget_bytes: int,
    artifact_prefix: str,
) -> GlossaryFallbackSummary:
    inventory_ref = context.artifacts.find(
        f"{artifact_prefix}/keyword-inventory"
    )
    if inventory_ref is None:
        return GlossaryFallbackSummary()
    inventory = _read_json_artifact(
        context, inventory_ref, "legacy keyword inventory"
    )
    _validate_keyword_inventory(
        inventory, source=source, approx_count=approx_count
    )
    terms = _mapping_list(inventory["terms"], "legacy keyword terms")
    windows = _glossary_windows(
        terms,
        target_language=target_language,
        budget_bytes=term_input_budget_bytes,
    )
    return _load_glossary_fallback_summary(
        context,
        terms=terms,
        window_count=len(windows),
        artifact_prefix=artifact_prefix,
    )


def _load_glossary_fallback_summary(
    context: RunContext,
    *,
    terms: Sequence[Mapping[str, Any]],
    window_count: int,
    artifact_prefix: str,
) -> GlossaryFallbackSummary:
    known_term_ids = {str(term["term_id"]) for term in terms}
    recovered: list[str] = []
    dropped: list[str] = []
    reasons: list[str] = []
    for ordinal in range(window_count):
        ref = context.artifacts.find(
            f"{artifact_prefix}/fallbacks/{ordinal:04d}"
        )
        if ref is None:
            continue
        summary = _glossary_fallback_summary_from_diagnostic(
            _read_json_artifact(context, ref, "glossary fallback diagnostic")
        )
        recovered.extend(summary.recovered_term_ids)
        dropped.extend(summary.dropped_term_ids)
        reasons.extend(summary.reason_codes)
    result = GlossaryFallbackSummary(
        recovered_term_ids=tuple(dict.fromkeys(recovered)),
        dropped_term_ids=tuple(dict.fromkeys(dropped)),
        reason_codes=tuple(dict.fromkeys(reasons)),
    )
    declared = set(result.recovered_term_ids) | set(result.dropped_term_ids)
    if not declared.issubset(known_term_ids):
        raise TranslationWorkflowError(
            "glossary_fallback_invalid",
            "glossary fallback summary refers to an unknown term",
        )
    return result


def _glossary_fallback_summary_from_diagnostic(
    value: Mapping[str, Any],
) -> GlossaryFallbackSummary:
    schema_version = _string(value, "schema_version")
    common = {"schema_version", "dropped_term_ids", "reason_codes"}
    if schema_version == "alc.translate.glossary_fallback_diagnostic.v2":
        _require_fields(
            value, {*common, "recovered_term_ids"}, "glossary fallback diagnostic"
        )
        recovered = _string_items(
            value["recovered_term_ids"], "recovered glossary term IDs"
        )
    elif schema_version == "alc.translate.glossary_fallback_diagnostic.v1":
        allowed = (common, {*common, "recovered_term_ids"})
        if set(value) not in allowed:
            raise TranslationWorkflowError(
                "glossary_fallback_invalid",
                "legacy glossary fallback diagnostic is invalid",
            )
        recovered = _string_items(
            value.get("recovered_term_ids", ()), "recovered glossary term IDs"
        )
    else:
        raise TranslationWorkflowError(
            "glossary_fallback_invalid",
            "glossary fallback diagnostic uses an unsupported schema",
        )
    try:
        return GlossaryFallbackSummary(
            recovered_term_ids=recovered,
            dropped_term_ids=_string_items(
                value["dropped_term_ids"], "dropped glossary term IDs"
            ),
            reason_codes=_string_items(
                value["reason_codes"], "glossary fallback reason codes"
            ),
        )
    except (TypeError, ValueError) as exc:
        raise TranslationWorkflowError(
            "glossary_fallback_invalid", str(exc)
        ) from exc


def _validated_glossary_document(
    value: Any, terms: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    document = _object(value, "glossary window")
    _validate_glossary_window(document, terms)
    return document


def _validate_glossary_entries(
    entries: Sequence[Mapping[str, Any]],
) -> None:
    term_ids: set[str] = set()
    for entry in entries:
        _require_fields(entry, _GLOSSARY_ENTRY_FIELDS, "glossary entry")
        term_id = _string(entry, "term_id")
        if (
            not term_id
            or term_id in term_ids
            or not _string(entry, "term").strip()
            or not isinstance(entry["aliases"], list)
            or any(not isinstance(item, str) for item in entry["aliases"])
            or isinstance(entry["occurrence_count"], bool)
            or not isinstance(entry["occurrence_count"], int)
            or entry["occurrence_count"] < 0
            or not isinstance(entry["source_refs"], list)
            or not isinstance(entry["matched_sentences"], list)
            or not isinstance(entry["preferred_translation"], str)
            or not entry["preferred_translation"].strip()
            or not isinstance(entry["target_definition"], str)
            or not entry["target_definition"].strip()
        ):
            raise ValueError("glossary entry is invalid or duplicated")
        term_ids.add(term_id)


def _translation_windows(
    blocks: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    language: LanguageResult,
    budget_bytes: int,
) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    windows: list[tuple[Mapping[str, Any], ...]] = []
    current: list[Mapping[str, Any]] = []
    for block in blocks:
        candidate = [*current, block]
        if (
            _translation_prompt_size(
                candidate,
                glossary=glossary,
                target_language=target_language,
                language=language,
                ordinal=len(windows),
            )
            <= budget_bytes
            and (
                len(candidate) == 1
                or _translation_review_estimate_size(
                    candidate,
                    glossary=glossary,
                    target_language=target_language,
                    ordinal=len(windows),
                )
                <= budget_bytes
            )
        ):
            current = candidate
            continue
        if current:
            windows.append(tuple(current))
            current = [block]
        else:
            current = [block]
        if (
            _translation_prompt_size(
                current,
                glossary=glossary,
                target_language=target_language,
                language=language,
                ordinal=len(windows),
            )
            > budget_bytes
        ):
            raise TranslationWorkflowError(
                "translation_block_exceeds_input_budget",
                f"block {block.get('block_id', '<unknown>')} exceeds the "
                f"{budget_bytes}-byte translation input budget",
            )
    if current:
        windows.append(tuple(current))
    return tuple(windows)


def _select_blocks(
    blocks: Sequence[Mapping[str, Any]],
    block_ids: Sequence[str] | None,
) -> tuple[Mapping[str, Any], ...]:
    if block_ids is None:
        return tuple(blocks)
    if (
        isinstance(block_ids, (str, bytes))
        or not isinstance(block_ids, Sequence)
        or not block_ids
        or any(not isinstance(item, str) or not item for item in block_ids)
        or len(set(block_ids)) != len(block_ids)
    ):
        raise TranslationWorkflowError(
            "block_selector_invalid",
            "block_ids must be a non-empty unique sequence of block IDs",
        )
    requested = set(block_ids)
    available = {str(item["block_id"]) for item in blocks}
    missing = requested - available
    if missing:
        raise TranslationWorkflowError(
            "block_selector_invalid",
            f"block_ids contain unknown source IDs: {sorted(missing)!r}",
        )
    return tuple(item for item in blocks if str(item["block_id"]) in requested)


def _translation_units(
    source: TranslationSource,
    blocks: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    selected_owner_ids = {str(block["block_id"]) for block in blocks}
    notes = source_note_blocks(source, owner_block_ids=selected_owner_ids)
    notes_by_owner: dict[str, list[Mapping[str, Any]]] = {}
    for note in notes:
        binding = note.get("source_note")
        if not isinstance(binding, Mapping):
            raise TranslationWorkflowError(
                "source_notes_invalid", "source note translation binding is invalid"
            )
        notes_by_owner.setdefault(
            str(binding.get("owner_block_id", "")), []
        ).append(note)
    units: list[Mapping[str, Any]] = []
    for block in blocks:
        units.append(block)
        units.extend(notes_by_owner.get(str(block["block_id"]), ()))
    return tuple(units)


def _model_translation_blocks(
    blocks: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    return tuple(
        block
        for block in blocks
        if not _is_nonlinguistic_media_block(block)
        and str(block.get("kind")) != "equation"
        and source_note_link_markdown(block) is None
    )


@dataclass(frozen=True)
class _TranslationUnitPlan:
    block_id: str
    kind: str
    unit_groups: tuple[tuple[str, ...], ...]
    direct: bool
    protected_atom_ids: tuple[str, ...]


def _bounded_model_translation_units(
    blocks: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    language: LanguageResult,
    budget_bytes: int,
) -> tuple[
    tuple[Mapping[str, Any], ...],
    tuple[_TranslationUnitPlan, ...],
]:
    units: list[Mapping[str, Any]] = []
    plans: list[_TranslationUnitPlan] = []
    for block in blocks:
        block_id = str(block["block_id"])
        if (
            str(block.get("kind")) != "list"
            and _translation_prompt_size(
                (block,),
                glossary=glossary,
                target_language=target_language,
                language=language,
                ordinal=0,
            )
            <= budget_bytes
            and _translation_review_estimate_size(
                (block,),
                glossary=glossary,
                target_language=target_language,
                ordinal=0,
            )
            <= budget_bytes
        ):
            units.append(block)
            plans.append(
                _TranslationUnitPlan(
                    block_id,
                    str(block.get("kind")),
                    ((block_id,),),
                    True,
                    protected_atom_ids(block),
                )
            )
            continue
        text_budget = max(64, budget_bytes // 4)
        while True:
            try:
                part_groups = protected_atom_part_groups(
                    block, max_bytes=text_budget
                )
            except ProtectedAtomError as exc:
                raise TranslationWorkflowError(
                    exc.code, str(exc), exc.details
                ) from exc
            candidate_units: list[Mapping[str, Any]] = []
            unit_groups: list[tuple[str, ...]] = []
            unit_ordinal = 0
            for group in part_groups:
                group_ids: list[str] = []
                for parts in group:
                    unit_id = (
                        f"{block_id}.translation-unit-{unit_ordinal:06d}"
                    )
                    unit_ordinal += 1
                    group_ids.append(unit_id)
                    unit_plan = protected_atom_subplan(
                        block, block_id=unit_id, parts=parts
                    )
                    unit = {
                        "block_id": unit_id,
                        "ordinal": block.get("ordinal"),
                        "kind": "translation_unit",
                        "section_path": block.get("section_path", []),
                        "payload": {"text": ""},
                        "protected_atom_plan": unit_plan,
                    }
                    try:
                        source_text, _ = assemble_protected_translation(
                            unit, unit_plan["parts"]
                        )
                    except ProtectedAtomError as exc:
                        raise TranslationWorkflowError(
                            exc.code, str(exc), exc.details
                        ) from exc
                    candidate_units.append(
                        {**unit, "payload": {"text": source_text}}
                    )
                unit_groups.append(tuple(group_ids))
            if not candidate_units:
                raise TranslationWorkflowError(
                    "translation_block_exceeds_input_budget",
                    f"block {block_id} has no translatable bounded units",
                )
            if all(
                _translation_prompt_size(
                    (unit,),
                    glossary=glossary,
                    target_language=target_language,
                    language=language,
                    ordinal=0,
                )
                <= budget_bytes
                and _translation_review_estimate_size(
                    (unit,),
                    glossary=glossary,
                    target_language=target_language,
                    ordinal=0,
                )
                <= budget_bytes
                for unit in candidate_units
            ):
                units.extend(candidate_units)
                actual_atom_ids = [
                    atom_id
                    for unit in candidate_units
                    for atom_id in protected_atom_ids(unit)
                ]
                expected_atom_ids = list(protected_atom_ids(block))
                if sorted(actual_atom_ids) != sorted(expected_atom_ids):
                    raise TranslationWorkflowError(
                        "translation_atom_plan_invalid",
                        "split translation units do not exactly cover source atoms",
                    )
                plans.append(
                    _TranslationUnitPlan(
                        block_id,
                        str(block.get("kind")),
                        tuple(unit_groups),
                        False,
                        tuple(expected_atom_ids),
                    )
                )
                break
            if text_budget == 64:
                raise TranslationWorkflowError(
                    "translation_block_exceeds_input_budget",
                    f"block {block_id} cannot be divided below the "
                    f"{budget_bytes}-byte translation input budget",
                )
            text_budget = max(64, text_budget // 2)
    return tuple(units), tuple(plans)


def _collapse_model_translation_units(
    blocks: Sequence[Mapping[str, Any]],
    plans: Sequence[_TranslationUnitPlan],
    translations: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, str], ...]:
    if len(blocks) != len(plans):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation unit plans do not cover the selected source blocks",
        )
    by_id = {str(item["block_id"]): item for item in translations}
    if len(by_id) != len(translations):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation units contain duplicate IDs",
        )
    output: list[Mapping[str, str]] = []
    consumed: set[str] = set()
    for block, plan in zip(blocks, plans, strict=True):
        if plan.block_id != str(block["block_id"]):
            raise TranslationWorkflowError(
                "translation_coverage_invalid",
                "translation unit plan source identity is invalid",
            )
        group_values: list[str] = []
        for group in plan.unit_groups:
            values: list[str] = []
            for unit_id in group:
                if unit_id not in by_id:
                    raise TranslationWorkflowError(
                        "translation_coverage_invalid",
                        f"translation omitted internal unit {unit_id}",
                    )
                consumed.add(unit_id)
                translation = by_id[unit_id]
                value = str(translation["text"]).strip()
                if plan.kind == "list" and not plan.direct:
                    value = " ".join(
                        line.strip()
                        for line in value.splitlines()
                        if line.strip()
                    )
                values.append(value)
            group_values.append(" ".join(value for value in values if value))
        text = (
            "\n".join(group_values)
            if plan.kind == "list" and not plan.direct
            else " ".join(group_values)
        ).strip()
        protected = all(
            item.get("schema_version") == PROTECTED_ATOM_RESULT_SCHEMA
            for item in (by_id[unit_id] for group in plan.unit_groups for unit_id in group)
        )
        if not protected:
            # Historical accepted Markdown is read through this explicit
            # compatibility branch. New model results were assembled locally
            # from immutable atoms and do not re-parse model Markdown.
            text = restore_translation_identity(text, block)
            try:
                validate_translation_text(text, block)
            except TranslationSourceError as exc:
                raise TranslationWorkflowError(
                    exc.code, str(exc), exc.details
                ) from exc
        output.append({"block_id": plan.block_id, "text": text})
    if consumed != set(by_id):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation contains unknown internal units",
        )
    return tuple(output)


def _collapse_model_translation_units_with_fallback(
    blocks: Sequence[Mapping[str, Any]],
    plans: Sequence[_TranslationUnitPlan],
    translations: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, str], ...], tuple[str, ...]]:
    """Collapse bounded units while preserving only identity-invalid blocks.

    Coverage, ordering, and unknown-unit errors remain fatal.  A source
    identity error is localized to its original block and replaced with the
    exact identity-preserving source projection.
    """

    try:
        return (
            _collapse_model_translation_units(blocks, plans, translations),
            (),
        )
    except TranslationWorkflowError as exc:
        if exc.code != "translation_source_identity_invalid":
            raise

    translated_by_id = {
        str(item["block_id"]): item for item in translations
    }
    if len(translated_by_id) != len(translations):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation units contain duplicate IDs",
        )
    expected_unit_ids = {
        unit_id
        for plan in plans
        for group in plan.unit_groups
        for unit_id in group
    }
    if set(translated_by_id) != expected_unit_ids:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation units do not exactly cover the unit plan",
        )

    output: list[Mapping[str, str]] = []
    source_fallback_ids: list[str] = []
    for block, plan in zip(blocks, plans, strict=True):
        unit_ids = [
            unit_id for group in plan.unit_groups for unit_id in group
        ]
        block_translations = tuple(
            translated_by_id[unit_id] for unit_id in unit_ids
        )
        try:
            output.extend(
                _collapse_model_translation_units(
                    (block,), (plan,), block_translations
                )
            )
        except TranslationWorkflowError as exc:
            if exc.code != "translation_source_identity_invalid":
                raise
            output.append(
                {
                    "block_id": str(block["block_id"]),
                    "text": _identity_preserving_source_text(block),
                }
            )
            source_fallback_ids.append(str(block["block_id"]))
    return tuple(output), tuple(source_fallback_ids)


def _protected_original_block_ids(
    plans: Sequence[_TranslationUnitPlan],
    translations: Sequence[Mapping[str, Any]],
) -> set[str]:
    by_id = {str(item.get("block_id")): item for item in translations}
    protected: set[str] = set()
    for plan in plans:
        unit_ids = [
            unit_id for group in plan.unit_groups for unit_id in group
        ]
        if unit_ids and all(
            by_id.get(unit_id, {}).get("schema_version")
            == PROTECTED_ATOM_RESULT_SCHEMA
            for unit_id in unit_ids
        ):
            protected.add(plan.block_id)
    return protected


def _salvaged_translation_fallback(
    blocks: Sequence[Mapping[str, Any]],
    *,
    candidate: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    candidate_by_id: dict[str, Mapping[str, Any]] = {}
    raw_translations = candidate.get("translations") if candidate else None
    if isinstance(raw_translations, Mapping):
        candidate_by_id = {
            str(block_id): item
            for block_id, item in raw_translations.items()
            if isinstance(block_id, str) and isinstance(item, Mapping)
        }
    elif isinstance(raw_translations, Sequence) and not isinstance(
        raw_translations, (str, bytes)
    ):
        for item in raw_translations:
            if not isinstance(item, Mapping):
                continue
            block_id = item.get("block_id")
            if isinstance(block_id, str) and block_id not in candidate_by_id:
                candidate_by_id[block_id] = item

    protected_candidate = (
        isinstance(candidate, Mapping)
        and candidate.get("schema_version") == PROTECTED_ATOM_RESULT_SCHEMA
    )
    text_slot_candidate = (
        isinstance(candidate, Mapping)
        and candidate.get("schema_version") == TEXT_SLOT_RESULT_SCHEMA
    )
    translations: list[dict[str, Any]] = []
    source_fallback_ids: list[str] = []
    for block in blocks:
        block_id = str(block["block_id"])
        candidate_item = candidate_by_id.get(block_id)
        if candidate_item is not None:
            try:
                if text_slot_candidate:
                    translations.extend(
                        _validate_text_slot_window(
                            {
                                "schema_version": TEXT_SLOT_RESULT_SCHEMA,
                                "translations": {
                                    block_id: dict(candidate_item)
                                },
                            },
                            (block,),
                        )
                    )
                elif protected_candidate:
                    translations.extend(
                        _validate_model_protected_atom_window(
                            {
                                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                                "translations": [dict(candidate_item)],
                            },
                            (block,),
                        )
                    )
                else:
                    # Explicit legacy input compatibility: this is only for
                    # artifacts created by pre-protected-atom prompt versions.
                    translations.extend(
                        _validate_draft_window(
                            {"translations": [dict(candidate_item)]},
                            (block,),
                        )
                    )
                continue
            except TranslationWorkflowError:
                pass
        source_fallback_ids.append(block_id)
        translations.append(_source_protected_translation(block))
    return translations, source_fallback_ids


def _source_protected_translation(block: Mapping[str, Any]) -> dict[str, Any]:
    try:
        text, parts = assemble_protected_translation(
            block, source_protected_parts(block)
        )
    except ProtectedAtomError as exc:
        raise TranslationWorkflowError(
            exc.code, str(exc), exc.details
        ) from exc
    return {
        "block_id": str(block["block_id"]),
        "text": text,
        "parts": parts,
        "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
    }


def _translation_result_document(
    translations: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if all(
        item.get("schema_version") == PROTECTED_ATOM_RESULT_SCHEMA
        and isinstance(item.get("parts"), Sequence)
        and not isinstance(item.get("parts"), (str, bytes))
        for item in translations
    ):
        return protected_result_document(translations)
    # A persisted pre-v13 candidate can contain valid neighboring Markdown
    # entries. Keep that replay on the explicit legacy representation instead
    # of silently interpreting it as a protected-atom result.
    return {
        "translations": [
            {"block_id": str(item["block_id"]), "text": str(item["text"])}
            for item in translations
        ]
    }


def _identity_preserving_source_text(block: Mapping[str, Any]) -> str:
    text = block_text(prompt_block(block))
    try:
        validate_translation_text(text, block)
    except TranslationSourceError as exc:
        raise TranslationWorkflowError(
            exc.code, str(exc), exc.details
        ) from exc
    return text


def _persist_source_fallback_window(
    context: RunContext,
    window: Sequence[Mapping[str, Any]],
    *,
    accepted_id: str,
    fallback_id: str,
    reason_code: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    fallback, source_fallback_ids = _salvaged_translation_fallback(window)
    _publish_translation_fallback(
        context,
        fallback_id,
        source_text_block_ids=source_fallback_ids,
        review_skipped_block_ids=[],
        reason_codes=[reason_code],
    )
    context.artifacts.publish_json(
        accepted_id, _translation_result_document(fallback)
    )
    return fallback, source_fallback_ids


def _provider_fallback_reason(outcome: Paused | RunError) -> str | None:
    """Return one typed provider reason eligible for block-local fallback."""

    markers: set[str] = set()
    if isinstance(outcome, Paused):
        details: Mapping[str, Any] = outcome.awaiting.details
    else:
        markers.add(outcome.code)
        details = outcome.details

    def collect(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                if key in {
                    "code",
                    "category",
                    "ac_error_code",
                    "detail_code",
                } and isinstance(child, str):
                    markers.add(child)
                if key in {"causes", "details", "provider_failure"}:
                    collect(child)
        elif isinstance(value, Sequence) and not isinstance(
            value, (str, bytes, bytearray)
        ):
            for child in value:
                collect(child)

    collect(details)
    if markers & _PROVIDER_HARD_STOP_MARKERS:
        return None
    if not markers & _PROVIDER_FALLBACK_MARKERS:
        return None
    for reason in _PROVIDER_FALLBACK_REASON_ORDER:
        if reason in markers:
            return reason
    return None


def _provider_reason_from_codes(
    reason_codes: Sequence[str],
) -> str | None:
    values = set(reason_codes)
    return next(
        (
            reason
            for reason in _PROVIDER_FALLBACK_REASON_ORDER
            if reason in values
        ),
        None,
    )


def _publish_translation_provider_failure(
    context: RunContext,
    artifact_id: str,
    *,
    outcome: Paused | RunError,
    model: ModelSelection,
    reason_code: str,
    stage: str,
    window_ordinal: int,
    consecutive_window_failures: int,
    global_fallback_triggered: bool,
    remaining_windows_skipped: int,
) -> None:
    document = _translation_provider_failure_document(
        outcome=outcome,
        model=model,
        reason_code=reason_code,
        stage=stage,
        window_ordinal=window_ordinal,
        consecutive_window_failures=consecutive_window_failures,
        global_fallback_triggered=global_fallback_triggered,
        remaining_windows_skipped=remaining_windows_skipped,
    )
    _publish_translation_provider_failure_document(context, artifact_id, document)


def _translation_provider_failure_document(
    *,
    outcome: Paused | RunError,
    model: ModelSelection,
    reason_code: str,
    stage: str,
    window_ordinal: int,
    consecutive_window_failures: int,
    global_fallback_triggered: bool,
    remaining_windows_skipped: int,
) -> dict[str, Any]:
    details: Mapping[str, Any] = (
        outcome.awaiting.details if isinstance(outcome, Paused) else outcome.details
    )
    provider_failure = _nested_provider_failure(details)
    category = _optional_nonblank_string(
        provider_failure.get("category")
    ) or _provider_category_from_reason(reason_code)
    detail_code = _optional_nonblank_string(
        provider_failure.get("detail_code")
    ) or _optional_nonblank_string(provider_failure.get("ac_error_code"))
    return {
        "schema_version": _TRANSLATION_PROVIDER_FALLBACK_DIAGNOSTIC_SCHEMA,
        "provider": model.provider,
        "model": model.model,
        "tier": model.tier,
        "effort": model.reasoning_effort,
        "reason_code": reason_code,
        "failure_category": category or "unknown",
        "detail_code": detail_code or reason_code,
        "stage": stage,
        "window_ordinal": window_ordinal,
        "consecutive_window_failures": consecutive_window_failures,
        "global_fallback_triggered": global_fallback_triggered,
        "remaining_windows_skipped": remaining_windows_skipped,
    }


def _publish_translation_provider_failure_document(
    context: RunContext,
    artifact_id: str,
    document: Mapping[str, Any],
) -> None:
    _validate_translation_provider_failure_document(document)
    existing = context.artifacts.find(artifact_id)
    if existing is not None:
        if _read_json_artifact(
            context, existing, "translation provider fallback diagnostic"
        ) != document:
            raise TranslationWorkflowError(
                "translation_provider_fallback_mismatch",
                "translation provider fallback diagnostic differs on replay",
            )
        return
    context.artifacts.publish_json(artifact_id, document)
    context.events.emit(
        "translation_provider_fallback",
        {key: value for key, value in document.items() if key != "schema_version"},
    )


def _validate_translation_provider_failure_document(
    document: Mapping[str, Any],
) -> None:
    expected_fields = {
        "schema_version",
        "provider",
        "model",
        "tier",
        "effort",
        "reason_code",
        "failure_category",
        "detail_code",
        "stage",
        "window_ordinal",
        "consecutive_window_failures",
        "global_fallback_triggered",
        "remaining_windows_skipped",
    }
    if (
        set(document) != expected_fields
        or document.get("schema_version")
        != _TRANSLATION_PROVIDER_FALLBACK_DIAGNOSTIC_SCHEMA
        or not isinstance(document.get("reason_code"), str)
        or not str(document["reason_code"])
    ):
        raise TranslationWorkflowError(
            "translation_provider_fallback_invalid",
            "translation provider fallback diagnostic is invalid",
        )


def _nested_provider_failure(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    direct = value.get("provider_failure")
    if isinstance(direct, Mapping):
        return direct
    for key in ("details", "causes"):
        child = value.get(key)
        if isinstance(child, Mapping):
            found = _nested_provider_failure(child)
            if found:
                return found
        elif isinstance(child, Sequence) and not isinstance(
            child, (str, bytes, bytearray)
        ):
            for item in child:
                found = _nested_provider_failure(item)
                if found:
                    return found
    return {}


def _optional_nonblank_string(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _provider_category_from_reason(reason_code: str) -> str:
    if reason_code == "provider_circuit_open":
        return "circuit_open"
    if reason_code == "provider_crash_retry_exhausted":
        return "crash_retry_exhausted"
    for category in (
        "timeout",
        "transport",
        "unavailable",
        "quota",
        "rate_limit",
    ):
        if reason_code in {category, f"provider_{category}"}:
            return category
    return "unknown"


def _publish_translation_fallback(
    context: RunContext,
    artifact_id: str,
    *,
    source_text_block_ids: Sequence[str],
    review_skipped_block_ids: Sequence[str],
    reason_codes: Sequence[str],
) -> None:
    document = _translation_fallback_document(
        source_text_block_ids=source_text_block_ids,
        review_skipped_block_ids=review_skipped_block_ids,
        reason_codes=reason_codes,
    )
    _publish_translation_fallback_document(context, artifact_id, document)


def _translation_fallback_document(
    *,
    source_text_block_ids: Sequence[str],
    review_skipped_block_ids: Sequence[str],
    reason_codes: Sequence[str],
) -> dict[str, Any]:
    return {
        "schema_version": _TRANSLATION_FALLBACK_DIAGNOSTIC_SCHEMA,
        "source_text_block_ids": list(
            dict.fromkeys(source_text_block_ids)
        ),
        "review_skipped_block_ids": list(
            dict.fromkeys(review_skipped_block_ids)
        ),
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }


def _publish_translation_fallback_document(
    context: RunContext,
    artifact_id: str,
    document: Mapping[str, Any],
) -> None:
    _translation_fallback_entries(document)
    existing = context.artifacts.find(artifact_id)
    if existing is not None:
        if _read_json_artifact(
            context, existing, "translation fallback diagnostic"
        ) != document:
            raise TranslationWorkflowError(
                "translation_fallback_mismatch",
                "translation fallback diagnostic differs on replay",
            )
        return
    context.artifacts.publish_json(artifact_id, document)
    context.events.emit(
        "translation_fallback",
        {
            "source_text_block_count": len(
                document["source_text_block_ids"]
            ),
            "review_skipped_block_count": len(
                document["review_skipped_block_ids"]
            ),
            "reason_codes": document["reason_codes"],
        },
    )


def _load_translation_fallback(
    context: RunContext,
    artifact_id: str,
    fallback_units: dict[str, str],
) -> tuple[str, ...]:
    ref = context.artifacts.find(artifact_id)
    if ref is None:
        return ()
    document = _read_json_artifact(
        context, ref, "translation fallback diagnostic"
    )
    return _apply_translation_fallback_document(document, fallback_units)


def _apply_translation_fallback_document(
    document: Mapping[str, Any],
    fallback_units: dict[str, str],
) -> tuple[str, ...]:
    source_ids, review_ids, reason_codes = _translation_fallback_entries(document)
    fallback_units.update(
        (block_id, "review_skipped") for block_id in review_ids
    )
    fallback_units.update(
        (block_id, "source_text") for block_id in source_ids
    )
    return reason_codes


def _translation_fallback_entries(
    document: Mapping[str, Any],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if set(document) != {
        "schema_version",
        "source_text_block_ids",
        "review_skipped_block_ids",
        "reason_codes",
    } or document.get("schema_version") != _TRANSLATION_FALLBACK_DIAGNOSTIC_SCHEMA:
        raise TranslationWorkflowError(
            "translation_fallback_invalid",
            "translation fallback diagnostic is invalid",
        )
    source_ids = _string_items(
        document.get("source_text_block_ids"),
        "source fallback block IDs",
    )
    review_ids = _string_items(
        document.get("review_skipped_block_ids"),
        "review fallback block IDs",
    )
    reason_codes = _string_items(
        document.get("reason_codes"), "fallback reason codes"
    )
    return source_ids, review_ids, reason_codes


def _collapse_translation_fallbacks(
    plans: Sequence[_TranslationUnitPlan],
    fallback_units: Mapping[str, str],
) -> dict[str, str]:
    known_units = {
        unit_id
        for plan in plans
        for group in plan.unit_groups
        for unit_id in group
    }
    if set(fallback_units) - known_units:
        raise TranslationWorkflowError(
            "translation_fallback_invalid",
            "translation fallback refers to an unknown internal unit",
        )
    collapsed: dict[str, str] = {}
    for plan in plans:
        kinds = {
            fallback_units[unit_id]
            for group in plan.unit_groups
            for unit_id in group
            if unit_id in fallback_units
        }
        if "source_text" in kinds:
            collapsed[plan.block_id] = "source_text"
        elif "review_skipped" in kinds:
            collapsed[plan.block_id] = "review_skipped"
    return collapsed


def _is_structural_figure(block: Mapping[str, Any]) -> bool:
    if str(block.get("kind")) != "figure":
        return False
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationWorkflowError(
            "source_block_invalid",
            "source block payload must be an object",
        )
    return not (
        str(payload.get("caption", "")).strip()
        or str(payload.get("alt_text", "")).strip()
    )


def _is_structural_table(block: Mapping[str, Any]) -> bool:
    """Tables without a caption have no ALC translation surface."""

    if str(block.get("kind")) != "table":
        return False
    payload = block.get("payload")
    if not isinstance(payload, Mapping):
        raise TranslationWorkflowError(
            "source_block_invalid",
            "source block payload must be an object",
        )
    return not str(payload.get("caption", "")).strip()


def _is_nonlinguistic_media_block(block: Mapping[str, Any]) -> bool:
    """Return whether a source media block has no language-bearing content."""

    return _is_structural_figure(block) or _is_structural_table(block)


def _is_nonlinguistic_media_translation(
    block: Mapping[str, Any], text: str
) -> bool:
    if not _is_nonlinguistic_media_block(block):
        return False
    if _is_structural_table(block):
        return text.strip() == STRUCTURAL_FIGURE_PLACEHOLDER
    payload = block.get("payload")
    assert isinstance(payload, Mapping)
    marker = text.strip()
    structural_markers = {
        STRUCTURAL_FIGURE_PLACEHOLDER,
        str(payload.get("target", "")).strip(),
        str(payload.get("asset_digest", "")).strip(),
    }
    structural_markers.discard("")
    return marker in structural_markers


def _merge_programmatic_translations(
    blocks: Sequence[Mapping[str, Any]],
    model_translations: Sequence[Mapping[str, str]],
) -> tuple[Mapping[str, str], ...]:
    translated_by_id = {
        str(item["block_id"]): dict(item) for item in model_translations
    }
    merged: list[Mapping[str, str]] = []
    for block in blocks:
        block_id = str(block["block_id"])
        link_markdown = source_note_link_markdown(block)
        if link_markdown is not None:
            merged.append({"block_id": block_id, "text": link_markdown})
            continue
        if _is_nonlinguistic_media_block(block):
            merged.append(
                {
                    "block_id": block_id,
                    "text": STRUCTURAL_FIGURE_PLACEHOLDER,
                }
            )
            continue
        if str(block.get("kind")) == "equation":
            payload = block.get("payload")
            if not isinstance(payload, Mapping):
                raise TranslationWorkflowError(
                    "source_block_invalid",
                    "equation block payload must be an object",
                )
            merged.append(
                {
                    "block_id": block_id,
                    "text": str(payload.get("tex", "")),
                }
            )
            continue
        translation = translated_by_id.pop(block_id, None)
        if translation is None:
            raise TranslationWorkflowError(
                "translation_coverage_invalid",
                f"translation omitted source block {block_id}",
            )
        merged.append(translation)
    if translated_by_id:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation contains unknown or duplicate source blocks",
        )
    return tuple(merged)


def _window_glossary(
    blocks: Sequence[Mapping[str, Any]],
    entries: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    text = "\n".join(block_text(item) for item in blocks)
    return tuple(
        {
            "term_id": item["term_id"],
            "term": item["term"],
            "aliases": item["aliases"],
            "preferred_translation": item["preferred_translation"],
            "target_definition": item["target_definition"],
        }
        for item in entries
        if isinstance(item.get("term"), str)
        and literal_term_occurs(text, (str(item["term"]),))
    )


def _translation_prompt_size(
    blocks: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    language: LanguageResult,
    ordinal: int,
) -> int:
    return len(
        translation_prompt(
            blocks=[text_slot_prompt_block(item) for item in blocks],
            glossary=_window_glossary(blocks, glossary),
            target_language=target_language,
            language_result=language.to_document(),
            window_ordinal=ordinal,
        ).encode("utf-8")
    )


def _translation_review_estimate_size(
    blocks: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    ordinal: int,
) -> int:
    return len(
        review_prompt(
            blocks=[text_slot_prompt_block(item) for item in blocks],
            translations=[
                _review_text_slot_projection(
                    item, _source_protected_translation(item)
                )
                for item in blocks
            ],
            glossary=_window_glossary(blocks, glossary),
            target_language=target_language,
            window_ordinal=ordinal,
        ).encode("utf-8")
    )


def _translation_review_windows(
    blocks: Sequence[Mapping[str, Any]],
    translations: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    window_ordinal: int,
    budget_bytes: int,
) -> tuple[
    tuple[
        tuple[Mapping[str, Any], ...],
        tuple[Mapping[str, Any], ...],
    ],
    ...,
]:
    if len(blocks) != len(translations):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "review blocks and translations differ in length",
        )
    windows: list[
        tuple[
            tuple[Mapping[str, Any], ...],
            tuple[Mapping[str, Any], ...],
        ]
    ] = []
    current_blocks: list[Mapping[str, Any]] = []
    current_translations: list[Mapping[str, Any]] = []
    for block, translation in zip(blocks, translations, strict=True):
        candidate_blocks = [*current_blocks, block]
        candidate_translations = [*current_translations, translation]
        candidate_text = review_prompt(
            blocks=[text_slot_prompt_block(item) for item in candidate_blocks],
            translations=[
                _review_text_slot_projection(block, item)
                for block, item in zip(
                    candidate_blocks, candidate_translations, strict=True
                )
            ],
            glossary=_window_glossary(candidate_blocks, glossary),
            target_language=target_language,
            window_ordinal=window_ordinal,
        )
        if len(candidate_text.encode("utf-8")) <= budget_bytes:
            current_blocks = candidate_blocks
            current_translations = candidate_translations
            continue
        if current_blocks:
            windows.append(
                (tuple(current_blocks), tuple(current_translations))
            )
        single_text = review_prompt(
            blocks=[text_slot_prompt_block(block)],
            translations=[
                _review_text_slot_projection(block, translation)
            ],
            glossary=_window_glossary([block], glossary),
            target_language=target_language,
            window_ordinal=window_ordinal,
        )
        if len(single_text.encode("utf-8")) > budget_bytes:
            windows.append(((block,), (translation,)))
            current_blocks = []
            current_translations = []
        else:
            current_blocks = [block]
            current_translations = [translation]
    if current_blocks:
        windows.append((tuple(current_blocks), tuple(current_translations)))
    return tuple(windows)


def _review_translation_projection(
    translation: Mapping[str, Any],
) -> dict[str, Any]:
    parts = translation.get("parts")
    if not isinstance(parts, Sequence) or isinstance(parts, (str, bytes)):
        raise TranslationWorkflowError(
            "translation_atom_result_invalid",
            "protected translation review requires structured atom parts",
        )
    return {
        "block_id": str(translation.get("block_id", "")),
        "content": {
            "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            "parts": [dict(part) for part in parts if isinstance(part, Mapping)],
        },
    }


def _review_text_slot_projection(
    block: Mapping[str, Any], translation: Mapping[str, Any]
) -> dict[str, Any]:
    parts = translation.get("parts")
    try:
        slots = text_slot_values_from_parts(block, parts)
    except ProtectedAtomError as exc:
        raise TranslationWorkflowError(
            exc.code, str(exc), exc.details
        ) from exc
    return {
        "block_id": str(translation.get("block_id", "")),
        "content": {
            "schema_version": TEXT_SLOT_RESULT_SCHEMA,
            "text_slots": slots,
        },
    }


def _validate_draft_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if "schema_version" in value:
        return _validate_protected_atom_window(value, blocks)
    return _validate_translation_window(
        value,
        blocks,
        container_description="translation draft",
        entries_description="translation draft entries",
        mismatch_message="translation block IDs must exactly match source order",
        item_description="translated block",
    )


def _validate_translation_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    *,
    container_description: str,
    entries_description: str,
    mismatch_message: str,
    item_description: str,
) -> list[dict[str, str]]:
    _require_fields(value, {"translations"}, container_description)
    translations = _mapping_list(value["translations"], entries_description)
    expected = [str(item["block_id"]) for item in blocks]
    if [item.get("block_id") for item in translations] != expected:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            mismatch_message,
        )
    output: list[dict[str, str]] = []
    for translated, _block in zip(translations, blocks, strict=True):
        _require_fields(translated, {"block_id", "text"}, item_description)
        text = translated["text"]
        if not isinstance(text, str):
            raise TranslationWorkflowError(
                "translation_coverage_invalid", "translation text must be a string"
            )
        output.append(
            {
                "block_id": str(translated["block_id"]),
                "text": restore_translation_identity(text, _block),
            }
        )
    _validate_window_formula_identity(blocks, output)
    for translated, block in zip(output, blocks, strict=True):
        try:
            validate_translation_text(translated["text"], block)
        except TranslationSourceError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
    return output


def _validate_protected_atom_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    _require_fields(value, {"schema_version", "translations"}, "protected translation result")
    if value["schema_version"] != PROTECTED_ATOM_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_atom_result_invalid",
            "translation result uses an unsupported protected-atom schema",
        )
    translations = _mapping_list(
        value["translations"], "protected translation entries"
    )
    expected = [str(item["block_id"]) for item in blocks]
    if [item.get("block_id") for item in translations] != expected:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "protected translation block IDs must exactly match source order",
        )
    output: list[dict[str, Any]] = []
    for translated, block in zip(translations, blocks, strict=True):
        _require_fields(
            translated, {"block_id", "parts"}, "protected translated block"
        )
        try:
            text, parts = assemble_protected_translation(
                block, translated["parts"]
            )
            validate_translation_text(text, block)
        except ProtectedAtomError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        except TranslationSourceError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        output.append(
            {
                "block_id": str(translated["block_id"]),
                "text": text,
                "parts": parts,
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            }
        )
    return output


def _validate_model_protected_atom_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate raw model output with bounded caller-side atom restoration."""

    _require_fields(
        value,
        {"schema_version", "translations"},
        "protected translation result",
    )
    if value["schema_version"] != PROTECTED_ATOM_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_atom_result_invalid",
            "translation result uses an unsupported protected-atom schema",
        )
    translations = _mapping_list(
        value["translations"], "protected translation entries"
    )
    expected = [str(item["block_id"]) for item in blocks]
    if [item.get("block_id") for item in translations] != expected:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "protected translation block IDs must exactly match source order",
        )
    output: list[dict[str, Any]] = []
    for translated, block in zip(translations, blocks, strict=True):
        _require_fields(
            translated, {"block_id", "parts"}, "protected translated block"
        )
        try:
            text, parts = assemble_model_protected_translation(
                block, translated["parts"]
            )
            validate_translation_text(text, block)
        except ProtectedAtomError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        except TranslationSourceError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        output.append(
            {
                "block_id": str(translated["block_id"]),
                "text": text,
                "parts": parts,
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            }
        )
    return output


def _validate_text_slot_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Validate exact model text slots and assemble caller-owned atoms locally."""

    _require_fields(
        value,
        {"schema_version", "translations"},
        "text-slot translation result",
    )
    if value["schema_version"] != TEXT_SLOT_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_text_slot_result_invalid",
            "translation result uses an unsupported text-slot schema",
        )
    translations = value["translations"]
    if not isinstance(translations, Mapping):
        raise TranslationWorkflowError(
            "translation_text_slot_result_invalid",
            "text-slot translations must be an object",
        )
    expected = [str(item["block_id"]) for item in blocks]
    if set(translations) != set(expected) or len(translations) != len(expected):
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "text-slot translation block IDs must exactly match the source",
        )
    output: list[dict[str, Any]] = []
    for block in blocks:
        block_id = str(block["block_id"])
        translated = translations.get(block_id)
        if not isinstance(translated, Mapping):
            raise TranslationWorkflowError(
                "translation_text_slot_result_invalid",
                f"text-slot translation is invalid for {block_id}",
            )
        _require_fields(
            translated, {"text_slots"}, "text-slot translated block"
        )
        try:
            text, parts = assemble_text_slot_translation(
                block, translated["text_slots"]
            )
            validate_translation_text(text, block)
        except ProtectedAtomError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        except TranslationSourceError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        output.append(
            {
                "block_id": block_id,
                "text": text,
                "parts": parts,
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            }
        )
    return output


def _protected_candidate_items(
    value: Any,
) -> dict[str, list[Mapping[str, Any]]]:
    if not isinstance(value, Mapping):
        return {}
    raw = value.get("translations")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return {}
    items: dict[str, list[Mapping[str, Any]]] = {}
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        block_id = item.get("block_id")
        if isinstance(block_id, str):
            items.setdefault(block_id, []).append(item)
    return items


def _text_slot_candidate_items(
    value: Any,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(value, Mapping):
        return {}
    raw = value.get("translations")
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(block_id): item
        for block_id, item in raw.items()
        if isinstance(block_id, str) and isinstance(item, Mapping)
    }


def _normalized_text_slot_candidate_item(
    item: Mapping[str, Any], block: Mapping[str, Any]
) -> dict[str, Any] | None:
    block_id = str(block["block_id"])
    try:
        validated = _validate_text_slot_window(
            {
                "schema_version": TEXT_SLOT_RESULT_SCHEMA,
                "translations": {block_id: dict(item)},
            },
            (block,),
        )
    except TranslationWorkflowError:
        return None
    return protected_result_document(validated)["translations"][0]


def _normalized_model_candidate_item(
    item: Mapping[str, Any], block: Mapping[str, Any]
) -> dict[str, Any] | None:
    try:
        validated = _validate_model_protected_atom_window(
            {
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                "translations": [dict(item)],
            },
            (block,),
        )
    except TranslationWorkflowError:
        return None
    return protected_result_document(validated)["translations"][0]


def _invalid_protected_candidate_blocks(
    candidate: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any], ...]:
    if candidate.get("schema_version") == TEXT_SLOT_RESULT_SCHEMA:
        items = _text_slot_candidate_items(candidate)
        return tuple(
            block
            for block in blocks
            if (
                (item := items.get(str(block["block_id"]))) is None
                or _normalized_text_slot_candidate_item(item, block) is None
            )
        )
    if candidate.get("schema_version") != PROTECTED_ATOM_RESULT_SCHEMA:
        return tuple(blocks)
    items = _protected_candidate_items(candidate)
    invalid: list[Mapping[str, Any]] = []
    for block in blocks:
        candidates = items.get(str(block["block_id"]), ())
        if (
            len(candidates) != 1
            or _normalized_model_candidate_item(candidates[0], block) is None
        ):
            invalid.append(block)
    return tuple(invalid)


def _protected_translation_retry_request(
    request: LLMRequest,
    error: TranslationWorkflowError,
    candidate: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
    *,
    glossary: Sequence[Mapping[str, Any]],
    target_language: str,
    language: LanguageResult,
    window_ordinal: int,
) -> LLMRequest:
    invalid = _invalid_protected_candidate_blocks(candidate, blocks) or tuple(
        blocks
    )
    scoped = LLMRequest(
        _task_id(
            "translation-retry-scope",
            {
                "parent_task_id": request.task_id,
                "block_ids": [str(item["block_id"]) for item in invalid],
            },
        ),
        translation_prompt(
            blocks=[text_slot_prompt_block(item) for item in invalid],
            glossary=glossary,
            target_language=target_language,
            language_result=language.to_document(),
            window_ordinal=window_ordinal,
        ),
        JsonOutput(
            translation_schema(
                [text_slot_prompt_block(item) for item in invalid]
            ),
            repair="format",
        ),
        request.model,
        request.session,
        request.inputs,
    )
    return _semantic_retry_request(scoped, error)


def _merge_protected_translation_candidates(
    first: Mapping[str, Any],
    second: Any,
    blocks: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if (
        first.get("schema_version") == TEXT_SLOT_RESULT_SCHEMA
        or (
            isinstance(second, Mapping)
            and second.get("schema_version") == TEXT_SLOT_RESULT_SCHEMA
        )
    ):
        first_items = _text_slot_candidate_items(first)
        second_items = _text_slot_candidate_items(second)
        first_protected_items = _protected_candidate_items(first)
        second_protected_items = _protected_candidate_items(second)
        if first_protected_items or second_protected_items:
            # A retry always returns text slots, while a pre-text-slot accepted
            # neighbor may use a valid non-canonical protected-atom order.
            # Keep that validated arrangement intact and assemble only the
            # retried units into the protected representation.
            merged: list[dict[str, Any]] = []
            for block in blocks:
                block_id = str(block["block_id"])
                chosen: dict[str, Any] | None = None
                for items in (second_items, first_items):
                    candidate = items.get(block_id)
                    if candidate is None:
                        continue
                    normalized = _normalized_text_slot_candidate_item(
                        candidate, block
                    )
                    if normalized is not None:
                        chosen = normalized
                        break
                if chosen is None:
                    for items in (second_protected_items, first_protected_items):
                        candidates = items.get(block_id, ())
                        if len(candidates) != 1:
                            continue
                        normalized = _normalized_model_candidate_item(
                            candidates[0], block
                        )
                        if normalized is not None:
                            chosen = normalized
                            break
                if chosen is None:
                    for items in (second_protected_items, first_protected_items):
                        candidates = items.get(block_id, ())
                        if candidates:
                            chosen = dict(candidates[0])
                            break
                if chosen is None:
                    for items in (second_items, first_items):
                        candidate = items.get(block_id)
                        if candidate is not None:
                            chosen = dict(candidate)
                            break
                if chosen is not None:
                    merged.append(chosen)
            return {
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                "translations": merged,
            }
        merged_slots: dict[str, dict[str, Any]] = {}
        for block in blocks:
            block_id = str(block["block_id"])
            chosen: dict[str, Any] | None = None
            for items in (second_items, first_items):
                candidate = items.get(block_id)
                if candidate is None:
                    continue
                if _normalized_text_slot_candidate_item(candidate, block) is not None:
                    chosen = dict(candidate)
                    break
            if chosen is None:
                for items in (second_items, first_items):
                    candidate = items.get(block_id)
                    if candidate is not None:
                        chosen = dict(candidate)
                        break
            if chosen is not None:
                merged_slots[block_id] = chosen
        return {
            "schema_version": TEXT_SLOT_RESULT_SCHEMA,
            "translations": merged_slots,
        }
    first_items = _protected_candidate_items(first)
    second_items = _protected_candidate_items(second)
    merged: list[dict[str, Any]] = []
    for block in blocks:
        block_id = str(block["block_id"])
        chosen: dict[str, Any] | None = None
        for items in (second_items, first_items):
            candidates = items.get(block_id, ())
            if len(candidates) != 1:
                continue
            chosen = _normalized_model_candidate_item(candidates[0], block)
            if chosen is not None:
                break
        if chosen is None:
            for items in (second_items, first_items):
                candidates = items.get(block_id, ())
                if candidates:
                    chosen = dict(candidates[0])
                    break
        if chosen is not None:
            merged.append(chosen)
    return {
        "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
        "translations": merged,
    }


def _validated_draft_document(
    value: Any, blocks: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    document = _object(value, "translation draft")
    _validate_draft_window(document, blocks)
    return document


def _validated_protected_draft_document(
    value: Any, blocks: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    document = _object(value, "protected translation draft")
    if document.get("schema_version") == TEXT_SLOT_RESULT_SCHEMA:
        validated = _validate_text_slot_window(document, blocks)
        return protected_result_document(validated)
    if document.get("schema_version") != PROTECTED_ATOM_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_atom_result_invalid",
            "translation calls must use a supported caller-owned result schema",
        )
    validated = _validate_model_protected_atom_window(document, blocks)
    return protected_result_document(validated)


def _validate_accepted_window(
    value: Mapping[str, Any],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if "schema_version" in value:
        return _validate_protected_atom_window(value, blocks)
    return _validate_translation_window(
        value,
        blocks,
        container_description="accepted translation window",
        entries_description="accepted translation entries",
        mismatch_message="accepted translations must exactly match source order",
        item_description="accepted translation",
    )


def _review_accepted_window_document(
    accepted: Mapping[str, Any],
    *,
    fallback_document: Mapping[str, Any] | None = None,
    provider_failure_document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind a review outcome to its diagnostics in one immutable artifact."""

    if fallback_document is None and provider_failure_document is None:
        return dict(accepted)
    if fallback_document is not None:
        _translation_fallback_entries(fallback_document)
    if provider_failure_document is not None:
        _validate_translation_provider_failure_document(
            provider_failure_document
        )
    return {
        "schema_version": REVIEW_ACCEPTED_WINDOW_SCHEMA,
        "accepted": dict(accepted),
        "fallback": (
            dict(fallback_document)
            if fallback_document is not None
            else None
        ),
        "provider_failure": (
            dict(provider_failure_document)
            if provider_failure_document is not None
            else None
        ),
    }


def _unpack_review_accepted_window(
    value: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    if value.get("schema_version") != REVIEW_ACCEPTED_WINDOW_SCHEMA:
        return dict(value), None, None
    _require_fields(
        value,
        {"schema_version", "accepted", "fallback", "provider_failure"},
        "review accepted translation window",
    )
    accepted = _object(value["accepted"], "review accepted translation")
    fallback_value = value["fallback"]
    provider_value = value["provider_failure"]
    if fallback_value is not None and not isinstance(fallback_value, Mapping):
        raise TranslationWorkflowError(
            "translation_review_acceptance_invalid",
            "review accepted fallback evidence is invalid",
        )
    if provider_value is not None and not isinstance(provider_value, Mapping):
        raise TranslationWorkflowError(
            "translation_review_acceptance_invalid",
            "review accepted provider evidence is invalid",
        )
    fallback = dict(fallback_value) if isinstance(fallback_value, Mapping) else None
    provider_failure = (
        dict(provider_value) if isinstance(provider_value, Mapping) else None
    )
    if fallback is None:
        if provider_failure is not None:
            raise TranslationWorkflowError(
                "translation_review_acceptance_invalid",
                "review provider evidence requires fallback evidence",
            )
    else:
        _translation_fallback_entries(fallback)
    if provider_failure is not None:
        _validate_translation_provider_failure_document(provider_failure)
    return accepted, fallback, provider_failure


def _migrate_legacy_accepted_list_windows(
    values: Mapping[int, Mapping[str, Any]],
    windows: Sequence[Sequence[Mapping[str, Any]]],
    plans: Sequence[_TranslationUnitPlan],
) -> dict[int, Mapping[str, Any]]:
    """Replay old whole-list translations across current item-unit windows."""

    original = dict(values)
    if not original:
        return original
    expected = tuple(
        str(block["block_id"])
        for window in windows
        for block in window
    )
    expected_set = set(expected)
    plans_by_owner = {
        plan.block_id: plan
        for plan in plans
        if plan.kind == "list" and not plan.direct
    }
    migrated: list[dict[str, str]] = []
    used_legacy_owner = False
    for ordinal in sorted(original):
        value = original[ordinal]
        raw = value.get("translations")
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            return original
        for item in raw:
            if (
                not isinstance(item, Mapping)
                or set(item) != {"block_id", "text"}
                or not isinstance(item.get("block_id"), str)
                or not isinstance(item.get("text"), str)
            ):
                return original
            block_id = str(item["block_id"])
            text = str(item["text"])
            if block_id in expected_set:
                migrated.append({"block_id": block_id, "text": text})
                continue
            plan = plans_by_owner.get(block_id)
            if plan is None or any(len(group) != 1 for group in plan.unit_groups):
                return original
            unit_ids = tuple(group[0] for group in plan.unit_groups)
            if not set(unit_ids).issubset(expected_set):
                return original
            lines = tuple(
                line.strip() for line in text.splitlines() if line.strip()
            )
            if len(lines) != len(unit_ids):
                return original
            used_legacy_owner = True
            migrated.extend(
                {"block_id": unit_id, "text": line}
                for unit_id, line in zip(unit_ids, lines, strict=True)
            )
    if not used_legacy_owner:
        return original
    migrated_ids = tuple(item["block_id"] for item in migrated)
    if migrated_ids != expected[: len(migrated_ids)]:
        return original
    repartitioned: dict[int, Mapping[str, Any]] = {}
    cursor = 0
    for ordinal, window in enumerate(windows):
        window_size = len(window)
        entries = migrated[cursor : cursor + window_size]
        if not entries:
            break
        repartitioned[ordinal] = {"translations": entries}
        cursor += len(entries)
        if len(entries) != window_size:
            break
    return repartitioned


def _validate_window_formula_identity(
    blocks: Sequence[Mapping[str, Any]],
    translations: Sequence[Mapping[str, str]],
) -> None:
    diagnostics = formula_identity_diagnostics(blocks, translations)
    if not diagnostics:
        return
    first = diagnostics[0]
    raise TranslationWorkflowError(
        "translation_source_identity_invalid",
        "translation changed formula occurrences for "
        f"{first['source_block_id']}",
        {"formula_diagnostics": list(diagnostics)},
    )


def _apply_review(
    value: Any,
    draft: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    document = _object(value, "translation review")
    _require_fields(
        document,
        {"schema_version", "translation_patches", "summary"},
        "translation review",
    )
    if document["schema_version"] != PROTECTED_ATOM_REVIEW_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_review_invalid",
            "review result uses an unsupported protected-atom schema",
        )
    patches = _mapping_list(
        document["translation_patches"], "translation review patches"
    )
    if not isinstance(document["summary"], str) or not document["summary"].strip():
        raise TranslationWorkflowError(
            "translation_review_invalid", "review summary must be non-empty"
        )
    allowed = {str(item["block_id"]) for item in draft}
    replacements: dict[str, Any] = {}
    for patch in patches:
        _require_fields(
            patch, {"block_id", "parts"}, "translation review patch"
        )
        block_id = _string(patch, "block_id")
        if block_id not in allowed or block_id in replacements:
            raise TranslationWorkflowError(
                "translation_review_invalid",
                "review patch IDs must be unique existing block IDs",
            )
        replacements[block_id] = patch["parts"]
    reviewed = []
    for item, block in zip(draft, blocks, strict=True):
        parts = replacements.get(str(item["block_id"]), item.get("parts"))
        try:
            text, normalized_parts = assemble_model_protected_translation(
                block, parts
            )
        except ProtectedAtomError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        reviewed.append(
            {
                "block_id": str(item["block_id"]),
                "text": text,
                "parts": normalized_parts,
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            }
        )
    return _validate_protected_atom_window(
        protected_result_document(reviewed), blocks
    )


def _apply_text_slot_review(
    value: Any,
    draft: Sequence[Mapping[str, Any]],
    blocks: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    document = _object(value, "text-slot translation review")
    _require_fields(
        document,
        {"schema_version", "translation_patches", "summary"},
        "text-slot translation review",
    )
    if document["schema_version"] != TEXT_SLOT_REVIEW_RESULT_SCHEMA:
        raise TranslationWorkflowError(
            "translation_review_invalid",
            "review result uses an unsupported text-slot schema",
        )
    patches = document["translation_patches"]
    if not isinstance(patches, Mapping):
        raise TranslationWorkflowError(
            "translation_review_invalid",
            "text-slot review patches must be an object",
        )
    if not isinstance(document["summary"], str) or not document["summary"].strip():
        raise TranslationWorkflowError(
            "translation_review_invalid", "review summary must be non-empty"
        )
    allowed = {str(item["block_id"]) for item in draft}
    if set(patches) - allowed:
        raise TranslationWorkflowError(
            "translation_review_invalid",
            "text-slot review patch IDs must be existing block IDs",
        )

    reviewed: list[dict[str, Any]] = []
    for item, block in zip(draft, blocks, strict=True):
        block_id = str(item["block_id"])
        patch = patches.get(block_id)
        if patch is None:
            reviewed.extend(
                _validate_protected_atom_window(
                    protected_result_document([item]), (block,)
                )
            )
            continue
        if not isinstance(patch, Mapping):
            raise TranslationWorkflowError(
                "translation_review_invalid",
                f"text-slot review patch is invalid for {block_id}",
            )
        _require_fields(patch, {"text_slots"}, "text-slot review patch")
        try:
            text, parts = assemble_text_slot_translation(
                block, patch["text_slots"]
            )
        except ProtectedAtomError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        reviewed.append(
            {
                "block_id": block_id,
                "text": text,
                "parts": parts,
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
            }
        )
    return _validate_protected_atom_window(
        protected_result_document(reviewed), blocks
    )


def _validate_language_binding(
    result: LanguageResult,
    source: TranslationSource,
    target_language: str,
) -> None:
    if (
        result.document_digest != source.document_digest
        or result.source_digest != source.source_digest
        or result.target_language != target_language
    ):
        raise TranslationWorkflowError(
            "language_result_binding_mismatch",
            "language result does not match source and target language",
        )


def _validate_glossary_binding(
    result: GlossaryResult,
    source: TranslationSource,
    target_language: str,
) -> None:
    if (
        result.document_digest != source.document_digest
        or result.source_digest != source.source_digest
        or result.target_language != target_language
    ):
        raise TranslationWorkflowError(
            "glossary_result_binding_mismatch",
            "glossary result does not match source and target language",
        )


def _validate_translation_result(
    context: RunContext,
    result: TranslationResult,
    source: TranslationSource,
    language: LanguageResult,
    target_language: str,
    blocks: Sequence[Mapping[str, Any]],
    *,
    expected_coverage: str,
) -> None:
    if (
        result.layer.source
        != source_identity_from_rich_document(source.rich)
        or result.layer.producer != "alc-translate"
        or result.source_language != language.language_tag
        or result.target_language != target_language
        or result.mode != language.mode
        or result.coverage != expected_coverage
    ):
        raise TranslationWorkflowError(
            "translation_result_binding_mismatch",
            "translation result does not match source, language, or target",
        )
    if result.mode == "skipped":
        if result.revision_artifacts:
            raise TranslationWorkflowError(
                "translation_coverage_invalid",
                "skipped translation result must be empty",
            )
        return
    expected = [
        str(item["block_id"])
        for item in blocks
        if not _is_nonlinguistic_media_block(item)
    ]
    actual: list[str] = []
    source_blocks_by_id = {
        block.block_id: block for block in source.rich.blocks
    }
    projected_source_blocks_by_id = {
        str(block["block_id"]): block for block in blocks
    }
    for item in result.revision_artifacts:
        try:
            payload = context.artifacts.read_bytes(item.artifact).decode(
                "utf-8"
            )
            revision = decode_fragment_revision(
                payload,
                filename=Path(item.revision.path).name,
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise TranslationWorkflowError(
                "translation_revision_invalid",
                "translation revision artifact is unreadable or invalid",
            ) from exc
        if (
            revision.semantic_digest != item.revision.semantic_digest
            or revision.fragment_id != item.revision.fragment_id
            or revision.source != result.layer.source
            or revision.priority != 10
            or revision.role != "translation"
            or revision.language != target_language
            or revision.anchor.kind is not AnchorKind.BLOCK
        ):
            raise TranslationWorkflowError(
                "translation_revision_binding_mismatch",
                "translation revision does not match its result manifest",
            )
        note_contract = revision.provenance.get("source_note_translation")
        if note_contract is not None:
            if (
                not isinstance(note_contract, Mapping)
                or set(note_contract) != {"schema_version", "note_id"}
                or note_contract.get("schema_version")
                != "alc.render.source_note_translation.v1"
                or not isinstance(note_contract.get("note_id"), str)
                or not str(note_contract["note_id"])
            ):
                raise TranslationWorkflowError(
                    "translation_revision_binding_mismatch",
                    "source note translation provenance is invalid",
                )
            unit_id = f"source-note:{note_contract['note_id']}"
            source_unit = projected_source_blocks_by_id.get(unit_id)
            binding = source_unit.get("source_note") if source_unit else None
            owner_block_id = (
                str(binding.get("owner_block_id", ""))
                if isinstance(binding, Mapping)
                else ""
            )
            rich_block = source_blocks_by_id.get(owner_block_id)
            if (
                source_unit is None
                or not isinstance(binding, Mapping)
                or binding.get("note_id") != note_contract["note_id"]
                or rich_block is None
                or revision.anchor.target_id != owner_block_id
                or revision.anchor.related_block_ids != (owner_block_id,)
                or revision.anchor.related_blocks[0]
                != anchor_block_from_rich_block(rich_block)
            ):
                raise TranslationWorkflowError(
                    "translation_revision_binding_mismatch",
                    "source note translation does not match its exact owner",
                )
            rich_block_document = source_unit
            actual_id = unit_id
        else:
            block_id = revision.anchor.target_id
            rich_block = source_blocks_by_id.get(block_id)
            if (
                rich_block is None
                or revision.anchor.related_block_ids != (block_id,)
                or revision.anchor.related_blocks[0]
                != anchor_block_from_rich_block(rich_block)
            ):
                raise TranslationWorkflowError(
                    "translation_revision_binding_mismatch",
                    "translation revision anchor does not match its RichDocument block",
                )
            rich_block_document = projected_source_blocks_by_id.get(block_id)
            if rich_block_document is None:
                raise TranslationWorkflowError(
                    "translation_revision_binding_mismatch",
                    "translation revision refers to an unselected source block",
                )
            actual_id = block_id
        atom_contract = revision.provenance.get("protected_atoms")
        if atom_contract is not None and (
            not isinstance(atom_contract, Mapping)
            or atom_contract
            != {
                "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                "assembled_by": "caller",
            }
        ):
            raise TranslationWorkflowError(
                "translation_revision_binding_mismatch",
                "protected-atom translation provenance is invalid",
            )
        try:
            if atom_contract is not None:
                # The model never produced Markdown/TeX/URL payloads for this
                # revision. Exact atom coverage was checked before caller-side
                # assembly, so do not re-parse it as model-authored Markdown.
                pass
            elif note_contract is not None:
                validate_translation_text(
                    revision.markdown_body,
                    rich_block_document,
                )
            elif rich_block.kind is RichBlockKind.CODE:
                expected_code = block_text_to_markdown(
                    rich_block,
                    str(rich_block.payload["text"]),
                )
                if revision.markdown_body != expected_code:
                    raise TranslationSourceError(
                        "translation_source_identity_invalid",
                        f"translation changed code text for {block_id}",
                    )
            elif rich_block.kind is RichBlockKind.EQUATION:
                expected_equation = block_text_to_markdown(
                    rich_block,
                    str(rich_block.payload["tex"]),
                )
                if revision.markdown_body != expected_equation:
                    raise TranslationSourceError(
                        "translation_source_identity_invalid",
                        f"translation changed equation text for {block_id}",
                    )
            else:
                validate_translation_text(
                    revision.markdown_body,
                    rich_block_document,
                )
        except TranslationSourceError as exc:
            raise TranslationWorkflowError(
                exc.code, str(exc), exc.details
            ) from exc
        actual.append(actual_id)
    if actual != expected:
        raise TranslationWorkflowError(
            "translation_coverage_invalid",
            "translation result must cover all source blocks in order",
        )


def _publish_translation_result(
    context: RunContext,
    source: TranslationSource,
    *,
    translations: Sequence[Mapping[str, str]],
    units: Sequence[Mapping[str, Any]],
    source_language: str,
    target_language: str,
    artifact_prefix: str,
    coverage: str,
    fallback_kinds: Mapping[str, str] | None = None,
    protected_atom_block_ids: set[str] | None = None,
) -> TranslationResult:
    rich_blocks = {item.block_id: item for item in source.rich.blocks}
    units_by_id = {str(item["block_id"]): item for item in units}
    fallback_by_id = dict(fallback_kinds or {})
    protected_by_id = set(protected_atom_block_ids or ())
    if any(
        kind not in {"source_text", "review_skipped"}
        for kind in fallback_by_id.values()
    ):
        raise TranslationWorkflowError(
            "translation_fallback_invalid",
            "translation fallback kind is invalid",
        )
    if not protected_by_id.issubset(units_by_id):
        raise TranslationWorkflowError(
            "translation_atom_result_invalid",
            "protected-atom provenance refers to an unknown source unit",
        )
    source_identity = source_identity_from_rich_document(source.rich)
    revisions: list[FragmentRevisionRef] = []
    artifacts: list[TranslationRevisionArtifact] = []
    for translated in translations:
        block_id = str(translated["block_id"])
        unit = units_by_id.get(block_id)
        if unit is None:
            raise TranslationWorkflowError(
                "translation_coverage_invalid",
                f"translation refers to unknown source unit {block_id}",
            )
        note_binding = unit.get("source_note")
        if isinstance(note_binding, Mapping):
            owner_block_id = str(note_binding.get("owner_block_id", ""))
            note_id = str(note_binding.get("note_id", ""))
            block = rich_blocks.get(owner_block_id)
            if block is None or not note_id:
                raise TranslationWorkflowError(
                    "source_notes_invalid",
                    "source note translation owner is invalid",
                )
            markdown_body = normalize_markdown(
                str(translated["text"])
            ).rstrip("\n") + "\n"
            note_provenance: dict[str, Any] = {
                "source_note_translation": {
                    "schema_version": "alc.render.source_note_translation.v1",
                    "note_id": note_id,
                }
            }
        else:
            block = rich_blocks.get(block_id)
            if block is None:
                raise TranslationWorkflowError(
                    "translation_coverage_invalid",
                    f"translation refers to unknown source block {block_id}",
                )
            block_document = rich_block_to_document(block)
            if _is_nonlinguistic_media_translation(
                block_document, str(translated["text"])
            ):
                continue
            markdown_body = block_text_to_markdown(
                block,
                str(translated["text"]),
            )
            note_provenance = {}
        fragment_material = {
            "producer": "alc-translate",
            "source": source_identity.rich_document_digest,
            "block_id": block_id,
            "target_language": target_language,
            "markdown_body": markdown_body,
            "fallback_kind": fallback_by_id.get(block_id),
            "protected_atom_schema": (
                PROTECTED_ATOM_RESULT_SCHEMA
                if block_id in protected_by_id
                else None
            ),
        }
        fragment_digest = hashlib.sha256(
            canonical_json_bytes(fragment_material)
        ).hexdigest()
        fallback_kind = fallback_by_id.get(block_id)
        fallback_provenance = (
            {
                "translation_fallback": {
                    "schema_version": "alc.translate.fallback.v1",
                    "kind": fallback_kind,
                    "source_preserved": fallback_kind == "source_text",
                }
            }
            if fallback_kind is not None
            else {}
        )
        atom_provenance = (
            {
                "protected_atoms": {
                    "schema_version": PROTECTED_ATOM_RESULT_SCHEMA,
                    "assembled_by": "caller",
                }
            }
            if block_id in protected_by_id
            else {}
        )
        revision = FragmentRevision(
            source=source_identity,
            fragment_id=f"translation-{fragment_digest[:32]}",
            revision=1,
            parent_semantic_digest=None,
            anchor=FragmentAnchor(
                AnchorKind.BLOCK,
                block.block_id,
                (anchor_block_from_rich_block(block),),
            ),
            priority=10,
            role="translation",
            language=target_language,
            title=None,
            citation_ids=(),
            provenance={
                "producer": "alc-translate",
                "source_language": source_language,
                "translation_mode": "enabled",
                **fallback_provenance,
                **atom_provenance,
                **note_provenance,
            },
            markdown_body=markdown_body,
        )
        path = fragment_revision_storage_path(revision)
        reference = fragment_revision_ref(path, revision)
        artifact = context.artifacts.publish_bytes(
            f"{artifact_prefix}/fragments/{revision.fragment_id}/revision-000001",
            encode_fragment_revision(revision).encode("utf-8"),
            media_type="text/markdown",
        )
        revisions.append(reference)
        artifacts.append(TranslationRevisionArtifact(reference, artifact))
    return TranslationResult(
        source_language=source_language,
        target_language=target_language,
        mode="enabled",
        coverage=coverage,
        layer=Layer(source_identity, "alc-translate", tuple(revisions)),
        revision_artifacts=tuple(artifacts),
    )


_awaiting = awaiting_from_pause
_run_error = run_error_from_failure


def _read_json_artifact(
    context: RunContext, ref: Any, description: str
) -> dict[str, Any]:
    try:
        value = json.loads(context.artifacts.read_bytes(ref).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranslationWorkflowError(
            "artifact_invalid", f"{description} is unreadable"
        ) from exc
    return _object(value, description)


def _task_id(prefix: str, semantic: Any) -> str:
    return f"{prefix}-{_digest(semantic)[:24]}"


def _digest(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _object(value: Any, description: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TranslationWorkflowError(
            "model_output_invalid", f"{description} must be an object"
        )
    return dict(value)


def _mapping_list(value: Any, description: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise TranslationWorkflowError(
            "model_output_invalid",
            f"{description} must be an array of objects",
        )
    return [dict(item) for item in value]


def _require_fields(
    value: Mapping[str, Any], fields: set[str], description: str
) -> None:
    if set(value) != fields:
        raise TranslationWorkflowError(
            "model_output_invalid", f"{description} has invalid fields"
        )


def _string_items(value: Any, description: str) -> tuple[str, ...]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or any(not isinstance(item, str) or not item for item in value)
    ):
        raise TranslationWorkflowError(
            "translation_fallback_invalid",
            f"{description} must contain non-empty strings",
        )
    items = tuple(value)
    if len(items) != len(set(items)):
        raise TranslationWorkflowError(
            "translation_fallback_invalid",
            f"{description} contains duplicates",
        )
    return items


def _string(value: Mapping[str, Any], key: str) -> str:
    item = value.get(key)
    if not isinstance(item, str):
        raise TranslationWorkflowError(
            "model_output_invalid", f"{key} must be a string"
        )
    return item


def _integer(value: Mapping[str, Any], key: str) -> int:
    item = value.get(key)
    if isinstance(item, bool) or not isinstance(item, int):
        raise TranslationWorkflowError(
            "model_output_invalid", f"{key} must be an integer"
        )
    return item


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


__all__ = [
    "REVIEW_SUPERVISION_SCHEMA",
    "GlossaryFallbackSummary",
    "GlossaryResult",
    "KeywordProvider",
    "LanguageResult",
    "TranslationResult",
    "TranslationRevisionArtifact",
    "TranslationWorkflowError",
    "TranslationWorkflowService",
    "outer_resume_input",
]
