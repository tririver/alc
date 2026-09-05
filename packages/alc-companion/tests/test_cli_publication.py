from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from ac_jobs import (
    Awaiting,
    CommandResult,
    CommandStatus,
    ResumeReason,
    RunBusyError,
    RunSnapshot,
    RunStatus,
)
from alc_companion import cli
from alc_companion.project import CompanionProjectError, CompanionProjectPaths
from alc_companion.service import _next_action, _translation_fallback_summary
from alc_companion.source_bundle import HTMLSourceBundleBinding
from alc_render import BrowserValidation, HTMLRenderError


def test_companion_execution_bounds_a_silent_provider() -> None:
    defaults = cli.CompanionExecutionOptions()
    command = cli._execution_options(
        SimpleNamespace(
            workers=1,
            document_cache_root=None,
            host_authority="unknown",
        )
    )

    assert defaults.llm.limits.idle_timeout_seconds == 300
    assert command.llm.limits.idle_timeout_seconds == 300


def test_delivery_mode_and_grade_normalize_legacy_publications() -> None:
    partial = SimpleNamespace(
        reader_profile={
            "translation_mode": "enabled",
            "delivery_ledger": {
                "delivery_grade": "degraded",
                "issues": [{"category": "translation_source_text"}],
            },
        }
    )
    source_only = SimpleNamespace(
        reader_profile={
            "build_state": "provider_source_only",
            "delivery_ledger": {"delivery_grade": "degraded", "issues": []},
        }
    )

    assert cli._delivery_mode(partial, source_only=False) == "partial_bilingual"
    assert cli._delivery_grade(partial, source_only=False) == "degraded"
    assert cli._delivery_mode(source_only, source_only=True) == "source_only"
    assert cli._delivery_grade(source_only, source_only=True) == "source_only"


class _Service:
    def __init__(self, _root: Path, publication: object) -> None:
        self._publication = publication
        self._snapshot = SimpleNamespace(status=RunStatus.SUCCEEDED)

    def inspect(self, _run_id: str) -> object:
        return SimpleNamespace(snapshot=self._snapshot)

    def build_diagnostics(self, _run_id: str) -> None:
        return None

    def progress(self, _run_id: str) -> dict[str, object]:
        return {"phase": "completed"}

    def publication(self, _run_id: str) -> object:
        return self._publication

    def materialize_publication(
        self, _run_id: str, workspace: Path, **_kwargs: object
    ) -> Path:
        return workspace / "publication.json"


def _state(publication: object) -> object:
    return SimpleNamespace(
        publication=publication,
        publication_digest=publication.publication_digest,
        edition_digest="b" * 64,
        revisions=(),
        selected_revisions=(),
        selected_revision_digests=(),
    )


def test_status_does_not_advertise_stale_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication_path = paths.publication_workspace("run") / "publication.json"
    publication_path.parent.mkdir(parents=True)
    publication_path.write_text("{}", encoding="utf-8")
    paths.delivery_html.write_text("stale", encoding="utf-8")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)

    monkeypatch.setattr(
        cli.CompanionProjectPaths, "load", lambda _value: paths
    )
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli,
        "command_result_from_snapshot",
        lambda *_args, **_kwargs: CommandResult(CommandStatus.COMPLETED),
    )
    monkeypatch.setattr(cli, "snapshot_data", lambda _snapshot: {})
    monkeypatch.setattr(
        cli, "validate_publication_workspace", lambda _path: ()
    )
    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )
    monkeypatch.setattr(
        cli,
        "validate_standalone_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HTMLRenderError("wrong publication")
        ),
    )

    result = cli._status(SimpleNamespace(project_dir=str(paths.root)))

    assert [item.role for item in result.artifacts] == ["publication"]
    assert any(
        item.code == "standalone_html_stale"
        for item in result.warnings
    )


