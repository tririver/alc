from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
import alc_translate.source as source_module

from ac_jobs import (
    ArtifactDigest,
    ArtifactSourceRef,
    Paused,
    RunContext,
    RunError,
    RunRepository,
    RunSpec,
    RunStatus,
    canonical_json_bytes,
)
from ac_llm import (
    FailureCategory,
    LLMCompleted,
    LLMFailed,
    ProviderFailure,
)
from ac_document import AcDocumentService, RichDocumentParserService
from alc_render import decode_fragment_revision

from alc_translate import (
    BlocksRequest,
    GenerationRecipe,
    GlossaryRequest,
    GlossaryResult,
    LanguageRequest,
    LanguageResult,
    TranslationService,
    TranslationResult,
    TranslationSource,
    TranslationWorkflowService,
    source_blocks,
)
from alc_translate.prompts import (
    GLOSSARY_SCHEMA,
    GLOSSARY_PROMPT_VERSION,
    LANGUAGE_PROMPT_VERSION,
    REVIEW_PROMPT_VERSION,
    TRANSLATION_SCHEMA,
    TRANSLATION_PROMPT_VERSION,
    glossary_prompt,
    review_prompt,
    translation_prompt,
)
from alc_translate.source import block_text
from alc_translate.source import (
    STRUCTURAL_FIGURE_PLACEHOLDER,
    TranslationSourceError,
    resolve_translation_source,
)
from alc_translate.workflow import (
    OUTPUT_SUPERVISION_SCHEMA,
    TranslationWorkflowError,
    _bounded_model_translation_units,
    _collapse_model_translation_units_with_fallback,
    _digest,
    _model_translation_blocks,
    _output_supervision,
    _salvaged_translation_fallback,
    _translation_review_windows,
    _translation_units,
    _translation_windows,
    _validate_draft_window,
)
from alc_translate.service import _run_id


class FakeTasks:
    def __init__(
        self,
        *,
        language: str = "en",
        classification: str = "known",
        invalid_review: bool = False,
        translation_prefix: str = "translated:",
        translation_prefix_by_text: dict[str, str] | None = None,
    ) -> None:
        self.language = language
        self.classification = classification
        self.invalid_review = invalid_review
        self.translation_prefix = translation_prefix
        self.translation_prefix_by_text = translation_prefix_by_text or {}
        self.calls: list[str] = []
        self.translation_glossaries: list[list[str]] = []
        self.prompt_glossary_fields: list[list[set[str]]] = []
        self.translation_blocks: list[list[dict[str, Any]]] = []
        self.review_blocks: list[list[dict[str, Any]]] = []
        self.prompt_sizes: list[tuple[str, int]] = []

    def execute_or_resume(
        self, _context, request, *, input=None, options=None
    ):
        contract, payload = _prompt(request.prompt)
        self.calls.append(contract)
        self.prompt_sizes.append((contract, len(request.prompt.encode("utf-8"))))
        if contract == LANGUAGE_PROMPT_VERSION:
            value = {
                "language_tag": self.language,
                "classification": self.classification,
                "confidence": 0.9,
            }
        elif contract == GLOSSARY_PROMPT_VERSION:
            value = {
                "entries": [
                    {
                        "term_id": term["term_id"],
                        "preferred_translation": f"target:{term['term']}",
                        "target_definition": f"definition:{term['term']}",
                    }
                    for term in payload["terms"]
                ]
            }
        elif contract == TRANSLATION_PROMPT_VERSION:
            self.translation_blocks.append(payload["blocks"])
            self.translation_glossaries.append(
                [item["term"] for item in payload["glossary"]]
            )
            self.prompt_glossary_fields.append(
                [set(item) for item in payload["glossary"]]
            )
            translations = []
            for block in payload["blocks"]:
                identity = block["source_identity"]
                if identity["code_text"] is not None:
                    text = identity["code_text"]
                elif block["kind"] == "equation":
                    text = block_text(block)
                else:
                    source_text = block_text(block)
                    prefix = next(
                        (
                            value
                            for marker, value in (
                                self.translation_prefix_by_text.items()
                            )
                            if marker in source_text
                        ),
                        self.translation_prefix,
                    )
                    text = f"{prefix}{source_text}"
                for token in [
                    *identity["equations"],
                    *identity["link_targets"],
                ]:
                    if token not in text:
                        text += f" {token}"
                if not text.strip():
                    text = "translated:block"
                translations.append(
                    {
                        "block_id": block["block_id"],
                        "text": text,
                    }
                )
            value = {"translations": translations}
        elif contract == REVIEW_PROMPT_VERSION:
            self.review_blocks.append(payload["blocks"])
            self.prompt_glossary_fields.append(
                [set(item) for item in payload["glossary"]]
            )
            patches = (
                [{"block_id": "missing-block", "replacement": "unsafe"}]
                if self.invalid_review
                else []
            )
            value = {
                "translation_patches": patches,
                "summary": "reviewed",
            }
        else:  # pragma: no cover - guards contract drift
            raise AssertionError(contract)
        return LLMCompleted(value, "fake", "fake", None, None)


class InvalidGlossaryTasks:
    def __init__(self):
        self.calls = 0

    def execute_or_resume(self, _context, request, *, input=None, options=None):
        contract, _payload = _prompt(request.prompt)
        assert contract == GLOSSARY_PROMPT_VERSION
        self.calls += 1
        return LLMCompleted(
            {
                "entries": [
                    {
                        "term_id": "wrong-id",
                        "preferred_translation": "wrong",
                        "target_definition": "wrong",
                    }
                ]
            },
            "fake",
            "fake",
            None,
            None,
        )


class ProviderFailingTasks:
    def execute_or_resume(self, _context, _request, *, input=None, options=None):
        return LLMFailed(
            ProviderFailure(
                "credentials are unavailable",
                category=FailureCategory.AUTHENTICATION,
            )
        )


class ReviewProviderFailingTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, _payload = _prompt(request.prompt)
        if contract == REVIEW_PROMPT_VERSION:
            return LLMFailed(
                ProviderFailure(
                    "review credentials are unavailable",
                    category=FailureCategory.AUTHENTICATION,
                )
            )
        return super().execute_or_resume(
            context, request, input=input, options=options
        )


class OverescapedFormulaTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, _payload = _prompt(request.prompt)
        outcome = super().execute_or_resume(
            context, request, input=input, options=options
        )
        if contract != TRANSLATION_PROMPT_VERSION:
            return outcome
        translations = [
            {
                **item,
                "text": str(item["text"]).replace(
                    r"\Psi^\dagger", r"\\Psi^\dagger"
                ),
            }
            for item in outcome.value["translations"]
        ]
        return LLMCompleted(
            {"translations": translations},
            outcome.provider,
            outcome.model,
            outcome.session,
            outcome.usage,
            outcome.warnings,
        )


class ListItemDroppingTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, payload = _prompt(request.prompt)
        outcome = super().execute_or_resume(
            context, request, input=input, options=options
        )
        if contract != TRANSLATION_PROMPT_VERSION:
            return outcome
        translations = []
        for block, translated in zip(
            payload["blocks"], outcome.value["translations"], strict=True
        ):
            text = str(translated["text"])
            if block["kind"] == "list":
                text = text.splitlines()[0]
            translations.append({**translated, "text": text})
        return LLMCompleted(
            {"translations": translations},
            outcome.provider,
            outcome.model,
            outcome.session,
            outcome.usage,
            outcome.warnings,
        )


class ListItemNewlineTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, payload = _prompt(request.prompt)
        outcome = super().execute_or_resume(
            context, request, input=input, options=options
        )
        if contract != TRANSLATION_PROMPT_VERSION:
            return outcome
        list_ordinal = 0
        translations = []
        for block, translated in zip(
            payload["blocks"], outcome.value["translations"], strict=True
        ):
            text = str(translated["text"])
            if ".translation-unit-" in str(block["block_id"]):
                text = "un\nextra" if list_ordinal == 0 else "deux"
                list_ordinal += 1
            translations.append({**translated, "text": text})
        return LLMCompleted(
            {"translations": translations},
            outcome.provider,
            outcome.model,
            outcome.session,
            outcome.usage,
            outcome.warnings,
        )


class FormulaOmittingTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, payload = _prompt(request.prompt)
        outcome = super().execute_or_resume(
            context, request, input=input, options=options
        )
        if contract != TRANSLATION_PROMPT_VERSION:
            return outcome
        translations = []
        for block, translated in zip(
            payload["blocks"], outcome.value["translations"], strict=True
        ):
            text = str(translated["text"])
            if block["source_identity"]["equations"]:
                text = "translated text without its formula"
            translations.append({**translated, "text": text})
        return LLMCompleted(
            {"translations": translations},
            outcome.provider,
            outcome.model,
            outcome.session,
            outcome.usage,
            outcome.warnings,
        )


class LinkOmittingTasks(FakeTasks):
    def execute_or_resume(
        self, context, request, *, input=None, options=None
    ):
        contract, payload = _prompt(request.prompt)
        outcome = super().execute_or_resume(
            context, request, input=input, options=options
        )
        if contract != TRANSLATION_PROMPT_VERSION:
            return outcome
        translations = []
        for block, translated in zip(
            payload["blocks"], outcome.value["translations"], strict=True
        ):
            text = str(translated["text"])
            if block["source_identity"]["link_targets"]:
                text = "translated text without its link"
            translations.append({**translated, "text": text})
        return LLMCompleted(
            {"translations": translations},
            outcome.provider,
            outcome.model,
            outcome.session,
            outcome.usage,
            outcome.warnings,
        )


class InvalidOnceTasks(FakeTasks):
    def __init__(self, invalid_contract: str):
        super().__init__()
        self.invalid_contract = invalid_contract
        self.invalid_attempts = 0
        self.task_ids: list[str] = []

    def execute_or_resume(self, context, request, *, input=None, options=None):
        contract, _payload = _prompt(request.prompt)
        self.task_ids.append(request.task_id)
        if contract == self.invalid_contract and self.invalid_attempts == 0:
            self.invalid_attempts += 1
            self.calls.append(contract)
            if contract == LANGUAGE_PROMPT_VERSION:
                value = {
                    "language_tag": " ",
                    "classification": "known",
                    "confidence": 0.9,
                }
            elif contract == TRANSLATION_PROMPT_VERSION:
                value = {
                    "translations": [
                        {"block_id": "wrong-block", "text": "translated"}
                    ]
                }
            else:  # pragma: no cover - guards fixture scope
                raise AssertionError(contract)
            return LLMCompleted(value, "fake", "fake", None, None)
        return super().execute_or_resume(
            context, request, input=input, options=options
        )


@dataclass
class FakeKeywords:
    terms: list[dict[str, Any]]
    calls: int = 0

    def extract_keywords(
        self,
        _context,
        source,
        *,
        approx_count=50,
        model=None,
        resume_input=None,
        options=None,
    ):
        self.calls += 1
        payload = canonical_json_bytes(self.terms)
        return {
            "schema_version": "ac.document.keyword_result.v1",
            "document_digest": source.document_digest,
            "source_digest": source.source.artifact_digest,
            "approx_count": approx_count,
            "planned_count": (3 * approx_count + 1) // 2,
            "returned_count": len(self.terms),
            "terms": self.terms,
            "inventory_digest": hashlib.sha256(payload).hexdigest(),
            "warnings": [],
        }


def _term(
    term_id: str, term: str, *, sentence: str | None = None
) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "term": term,
        "aliases": [],
        "occurrence_count": 2,
        "source_refs": ["section:intro"],
        "matched_sentences": [
            {
                "text": sentence or f"{term} occurs here.",
                "section_id": "intro",
                "page_number": None,
                "matched_surface": term,
                "clipped": False,
            }
        ],
    }


