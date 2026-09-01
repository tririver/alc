"""Public durable service for Companion build control and publications."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ac_jobs import (
    ArtifactRef,
    CorruptStateError,
    ImmutableArtifactStore,
    RunEngine,
    RunRepository,
    RunSnapshot,
    RunSpec,
    RunStatus,
    RunView,
    canonical_json_bytes,
)
from ac_llm import LLMTaskService
from alc_render import (
    Publication,
    PublicationWorkspaceState,
    read_publication_workspace_state,
)

from .build import (
    COMPANION_BUILD_HANDLER,
    CompanionBuildHandler,
    validate_build_diagnostics,
)
from .generation_validation import CompanionContentError
from .publication import (
    CompanionPublicationError,
    PublishedCompanion,
    load_published_companion,
    materialize_published_companion,
)
from .project import CompanionProjectPaths
from .publication_revisions import materialize_operator_revisions
from .request_contracts import (
    CompanionBuildRequest,
    CompanionExecutionOptions,
    CompanionGenerationRecipe,
    decode_handler_semantic_input,
    encode_handler_semantic_input,
    freeze_generation_recipe,
)
from .translation_adapter import (
    CompanionTranslationAdapter,
    require_translation_runtime,
)


class CompanionServiceError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CompanionService:
    """Build, resume, inspect, stop, and load one Companion lineage."""

    def __init__(self, repository: RunRepository | str | Path) -> None:
        self.repository = (
            repository
            if isinstance(repository, RunRepository)
            else RunRepository(repository)
        )
        self.engine = RunEngine(self.repository)

    def build(
        self,
        request: CompanionBuildRequest,
        *,
        recipe: CompanionGenerationRecipe | None = None,
        execution: CompanionExecutionOptions = CompanionExecutionOptions(),
        run_id: str | None = None,
        task_service: LLMTaskService | None = None,
        translation_adapter: CompanionTranslationAdapter | None = None,
    ) -> RunSnapshot:
        if translation_adapter is None:
            require_translation_runtime()
        prepared = self.prepare(request, recipe=recipe, run_id=run_id)
        return self.execute(
            prepared.run_id,
            execution=execution,
            task_service=task_service,
            translation_adapter=translation_adapter,
        )

    def prepare(
        self,
        request: CompanionBuildRequest,
        *,
        recipe: CompanionGenerationRecipe | None = None,
        run_id: str | None = None,
    ) -> RunSnapshot:
        """Durably create one build before an external selector points to it."""

        resolved_recipe = _recipe_for_request(request, recipe)
        resolved = run_id or _companion_run_id_for_recipe(
            request, resolved_recipe
        )
        spec = RunSpec(
            resolved,
            COMPANION_BUILD_HANDLER,
            encode_handler_semantic_input(request, resolved_recipe),
        )
        return self.repository.create(spec)

    def execute(
        self,
        run_id: str,
        *,
        execution: CompanionExecutionOptions = CompanionExecutionOptions(),
        task_service: LLMTaskService | None = None,
        translation_adapter: CompanionTranslationAdapter | None = None,
    ) -> RunSnapshot:
        """Execute or replay one already prepared Companion build."""

        if translation_adapter is None:
            require_translation_runtime()
        spec = self.repository.read_spec(run_id)
        handler = self._handler(
            spec,
            execution=execution,
            task_service=task_service,
            translation_adapter=translation_adapter,
        )
        return self.engine.execute(spec, handler)

    def resume(
        self,
        run_id: str,
        *,
        input: Mapping[str, Any] | None = None,
        execution: CompanionExecutionOptions = CompanionExecutionOptions(),
        task_service: LLMTaskService | None = None,
        translation_adapter: CompanionTranslationAdapter | None = None,
    ) -> RunSnapshot:
        if translation_adapter is None:
            require_translation_runtime()
        spec = self.repository.read_working_spec(run_id)
        handler = self._handler(
            spec,
            execution=execution,
            task_service=task_service,
            translation_adapter=translation_adapter,
        )
        return self.engine.resume(run_id, handler, input=input)

    def _handler(
        self,
        spec: RunSpec,
        *,
        execution: CompanionExecutionOptions,
        task_service: LLMTaskService | None,
        translation_adapter: CompanionTranslationAdapter | None,
    ) -> CompanionBuildHandler:
        if spec.handler == COMPANION_BUILD_HANDLER:
            request, recipe = decode_handler_semantic_input(
                spec.semantic_input
            )
            return CompanionBuildHandler(
                request,
                recipe,
                execution=execution,
                task_service=task_service,
                translation_adapter=translation_adapter,
            )
        raise CompanionServiceError(
            "run_handler_invalid", "run is not a Companion build"
        )

    def inspect(self, run_id: str) -> RunView:
        return self.repository.inspect(run_id)

    def build_diagnostics(
        self, run_id: str
    ) -> Mapping[str, Any] | None:
        """Return the immutable terminal source-preparation diagnostic."""

        self.repository.inspect(run_id)
        artifacts = ImmutableArtifactStore(
            self.repository.run_directory(run_id),
            repository_root=self.repository.root,
        )
        ref = artifacts.find("diagnostics/build")
        if ref is None:
            return None
        try:
            value = json.loads(
                artifacts.read_bytes(ref).decode("utf-8")
            )
        except (
            OSError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise CompanionServiceError(
                "build_diagnostics_invalid",
                "run build diagnostics are unreadable",
            ) from exc
        if not isinstance(value, Mapping):
            raise CompanionServiceError(
                "build_diagnostics_invalid",
                "run build diagnostics are invalid",
            )
        try:
            validate_build_diagnostics(value)
        except (CompanionContentError, TypeError, ValueError) as exc:
            raise CompanionServiceError(
                "build_diagnostics_invalid",
                "run build diagnostics are invalid",
            ) from exc
        return dict(value)

    def progress(self, run_id: str) -> Mapping[str, Any]:
        """Return normalized durable progress and the valid next action."""

        view = self.repository.inspect(run_id)
        request, recipe = decode_handler_semantic_input(
            self.repository.read_spec(run_id).semantic_input
        )
        artifacts = ImmutableArtifactStore(
            self.repository.run_directory(run_id),
            repository_root=self.repository.root,
        )
        plan = _optional_artifact_json(
            artifacts,
            "diagnostics/progress-plan",
            recovery_epoch=view.snapshot.recovery_epoch,
        )
        chapter_ids: tuple[str, ...] = ()
        translation_required = False
        provider: str | None = recipe.model.provider
        model: str | None = recipe.model.model
        tier: str | None = recipe.model.tier
        if plan is not None:
            if plan.get("schema_version") != "alc.companion.progress_plan.v1":
                raise CompanionServiceError(
                    "progress_plan_invalid", "run progress plan is invalid"
                )
            raw_chapters = plan.get("chapters")
            if not isinstance(raw_chapters, list) or any(
                not isinstance(item, Mapping)
                or not isinstance(item.get("chapter_id"), str)
                for item in raw_chapters
            ):
                raise CompanionServiceError(
                    "progress_plan_invalid", "run progress plan is invalid"
                )
            chapter_ids = tuple(
                str(item["chapter_id"]) for item in raw_chapters
            )
            translation_required = plan.get("translation_required") is True
            provider = _optional_string(plan.get("provider"))
            model = _optional_string(plan.get("model"))
            tier = _optional_string(plan.get("tier"))

        glossary_ready = _find_artifact_in_lineage(
            artifacts,
            "diagnostics/glossary-ready",
            recovery_epoch=view.snapshot.recovery_epoch,
        ) is not None
        translated = (
            _completed_group_units(
                self.repository, run_id, "chapter-translations-v3"
            )
            if translation_required
            else len(chapter_ids)
        )
        guided = sum(
            _find_artifact_in_lineage(
                artifacts,
                f"chapters/{chapter_id}/guide-accepted",
                recovery_epoch=view.snapshot.recovery_epoch,
            )
            is not None
            for chapter_id in chapter_ids
        )
        joined = sum(
            _find_artifact_in_lineage(
                artifacts,
                f"chapters/{chapter_id}/accepted",
                recovery_epoch=view.snapshot.recovery_epoch,
            )
            is not None
            for chapter_id in chapter_ids
        )
        final_ready = view.snapshot.result_ref is not None
        if view.snapshot.status is RunStatus.SUCCEEDED:
            glossary_ready = True
            translated = len(chapter_ids)
            guided = len(chapter_ids)
            joined = len(chapter_ids)
        partial_reader = (
            self.repository.run_directory(run_id)
            / "partial-reader"
            / "companion.html"
        )
        translation_fallbacks = _translation_fallback_summary(
            self.repository.run_directory(run_id)
        )
        total = (
            4
            + len(chapter_ids) * (2 + int(translation_required))
            + 1
            if plan is not None
            else 0
        )
        completed = (
            3
            + int(glossary_ready)
            + min(translated, len(chapter_ids))
            * int(translation_required)
            + guided
            + joined
            + int(final_ready)
            if plan is not None
            else 0
        )
        if plan is None:
            source_ready = _find_artifact_in_lineage(
                artifacts,
                "diagnostics/build",
                recovery_epoch=view.snapshot.recovery_epoch,
            ) is not None
            authors_ready = bool(request.authors) or (
                _find_artifact_in_lineage(
                    artifacts,
                    "identity/authors",
                    recovery_epoch=view.snapshot.recovery_epoch,
                )
                is not None
            )
            phase = (
                "source_preparation"
                if not source_ready
                else "author_identity"
                if not authors_ready
                else "language_detection"
            )
        elif not glossary_ready:
            phase = "glossary"
        elif translation_required and translated < len(chapter_ids):
            phase = "translation"
        elif guided < len(chapter_ids):
            phase = "guides"
        elif joined < len(chapter_ids):
            phase = "chapter_join"
        elif not final_ready:
            phase = "publication"
        else:
            phase = "completed"
        return {
            "schema_version": "alc.companion.run_progress.v1",
            "phase": phase,
            "completed_units": completed,
            "total_units": total,
            "completed_chapters": joined,
            "total_chapters": len(chapter_ids),
            "active_model": {
                "provider": provider,
                "model": model,
                "tier": tier,
            },
            "last_progress_at": _last_progress_at(
                self.repository.run_directory(run_id),
                fallback=view.snapshot.updated_at,
            ),
            "partial_reader_available": partial_reader.is_file(),
            "partial_reader_path": (
                str(partial_reader) if partial_reader.is_file() else None
            ),
            "translation_fallbacks": translation_fallbacks,
            "next_action": _next_action(view.snapshot),
        }

    def stop(self, run_id: str, *, reason: str | None = None) -> RunView:
        return self.repository.request_stop(run_id, reason=reason)

    def published_companion(self, run_id: str) -> PublishedCompanion:
        snapshot = self.repository.inspect(run_id).snapshot
        if snapshot.status is not RunStatus.SUCCEEDED or snapshot.result_ref is None:
            raise CompanionServiceError(
                "publication_unavailable",
                "run has no accepted publication",
            )
        artifacts = ImmutableArtifactStore(
            self.repository.run_directory(run_id),
            repository_root=self.repository.root,
        )
        try:
            return load_published_companion(
                artifacts, snapshot.result_ref
            )
        except CompanionPublicationError as exc:
            raise CompanionServiceError(
                "publication_invalid",
                "run publication artifacts are invalid",
            ) from exc

    def publication(self, run_id: str) -> Publication:
        return self.published_companion(run_id).publication

    def materialize_publication(
        self,
        run_id: str,
        workspace: str | Path,
        *,
        project_paths: CompanionProjectPaths | None = None,
    ) -> Path:
        published = self.published_companion(run_id)
        artifacts = ImmutableArtifactStore(
            self.repository.run_directory(run_id),
            repository_root=self.repository.root,
        )
        try:
            publication_path = materialize_published_companion(
                artifacts, published, workspace
            )
            if project_paths is not None:
                materialize_operator_revisions(
                    project_paths, run_id, Path(workspace)
                )
            return publication_path
        except CompanionPublicationError as exc:
            raise CompanionServiceError(
                "publication_invalid",
                "run publication cannot be materialized",
            ) from exc

    def publication_workspace_state(
        self,
        run_id: str,
        workspace: str | Path,
        *,
        project_paths: CompanionProjectPaths | None = None,
    ) -> PublicationWorkspaceState:
        publication_path = self.materialize_publication(
            run_id,
            workspace,
            project_paths=project_paths,
        )
        return read_publication_workspace_state(publication_path)


def companion_run_id(
    request: CompanionBuildRequest,
    recipe: CompanionGenerationRecipe | None,
) -> str:
    resolved_recipe = _recipe_for_request(request, recipe)
    return _companion_run_id_for_recipe(request, resolved_recipe)


def _companion_run_id_for_recipe(
    request: CompanionBuildRequest,
    recipe: CompanionGenerationRecipe,
) -> str:
    semantic_input = encode_handler_semantic_input(request, recipe)
    digest = hashlib.sha256(
        canonical_json_bytes(
            {
                "handler": COMPANION_BUILD_HANDLER,
                "semantic_input": semantic_input,
            }
        )
    ).hexdigest()
    return f"companion-{digest[:24]}"


def _recipe_for_request(
    request: CompanionBuildRequest,
    recipe: CompanionGenerationRecipe | None,
) -> CompanionGenerationRecipe:
    if not isinstance(request, CompanionBuildRequest):
        raise ValueError("unsupported Companion build request")
    resolved_recipe = recipe or CompanionGenerationRecipe()
    if not isinstance(resolved_recipe, CompanionGenerationRecipe):
        raise ValueError("build request requires a Companion recipe")
    return freeze_generation_recipe(resolved_recipe)


def _optional_artifact_json(
    artifacts: ImmutableArtifactStore,
    artifact_id: str,
    *,
    recovery_epoch: int,
) -> Mapping[str, Any] | None:
    ref = _find_artifact_in_lineage(
        artifacts, artifact_id, recovery_epoch=recovery_epoch
    )
    if ref is None:
        return None
    try:
        value = json.loads(artifacts.read_bytes(ref).decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CompanionServiceError(
            "progress_plan_invalid", "run progress data are unreadable"
        ) from exc
    if not isinstance(value, Mapping):
        raise CompanionServiceError(
            "progress_plan_invalid", "run progress data are invalid"
        )
    return value


def _find_artifact_in_lineage(
    artifacts: ImmutableArtifactStore,
    artifact_id: str,
    *,
    recovery_epoch: int,
) -> ArtifactRef | None:
    for epoch in range(recovery_epoch, 0, -1):
        ref = artifacts.find(f"recovery-{epoch}/{artifact_id}")
        if ref is not None:
            return ref
    return artifacts.find(artifact_id)


def _completed_group_units(
    repository: RunRepository, run_id: str, group_id: str
) -> int:
    try:
        group = repository.inspect_group(run_id, group_id)
    except CorruptStateError:
        snapshot = repository.inspect(run_id).snapshot
        group_root = repository.run_directory(run_id) / "groups"
        if snapshot.recovery_epoch:
            group_root = (
                group_root
                / f"recovery-{snapshot.recovery_epoch:04d}"
            )
        if not (group_root / group_id / "state.json").is_file():
            return 0
        raise
    except (OSError, ValueError):
        return 0
    return sum(item.status == "succeeded" for item in group.units)


def _last_progress_at(run_directory: Path, *, fallback: str) -> str:
    timestamps: list[float] = []
    for path in run_directory.rglob("*"):
        try:
            if path.is_file() and path.name not in {
                "lease.lock",
                "lease.json",
            }:
                timestamps.append(path.stat().st_mtime)
        except OSError:
            continue
    if not timestamps:
        return fallback
    return (
        datetime.fromtimestamp(max(timestamps), timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _translation_fallback_summary(
    run_directory: Path,
) -> dict[str, Any]:
    source_text_units = 0
    review_skipped_units = 0
    reason_codes: list[str] = []
    path = run_directory / "events.jsonl"
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(event, Mapping) or event.get("event") != (
                    "translation_fallback"
                ):
                    continue
                data = event.get("data")
                if not isinstance(data, Mapping):
                    continue
                source_count = data.get("source_text_block_count")
                review_count = data.get("review_skipped_block_count")
                if isinstance(source_count, int) and not isinstance(
                    source_count, bool
                ):
                    source_text_units += max(0, source_count)
                if isinstance(review_count, int) and not isinstance(
                    review_count, bool
                ):
                    review_skipped_units += max(0, review_count)
                raw_codes = data.get("reason_codes")
                if isinstance(raw_codes, list):
                    reason_codes.extend(
                        code
                        for code in raw_codes
                        if isinstance(code, str) and code
                    )
    except (OSError, UnicodeError):
        pass
    return {
        "source_text_units": source_text_units,
        "review_skipped_units": review_skipped_units,
        "reason_codes": list(dict.fromkeys(reason_codes)),
    }


def _next_action(snapshot: RunSnapshot) -> dict[str, Any]:
    awaiting = snapshot.awaiting
    candidate_path = (
        snapshot.error.details.get("candidate_path")
        if snapshot.error is not None
        else None
    )
    if awaiting is not None and not (
        isinstance(candidate_path, str) and candidate_path
    ):
        candidate_path = awaiting.details.get(
            "active_candidate_path",
            awaiting.details.get("candidate_path"),
        )
    if snapshot.status is RunStatus.SUCCEEDED:
        kind = "render_and_validate"
        command = "alc-companion render"
        input_required = False
        request_artifact = None
    elif snapshot.status in {RunStatus.PENDING, RunStatus.RUNNING}:
        kind = "wait"
        command = "alc-companion status"
        input_required = False
        request_artifact = None
    elif snapshot.status is RunStatus.PAUSED:
        assert awaiting is not None
        kind = (
            "provide_validated_input"
            if awaiting.input_required
            else "repair_candidate_and_resume"
            if isinstance(candidate_path, str) and candidate_path
            else "resume_same_run"
        )
        command = "alc-companion resume"
        input_required = awaiting.input_required
        request_artifact = (
            awaiting.request_ref.relative_path
            if awaiting.request_ref is not None
            else None
        )
    else:
        kind = (
            "repair_candidate_and_resume"
            if isinstance(candidate_path, str) and candidate_path
            else "retry_same_run"
        )
        command = "alc-companion resume"
        input_required = False
        request_artifact = None
    return {
        "kind": kind,
        "command": command,
        "input_required": input_required,
        "request_artifact": request_artifact,
        "candidate_path": (
            candidate_path
            if isinstance(candidate_path, str) and candidate_path
            else None
        ),
    }


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = [
    "CompanionService",
    "CompanionServiceError",
    "companion_run_id",
]