def test_status_reports_validated_static_fallback_as_source_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication_path = paths.publication_workspace("run") / "publication.json"
    publication_path.parent.mkdir(parents=True)
    publication_path.write_text("{}", encoding="utf-8")
    paths.delivery_html.write_text(
        '<html data-alc-source-only="true"></html>', encoding="utf-8"
    )
    publication = SimpleNamespace(
        publication_digest="a" * 64,
        reader_profile={
            "translation_mode": "enabled",
            "delivery_mode": "bilingual",
            "delivery_ledger": {"delivery_grade": "complete", "issues": []},
        },
    )
    service = _Service(paths.jobs_root, publication)
    validated: list[Path] = []

    monkeypatch.setattr(
        cli.CompanionProjectPaths, "load", lambda _value: paths
    )
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli,
        "command_result_from_snapshot",
        lambda *_args, **_kwargs: CommandResult(CommandStatus.COMPLETED),
    )
    monkeypatch.setattr(cli, "snapshot_data", lambda _snapshot: {})
    monkeypatch.setattr(
        cli, "validate_publication_workspace", lambda _path: ()
    )
    monkeypatch.setattr(
        cli,
        "read_publication_workspace_state",
        lambda _path: _state(publication),
    )
    monkeypatch.setattr(
        cli,
        "validate_source_only_html",
        lambda _publication, path: validated.append(Path(path)),
    )
    monkeypatch.setattr(
        cli,
        "validate_standalone_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("static fallback must not use the interactive validator")
        ),
    )

    result = cli._status(SimpleNamespace(project_dir=str(paths.root)))

    assert validated == [paths.delivery_html]
    assert result.data["delivery_grade"] == "source_only"
    assert result.data["delivery_mode"] == "source_only"
    assert result.data["workspace_html_consistent"] is True


def test_status_never_acquires_the_delivery_write_lease(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    snapshot = SimpleNamespace(status=RunStatus.RUNNING)
    service = SimpleNamespace(
        inspect=lambda _run_id: SimpleNamespace(snapshot=snapshot),
        build_diagnostics=lambda _run_id: None,
        progress=lambda _run_id: {"phase": "translation"},
    )
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli,
        "file_lease",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("status must not acquire the delivery lease")
        ),
    )
    monkeypatch.setattr(
        cli,
        "command_result_from_snapshot",
        lambda *_args, **_kwargs: CommandResult(CommandStatus.COMPLETED),
    )
    monkeypatch.setattr(cli, "snapshot_data", lambda _snapshot: {})

    result = cli._status(SimpleNamespace(project_dir=str(paths.root)))

    assert result.data["progress"] == {"phase": "translation"}


def test_wait_emits_heartbeats_until_terminal_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    statuses = iter((RunStatus.RUNNING, RunStatus.SUCCEEDED))

    class WaitService:
        def inspect(self, _run_id: str) -> object:
            return SimpleNamespace(
                snapshot=SimpleNamespace(status=next(statuses))
            )

        def resume(self, _run_id: str) -> object:
            raise RunBusyError("lease is held")

        def progress(self, _run_id: str) -> dict[str, object]:
            return {
                "phase": "translation",
                "completed_units": 3,
                "total_units": 8,
                "last_progress_at": "2026-09-04T00:00:00Z",
            }

    terminal = CommandResult(CommandStatus.COMPLETED, data={"terminal": True})
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: WaitService())
    monkeypatch.setattr(cli, "_status_locked", lambda _paths: terminal)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    result = cli._wait(
        SimpleNamespace(project_dir=str(paths.root), poll_seconds=0.25)
    )

    assert result is terminal
    heartbeat = json.loads(capsys.readouterr().err)
    assert heartbeat == {
        "completed_units": 3,
        "event": "alc.companion.wait",
        "last_progress_at": "2026-09-04T00:00:00Z",
        "phase": "translation",
        "run_id": "run",
        "status": "running",
        "total_units": 8,
    }