def _source(tmp_path: Path) -> TranslationSource:
    markdown = tmp_path / "source.md"
    markdown.write_text(
        "# Intro\n\nEntropy appears in this paragraph.\n\n"
        "# Methods\n\nA tensor appears in this paragraph.\n\n"
        "```python\nprint('fixed')\n```\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "document-cache")
    artifact = paper.import_source(markdown)
    rich = RichDocumentParserService(paper.repository).parse_source(artifact)
    return TranslationSource(rich)


def _context(tmp_path: Path, run_id: str = "parent-run") -> RunContext:
    repository = RunRepository(tmp_path / "jobs")
    snapshot = repository.create(RunSpec(run_id, "test.parent", {}))
    return RunContext(
        repository,
        snapshot,
        resume_input=None,
    )


def _prompt(prompt: str) -> tuple[str, dict[str, Any]]:
    contract = prompt.splitlines()[0].removeprefix("Contract: ")
    payload = json.loads(prompt.split("Input JSON:\n", 1)[1])
    return contract, payload


def test_equation_translation_round_trips_through_fragment_markdown(
    tmp_path: Path,
) -> None:
    tex = r"\left[p_\mu\right](p'-p)"
    markdown = tmp_path / "equation.md"
    markdown.write_text(
        f"# Equation\n\n$$\n{tex}\n$$\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "equation-cache")
    rich = RichDocumentParserService(paper.repository).parse_source(
        paper.import_source(markdown)
    )
    source = TranslationSource(rich)
    equation = next(
        block
        for block in source_blocks(source)
        if block["kind"] == "equation"
    )
    tasks = FakeTasks()
    context = _context(tmp_path, "equation-round-trip")

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "d" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    assert all(
        block["block_id"] != equation["block_id"]
        for window in tasks.translation_blocks
        for block in window
    )
    assert all(
        block["block_id"] != equation["block_id"]
        for window in tasks.review_blocks
        for block in window
    )
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == equation["block_id"]
    )
    assert revision.markdown_body == f"$$\n{tex}\n$$\n"


def test_equation_is_reinjected_when_review_falls_back(tmp_path: Path) -> None:
    tex = r"E = mc^2"
    markdown = tmp_path / "equation-supervision.md"
    markdown.write_text(
        f"# Intro\n\nSource prose.\n\n$$\n{tex}\n$$\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "equation-supervision-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    equation = next(
        block for block in source_blocks(source) if block["kind"] == "equation"
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "d" * 64,
        (),
    )
    context = _context(tmp_path, "equation-supervision")
    tasks = FakeTasks(invalid_review=True)
    workflow = TranslationWorkflowService(tasks)

    result = workflow.translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    assert all(
        block["block_id"] != equation["block_id"]
        for window in tasks.translation_blocks
        for block in window
    )
    assert all(
        block["block_id"] != equation["block_id"]
        for window in tasks.review_blocks
        for block in window
    )
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == equation["block_id"]
    )
    assert revision.markdown_body == f"$$\n{tex}\n$$\n"
    assert any(
        item.provenance.get("translation_fallback", {}).get("kind")
        == "review_skipped"
        for item in revisions
        if item.anchor.target_id != equation["block_id"]
    )


def test_glossary_schema_only_requests_reasoned_content_and_join_id():
    entry = GLOSSARY_SCHEMA["properties"]["entries"]["items"]
    assert entry["additionalProperties"] is False
    assert entry["required"] == [
        "term_id",
        "preferred_translation",
        "target_definition",
    ]
    assert set(entry["properties"]) == set(entry["required"])


def test_glossary_prompt_contracts_markdown_definitions_and_plain_terms() -> None:
    prompt = glossary_prompt(
        terms=[{"term_id": "term-1", "term": "Hubble parameter"}],
        target_language="zh-CN",
        window_ordinal=0,
    )

    assert GLOSSARY_PROMPT_VERSION == "alc.translate.glossary_prompt.v4"
    assert "preferred_translation as plain text" in prompt
    assert "target_definition as concise CommonMark-compatible Markdown" in prompt
    assert "$...$ for inline formulas" in prompt
    assert "Do not use raw HTML, headings, tables, images" in prompt


def test_translation_schema_only_requests_block_id_and_text():
    entry = TRANSLATION_SCHEMA["properties"]["translations"]["items"]
    assert entry["additionalProperties"] is False
    assert entry["required"] == ["block_id", "text"]
    assert set(entry["properties"]) == {"block_id", "text"}


def test_translation_prompts_require_complete_block_text() -> None:
    block = {"block_id": "block-1", "kind": "paragraph", "text": "Part"}
    draft = {"block_id": "block-1", "text": "部分"}
    generated = translation_prompt(
        blocks=[block],
        glossary=[],
        target_language="zh-CN",
        language_result={"language_tag": "en"},
        window_ordinal=0,
    )
    reviewed = review_prompt(
        blocks=[block],
        translations=[draft],
        glossary=[],
        target_language="zh-CN",
        window_ordinal=0,
    )
    assert "beginning to end" in generated
    assert "never omit, summarize, or start partway through" in generated
    assert "beginning to end" in reviewed
    assert "Patch any omission, summary, or truncation" in reviewed


def test_derived_run_id_binds_handler_contract() -> None:
    semantic_input = {"request": {"source": "same"}}
    assert _run_id("blocks", "handler.v1", semantic_input) != _run_id(
        "blocks", "handler.v2", semantic_input
    )


def test_language_same_primary_skips_but_mixed_stays_enabled(tmp_path):
    source = _source(tmp_path)
    context = _context(tmp_path, "known-language")
    known = TranslationWorkflowService(FakeTasks(language="zh")).detect_language(
        context, source, target_language="zh-CN"
    )
    assert isinstance(known, LanguageResult)
    assert known.mode == "skipped"

    mixed_context = _context(tmp_path, "mixed-language")
    mixed = TranslationWorkflowService(
        FakeTasks(language="zh", classification="mixed")
    ).detect_language(mixed_context, source, target_language="zh-CN")
    assert isinstance(mixed, LanguageResult)
    assert mixed.mode == "enabled"


def test_outer_handler_round_trips_companion_rich_only_source(tmp_path):
    source = _source(tmp_path)
    assert source.rich is not None
    rich_only = TranslationSource(rich=source.rich)
    service = TranslationService(tmp_path / "rich-only-jobs")
    snapshot = service.prepare_language(LanguageRequest(rich_only, "fr"))
    snapshot = service.execute(snapshot.run_id, task_service=FakeTasks())
    assert snapshot.status is RunStatus.SUCCEEDED
    result = service.result(snapshot.run_id)
    assert isinstance(result, LanguageResult)
    assert result.document_digest == source.rich.document_digest


def test_standalone_steps_use_verified_cross_run_results(tmp_path):
    source = _source(tmp_path)
    service = TranslationService(tmp_path / "jobs")
    tasks = FakeTasks()
    language_snapshot = service.prepare_language(
        LanguageRequest(source, "fr")
    )
    language_snapshot = service.execute(
        language_snapshot.run_id, task_service=tasks
    )
    assert language_snapshot.status is RunStatus.SUCCEEDED

    keywords = FakeKeywords([_term("term-1", "Entropy")])
    glossary_snapshot = service.prepare_glossary(
        GlossaryRequest(
            source,
            "fr",
            50,
            service.result_source(language_snapshot.run_id),
        )
    )
    glossary_snapshot = service.execute(
        glossary_snapshot.run_id,
        task_service=tasks,
        keyword_provider=keywords,
    )
    assert glossary_snapshot.status is RunStatus.SUCCEEDED
    glossary = service.result(glossary_snapshot.run_id)
    assert isinstance(glossary, GlossaryResult)
    assert [item["term_id"] for item in glossary.entries] == ["term-1"]
    assert keywords.calls == 1

    blocks_snapshot = service.prepare_blocks(
        BlocksRequest(
            source,
            "fr",
            service.result_source(language_snapshot.run_id),
            service.result_source(glossary_snapshot.run_id),
        )
    )
    blocks_snapshot = service.execute(
        blocks_snapshot.run_id, task_service=tasks
    )
    assert blocks_snapshot.status is RunStatus.SUCCEEDED
    blocks = service.result(blocks_snapshot.run_id)
    assert isinstance(blocks, TranslationResult)
    assert blocks.coverage == "document"
    assert len(blocks.revision_artifacts) == len(source_blocks(source))
    revisions = [
        decode_fragment_revision(
            payload.decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item, payload in zip(
            blocks.revision_artifacts,
            service.revision_payloads(blocks_snapshot.run_id, blocks),
            strict=True,
        )
    ]
    assert [item.anchor.target_id for item in revisions] == [
        item["block_id"] for item in source_blocks(source)
    ]
    assert all(
        item.priority == 10
        and item.role == "translation"
        and item.anchor.related_block_ids == (item.anchor.target_id,)
        for item in revisions
    )
    manifest = blocks.to_document()
    assert manifest["schema_version"] == "alc.translate.translation_result.v1"
    assert set(manifest) == {
        "schema_version",
        "source_language",
        "target_language",
        "mode",
        "coverage",
        "layer",
        "revision_artifacts",
    }
    assert TranslationResult.from_document(manifest) == blocks


def test_missing_or_unverified_prerequisite_never_runs_keyword_step(tmp_path):
    source = _source(tmp_path)
    service = TranslationService(tmp_path / "jobs")
    keywords = FakeKeywords([_term("term-1", "Entropy")])
    missing = ArtifactSourceRef(
        "missing-run",
        "language/result",
        ArtifactDigest("sha256", "0" * 64, 1),
    )
    snapshot = service.prepare_glossary(
        GlossaryRequest(source, "fr", 50, missing)
    )
    snapshot = service.execute(
        snapshot.run_id,
        task_service=FakeTasks(),
        keyword_provider=keywords,
    )
    assert snapshot.status is RunStatus.FAILED
    assert snapshot.error is not None
    assert snapshot.error.code == "prerequisite_not_verified"
    assert keywords.calls == 0


def test_glossary_windows_preserve_every_term_identity_and_order(tmp_path):
    source = _source(tmp_path)
    terms = [
        _term(f"term-{index}", f"Term {index}", sentence="x" * 1100)
        for index in range(3)
    ]
    tasks = FakeTasks()
    result = TranslationWorkflowService(
        tasks, FakeKeywords(terms)
    ).build_glossary(
        _context(tmp_path, "glossary-windows"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1.0,
            "fr",
            "enabled",
        ),
        target_language="fr",
        approx_count=3,
        term_input_budget_bytes=4096,
    )
    assert isinstance(result, GlossaryResult)
    assert [item["term_id"] for item in result.entries] == [
        "term-0",
        "term-1",
        "term-2",
    ]
    assert tasks.calls.count(GLOSSARY_PROMPT_VERSION) >= 2


def test_invalid_glossary_retries_once_then_pauses_with_editable_candidate(
    tmp_path,
):
    source = _source(tmp_path)
    term = _term("term-1", "Entropy")
    context = _context(tmp_path, "editable-glossary")
    tasks = InvalidGlossaryTasks()
    workflow = TranslationWorkflowService(tasks, FakeKeywords([term]))
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1.0,
        "fr",
        "enabled",
    )

    paused = workflow.build_glossary(
        context,
        source,
        language=language,
        target_language="fr",
        approx_count=1,
    )

    assert isinstance(paused, Paused)
    assert paused.awaiting.details["automatic_retry_exhausted"] is True
    assert paused.awaiting.details["output_attempts"] == 2
    candidate_path = Path(str(paused.awaiting.details["candidate_path"]))
    assert candidate_path.is_file()
    assert tasks.calls == 2
    candidate_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "term_id": "term-1",
                        "preferred_translation": "entropie",
                        "target_definition": "Une grandeur thermodynamique.",
                    }
                ]
            }
        )
    )

    recovered = workflow.build_glossary(
        context,
        source,
        language=language,
        target_language="fr",
        approx_count=1,
    )

    assert isinstance(recovered, GlossaryResult)
    assert tasks.calls == 2
    assert recovered.entries[0]["term"] == term["term"]
    assert recovered.entries[0]["matched_sentences"] == term["matched_sentences"]


