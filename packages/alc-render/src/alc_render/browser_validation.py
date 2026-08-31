"""Optional system-browser checks for a standalone ALC reader."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import time
from typing import Any, Final
from urllib.parse import urlsplit
from urllib.request import urlopen

from .html import HTMLRenderError


_BROWSER_CANDIDATES: Final = (
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "chrome",
)


@dataclass(frozen=True)
class BrowserValidation:
    """Successful optional browser validation details."""

    executable: str
    timeout_seconds: int


def validate_reader_in_browser(
    html_path: str | Path,
    *,
    browser_executable: str | None = None,
    timeout_seconds: int = 60,
) -> BrowserValidation:
    """Check one standalone reader with a locally installed Chromium browser."""

    if timeout_seconds <= 0:
        raise HTMLRenderError("browser validation timeout must be positive")
    source = Path(html_path).resolve()
    if not source.is_file():
        raise HTMLRenderError("standalone HTML is unreadable")
    executable = _browser_executable(browser_executable)
    report, exceptions = _reader_report(executable, source, timeout_seconds)
    _raise_for_report(report, exceptions)
    return BrowserValidation(executable=executable, timeout_seconds=timeout_seconds)


def _browser_executable(requested: str | None) -> str:
    if requested:
        resolved = shutil.which(requested)
        if resolved is None and Path(requested).is_file():
            resolved = requested
        if resolved is None:
            raise HTMLRenderError(
                f"browser executable is unavailable: {requested}"
            )
        return resolved
    for candidate in _BROWSER_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved is not None:
            return resolved
    raise HTMLRenderError(
        "browser validation requires a local Chromium-family executable"
    )


def _reader_report(
    executable: str, html_path: Path, timeout_seconds: int
) -> tuple[dict[str, object], tuple[str, ...]]:
    deadline = time.monotonic() + timeout_seconds
    with tempfile.TemporaryDirectory(prefix=".alc-render-browser-") as raw:
        profile = Path(raw) / "profile"
        command = [
            executable,
            "--headless",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={profile}",
            html_path.as_uri(),
        ]
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise HTMLRenderError("browser validation could not start") from exc
        try:
            port = _wait_for_debug_port(profile / "DevToolsActivePort", deadline)
            websocket_url = _page_websocket_url(
                port, deadline, html_path.as_uri()
            )
            with _CdpSocket(websocket_url, deadline) as cdp:
                cdp.call("Runtime.enable", {})
                response = cdp.call(
                    "Runtime.evaluate",
                    {
                        "expression": _reader_report_expression(
                            _remaining(deadline)
                        ),
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                )
                result = response.get("result", {})
                value = result.get("result", {}).get("value")
                if not isinstance(value, dict):
                    detail = result.get("exceptionDetails")
                    raise HTMLRenderError(
                        "browser validation could not evaluate reader state"
                        + (f": {detail}" if detail else "")
                    )
                return dict(value), tuple(cdp.exceptions)
        except TimeoutError as exc:
            raise HTMLRenderError(
                f"browser validation timed out after {timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise HTMLRenderError("browser validation could not start") from exc
        finally:
            _stop_browser(process)


def _wait_for_debug_port(path: Path, deadline: float) -> int:
    while time.monotonic() < deadline:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
            if lines:
                return int(lines[0])
        except (OSError, ValueError):
            pass
        time.sleep(0.05)
    raise TimeoutError("DevTools port was not ready")


def _page_websocket_url(
    port: int, deadline: float, expected_url: str
) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=_remaining(deadline)) as response:
                pages = json.loads(response.read().decode("utf-8"))
            for page in pages:
                if (
                    page.get("type") == "page"
                    and page.get("url") == expected_url
                    and page.get("webSocketDebuggerUrl")
                ):
                    return str(page["webSocketDebuggerUrl"])
        except (OSError, ValueError, TimeoutError):
            pass
        time.sleep(0.05)
    raise TimeoutError("browser page was not ready")


class _CdpSocket:
    def __init__(self, websocket_url: str, deadline: float) -> None:
        self._deadline = deadline
        self._socket = _websocket_connect(websocket_url, deadline)
        self._next_id = 1
        self.exceptions: list[str] = []

    def __enter__(self) -> _CdpSocket:
        return self

    def __exit__(self, *_args: object) -> None:
        self._socket.close()

    def call(self, method: str, params: dict[str, object]) -> dict[str, Any]:
        identifier = self._next_id
        self._next_id += 1
        _websocket_send(self._socket, json.dumps({
            "id": identifier, "method": method, "params": params
        }))
        while True:
            payload = _websocket_receive(self._socket, self._deadline)
            message = json.loads(payload)
            if message.get("method") == "Runtime.exceptionThrown":
                details = message.get("params", {}).get("exceptionDetails", {})
                text = (
                    details.get("exception", {}).get("description")
                    or details.get("text")
                )
                self.exceptions.append(str(text or "runtime exception"))
            if message.get("id") == identifier:
                return message


def _websocket_connect(url: str, deadline: float) -> socket.socket:
    parsed = urlsplit(url)
    if parsed.scheme != "ws" or not parsed.hostname or not parsed.port:
        raise OSError("browser supplied an invalid DevTools socket")
    connection = socket.create_connection(
        (parsed.hostname, parsed.port), timeout=_remaining(deadline)
    )
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    target = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    request = (
        f"GET {target} HTTP/1.1\r\n"
        f"Host: {parsed.hostname}:{parsed.port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    ).encode("ascii")
    connection.sendall(request)
    response = _read_until(connection, b"\r\n\r\n", deadline)
    if not response.startswith(b"HTTP/1.1 101"):
        connection.close()
        raise OSError("browser rejected DevTools socket")
    return connection


def _websocket_send(connection: socket.socket, value: str) -> None:
    payload = value.encode("utf-8")
    mask = os.urandom(4)
    size = len(payload)
    if size < 126:
        header = bytes((0x81, 0x80 | size))
    elif size < 65536:
        header = bytes((0x81, 0x80 | 126)) + struct.pack("!H", size)
    else:
        header = bytes((0x81, 0x80 | 127)) + struct.pack("!Q", size)
    masked = bytes(item ^ mask[index % 4] for index, item in enumerate(payload))
    connection.sendall(header + mask + masked)


def _websocket_receive(connection: socket.socket, deadline: float) -> str:
    header = _read_exact(connection, 2, deadline)
    opcode = header[0] & 0x0F
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(connection, 2, deadline))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(connection, 8, deadline))[0]
    masked = bool(header[1] & 0x80)
    mask = _read_exact(connection, 4, deadline) if masked else b""
    payload = _read_exact(connection, length, deadline)
    if masked:
        payload = bytes(item ^ mask[index % 4] for index, item in enumerate(payload))
    if opcode == 8:
        raise OSError("browser DevTools socket closed")
    if opcode != 1:
        return _websocket_receive(connection, deadline)
    return payload.decode("utf-8")


def _read_exact(connection: socket.socket, size: int, deadline: float) -> bytes:
    values = bytearray()
    while len(values) < size:
        connection.settimeout(_remaining(deadline))
        part = connection.recv(size - len(values))
        if not part:
            raise OSError("browser DevTools socket closed")
        values.extend(part)
    return bytes(values)


def _read_until(connection: socket.socket, marker: bytes, deadline: float) -> bytes:
    values = bytearray()
    while marker not in values:
        connection.settimeout(_remaining(deadline))
        part = connection.recv(1024)
        if not part:
            raise OSError("browser DevTools socket closed")
        values.extend(part)
    return bytes(values)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("browser validation timed out")
    return remaining


def _stop_browser(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _raise_for_report(
    report: dict[str, object], exceptions: tuple[str, ...]
) -> None:
    ready = report.get("ready")
    errors = report.get("errors")
    omitted = report.get("omitted")
    math_errors = report.get("mathErrors")
    failed_images = report.get("failedImages")
    missing_fragments = report.get("missingFragments")
    legacy_bibliography_links = report.get("legacyBibliographyLinks")
    legacy_structural_links = report.get("legacyStructuralLinks")
    invalid_table_regions = report.get("invalidTableRegions")
    invalid_list_path_cards = report.get("invalidListPathCards")
    missing_reference_targets = report.get("missingReferenceTargets")
    invalid_figure_panels = report.get("invalidFigurePanels")
    invalid_parallel_table_alignment = report.get(
        "invalidParallelTableAlignment"
    )
    invalid_front_matter = report.get("invalidFrontMatterEntries")
    invalid_source_notes = report.get("invalidSourceNotes")
    leaked_source_note_translations = report.get(
        "leakedSourceNoteTranslations"
    )
    if ready != "true":
        raise HTMLRenderError(f"browser reader initialization did not complete: {ready}")
    if exceptions:
        raise HTMLRenderError("browser reader raised: " + exceptions[0])
    if isinstance(errors, list) and errors:
        raise HTMLRenderError("browser reader raised: " + str(errors[0]))
    for count, description in (
        (omitted, "unhydrated reader chunks"),
        (math_errors, "math rendering errors"),
        (failed_images, "failed reader images"),
        (missing_fragments, "missing selected fragments"),
        (legacy_bibliography_links, "unresolved legacy bibliography links"),
        (legacy_structural_links, "unresolved legacy structural links"),
        (invalid_table_regions, "invalid responsive table regions"),
        (invalid_list_path_cards, "invalid list-path cards"),
        (missing_reference_targets, "missing bibliography targets"),
        (invalid_figure_panels, "invalid Figure panel groups"),
        (invalid_parallel_table_alignment, "misaligned parallel Tables"),
        (invalid_front_matter, "invalid source front-matter entries"),
        (invalid_source_notes, "invalid source notes"),
        (
            leaked_source_note_translations,
            "source-note translations in ordinary lanes",
        ),
    ):
        if not isinstance(count, int):
            raise HTMLRenderError("browser validation report is malformed")
        if count:
            raise HTMLRenderError(f"browser reader has {count} {description}")


_READER_REPORT_EXPRESSION: Final = """(async () => {
  const errors = [];
  const deadline = Date.now() + __ALC_BROWSER_TIMEOUT_MS__;
  while (
    (!document.body || !document.body.dataset.alcRenderReady ||
      document.body.dataset.alcRenderReady === "loading") &&
    Date.now() < deadline
  ) {
    await new Promise(resolve => setTimeout(resolve, 25));
  }
  const ready = document.body.dataset.alcRenderReady || "missing";
  if (ready === "true") {
    window.dispatchEvent(new Event("beforeprint"));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await Promise.all(Array.from(document.images).map(async image => {
      image.loading = "eager";
      if (typeof image.decode !== "function") return;
      try {
        await Promise.race([
          image.decode(),
          new Promise(resolve => setTimeout(resolve, 5000))
        ]);
      } catch (_error) {
        // The failedImages check below reports decode failures.
      }
    }));
  }
  return {
    ready,
    errors,
    omitted: document.querySelectorAll(
      ".alc-render-chunk:not(.is-rendered), .alc-render-chunk[aria-busy=\\"true\\"]"
    ).length,
    mathErrors: document.querySelectorAll(".katex-error, .math-error").length,
    missingFragments: (() => {
      try {
        const payload = JSON.parse(
          document.getElementById("alc-render-payload").textContent || "{}"
        );
        const expected = new Set(payload.selected_revision_digests || []);
        const loaded = Number(document.body.dataset.alcSelectedRevisionCount);
        return Number.isInteger(loaded) ? Math.max(0, expected.size - loaded) : -1;
      } catch (_error) {
        return -1;
      }
    })(),
    failedImages: Array.from(document.images).filter(
      image => !image.complete || image.naturalWidth === 0
    ).length,
    legacyBibliographyLinks: Array.from(document.querySelectorAll(
      'a[href^="#bib.bib"]'
    )).filter(
      link => /^#bib[.]bib[1-9][0-9]*$/.test(
        link.getAttribute("href") || ""
      )
    ).length,
    legacyStructuralLinks: Array.from(document.querySelectorAll(
      'a[href^="#"]'
    )).filter(link => {
      const href = link.getAttribute("href") || "";
      try {
        return /^S[0-9]+(?:[.][A-Za-z][A-Za-z0-9_-]*)*$/.test(
          decodeURIComponent(href.slice(1))
        );
      } catch (_error) {
        return false;
      }
    }).length,
    invalidTableRegions: Array.from(document.querySelectorAll("table")).filter(
      table => {
        const region = table.parentElement;
        if (!region || !region.classList.contains("alc-table-scroll")) {
          return true;
        }
        const overflowing = region.scrollWidth > region.clientWidth + 1;
        if (overflowing) {
          return region.getAttribute("tabindex") !== "0" ||
            region.getAttribute("role") !== "region" ||
            !(region.getAttribute("aria-label") || "").trim();
        }
        return region.hasAttribute("tabindex") ||
          region.hasAttribute("role") || region.hasAttribute("aria-label");
      }
    ).length,
    invalidParallelTableAlignment: Array.from(document.querySelectorAll(
      '.alc-source-row[data-block-kind="table"]'
    )).filter(row => {
      const source = row.querySelector(
        ":scope > .alc-lanes > .alc-source-card"
      );
      const target = row.querySelector(
        ':scope > .alc-lanes > .alc-fragment[data-role="translation"]'
      );
      const sourceCaption = source && source.querySelector(
        '.alc-table-caption[data-caption-placement="before_content"]'
      );
      const targetCaption = target && target.querySelector(
        '.alc-table-caption[data-caption-placement="before_content"]'
      );
      const sourceTable = source && source.querySelector(".alc-table-scroll");
      const targetTable = target && target.querySelector(".alc-table-scroll");
      if (!sourceCaption || !targetCaption || !sourceTable || !targetTable) {
        return false;
      }
      const sourceCardRect = source.getBoundingClientRect();
      const targetCardRect = target.getBoundingClientRect();
      if (Math.abs(sourceCardRect.top - targetCardRect.top) > 1) return false;
      const sourceTableRect = sourceTable.getBoundingClientRect();
      const targetTableRect = targetTable.getBoundingClientRect();
      return Math.abs(sourceTableRect.top - targetTableRect.top) > 1 ||
        Math.abs(sourceTableRect.height - targetTableRect.height) > 1;
    }).length,
    invalidListPathCards: Array.from(document.querySelectorAll(
      ".alc-source-card.alc-list-owned-card"
    )).filter(card => {
      const rail = card.querySelector(":scope > .alc-list-marker-rail");
      const markers = rail ? Array.from(rail.children) : [];
      const depth = Number(card.style.getPropertyValue("--alc-list-depth"));
      const continuation = card.dataset.listContinuation === "true";
      const deepest = markers[markers.length - 1];
      return !Number.isInteger(depth) || depth < 1 || markers.length !== depth ||
        !deepest || (continuation ?
          !deepest.classList.contains("is-continuation") ||
            Boolean((deepest.textContent || "").trim()) :
          deepest.classList.contains("is-continuation") ||
            !(deepest.textContent || "").trim());
    }).length,
    missingReferenceTargets: (() => {
      try {
        const payload = JSON.parse(
          document.getElementById("alc-render-payload").textContent || "{}"
        );
        return (payload.legacy_bibliography_targets || []).filter(item =>
          !document.getElementById(
            "source-reference-" + String(item.block_id).replace(
              /[^A-Za-z0-9_-]+/g, "-"
            ) + "-" + String(Number(item.item_index) + 1)
          )
        ).length;
      } catch (_error) {
        return -1;
      }
    })(),
    invalidFigurePanels: (() => {
      try {
        const payload = JSON.parse(
          document.getElementById("alc-render-payload").textContent || "{}"
        );
        const metadata = payload.publication.source_document.metadata || {};
        const manifest = metadata.source_target_manifest || {};
        const presentation = metadata.source_presentation || {};
        const figurePresentations = new Map(
          Array.isArray(presentation.figures) ? presentation.figures.map(
            item => [item.block_id, item]
          ) : []
        );
        if (!Array.isArray(manifest.targets)) return 0;
        return manifest.targets.filter(target =>
          target && target.kind === "figure" &&
          Array.isArray(target.panels) && target.panels.length
        ).filter(target => {
          const row = document.getElementById(
            "block-" + String(target.block_id).replace(/[^A-Za-z0-9_-]+/g, "-")
          );
          const expected = target.panels.filter(
            panel => panel.status === "available"
          );
          const figurePresentation = figurePresentations.get(target.block_id);
          const authoredLayout = figurePresentation &&
            figurePresentation.layout &&
            figurePresentation.layout.kind !== "neutral";
          const renderedGroups = row ? Array.from(row.querySelectorAll(
            ":scope > .alc-lanes > * .alc-figure-panels"
          )) : [];
          if (authoredLayout) {
            const layout = figurePresentation.layout;
            if (renderedGroups.some(group => {
              const panelRows = Array.from(group.querySelectorAll(
                ":scope > .alc-figure-panel-row"
              ));
              return group.dataset.layoutKind !== layout.kind ||
                group.dataset.layoutColumns !== String(layout.column_count) ||
                group.dataset.layoutRows !== String(layout.row_count) ||
                group.dataset.columnSource !== (layout.column_source || "") ||
                panelRows.length !== layout.rows.length ||
                panelRows.some((panelRow, index) => {
                  const rowSource = layout.row_sources[index];
                  const responsiveWrapProfile = rowSource ===
                    "class:ltx_flex_size_2" ?
                    "latexml_ar5iv_flex_size_2" : "";
                  return panelRow.dataset.authoredColumnCount !== String(
                    layout.rows[index].length
                  ) || panelRow.dataset.columnSource !== rowSource ||
                    (panelRow.dataset.responsiveWrapProfile || "") !==
                      responsiveWrapProfile;
                });
            })) return true;
          }
          const images = row ? Array.from(row.querySelectorAll(
            ".alc-source-card .alc-figure-panel"
          )) : [];
          return images.length !== expected.length || images.some(
            (image, index) =>
              image.dataset.panelIndex !== String(expected[index].panel_index) ||
              image.dataset.artifactDigest !== expected[index].asset_digest
          );
        }).length;
      } catch (_error) {
        return -1;
      }
    })(),
    invalidFrontMatterEntries: (() => {
      try {
        const payload = JSON.parse(
          document.getElementById("alc-render-payload").textContent || "{}"
        );
        const metadata = payload.publication.source_document.metadata || {};
        const front = metadata.source_front_matter;
        if (!front) return 0;
        if (!Array.isArray(front.entries)) return -1;
        const rendered = Array.from(document.querySelectorAll(
          ".alc-source-front-matter"
        ));
        return front.entries.filter(entry => {
          const node = rendered.find(item =>
            item.dataset.frontMatterId === entry.front_matter_id
          );
          if (!node) return true;
          if (entry.creator_flow) {
            const authorsById = new Map((entry.authors || []).map(
              author => [author.author_id, author]
            ));
            const affiliationsById = new Map((entry.affiliations || []).map(
              affiliation => [affiliation.affiliation_id, affiliation]
            ));
            const expectedCreators = entry.creator_flow.creators || [];
            const creators = Array.from(node.querySelectorAll(
              ".alc-source-creator"
            ));
            if (creators.length !== expectedCreators.length) return true;
            return creators.some((creator, index) => {
              const expectedCreator = expectedCreators[index] || {};
              const expectedAuthor = authorsById.get(
                expectedCreator.author_id
              ) || {};
              const expectedSlots = expectedCreator.slots || [];
              const expectedAffiliations = expectedSlots.filter(
                slot => slot.kind === "affiliation"
              ).map(slot => affiliationsById.get(slot.affiliation_id) || {});
              const actualAffiliations = Array.from(creator.querySelectorAll(
                ".alc-source-creator-slot-affiliation"
              ));
              const expectedContacts = expectedSlots.filter(
                slot => slot.kind === "contact"
              ).map(slot => (expectedAuthor.contacts || [])[slot.contact_index]);
              const actualContacts = Array.from(creator.querySelectorAll(
                ".alc-source-author-contact"
              ));
              const markers = Array.from(creator.querySelectorAll(
                ".alc-source-author-marker"
              )).map(item => item.textContent);
              return creator.dataset.creatorId !== expectedCreator.creator_id ||
                markers.join("\u0000") !==
                  (expectedAuthor.markers || []).join("\u0000") ||
                actualContacts.length !== expectedContacts.length ||
                actualContacts.some((item, contactIndex) =>
                  item.textContent !== expectedContacts[contactIndex]?.value
                ) ||
                actualAffiliations.length !== expectedAffiliations.length ||
                actualAffiliations.some((item, affiliationIndex) => {
                  const expected = expectedAffiliations[affiliationIndex];
                  return item.querySelector(".alc-source-affiliation-marker")
                      ?.textContent !== expected.marker ||
                    item.querySelector(".alc-source-affiliation")
                      ?.textContent !== expected.text;
                });
            });
          }
          const authors = Array.from(node.querySelectorAll(
            ".alc-source-author"
          ));
          const affiliations = Array.from(node.querySelectorAll(
            ".alc-source-affiliation-item"
          ));
          return authors.length !== (entry.authors || []).length ||
            authors.some((author, index) => {
              const expected = entry.authors[index] || {};
              const markers = Array.from(author.querySelectorAll(
                ".alc-source-author-marker"
              )).map(item => item.textContent);
              return markers.join("\u0000") !==
                (expected.markers || []).join("\u0000");
            }) || affiliations.length !== (entry.affiliations || []).length ||
            affiliations.some((item, index) => {
              const expected = entry.affiliations[index] || {};
              return item.querySelector(".alc-source-affiliation-marker")
                  ?.textContent !== expected.marker ||
                item.querySelector(".alc-source-affiliation")
                  ?.textContent !== expected.text;
            });
        }).length;
      } catch (_error) {
        return -1;
      }
    })(),
    invalidSourceNotes: (() => {
      try {
        const payload = JSON.parse(
          document.getElementById("alc-render-payload").textContent || "{}"
        );
        const metadata = payload.publication.source_document.metadata || {};
        const sourceNotes = metadata.source_notes;
        if (!sourceNotes) return 0;
        if (!Array.isArray(sourceNotes.notes)) return -1;
        return sourceNotes.notes.filter(note => {
          const row = Array.from(document.querySelectorAll(
            ".alc-source-note-row"
          )).find(candidate => candidate.dataset.sourceNoteId === note.note_id);
          const referenceLink = row ? Array.from(document.querySelectorAll(
            ".alc-source-note-ref:not(.alc-translation-note-ref) > a"
          )).find(candidate =>
            candidate.getAttribute("href") === "#" + row.id
          ) : null;
          const reference = referenceLink ?
            referenceLink.closest(".alc-source-note-ref") : null;
          return !row || !reference ||
            !(row.querySelector(".alc-source-note-content") || {}).textContent ||
            (reference.textContent || "").trim() !== String(note.marker);
        }).length;
      } catch (_error) {
        return -1;
      }
    })(),
    leakedSourceNoteTranslations: (() => {
      try {
        const fragmentIds = new Set();
        Array.from(document.querySelectorAll(
          'script[id^="alc-render-payload-chunk-"]'
        )).forEach(script => {
          const chunk = JSON.parse(script.textContent || "{}");
          (chunk.revisions || []).forEach(raw => {
            const revision = raw.metadata || raw;
            const provenance = revision.provenance || {};
            const contract = provenance.source_note_translation;
            if (
              contract &&
              contract.schema_version ===
                "alc.render.source_note_translation.v1" &&
              typeof contract.note_id === "string" &&
              contract.note_id.trim() &&
              typeof revision.fragment_id === "string"
            ) fragmentIds.add(revision.fragment_id);
          });
        });
        return Array.from(document.querySelectorAll(
          ".alc-fragment[data-fragment-id]"
        )).filter(fragment =>
          fragmentIds.has(fragment.dataset.fragmentId || "") &&
          !fragment.classList.contains("alc-source-note-translation")
        ).length;
      } catch (_error) {
        return -1;
      }
    })()
  };
})()"""


def _reader_report_expression(timeout_seconds: float) -> str:
    timeout_ms = max(1, int(timeout_seconds * 1000))
    return _READER_REPORT_EXPRESSION.replace(
        "__ALC_BROWSER_TIMEOUT_MS__", str(timeout_ms)
    )


__all__ = ["BrowserValidation", "validate_reader_in_browser"]