def test_wait_recovers_an_orphaned_running_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    recovered: list[str] = []

    class WaitService:
        def __init__(self) -> None:
            self.status = RunStatus.RUNNING

        def inspect(self, _run_id: str) -> object:
            return SimpleNamespace(
                snapshot=SimpleNamespace(status=self.status)
            )

        def resume(self, run_id: str) -> object:
            recovered.append(run_id)
            self.status = RunStatus.SUCCEEDED
            return SimpleNamespace(status=self.status)

        def progress(self, _run_id: str) -> dict[str, object]:
            raise AssertionError("orphan recovery should run before another heartbeat")

    terminal = CommandResult(CommandStatus.COMPLETED, data={"terminal": True})
    service = WaitService()
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(cli, "_status_locked", lambda _paths: terminal)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    result = cli._wait(
        SimpleNamespace(project_dir=str(paths.root), poll_seconds=0.25)
    )

    assert result is terminal
    assert recovered == ["run"]


def test_wait_observes_an_actively_owned_running_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    statuses = iter((RunStatus.RUNNING, RunStatus.SUCCEEDED))
    resume_attempts: list[str] = []

    class WaitService:
        def inspect(self, _run_id: str) -> object:
            return SimpleNamespace(
                snapshot=SimpleNamespace(status=next(statuses))
            )

        def resume(self, run_id: str) -> object:
            resume_attempts.append(run_id)
            raise RunBusyError("lease is held")

        def progress(self, _run_id: str) -> dict[str, object]:
            return {
                "phase": "translation",
                "completed_units": 3,
                "total_units": 8,
                "last_progress_at": "2026-09-04T00:00:00Z",
            }

    terminal = CommandResult(CommandStatus.COMPLETED, data={"terminal": True})
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: WaitService())
    monkeypatch.setattr(cli, "_status_locked", lambda _paths: terminal)
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    result = cli._wait(
        SimpleNamespace(project_dir=str(paths.root), poll_seconds=0.25)
    )

    assert result is terminal
    assert resume_attempts == ["run"]


def test_wait_does_not_recover_a_terminal_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")

    class WaitService:
        def inspect(self, _run_id: str) -> object:
            return SimpleNamespace(
                snapshot=SimpleNamespace(status=RunStatus.SUCCEEDED)
            )

        def resume(self, _run_id: str) -> object:
            raise AssertionError("terminal attempts must not be resumed")

    terminal = CommandResult(CommandStatus.COMPLETED, data={"terminal": True})
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: WaitService())
    monkeypatch.setattr(cli, "_status_locked", lambda _paths: terminal)

    result = cli._wait(
        SimpleNamespace(project_dir=str(paths.root), poll_seconds=0.25)
    )

    assert result is terminal


def test_build_refuses_implicit_selected_lineage_replacement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("existing-run")
    monkeypatch.setattr(cli, "require_translation_runtime", lambda: None)
    monkeypatch.setattr(
        cli.CompanionProjectPaths, "open", lambda _value: paths
    )
    monkeypatch.setattr(cli, "AcDocumentService", lambda **_kwargs: object())
    monkeypatch.setattr(
        cli,
        "_resolve_source",
        lambda *_args, **_kwargs: (object(), (), ()),
    )
    monkeypatch.setattr(cli, "CompanionBuildRequest", lambda **_kwargs: object())
    monkeypatch.setattr(
        cli, "CompanionGenerationRecipe", lambda **_kwargs: object()
    )
    monkeypatch.setattr(cli, "freeze_generation_recipe", lambda value: value)
    monkeypatch.setattr(cli, "companion_run_id", lambda *_args: "new-run")
    monkeypatch.setattr(cli, "CompanionService", lambda _root: object())
    args = SimpleNamespace(
        workers=1,
        target_language="zh-CN",
            provider="codex",
            model=None,
            effort=None,
            approx_term_count=50,
        author=[],
        reader_labels=None,
        pdf=None,
        project_dir=str(paths.root),
        document_cache_root=None,
        source="source.html",
        refresh=False,
        user_intent="",
        cross_chapter_editorial_review=False,
        host_authority="unknown",
        new_lineage=False,
    )

    with pytest.raises(CompanionProjectError) as error:
        cli._build(args)

    assert error.value.code == "selected_run_conflict"