def test_invalid_language_output_gets_one_fresh_retry(tmp_path):
    source = _source(tmp_path)
    tasks = InvalidOnceTasks(LANGUAGE_PROMPT_VERSION)
    context = _context(tmp_path, "language-retry")

    result = TranslationWorkflowService(tasks).detect_language(
        context,
        source,
        target_language="fr",
    )

    assert isinstance(result, LanguageResult)
    assert tasks.calls == [
        LANGUAGE_PROMPT_VERSION,
        LANGUAGE_PROMPT_VERSION,
    ]
    assert context.working.find_candidate(
        "language/language/result.json"
    ) is not None
    assert len(set(tasks.task_ids)) == 2


def test_full_translation_publishes_source_note_revision_and_caption_only_table(
    tmp_path: Path,
) -> None:
    if not callable(getattr(source_module._ac_document, "source_notes", None)):
        pytest.skip("requires AC Foundation source-note producer")
    html = tmp_path / "source.html"
    html.write_text(
        """
        <article>
          <p id="P1">Alpha<span class="ltx_note ltx_role_footnote" id="footnote1">
            <sup class="ltx_note_mark">1</sup><span class="ltx_note_outer">
              <span class="ltx_note_content"><sup class="ltx_note_mark">1</sup>
                Authored note body.
              </span>
            </span>
          </span>.</p>
          <p id="P2">Resource<span class="ltx_note ltx_role_footnote" id="footnote2">
            <sup class="ltx_note_mark">2</sup><span class="ltx_note_outer">
              <span class="ltx_note_content"><sup class="ltx_note_mark">2</sup>
                <a href="https://example.test/original">https://example.test/original</a>
              </span>
            </span>
          </span>.</p>
          <table id="T1"><caption>Table 1: Measurements.</caption>
            <tr><th>System</th><th>Meaning</th></tr>
            <tr><td>A</td><td>Natural-language cell</td></tr>
          </table>
        </article>
        """,
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "document-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(html)
        )
    )
    tasks = FakeTasks(translation_prefix="译：")
    context = _context(tmp_path, "source-note-and-table")

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "d" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    table_prompt = next(
        block
        for window in tasks.translation_blocks
        for block in window
        if block["kind"] == "table"
    )
    assert table_prompt["payload"] == {"caption": "Table 1: Measurements."}
    note_prompt = next(
        block
        for window in tasks.translation_blocks
        for block in window
        if block["kind"] == "source_note"
    )
    assert note_prompt["payload"] == {"text": "Authored note body."}
    prompted_note_ids = {
        block["block_id"]
        for window in tasks.translation_blocks
        for block in window
        if block["kind"] == "source_note"
    }
    assert prompted_note_ids == {"source-note:footnote1"}

    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    note_revision = next(
        revision
        for revision in revisions
        if "source_note_translation" in revision.provenance
    )
    note_contract = note_revision.provenance["source_note_translation"]
    assert note_contract == {
        "schema_version": "alc.render.source_note_translation.v1",
        "note_id": "footnote1",
    }
    owner = next(block for block in source.rich.blocks if block.kind.value == "paragraph")
    assert note_revision.anchor.target_id == owner.block_id
    link_note_revision = next(
        revision
        for revision in revisions
        if revision.provenance.get("source_note_translation", {}).get("note_id")
        == "footnote2"
    )
    assert link_note_revision.markdown_body == "<https://example.test/original>\n"
    table_revision = next(
        revision
        for revision in revisions
        if revision.anchor.target_id
        == next(
            block.block_id
            for block in source.rich.blocks
            if block.kind.value == "table"
        )
    )
    assert table_revision.markdown_body == "译：Table 1: Measurements.\n"
    assert "Natural-language cell" not in table_revision.markdown_body


def test_language_second_invalid_output_pauses_and_resumes_without_third_call(
    tmp_path,
):
    source = _source(tmp_path)
    service = TranslationService(tmp_path / "language-recovery-jobs")
    tasks = FakeTasks(language=" ")
    snapshot = service.prepare_language(
        LanguageRequest(source, "fr"),
        run_id="language-output-recovery",
    )

    paused = service.execute(snapshot.run_id, task_service=tasks)

    assert paused.status is RunStatus.PAUSED
    assert paused.awaiting is not None
    assert paused.awaiting.input_required is False
    assert paused.awaiting.details["output_attempts"] == 2
    candidate_path = Path(
        str(paused.awaiting.details["candidate_path"])
    )
    candidate_path.write_text(
        json.dumps(
            {
                "language_tag": "en",
                "classification": "known",
                "confidence": 0.9,
            }
        ),
        encoding="utf-8",
    )

    resumed = service.resume(snapshot.run_id, task_service=tasks)

    assert resumed.status is RunStatus.SUCCEEDED
    assert tasks.calls.count(LANGUAGE_PROMPT_VERSION) == 2
    assert service.result(snapshot.run_id).language_tag == "en"


def test_invalid_translation_draft_gets_one_fresh_retry(tmp_path):
    source = _source(tmp_path)
    tasks = InvalidOnceTasks(TRANSLATION_PROMPT_VERSION)

    result = TranslationWorkflowService(tasks).translate_blocks(
        _context(tmp_path, "draft-retry"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "d" * 64,
            (),
        ),
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    assert result.coverage == "document"
    assert tasks.calls.count(TRANSLATION_PROMPT_VERSION) == 2


def test_provider_failure_is_not_published_as_source_fallback(tmp_path):
    source = _source(tmp_path)
    context = _context(tmp_path, "provider-failure")

    result = TranslationWorkflowService(ProviderFailingTasks()).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "d" * 64,
            (),
        ),
        target_language="fr",
    )

    assert isinstance(result, RunError)
    assert result.code == "provider_authentication"
    assert context.artifacts.find("translation/result") is None
    assert all(
        event.event != "translation_fallback"
        for event in context.events.read_all()
    )


def test_review_provider_failure_is_not_published_as_review_skipped(tmp_path):
    source = _source(tmp_path)
    context = _context(tmp_path, "review-provider-failure")

    result = TranslationWorkflowService(
        ReviewProviderFailingTasks()
    ).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "d" * 64,
            (),
        ),
        target_language="fr",
    )

    assert isinstance(result, RunError)
    assert result.code == "provider_authentication"
    assert context.artifacts.find("translation/result") is None
    assert all(
        event.event != "translation_fallback"
        for event in context.events.read_all()
    )


def test_output_supervision_request_tracks_current_error(tmp_path):
    context = _context(tmp_path, "output-supervision-identity")
    candidate = tmp_path / "candidate.json"
    first = _output_supervision(
        context,
        artifact_prefix="translation",
        stage="draft-0001",
        error=TranslationWorkflowError("invalid", "first error"),
        candidate_path=candidate,
    )
    second = _output_supervision(
        context,
        artifact_prefix="translation",
        stage="draft-0001",
        error=TranslationWorkflowError("invalid", "second error"),
        candidate_path=candidate,
    )

    assert first.awaiting.response_contract is None
    assert first.awaiting.resume_key != second.awaiting.resume_key
    assert first.awaiting.request_ref != second.awaiting.request_ref
    assert second.awaiting.request_ref is not None
    request = json.loads(
        context.artifacts.read_bytes(second.awaiting.request_ref)
    )
    assert request["schema_version"] == OUTPUT_SUPERVISION_SCHEMA
    assert request["message"] == "second error"


