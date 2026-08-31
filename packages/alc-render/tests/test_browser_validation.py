from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from alc_render import HTMLRenderError, validate_reader_in_browser
from alc_render import browser_validation


def _html(path: Path) -> Path:
    path.write_text("<html><body>reader</body></html>", encoding="utf-8")
    return path


def _report(**overrides: object) -> dict[str, object]:
    values = {
        "ready": "true",
        "errors": [],
        "omitted": 0,
        "mathErrors": 0,
        "missingFragments": 0,
        "failedImages": 0,
        "legacyBibliographyLinks": 0,
        "legacyStructuralLinks": 0,
        "invalidTableRegions": 0,
        "invalidListPathCards": 0,
        "missingReferenceTargets": 0,
        "invalidFigurePanels": 0,
        "invalidParallelTableAlignment": 0,
        "invalidFrontMatterEntries": 0,
        "invalidSourceNotes": 0,
        "leakedSourceNoteTranslations": 0,
    }
    values.update(overrides)
    return values


def test_browser_validation_discovers_system_browser_and_forces_reader_checks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        browser_validation.shutil,
        "which",
        lambda value: "/usr/bin/chromium" if value == "chromium" else None,
    )

    calls: list[tuple[str, Path, int]] = []

    def reader_report(
        executable: str, path: Path, timeout_seconds: int
    ) -> tuple[dict[str, object], tuple[str, ...]]:
        calls.append((executable, path, timeout_seconds))
        return _report(), ()

    monkeypatch.setattr(browser_validation, "_reader_report", reader_report)

    result = validate_reader_in_browser(_html(tmp_path / "reader.html"), timeout_seconds=12)

    assert result.executable == "/usr/bin/chromium"
    assert result.timeout_seconds == 12
    assert calls == [("/usr/bin/chromium", tmp_path / "reader.html", 12)]
    assert "window.dispatchEvent(new Event(\"beforeprint\"))" in browser_validation._READER_REPORT_EXPRESSION
    assert ".katex-error, .math-error" in browser_validation._READER_REPORT_EXPRESSION
    assert "failedImages" in browser_validation._READER_REPORT_EXPRESSION
    assert "alcSelectedRevisionCount" in browser_validation._READER_REPORT_EXPRESSION
    assert "image.decode()" in browser_validation._READER_REPORT_EXPRESSION
    assert 'image.loading = "eager"' in browser_validation._READER_REPORT_EXPRESSION
    assert "alc-render-chunk:not(.is-rendered)" in browser_validation._READER_REPORT_EXPRESSION
    assert "legacyBibliographyLinks" in browser_validation._READER_REPORT_EXPRESSION
    assert "legacyStructuralLinks" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidTableRegions" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidListPathCards" in browser_validation._READER_REPORT_EXPRESSION
    assert "missingReferenceTargets" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidFigurePanels" in browser_validation._READER_REPORT_EXPRESSION
    assert "renderedGroups.length !== 2" not in browser_validation._READER_REPORT_EXPRESSION
    assert "figurePresentations" in browser_validation._READER_REPORT_EXPRESSION
    assert "panelRow.dataset.authoredColumnCount" in browser_validation._READER_REPORT_EXPRESSION
    assert "layout.row_sources[index]" in browser_validation._READER_REPORT_EXPRESSION
    assert "responsiveWrapProfile" in browser_validation._READER_REPORT_EXPRESSION
    assert "latexml_ar5iv_flex_size_2" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidParallelTableAlignment" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidFrontMatterEntries" in browser_validation._READER_REPORT_EXPRESSION
    assert "invalidSourceNotes" in browser_validation._READER_REPORT_EXPRESSION
    assert "candidate.getAttribute(\"href\") === \"#\" + row.id" in (
        browser_validation._READER_REPORT_EXPRESSION
    )
    assert "const token = String(note.note_id).replace" not in (
        browser_validation._READER_REPORT_EXPRESSION
    )
    assert "leakedSourceNoteTranslations" in browser_validation._READER_REPORT_EXPRESSION
    assert "^#bib[.]bib[1-9][0-9]*$" in browser_validation._READER_REPORT_EXPRESSION
    assert "Date.now() + 120000" in browser_validation._reader_report_expression(120)
    assert "55000" not in browser_validation._reader_report_expression(120)