def test_build_binds_html_source_manifest_and_persists_warnings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    binding = HTMLSourceBundleBinding(
        bundle_digest="a" * 64,
        primary_artifact_digest="b" * 64,
        materialized_source_digest="c" * 64,
        requested_url="https://example.test/paper.html",
        final_url="https://example.test/paper.html",
    )
    source_manifest = SimpleNamespace(
        binding=binding,
        warnings=("html_dependency_fetch_failed: resource unavailable",),
    )
    captured: dict[str, object] = {}

    class Service:
        def __init__(self, _root: Path) -> None:
            pass

        def prepare(self, request: object, **_kwargs: object) -> object:
            captured["request"] = request
            return SimpleNamespace(run_id="bundle-run")

        def execute(self, _run_id: str, **_kwargs: object) -> object:
            return SimpleNamespace()

    def request_factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(cli, "require_translation_runtime", lambda: None)
    monkeypatch.setattr(cli.CompanionProjectPaths, "open", lambda _value: paths)
    monkeypatch.setattr(
        cli, "load_html_source_manifest", lambda *_args, **_kwargs: source_manifest
    )
    monkeypatch.setattr(cli, "AcDocumentService", lambda **_kwargs: object())
    monkeypatch.setattr(
        cli,
        "_resolve_source",
        lambda *_args, **_kwargs: (object(), (), ("parser warning",)),
    )
    monkeypatch.setattr(cli, "CompanionBuildRequest", request_factory)
    monkeypatch.setattr(cli, "freeze_generation_recipe", lambda value: value)
    monkeypatch.setattr(cli, "CompanionService", Service)
    monkeypatch.setattr(cli, "companion_run_id", lambda *_args: "bundle-run")
    monkeypatch.setattr(cli, "_snapshot_result", lambda *_args, **_kwargs: "ok")
    args = SimpleNamespace(
        workers=1,
        target_language="zh-CN",
            provider="codex",
            model=None,
            effort=None,
            approx_term_count=50,
        author=[],
        reader_labels=None,
        pdf=None,
        project_dir=str(paths.root),
        document_cache_root=None,
        source="source.html",
        html_source_manifest="manifest.json",
        refresh=False,
        user_intent="",
        cross_chapter_editorial_review=False,
        host_authority="unknown",
        new_lineage=False,
    )

    assert cli._build(args) == "ok"
    assert captured["source_bundle"] == binding
    assert paths.source_diagnostics("bundle-run") == (
        "parser warning",
        "html_dependency_fetch_failed: resource unavailable",
    )


def test_invalid_html_source_manifest_creates_no_companion_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "source.html"
    source.write_text("<p>source</p>", encoding="utf-8")
    project = tmp_path / "project"
    monkeypatch.setattr(cli, "require_translation_runtime", lambda: None)

    def invalid_manifest(*_args: object, **_kwargs: object) -> object:
        raise ValueError("manifest integrity failure")

    monkeypatch.setattr(cli, "load_html_source_manifest", invalid_manifest)

    assert cli.main(
        [
            "build",
            str(source),
            "--html-source-manifest",
            str(tmp_path / "manifest.json"),
            "--project-dir",
            str(project),
            "--host-authority",
            "unknown",
        ]
    ) == 1

    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "invalid_request"
    assert not (project / ".alc" / "companion" / "project.json").exists()