def test_changed_translation_gets_a_distinct_fragment_identity(tmp_path) -> None:
    source = _source(tmp_path)
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "d" * 64,
        (),
    )
    first = TranslationWorkflowService(
        FakeTasks(translation_prefix="first:")
    ).translate_blocks(
        _context(tmp_path, "first-generation"),
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )
    second = TranslationWorkflowService(
        FakeTasks(translation_prefix="second:")
    ).translate_blocks(
        _context(tmp_path, "second-generation"),
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )

    assert isinstance(first, TranslationResult)
    assert isinstance(second, TranslationResult)
    assert first.layer.initial_revisions[0].fragment_id != (
        second.layer.initial_revisions[0].fragment_id
    )


def test_block_selector_normalizes_order_and_filters_window_glossary(tmp_path):
    source = _source(tmp_path)
    blocks = source_blocks(source)
    entropy_block = next(
        item for item in blocks if "Entropy" in block_text(item)
    )
    tensor_block = next(
        item for item in blocks if "tensor" in block_text(item)
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        2,
        "a" * 64,
        (
            {
                **_term("entropy", "Entropy"),
                "preferred_translation": "entropie",
                "target_definition": "definition entropy",
            },
            {
                **_term("tensor", "tensor"),
                "preferred_translation": "tenseur",
                "target_definition": "definition tensor",
            },
        ),
    )
    tasks = FakeTasks()
    result = TranslationWorkflowService(tasks).translate_blocks(
        _context(tmp_path, "selected-block"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=glossary,
        target_language="fr",
        block_ids=[entropy_block["block_id"]],
    )
    assert isinstance(result, TranslationResult)
    assert result.coverage == "selection"
    assert len(result.revision_artifacts) == 1
    assert tasks.translation_glossaries == [["Entropy"]]
    assert tasks.prompt_glossary_fields == [
        [
            {
                "term_id",
                "term",
                "aliases",
                "preferred_translation",
                "target_definition",
            }
        ],
        [
            {
                "term_id",
                "term",
                "aliases",
                "preferred_translation",
                "target_definition",
            }
        ],
    ]

    invalid = TranslationWorkflowService(FakeTasks()).translate_blocks(
        _context(tmp_path, "invalid-selector"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=glossary,
        target_language="fr",
        block_ids=[tensor_block["block_id"], tensor_block["block_id"]],
    )
    assert isinstance(invalid, RunError)
    assert invalid.code == "block_selector_invalid"


def test_window_glossary_does_not_match_inside_longer_word(tmp_path):
    source = _source(tmp_path)
    blocks = source_blocks(source)
    tensor_block = next(
        item for item in blocks if "tensor" in block_text(item)
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "a" * 64,
        (
            {
                **_term("ten", "ten"),
                "preferred_translation": "dix",
                "target_definition": "number",
            },
        ),
    )
    tasks = FakeTasks()
    result = TranslationWorkflowService(tasks).translate_blocks(
        _context(tmp_path, "bounded-window-glossary"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=glossary,
        target_language="fr",
        block_ids=[tensor_block["block_id"]],
    )
    assert isinstance(result, TranslationResult)
    assert tasks.translation_glossaries == [[]]

def test_structural_figures_bypass_models_and_keep_ordered_coverage(tmp_path):
    assets = tmp_path / "images"
    assets.mkdir()
    (assets / "structural.png").write_bytes(b"\x89PNG structural")
    (assets / "captioned.png").write_bytes(b"\x89PNG captioned")
    (assets / "alt.png").write_bytes(b"\x89PNG alt")
    markdown = tmp_path / "figures.md"
    markdown.write_text(
        "# Figures\n\n"
        "![](images/structural.png)\n\n"
        "<details>\n<summary>natural_image</summary>\n\n"
        "Extractor-only sidecar text.\n</details>\n\n"
        "![private alt](images/captioned.png \"Visible scientific caption\")\n\n"
        "![Accessibility language](images/alt.png)\n\n"
        "The surrounding prose remains translatable.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "figure-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    blocks = source_blocks(source)
    structural = next(
        item
        for item in blocks
        if item["kind"] == "figure"
        and not str(item["payload"]["caption"]).strip()
    )
    captioned = next(
        item
        for item in blocks
        if item["kind"] == "figure"
        and str(item["payload"]["caption"]).strip()
    )
    alt_only = next(
        item
        for item in blocks
        if item["kind"] == "figure"
        and str(item["payload"]["alt_text"]).strip()
        == "Accessibility language"
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "e" * 64,
        (),
    )
    tasks = FakeTasks()

    context = _context(tmp_path, "figures")
    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    revision_block_ids = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        ).anchor.target_id
        for item in result.revision_artifacts
    ]
    assert structural["block_id"] not in revision_block_ids
    assert captioned["block_id"] in revision_block_ids
    assert alt_only["block_id"] in revision_block_ids
    prompted = [
        item for window in tasks.translation_blocks for item in window
    ]
    reviewed = [item for window in tasks.review_blocks for item in window]
    assert structural["block_id"] not in {
        item["block_id"] for item in [*prompted, *reviewed]
    }
    prompted_caption = next(
        item for item in prompted if item["block_id"] == captioned["block_id"]
    )
    assert prompted_caption["payload"] == {
        "caption": "Visible scientific caption",
        "alt_text": "private alt",
    }
    prompted_alt = next(
        item for item in prompted if item["block_id"] == alt_only["block_id"]
    )
    assert prompted_alt["payload"] == {
        "caption": "",
        "alt_text": "Accessibility language",
    }
    assert set(prompted_caption) == {
        "block_id",
        "ordinal",
        "kind",
        "section_path",
        "payload",
        "source_identity",
    }
    figure_prompts = json.dumps(
        [
            item
            for item in [*prompted, *reviewed]
            if item["kind"] == "figure"
        ],
        ensure_ascii=False,
    )
    for private_value in (
            "images/structural.png",
            "images/captioned.png",
            "Extractor-only sidecar text",
            "asset_digest",
            "asset_target",
            "logical_name",
        '"target"',
    ):
        assert private_value not in figure_prompts

    structural_only_tasks = FakeTasks()
    structural_only = TranslationWorkflowService(
        structural_only_tasks
    ).translate_blocks(
        _context(tmp_path, "structural-only"),
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
        block_ids=[structural["block_id"]],
    )
    assert isinstance(structural_only, TranslationResult)
    assert structural_only.coverage == "selection"
    assert structural_only.revision_artifacts == ()
    assert structural_only_tasks.calls == []


def test_failed_review_automatically_keeps_validated_translation(tmp_path):
    source = _source(tmp_path)
    first_context = _context(tmp_path, "review-supervision")
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "b" * 64,
        (),
    )
    tasks = FakeTasks(invalid_review=True)
    workflow = TranslationWorkflowService(tasks)
    result = workflow.translate_blocks(
        first_context,
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )
    assert isinstance(result, TranslationResult)
    assert tasks.calls.count(REVIEW_PROMPT_VERSION) == 2
    assert len(result.revision_artifacts) == len(source_blocks(source))
    revisions = [
        decode_fragment_revision(
            first_context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    assert all(
        item.provenance["translation_fallback"]["kind"]
        == "review_skipped"
        for item in revisions
    )


def test_oversized_single_block_review_uses_bounded_internal_units(tmp_path):
    markdown = tmp_path / "long.md"
    markdown.write_text("# Long\n\n" + ("source prose " * 180), encoding="utf-8")
    paper = AcDocumentService(cache_root=tmp_path / "long-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    context = _context(tmp_path, "review-budget")
    tasks = FakeTasks()
    workflow = TranslationWorkflowService(tasks)
    result = workflow.translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "c" * 64,
            (),
        ),
        target_language="fr",
        input_budget_bytes=4500,
    )
    assert isinstance(result, TranslationResult)
    assert tasks.calls.count(REVIEW_PROMPT_VERSION) > 0
    assert max(size for _contract, size in tasks.prompt_sizes) <= 4_500


def test_overescaped_formula_is_restored_without_supervision(tmp_path):
    markdown = tmp_path / "formula.md"
    markdown.write_text(
        "# Formula\n\nUse $\\Psi^\\dagger$ in this expression.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "formula-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    paragraph = next(
        block for block in source_blocks(source) if block["kind"] == "paragraph"
    )
    context = _context(tmp_path, "formula-restore")

    result = TranslationWorkflowService(
        OverescapedFormulaTasks()
    ).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "c" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == paragraph["block_id"]
    )
    assert r"$\Psi^\dagger$" in revision.markdown_body
    assert r"$\\Psi^\dagger$" not in revision.markdown_body


def test_small_list_is_translated_as_item_units(tmp_path):
    markdown = tmp_path / "small-list.md"
    markdown.write_text(
        "# Data\n\n- (16)\n"
        "- Type Ia observations span $0.001<z<2.26$.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "small-list-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    list_block = next(
        block for block in source_blocks(source) if block["kind"] == "list"
    )
    context = _context(tmp_path, "small-list-items")
    tasks = ListItemDroppingTasks()

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "f" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    assert all(
        block["kind"] != "list"
        for window in tasks.translation_blocks
        for block in window
    )
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == list_block["block_id"]
    )
    assert len(revision.markdown_body.splitlines()) == 2
    assert "$0.001<z<2.26$" in revision.markdown_body


def test_list_item_translation_newlines_preserve_source_item_boundaries(
    tmp_path,
):
    markdown = tmp_path / "list-newlines.md"
    markdown.write_text("# Data\n\n- one\n- two\n", encoding="utf-8")
    paper = AcDocumentService(cache_root=tmp_path / "list-newlines-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    list_block = next(
        block for block in source_blocks(source) if block["kind"] == "list"
    )
    context = _context(tmp_path, "list-newlines")

    result = TranslationWorkflowService(ListItemNewlineTasks()).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "e" * 64,
            (),
        ),
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == list_block["block_id"]
    )
    assert revision.markdown_body.splitlines() == ["- un extra", "- deux"]