@pytest.mark.parametrize(
    ("report", "message"),
    (
        (_report(ready="error"), "initialization did not complete"),
        (_report(errors=["boom"]), "browser reader raised: boom"),
        (_report(omitted=2), "2 unhydrated reader chunks"),
        (_report(mathErrors=3), "3 math rendering errors"),
        (_report(failedImages=1), "1 failed reader images"),
        (_report(missingFragments=2), "2 missing selected fragments"),
        (
            _report(legacyBibliographyLinks=2),
            "2 unresolved legacy bibliography links",
        ),
        (
            _report(legacyStructuralLinks=3),
            "3 unresolved legacy structural links",
        ),
        (
            _report(invalidTableRegions=2),
            "2 invalid responsive table regions",
        ),
        (
            _report(invalidListPathCards=2),
            "2 invalid list-path cards",
        ),
        (
            _report(missingReferenceTargets=2),
            "2 missing bibliography targets",
        ),
        (
            _report(invalidFigurePanels=2),
            "2 invalid Figure panel groups",
        ),
        (
            _report(invalidParallelTableAlignment=2),
            "2 misaligned parallel Tables",
        ),
        (
            _report(invalidFrontMatterEntries=2),
            "2 invalid source front-matter entries",
        ),
        (
            _report(invalidSourceNotes=2),
            "2 invalid source notes",
        ),
        (
            _report(leakedSourceNoteTranslations=2),
            "2 source-note translations in ordinary lanes",
        ),
    ),
)
def test_browser_validation_reports_reader_runtime_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    report: dict[str, object],
    message: str,
) -> None:
    monkeypatch.setattr(browser_validation, "_browser_executable", lambda _value: "browser")
    monkeypatch.setattr(
        browser_validation,
        "_reader_report",
        lambda *_args: (report, ()),
    )

    with pytest.raises(HTMLRenderError, match=message):
        validate_reader_in_browser(_html(tmp_path / "reader.html"))


def test_browser_validation_requires_available_executable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(browser_validation.shutil, "which", lambda _value: None)
    with pytest.raises(HTMLRenderError, match="requires a local Chromium"):
        browser_validation._browser_executable(None)


def test_browser_validation_maps_browser_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_validation, "_browser_executable", lambda _value: "browser")
    monkeypatch.setattr(
        browser_validation,
        "_reader_report",
        lambda *_args: (_ for _ in ()).throw(HTMLRenderError("browser validation timed out after 60s")),
    )

    with pytest.raises(HTMLRenderError, match="timed out after 60s"):
        validate_reader_in_browser(_html(tmp_path / "reader.html"))


def test_browser_page_selection_waits_for_requested_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = iter(
        [
            [
                {
                    "type": "page",
                    "url": "chrome://newtab/",
                    "webSocketDebuggerUrl": "ws://wrong",
                }
            ],
            [
                {
                    "type": "page",
                    "url": "chrome://newtab/",
                    "webSocketDebuggerUrl": "ws://wrong",
                },
                {
                    "type": "page",
                    "url": "file:///reader.html",
                    "webSocketDebuggerUrl": "ws://right",
                },
            ],
        ]
    )

    class _Response:
        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(next(responses)).encode("utf-8")

    monkeypatch.setattr(
        browser_validation,
        "urlopen",
        lambda *_args, **_kwargs: _Response(),
    )
    monkeypatch.setattr(
        browser_validation.time, "sleep", lambda _seconds: None
    )

    assert browser_validation._page_websocket_url(
        9222, time.monotonic() + 1, "file:///reader.html"
    ) == "ws://right"