def test_progress_summarizes_translation_fallback_events(
    tmp_path: Path,
) -> None:
    run = tmp_path / "run"
    run.mkdir()
    (run / "events.jsonl").write_text(
        json.dumps(
            {
                "event": "translation_fallback",
                "data": {
                    "source_text_block_count": 2,
                    "review_skipped_block_count": 1,
                    "reason_codes": ["translation_source_identity_invalid"],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "event": "translation_fallback",
                "data": {
                    "glossary_entry_count": 3,
                    "reason_codes": ["glossary_control_character_invalid"],
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "event": "translation_provider_fallback",
                "data": {
                    "provider": "codex",
                    "model": "gpt-5.6-luna",
                    "tier": "medium",
                    "effort": "medium",
                    "reason_code": "provider_crash_retry_exhausted",
                    "failure_category": "timeout",
                    "detail_code": "provider_idle_timeout",
                    "stage": "translation",
                    "window_ordinal": 3,
                    "consecutive_window_failures": 2,
                    "global_fallback_triggered": True,
                    "remaining_windows_skipped": 4,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert _translation_fallback_summary(run) == {
        "source_text_units": 2,
        "review_skipped_units": 1,
        "reason_codes": [
            "translation_source_identity_invalid",
            "glossary_control_character_invalid",
        ],
        "provider_failure": {
            "provider": "codex",
            "model": "gpt-5.6-luna",
            "tier": "medium",
            "effort": "medium",
            "failure_categories": ["timeout"],
            "detail_codes": ["provider_idle_timeout"],
            "first_failed_window": 3,
            "failed_window_count": 1,
            "remaining_windows_skipped": 4,
            "global_fallback_triggered": True,
        },
    }


def test_paused_semantic_candidate_is_reported_as_repair_action() -> None:
    candidate = "/tmp/chapter.semantic-retry.json"
    snapshot = RunSnapshot(
        "paused-run",
        2,
        RunStatus.PAUSED,
        1,
        "2026-09-01T00:00:00Z",
        "2026-09-01T00:01:00Z",
        awaiting=Awaiting(
            ResumeReason.SUPERVISION_REQUIRED,
            "semantic-retry",
            False,
            details={"active_candidate_path": candidate},
        ),
    )

    assert _next_action(snapshot) == {
        "kind": "repair_candidate_and_resume",
        "command": "alc-companion resume",
        "input_required": False,
        "request_artifact": None,
        "candidate_path": candidate,
    }


def test_status_never_advertises_html_when_workspace_state_is_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication_path = paths.publication_workspace("run") / "publication.json"
    publication_path.parent.mkdir(parents=True)
    publication_path.write_text("{}", encoding="utf-8")
    paths.delivery_html.write_text("reader", encoding="utf-8")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)
    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli,
        "command_result_from_snapshot",
        lambda *_args, **_kwargs: CommandResult(CommandStatus.COMPLETED),
    )
    monkeypatch.setattr(cli, "snapshot_data", lambda _snapshot: {})
    monkeypatch.setattr(cli, "validate_publication_workspace", lambda _path: ())
    monkeypatch.setattr(
        cli,
        "read_publication_workspace_state",
        lambda _path: (_ for _ in ()).throw(HTMLRenderError("bad workspace")),
    )
    monkeypatch.setattr(
        cli,
        "validate_standalone_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("HTML must not validate without workspace state")
        ),
    )

    result = cli._status(SimpleNamespace(project_dir=str(paths.root)))

    assert result.artifacts == ()
    assert result.data["workspace_html_consistent"] is False


def test_validate_requires_standalone_html(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)
    publication_path = paths.publication_workspace("run") / "publication.json"
    publication_path.parent.mkdir(parents=True)
    publication_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        cli.CompanionProjectPaths, "load", lambda _value: paths
    )
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli, "validate_publication_workspace", lambda _path: ()
    )
    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )

    with pytest.raises(
        HTMLRenderError, match="no standalone HTML release"
    ):
        cli._validate(SimpleNamespace(project_dir=str(paths.root)))


def test_validate_forwards_optional_browser_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)
    publication_path = paths.publication_workspace("run") / "publication.json"
    publication_path.parent.mkdir(parents=True)
    publication_path.write_text("{}", encoding="utf-8")
    paths.delivery_html.write_text("reader", encoding="utf-8")
    calls: list[tuple[Path, str | None, int]] = []

    monkeypatch.setattr(cli.CompanionProjectPaths, "load", lambda _value: paths)
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(cli, "validate_publication_workspace", lambda _path: ())
    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )
    monkeypatch.setattr(
        cli, "validate_standalone_html", lambda *_args, **_kwargs: None
    )

    def validate_browser(
        path: Path, *, browser_executable: str | None, timeout_seconds: int
    ) -> BrowserValidation:
        calls.append((path, browser_executable, timeout_seconds))
        return BrowserValidation("/usr/bin/chromium", timeout_seconds)

    monkeypatch.setattr(cli, "validate_reader_in_browser", validate_browser)

    result = cli._validate(SimpleNamespace(
        project_dir=str(paths.root),
        browser=True,
        browser_executable="custom-chromium",
        browser_timeout=11,
    ))

    assert calls == [(paths.delivery_html, "custom-chromium", 11)]
    assert result.data["browser"] == {
        "executable": "/usr/bin/chromium",
        "timeout_seconds": 11,
    }