def test_invalid_formula_falls_back_to_source_and_continues(tmp_path):
    markdown = tmp_path / "formula-fallback.md"
    markdown.write_text(
        "# Formula\n\nThe range is $0.001<z<2.26$.\n\nAfterward.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "formula-fallback-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    formula_block = next(
        block
        for block in source_blocks(source)
        if "$0.001<z<2.26$" in block_text(block)
    )
    context = _context(tmp_path, "formula-fallback")

    result = TranslationWorkflowService(
        FormulaOmittingTasks()
    ).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "a" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == formula_block["block_id"]
    )
    assert "$0.001<z<2.26$" in revision.markdown_body
    assert revision.provenance["translation_fallback"] == {
        "schema_version": "alc.translate.fallback.v1",
        "kind": "source_text",
        "source_preserved": True,
    }
    assert all(
        "translation_fallback" not in item.provenance
        for item in revisions
        if item.anchor.target_id != formula_block["block_id"]
    )


def test_invalid_link_falls_back_to_source_and_continues(tmp_path):
    markdown = tmp_path / "link-fallback.md"
    markdown.write_text(
        "# Links\n\n"
        "The project is at "
        "[https://example.test/source](https://example.test/source).\n\n"
        "Afterward.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "link-fallback-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    link_block = next(
        block
        for block in source_blocks(source)
        if block["payload"].get("inline_spans")
        and any(
            span.get("kind") == "link"
            for span in block["payload"]["inline_spans"]
        )
    )
    context = _context(tmp_path, "link-fallback")

    result = TranslationWorkflowService(LinkOmittingTasks()).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "b" * 64,
            (),
        ),
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == link_block["block_id"]
    )
    assert revision.markdown_body.strip() == (
        "The project is at "
        "[https://example.test/source](https://example.test/source)."
    )
    assert revision.provenance["translation_fallback"] == {
        "schema_version": "alc.translate.fallback.v1",
        "kind": "source_text",
        "source_preserved": True,
    }
    assert any(
        item.anchor.target_id != link_block["block_id"]
        and "translation_fallback" not in item.provenance
        for item in revisions
    )


def test_parenthesized_repeated_link_source_fallback_is_valid():
    doi_target = (
        "https://dx.doi.org/https://doi.org/10.1016/"
        "0370-2693(80)90670-X"
    )
    article_target = (
        "https://www.sciencedirect.com/science/article/pii/"
        "037026938090670X"
    )
    block = {
        "block_id": "block-parenthesized-links",
        "kind": "list",
        "payload": {
            "ordered": False,
            "items": [
                {
                    "text": (
                        "[2] A. A. Starobinsky, Physics Letters B 91 no. 1, "
                        "(1980) 99–102. "
                        f"{article_target}."
                    ),
                    "inline_spans": [
                        {"kind": "text", "text": "[2] A. A. Starobinsky, "},
                        {
                            "kind": "link",
                            "text": "Physics Letters B",
                            "target": doi_target,
                        },
                        {"kind": "link", "text": " ", "target": doi_target},
                        {"kind": "link", "text": "91", "target": doi_target},
                        {
                            "kind": "link",
                            "text": " no. 1, (1980) 99–102",
                            "target": doi_target,
                        },
                        {"kind": "text", "text": ". "},
                        {
                            "kind": "link",
                            "text": article_target,
                            "target": article_target,
                        },
                        {"kind": "text", "text": "."},
                    ],
                }
            ],
        },
    }

    fallback, fallback_ids = _salvaged_translation_fallback(
        (block,),
        candidate={
            "translations": [
                {"block_id": block["block_id"], "text": "invalid translation"}
            ]
        },
    )

    assert fallback_ids == [block["block_id"]]
    assert fallback == [
        {
            "block_id": block["block_id"],
            "text": (
                "[2] A. A. Starobinsky, "
                f"[Physics Letters B]({doi_target})"
                f"[ ]({doi_target})"
                f"[91]({doi_target})"
                f"[ no. 1, (1980) 99–102]({doi_target}). "
                f"[{article_target}]({article_target})."
            ),
        }
    ]


@pytest.mark.parametrize(
    "target",
    ["https://example.test/é", "foo&amp;bar"],
    ids=["unicode", "entity"],
)
def test_lexical_link_source_fallback_is_valid(target):
    block = {
        "block_id": "block-lexical-link",
        "kind": "paragraph",
        "payload": {
            "text": "source",
            "inline_spans": [
                {"kind": "link", "text": "source", "target": target}
            ],
        },
    }

    fallback, fallback_ids = _salvaged_translation_fallback(
        (block,),
        candidate={
            "translations": [
                {"block_id": block["block_id"], "text": "invalid translation"}
            ]
        },
    )

    assert fallback_ids == [block["block_id"]]
    assert fallback == [
        {"block_id": block["block_id"], "text": f"[source]({target})"}
    ]


@pytest.mark.parametrize("artifact_kind", ["draft", "accepted"])
def test_invalid_replayed_translation_artifact_falls_back_and_continues(
    tmp_path, artifact_kind
):
    markdown = tmp_path / f"replayed-{artifact_kind}.md"
    markdown.write_text(
        "# Links\n\n"
        "Read the [project](https://example.test/source).\n\n"
        "Afterward.\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(
        cache_root=tmp_path / f"replayed-{artifact_kind}-cache"
    )
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "zh-CN",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "zh-CN",
        1,
        "c" * 64,
        (),
    )
    blocks = source_blocks(source)
    link_block = next(
        block
        for block in blocks
        if any(
            span.get("kind") == "link"
            for span in block["payload"].get("inline_spans", ())
        )
    )
    units = _translation_units(source, blocks)
    model_blocks = _model_translation_blocks(units)
    model_units, _plans = _bounded_model_translation_units(
        model_blocks,
        glossary=glossary.entries,
        target_language="zh-CN",
        language=language,
        budget_bytes=32_000,
    )
    windows = _translation_windows(
        model_units,
        glossary=glossary.entries,
        target_language="zh-CN",
        language=language,
        budget_bytes=32_000,
    )
    assert len(windows) == 1
    replayed = {
        "translations": [
            {
                "block_id": str(block["block_id"]),
                "text": (
                    "translated text without its link"
                    if str(block["block_id"]) == link_block["block_id"]
                    else block_text(block)
                ),
            }
            for block in windows[0]
        ]
    }
    context = _context(tmp_path, f"replayed-{artifact_kind}")
    context.artifacts.publish_json(
        f"translation/windows/0000/{artifact_kind}", replayed
    )
    tasks = FakeTasks()

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="zh-CN",
    )

    assert isinstance(result, TranslationResult)
    assert TRANSLATION_PROMPT_VERSION not in tasks.calls
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == link_block["block_id"]
    )
    assert revision.markdown_body.strip() == (
        "Read the [project](https://example.test/source)."
    )
    assert revision.provenance["translation_fallback"] == {
        "schema_version": "alc.translate.fallback.v1",
        "kind": "source_text",
        "source_preserved": True,
    }


