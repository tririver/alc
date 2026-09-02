from __future__ import annotations

import hashlib
import json
import re
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / "packages"
PLUGIN = ROOT / "plugins/alc"
SCRIPTS = PLUGIN / "skills/alc/scripts"
EXPECTED = {
    "alc-companion": {
        "ac-jobs",
        "ac-llm",
        "ac-document",
        "ac-proposer-reviewer",
        "alc-render",
        "alc-translate",
    },
    "alc-ocr-proofread": {"ac-jobs", "ac-llm", "ac-document"},
    "alc-render": {"ac-document"},
    "alc-translate": {"ac-jobs", "ac-llm", "ac-document", "alc-render"},
}
VERSION = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
ALC_MAJOR = int(VERSION.split(".")[0])


def _project(package: str) -> dict[str, object]:
    return tomllib.loads(
        (PACKAGES / package / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]


def test_package_set_metadata_and_dependency_graph() -> None:
    assert {path.name for path in PACKAGES.iterdir() if path.is_dir()} == set(EXPECTED)
    for package, internal in EXPECTED.items():
        project = _project(package)
        assert project["name"] == package
        assert project["version"] == VERSION
        assert project["authors"] == [{"name": "ALC"}]
        assert project["urls"]["Repository"] == "https://github.com/tririver/alc"
        dependencies = {
            dependency.split(">=", 1)[0]
            for dependency in project.get("dependencies", [])
            if dependency.startswith(("ac-", "alc-"))
        }
        assert dependencies == internal
        for dependency in project.get("dependencies", []):
            if dependency.startswith("alc-"):
                assert dependency.endswith(f">={ALC_MAJOR},<{ALC_MAJOR + 1}")
            elif dependency.startswith("ac-"):
                ac_range = re.search(r">=(\d+)(?:\.\d+\.\d+)?,<(\d+)$", dependency)
                assert ac_range is not None
                assert int(ac_range[2]) == int(ac_range[1]) + 1


def test_companion_requires_html_source_export_floor() -> None:
    assert "ac-document>=2.0.4,<3" in _project("alc-companion")[
        "dependencies"
    ]


def test_learning_packages_have_no_arc_code_dependency() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in PACKAGES.rglob("*")
        if path.is_file() and path.suffix in {".py", ".toml"}
    )
    for stale in ("import arc_", "from arc_", '"arc-', '"arc.', "ARC_"):
        assert stale not in source


def test_plugin_exposes_only_learning_wrappers_and_workflows() -> None:
    wrappers = {path.name for path in (PLUGIN / "bin").iterdir() if path.is_file()}
    assert wrappers == {
        "alc-runtime",
        "alc-render",
        "alc-ocr-proofread",
        "alc-translate",
        "alc-companion",
    }
    workflows = {
        path.name for path in (PLUGIN / "skills/alc/workflows").iterdir() if path.is_file()
    }
    assert workflows == {"companion.md", "ocr-proofread.md"}
    skill = (PLUGIN / "skills/alc/SKILL.md").read_text(encoding="utf-8")
    assert "never make it a Python or runtime dependency" in skill
    assert "install ARC automatically" in skill


def test_companion_skill_declares_codex_host_execution_boundary() -> None:
    workflow = (PLUGIN / "skills/alc/workflows/companion.md").read_text(
        encoding="utf-8"
    )
    manual = (PLUGIN / "skills/alc/manuals/alc-companion.md").read_text(
        encoding="utf-8"
    )
    operating = (PLUGIN / "skills/alc/rules/operating.md").read_text(
        encoding="utf-8"
    )
    workflow_prose = " ".join(workflow.split())
    manual_prose = " ".join(manual.split())
    operating_prose = " ".join(operating.split())

    assert 'sandbox_permissions="require_escalated"' in workflow
    assert "before the first model-backed `build` or `resume`" in workflow_prose
    assert "Do not ask a separate chat confirmation" in workflow_prose
    assert "let the host's configured approval reviewer decide" in workflow_prose
    assert (
        "already authorizes model processing of that source" in workflow_prose
    )
    assert "Do not ask a second chat question" in workflow_prose
    assert "ac-llm doctor --provider auto" in workflow
    assert "`data.provider`" in workflow
    assert "Do not submit `--provider auto`" in workflow_prose
    assert "--provider <resolved-provider>" in workflow
    assert (
        "does not make `--host-authority unrestricted` truthful" in manual_prose
    )
    assert "it cannot grant its own escalation" in manual_prose
    assert "Do not discover this boundary by first launching" in operating_prose
    assert "Do not split that one requested workflow" in operating_prose


def test_runtime_source_lock_uses_full_shas() -> None:
    lock = json.loads((SCRIPTS / "runtime-sources.json").read_text(encoding="utf-8"))
    assert lock["schema_version"] == "ac.runtime_sources.v2"
    assert lock["profile"] == "alc"
    assert {source["id"] for source in lock["sources"]} == {"foundation", "product"}
    for source in lock["sources"]:
        assert re.fullmatch(r"[0-9a-f]{40}", source["commit"])
        assert "version" not in source
    assert lock["environment_defaults"] == {}


def test_generated_foundation_copies_match_manifest() -> None:
    manifest = json.loads((SCRIPTS / "generated-sources.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "ac.generated_sources.v1"
    for relative, metadata in manifest["files"].items():
        path = (SCRIPTS / relative).resolve()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == metadata["sha256"]


def test_release_script_covers_all_packages_and_plugin_manifests() -> None:
    release = (ROOT / "scripts/release-alc.sh").read_text(encoding="utf-8")
    for package in EXPECTED:
        assert f'"{package}"' in release
    assert "plugins/alc/.codex-plugin/plugin.json" in release
    assert "plugins/alc/.claude-plugin/plugin.json" in release
    assert "runtime-sources.json" in release
    assert "check-generated-foundation.py" in release
    assert "check-runtime-constraints.py" in release


def test_public_marketplaces_and_install_instructions_are_complete() -> None:
    codex = json.loads(
        (ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8")
    )
    claude = json.loads(
        (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
    )
    for marketplace in (codex, claude):
        assert marketplace["name"] == "alc"
        assert marketplace["plugins"] == [
            {
                "name": "alc",
                "description": "Agentic Learning Copilot learning workflows.",
                "source": "./plugins/alc",
                "category": "education",
            }
        ]

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "codex plugin marketplace add tririver/alc --ref stable" in readme
    assert "/plugin marketplace add tririver/alc@stable" in readme
    assert "dsh plugin --profile alc add github:tririver/alc" in readme
