from __future__ import annotations

from pathlib import Path


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_direct_html_routing_stays_skill_owned_and_uses_one_bundle_contract() -> None:
    skill = (
        _REPOSITORY_ROOT / "plugins" / "alc" / "skills" / "alc" / "SKILL.md"
    ).read_text(encoding="utf-8")
    workflow = (
        _REPOSITORY_ROOT
        / "plugins"
        / "alc"
        / "skills"
        / "alc"
        / "workflows"
        / "companion.md"
    ).read_text(encoding="utf-8")
    manual = (
        _REPOSITORY_ROOT
        / "plugins"
        / "alc"
        / "skills"
        / "alc"
        / "manuals"
        / "alc-companion.md"
    ).read_text(encoding="utf-8")
    readme = (
        _REPOSITORY_ROOT / "packages" / "alc-companion" / "README.md"
    ).read_text(encoding="utf-8")
    arc_distribution = "-".join(("arc", "paper"))

    assert "`ac-document acquire-html-bundle`" in skill
    assert "`ac.document.html_source_bundle.v1`" in skill
    assert "ac-document acquire-html-bundle" in workflow
    assert "--output-dir <bundle-dir>" in workflow
    assert "--html-source-manifest" in workflow
    assert f"{arc_distribution} export-arxiv-html-acquisition <paper-id>" in skill
    assert f"<arc-skill-dir>/scripts/arc-runtime {arc_distribution}" in skill
    assert f"{arc_distribution} export-arxiv-html-acquisition --help" in skill
    assert f"{arc_distribution} export-arxiv-html-acquisition <paper-id>" in workflow
    assert f"{arc_distribution} export-arxiv-html-acquisition <paper-id>" in manual
    assert f"<arc-skill-dir>/scripts/arc-runtime {arc_distribution}" in manual
    assert "https://arxiv.org/html/<id>[vN]" in skill
    assert "An explicit ar5iv URL" in skill
    assert "other HTTPS HTML URL go to generic ACF" in skill
    assert "scripts/arc-runtime doctor" in skill
    assert "`ready:true`" in skill
    assert "Never call `setup`" in skill
    assert "original URL unchanged" in skill
    assert "--html-source-manifest bundle/manifest.json" in readme
    assert "scripts/arc-runtime doctor" in readme
    assert "An ar5iv URL and every other HTTPS HTML URL use generic ACF" in readme
    assert "does not import, install, or invoke ARC" in skill


def test_companion_package_declares_no_arc_runtime_dependency() -> None:
    package = (
        _REPOSITORY_ROOT / "packages" / "alc-companion" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    source_root = _REPOSITORY_ROOT / "packages" / "alc-companion" / "src"
    arc_distribution = "-".join(("arc", "paper"))
    arc_module = "_".join(("arc", "paper"))

    assert arc_distribution not in package
    assert arc_module not in package
    assert not any(
        f"import {arc_module}" in path.read_text(encoding="utf-8")
        or f"from {arc_module}" in path.read_text(encoding="utf-8")
        for path in source_root.rglob("*.py")
    )