def test_historical_accepted_list_translation_replays_into_item_units(
    tmp_path,
):
    markdown = tmp_path / "historical-list.md"
    markdown.write_text("# Data\n\n- one\n- two\n", encoding="utf-8")
    paper = AcDocumentService(cache_root=tmp_path / "historical-list-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "f" * 64,
        (),
    )
    blocks = source_blocks(source)
    list_block = next(block for block in blocks if block["kind"] == "list")
    model_blocks = _model_translation_blocks(_translation_units(source, blocks))
    legacy_windows = _translation_windows(
        model_blocks,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    assert len(legacy_windows) == 1
    model_units, _plans = _bounded_model_translation_units(
        model_blocks,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    windows = _translation_windows(
        model_units,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    assert len(windows) == 1
    heading = next(block for block in model_blocks if block["kind"] == "heading")
    context = _context(tmp_path, "historical-list")
    context.artifacts.publish_json(
        "translation/windows/0000/accepted",
        {
            "translations": [
                {"block_id": heading["block_id"], "text": "Données"},
                {
                    "block_id": list_block["block_id"],
                    "text": "ancien un\nancien deux",
                },
            ]
        },
    )
    tasks = FakeTasks()

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    assert TRANSLATION_PROMPT_VERSION not in tasks.calls
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == list_block["block_id"]
    )
    assert revision.markdown_body.splitlines() == [
        "- ancien un",
        "- ancien deux",
    ]
    assert "translation_fallback" not in revision.provenance


def test_historical_accepted_list_translation_replays_across_new_windows(
    tmp_path,
):
    markdown = tmp_path / "historical-long-list.md"
    items = [
        f"item {index:02d} " + "detail " * 12
        for index in range(70)
    ]
    markdown.write_text(
        "# Data\n\n" + "\n".join(f"- {item}" for item in items) + "\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "historical-long-list-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "fr",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "fr",
        1,
        "f" * 64,
        (),
    )
    blocks = source_blocks(source)
    list_block = next(block for block in blocks if block["kind"] == "list")
    model_blocks = _model_translation_blocks(_translation_units(source, blocks))
    legacy_windows = _translation_windows(
        model_blocks,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    assert len(legacy_windows) == 1
    model_units, _plans = _bounded_model_translation_units(
        model_blocks,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    windows = _translation_windows(
        model_units,
        glossary=glossary.entries,
        target_language="fr",
        language=language,
        budget_bytes=32_000,
    )
    assert len(windows) > 1
    heading = next(block for block in model_blocks if block["kind"] == "heading")
    translated_items = [f"ancien {index:02d}" for index in range(70)]
    context = _context(tmp_path, "historical-long-list")
    context.artifacts.publish_json(
        "translation/windows/0000/accepted",
        {
            "translations": [
                {"block_id": heading["block_id"], "text": "Données"},
                {
                    "block_id": list_block["block_id"],
                    "text": "\n".join(translated_items),
                },
            ]
        },
    )
    tasks = FakeTasks()

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="fr",
    )

    assert isinstance(result, TranslationResult)
    assert TRANSLATION_PROMPT_VERSION not in tasks.calls
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == list_block["block_id"]
    )
    assert revision.markdown_body.splitlines() == [
        f"- {item}" for item in translated_items
    ]
    assert "translation_fallback" not in revision.provenance


def test_invalid_replayed_review_artifact_keeps_draft_and_continues(tmp_path):
    markdown = tmp_path / "replayed-review.md"
    markdown.write_text(
        "# Long\n\n" + "\n\n".join(["source prose " * 8] * 6),
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "replayed-review-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "zh-CN",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "zh-CN",
        1,
        "d" * 64,
        (),
    )
    blocks = source_blocks(source)
    model_blocks = _model_translation_blocks(
        _translation_units(source, blocks)
    )
    model_units, _plans = _bounded_model_translation_units(
        model_blocks,
        glossary=glossary.entries,
        target_language="zh-CN",
        language=language,
        budget_bytes=4_800,
    )
    windows = _translation_windows(
        model_units,
        glossary=glossary.entries,
        target_language="zh-CN",
        language=language,
        budget_bytes=4_800,
    )
    assert len(windows) == 1
    draft_doc = {
        "translations": [
            {
                "block_id": str(block["block_id"]),
                "text": f"{'译' * 600}{block_text(block)}",
            }
            for block in windows[0]
        ]
    }
    draft = _validate_draft_window(draft_doc, windows[0])
    review_windows = _translation_review_windows(
        windows[0],
        draft,
        glossary=glossary.entries,
        target_language="zh-CN",
        window_ordinal=0,
        budget_bytes=4_800,
    )
    assert len(review_windows) > 1
    first_review_blocks, first_review_draft = review_windows[0]
    review_digest = _digest(first_review_draft)[:24]
    context = _context(tmp_path, "replayed-review")
    context.artifacts.publish_json("translation/windows/0000/draft", draft_doc)
    context.artifacts.publish_json(
        "translation/windows/0000/reviews/0000/"
        f"{review_digest}/accepted",
        {"translations": [{"block_id": "wrong-block", "text": "unsafe"}]},
    )
    tasks = FakeTasks(translation_prefix="译" * 600)

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    assert TRANSLATION_PROMPT_VERSION not in tasks.calls
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    skipped_ids = {str(item["block_id"]) for item in first_review_blocks}
    assert all(
        revision.provenance["translation_fallback"]["kind"]
        == "review_skipped"
        for revision in revisions
        if revision.anchor.target_id in skipped_ids
    )
    assert any(
        revision.anchor.target_id not in skipped_ids
        and "translation_fallback" not in revision.provenance
        for revision in revisions
    )


@pytest.mark.parametrize(
    ("block", "expected_text"),
    [
        (
            {
                "block_id": "markdown-link",
                "kind": "paragraph",
                "ordinal": 1,
                "section_path": [],
                "payload": {
                    "text": "See Table 1.",
                    "inline_spans": [
                        {"kind": "text", "text": "See ", "start": 0, "end": 4},
                        {
                            "kind": "link",
                            "text": "Table 1",
                            "target": "#S3.T1",
                            "start": 4,
                            "end": 11,
                        },
                        {"kind": "text", "text": ".", "start": 11, "end": 12},
                    ],
                },
            },
            "See [Table 1](#S3.T1).",
        ),
        (
            {
                "block_id": "html-math",
                "kind": "paragraph",
                "ordinal": 1,
                "section_path": [],
                "payload": {
                    "text": "The kernel Ka​b evolves.",
                    "inline_spans": [
                        {
                            "kind": "text",
                            "text": "The kernel ",
                            "start": 0,
                            "end": 11,
                        },
                        {
                            "kind": "math",
                            "text": "Ka​b",
                            "source": "Ka​b",
                            "tex": "K_{ab}",
                            "start": 11,
                            "end": 15,
                        },
                        {
                            "kind": "text",
                            "text": " evolves.",
                            "start": 15,
                            "end": 24,
                        },
                    ],
                },
            },
            "The kernel $K_{ab}$ evolves.",
        ),
    ],
)
def test_structured_inline_identity_survives_source_fallback_and_collapse(
    block, expected_text
):
    candidate = {
        "translations": [
            {"block_id": block["block_id"], "text": "invalid translation"}
        ]
    }

    fallback, fallback_ids = _salvaged_translation_fallback(
        (block,), candidate=candidate
    )

    assert fallback == [{"block_id": block["block_id"], "text": expected_text}]
    assert fallback_ids == [block["block_id"]]

    units, plans = _bounded_model_translation_units(
        (block,),
        glossary=(),
        target_language="zh-CN",
        language=LanguageResult(
            "d" * 64,
            "s" * 64,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        budget_bytes=32_000,
    )
    assert [item["block_id"] for item in units] == [block["block_id"]]

    collapsed, collapsed_fallback_ids = (
        _collapse_model_translation_units_with_fallback(
            (block,),
            plans,
            ({"block_id": block["block_id"], "text": "invalid translation"},),
        )
    )

    assert collapsed == ({"block_id": block["block_id"], "text": expected_text},)
    assert collapsed_fallback_ids == (block["block_id"],)


def test_oversized_list_is_translated_as_bounded_internal_units(tmp_path):
    markdown = tmp_path / "large-list.md"
    markdown.write_text(
        "# References\n\n"
        + "\n".join(
            f"- Reference {index}: " + ("source detail " * 18)
            for index in range(1, 61)
        )
        + "\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "large-list-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    list_block = next(
        block for block in source_blocks(source) if block["kind"] == "list"
    )
    tasks = FakeTasks()
    context = _context(tmp_path, "large-list")

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "d" * 64,
            (),
        ),
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    assert max(size for _contract, size in tasks.prompt_sizes) <= 4_800
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    revision = next(
        item
        for item in revisions
        if item.anchor.target_id == list_block["block_id"]
    )
    assert len(revision.markdown_body.splitlines()) == 60


def test_oversized_paragraph_is_translated_as_bounded_internal_units(tmp_path):
    markdown = tmp_path / "large-paragraph.md"
    markdown.write_text(
        "# Long\n\n"
        + " ".join(
            f"Sentence {index} contains source detail."
            for index in range(1, 241)
        )
        + "\n",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "large-paragraph-cache")
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(
            paper.import_source(markdown)
        )
    )
    paragraph = next(
        block for block in source_blocks(source) if block["kind"] == "paragraph"
    )
    tasks = FakeTasks()
    context = _context(tmp_path, "large-paragraph")

    result = TranslationWorkflowService(tasks).translate_blocks(
        context,
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "e" * 64,
            (),
        ),
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    assert max(size for _contract, size in tasks.prompt_sizes) <= 4_800
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    assert any(
        item.anchor.target_id == paragraph["block_id"] for item in revisions
    )


def test_oversized_review_block_does_not_skip_neighbor_reviews(tmp_path):
    markdown = tmp_path / "mixed-review.md"
    markdown.write_text(
        "small before\n\nmiddle expands\n\nsmall after",
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "mixed-review-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    tasks = FakeTasks(
        translation_prefix_by_text={"middle expands": "译" * 2_000}
    )
    workflow = TranslationWorkflowService(tasks)
    context = _context(tmp_path, "mixed-review")
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "zh-CN",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "zh-CN",
        1,
        "d" * 64,
        (),
    )

    result = workflow.translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )
    assert isinstance(result, TranslationResult)
    assert len(tasks.review_blocks) == 2
    assert all(
        "middle expands" not in block_text(block)
        for blocks in tasks.review_blocks
        for block in blocks
    )
    assert max(
        size
        for contract, size in tasks.prompt_sizes
        if contract == REVIEW_PROMPT_VERSION
    ) <= 4_800