@pytest.mark.parametrize(
    "message",
    (
        "fragment provenance differs from the rich source",
        "fragment Markdown citations do not match citation_ids",
        "layer producer differs from publication reference",
    ),
)
def test_render_locked_does_not_downgrade_integrity_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, message: str
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)
    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )
    monkeypatch.setattr(
        cli,
        "render_publication_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(HTMLRenderError(message)),
    )
    monkeypatch.setattr(
        cli,
        "render_source_only_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("integrity error was downgraded")
        ),
    )
    with pytest.raises(HTMLRenderError, match=message):
        cli._render_locked(paths, "run", service)


def test_render_locked_forces_provider_source_only_delivery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication = SimpleNamespace(
        publication_digest="a" * 64,
        reader_profile={"build_state": "provider_source_only"},
    )
    service = _Service(paths.jobs_root, publication)
    run_html = paths.publication_html("run")
    calls: list[str] = []

    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )
    monkeypatch.setattr(
        cli,
        "render_publication_html",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("provider fallback attempted interactive rendering")
        ),
    )

    def render_source_only(_publication, output):
        calls.append("render")
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text("source-only", encoding="utf-8")
        return SimpleNamespace(html_path=run_html, warnings=())

    monkeypatch.setattr(cli, "render_source_only_html", render_source_only)
    monkeypatch.setattr(
        cli,
        "validate_source_only_html",
        lambda *_args, **_kwargs: calls.append("validate"),
    )
    monkeypatch.setattr(
        CompanionProjectPaths,
        "_promote_publication_html_locked",
        lambda _self, _run_id: True,
    )

    result = cli._render_locked(paths, "run", service)

    assert calls == ["render", "validate"]
    assert result.data["delivery_grade"] == "source_only"
    assert any(
        item.code == "provider_degraded_source_only"
        for item in result.warnings
    )


@pytest.mark.parametrize(
    ("promoted", "artifact_roles"),
    ((True, ["publication", "web"]), (False, ["publication"])),
)
def test_render_advertises_only_the_promoted_root_html(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    promoted: bool,
    artifact_roles: list[str],
) -> None:
    paths = CompanionProjectPaths.open(tmp_path / "project")
    paths.select_run("run")
    publication = SimpleNamespace(publication_digest="a" * 64)
    service = _Service(paths.jobs_root, publication)
    run_html = paths.publication_html("run")

    monkeypatch.setattr(
        cli.CompanionProjectPaths, "load", lambda _value: paths
    )
    monkeypatch.setattr(cli, "CompanionService", lambda _root: service)
    monkeypatch.setattr(
        cli,
        "render_publication_html",
        lambda _publication, _output: SimpleNamespace(
            html_path=run_html,
            warnings=(),
        ),
    )
    monkeypatch.setattr(
        cli, "read_publication_workspace_state", lambda _path: _state(publication)
    )
    monkeypatch.setattr(
        cli, "validate_standalone_html", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(
        CompanionProjectPaths,
        "_promote_publication_html_locked",
        lambda _self, _run_id: promoted,
    )

    result = cli._render(SimpleNamespace(project_dir=str(paths.root)))

    assert [item.role for item in result.artifacts] == artifact_roles
    if promoted:
        assert result.artifacts[-1].path == str(paths.delivery_html)
        assert result.data["delivery"] == {
            "html": str(paths.delivery_html)
        }
    else:
        assert result.data["delivery"] == {}
        assert any(
            item.code == "publication_not_selected"
            for item in result.warnings
        )


def test_main_reports_html_validation_errors_as_protocol_failures(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        cli,
        "_dispatch",
        lambda _args: (_ for _ in ()).throw(
            HTMLRenderError("standalone HTML is invalid")
        ),
    )

    assert cli.main(["status", "--project-dir", "unused"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "html_render_failed"
