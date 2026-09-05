from __future__ import annotations

import json

import pytest

import alc_companion.request_contracts as request_contracts
from ac_llm import ModelSelection
from alc_companion.cli import main
from alc_companion.request_contracts import (
    CompanionGenerationRecipe,
    freeze_generation_recipe,
)


def test_build_freezes_auto_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AC_AGENT_HOST", "codex")
    frozen = freeze_generation_recipe(
        CompanionGenerationRecipe(model=ModelSelection())
    )

    assert frozen.model == ModelSelection(
        provider="codex",
        model="gpt-5.6-luna",
        tier="medium",
        reasoning_effort="medium",
    )


def test_build_freezes_missing_model_for_explicit_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        request_contracts,
        "resolve_model_selection",
        lambda selection: ModelSelection(
            provider=selection.provider,
            model="gpt-5.6-luna",
            tier="medium",
        ),
    )

    frozen = freeze_generation_recipe(
        CompanionGenerationRecipe(
            model=ModelSelection(provider="codex", model=None, tier="high")
        )
    )

    assert frozen.model == ModelSelection(
        provider="codex",
        model="gpt-5.6-luna",
        tier="medium",
        reasoning_effort="medium",
    )


def test_build_preserves_custom_model_and_reasoning_effort() -> None:
    frozen = freeze_generation_recipe(
        CompanionGenerationRecipe(
            model=ModelSelection(
                provider="codex",
                model="gpt-5.6-terra",
                reasoning_effort="high",
            )
        )
    )

    assert frozen.model == ModelSelection(
        provider="codex",
        model="gpt-5.6-terra",
        tier="medium",
        reasoning_effort="high",
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["--help"],
        ["build", "--help"],
        ["status", "--help"],
        ["resume", "--help"],
        ["stop", "--help"],
        ["render", "--help"],
        ["revise", "--help"],
        ["validate", "--help"],
    ],
)
def test_root_and_subcommand_help_is_human_readable(
    argv: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(argv) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out.startswith("usage: alc-companion")
    assert "ac.command_result.v2" not in captured.out


def test_help_has_no_obsolete_json_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status", "--help"]) == 0
    output = capsys.readouterr().out
    assert "--json" not in output


def test_only_document_access_commands_accept_a_document_cache_root(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in ("build", "resume"):
        assert main([command, "--help"]) == 0
        assert "--document-cache-root" in capsys.readouterr().out
    for command in ("render", "revise", "validate"):
        assert main([command, "--help"]) == 0
        assert "--document-cache-root" not in capsys.readouterr().out


def test_build_and_resume_expose_explicit_host_authority(
    capsys: pytest.CaptureFixture[str],
) -> None:
    for command in ("build", "resume"):
        assert main([command, "--help"]) == 0
        assert "--host-authority" in capsys.readouterr().out


def test_build_exposes_optional_cross_chapter_editorial_review(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["build", "--help"]) == 0
    assert "--cross-chapter-editorial-review" in capsys.readouterr().out


def test_build_exposes_independent_model_and_effort_controls(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["build", "--help"]) == 0
    output = capsys.readouterr().out
    assert "--model MODEL" in output
    assert "--effort {low,medium,high,xhigh}" in output


def test_build_accepts_an_explicit_html_source_manifest(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["build", "--help"]) == 0
    assert "--html-source-manifest" in capsys.readouterr().out


def test_build_requires_explicit_new_lineage_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["build", "--help"]) == 0
    assert "--new-lineage" in capsys.readouterr().out


def test_usage_error_points_to_contextual_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["status"]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    lines = captured.out.splitlines()
    assert len(lines) == 1
    result = json.loads(lines[0])
    assert result["error"]["code"] == "invalid_request"
    assert result["error"]["details"] == {
        "help_command": "alc-companion status --help"
    }


def test_missing_local_build_source_returns_typed_error(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "build",
            str(tmp_path / "missing.md"),
            "--project-dir",
            str(tmp_path / "project"),
            "--user-intent",
            "Explain the source.",
            "--host-authority",
            "unknown",
        ]
    )

    assert code == 1
    result = json.loads(capsys.readouterr().out)
    assert result["error"]["code"] == "source_not_found"
    assert "existing local file" in result["error"]["message"]