def test_translation_windows_reserve_space_for_review(tmp_path):
    markdown = tmp_path / "review-windows.md"
    markdown.write_text(
        "# Long\n\n" + "\n\n".join(["source prose " * 40] * 6),
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "review-windows-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    tasks = FakeTasks()
    result = TranslationWorkflowService(tasks).translate_blocks(
        _context(tmp_path, "review-windows"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "fr",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "fr",
            1,
            "d" * 64,
            (),
        ),
        target_language="fr",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    assert tasks.calls.count(TRANSLATION_PROMPT_VERSION) == 3
    assert tasks.calls.count(REVIEW_PROMPT_VERSION) >= 3
    assert max(size for _contract, size in tasks.prompt_sizes) <= 4_800


def test_actual_translation_expansion_splits_review_windows(tmp_path):
    markdown = tmp_path / "expanded-review.md"
    markdown.write_text(
        "# Long\n\n" + "\n\n".join(["source prose " * 8] * 6),
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "expanded-review-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    tasks = FakeTasks(translation_prefix="译" * 600)
    result = TranslationWorkflowService(tasks).translate_blocks(
        _context(tmp_path, "expanded-review"),
        source,
        language=LanguageResult(
            source.document_digest,
            source.source_digest,
            "en",
            "known",
            1,
            "zh-CN",
            "enabled",
        ),
        glossary=GlossaryResult(
            source.document_digest,
            source.source_digest,
            "zh-CN",
            1,
            "e" * 64,
            (),
        ),
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    translation_count = tasks.calls.count(TRANSLATION_PROMPT_VERSION)
    review_count = tasks.calls.count(REVIEW_PROMPT_VERSION)
    assert review_count > translation_count
    assert max(
        size
        for contract, size in tasks.prompt_sizes
        if contract == REVIEW_PROMPT_VERSION
    ) <= 4_800


def test_split_review_fallback_progresses_across_subwindows(tmp_path):
    markdown = tmp_path / "split-review-supervision.md"
    markdown.write_text(
        "# Long\n\n" + "\n\n".join(["source prose " * 8] * 4),
        encoding="utf-8",
    )
    paper = AcDocumentService(cache_root=tmp_path / "split-supervision-cache")
    artifact = paper.import_source(markdown)
    source = TranslationSource(
        RichDocumentParserService(paper.repository).parse_source(artifact)
    )
    language = LanguageResult(
        source.document_digest,
        source.source_digest,
        "en",
        "known",
        1,
        "zh-CN",
        "enabled",
    )
    glossary = GlossaryResult(
        source.document_digest,
        source.source_digest,
        "zh-CN",
        1,
        "f" * 64,
        (),
    )
    tasks = FakeTasks(
        invalid_review=True,
        translation_prefix="译" * 600,
    )
    workflow = TranslationWorkflowService(tasks)
    context = _context(tmp_path, "split-review-supervision")
    result = workflow.translate_blocks(
        context,
        source,
        language=language,
        glossary=glossary,
        target_language="zh-CN",
        input_budget_bytes=4_800,
    )

    assert isinstance(result, TranslationResult)
    assert tasks.calls.count(REVIEW_PROMPT_VERSION) > 1
    revisions = [
        decode_fragment_revision(
            context.artifacts.read_bytes(item.artifact).decode("utf-8"),
            filename=Path(item.revision.path).name,
        )
        for item in result.revision_artifacts
    ]
    assert all(
        item.provenance["translation_fallback"]["kind"]
        == "review_skipped"
        for item in revisions
    )


def test_non_rich_pdf_source_is_rejected(tmp_path):
    path = tmp_path / "scan.pdf"
    path.write_bytes(b"%PDF-fake")
    paper = AcDocumentService(cache_root=tmp_path / "pdf-cache")

    try:
        resolve_translation_source(paper, path)
    except TranslationSourceError as exc:
        assert exc.code == "rich_source_required"
    else:  # pragma: no cover
        raise AssertionError("non-rich PDF source was accepted")


def test_missing_local_source_is_not_misrouted_to_arxiv(tmp_path):
    paper = AcDocumentService(cache_root=tmp_path / "cache")

    with pytest.raises(TranslationSourceError) as exc_info:
        resolve_translation_source(paper, tmp_path / "missing.md")

    assert exc_info.value.code == "source_not_found"
