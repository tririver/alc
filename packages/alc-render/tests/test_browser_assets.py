from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest


ASSETS = (
    Path(__file__).parents[1]
    / "src"
    / "alc_render"
    / "web_assets"
)


def _text(name: str) -> str:
    return (ASSETS / name).read_text(encoding="utf-8")


def test_reader_javascript_passes_node_syntax_check() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")

    subprocess.run(
        [node, "--check", str(ASSETS / "reader.js")],
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_glossary_uses_latest_entry_and_only_exact_target_ranges() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    instrumented = (
        _text("markdown-it/markdown-it.min.js")
        + "\nglobalThis.window = globalThis;\n"
        + "globalThis.markdownit = module.exports;\n"
        "globalThis.crypto = require('node:crypto').webcrypto;\n"
        + javascript[:startup]
        + """
  globalThis.__alcGlossaryTest = {
      state: state,
      setupMarkdown: setupMarkdown,
    canonicalDigest: canonicalDigest,
    stableStringify: stableStringify,
    glossaryBaseMaterial: glossaryBaseMaterial,
    glossaryRevisionMaterial: glossaryRevisionMaterial,
    encodeGlossaryRevision: encodeGlossaryRevision,
    glossaryRevisionFileName: glossaryRevisionFileName,
    parseGlossaryRevisionFile: parseGlossaryRevisionFile,
    prepareGlossary: prepareGlossary,
    resolveGlossaryAll: resolveGlossaryAll,
    projectGlossaryMarkdown: projectGlossaryMarkdown,
    buildMarkdownPackage: buildMarkdownPackage,
    validGlossarySurfaceAnchors: validGlossarySurfaceAnchors,
    glossaryEntryEditableInState: glossaryEntryEditableInState,
    assertGlossaryBaseCurrent: assertGlossaryBaseCurrent,
    beginGlossaryEdit: beginGlossaryEdit,
    renderGlossaryRow: renderGlossaryRow,
    handleGlossaryEntryClick: handleGlossaryEntryClick,
    handleGlossaryEntryDoubleClick: handleGlossaryEntryDoubleClick,
    activeGlossaryDraftValid: activeGlossaryDraftValid,
    showGlossaryValidationError: showGlossaryValidationError,
    clearGlossaryValidationError: clearGlossaryValidationError,
    installGlossaryInlineSpies: function (calls) {
      replaceGlossaryRow = function (entryId) { calls.replaced.push(entryId); };
      focusGlossaryInlineEditor = function (entryId) { calls.focused.push(entryId); };
      openAdvancedEditor = function () { calls.dialogs += 1; };
    },
    installGlossaryRowSpies: function (calls) {
      element = function (tag, className, text) {
        return new FakeNode(tag, className, text);
      };
      decorateGlossary = function () {};
      renderGlossaryDefinition = function (markdown) {
        return new FakeNode("div", "alc-markdown", markdown);
      };
      labels = function () {
        return {
          glossary: "Glossary",
          listen: "Listen",
          editGlossary: "Edit glossary term"
        };
      };
      appendInlineActions = function (actions) {
        calls.actions += 1;
        actions.appendChild(new FakeNode("button", "alc-inline-save", "Save"));
      };
      updateDraftSaveButtons = function (scope) {
        calls.saveScopes.push(scope);
      };
    },
    installGlossaryActivationSpy: function (calls) {
      beginGlossaryEdit = function (entry, focusField) {
        calls.push(entry.entry_id + ":" + (focusField || "definition"));
      };
    }
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function FakeNode(tag, className, text) {
  this.tagName = String(tag || "div").toUpperCase();
  this.className = className || "";
  this.textContent = text || "";
  this.children = [];
  this.dataset = {};
  this.listeners = {};
  this.attrs = {};
  this.classList = {
    add: (...names) => {
      var values = new Set(this.className.split(/\\s+/).filter(Boolean));
      names.forEach(function (name) { values.add(name); });
      this.className = Array.from(values).join(" ");
    }
  };
}
FakeNode.prototype.appendChild = function (child) {
  this.children.push(child);
  return child;
};
FakeNode.prototype.addEventListener = function (name, listener) {
  this.listeners[name] = this.listeners[name] || [];
  this.listeners[name].push(listener);
};
FakeNode.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
FakeNode.prototype.removeAttribute = function (name) {
  delete this.attrs[name];
};
FakeNode.prototype.focus = function () { this.focused = true; };
var validationNodes = {
  "alc-editor-dialog": new FakeNode("dialog"),
  "alc-editor-error": new FakeNode("p"),
  "alc-editor-title": new FakeNode("input"),
  "alc-storage-status": new FakeNode("p")
};
validationNodes["alc-editor-dialog"].open = false;
validationNodes["alc-editor-error"].hidden = true;
validationNodes["alc-storage-status"].hidden = true;
var inlineValidationControl = new FakeNode("textarea");
globalThis.document = {
  getElementById: function (id) { return validationNodes[id] || null; },
  querySelector: function () { return inlineValidationControl; },
  querySelectorAll: function (selector) {
    return selector === ".alc-glossary-inline-input" ?
      [inlineValidationControl] : [];
  }
};
var helpers = globalThis.__alcGlossaryTest;
var base = {
  entry_id: "term-reader", term: "Reader", translated_term: "读者",
  definition: "旧解释", anchor_ids: ["block-1"], citations: [],
  surface_anchors: [{
    block_id: "block-1", fragment_id: "translation-1",
    fragment_semantic_digest: "d".repeat(64), markdown_start: 0,
    markdown_end: 2, surface: "读者"
  }]
};
(async function () {
  helpers.state.payload = {
    publication: {
      glossary: [base],
      source_document: {blocks: [], metadata: {}},
      labels: {},
      reader_profile: {title: "Glossary QA"},
      bibliography: []
    },
    resources: []
  };
  helpers.state.selectedGlossaryRevisions = new Map([["term-reader", null]]);
  helpers.state.glossaryBaseDigests = new Map([
    ["term-reader", "a".repeat(64)]
  ]);
  var inlineCalls = {replaced: [], focused: [], dialogs: 0};
  helpers.installGlossaryInlineSpies(inlineCalls);
  helpers.beginGlossaryEdit(base);
  assert(
    helpers.state.activeGlossaryDraft &&
      helpers.state.activeGlossaryDraft.entryId === "term-reader" &&
      inlineCalls.replaced.join(",") === "term-reader" &&
      inlineCalls.focused.join(",") === "term-reader" &&
      inlineCalls.dialogs === 0,
    "glossary edit did not start as an in-row draft"
  );
  helpers.state.activeGlossaryDraft.translated_term = "";
  helpers.showGlossaryValidationError("Translated term required");
  assert(
    validationNodes["alc-storage-status"].textContent ===
      "Translated term required" &&
      validationNodes["alc-storage-status"].dataset.kind === "error" &&
      validationNodes["alc-storage-status"].attrs.role === "alert" &&
      inlineValidationControl.attrs["aria-invalid"] === "true" &&
      inlineValidationControl.focused,
    "inline glossary validation did not use an accessible centered status"
  );
  helpers.clearGlossaryValidationError();
  assert(
    validationNodes["alc-storage-status"].hidden &&
      inlineValidationControl.attrs["aria-invalid"] === undefined,
    "editing the inline translated term did not clear its validation state"
  );
  validationNodes["alc-editor-dialog"].open = true;
  helpers.showGlossaryValidationError("Translated term required");
  assert(
    !validationNodes["alc-editor-error"].hidden &&
      validationNodes["alc-editor-error"].textContent ===
        "Translated term required" &&
      validationNodes["alc-editor-title"].attrs["aria-invalid"] === "true" &&
      validationNodes["alc-editor-title"].focused,
    "advanced glossary validation did not stay inside the editor panel"
  );
  helpers.clearGlossaryValidationError();
  validationNodes["alc-editor-dialog"].open = false;
  helpers.state.activeGlossaryDraft.translated_term = "读者";
  var rowCalls = {actions: 0, saveScopes: []};
  helpers.installGlossaryRowSpies(rowCalls);
  var inlineRow = helpers.renderGlossaryRow(base, {
    source: "Source",
    translatedTerm: "Translated term",
    definition: "Definition",
    glossaryTerm: "Glossary"
  });
  var sourceColumn = inlineRow.children[0];
  var translatedColumn = inlineRow.children[1];
  var definitionColumn = inlineRow.children[2];
  var translatedInput = translatedColumn.children[2];
  var definitionInput = definitionColumn.children[2];
  var mobileActions = sourceColumn.children[0].children[1];
  var definitionActions = definitionColumn.children[0].children[1];
  assert(
    inlineRow.className.includes("is-inline-editing") &&
      inlineRow.children.length === 3 &&
      sourceColumn.tagName === "DT" &&
      sourceColumn.className.includes("alc-glossary-inline-source") &&
      mobileActions.className.includes("alc-glossary-inline-mobile-actions") &&
      mobileActions.children[0].textContent === "Glossary · v1" &&
      sourceColumn.children[0].children[0].textContent === "Source" &&
      sourceColumn.children[1].textContent === "Reader" &&
      translatedColumn.tagName === "DD" &&
      translatedColumn.children[0].children[0].textContent === "Translated term" &&
      definitionColumn.children[0].children[0].textContent === "Definition" &&
      definitionActions.className.includes(
        "alc-glossary-inline-desktop-actions"
      ) &&
      definitionActions.children[0].textContent === "Glossary · v1" &&
      translatedInput.tagName === "TEXTAREA" && translatedInput.value === "读者" &&
      translatedInput.attrs["aria-label"] === "Translated term" &&
      definitionInput.tagName === "TEXTAREA" &&
      definitionInput.value === "旧解释" &&
      definitionInput.attrs["aria-label"] === "Definition" &&
      rowCalls.actions === 2,
    "active glossary draft did not render in-row fields and actions"
  );
  translatedInput.value = "阅读器";
  translatedInput.listeners.input[0]();
  assert(
    helpers.state.activeGlossaryDraft.translated_term === "阅读器" &&
      rowCalls.saveScopes[0] === inlineRow,
    "in-row glossary input did not update the active draft"
  );
  helpers.state.activeGlossaryDraft.translated_term = " \\n ";
  assert(
    helpers.activeGlossaryDraftValid() === false,
    "an empty translated glossary term remained saveable"
  );
  helpers.state.activeGlossaryDraft.translated_term = "阅读器";
  assert(
    helpers.activeGlossaryDraftValid() === true,
    "a non-empty translated glossary term was rejected"
  );
  helpers.state.activeGlossaryDraft = null;
  helpers.state.editorBase = null;
  helpers.state.editorKind = "fragment";
  var savedRow = helpers.renderGlossaryRow(base, {
    translatedTerm: "Translated term",
    definition: "Definition"
  });
  var cardActions = savedRow.children[savedRow.children.length - 1];
  assert(
    savedRow.children.length === 4 &&
      savedRow.children[1].className === "alc-glossary-translation" &&
      cardActions.className.includes("alc-glossary-card-actions") &&
      cardActions.children.length === 2 &&
      cardActions.children.every(function (button) {
        return button.className === "alc-card-action";
      }),
    "saved glossary row did not use speaker/edit hover actions"
  );
  var activationCalls = [];
  helpers.installGlossaryActivationSpy(activationCalls);
  function activationEvent(control, translation) {
    return {
      target: {
        closest: function (selector) {
          if (control && selector.includes("button")) return {};
          return translation && selector === ".alc-glossary-translation" ?
            {} : null;
        }
      },
      prevented: false,
      stopped: false,
      preventDefault: function () { this.prevented = true; },
      stopPropagation: function () { this.stopped = true; }
    };
  }
  helpers.state.readerPreferences.editActivation = "double";
  helpers.handleGlossaryEntryClick(activationEvent(false), base);
  assert(activationCalls.length === 0, "double-click mode accepted a row click");
  var doubleEvent = activationEvent(false, true);
  helpers.handleGlossaryEntryDoubleClick(doubleEvent, base);
  assert(
    activationCalls.join(",") === "term-reader:translation" &&
      doubleEvent.prevented && doubleEvent.stopped,
    "double-clicking the translated term did not route translated focus"
  );
  helpers.handleGlossaryEntryDoubleClick(activationEvent(false, false), base);
  assert(
    activationCalls.join(",") ===
      "term-reader:translation,term-reader:definition",
    "double-clicking outside the translated term did not route definition focus"
  );
  helpers.handleGlossaryEntryDoubleClick(activationEvent(true), base);
  assert(
    activationCalls.length === 2,
    "nested glossary control triggered row double-click editing"
  );
  helpers.state.readerPreferences.editActivation = "single";
  helpers.handleGlossaryEntryDoubleClick(activationEvent(false), base);
  assert(activationCalls.length === 2, "single-click mode accepted a double click");
  helpers.handleGlossaryEntryClick(activationEvent(false), base);
  assert(
    activationCalls.join(",") ===
      "term-reader:translation,term-reader:definition,term-reader:definition",
    "single-click mode did not keep definition focus"
  );
  helpers.handleGlossaryEntryClick(activationEvent(true), base);
  assert(
    activationCalls.length === 3,
    "nested glossary control triggered row single-click editing"
  );
  helpers.state.glossaryBase = [JSON.parse(JSON.stringify(base))];
  var baseDigest = await helpers.canonicalDigest(helpers.glossaryBaseMaterial(base));
  helpers.state.glossaryBaseDigests = new Map([["term-reader", baseDigest]]);
  var revision = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: "term-reader", revision: 2,
    parent_semantic_digest: baseDigest,
    entry: Object.assign({}, base, {
      translated_term: "阅读器",
      definition: "新解释：$H_0$ 与 **宇宙学**。"
    }),
    provenance: {producer: "alc-render-browser"}, semantic_digest: ""
  };
  revision.semantic_digest = await helpers.canonicalDigest(
    helpers.glossaryRevisionMaterial(revision)
  );
  var encodedRevision = helpers.encodeGlossaryRevision(revision);
  var revisionFilename = helpers.glossaryRevisionFileName(
    revision.revision, revision.semantic_digest
  );
  var revisionFrontMatter = encodedRevision.split(
    "\\n<!-- ALC:GLOSSARY-JSON:END -->\\n", 1
  )[0];
  var decodedRevision = await helpers.parseGlossaryRevisionFile(
    encodedRevision, revisionFilename
  );
  var legacyRevision = await helpers.parseGlossaryRevisionFile(
    helpers.stableStringify(helpers.glossaryRevisionMaterial(revision)) + "\\n",
    revisionFilename.replace(/[.]md$/, ".json")
  );
  assert(
    revisionFilename.endsWith(".md") &&
      encodedRevision.startsWith("<!-- ALC:GLOSSARY-JSON:BEGIN -->\\n") &&
      !revisionFrontMatter.includes('"definition"') &&
      encodedRevision.endsWith(revision.entry.definition) &&
      decodedRevision.semantic_digest === revision.semantic_digest &&
      decodedRevision.entry.definition === revision.entry.definition &&
      legacyRevision.semantic_digest === revision.semantic_digest,
    "glossary Markdown revision envelope did not round-trip compatibly"
  );
  helpers.state.glossaryRevisions = new Map([["term-reader", [revision]]]);
  helpers.state.glossaryRevisionDigests = new Map([
    ["term-reader", new Set([revision.semantic_digest])]
  ]);
  helpers.state.glossaryFileDiagnostics = [];
  helpers.resolveGlossaryAll();
  assert(
    helpers.state.payload.publication.glossary[0].translated_term === "阅读器" &&
      helpers.state.payload.publication.glossary[0].definition ===
        "新解释：$H_0$ 与 **宇宙学**。",
    "latest glossary revision was not projected into the effective entry"
  );
  var numericBase = Object.assign({}, base, {
    entry_id: "term-numeric", term: "Numeric", translated_term: "数值",
    confidence: 0.9
  });
  var numericDigest = "b".repeat(64);
  var numericRevision = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: numericBase.entry_id,
    revision: 2,
    parent_semantic_digest: "c".repeat(64),
    entry: Object.assign({}, numericBase, {translated_term: "数值术语"}),
    provenance: {producer: "alc-render-browser"},
    semantic_digest: numericDigest
  };
  helpers.state.payload.publication.glossary = [numericBase];
  helpers.state.payload.glossary_base_digests = {
    "term-numeric": numericRevision.parent_semantic_digest
  };
  helpers.state.payload.glossary_revisions = [numericRevision];
  await helpers.prepareGlossary();
  assert(
    helpers.state.payload.publication.glossary[0].translated_term ===
      "数值术语" &&
      !helpers.glossaryEntryEditableInState(
        helpers.state.payload.publication.glossary[0]
      ),
    "a legal unknown numeric field crashed Reader state or remained editable"
  );
  var duplicateA = Object.assign({}, base, {
    entry_id: "term-duplicate", translated_term: "第一项"
  });
  var duplicateB = Object.assign({}, base, {
    entry_id: "term-duplicate", translated_term: "第二项"
  });
  helpers.state.payload.publication.glossary = [duplicateA, duplicateB];
  helpers.state.payload.glossary_base_digests = {};
  helpers.state.payload.glossary_revisions = [];
  await helpers.prepareGlossary();
  assert(
    helpers.state.payload.publication.glossary.map(function (entry) {
      return entry.translated_term;
    }).join(",") === "第一项,第二项" &&
      helpers.state.glossaryDuplicateIds.has("term-duplicate") &&
      !helpers.glossaryEntryEditableInState(duplicateA),
    "duplicate glossary IDs were projected through one shared Map entry"
  );
  helpers.state.payload.publication.glossary = [base];
  helpers.state.payload.glossary_base_digests = {"term-reader": baseDigest};
  helpers.state.payload.glossary_revisions = [];
  await helpers.prepareGlossary();
  helpers.state.glossaryRevisions = new Map([["term-reader", [
    Object.assign({}, revision, {semantic_digest: "c".repeat(64)}),
    Object.assign({}, revision, {
      entry: Object.assign({}, revision.entry, {translated_term: "阅读界面"}),
      semantic_digest: "d".repeat(64)
    })
  ]]]);
  var forkRejected = false;
  try {
    helpers.assertGlossaryBaseCurrent({
      entryId: "term-reader", baseDigest: baseDigest, baseRevision: 1
    });
  } catch (_error) {
    forkRejected = true;
  }
  assert(forkRejected, "a known glossary fork remained writable");
  helpers.state.glossaryBase = [JSON.parse(JSON.stringify(base))];
  helpers.state.glossaryDuplicateIds = new Set();
  helpers.state.glossaryBaseDigests = new Map([["term-reader", baseDigest]]);
  helpers.state.glossaryRevisions = new Map([["term-reader", [revision]]]);
  helpers.state.glossaryFileDiagnostics = [];
  helpers.state.payload.publication.glossary = [base];
  helpers.resolveGlossaryAll();
  assert(
    helpers.projectGlossaryMarkdown(
      "读者在此", {
        fragment_id: "translation-1", semantic_digest: "d".repeat(64),
        anchor: {kind: "block", target_id: "block-1"}
      }
    ) === "阅读器在此",
    "exact structured target range was not projected"
  );
  assert(
    helpers.projectGlossaryMarkdown(
      "读者在此", {
        fragment_id: "translation-1", semantic_digest: "e".repeat(64),
        anchor: {kind: "block", target_id: "block-1"}
      }
    ) === "读者在此",
    "stale target range caused an unsafe replacement"
  );
  assert(
    !helpers.validGlossarySurfaceAnchors({surface_anchors: [{surface: "读者"}]}),
    "incomplete surface anchor was accepted"
  );
      helpers.state.initialGlossaryDigests = new Map([["term-reader", baseDigest]]);
      helpers.setupMarkdown();
      var changed = helpers.buildMarkdownPackage("changed", new Set(["glossary"]));
  var changedHtml = changed && helpers.state.md.render(changed.markdown);
  assert(
    changed && changed.markdown.includes("Reader / 阅读器") &&
      changed.markdown.includes("新解释：$H_0$ 与 **宇宙学**。") &&
      !changed.markdown.includes("\\\\$H\\\\_0\\\\$") &&
      changedHtml.includes('class="math math-inline"') &&
      changedHtml.includes("<strong>宇宙学</strong>") &&
      !changedHtml.includes("<pre><code>") &&
      changed.manifest.selected_glossary_revision_digests.join(",") ===
        revision.semantic_digest,
    "changed-only Markdown did not include the latest glossary revision"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )
    completed = subprocess.run(
        [node, "-"], input=instrumented, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_glossary_propagation_indexes_safe_mentions_and_rejects_stale_batches() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        _text("markdown-it/markdown-it.min.js")
        + "\nglobalThis.window = globalThis;\n"
        + "globalThis.markdownit = module.exports;\n"
        + "globalThis.crypto = require('node:crypto').webcrypto;\n"
        + javascript[:startup]
        + """
  globalThis.__alcPropagationTest = {
    state: state,
    setupMarkdown: setupMarkdown,
    canonicalDigest: canonicalDigest,
    glossaryBaseMaterial: glossaryBaseMaterial,
    buildGlossaryMentionIndex: buildGlossaryMentionIndex,
    fragmentGlossaryMentions: fragmentGlossaryMentions,
    applyGlossaryMentionReplacement: applyGlossaryMentionReplacement,
    validateStoredGlossaryMentions: validateStoredGlossaryMentions,
    updateGlossaryMentionProvenance: updateGlossaryMentionProvenance,
    prepareGlossaryPropagation: prepareGlossaryPropagation,
    loadGlossaryPropagationBatch: loadGlossaryPropagationBatch,
    buildMarkdownPackage: buildMarkdownPackage,
    resolveGlossaryAll: resolveGlossaryAll,
    projectedRevisionMarkdown: projectedRevisionMarkdown,
    buildCommittedGlossarySnapshot: buildCommittedGlossarySnapshot,
    structurallySelectedGlossaryChains: structurallySelectedGlossaryChains
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcPropagationTest;
var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var anchor = {
  kind: "block",
  target_id: "block-1",
  related_blocks: [{
    block_id: "block-1",
    kind: "paragraph",
    ordinal: 0,
    locator: {line_start: 1},
    content_fingerprint: "c".repeat(64)
  }]
};
var entry = {
  entry_id: "term-reader",
  term: "Reader",
  translated_term: "读者",
  definition: "阅读文本的人。",
  anchor_ids: ["block-1"]
};
var peerEntry = {
  entry_id: "term-peer",
  term: "Peer",
  translated_term: "相关术语",
  definition: "读者用于解释；`读者`；[链接](https://读者.example)；$读者$。",
  anchor_ids: ["block-1"]
};
var markdown = "读者与 **读者**；`读者`；[链接](https://读者.example)；$读者$。";
var fragment = {
  schema_version: "alc.render.fragment_revision.v3",
  source: source,
  fragment_id: "translation-1",
  revision: 1,
  parent_semantic_digest: null,
  anchor: anchor,
  priority: 10,
  role: "translation",
  language: "zh-CN",
  title: null,
  citation_ids: [],
  appearance: null,
  deleted: false,
  provenance: {producer: "alc-translate"},
  markdown_body: markdown,
  semantic_digest: "d".repeat(64)
};
helpers.state.payload = {
  source_identity: source,
  block_fingerprints: {"block-1": "c".repeat(64)},
  diagnostics: [],
  publication: {
    source_document: {blocks: [{
      block_id: "block-1", kind: "paragraph", ordinal: 0,
      locator: {line_start: 1}, payload: {text: "Reader"}
    }]},
    outline: [], bibliography: [], labels: {},
    reader_profile: {source_language: "en", target_language: "zh-CN"},
    glossary: [entry]
  }
};
helpers.setupMarkdown();
helpers.state.glossaryBase = [entry];
helpers.state.glossaryRevisions = new Map();
helpers.state.selected = new Map([[fragment.fragment_id, fragment]]);
helpers.state.revisions = new Map([[fragment.fragment_id, [fragment]]]);

(async function () {
  var indexed = helpers.buildGlossaryMentionIndex(
    fragment, markdown, [entry], false
  );
  assert(
    indexed.mentions.length === 2 && indexed.skipped === 3,
    "bounded mention indexing included protected Markdown"
  );
  var nestedLong = {
    entry_id: "term-pede", term: "PEDE",
    translated_term: "现象学涌现暗能量（PEDE）模型",
    definition: "specific", anchor_ids: ["block-1"]
  };
  var nestedShort = {
    entry_id: "term-emergent", term: "emergent dark energy",
    translated_term: "涌现暗能量",
    definition: "generic", anchor_ids: ["block-1"]
  };
  var nestedMarkdown = "现象学涌现暗能量（PEDE）模型与涌现暗能量";
  var nested = helpers.buildGlossaryMentionIndex(
    fragment, nestedMarkdown, [nestedLong, nestedShort], false
  );
  assert(
    nested.ambiguous === 0 && nested.mentions.length === 2 &&
      nested.mentions[0].entry_id === "term-pede" &&
      nested.mentions[1].entry_id === "term-emergent",
    "contained generic term did not defer to the longer glossary surface"
  );
  var duplicateShort = Object.assign({}, nestedShort, {
    entry_id: "term-bic", term: "BIC", translated_term: "贝叶斯信息准则（BIC）"
  });
  var duplicateLong = Object.assign({}, nestedShort, {
    entry_id: "term-bayesian-information-criterion",
    term: "Bayesian Information Criterion",
    translated_term: "贝叶斯信息准则（BIC）"
  });
  var duplicate = helpers.buildGlossaryMentionIndex(
    fragment, "贝叶斯信息准则（BIC）", [duplicateShort, duplicateLong], false
  );
  assert(
    duplicate.ambiguous === 0 && duplicate.mentions.length === 1 &&
      duplicate.mentions[0].entry_id === duplicateLong.entry_id &&
      Object.keys(duplicate.mentions[0]).sort().join(",") ===
        "entry_id,markdown_end,markdown_start,surface",
    "identical translated aliases did not choose the more complete source term"
  );
  var preferredDuplicate = helpers.buildGlossaryMentionIndex(
    fragment, "贝叶斯信息准则（BIC）", [duplicateShort, duplicateLong], false,
    duplicateShort.entry_id
  );
  assert(
    preferredDuplicate.ambiguous === 0 &&
      preferredDuplicate.mentions.length === 1 &&
      preferredDuplicate.mentions[0].entry_id === duplicateShort.entry_id,
    "the glossary entry being edited did not own its shared translated surface"
  );
  var crossingLeft = Object.assign({}, nestedShort, {
    entry_id: "term-crossing-left", term: "crossing left",
    translated_term: "甲乙丙"
  });
  var crossingRight = Object.assign({}, nestedShort, {
    entry_id: "term-crossing-right", term: "crossing right",
    translated_term: "乙丙丁"
  });
  var crossing = helpers.buildGlossaryMentionIndex(
    fragment, "甲乙丙丁", [crossingLeft, crossingRight], false
  );
  assert(
    crossing.ambiguous === 2 && crossing.mentions.length === 0 &&
      crossing.ambiguous_entry_ids.join(",") ===
        "term-crossing-left,term-crossing-right",
    "true crossing glossary ranges stopped failing closed"
  );
  function aidFragment(role, fragmentId, digest, priority) {
    return Object.assign({}, fragment, {
      fragment_id: fragmentId,
      role: role,
      priority: priority,
      markdown_body: "辅助说明：读者。",
      semantic_digest: digest.repeat(64)
    });
  }
  var companion = aidFragment("companion", "companion-1", "e", 20);
  var guide = aidFragment("guide", "guide-1", "f", 101);
  var note = aidFragment("note", "note-1", "9", 110);
  assert(
    helpers.buildGlossaryMentionIndex(
      companion, companion.markdown_body, [entry], false
    ).mentions.length === 1 &&
      helpers.buildGlossaryMentionIndex(
        guide, guide.markdown_body, [entry], false
      ).mentions.length === 1 &&
      helpers.buildGlossaryMentionIndex(
        note, note.markdown_body, [entry], false
      ).mentions.length === 0,
    "glossary mention role boundary did not include companion and guide only"
  );
  var unanchoredEntry = Object.assign({}, entry, {anchor_ids: ["another-block"]});
  assert(
    helpers.buildGlossaryMentionIndex(
      fragment, "读者。", [unanchoredEntry], false
    ).mentions.length === 1,
    "eligible translated prose remained incorrectly gated by source anchor_ids"
  );
  var oldIndexed = JSON.parse(JSON.stringify(fragment));
  oldIndexed.markdown_body = "旧索引遗漏了读者。";
  oldIndexed.provenance = {
    producer: "alc-translate",
    glossary_mentions_schema: "alc.render.glossary_mentions.v1",
    glossary_mentions: []
  };
  assert(
    helpers.fragmentGlossaryMentions(oldIndexed, [entry]).mentions.length === 1,
    "propagation trusted an older incomplete mention index"
  );
  var persistedAlias = JSON.parse(JSON.stringify(fragment));
  persistedAlias.markdown_body = "贝叶斯信息准则（BIC）";
  persistedAlias.provenance = {
    producer: "alc-translate",
    glossary_mentions_schema: "alc.render.glossary_mentions.v1",
    glossary_mentions: [{
      entry_id: duplicateLong.entry_id,
      markdown_start: 0,
      markdown_end: persistedAlias.markdown_body.length,
      surface: persistedAlias.markdown_body
    }]
  };
  assert(
    helpers.fragmentGlossaryMentions(
      persistedAlias, [duplicateShort, duplicateLong], duplicateShort.entry_id
    ).mentions[0].entry_id === duplicateLong.entry_id,
    "the actively edited alias stole a persisted mention owner"
  );
  var citationEntry = Object.assign({}, entry, {
    entry_id: "term-citation-key",
    translated_term: "ref-1"
  });
  var citationIndex = helpers.buildGlossaryMentionIndex(
    fragment, "引用 [@ref-1]，正文 ref-1。", [citationEntry], false
  );
  assert(
    citationIndex.mentions.length === 1 &&
      citationIndex.mentions[0].markdown_start > 10,
    "citation-key text was indexed as replaceable glossary prose"
  );
  var explicitEntry = Object.assign({}, entry, {surface_anchors: [{
    block_id: "block-1",
    fragment_id: fragment.fragment_id,
    fragment_semantic_digest: fragment.semantic_digest,
    markdown_start: 0,
    markdown_end: 2,
    surface: "读者"
  }]});
  assert(
    helpers.fragmentGlossaryMentions(fragment, [explicitEntry]).mentions.length === 1,
    "structured surface anchor did not take priority over legacy matching"
  );
  var replaced = helpers.applyGlossaryMentionReplacement(
    markdown, indexed.mentions, "阅读器"
  );
  assert(
    replaced === "阅读器与 **阅读器**；`读者`；[链接](https://读者.example)；$读者$。",
    "mention replacement escaped its validated prose ranges"
  );

  var nextEntry = Object.assign({}, entry, {translated_term: "阅读器"});
  var entryBaseDigest = await helpers.canonicalDigest(
    helpers.glossaryBaseMaterial(entry)
  );
  var peerBaseDigest = await helpers.canonicalDigest(
    helpers.glossaryBaseMaterial(peerEntry)
  );
  helpers.state.payload.publication.glossary = [entry, peerEntry];
  helpers.state.glossaryBase = [entry, peerEntry];
  helpers.state.glossaryBaseDigests = new Map([
    [entry.entry_id, entryBaseDigest],
    [peerEntry.entry_id, peerBaseDigest]
  ]);
  helpers.state.selectedGlossary = new Map([
    [entry.entry_id, entry], [peerEntry.entry_id, peerEntry]
  ]);
  helpers.state.selectedGlossaryRevisions = new Map([
    [entry.entry_id, null], [peerEntry.entry_id, null]
  ]);
  helpers.state.glossaryRevisions = new Map();
  var prepared = await helpers.prepareGlossaryPropagation(
    {base: entry, entryId: entry.entry_id}, nextEntry,
    "2026-08-28T00:00:00.000Z"
  );
  assert(
    prepared.revisions.length === 1 &&
      prepared.revisions[0].markdown === replaced &&
      prepared.manifest.fragments.length === 1 &&
      prepared.glossaryRevisions.length === 1 &&
      prepared.manifest.glossary_revisions.length === 1 &&
      prepared.glossaryRevisions[0].metadata.entry_id === peerEntry.entry_id &&
      prepared.glossaryRevisions[0].metadata.entry.translated_term ===
        peerEntry.translated_term &&
      prepared.glossaryRevisions[0].metadata.entry.definition ===
        "阅读器用于解释；`读者`；[链接](https://读者.example)；$读者$。" &&
      prepared.glossaryRevisions[0].path.startsWith(
        "glossary-batches/" + prepared.manifest.batch_id + "/glossary/"
      ) &&
      prepared.revisions[0].metadata.provenance.glossary_mentions.length === 2 &&
      prepared.revisions[0].metadata.provenance.glossary_mentions.every(
        function (mention) { return mention.surface === "阅读器"; }
      ),
    "glossary save did not prepare Fragment and peer-definition successors"
  );
  function batchDirectory(files, prefix) {
    prefix = prefix || [];
    return {
      getDirectoryHandle: async function (name) {
        return batchDirectory(files, prefix.concat([name]));
      },
      getFileHandle: async function (name) {
        var path = prefix.concat([name]).join("/");
        if (!files.has(path)) throw new Error("missing batch file: " + path);
        return {
          getFile: async function () {
            return {text: async function () { return files.get(path); }};
          }
        };
      }
    };
  }
  var batchFiles = new Map([
    [prepared.revisions[0].path, prepared.revisions[0].encoded],
    [prepared.glossaryRevisions[0].path,
      prepared.glossaryRevisions[0].encoded]
  ]);
  var loadedBatch = await helpers.loadGlossaryPropagationBatch(
    batchDirectory(batchFiles), {
      entry_id: entry.entry_id,
      provenance: {propagation: prepared.manifest}
    }
  );
  assert(
    loadedBatch.fragments.length === 1 &&
      loadedBatch.glossaryRevisions.length === 1 &&
      loadedBatch.glossaryRevisions[0].entry_id === peerEntry.entry_id,
    "browser directory reload did not validate both propagation member types"
  );
  var rootMetadata = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: entry.entry_id,
    revision: 2,
    parent_semantic_digest: entryBaseDigest,
    entry: nextEntry,
    provenance: {
      producer: "alc-render-browser", propagation: prepared.manifest
    }
  };
  var rootDigest = await helpers.canonicalDigest({
    schema_version: rootMetadata.schema_version,
    entry_id: rootMetadata.entry_id,
    revision: rootMetadata.revision,
    parent_semantic_digest: rootMetadata.parent_semantic_digest,
    entry: rootMetadata.entry,
    provenance: rootMetadata.provenance
  });
  var peerMetadata = prepared.glossaryRevisions[0].metadata;
  helpers.state.glossaryRevisions = new Map([
    [entry.entry_id, [Object.assign({}, rootMetadata, {
      semantic_digest: rootDigest
    })]],
    [peerEntry.entry_id, [Object.assign({}, peerMetadata, {
      semantic_digest: prepared.glossaryRevisions[0].digest
    })]]
  ]);
  helpers.state.glossaryFileDiagnostics = [];
  helpers.state.initialGlossaryDigests = new Map([
    [entry.entry_id, entryBaseDigest],
    [peerEntry.entry_id, peerBaseDigest]
  ]);
  helpers.resolveGlossaryAll();
  var changedGlossary = helpers.buildMarkdownPackage(
    "changed", new Set(["glossary"])
  );
  assert(
    changedGlossary.markdown.includes("Reader / 阅读器") &&
      changedGlossary.markdown.includes("Peer / 相关术语") &&
      changedGlossary.markdown.includes("阅读器用于解释") &&
      changedGlossary.manifest.selected_glossary_revision_digests.length === 2,
    "changed Markdown omitted the propagated peer glossary revision"
  );
  helpers.state.payload.publication.glossary = [entry, peerEntry];
  helpers.state.glossaryRevisions = new Map();
  helpers.state.selectedGlossary = new Map([
    [entry.entry_id, entry], [peerEntry.entry_id, peerEntry]
  ]);
  helpers.state.selectedGlossaryRevisions = new Map([
    [entry.entry_id, null], [peerEntry.entry_id, null]
  ]);
  helpers.state.selected = new Map([
    [fragment.fragment_id, fragment],
    [companion.fragment_id, companion],
    [guide.fragment_id, guide]
  ]);
  helpers.state.revisions = new Map([
    [fragment.fragment_id, [fragment]],
    [companion.fragment_id, [companion]],
    [guide.fragment_id, [guide]]
  ]);
  var preparedAcrossRoles = await helpers.prepareGlossaryPropagation(
    {base: entry, entryId: entry.entry_id}, nextEntry,
    "2026-08-28T00:00:00.500Z"
  );
  assert(
    preparedAcrossRoles.revisions.length === 3 &&
      preparedAcrossRoles.manifest.fragments.length === 3 &&
      preparedAcrossRoles.revisions.map(function (item) {
        return item.metadata.role;
      }).sort().join(",") === "companion,guide,translation",
    "glossary propagation did not version all authored reading-aid roles"
  );
  helpers.state.selected = new Map([[fragment.fragment_id, fragment]]);
  helpers.state.revisions = new Map([[fragment.fragment_id, [fragment]]]);
  helpers.validateStoredGlossaryMentions(
    Object.assign({}, prepared.revisions[0].metadata, {
      markdown_body: prepared.revisions[0].markdown
    }),
    prepared.revisions[0].markdown,
    [nextEntry]
  );
  var manuallyEdited = JSON.parse(JSON.stringify(fragment));
  manuallyEdited.provenance = {producer: "alc-translate"};
  helpers.updateGlossaryMentionProvenance(
    manuallyEdited.provenance, manuallyEdited, "补充说明：读者。", [entry]
  );
  assert(
    manuallyEdited.provenance.glossary_mentions.length === 1 &&
      manuallyEdited.provenance.glossary_mentions[0].markdown_start === 5,
    "manual translation edit did not rebuild shifted mention ranges"
  );
  var definitionOnly = await helpers.prepareGlossaryPropagation(
    {base: entry, entryId: entry.entry_id},
    Object.assign({}, entry, {definition: "修订解释。"}),
    "2026-08-28T00:00:01.000Z"
  );
  assert(
    definitionOnly.revisions.length === 0 &&
      definitionOnly.glossaryRevisions.length === 0 &&
      definitionOnly.manifest === null,
    "definition-only glossary edit generated Fragment work"
  );

  var crossingFragment = Object.assign({}, fragment, {
    fragment_id: "translation-crossing",
    markdown_body: "甲乙丙丁",
    semantic_digest: "2".repeat(64)
  });
  helpers.state.payload.publication.glossary = [
    entry, crossingLeft, crossingRight
  ];
  helpers.state.glossaryBase = [entry, crossingLeft, crossingRight];
  helpers.state.selected = new Map([
    [fragment.fragment_id, fragment],
    [crossingFragment.fragment_id, crossingFragment]
  ]);
  helpers.state.revisions = new Map([
    [fragment.fragment_id, [fragment]],
    [crossingFragment.fragment_id, [crossingFragment]]
  ]);
  var unrelatedPrepared = await helpers.prepareGlossaryPropagation(
    {base: entry, entryId: entry.entry_id}, nextEntry,
    "2026-08-28T00:00:01.500Z"
  );
  assert(
    unrelatedPrepared.revisions.length === 1 &&
      unrelatedPrepared.revisions[0].metadata.fragment_id === fragment.fragment_id,
    "an unrelated crossing glossary range blocked a safe glossary edit"
  );
  var targetCrossingRejected = false;
  try {
    await helpers.prepareGlossaryPropagation(
      {base: crossingLeft, entryId: crossingLeft.entry_id},
      Object.assign({}, crossingLeft, {translated_term: "甲乙丙新"}),
      "2026-08-28T00:00:02.000Z"
    );
  } catch (error) {
    targetCrossingRejected = error.message.includes(
      "glossary propagation found overlapping term mentions"
    );
  }
  assert(
    targetCrossingRejected,
    "a true crossing range involving the edited glossary entry was accepted"
  );
  helpers.state.payload.publication.glossary = [entry];
  helpers.state.glossaryBase = [entry];
  helpers.state.selected = new Map([[fragment.fragment_id, fragment]]);
  helpers.state.revisions = new Map([[fragment.fragment_id, [fragment]]]);

  var baseDigest = await helpers.canonicalDigest(
    helpers.glossaryBaseMaterial(entry)
  );
  helpers.state.glossaryBaseDigests = new Map([[entry.entry_id, baseDigest]]);
  var glossaryRevision = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: entry.entry_id,
    revision: 2,
    parent_semantic_digest: baseDigest,
    entry: nextEntry,
    provenance: {
      producer: "alc-render-browser",
      propagation: prepared.manifest
    },
    semantic_digest: "e".repeat(64)
  };
  var equivalentRetry = Object.assign({}, glossaryRevision, {
    provenance: {producer: "alc-render-browser", attempt: "retry"},
    semantic_digest: "f".repeat(64)
  });
  var equivalentSuccessor = Object.assign({}, equivalentRetry, {
    revision: 3,
    parent_semantic_digest: equivalentRetry.semantic_digest,
    entry: Object.assign({}, nextEntry, {definition: "continued"}),
    semantic_digest: "1".repeat(64)
  });
  var equivalentMap = new Map([[entry.entry_id, [
    glossaryRevision, equivalentRetry, equivalentSuccessor
  ]]]);
  var equivalentChain = helpers.structurallySelectedGlossaryChains(
    equivalentMap
  )[0];
  assert(
    equivalentChain.length === 2 &&
      equivalentChain[0].semantic_digest === equivalentRetry.semantic_digest &&
      equivalentChain[1].semantic_digest === equivalentSuccessor.semantic_digest,
    "content-equivalent glossary retry did not follow its unique successor"
  );
  var fragmentRevision = Object.assign({}, prepared.revisions[0].metadata, {
    markdown_body: prepared.revisions[0].markdown,
    semantic_digest: prepared.revisions[0].digest
  });
  assert(
    helpers.projectedRevisionMarkdown(fragmentRevision) === replaced,
    "Markdown export path did not consume the materialized Fragment body"
  );
  var fragmentRevisions = new Map([[fragment.fragment_id, [fragment]]]);
  var accepted = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision],
    new Map([[glossaryRevision.semantic_digest, [fragmentRevision]]]),
    fragmentRevisions,
    []
  );
  assert(
    accepted.batchRevisions.length === 1 &&
      accepted.revisions.get(entry.entry_id).length === 1,
    "complete propagation batch was not admitted atomically"
  );
  var peerRevision = Object.assign(
    {}, prepared.glossaryRevisions[0].metadata, {
      semantic_digest: prepared.glossaryRevisions[0].digest
    }
  );
  helpers.state.glossaryBase = [entry, peerEntry];
  helpers.state.glossaryBaseDigests = new Map([
    [entry.entry_id, baseDigest], [peerEntry.entry_id, peerBaseDigest]
  ]);
  var acceptedWithPeer = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision, peerRevision],
    new Map([[glossaryRevision.semantic_digest, {
      fragments: [fragmentRevision],
      glossaryRevisions: [peerRevision]
    }]]),
    fragmentRevisions,
    []
  );
  assert(
    acceptedWithPeer.batchRevisions.length === 1 &&
      acceptedWithPeer.revisions.get(peerEntry.entry_id).some(function (item) {
        return item.semantic_digest === peerRevision.semantic_digest;
      }),
    "peer glossary revision was not admitted with its commit marker"
  );
  var missingPeer = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision],
    new Map([[glossaryRevision.semantic_digest, {
      fragments: [fragmentRevision],
      glossaryRevisions: [peerRevision]
    }]]),
    fragmentRevisions,
    []
  );
  assert(
    !missingPeer.revisions.has(entry.entry_id) &&
      missingPeer.batchRevisions.length === 0,
    "commit marker survived a missing peer glossary member"
  );
  helpers.state.glossaryBase = [entry];
  helpers.state.glossaryBaseDigests = new Map([[entry.entry_id, baseDigest]]);

  var manualV3 = Object.assign({}, fragment, {
    revision: 3,
    parent_semantic_digest: fragmentRevision.semantic_digest,
    markdown_body: "补充：阅读器。",
    semantic_digest: "6".repeat(64)
  });
  var batch2 = "glossary-follow-up";
  var fragmentV4 = Object.assign({}, fragmentRevision, {
    revision: 4,
    parent_semantic_digest: manualV3.semantic_digest,
    markdown_body: "补充：阅读界面。",
    semantic_digest: "7".repeat(64),
    provenance: Object.assign({}, fragmentRevision.provenance, {
      propagation_batch_id: batch2,
      glossary_mentions: [{
        entry_id: entry.entry_id,
        markdown_start: 3,
        markdown_end: 7,
        surface: "阅读界面"
      }]
    })
  });
  var followUpManifest = {
    schema_version: "alc.render.glossary_propagation.v1",
    batch_id: batch2,
    fragments: [{
      path: "glossary-batches/" + batch2 + "/fragments/" +
        "revision-000004-" + fragmentV4.semantic_digest + ".md",
      fragment_id: fragmentV4.fragment_id,
      revision: fragmentV4.revision,
      parent_semantic_digest: fragmentV4.parent_semantic_digest,
      semantic_digest: fragmentV4.semantic_digest
    }]
  };
  var glossaryV3 = {
    schema_version: "alc.render.glossary_revision.v1",
    entry_id: entry.entry_id,
    revision: 3,
    parent_semantic_digest: glossaryRevision.semantic_digest,
    entry: Object.assign({}, entry, {translated_term: "阅读界面"}),
    provenance: {producer: "alc-render-browser", propagation: followUpManifest},
    semantic_digest: "8".repeat(64)
  };
  var followed = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision, glossaryV3],
    new Map([
      [glossaryRevision.semantic_digest, [fragmentRevision]],
      [glossaryV3.semantic_digest, [fragmentV4]]
    ]),
    new Map([[fragment.fragment_id, [fragment, manualV3]]]),
    []
  );
  assert(
    followed.batchRevisions.length === 2 &&
      followed.revisions.get(entry.entry_id).length === 2,
    "follow-up glossary batch did not advance through a manual Fragment revision"
  );

  var staleFragment = Object.assign({}, fragmentRevision, {
    parent_semantic_digest: "f".repeat(64)
  });
  var staleManifest = JSON.parse(JSON.stringify(prepared.manifest));
  staleManifest.fragments[0].parent_semantic_digest = "f".repeat(64);
  var staleGlossary = Object.assign({}, glossaryRevision, {
    provenance: {producer: "alc-render-browser", propagation: staleManifest},
    semantic_digest: "9".repeat(64)
  });
  var staleDiagnostics = [];
  var rejected = helpers.buildCommittedGlossarySnapshot(
    [staleGlossary],
    new Map([[staleGlossary.semantic_digest, [staleFragment]]]),
    fragmentRevisions,
    staleDiagnostics
  );
  assert(
    rejected.batchRevisions.length === 0 &&
      !rejected.revisions.has(entry.entry_id) &&
      staleDiagnostics.some(function (value) {
        return value.includes("stale or conflicting");
      }),
    "stale propagation parent changed glossary state without its Fragment"
  );
  var staleSuccessor = Object.assign({}, staleGlossary, {
    revision: 3,
    parent_semantic_digest: staleGlossary.semantic_digest,
    entry: Object.assign({}, staleGlossary.entry, {definition: "continued"}),
    provenance: {producer: "alc-render-browser"},
    semantic_digest: "a".repeat(64)
  });
  var readmitted = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision, staleGlossary, staleSuccessor],
    new Map([
      [glossaryRevision.semantic_digest, [fragmentRevision]],
      [staleGlossary.semantic_digest, [staleFragment]]
    ]),
    fragmentRevisions,
    []
  );
  assert(
    readmitted.batchRevisions.length === 1 &&
      readmitted.revisions.get(entry.entry_id).some(function (item) {
        return item.semantic_digest === glossaryRevision.semantic_digest;
      }),
    "an equivalent retry selected after rejection was not re-admitted"
  );
  var forkA = Object.assign({}, fragmentRevision, {
    semantic_digest: "b".repeat(64)
  });
  var forkB = Object.assign({}, fragmentRevision, {
    markdown_body: "另一个分支",
    semantic_digest: "c".repeat(64)
  });
  var forkRejectedSnapshot = helpers.buildCommittedGlossarySnapshot(
    [glossaryRevision],
    new Map([[glossaryRevision.semantic_digest, [fragmentRevision]]]),
    new Map([[fragment.fragment_id, [fragment, forkA, forkB]]]),
    []
  );
  assert(
    forkRejectedSnapshot.batchRevisions.length === 0 &&
      !forkRejectedSnapshot.revisions.has(entry.entry_id),
    "an existing Fragment fork was treated as a writable common parent"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )
    completed = subprocess.run(
        [node, "-"], input=instrumented, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_markdown_supports_tables_and_glossary_math_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        _text("markdown-it/markdown-it.min.js")
        + "\nglobalThis.window = globalThis;\n"
        + "globalThis.markdownit = module.exports;\n"
        + javascript[:startup]
        + """
  globalThis.__alcMarkdownTest = {
    setupMarkdown: setupMarkdown,
    markdownPlainText: markdownPlainText,
    glossarySpeechText: glossarySpeechText,
    buildGlossarySpeechQueue: buildGlossarySpeechQueue,
    state: state
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcMarkdownTest;
helpers.state.payload = {
  publication: {
    labels: {},
    reader_profile: {source_language: "en-US", target_language: "zh-CN"}
  },
  resources: [],
  source_identity: null
};
helpers.setupMarkdown();
var rendered = helpers.state.md.render(
  "| Material | Use |\\n| --- | --- |\\n| Brass | Ring |\\n"
);
assert(
  rendered.includes("<table>") && rendered.includes("<th>Material</th>") &&
    rendered.includes("<td>Brass</td>"),
  "overlay Markdown table was rendered as literal pipe text"
);
var definition = helpers.state.md.render(
  "定义包含 **强调** 和 $H_0 = 70$。"
);
assert(
  definition.includes("<strong>强调</strong>") &&
    definition.includes('class="math math-inline"') &&
    definition.includes('data-tex="H_0 = 70"'),
  "glossary definition Markdown or inline math did not render"
);
var plainDefinition = helpers.markdownPlainText(
  "第一段包含 **强调** 和 $H_0$。\\n\\n第二段包含 `code`。"
);
assert(
  plainDefinition === "第一段包含 强调 和 H_0。\\n第二段包含 code。",
  "glossary tooltip plain text retained Markdown delimiters: " +
    JSON.stringify(plainDefinition)
);
assert(
  helpers.glossarySpeechText({
    term: "Hubble parameter",
    translated_term: "哈勃参数",
    definition: "定义为 $H_0$。"
  }) === "哈勃参数\\n定义为 H_0。",
  "glossary speech did not use target text and plain Markdown definition"
);
var glossaryQueue = helpers.buildGlossarySpeechQueue({
  entry_id: "term-hubble",
  term: "Hubble parameter",
  translated_term: "哈勃参数",
  definition: "定义为 $H_0$。"
});
assert(
  glossaryQueue.length === 2 &&
    glossaryQueue[0].text === "Hubble parameter" &&
    glossaryQueue[0].role === "source" &&
    glossaryQueue[0].language === "en-US" &&
    glossaryQueue[1].text === "哈勃参数\\n定义为 H_0。" &&
    glossaryQueue[1].role === "glossary" &&
    glossaryQueue[1].language === "zh-CN" &&
    glossaryQueue.every(function (segment) {
      return segment.glossaryEntryId === "term-hubble";
    }),
  "glossary speech queue did not read source before translated content"
);
"""
    )
    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_resolves_strict_legacy_bibliography_links_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")
    assert "outline: 2px solid currentColor" in stylesheet
    assert ".alc-unresolved-reference {\n  color: inherit;" in stylesheet
    assert "@supports (grid-template-rows: subgrid)" in stylesheet
    assert "@media screen and (min-width: 900px)" in stylesheet
    assert ".alc-aligned-bibliography" in stylesheet
    alignment = javascript[javascript.index(
        "function syncSourceBibliographyAlignment"
    ) : javascript.index("function decorateLegacyBibliographyLinks")]
    assert "getBoundingClientRect" not in alignment
    assert "ResizeObserver" not in alignment
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        _text("markdown-it/markdown-it.min.js")
        + "\nglobalThis.window = globalThis;\n"
        + "globalThis.markdownit = module.exports;\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcBibliographyTest = {
    state: state,
    setupMarkdown: setupMarkdown,
    buildSourceBibliographyIndex: buildSourceBibliographyIndex,
    sourceReferenceTargetId: sourceReferenceTargetId,
    canonicalReaderTargetId: canonicalReaderTargetId,
    chunkForTargetId: chunkForTargetId,
    revealSourceReferenceTarget: revealSourceReferenceTarget,
    syncSourceBibliographyAlignment: syncSourceBibliographyAlignment,
    legacyBibliographyTarget: legacyBibliographyTarget,
    degradeLegacyBibliographyMarkdownLinks:
      degradeLegacyBibliographyMarkdownLinks
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcBibliographyTest;
helpers.state.payload = {
  publication: {labels: {}, reader_profile: {}, source_document: {blocks: []}},
  resources: [],
  source_identity: null
};
helpers.setupMarkdown();
assert(
  helpers.legacyBibliographyTarget("#bib.bib1") &&
    !helpers.legacyBibliographyTarget("#bib.bibliography") &&
    !helpers.legacyBibliographyTarget("#bib.bib0"),
  "legacy bibliography target matching reserved more than exact positive IDs"
);
var manifest = [{block_id: "prose", kind: "paragraph"}, {
  block_id: "references", kind: "list"
}];
var descriptors = [{
  alias: "bib.bib1", block_id: "references", item_index: 0
}, {
  alias: "bib.bib2", block_id: "references", item_index: 1
}];
var index = helpers.buildSourceBibliographyIndex(descriptors, manifest);
var firstTarget = helpers.sourceReferenceTargetId("references", 0);
var secondTarget = helpers.sourceReferenceTargetId("references", 1);
assert(index.blockId === "references", "References list was not selected");
assert(index.aliases.size === 2, "validated bibliography aliases were omitted");
assert(index.aliases.get("bib.bib1") === firstTarget, "bib1 mapped incorrectly");
assert(index.aliases.get("bib.bib2") === secondTarget, "bib2 mapped incorrectly");

helpers.state.sourceBibliographyIndex = index;
helpers.state.chunkByTargetId = new Map([[firstTarget, "reference-chunk"]]);
assert(
  helpers.canonicalReaderTargetId("bib.bib1") === firstTarget,
  "legacy alias did not resolve to a canonical Reader target"
);
assert(
  helpers.chunkForTargetId("bib.bib1") === "reference-chunk",
  "legacy alias did not activate its progressive chunk"
);
helpers.state.sourceVisible = false;
helpers.state.visibilityReady = false;
assert(
  helpers.revealSourceReferenceTarget(firstTarget) &&
    helpers.state.sourceVisible,
  "source-reference navigation did not reveal its source target"
);
helpers.state.sourceVisible = false;
assert(
  !helpers.revealSourceReferenceTarget("block-prose") &&
    !helpers.state.sourceVisible,
  "ordinary Reader navigation changed Source visibility"
);

function fakeNode(tagName, className) {
  var names = new Set(String(className || "").split(/\s+/).filter(Boolean));
  return {
    tagName: String(tagName || "div").toUpperCase(),
    children: [],
    dataset: {},
    classList: {
      add: function (name) { names.add(name); },
      remove: function (name) { names.delete(name); },
      contains: function (name) { return names.has(name); }
    },
    style: {
      values: {},
      setProperty: function (name, value) { this.values[name] = value; },
      removeProperty: function (name) { delete this.values[name]; }
    }
  };
}
function listNode(count) {
  var list = fakeNode("ul");
  for (var item = 0; item < count; item += 1) {
    list.children.push(fakeNode("li"));
  }
  return list;
}
var alignedRow = fakeNode("article");
alignedRow.dataset.blockId = "references";
var alignedLanes = fakeNode("div", "alc-lanes");
var alignedSource = fakeNode("section", "alc-source-card");
var sourceList = listNode(2);
alignedSource.children.push(sourceList, fakeNode("div", "alc-card-actions"));
var alignedTranslation = fakeNode("aside", "alc-fragment");
alignedTranslation.dataset.role = "translation";
var saved = fakeNode("div", "alc-fragment-saved-content");
var renderedMarkdown = fakeNode("div", "alc-markdown");
var translatedList = listNode(2);
renderedMarkdown.children.push(translatedList);
saved.children.push(renderedMarkdown);
alignedTranslation.children.push(
  fakeNode("header", "alc-fragment-header"), saved,
  fakeNode("div", "alc-card-actions")
);
alignedLanes.children.push(alignedSource, alignedTranslation);
alignedRow.children.push(alignedLanes);
assert(
  helpers.syncSourceBibliographyAlignment(alignedRow) &&
    alignedLanes.classList.contains("alc-aligned-bibliography") &&
    alignedLanes.style.values["--alc-aligned-list-rows"] === "2",
  "matching source and translation lists were not shape-gated for alignment"
);
translatedList.children.pop();
assert(
  !helpers.syncSourceBibliographyAlignment(alignedRow) &&
    !alignedLanes.classList.contains("alc-aligned-bibliography") &&
    alignedLanes.style.values["--alc-aligned-list-rows"] === undefined,
  "a mismatched translation list retained item alignment"
);
translatedList.children.push(fakeNode("li"));
renderedMarkdown.children.push(fakeNode("p"));
assert(
  !helpers.syncSourceBibliographyAlignment(alignedRow),
  "translation content outside its one top-level list was aligned"
);
renderedMarkdown.children.pop();
alignedTranslation.classList.add("is-inline-editing");
assert(
  !helpers.syncSourceBibliographyAlignment(alignedRow),
  "an actively edited translation list retained alignment"
);
alignedTranslation.classList.remove("is-inline-editing");
alignedRow.dataset.blockId = "ordinary-list";
assert(
  !helpers.syncSourceBibliographyAlignment(alignedRow),
  "a non-bibliography list received per-item alignment"
);
alignedRow.dataset.blockId = "references";

var invalidDescriptors = descriptors.concat([{
  alias: "bib.bib1", block_id: "references", item_index: 1
}]);
var rejected = false;
try {
  helpers.buildSourceBibliographyIndex(invalidDescriptors, manifest);
} catch (_error) {
  rejected = true;
}
assert(rejected, "duplicate bibliography aliases were accepted");

var markdown = [
  "See [Smith 2020](#bib.bib1), [section](#S2), and " +
    "[site](https://example.test).",
  "",
  "Unclosed ` and [Smith 2020](#bib.bib1).",
  "",
  "[Jones 2021][legacy]",
  "",
  "[legacy]: #bib.bib2",
  "",
  "![Figure reference](#bib.bib1)",
  "",
  "Destination [Smith 2020](",
  "#bib.bib1)",
  "",
  "Label [Smith",
  "2020](#bib.bib1)",
  "",
  "Title [Smith 2020](#bib.bib1",
  " \"Paper\")",
  "",
  "`[multiline",
  "code](#bib.bib1)`",
  "",
  "`[inline](#bib.bib1)`",
  "",
  "```text",
  "[fenced](#bib.bib1)",
  "```",
  "",
  "    [indented](#bib.bib1)"
].join("\n");
var degraded = helpers.degradeLegacyBibliographyMarkdownLinks(markdown);
assert(
  degraded.includes("See Smith 2020, [section](#S2), and " +
    "[site](https://example.test)."),
  "export did not degrade the exact legacy bibliography link"
);
assert(degraded.includes("`[inline](#bib.bib1)`"), "inline code changed");
assert(degraded.includes("[fenced](#bib.bib1)"), "fenced code changed");
assert(degraded.includes("    [indented](#bib.bib1)"), "indented code changed");
assert(
  degraded.includes("Unclosed ` and Smith 2020."),
  "a link after an unmatched backtick remained clickable"
);
assert(
  degraded.includes("Jones 2021") && !degraded.includes("[legacy]:"),
  "a reference-style bibliography link was not degraded"
);
assert(
  degraded.includes("Figure reference") &&
    !degraded.includes("!Figure reference"),
  "a bibliography image link was degraded into broken image syntax"
);
assert(
  degraded.includes("Destination Smith 2020") &&
    degraded.includes("Label Smith\n2020") &&
    degraded.includes("Title Smith 2020"),
  "a multiline CommonMark bibliography link was not degraded"
);
assert(
  degraded.includes("`[multiline\ncode](#bib.bib1)`"),
  "a multiline code span was rewritten"
);
'''
    )
    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_persists_directory_handles_per_source_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcDirectoryKeyTest = {
    state: state,
    directoryHandleKey: directoryHandleKey,
    rememberDirectoryHandle: rememberDirectoryHandle,
    restoreDirectoryHandle: restoreDirectoryHandle
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcDirectoryKeyTest;
var puts = [];
var gets = [];
var stored = new Map();
var database = {
  objectStoreNames: {contains: function () { return true; }},
  transaction: function () {
    return {objectStore: function () {
      return {
        put: function (handle, key) {
          puts.push(key);
          stored.set(key, handle);
        },
        get: function (key) {
          gets.push(key);
          var request = {};
          setTimeout(function () {
            request.result = stored.get(key);
            request.onsuccess();
          }, 0);
          return request;
        }
      };
    }};
  }
};
globalThis.indexedDB = {open: function () {
  var request = {result: database};
  setTimeout(function () { request.onsuccess(); }, 0);
  return request;
}};
function identity(digest) {
  return {
    source_format: "markdown",
    artifact_digest: digest.repeat(64),
    size: 4,
    rich_document_digest: digest.repeat(64)
  };
}
var bookHandle = {queryPermission: async function () { return "denied"; }};
var paperHandle = {queryPermission: async function () { return "denied"; }};
(async function () {
  helpers.state.payload = {source_identity: identity("a")};
  var bookKey = helpers.directoryHandleKey();
  await helpers.rememberDirectoryHandle(bookHandle);
  helpers.state.payload = {source_identity: identity("b")};
  var paperKey = helpers.directoryHandleKey();
  await helpers.rememberDirectoryHandle(paperHandle);
  helpers.state.payload = {source_identity: identity("a")};
  await helpers.restoreDirectoryHandle();
  assert(bookKey !== paperKey, "different sources shared one directory key");
  assert(
    puts.join(",") === [bookKey, paperKey].join(",") &&
      gets.join(",") === bookKey && !puts.includes("project"),
    "directory persistence used a global project key"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )
    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_speech_uses_structured_paragraphs_and_current_viewport() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    queue_source = javascript[
        javascript.index("function buildSpeechQueue(selectedRoles)") :
        javascript.index("function speechSegmentText(")
    ]
    assert "loadAllPayload(false);" in queue_source
    assert "renderAllChunks();" not in queue_source
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcSpeechTest = {
    normalizeSpeechText: normalizeSpeechText,
    speechInlineText: speechInlineText,
    sourceSpeechText: sourceSpeechText,
    speechLanguage: speechLanguage,
    speechSegmentNode: speechSegmentNode,
    viewportNodeIndex: viewportNodeIndex,
    speakSpeechIndex: speakSpeechIndex,
    moveSpeech: moveSpeech,
    renderSpeechPlaylist: renderSpeechPlaylist,
    toggleSpeechPause: toggleSpeechPause,
    setSpeechRate: setSpeechRate,
    setSpeechStatus: setSpeechStatus,
    positionSpeechRateMenu: positionSpeechRateMenu,
    speechVoiceDescription: speechVoiceDescription,
    state: state
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function row(top, bottom) {
  return {getBoundingClientRect: function () {
    return {top: top, bottom: bottom};
  }};
}
var helpers = globalThis.__alcSpeechTest;
globalThis.innerHeight = 600;
var controls = {
  "alc-speech-rate": {value: "1.2"},
  "alc-speech-play": {disabled: false},
  "alc-speech-pause": {disabled: false, textContent: ""},
  "alc-speech-stop": {disabled: false},
  "alc-speech-previous": {disabled: false},
  "alc-speech-next": {disabled: false},
  "alc-speech-status": {textContent: "", dataset: {}}
};
var toolbarBottom = 0;
var speechRows = {};
var glossarySpeechRow = {};
var statusProgress = {textContent: "", dataset: {}};
var statusTitle = {textContent: ""};
var statusPlayer = {
  querySelector: function (selector) {
    if (selector === ".alc-speech-player-progress") return statusProgress;
    if (selector === ".alc-speech-player-title") return statusTitle;
    return null;
  },
  querySelectorAll: function () { return []; }
};
globalThis.document = {
  documentElement: {clientHeight: 600, lang: "zh-CN"},
  getElementById: function (id) { return controls[id] || speechRows[id] || null; },
  querySelector: function (selector) {
    if (selector.includes("data-glossary-entry-id")) return glossarySpeechRow;
    if (selector !== ".alc-fixed-tools") return null;
    return {getBoundingClientRect: function () { return {bottom: toolbarBottom}; }};
  },
  querySelectorAll: function (selector) {
    return selector === ".alc-speech-player" ? [statusPlayer] : [];
  }
};
helpers.state.payload = {
  publication: {
    labels: {},
    reader_profile: {source_language: "en", target_language: "zh-CN"}
  }
};
assert(
  helpers.speechSegmentNode({glossaryEntryId: "term-reader"}) ===
    glossarySpeechRow,
  "glossary speech did not retain its active row identity"
);
assert(
  helpers.sourceSpeechText({kind: "paragraph", payload: {text: " A  paragraph. "}}) ===
    "A paragraph.",
  "source paragraph was not preserved as one speech segment"
);
assert(
  helpers.sourceSpeechText({
    kind: "list", payload: {items: [{text: "First"}, {text: "Second"}]}
  }) === "First\\nSecond",
  "structured list items were not preserved"
);
assert(
  helpers.sourceSpeechText({kind: "equation", payload: {tex: "x^2"}}) === "",
  "display equation unexpectedly became a speech paragraph"
);
assert(
  helpers.speechInlineText([
    {kind: "text", text: "Energy "},
    {kind: "math", source: "$E=mc^2$"},
    {kind: "text", text: "."}
  ], "Energy $E=mc^2$.") === "Energy.",
  "inline math was spoken instead of using structured prose spans"
);
assert(
  helpers.speechLanguage("source", null) === "en" &&
    helpers.speechLanguage("translation", null) === "zh-CN",
  "speech language did not follow content role"
);
var above = row(-300, -20);
var visible = row(-10, 180);
var below = row(700, 820);
var queue = [
  {row: above},
  {row: visible},
  {row: visible},
  {row: below}
];
assert(
  helpers.viewportNodeIndex(queue.map(item => item.row)) === 1,
  "speech did not start at first selected segment in visible source row"
);
above.getBoundingClientRect = function () { return {top: -600, bottom: -500}; };
visible.getBoundingClientRect = function () { return {top: -300, bottom: -200}; };
below.getBoundingClientRect = function () { return {top: 40, bottom: 160}; };
assert(
  helpers.viewportNodeIndex(queue.map(item => item.row)) === 3,
  "speech did not follow viewport after scrolling"
);
toolbarBottom = 36;
visible.getBoundingClientRect = function () { return {top: -350, bottom: 16}; };
below.getBoundingClientRect = function () { return {top: 16, bottom: 94}; };
assert(
  helpers.viewportNodeIndex(queue.map(item => item.row)) === 3,
  "speech treated a sliver hidden behind the toolbar as the current paragraph"
);

function speakingNode() {
  return {
    active: false,
    scrolled: false,
    classList: {
      add: function () { this.owner.active = true; },
      remove: function () { this.owner.active = false; },
      owner: null
    },
    scrollIntoView: function () { this.scrolled = true; }
  };
}
var firstNode = speakingNode();
var secondNode = speakingNode();
var titleSourceNode = speakingNode();
var titleTargetNode = speakingNode();
firstNode.classList.owner = firstNode;
secondNode.classList.owner = secondNode;
speechRows["block-b1"] = {querySelector: function () { return firstNode; }};
speechRows["block-b2"] = {querySelector: function () { return secondNode; }};
controls["alc-book-header"] = {
  querySelector: function (selector) {
    return selector.includes("h1") ? titleSourceNode : titleTargetNode;
  }
};
var spoken = [];
var pauses = 0;
var resumes = 0;
globalThis.matchMedia = function () { return {matches: true}; };
globalThis.SpeechSynthesisUtterance = function (text) { this.text = text; };
globalThis.speechSynthesis = {
  cancel: function () {},
  speak: function (utterance) { spoken.push(utterance); },
  pause: function () { pauses += 1; },
  resume: function () { resumes += 1; }
};
helpers.state.speechSupported = true;
helpers.state.speechReady = true;
helpers.state.speechVoices = [{
  name: "System English", lang: "en-US", voiceURI: "system-en", localService: true
}];
helpers.state.speechVoiceIdentity = "";
helpers.state.speechRate = 1.2;
assert(
  helpers.speechVoiceDescription({
    name: "Samantha", lang: "en-US", localService: true
  }) === "Samantha · en-US · 本机",
  "voice description omitted the automatic voice details"
);
var dockRateMenu = {
  dataset: {},
  style: {},
  getBoundingClientRect: function () { return {height: 300}; }
};
var dockTriggerTop = 400;
var dockPlayerBottom = 450;
var dockRateTrigger = {
  getBoundingClientRect: function () {
    return {
      left: 264, right: 320, top: dockTriggerTop,
      bottom: dockTriggerTop + 32, width: 56
    };
  }
};
var dockRatePlayer = {
  dataset: {playerKind: "dock"},
  getBoundingClientRect: function () {
    return {
      left: 0, right: 330,
      top: dockPlayerBottom - 70, bottom: dockPlayerBottom
    };
  },
  querySelector: function (selector) {
    return selector === ".alc-speech-rate-menu" ? dockRateMenu : dockRateTrigger;
  }
};
helpers.positionSpeechRateMenu(dockRatePlayer);
assert(
  dockRateMenu.style.width === "56px" &&
    dockRateMenu.style.right === "10px" &&
    dockRateMenu.style.top === "auto" &&
    dockRateMenu.style.bottom === "55px" &&
    dockRateMenu.style.maxHeight === "none" &&
    dockRateMenu.dataset.layout === "list",
  "docked rate menu did not stay above and overlap the player without scrolling"
);
dockTriggerTop = 250;
dockPlayerBottom = 300;
helpers.positionSpeechRateMenu(dockRatePlayer);
assert(
  dockRateMenu.dataset.layout === "grid" &&
    dockRateMenu.style.width === "112px" &&
    dockRateMenu.style.bottom === "55px" &&
    dockRateMenu.style.maxHeight === "none",
  "short dock viewport did not compact the full rate menu into two columns"
);
helpers.setSpeechStatus("当前段落无法朗读。", true);
assert(
  statusProgress.textContent === "当前段落无法朗读。" &&
    statusProgress.dataset.kind === "error",
  "speech error updated only the hidden live region"
);
helpers.setSpeechStatus("准备朗读。", false);
helpers.state.primaryTitleBlockId = "title-block";
helpers.state.primaryTitleFragmentId = "title-fragment";
assert(
  helpers.speechSegmentNode({
    blockId: "title-block", role: "source", fragmentId: null
  }) === titleSourceNode &&
  helpers.speechSegmentNode({
    blockId: "title-block", role: "translation", fragmentId: "title-fragment"
  }) === titleTargetNode,
  "promoted title speech did not target the visible header"
);
helpers.state.speechQueue = [
  {text: "First paragraph.", language: "en", role: "source", blockId: "b1"},
  {text: "", language: "zh-CN", role: "note", blockId: "empty", fragmentId: "empty"},
  {text: "第二段。", language: "zh-CN", role: "translation", blockId: "b2", fragmentId: "f2"}
];
helpers.speakSpeechIndex(0);
assert(
  spoken.length === 1 && spoken[0].text === "First paragraph." &&
    spoken[0].lang === "en-US" && spoken[0].rate === 1.2 &&
    firstNode.active && firstNode.scrolled &&
    controls["alc-speech-status"].textContent === "",
  "first speech paragraph duplicated progress outside the player"
);
helpers.toggleSpeechPause();
helpers.toggleSpeechPause();
assert(pauses === 1 && resumes === 1, "pause/resume did not reach browser speech");
helpers.setSpeechRate(1.5);
assert(
  spoken.length === 2 && spoken[1].text === "First paragraph." &&
    spoken[1].rate === 1.5 && firstNode.active,
  "rate change did not immediately restart the current paragraph"
);
spoken[1].onend();
assert(
  spoken.length === 3 && spoken[2].text === "第二段。" &&
    spoken[2].lang === "zh-CN" && !firstNode.active && secondNode.active,
  "speech did not advance by structured paragraph"
);
helpers.state.speechLoopMode = "one";
spoken[2].onend();
assert(
  spoken.length === 4 && spoken[3].text === "第二段。",
  "single-paragraph loop did not repeat the current paragraph"
);
helpers.state.speechLoopMode = "none";
helpers.moveSpeech(-1);
assert(
  spoken.length === 5 && spoken[4].text === "First paragraph." &&
    helpers.state.speechIndex === 0,
  "Previous did not skip an unreadable fragment in the backward direction"
);
spoken[4].onend();
assert(
  spoken.length === 6 && spoken[5].text === "第二段。" &&
    helpers.state.speechIndex === 2,
  "forward playback did not skip an unreadable fragment"
);
spoken[5].onend();
assert(
  !helpers.state.speechPlaying && !secondNode.active &&
    controls["alc-speech-status"].textContent === "朗读完成。",
  "speech completion did not clear active state"
);

var playlistUpdates = [];
var playlistRebuilds = 0;
var playlistHeading = {textContent: ""};
var playlistList = {replaceChildren: function () { playlistRebuilds += 1; }};
var playlistRoot = {
  _alcSpeechQueue: helpers.state.speechQueue,
  _alcSpeechCurrentIndex: 0,
  querySelector: function (selector) {
    if (selector === "h2") return playlistHeading;
    if (selector === "ol") return playlistList;
    var match = /data-speech-index="(\\d+)"/.exec(selector);
    if (match) {
      return {
        setAttribute: function (_name, value) {
          playlistUpdates.push([Number(match[1]), value]);
        }
      };
    }
    return null;
  }
};
helpers.state.speechPlaying = true;
helpers.state.speechIndex = 2;
helpers.renderSpeechPlaylist({
  querySelector: function () { return playlistRoot; }
});
assert(
  playlistRebuilds === 0 &&
    JSON.stringify(playlistUpdates) === JSON.stringify([[0, "false"], [2, "true"]]),
  "an unchanged open playlist rebuilt its complete queue"
);
"""
    )
    completed = subprocess.run(
        [node, "-"], input=instrumented, capture_output=True, text=True
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_contents_sidebar_resizes_and_collapses_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {state: state, setupContents: setupContents};
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function Node() {
  this.attrs = {};
  this.listeners = {};
  this.style = {
    values: {},
    setProperty: function (name, value) { this.values[name] = value; }
  };
  this.classes = new Set();
  this.classList = {
    owner: this,
    toggle: function (name, enabled) {
      if (enabled) this.owner.classes.add(name);
      else this.owner.classes.delete(name);
    },
    add: function (name) { this.owner.classes.add(name); },
    remove: function (name) { this.owner.classes.delete(name); },
    contains: function (name) { return this.owner.classes.has(name); }
  };
}
Node.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
Node.prototype.addEventListener = function (name, callback) {
  (this.listeners[name] = this.listeners[name] || []).push(callback);
};
Node.prototype.dispatch = function (name, event) {
  (this.listeners[name] || []).forEach(function (callback) { callback(event); });
};
var shell = new Node();
var contents = new Node();
var toggle = new Node();
var resizer = new Node();
var root = new Node();
var nodes = {
  "alc-shell": shell,
  "alc-contents": contents,
  "alc-contents-toggle": toggle,
  "alc-contents-resizer": resizer
};
globalThis.document = {
  documentElement: root,
  getElementById: function (id) { return nodes[id]; }
};
globalThis.innerWidth = 1400;
globalThis.getComputedStyle = function () { return {fontSize: "16px"}; };
globalThis.matchMedia = function () { return {matches: false}; };
var windowListeners = {};
globalThis.addEventListener = function (name, callback) {
  (windowListeners[name] = windowListeners[name] || []).push(callback);
};
globalThis.removeEventListener = function (name, callback) {
  windowListeners[name] = (windowListeners[name] || []).filter(function (item) {
    return item !== callback;
  });
};
function windowDispatch(name, event) {
  (windowListeners[name] || []).slice().forEach(function (callback) {
    callback(event || {});
  });
}
globalThis.__alcReaderTest.state.payload = {
  publication: {labels: {}, reader_profile: {target_language: "en"}}
};
globalThis.__alcReaderTest.setupContents();
assert(
  shell.style.values["--alc-contents-width"] === "288px" &&
    resizer.attrs["aria-valuemin"] === "192" &&
    resizer.attrs["aria-valuemax"] === "512",
  "sidebar did not initialize its bounded width"
);
resizer.dispatch("pointerdown", {
  button: 0, clientX: 288, preventDefault: function () {}
});
windowDispatch("pointermove", {clientX: 420, preventDefault: function () {}});
windowDispatch("pointerup");
assert(
  shell.style.values["--alc-contents-width"] === "420px",
  "pointer drag did not resize the sidebar"
);
resizer.dispatch("pointerdown", {
  button: 0, clientX: 420, preventDefault: function () {}
});
windowDispatch("pointermove", {clientX: 180, preventDefault: function () {}});
assert(
  !shell.classList.contains("contents-collapsed") &&
    shell.style.values["--alc-contents-width"] === "192px",
  "sidebar collapsed without enough minimum-width overshoot"
);
windowDispatch("pointermove", {clientX: 150, preventDefault: function () {}});
assert(
  shell.classList.contains("contents-collapsed") &&
    toggle.attrs["aria-expanded"] === "false",
  "dragging beyond the minimum-width overshoot did not collapse the sidebar"
);
toggle.onclick();
assert(
  !shell.classList.contains("contents-collapsed") &&
    shell.style.values["--alc-contents-width"] === "192px",
  "contents button did not restore the previous width"
);
resizer.dispatch("pointerdown", {
  button: 0, clientX: 188, preventDefault: function () {}
});
windowDispatch("pointermove", {clientX: 220, preventDefault: function () {}});
windowDispatch("pointerup");
assert(
  !shell.classList.contains("contents-collapsed") &&
    shell.style.values["--alc-contents-width"] === "224px",
  "right drag from minimum width incorrectly collapsed the sidebar"
);
resizer.dispatch("keydown", {key: "Home", preventDefault: function () {}});
assert(
  shell.style.values["--alc-contents-width"] === "192px",
  "Home did not select the minimum sidebar width"
);
resizer.dispatch("keydown", {key: "ArrowLeft", preventDefault: function () {}});
assert(
  shell.classList.contains("contents-collapsed"),
  "keyboard resize below the minimum did not collapse"
);
toggle.onclick();
resizer.dispatch("keydown", {key: "End", preventDefault: function () {}});
assert(
  shell.style.values["--alc-contents-width"] === "512px",
  "End did not select the maximum sidebar width"
);
"""
    )
    subprocess.run(
        [node, "-"], input=instrumented, check=True, capture_output=True, text=True
    )


def test_reader_renders_structured_document_notes_default_hidden() -> None:
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")

    assert "metadata.document_notes" in javascript
    assert '"ac.document.document_notes.v1"' in javascript
    assert '"ac-document-data-note"' in javascript
    assert 'documentData: traditional ? "文件資料" : "文档数据"' in javascript
    assert 'documentData: "Document data"' in javascript
    assert '"page-markers"' in javascript
    assert "pageMarkersVisible: false" in javascript
    assert ".alc-show-page-markers .ac-document-data-note" in stylesheet


def test_reader_exposes_lightweight_supplement_coverage_download() -> None:
    javascript = _text("reader.js")

    assert "appendSupplementCoverage(list)" in javascript
    assert "coverage.report_logical_name" in javascript
    assert 'link.download = coverage.report_filename ||' in javascript
    assert "Download complete report" in javascript


def test_reader_exposes_lightweight_editorial_review_download() -> None:
    javascript = _text("reader.js")

    assert "appendEditorialReview(list)" in javascript
    assert "review.report_logical_name" in javascript
    assert 'link.download = review.report_filename ||' in javascript
    assert "Download editorial review" in javascript


def test_reader_contract_helpers_execute_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    markdown_it = _text("markdown-it/markdown-it.min.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
module = undefined;
exports = undefined;
define = undefined;
"""
        + markdown_it
        + "\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    browserCreatedHistory: browserCreatedHistory,
    bibliographyIndex: bibliographyIndex,
    effectiveEquationLabel: effectiveEquationLabel,
    fragmentsDirectory: fragmentsDirectory,
    labels: labels,
    setStatus: setStatus,
    updateDirectoryControl: updateDirectoryControl,
    stableStringify: stableStringify,
    setupMarkdown: setupMarkdown,
    canonicalizeLegacyDisplayMath: canonicalizeLegacyDisplayMath,
    buildRenderChunks: buildRenderChunks,
    isPdfPageMarkerBlock: isPdfPageMarkerBlock,
    isStandaloneHtmlCommentBlock: isStandaloneHtmlCommentBlock,
    katexCandidates: katexCandidates,
    katexTex: katexTex,
    syncVisibilityRoles: syncVisibilityRoles,
    validateIntegerJson: validateIntegerJson,
    validateRevisionMetadata: validateRevisionMetadata
  };
}());
var helpers = globalThis.__alcReaderTest;
helpers.setupMarkdown();
var nestedMathTex = String.raw`\\langle\\Psi^{-}|M|\\Psi^{-}\\rangle>\\mbox{$\\textstyle\\frac{1}{2}$}`;
var nestedMathTokens = helpers.state.md.parseInline(
  "成立 $" + nestedMathTex + "$。", {}
)[0].children.filter(function (token) { return token.type === "alc_math_inline"; });
if (
  nestedMathTokens.length !== 1 ||
  nestedMathTokens[0].content !== nestedMathTex
) {
  throw new Error("old-style nested TeX math shift split Markdown math");
}
var legacyDisplayTokens = helpers.state.md.parse(
  String.raw`$$q(z)=-1+\frac{1+z}{2E(z)^2}。$$`, {}
);
if (
  legacyDisplayTokens.length !== 1 ||
  legacyDisplayTokens[0].type !== "alc_math_block" ||
  legacyDisplayTokens[0].content !==
    String.raw`q(z)=-1+\frac{1+z}{2E(z)^2}。`
) {
  throw new Error("legacy single-line display math left visible delimiters");
}
if (
  helpers.canonicalizeLegacyDisplayMath(
    "推导：\\n\\n$$q(z)=-1。$$\\n\\n完成。"
  ) !== "推导：\\n\\n$$\\nq(z)=-1。\\n$$\\n\\n完成。"
) {
  throw new Error("legacy supplemental display math was not canonicalized");
}
var fencedLegacyDisplay = "```text\\n$$q(z)=-1。$$\\n```";
if (
  helpers.canonicalizeLegacyDisplayMath(fencedLegacyDisplay) !==
  fencedLegacyDisplay
) {
  throw new Error("fenced legacy display math was rewritten");
}
helpers.validateIntegerJson({value: 4, nested: [1, 2]}, "fixture");
var rejected = false;
try {
  helpers.validateIntegerJson({value: 1.5}, "fixture");
} catch (_error) {
  rejected = true;
}
if (!rejected) throw new Error("non-integer JSON was accepted");
if (!helpers.isPdfPageMarkerBlock({
  kind: "paragraph",
  payload: {text: "<!-- PDF_PAGE: 1 -->"}
})) {
  throw new Error("PDF page marker remained visible");
}
if (helpers.isPdfPageMarkerBlock({
  kind: "paragraph",
  payload: {text: "<!-- note --> visible text"}
})) {
  throw new Error("visible paragraph text was hidden with its comment");
}
if (helpers.isPdfPageMarkerBlock({
  kind: "paragraph",
  payload: {text: "<!-- note -->"}
})) {
  throw new Error("ordinary HTML comment was treated as a PDF page marker");
}
if (!helpers.isStandaloneHtmlCommentBlock({
  kind: "paragraph",
  payload: {text: "  <!-- retained extraction note -->\\n"}
})) {
  throw new Error("standalone HTML comment block remained visible");
}
if (helpers.isStandaloneHtmlCommentBlock({
  kind: "paragraph",
  payload: {text: "<!-- note --> visible text"}
})) {
  throw new Error("mixed visible source text was hidden with its comment");
}
if (helpers.isStandaloneHtmlCommentBlock({
  kind: "code",
  payload: {text: "<!-- code comment -->"}
})) {
  throw new Error("code comment was hidden");
}
if (
  helpers.katexTex(String.raw`a&=b\\\\&=c`) !==
  String.raw`\\begin{aligned}a&=b\\\\&=c\\end{aligned}`
) {
  throw new Error("bare TeX alignment rows were not wrapped for KaTeX");
}
if (helpers.katexTex(String.raw`A\\&B`) !== String.raw`A\\&B`) {
  throw new Error("escaped TeX ampersand was treated as an alignment tab");
}
if (
  helpers.katexTex(String.raw`\\begin{matrix}a&b\\end{matrix}`) !==
  String.raw`\\begin{matrix}a&b\\end{matrix}`
) {
  throw new Error("existing TeX environment was wrapped a second time");
}
var matrixCandidates = helpers.katexCandidates(
  String.raw`\\left[{cc}a&b\\\\c&d\\right]`
);
if (
  !matrixCandidates.some(function (candidate) {
    return candidate.includes(String.raw`\\begin{array}{cc}`) &&
      candidate.includes(String.raw`\\end{array}\\right]`);
  })
) {
  throw new Error("OCR matrix shorthand was not repaired for KaTeX");
}
if (
  !matrixCandidates.some(function (candidate) {
    return candidate.includes(String.raw`\\bigl[`) &&
      candidate.includes(String.raw`\\bigr]`);
  })
) {
  throw new Error("cross-row scalable delimiter fallback is missing");
}
var repeatedScriptCandidates = helpers.katexCandidates(
  String.raw`A^{*}^{\\mathrm{T}} + \\omega_A^*^\\dagger + \\chi_n^\\dagger'`
);
if (
  !repeatedScriptCandidates.some(function (candidate) {
    return candidate.includes(String.raw`{A^{*}}^{\\mathrm{T}}`) &&
      candidate.includes(String.raw`{\\omega_A^*}^\\dagger`) &&
      candidate.includes(String.raw`{\\chi_n^\\dagger}'`);
  })
) {
  throw new Error("repeated TeX superscripts were not grouped for KaTeX");
}
var groupedDelimiterCandidates = helpers.katexCandidates(
  String.raw`\\Big{|}x\\Big{|}^{2}+\\vphantom{\\Biggl{(}}`
);
if (
  !groupedDelimiterCandidates.some(function (candidate) {
    return candidate.includes(String.raw`\\Big|x\\Big|^{2}`) &&
      candidate.includes(String.raw`\\vphantom{\\Biggl(}`);
  })
) {
  throw new Error("grouped TeX size delimiters were not repaired for KaTeX");
}
var oldMathShiftCandidates = helpers.katexCandidates(
  String.raw`F>\\mbox{$\\textstyle\\frac{1}{2}$}`
);
if (
  !oldMathShiftCandidates.some(function (candidate) {
    return candidate === String.raw`F>{\\textstyle\\frac{1}{2}}`;
  })
) {
  throw new Error("old-style nested TeX math shift was not repaired for KaTeX");
}
if (
  !helpers.katexCandidates(String.raw`x,\\mbox{ where }y`).some(function (candidate) {
    return candidate === String.raw`x,\\text{ where }y`;
  })
) {
  throw new Error("legacy TeX text box was not repaired for KaTeX");
}
var strippedArrayCandidates = helpers.katexCandidates(
  String.raw`[]{cc|cl}a&&b&c\\\\d&e&f&g\\\\`
);
if (
  !strippedArrayCandidates.some(function (candidate) {
    return candidate === String.raw`\\begin{array}{cc|cl}a&&b&c\\\\d&e&f&g\\\\\\end{array}`;
  })
) {
  throw new Error("legacy stripped TeX array environment was not repaired");
}
var optionalArrayCandidates = helpers.katexCandidates(
  String.raw`\\begin{array}[]{cc}a&b\\end{array}`
);
if (
  !optionalArrayCandidates.some(function (candidate) {
    return candidate === String.raw`\\begin{array}{cc}a&b\\end{array}`;
  })
) {
  throw new Error("empty TeX array position option was not removed");
}
if (
  !helpers.katexCandidates("x+\frac{a}{b}").some(function (candidate) {
    return candidate === String.raw`x+\\frac{a}{b}`;
  })
) {
  throw new Error("legacy form-feed frac escape was not repaired for KaTeX");
}
if (helpers.stableStringify({b: 2, a: 1}) !== '{"a":1,"b":2}') {
  throw new Error("canonical JSON ordering changed");
}
if (!helpers.browserCreatedHistory([{
  revision: 1,
  parent_semantic_digest: null,
  semantic_digest: "d".repeat(64),
  provenance: {producer: "alc-render-browser"}
}])) {
  throw new Error("browser-created fragment history was not recognized");
}
if (helpers.browserCreatedHistory([{
  revision: 1,
  parent_semantic_digest: null,
  semantic_digest: "e".repeat(64),
  provenance: {producer: "alc-translate"}
}])) {
  throw new Error("stale machine fragment history was treated as user-owned");
}
helpers.state.payload = {
  selected_roles: ["translation", "custom-a"],
  source_identity: {
    source_format: "markdown",
    media_type: "text/markdown",
    artifact_digest: "a".repeat(64),
    size: 4,
    rich_document_digest: "b".repeat(64)
  },
  block_fingerprints: {"block-1": "c".repeat(64)},
  publication: {
    source_document: {
      blocks: [{
        block_id: "block-1",
        kind: "paragraph",
        ordinal: 0,
        locator: {line_start: 1}
      }],
      sections: [],
      metadata: {
        equation_label_reconciliation: {
          "eq-1": {effective_label: " (7) "}
        }
      }
    },
    outline: [],
    bibliography: [],
    labels: {},
    reader_profile: {target_language: "zh-CN"}
  }
};
helpers.state.selected = new Map([
  ["guide-1", {fragment_id: "guide-1", priority: 30, role: "guide"}],
  ["custom-1", {fragment_id: "custom-1", priority: 20, role: "custom-a"}]
]);
helpers.syncVisibilityRoles();
if (
  JSON.stringify(helpers.state.roleOrder) !==
  JSON.stringify(["translation", "custom-a", "guide"])
) {
  throw new Error("dynamic selected roles were not discovered in stable order");
}
helpers.state.payload.publication.labels.translation = "译名";
if (
  helpers.labels().translation !== "译文" ||
  helpers.labels().translatedTerm !== "译文"
) {
  throw new Error("legacy simplified Chinese translation labels were not normalized");
}
helpers.state.payload.publication.reader_profile.target_language = "zh-TW";
helpers.state.payload.publication.labels.translation = "譯名";
if (
  helpers.labels().translation !== "譯文" ||
  helpers.labels().translatedTerm !== "譯文"
) {
  throw new Error("legacy traditional Chinese translation labels were not normalized");
}
helpers.state.payload.publication.reader_profile.target_language = "zh-CN";
helpers.state.payload.publication.labels = {};
helpers.state.payload.publication.bibliography = [
  {
    evidence_id: "ref-english",
    title: "Paper",
    source: "https://arxiv.org/abs/1811.00024",
    arxiv_ids: ["1811.00024"]
  },
  {
    evidence_id: "ref-translated",
    title: "论文",
    source: "https://arxiv.org/abs/1811.00024/",
    arxiv_ids: ["arXiv:1811.00024"]
  },
  {
    evidence_id: "ref-other",
    title: "Other",
    source: "https://example.test/other"
  }
];
helpers.state.bibliographyIndexCache = null;
var bibliography = helpers.bibliographyIndex();
if (
  bibliography.groups.length !== 2 ||
  bibliography.numbers["ref-english"] !== 1 ||
  bibliography.numbers["ref-translated"] !== 1 ||
  bibliography.targets["ref-translated"] !== "ref-english" ||
  bibliography.numbers["ref-other"] !== 2
) {
  throw new Error("duplicate bibliography identities were not consolidated");
}
var connectControl = {
  attrs: {},
  title: "",
  setAttribute: function (name, value) { this.attrs[name] = value; }
};
var statusControl = {textContent: "", dataset: {}, hidden: true};
globalThis.document = {
  getElementById: function (id) {
    if (id === "alc-connect") return connectControl;
    if (id === "alc-storage-status") return statusControl;
    return null;
  }
};
helpers.state.directory = null;
helpers.updateDirectoryControl();
if (
  connectControl.title !== "新建保存位置" ||
  connectControl.attrs["aria-label"] !== "新建保存位置"
) {
  throw new Error("missing-directory button label changed");
}
helpers.state.directory = {};
helpers.updateDirectoryControl();
if (
  connectControl.title !== "更改保存位置" ||
  connectControl.attrs["aria-label"] !== "更改保存位置"
) {
  throw new Error("connected-directory button label changed");
}
var statusTimers = [];
var clearedStatusTimers = [];
window.setTimeout = function (callback, delay) {
  statusTimers.push({callback: callback, delay: delay});
  return statusTimers.length;
};
window.clearTimeout = function (timer) {
  clearedStatusTimers.push(timer);
};
helpers.setStatus("Save or cancel the current edit first.", "error");
if (
  statusControl.hidden || statusTimers.length !== 1 ||
  statusTimers[0].delay !== 3000
) {
  throw new Error("toolbar status did not receive a three-second expiry");
}
helpers.setStatus("Newer status");
if (clearedStatusTimers[0] !== 1) {
  throw new Error("new toolbar status did not cancel the previous expiry");
}
statusTimers[0].callback();
if (statusControl.textContent !== "Newer status" || statusControl.hidden) {
  throw new Error("stale expiry cleared a newer toolbar status");
}
statusTimers[1].callback();
if (statusControl.textContent || !statusControl.hidden) {
  throw new Error("toolbar status remained visible after three seconds");
}
helpers.validateRevisionMetadata({
  schema_version: "alc.render.fragment_revision.v3",
  source: helpers.state.payload.source_identity,
  fragment_id: "note-1",
  revision: 1,
  parent_semantic_digest: null,
  anchor: {
    kind: "block",
    target_id: "block-1",
    related_blocks: [{
      block_id: "block-1",
      kind: "paragraph",
      ordinal: 0,
      locator: {line_start: 1},
      content_fingerprint: "c".repeat(64)
    }]
  },
  priority: 110,
  role: "note",
  language: "en",
  title: null,
  citation_ids: [],
  appearance: null,
  deleted: false,
  provenance: {producer: "test"}
});
helpers.setupMarkdown();
helpers.state.payload.resources = [{
  artifact_digest: "f".repeat(64),
  media_type: "image/jpeg",
  logical_name: "note-figures/owned.jpg",
  size: 3,
  data_uri: "data:image/jpeg;base64,AAEC"
}];
var ownedImageMarkup = helpers.state.md.render(
  "![owned diagram](note-figures/owned.jpg)"
);
if (
  !ownedImageMarkup.includes('<img class="alc-markdown-image"') ||
  !ownedImageMarkup.includes('src="data:image/jpeg;base64,AAEC"') ||
  !ownedImageMarkup.includes('alt="owned diagram"')
) {
  throw new Error("publication-owned Markdown image was not rendered");
}
var imageMarkup = helpers.state.md.render(
  "![remote](https://example.test/image.png)"
);
if (!imageMarkup.includes("alc-markdown-image")) {
  throw new Error("Markdown image placeholder is missing");
}
if (/\b(?:src|href)=/.test(imageMarkup)) {
  throw new Error("Markdown image placeholder retained a fetchable URL");
}
var nearMatchImageMarkup = helpers.state.md.render(
  "![near match](note-figures/owned.jpg?variant=1)"
);
if (
  !nearMatchImageMarkup.includes("alc-markdown-image") ||
  /\b(?:src|href)=/.test(nearMatchImageMarkup) ||
  nearMatchImageMarkup.includes("data:image/jpeg")
) {
  throw new Error("Markdown image resource matching was not exact");
}
if (
  helpers.effectiveEquationLabel({block_id: "eq-1"}, {label: "(3)"}) !== "(7)"
) {
  throw new Error("effective equation label was not preferred");
}
if (
  helpers.effectiveEquationLabel({block_id: "eq-2"}, {label: " (3) "}) !== "(3)"
) {
  throw new Error("equation payload label fallback changed");
}
var requestedDirectory = null;
helpers.state.directory = {
  getDirectoryHandle: function (name, options) {
    requestedDirectory = {name: name, create: options.create};
    return Promise.resolve({name: name});
  }
};
helpers.fragmentsDirectory(true).then(function (handle) {
  if (
    requestedDirectory.name !== "fragments" ||
    requestedDirectory.create !== true ||
    handle.name !== "fragments"
  ) {
    throw new Error("fragment storage used a semantic ID as a directory name");
  }
});
var chunkBlocks = Array.from({length: 95}, function (_value, index) {
  return {block_id: "chunk-block-" + index};
});
var chunks = helpers.buildRenderChunks(chunkBlocks, [{
  block_start: 0,
  block_end: 10,
  level: 1,
  ordinal: 0,
  path: ["front"],
  title: "Front"
}, {
  block_start: 10,
  block_end: 95,
  level: 1,
  ordinal: 1,
  path: ["body"],
  title: "Body"
}]);
var contentChunks = chunks.filter(function (item) {
  return item.kind === "content";
});
if (
  contentChunks[0].block_start !== 0 ||
  contentChunks[contentChunks.length - 1].block_end !== 95 ||
  contentChunks.some(function (item) {
    return item.block_end - item.block_start > 36;
  }) ||
  chunks[chunks.length - 1].kind !== "appendices"
) {
  throw new Error("progressive render chunks lost coverage or bounds");
}
for (var chunkIndex = 1; chunkIndex < contentChunks.length; chunkIndex += 1) {
  if (
    contentChunks[chunkIndex - 1].block_end !==
    contentChunks[chunkIndex].block_start
  ) {
    throw new Error("progressive render chunks contain a gap");
  }
}
"""
    )

    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_steady_save_uses_constant_filesystem_work_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    saveEditor: saveEditor,
    deleteEditor: deleteEditor,
    installRenderSpies: function (rerender) {
      renderDiagnostics = function () {};
      rerenderChunk = rerender;
    },
    installPostCommitFailureSpies: function (failures, recoveredCards, titleSyncs) {
      var originalGroupRefresh = refreshFragmentGroup;
      var originalChunkRefresh = refreshChunkForAnchor;
      refreshFragmentGroup = function (fragmentId, anchor) {
        if (failures.group) throw new Error("group refresh failed");
        return originalGroupRefresh(fragmentId, anchor);
      };
      refreshChunkForAnchor = function (anchor) {
        if (failures.chunk) throw new Error("chunk refresh failed");
        return originalChunkRefresh(anchor);
      };
      replaceFragmentCard = function (fragmentId, anchor) {
        recoveredCards.push({fragmentId: fragmentId, anchor: anchor});
      };
      syncPromotedTitleSurface = function () { titleSyncs.count += 1; };
    }
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var anchor = {
  kind: "block",
  target_id: "block-1",
  related_blocks: [{
    block_id: "block-1",
    kind: "paragraph",
    ordinal: 0,
    locator: {line_start: 1},
    content_fingerprint: "c".repeat(64)
  }]
};
var base = {
  schema_version: "alc.render.fragment_revision.v3",
  source: source,
  fragment_id: "note-1",
  revision: 1,
  parent_semantic_digest: null,
  anchor: anchor,
  priority: 110,
  role: "note",
  language: "en",
  title: null,
  citation_ids: [],
  appearance: null,
  deleted: false,
  provenance: {producer: "alc-render-browser"},
  markdown_body: "old",
  semantic_digest: "d".repeat(64),
  _origin: "embedded"
};
var nodes = {
  "alc-editor-markdown": {value: "updated"},
  "alc-editor-title": {value: "Updated"},
  "alc-editor-role": {value: "note"},
  "alc-editor-priority": {value: "110"},
  "alc-editor-save": {disabled: false},
  "alc-editor-dialog": {
    open: true,
    close: function () { this.open = false; this.closeCalls += 1; },
    closeCalls: 0,
    querySelectorAll: function () {
      return [
        nodes["alc-editor-title"],
        nodes["alc-editor-role"],
        nodes["alc-editor-priority"],
        nodes["alc-editor-markdown"],
        nodes["alc-editor-save"]
      ];
    }
  },
  "alc-storage-status": {textContent: "", dataset: {}, hidden: true}
};
globalThis.document = {
  getElementById: function (id) {
    if (!nodes[id]) throw new Error("unexpected DOM lookup: " + id);
    return nodes[id];
  }
};
globalThis.confirm = function () { return true; };

var directoryCalls = [];
var fileCalls = [];
var writes = [];
var closeCalls = 0;
var failClose = false;
var commitOnCloseFailure = false;
var savedContent = "";
var revisionHandle = {
  getFile: function () {
    return Promise.resolve({
      size: savedContent.length,
      text: function () { return Promise.resolve(savedContent); }
    });
  },
  createWritable: function () {
    var pending = "";
    return Promise.resolve({
      write: function (value) { pending = value; writes.push(value); },
      close: function () {
        closeCalls += 1;
        if (failClose) {
          if (commitOnCloseFailure) savedContent = pending;
          return Promise.reject(new Error("close failed"));
        }
        savedContent = pending;
      }
    });
  }
};
var folder = {
  values: function () { throw new Error("steady save scanned revision history"); },
  getFileHandle: function (name, options) {
    fileCalls.push({name: name, create: Boolean(options && options.create)});
    if (!options || !options.create) {
      var missing = new Error("missing");
      missing.name = "NotFoundError";
      return Promise.reject(missing);
    }
    savedContent = "";
    return Promise.resolve(revisionHandle);
  }
};
var helpers = globalThis.__alcReaderTest;
helpers.state.payload = {
  source_identity: source,
  block_fingerprints: {"block-1": "c".repeat(64)},
  revisions: [],
  diagnostics: [],
  publication: {
    source_document: {
      blocks: [{
        block_id: "block-1",
        kind: "paragraph",
        ordinal: 0,
        locator: {line_start: 1},
        payload: {text: "source"}
      }]
    },
    outline: [],
    bibliography: [],
    glossary: [],
    labels: {},
    reader_profile: {source_language: "en", target_language: "en"}
  }
};
helpers.state.directory = {
  getDirectoryHandle: function (name, options) {
    directoryCalls.push({name: name, create: Boolean(options && options.create)});
    if (!options) throw new Error("steady save reloaded the directory");
    return Promise.resolve(folder);
  }
};
helpers.state.revisions = new Map([[base.fragment_id, [base]]]);
helpers.state.selected = new Map([[base.fragment_id, base]]);
helpers.state.fragmentGroups = new Map([[anchor.target_id, [base]]]);
helpers.state.editorBase = base;
helpers.state.editorAnchor = anchor;
helpers.state.readerShellReady = true;
helpers.state.chunkByTargetId = new Map([["block-" + anchor.target_id, {chunk_id: "chunk-1"}]]);
var renderedChunks = [];
helpers.installRenderSpies(function (chunk) { renderedChunks.push(chunk); });
var postCommitFailures = {group: false, chunk: false};
var recoveredCards = [];
var titleSyncs = {count: 0};
helpers.installPostCommitFailureSpies(
  postCommitFailures, recoveredCards, titleSyncs
);

function prepareDraft(revision) {
  helpers.state.editorBase = revision;
  helpers.state.editorAnchor = revision.anchor;
  helpers.state.editorHistorical = revision;
  helpers.state.activeDraft = {
    base: revision,
    anchor: revision.anchor,
    title: nodes["alc-editor-title"].value,
    role: nodes["alc-editor-role"].value,
    priority: Number(nodes["alc-editor-priority"].value),
    markdown_body: nodes["alc-editor-markdown"].value
  };
  nodes["alc-editor-dialog"].open = true;
}

(async function () {
  prepareDraft(base);
  helpers.state.exportInProgress = true;
  var fileCallsBeforeBlockedSave = fileCalls.length;
  await helpers.saveEditor({preventDefault: function () {}});
  assert(
    fileCalls.length === fileCallsBeforeBlockedSave,
    "save overlapped a latest-content export sync"
  );
  assert(
    nodes["alc-storage-status"].textContent.includes("sync is already in progress"),
    "export/save overlap did not report the shared revision guard"
  );
  helpers.state.exportInProgress = false;
  var first = helpers.saveEditor({preventDefault: function () {}});
  assert(
    nodes["alc-editor-dialog"].querySelectorAll().every(function (control) {
      return control.disabled;
    }),
    "editor controls remained enabled during save"
  );
  var duplicate = helpers.saveEditor({preventDefault: function () {}});
  await Promise.all([first, duplicate]);
  assert(directoryCalls.length === 1, "steady save did not use constant directory work");
  assert(
    directoryCalls[0].name === "fragments" && directoryCalls[0].create,
    "steady save requested the wrong revision directory"
  );
  assert(fileCalls.length === 2, "immutable existence probe/create count changed");
  assert(fileCalls[0].name === fileCalls[1].name, "probe and create names differ");
  assert(!fileCalls[0].create && fileCalls[1].create, "immutable write order changed");
  assert(writes.length === 1 && closeCalls === 1, "duplicate save wrote more than once");
  assert(
    renderedChunks.length === 1 && renderedChunks[0].chunk_id === "chunk-1",
    "steady save did not rerender exactly the affected chunk"
  );
  assert(nodes["alc-editor-dialog"].closeCalls === 1, "successful save did not close once");
  assert(!nodes["alc-editor-save"].disabled, "save button remained disabled");
  var selected = helpers.state.selected.get(base.fragment_id);
  assert(selected.revision === 2, "saved revision was not selected");
  assert(
    helpers.state.revisions.get(base.fragment_id).length === 2,
    "saved revision was not added once"
  );
  assert(
    helpers.state.fragmentGroups.get(anchor.target_id).length === 1 &&
      helpers.state.fragmentGroups.get(anchor.target_id)[0].revision === 2,
    "saved fragment group was not updated in place"
  );
  assert(titleSyncs.count === 1, "successful save did not refresh the title surface");
  assert(
    writes[0].includes("Updated") && writes[0].endsWith("updated"),
    "saved bytes do not contain the editor value"
  );

  nodes["alc-editor-markdown"].value = "failed update";
  prepareDraft(selected);
  failClose = true;
  await helpers.saveEditor({preventDefault: function () {}});
  assert(
    helpers.state.selected.get(base.fragment_id).revision === 2 &&
      helpers.state.revisions.get(base.fragment_id).length === 2,
    "failed close changed in-memory revision state"
  );
  assert(nodes["alc-editor-dialog"].closeCalls === 1, "failed save closed the editor");
  assert(
    nodes["alc-storage-status"].dataset.kind === "error" &&
      nodes["alc-storage-status"].textContent === "close failed",
    "failed save did not report the close error"
  );
  assert(!nodes["alc-editor-save"].disabled, "failed save did not release its guard");

  failClose = false;
  await helpers.saveEditor({preventDefault: function () {}});
  assert(
    helpers.state.selected.get(base.fragment_id).revision === 3,
    "save guard was not reusable after failure"
  );
  var latest = helpers.state.selected.get(base.fragment_id);
  nodes["alc-editor-markdown"].value = "committed despite close error";
  prepareDraft(latest);
  failClose = true;
  commitOnCloseFailure = true;
  await helpers.saveEditor({preventDefault: function () {}});
  assert(
    helpers.state.selected.get(base.fragment_id).revision === 4,
    "exact readback did not recover an ambiguous close"
  );
  assert(
    nodes["alc-storage-status"].dataset.kind === "info",
    "verified close recovery was reported as a failure"
  );
  failClose = false;
  commitOnCloseFailure = false;
  latest = helpers.state.selected.get(base.fragment_id);

  nodes["alc-editor-markdown"].value = "saved before chunk refresh failed";
  prepareDraft(latest);
  postCommitFailures.chunk = true;
  await helpers.saveEditor({preventDefault: function () {}});
  postCommitFailures.chunk = false;
  latest = helpers.state.selected.get(base.fragment_id);
  assert(
    latest.revision === 5 && helpers.state.activeDraft === null,
    "chunk refresh failure left a persisted revision as an active draft"
  );
  assert(
    recoveredCards.length === 1 &&
      recoveredCards[0].fragmentId === base.fragment_id,
    "chunk refresh failure did not restore a readable fragment card"
  );
  assert(
    nodes["alc-storage-status"].dataset.kind === "info" &&
      nodes["alc-storage-status"].textContent.includes("chunk refresh failed"),
    "post-commit chunk failure was not reported as saved with a UI warning"
  );

  nodes["alc-editor-markdown"].value = "saved before group refresh failed";
  prepareDraft(latest);
  postCommitFailures.group = true;
  await helpers.saveEditor({preventDefault: function () {}});
  postCommitFailures.group = false;
  latest = helpers.state.selected.get(base.fragment_id);
  assert(
    latest.revision === 6 && helpers.state.activeDraft === null,
    "group refresh failure left a persisted revision as an active draft"
  );
  assert(
    recoveredCards.length === 2 &&
      recoveredCards[1].fragmentId === base.fragment_id,
    "group refresh failure did not restore a readable fragment card"
  );
  assert(
    nodes["alc-storage-status"].dataset.kind === "info" &&
      nodes["alc-storage-status"].textContent.includes("group refresh failed"),
    "post-commit group failure was not reported as saved with a UI warning"
  );

  nodes["alc-editor-title"].value = "New saved note";
  nodes["alc-editor-role"].value = "note";
  nodes["alc-editor-priority"].value = "110";
  nodes["alc-editor-markdown"].value = "new note survives UI recovery";
  helpers.state.editorBase = null;
  helpers.state.editorAnchor = anchor;
  helpers.state.editorHistorical = null;
  helpers.state.activeDraft = {
    base: null,
    anchor: anchor,
    title: nodes["alc-editor-title"].value,
    role: nodes["alc-editor-role"].value,
    priority: Number(nodes["alc-editor-priority"].value),
    markdown_body: nodes["alc-editor-markdown"].value
  };
  nodes["alc-editor-dialog"].open = true;
  var renderedBeforeNewNoteRecovery = renderedChunks.length;
  postCommitFailures.chunk = true;
  await helpers.saveEditor({preventDefault: function () {}});
  postCommitFailures.chunk = false;
  var newNote = Array.from(helpers.state.selected.values()).find(function (item) {
    return item.fragment_id.indexOf("user-") === 0;
  });
  assert(
    newNote && helpers.state.activeDraft === null,
    "new note was not retained after its post-commit chunk failure"
  );
  assert(
    helpers.state.fragmentGroups.get(anchor.target_id).some(function (item) {
      return item.fragment_id === newNote.fragment_id;
    }),
    "new note recovery did not repair its fragment group"
  );
  assert(
    renderedChunks.length === renderedBeforeNewNoteRecovery + 1,
    "new note recovery did not retry the affected rendered chunk"
  );

  nodes["alc-editor-title"].value = latest.title || "";
  nodes["alc-editor-role"].value = latest.role;
  nodes["alc-editor-priority"].value = String(latest.priority);
  nodes["alc-editor-markdown"].value = latest.markdown_body;
  prepareDraft(latest);
  helpers.state.revisions.get(base.fragment_id).push(Object.assign({}, latest, {
    revision: 7,
    parent_semantic_digest: latest.semantic_digest,
    semantic_digest: "e".repeat(64),
    anchor: {kind: "block", target_id: "other", related_blocks: []}
  }));
  var fileCallsBeforeStaleSave = fileCalls.length;
  await helpers.saveEditor({preventDefault: function () {}});
  assert(
    fileCalls.length === fileCallsBeforeStaleSave,
    "known next revision was not rejected before filesystem access"
  );
  assert(
    nodes["alc-storage-status"].textContent.includes("current directory revision changed"),
    "known next revision did not report stale editor state"
  );
  helpers.state.revisions.get(base.fragment_id).pop();
  prepareDraft(latest);
  await helpers.deleteEditor({preventDefault: function () {}});
  var tombstone = helpers.state.selected.get(base.fragment_id);
  assert(
    tombstone.revision === latest.revision + 1 && tombstone.deleted === true,
    "Delete did not select a tombstone revision"
  );
  assert(
    tombstone.title === null && tombstone.markdown_body === "" &&
      tombstone.citation_ids.length === 0,
    "Delete did not persist an empty tombstone revision"
  );
  assert(
    !helpers.state.fragmentGroups.get(anchor.target_id).some(function (item) {
      return item.fragment_id === base.fragment_id;
    }),
    "deleted fragment remained in its render group"
  );
  assert(
    writes[writes.length - 1].includes('"deleted":true'),
    "persisted deletion omitted its tombstone flag"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_hides_tombstones_and_empty_notes_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    fragmentIsVisible: fragmentIsVisible,
    emptyNoteState: emptyNoteState
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
assert(!helpers.fragmentIsVisible({
  role: "translation", title: "Text", markdown_body: "body", deleted: true
}), "tombstone remained visible");
assert(!helpers.fragmentIsVisible({
  role: "note", title: null, markdown_body: "  \\n", deleted: false
}), "legacy empty note remained visible");
assert(helpers.fragmentIsVisible({
  role: "note", title: "Title", markdown_body: "", deleted: false
}), "titled note was hidden");
assert(helpers.emptyNoteState({
  role: "note", title: null, markdown_body: "\\n"
}), "cleared note did not trigger automatic deletion");
"""
    )
    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_groups_colors_by_role_and_priority_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    syncAppearanceGroups: syncAppearanceGroups,
    appearanceForGroup: appearanceForGroup
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function fragment(id, priority, appearance, provenance) {
  return {
    fragment_id: id,
    semantic_digest: id.repeat(64).slice(0, 64),
    revision: 1,
    role: "translation",
    priority: priority,
    appearance: appearance,
    provenance: provenance || {}
  };
}
var helpers = globalThis.__alcReaderTest;
var ocean = {foreground: "#17324d", background: "#e7f0fa"};
var paper = {foreground: "#3a2e1f", background: "#fff4d6"};
var plum = {foreground: "#442857", background: "#f2eaf6"};
helpers.state.selected = new Map([
  ["a", fragment("a", 50, ocean, {created_at: "2026-01-01T00:00:00Z"})],
  ["b", fragment("b", 50, null, {created_at: "2026-02-01T00:00:00Z"})],
  ["c", fragment("c", 60, paper, {created_at: "2026-01-01T00:00:00Z"})]
]);
helpers.syncAppearanceGroups();
assert(
  JSON.stringify(helpers.appearanceForGroup("translation", 50)) ===
    JSON.stringify(ocean),
  "legacy per-fragment colors did not converge on one explicit group color"
);
assert(
  JSON.stringify(helpers.appearanceForGroup("translation", 60)) ===
    JSON.stringify(paper),
  "another priority did not retain its independent color"
);

helpers.state.selected.set("d", fragment("d", 50, null, {
  appearance_scope: "role_priority",
  edited_at: "2026-03-01T00:00:00Z"
}));
helpers.syncAppearanceGroups();
assert(
  helpers.appearanceForGroup("translation", 50) === null,
  "scoped reset did not restore the role default for the whole group"
);

helpers.state.selected.set("e", fragment("e", 50, plum, {
  appearance_scope: "role_priority",
  edited_at: "2026-04-01T00:00:00Z"
}));
helpers.syncAppearanceGroups();
assert(
  JSON.stringify(helpers.appearanceForGroup("translation", 50)) ===
    JSON.stringify(plum),
  "newest scoped declaration did not recolor the group"
);
assert(
  JSON.stringify(helpers.appearanceForGroup("translation", 60)) ===
    JSON.stringify(paper),
  "recoloring one priority changed another priority"
);
"""
    )
    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_unchanged_save_is_a_normalized_zero_work_noop_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    saveEditor: saveEditor,
    installNoopSpies: function (calls) {
      connectDirectory = async function () { calls.picker += 1; return false; };
      semanticDigest = async function () { calls.digest += 1; return "f".repeat(64); };
      fragmentsDirectory = async function () { calls.filesystem += 1; return {}; };
      writeImmutableRevision = async function () { calls.filesystem += 1; };
      refreshFragmentGroup = function () { calls.rerender += 1; };
      refreshChunkForAnchor = function () { calls.rerender += 1; };
      replaceFragmentCard = function () { calls.cardReplace += 1; };
    }
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var anchor = {
  kind: "block",
  target_id: "block-1",
  related_blocks: [{
    block_id: "block-1",
    kind: "paragraph",
    ordinal: 0,
    locator: {line_start: 1},
    content_fingerprint: "c".repeat(64)
  }]
};
var base = {
  schema_version: "alc.render.fragment_revision.v3",
  source: source,
  fragment_id: "note-1",
  revision: 1,
  parent_semantic_digest: null,
  anchor: anchor,
  priority: 110,
  role: "note",
  language: "en",
  title: "Caf\u00e9",
  citation_ids: ["ref-1"],
  appearance: null,
  deleted: false,
  provenance: {
    producer: "some-other-editor",
    last_editor: "some-other-editor",
    edited_at: "2000-01-01T00:00:00.000Z"
  },
  markdown_body: "Caf\u00e9 [@ref-1]\\nsecond line",
  semantic_digest: "d".repeat(64),
  _origin: "embedded"
};
var controls = {
  title: {value: base.title, disabled: false},
  role: {value: base.role, disabled: false},
  priority: {value: String(base.priority), disabled: false},
  markdown: {value: base.markdown_body, disabled: false},
  save: {disabled: false}
};
var nodes = {
  "alc-editor-title": controls.title,
  "alc-editor-role": controls.role,
  "alc-editor-priority": controls.priority,
  "alc-editor-markdown": controls.markdown,
  "alc-editor-save": controls.save,
  "alc-editor-dialog": {
    open: true,
    closeCalls: 0,
    close: function () { this.open = false; this.closeCalls += 1; },
    querySelectorAll: function () { return Object.values(controls); }
  },
  "alc-storage-status": {textContent: "", dataset: {}, hidden: true}
};
globalThis.document = {
  getElementById: function (id) {
    if (!nodes[id]) throw new Error("unexpected DOM lookup: " + id);
    return nodes[id];
  }
};

var helpers = globalThis.__alcReaderTest;
var calls = {picker: 0, digest: 0, filesystem: 0, rerender: 0, cardReplace: 0};
helpers.installNoopSpies(calls);
helpers.state.payload = {
  source_identity: source,
  block_fingerprints: {"block-1": "c".repeat(64)},
  publication: {
    source_document: {blocks: []},
    bibliography: [{evidence_id: "ref-1"}],
    labels: {},
    reader_profile: {source_language: "en", target_language: "en"}
  }
};
helpers.state.directory = null;
helpers.state.revisions = new Map([[base.fragment_id, [base]]]);
helpers.state.selected = new Map([[base.fragment_id, base]]);

function prepareDraft() {
  nodes["alc-editor-dialog"].open = true;
  helpers.state.editorBase = base;
  helpers.state.editorAnchor = anchor;
  helpers.state.editorHistorical = base;
  helpers.state.editorGeneration += 1;
  helpers.state.activeDraft = {
    base: base,
    anchor: anchor,
    historical: base,
    title: controls.title.value,
    role: controls.role.value,
    priority: Number(controls.priority.value),
    markdown_body: controls.markdown.value
  };
}

function assertNoWork(description) {
  assert(calls.picker === 0, description + " opened a directory picker");
  assert(calls.digest === 0, description + " computed a digest");
  assert(calls.filesystem === 0, description + " touched the filesystem");
  assert(calls.rerender === 0, description + " rerendered content");
}

(async function () {
  prepareDraft();
  await helpers.saveEditor({preventDefault: function () {}});
  assertNoWork("exact unchanged save");
  assert(calls.cardReplace === 1, "unchanged inline card was not restored locally");
  assert(
    helpers.state.selected.get(base.fragment_id) === base &&
      helpers.state.revisions.get(base.fragment_id).length === 1,
    "unchanged save mutated selected revision state"
  );
  assert(nodes["alc-editor-dialog"].closeCalls === 1, "unchanged save did not close");
  assert(
    nodes["alc-storage-status"].dataset.kind === "info" &&
      nodes["alc-storage-status"].textContent === "Content is unchanged.",
    "unchanged save did not report the neutral status"
  );

  controls.title.value = "Cafe\u0301";
  controls.markdown.value = "Cafe\u0301 [@ref-1]\\r\\nsecond line";
  prepareDraft();
  await helpers.saveEditor({preventDefault: function () {}});
  assertNoWork("normalized unchanged save");
  assert(calls.cardReplace === 2, "normalized unchanged inline card was not restored");
  assert(
    helpers.state.selected.get(base.fragment_id) === base &&
      helpers.state.revisions.get(base.fragment_id).length === 1,
    "normalized unchanged save created a revision"
  );
  assert(
    nodes["alc-editor-dialog"].closeCalls === 2,
    "CRLF/NFC-equivalent save did not close as unchanged"
  );

  helpers.state.revisions.get(base.fragment_id).push(Object.assign({}, base, {
    revision: 2,
    parent_semantic_digest: base.semantic_digest,
    semantic_digest: "e".repeat(64)
  }));
  prepareDraft();
  await helpers.saveEditor({preventDefault: function () {}});
  assertNoWork("known-stale unchanged save");
  assert(calls.cardReplace === 2, "known-stale save replaced the inline card");
  assert(
    nodes["alc-editor-dialog"].closeCalls === 2,
    "known-stale unchanged save closed the editor"
  );
  assert(
    nodes["alc-storage-status"].dataset.kind === "error" &&
      nodes["alc-storage-status"].textContent.includes("current directory revision changed"),
    "known-stale unchanged save bypassed lineage rejection"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_inline_draft_lifecycle_and_mutexes_execute_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    renderFragment: renderFragment,
    renderSourceRow: renderSourceRow,
    primaryTitlePromotion: primaryTitlePromotion,
    beginInlineEdit: beginInlineEdit,
    openAdvancedEditor: openAdvancedEditor,
    closeEditorDialog: closeEditorDialog,
    cancelActiveDraft: cancelActiveDraft,
    restoreHistoricalRevision: restoreHistoricalRevision,
    syncDraftFromDialog: syncDraftFromDialog,
    setDraftAppearance: setDraftAppearance,
    renderColorPresets: renderColorPresets,
    resetDraftAppearance: resetDraftAppearance,
    updateAppearanceFromPicker: updateAppearanceFromPicker,
    updateAppearanceFromText: updateAppearanceFromText,
    openNewEditorForAnchor: openNewEditorForAnchor,
    renderHistory: renderHistory,
    openExportPanel: openExportPanel,
    connectDirectory: connectDirectory,
    attemptInlineDraftExit: attemptInlineDraftExit,
    guardUnsavedDraftBeforeUnload: guardUnsavedDraftBeforeUnload,
    hideNativeSelectForCustomControl: hideNativeSelectForCustomControl,
    installDraftSpies: function (calls, render) {
      renderMarkdown = render;
      renderSourceBlock = function () { return new FakeNode("div"); };
      renderCardActions = function () { return new FakeNode("div"); };
      decorateGlossary = function () {};
      typeset = function () {};
      refreshChunkForAnchor = function (anchor) { calls.refresh.push(anchor); };
      saveEditor = function () { calls.save += 1; };
      markEditorPreviewDirty = function () { state.editorPreviewDirty = true; };
    }
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function FakeNode(tag) {
  this.tagName = String(tag || "div").toUpperCase();
  this.className = "";
  this.children = [];
  this.parentElement = null;
  this.listeners = {};
  this.attrs = {};
  this.dataset = {};
  this.style = {
    setProperty: function (name, value) { this[name] = value; },
    removeProperty: function (name) { delete this[name]; }
  };
  this.textContent = "";
  this.value = "";
  this.disabled = false;
  this.hidden = false;
  this.open = false;
  this.scrollHeight = 240;
  this.classList = {
    owner: this,
    contains: function (name) {
      return this.owner.className.split(/\\s+/).includes(name);
    },
    add: function (name) {
      if (!this.contains(name)) {
        this.owner.className = (this.owner.className + " " + name).trim();
      }
    },
    remove: function (name) {
      this.owner.className = this.owner.className.split(/\\s+/).filter(
        function (value) { return value && value !== name; }
      ).join(" ");
    },
    toggle: function (name, enabled) {
      if (enabled) this.add(name);
    }
  };
}
FakeNode.prototype.appendChild = function (child) {
  child.parentElement = this;
  this.children.push(child);
  return child;
};
FakeNode.prototype.replaceChildren = function () {
  this.children = [];
  for (var index = 0; index < arguments.length; index += 1) {
    this.appendChild(arguments[index]);
  }
};
FakeNode.prototype.setAttribute = function (name, value) {
  this.attrs[name] = String(value);
};
FakeNode.prototype.removeAttribute = function (name) { delete this.attrs[name]; };
FakeNode.prototype.setCustomValidity = function (value) {
  this.validationMessage = String(value || "");
};
FakeNode.prototype.addEventListener = function (name, listener) {
  (this.listeners[name] = this.listeners[name] || []).push(listener);
};
FakeNode.prototype.dispatch = function (name, event) {
  event = event || {};
  if (!event.target) event.target = this;
  (this.listeners[name] || []).forEach(function (listener) { listener(event); });
};
FakeNode.prototype.matchesSelector = function (selector) {
  if (selector[0] === ".") return this.classList.contains(selector.slice(1));
  return this.tagName.toLowerCase() === selector.toLowerCase();
};
FakeNode.prototype.closest = function (selectors) {
  var choices = selectors.split(",").map(function (value) { return value.trim(); });
  var current = this;
  while (current) {
    if (choices.some(function (choice) { return current.matchesSelector(choice); })) {
      return current;
    }
    current = current.parentElement;
  }
  return null;
};
FakeNode.prototype.querySelector = function (selector) {
  for (var index = 0; index < this.children.length; index += 1) {
    var child = this.children[index];
    if (child.matchesSelector(selector)) return child;
    var nested = child.querySelector(selector);
    if (nested) return nested;
  }
  return null;
};
FakeNode.prototype.contains = function (candidate) {
  if (candidate === this) return true;
  return this.children.some(function (child) { return child.contains(candidate); });
};
FakeNode.prototype.focus = function () { this.focused = true; };
FakeNode.prototype.scrollIntoView = function (options) {
  this.scrollCalls = (this.scrollCalls || 0) + 1;
  this.scrollOptions = options;
};
FakeNode.prototype.setSelectionRange = function (start, end) {
  this.selection = [start, end];
};
FakeNode.prototype.showModal = function () {
  this.open = true;
  this.showCalls = (this.showCalls || 0) + 1;
};
FakeNode.prototype.close = function () {
  this.open = false;
  this.closeCalls = (this.closeCalls || 0) + 1;
};

var nodes = {
  "alc-editor-dialog": new FakeNode("dialog"),
  "alc-editor-heading": new FakeNode("h2"),
  "alc-editor-title": new FakeNode("input"),
  "alc-editor-role": new FakeNode("select"),
  "alc-editor-priority": new FakeNode("input"),
  "alc-editor-markdown": new FakeNode("textarea"),
  "alc-editor-save": new FakeNode("button"),
  "alc-editor-delete": new FakeNode("button"),
  "alc-editor-history": new FakeNode("div"),
  "alc-editor-preview": new FakeNode("div"),
  "alc-editor-foreground-picker": new FakeNode("input"),
  "alc-editor-foreground": new FakeNode("input"),
  "alc-editor-background-picker": new FakeNode("input"),
  "alc-editor-background": new FakeNode("input"),
  "alc-editor-color-presets": new FakeNode("div"),
  "alc-export": new FakeNode("button"),
  "alc-export-panel": new FakeNode("div"),
  "alc-unsaved-dialog": new FakeNode("dialog"),
  "alc-unsaved-error": new FakeNode("p"),
  "alc-unsaved-save": new FakeNode("button"),
  "alc-storage-status": new FakeNode("div")
};
nodes["alc-editor-foreground"].value = "#f9fafb";
nodes["alc-editor-background"].value = "#111827";
nodes["alc-export-panel"].hidden = true;
var visibleCard = null;
globalThis.document = {
  createElement: function (tag) { return new FakeNode(tag); },
  getElementById: function (id) {
    if (!nodes[id]) throw new Error("unexpected DOM lookup: " + id);
    return nodes[id];
  },
  querySelector: function (selector) {
    return selector.includes('.alc-fragment[data-fragment-id=') ? visibleCard : null;
  }
};
globalThis.innerHeight = 900;
globalThis.requestAnimationFrame = function (callback) { callback(); };
globalThis.CSS = {escape: function (value) { return value; }};
var pickerCalls = 0;
globalThis.showDirectoryPicker = async function () { pickerCalls += 1; return {}; };

var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
function anchor(id) {
  return {kind: "block", target_id: id, related_blocks: []};
}
var first = {
  fragment_id: "note-1",
  revision: 2,
  semantic_digest: "c".repeat(64),
  anchor: anchor("block-1"),
  title: "First",
  role: "note",
  priority: 110,
  markdown_body: "saved body"
};
var second = Object.assign({}, first, {
  fragment_id: "note-2",
  semantic_digest: "d".repeat(64),
  anchor: anchor("block-2"),
  title: "Second"
});
var historical = Object.assign({}, first, {
  revision: 1,
  semantic_digest: "e".repeat(64),
  title: "Historical",
  role: "guide",
  priority: 70,
  markdown_body: "historical body"
});
var helpers = globalThis.__alcReaderTest;
var calls = {refresh: [], save: 0};
helpers.installDraftSpies(calls, function (markdown) {
  var rendered = new FakeNode("div");
  rendered.className = "alc-markdown";
  rendered.textContent = markdown;
  return rendered;
});
helpers.state.payload = {
  source_identity: source,
  publication: {
    source_document: {blocks: []},
    bibliography: [],
    labels: {},
    reader_profile: {source_language: "en", target_language: "en"}
  }
};
helpers.state.revisions = new Map([[first.fragment_id, [historical, first]]]);
helpers.state.selected = new Map([[first.fragment_id, first]]);
helpers.state.readerPreferences.editActivation = "single";

var nativeAttrs = {};
var nativeSelect = {
  className: "",
  classList: {
    add: function (name) { nativeSelect.className = name; }
  },
  setAttribute: function (name, value) { nativeAttrs[name] = value; }
};
helpers.hideNativeSelectForCustomControl(nativeSelect);
assert(
  nativeSelect.tabIndex === -1 && nativeAttrs["aria-hidden"] === "true" &&
    nativeSelect.className === "alc-native-select",
  "custom select left its native control focusable or exposed"
);

(async function () {
  var titleBlock = {
    block_id: "title-block",
    kind: "heading",
    payload: {level: 1, text: "Source title"}
  };
  var titleTranslation = Object.assign({}, first, {
    fragment_id: "title-translation",
    anchor: anchor(titleBlock.block_id),
    role: "translation",
    priority: 10,
    title: null,
    markdown_body: "Translated title"
  });
  var titleCompanion = Object.assign({}, first, {
    fragment_id: "title-companion",
    anchor: anchor(titleBlock.block_id),
    role: "companion",
    priority: 20,
    title: "Context",
    markdown_body: "Visible context"
  });
  helpers.state.primaryTitleBlockId = titleBlock.block_id;
  helpers.state.primaryTitleFragmentId = titleTranslation.fragment_id;
  helpers.state.payload.publication.source_document.blocks = [titleBlock];
  helpers.state.fragmentGroups = new Map([[
    titleBlock.block_id, [titleTranslation, titleCompanion]
  ]]);
  helpers.state.selected = new Map([
    [titleTranslation.fragment_id, titleTranslation],
    [titleCompanion.fragment_id, titleCompanion]
  ]);
  assert(
    helpers.primaryTitlePromotion(
      helpers.state.payload.publication.source_document
    ).fragment === titleTranslation,
    "current translated title was not selected for promotion"
  );
  var titleRow = helpers.renderSourceRow(
    titleBlock, [titleTranslation, titleCompanion]
  );
  var titleLanes = titleRow.querySelector(".alc-lanes");
  assert(
    titleRow.classList.contains("alc-promoted-title-row") &&
      titleLanes.children.length === 2 &&
      titleLanes.children[1].dataset.fragmentId === titleCompanion.fragment_id,
    "promoting the translated title removed another low-priority fragment"
  );
  assert(
    !titleLanes.classList.contains("has-parallel-translation"),
    "the promoted title incorrectly reserved an empty translation lane"
  );
  var parallelTranslation = Object.assign({}, titleTranslation, {
    fragment_id: "paragraph-translation",
    anchor: anchor("paragraph-block")
  });
  var sourceOnlyRow = helpers.renderSourceRow({
    block_id: "paragraph-block", kind: "paragraph", payload: {text: "Source"}
  }, []);
  var parallelRow = helpers.renderSourceRow({
    block_id: "parallel-block", kind: "paragraph", payload: {text: "Source"}
  }, [Object.assign({}, parallelTranslation, {anchor: anchor("parallel-block")})]);
  assert(
    !sourceOnlyRow.querySelector(".alc-lanes").classList.contains(
      "has-parallel-translation"
    ) && parallelRow.querySelector(".alc-lanes").classList.contains(
      "has-parallel-translation"
    ),
    "source-only and translated rows did not receive distinct lane states"
  );
  helpers.state.payload.selected_heading_fragments = [titleTranslation];
  helpers.state.selected.set(titleTranslation.fragment_id, Object.assign(
    {}, titleTranslation, {deleted: true, revision: 3}
  ));
  helpers.state.fragmentGroups.set(titleBlock.block_id, [titleCompanion]);
  assert(
    helpers.primaryTitlePromotion(
      helpers.state.payload.publication.source_document
    ) === null,
    "a deleted title revision fell back to the stale embedded heading"
  );
  helpers.state.primaryTitleBlockId = "";
  helpers.state.primaryTitleFragmentId = "";
  helpers.state.payload.selected_heading_fragments = [];
  helpers.state.fragmentGroups = new Map();
  helpers.state.selected = new Map([[first.fragment_id, first]]);

  var firstCard = helpers.renderFragment(first);
  assert(!firstCard.querySelector(".alc-edit-button"), "fragment retained an edit pencil");
  assert(
    firstCard.querySelector(".alc-fragment-meta").textContent === "Note · v2",
    "reading mode exposed priority or hid a non-v1 revision"
  );
  assert(
    helpers.renderFragment(historical)
      .querySelector(".alc-fragment-meta").textContent === "Guide",
    "reading mode exposed priority or v1"
  );
  assert(
    firstCard.querySelector(".alc-edit-accessible"),
    "fragment lost its keyboard-accessible edit action"
  );
  helpers.renderHistory(historical.fragment_id);
  assert(
    nodes["alc-editor-history"].children.length > 0,
    "multi-revision fragment hid version history"
  );
  var forkRoot = Object.assign({}, historical, {
    fragment_id: "forked-history", semantic_digest: "1".repeat(64)
  });
  var forkA = Object.assign({}, first, {
    fragment_id: "forked-history", semantic_digest: "2".repeat(64)
  });
  var forkB = Object.assign({}, first, {
    fragment_id: "forked-history", semantic_digest: "3".repeat(64)
  });
  helpers.state.revisions.set("forked-history", [forkRoot, forkA, forkB]);
  helpers.renderHistory("forked-history");
  var forkLabels = nodes["alc-editor-history"].children[0].children.slice(1)
    .map(function (button) { return button.textContent; });
  assert(
    forkLabels.join(",") === "v1,v2 · 2222222,v2 · 3333333",
    "same-version history branches remained indistinguishable"
  );
  helpers.state.revisions.set("single", [Object.assign({}, historical, {
    fragment_id: "single"
  })]);
  helpers.renderHistory("single");
  assert(
    nodes["alc-editor-history"].children.length === 0,
    "single-revision fragment showed version history"
  );
  var saved = firstCard.querySelector(".alc-fragment-saved-content");
  assert(
    !saved.attrs.role && saved.tabIndex === undefined,
    "clickable Markdown became a nested interactive container"
  );
  var link = new FakeNode("a");
  saved.appendChild(link);
  saved.dispatch("click", {target: link});
  assert(helpers.state.activeDraft === null, "interactive descendant started editing");

  saved.dispatch("click", {target: saved});
  assert(
    helpers.state.activeDraft && helpers.state.activeDraft.base === first,
    "body click did not establish the active draft"
  );
  var active = helpers.state.activeDraft;
  var secondCard = helpers.renderFragment(second);
  secondCard.querySelector(".alc-fragment-saved-content").dispatch("click");
  assert(
    helpers.state.activeDraft !== active &&
      helpers.state.activeDraft.base === second,
    "a clean draft did not switch directly to the second fragment"
  );
  saved.dispatch("click", {target: saved});
  assert(
    helpers.state.activeDraft.base === first,
    "switching back from a clean second draft failed"
  );
  active = helpers.state.activeDraft;

  var editingCard = helpers.renderFragment(first);
  assert(
    editingCard.querySelector(".alc-fragment-meta").textContent === "Note · 110 · v2",
    "editing mode hid priority or revision"
  );
  var textarea = editingCard.querySelector(".alc-inline-markdown");
  assert(textarea && textarea.value === "saved body", "inline editor missed draft content");
  var inlineSave = editingCard.querySelector(".alc-inline-save");
  assert(inlineSave.disabled, "unchanged inline draft left Save enabled");
  var prevented = 0;
  textarea.dispatch("keydown", {
    key: "Enter", ctrlKey: true, metaKey: false,
    preventDefault: function () { prevented += 1; }
  });
  textarea.dispatch("keydown", {
    key: "Enter", ctrlKey: false, metaKey: true,
    preventDefault: function () { prevented += 1; }
  });
  assert(
    calls.save === 0 && prevented === 2,
    "unchanged Ctrl/Cmd+Enter bypassed disabled Save"
  );

  textarea.value = "latest inline draft";
  textarea.dispatch("input");
  assert(!inlineSave.disabled, "changed inline draft did not enable Save");
  visibleCard = editingCard;
  var outsidePrevented = 0;
  var outsideStopped = 0;
  helpers.attemptInlineDraftExit({
    target: new FakeNode("a"),
    preventDefault: function () { outsidePrevented += 1; },
    stopImmediatePropagation: function () { outsideStopped += 1; }
  });
  assert(
    nodes["alc-unsaved-dialog"].open && outsidePrevented === 1 &&
      outsideStopped === 1,
    "keyboard-style outside activation bypassed the dirty draft dialog"
  );
  assert(
    nodes["alc-unsaved-save"].focused &&
      !nodes["alc-unsaved-save"].attrs["data-initial-focus"],
    "keyboard-opened dialog hid its initial focus indicator"
  );
  nodes["alc-unsaved-dialog"].close();
  helpers.attemptInlineDraftExit({
    type: "pointerdown",
    target: new FakeNode("a"),
    preventDefault: function () {},
    stopImmediatePropagation: function () {}
  });
  assert(
    nodes["alc-unsaved-save"].attrs["data-initial-focus"] === "true",
    "pointer-opened dialog exposed a programmatic focus ring"
  );
  nodes["alc-unsaved-save"].dispatch("blur");
  assert(
    !nodes["alc-unsaved-save"].attrs["data-initial-focus"],
    "pointer focus suppression remained after the default action blurred"
  );
  nodes["alc-unsaved-dialog"].close();
  var unloadPrevented = 0;
  var unloadEvent = {
    returnValue: null,
    preventDefault: function () { unloadPrevented += 1; }
  };
  helpers.guardUnsavedDraftBeforeUnload(unloadEvent);
  assert(
    unloadPrevented === 1 && unloadEvent.returnValue === "",
    "page unload did not protect a changed draft"
  );
  textarea.dispatch("keydown", {
    key: "Enter", ctrlKey: true, metaKey: false,
    preventDefault: function () { prevented += 1; }
  });
  textarea.dispatch("keydown", {
    key: "Enter", ctrlKey: false, metaKey: true,
    preventDefault: function () { prevented += 1; }
  });
  assert(calls.save === 2 && prevented === 4, "changed Ctrl/Cmd+Enter did not save");
  editingCard.querySelector(".alc-inline-advanced").dispatch("click", {
    preventDefault: function () {}
  });
  assert(
    nodes["alc-editor-dialog"].open &&
      nodes["alc-editor-dialog"].dataset.editorKind === "fragment" &&
      nodes["alc-editor-markdown"].value === "latest inline draft",
    "Advanced did not open on the latest inline draft"
  );
  assert(!nodes["alc-editor-save"].disabled, "changed Advanced draft disabled Save");
  helpers.renderColorPresets();
  nodes["alc-editor-color-presets"].children[1].dispatch("click");
  assert(
    active.appearance.foreground === "#3a2e1f" &&
      active.appearance.background === "#fff4d6" &&
      nodes["alc-editor-foreground"].value === "#3a2e1f" &&
      nodes["alc-editor-background-picker"].value === "#fff4d6",
    "clicking a preset did not synchronize draft, text, and picker controls"
  );
  nodes["alc-editor-foreground"].value = "#ABCDEF";
  helpers.updateAppearanceFromText("foreground", nodes["alc-editor-foreground"]);
  assert(
    active.appearance.foreground === "#abcdef" &&
      nodes["alc-editor-foreground-picker"].value === "#abcdef",
    "valid color text did not update picker and canonical draft"
  );
  nodes["alc-editor-background"].value = "#bad";
  helpers.updateAppearanceFromText("background", nodes["alc-editor-background"]);
  assert(nodes["alc-editor-save"].disabled, "invalid color text left Save enabled");
  nodes["alc-editor-background-picker"].value = "#010203";
  helpers.updateAppearanceFromPicker(
    "background", nodes["alc-editor-background-picker"]
  );
  assert(
    active.appearance.background === "#010203" &&
      nodes["alc-editor-background"].value === "#010203" &&
      !nodes["alc-editor-save"].disabled,
    "picker color did not repair text and draft state"
  );
  helpers.resetDraftAppearance({preventDefault: function () {}});
  assert(
    active.appearance === null &&
      nodes["alc-editor-foreground"].value === "#f9fafb" &&
      nodes["alc-editor-background"].value === "#111827",
    "role-default reset did not clear the override and restore note colors"
  );
  nodes["alc-editor-title"].value = "Latest title";
  nodes["alc-editor-role"].value = "companion";
  nodes["alc-editor-priority"].value = "80";
  nodes["alc-editor-markdown"].value = "latest advanced draft";
  helpers.closeEditorDialog();
  assert(
    helpers.state.activeDraft === active &&
      active.title === "Latest title" &&
      active.role === "companion" &&
      Number(active.priority) === 80 &&
      active.markdown_body === "latest advanced draft",
    "closing Advanced discarded or failed to share the draft"
  );

  nodes["alc-editor-dialog"].showModal();
  helpers.state.editorHistorical = historical;
  helpers.restoreHistoricalRevision();
  assert(
    active.title === historical.title &&
      active.role === historical.role &&
      active.priority === historical.priority &&
      active.markdown_body === historical.markdown_body,
    "history restore did not update the shared draft"
  );
  assert(
    nodes["alc-editor-title"].value === historical.title &&
      nodes["alc-editor-markdown"].value === historical.markdown_body,
    "history restore did not update Advanced controls"
  );
  assert(
    helpers.renderFragment(first).querySelector(".alc-inline-markdown").value ===
      historical.markdown_body,
    "history restore did not flow back to the inline editor"
  );

  var redirectCard = helpers.renderFragment(first);
  visibleCard = redirectCard;
  helpers.closeEditorDialog();
  var showCalls = nodes["alc-editor-dialog"].showCalls;
  helpers.openNewEditorForAnchor(anchor("block-3"));
  assert(
    helpers.state.activeDraft === active &&
      nodes["alc-editor-dialog"].showCalls === showCalls,
    "add-note bypassed the active-draft guard"
  );
  assert(
    redirectCard.scrollCalls === 1 &&
      redirectCard.querySelector(".alc-inline-markdown").focused &&
      nodes["alc-storage-status"].textContent ===
        "The current edit has unsaved changes; returned to it.",
    "dirty draft guard did not reveal and focus the unsaved editor"
  );
  await helpers.openExportPanel();
  assert(nodes["alc-export-panel"].hidden, "export opened during an active draft");
  var connected = await helpers.connectDirectory();
  assert(!connected && pickerCalls === 0, "directory selection opened during an active draft");

  var cancel = helpers.renderFragment(first).querySelector(".alc-inline-cancel");
  cancel.dispatch("click", {preventDefault: function () {}});
  assert(helpers.state.activeDraft === null, "inline cancel retained the active draft");

  helpers.openNewEditorForAnchor(anchor("block-4"));
  assert(
    helpers.state.activeDraft && !helpers.state.activeDraft.base,
    "blank new-note editor did not open"
  );
  helpers.beginInlineEdit(second);
  assert(
    helpers.state.activeDraft && helpers.state.activeDraft.base === second &&
      !nodes["alc-editor-dialog"].open,
    "blank new-note draft was not treated as clean during a switch"
  );
  helpers.cancelActiveDraft();

  var deleted = Object.assign({}, first, {
    revision: 3,
    semantic_digest: "f".repeat(64),
    anchor: anchor("block-5"),
    title: null,
    markdown_body: "",
    deleted: true
  });
  var deletedHistory = [historical, first].map(function (revision) {
    return Object.assign({}, revision, {anchor: anchor("block-5")});
  }).concat([deleted]);
  helpers.state.revisions.set(deleted.fragment_id, deletedHistory);
  helpers.state.selected.set(deleted.fragment_id, deleted);
  helpers.openNewEditorForAnchor(anchor("block-5"));
  assert(
    helpers.state.activeDraft && helpers.state.activeDraft.base === deleted &&
      helpers.state.activeDraft.markdown_body === "" &&
      nodes["alc-editor-dialog"].open,
    "same-anchor Add did not reopen the deleted fragment"
  );
  assert(
    helpers.state.editorHistorical.revision === 2 &&
      nodes["alc-editor-history"].children.length > 0 &&
      nodes["alc-editor-delete"].hidden,
    "reopened deletion did not expose history or hid its redundant Delete action"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_directory_sync_skips_embedded_and_caches_external_files() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    loadDirectoryRevisions: loadDirectoryRevisions,
    revisionFilename: revisionFilename,
    semanticDigest: semanticDigest,
    stableStringify: stableStringify
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var anchor = {
  kind: "block",
  target_id: "block-1",
  related_blocks: [{
    block_id: "block-1",
    kind: "paragraph",
    ordinal: 0,
    locator: {line_start: 1},
    content_fingerprint: "c".repeat(64)
  }]
};
var baseMetadata = {
  schema_version: "alc.render.fragment_revision.v3",
  source: source,
  fragment_id: "note-1",
  revision: 1,
  parent_semantic_digest: null,
  anchor: anchor,
  priority: 110,
  role: "note",
  language: "en",
  title: null,
  citation_ids: [],
  appearance: null,
  deleted: false,
  provenance: {producer: "alc-render-browser"}
};
var baseDigest = "d".repeat(64);
helpers.state.payload = {
  source_identity: source,
  block_fingerprints: {"block-1": "c".repeat(64)},
  diagnostics: [],
  publication: {
    source_document: {
      blocks: [{
        block_id: "block-1",
        kind: "paragraph",
        ordinal: 0,
        locator: {line_start: 1},
        payload: {text: "source"}
      }]
    },
    outline: [],
    bibliography: [],
    labels: {},
    reader_profile: {source_language: "en", target_language: "en"}
  }
};
helpers.state.embeddedRevisions = [{
  metadata: baseMetadata,
  markdown_body: "base",
  semantic_digest: baseDigest
}];
helpers.state.activeFragmentIds = new Set([baseMetadata.fragment_id]);
helpers.state.readerShellReady = false;

var embeddedReads = 0;
var externalGetFileCalls = 0;
var externalTextCalls = 0;
var externalValue = null;
var externalStamp = 1;
var entries = [];
var failEnumeration = false;
var glossaryRequests = 0;
var embeddedEntry = {
  kind: "file",
  name: helpers.revisionFilename(1, baseDigest),
  getFile: function () {
    embeddedReads += 1;
    throw new Error("embedded revision bytes should not be read");
  }
};
var externalEntry = {
  kind: "file",
  name: "",
  getFile: function () {
    externalGetFileCalls += 1;
    var captured = externalValue;
    return Promise.resolve({
      size: captured.length,
      lastModified: externalStamp,
      text: function () {
        externalTextCalls += 1;
        return Promise.resolve(captured);
      }
    });
  }
};
var fragments = {
  values: async function* () {
    if (failEnumeration) throw new Error("enumeration failed");
    for (var index = 0; index < entries.length; index += 1) yield entries[index];
  }
};
var directory = {
  getDirectoryHandle: function (name) {
    if (name === "glossary") {
      glossaryRequests += 1;
      return Promise.reject(Object.assign(new Error("missing"), {name: "NotFoundError"}));
    }
    if (name !== "fragments") throw new Error("unexpected directory: " + name);
    return Promise.resolve(fragments);
  }
};

function encode(metadata, markdown) {
  return "<!-- ALC:FRAGMENT-JSON:BEGIN -->\\n" +
    helpers.stableStringify(metadata) +
    "\\n<!-- ALC:FRAGMENT-JSON:END -->\\n" + markdown;
}

(async function () {
  var childMetadata = JSON.parse(JSON.stringify(baseMetadata));
  childMetadata.revision = 2;
  childMetadata.parent_semantic_digest = baseDigest;
  childMetadata.title = "child";
  var childMarkdown = "external child";
  var childDigest = await helpers.semanticDigest(childMetadata, childMarkdown);
  externalEntry.name = helpers.revisionFilename(2, childDigest);
  externalValue = encode(childMetadata, childMarkdown);
  entries = [embeddedEntry, externalEntry];

  assert(await helpers.loadDirectoryRevisions(directory), "first sync did not commit");
  assert(glossaryRequests === 1, "legacy payload skipped the glossary directory scan");
  assert(embeddedReads === 0, "embedded revision was read from disk");
  assert(externalGetFileCalls === 1 && externalTextCalls === 1, "external revision was not read once");
  assert(helpers.state.selected.get("note-1").revision === 2, "external child was not selected");

  assert(await helpers.loadDirectoryRevisions(directory), "cached sync did not commit");
  assert(externalGetFileCalls === 2, "cached sync did not refresh file metadata");
  assert(externalTextCalls === 1, "unchanged external bytes were read again");

  externalValue = "broken";
  externalStamp = 2;
  assert(await helpers.loadDirectoryRevisions(directory), "broken-file sync did not commit");
  assert(externalTextCalls === 2, "changed external bytes were not reread");
  assert(helpers.state.selected.get("note-1").revision === 1, "broken child remained selected");
  assert(
    helpers.state.diagnostics.some(function (value) {
      return value.includes("Ignored invalid fragment file");
    }),
    "broken external file did not produce a diagnostic"
  );

  externalValue = encode(childMetadata, childMarkdown);
  externalStamp = 3;
  assert(await helpers.loadDirectoryRevisions(directory), "repaired-file sync did not commit");
  assert(externalTextCalls === 3, "repaired external bytes were not reread");
  assert(helpers.state.selected.get("note-1").revision === 2, "repaired child was not selected");

  var selectedBeforeFailure = helpers.state.selected.get("note-1").semantic_digest;
  var cacheSizeBeforeFailure = helpers.state.directoryFileCache.size;
  failEnumeration = true;
  var enumerationFailed = false;
  try {
    await helpers.loadDirectoryRevisions(directory);
  } catch (error) {
    enumerationFailed = error.message === "enumeration failed";
  }
  failEnumeration = false;
  assert(enumerationFailed, "directory enumeration failure was hidden");
  assert(
    helpers.state.selected.get("note-1").semantic_digest === selectedBeforeFailure &&
      helpers.state.directoryFileCache.size === cacheSizeBeforeFailure,
    "failed directory sync replaced the last complete snapshot"
  );

  var siblingMetadata = JSON.parse(JSON.stringify(childMetadata));
  siblingMetadata.title = "sibling";
  var siblingMarkdown = "external sibling";
  var siblingDigest = await helpers.semanticDigest(siblingMetadata, siblingMarkdown);
  var siblingValue = encode(siblingMetadata, siblingMarkdown);
  var siblingEntry = {
    kind: "file",
    name: helpers.revisionFilename(2, siblingDigest),
    getFile: function () {
      return Promise.resolve({
        size: siblingValue.length,
        lastModified: 1,
        text: function () { return Promise.resolve(siblingValue); }
      });
    }
  };
  entries = [embeddedEntry, externalEntry, siblingEntry];
  assert(await helpers.loadDirectoryRevisions(directory), "fork sync did not commit");
  assert(helpers.state.selected.get("note-1").revision === 1, "fork did not retain its common parent");
  assert(
    helpers.state.diagnostics.some(function (value) { return value.includes("forks after revision 1"); }),
    "external fork was not diagnosed"
  );

  entries = [embeddedEntry];
  assert(await helpers.loadDirectoryRevisions(directory), "deletion sync did not commit");
  assert(helpers.state.selected.get("note-1").revision === 1, "deleted external files remained selected");
  assert(helpers.state.directoryFileCache.size === 0, "deleted external cache entries survived");
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_selection_sync_rerenders_only_changed_anchor_chunk() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    refreshChangedSelections: refreshChangedSelections,
    rebuildDiagnostics: rebuildDiagnostics
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
var firstRenders = 0;
var secondRenders = 0;
var firstNode = {
  replaceChildren: function () { firstRenders += 1; },
  querySelectorAll: function () { return []; }
};
var secondNode = {
  replaceChildren: function () { secondRenders += 1; },
  querySelectorAll: function () { return []; }
};
var diagnosticsRoot = {
  replaceChildren: function () {},
  appendChild: function () {}
};
globalThis.document = {
  createDocumentFragment: function () { return {}; }
};
var firstChunk = {
  chunk_id: "chunk-1",
  kind: "content",
  block_start: 0,
  block_end: 0
};
var secondChunk = {
  chunk_id: "chunk-2",
  kind: "content",
  block_start: 0,
  block_end: 0
};
var previous = {
  fragment_id: "note-1",
  semantic_digest: "a".repeat(64),
  priority: 110,
  anchor: {kind: "section", target_id: "section-1"}
};
var current = {
  fragment_id: "note-1",
  semantic_digest: "b".repeat(64),
  priority: 110,
  anchor: {kind: "section", target_id: "section-1"}
};
helpers.state.payload = {
  publication: {
    source_document: {blocks: []},
    outline: [{section_id: "section-1", anchor_block_id: "block-1"}]
  }
};
helpers.state.selected = new Map([["note-1", current]]);
helpers.state.diagnostics = [];
helpers.state.readerShellReady = true;
helpers.state.diagnosticsRoot = diagnosticsRoot;
helpers.state.renderPlan = [firstChunk, secondChunk];
helpers.state.renderedChunkIds = new Set(["chunk-1", "chunk-2"]);
helpers.state.chunkNodes = new Map([
  ["chunk-1", firstNode],
  ["chunk-2", secondNode]
]);
helpers.state.chunkByTargetId = new Map([
  ["block-block-1", firstChunk],
  ["block-block-2", secondChunk]
]);
helpers.state.laneFallbackListener = function () {};
helpers.refreshChangedSelections(new Map([["note-1", previous]]));
assert(firstRenders === 1, "changed section anchor chunk was not rerendered once");
assert(secondRenders === 0, "unchanged chunk was rerendered");
current.anchor = {kind: "section", target_id: "missing-section"};
helpers.rebuildDiagnostics();
helpers.rebuildDiagnostics();
assert(
  helpers.state.diagnostics.filter(function (value) {
    return value.includes("unknown anchor");
  }).length === 1,
  "incremental diagnostics lost or duplicated the unknown-anchor warning"
);
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_markdown_export_uses_latest_or_embedded_change_scope() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    markdown_it = _text("markdown-it/markdown-it.min.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        "module = undefined; exports = undefined; define = undefined;\n"
        + markdown_it
        + "\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    setupMarkdown: setupMarkdown,
    buildMarkdownPackage: buildMarkdownPackage,
    buildPlainMarkdown: buildPlainMarkdown,
    captureInitialSelection: captureInitialSelection,
    exportRevisionState: exportRevisionState
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
helpers.setupMarkdown();
var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var blocks = [
  {block_id: "block-1", kind: "paragraph", ordinal: 0, locator: {}, payload: {text: "one"}},
  {block_id: "block-2", kind: "paragraph", ordinal: 1, locator: {}, payload: {text: "two"}}
];
function revision(fragmentId, digest, role, target, body, priority, number, parent, title) {
  return {
    schema_version: "alc.render.fragment_revision.v3",
    source: source,
    fragment_id: fragmentId,
    revision: number,
    parent_semantic_digest: parent,
    anchor: {
      kind: "block",
      target_id: target,
      related_blocks: [{block_id: target}]
    },
    priority: priority,
    role: role,
    language: "zh-CN",
    title: title || null,
    citation_ids: [],
    appearance: null,
    deleted: false,
    provenance: {producer: "alc-render-browser"},
    markdown_body: body,
    semantic_digest: digest
  };
}
var first = revision("translation-1", "1".repeat(64), "translation", "block-1", "旧译文", 10, 1, null);
var unchanged = revision("translation-2", "2".repeat(64), "translation", "block-2", "未改译文", 10, 1, null);
var companion = revision(
  "companion-1", "3".repeat(64), "companion", "block-1",
  "未改伴读\\n\\n$$q(z)=-1。$$", 20, 1, null
);
var reportDigest = "d".repeat(64);
var unusedDigest = "e".repeat(64);
var htmlDigest = "f".repeat(64);
var guide = revision(
  "guide-1", "6".repeat(64), "guide", "block-2",
  "导读正文\\n\\n- 第一项\\n- 第二项\\n\\n```text\\n示例\\n```" +
    "\\n\\n[报告][asset]\\n\\n[asset]: report.json",
  30, 1, null, "阅读提示"
);
helpers.state.payload = {
  source_identity: source,
  resources: [{
    artifact_digest: reportDigest,
    media_type: "application/json",
    logical_name: "report.json",
    size: 3,
    data_uri: "data:application/json;base64,e30K"
  }, {
    artifact_digest: unusedDigest,
    media_type: "image/png",
    logical_name: "unused.png",
    size: 1,
    data_uri: "data:image/png;base64,AA=="
  }, {
    artifact_digest: htmlDigest,
    media_type: "image/png",
    logical_name: "html.png",
    size: 1,
    data_uri: "data:image/png;base64,AA=="
  }],
  publication: {
    publication_digest: "c".repeat(64),
    source_document: {blocks: blocks, metadata: {}},
    outline: [],
    glossary: [],
    bibliography: [],
    labels: {document_title: "Fearful Symmetry", translation: "译名"},
    reader_profile: {target_language: "zh-CN"}
  }
};
helpers.state.selected = new Map([
  [first.fragment_id, first],
  [unchanged.fragment_id, unchanged],
  [companion.fragment_id, companion],
  [guide.fragment_id, guide]
]);
helpers.captureInitialSelection();
var revised = revision(
  first.fragment_id, "4".repeat(64), "translation", "block-1",
  "最新译文", 10, 2, first.semantic_digest, "改动标题"
);
var note = revision(
  "note-1", "5".repeat(64), "note", "block-2",
  "新增笔记\\n\\n[报告][asset]\\n\\n[asset]: report.json" +
    "\\n\\n<img src=\\\"html.png\\\" alt=\\\"HTML image\\\">" +
    "\\n\\n`<img src=\\\"resources/" + unusedDigest +
    "/unused.png\\\">`" +
    "\\n\\n    <img src=\\\"resources/" + unusedDigest +
    "/unused.png\\\">" +
    "\\n\\n```text\\n[ignored](resources/" + unusedDigest +
    "/unused.png)\\n```", 110, 1, null
);
helpers.state.selected = new Map([
  [first.fragment_id, revised],
  [unchanged.fragment_id, unchanged],
  [companion.fragment_id, companion],
  [guide.fragment_id, guide],
  [note.fragment_id, note]
]);
helpers.state.revisions = new Map([
  [first.fragment_id, [first, revised]],
  [unchanged.fragment_id, [unchanged]],
  [companion.fragment_id, [companion]],
  [guide.fragment_id, [guide]],
  [note.fragment_id, [note]]
]);
helpers.state.activeFragmentIds = new Set([
  first.fragment_id, unchanged.fragment_id, companion.fragment_id,
  guide.fragment_id
]);
var translationOnly = helpers.buildMarkdownPackage(
  "all", new Set(["translation"])
).markdown;
var changedTranslation = helpers.buildMarkdownPackage(
  "changed", new Set(["translation"])
).markdown;
assert(
  translationOnly.includes("最新译文") && translationOnly.includes("未改译文"),
  "all-latest translation package omitted content"
);
assert(
  changedTranslation.includes("最新译文") &&
    !changedTranslation.includes("未改译文") &&
    changedTranslation.includes("## 改动标题"),
  "changed translation package does not match current selections"
);
assert(
  helpers.buildMarkdownPackage("changed", new Set(["companion"])) === null,
  "unchanged companion content was exported as changed"
);
assert(
  helpers.buildMarkdownPackage(
    "changed", new Set(["note"])
  ).markdown.includes("新增笔记"),
  "new browser fragment was not exported as changed"
);
var combined = helpers.buildMarkdownPackage(
  "all", new Set(["source", "translation", "guide", "companion"])
);
var reportPath = "resources/" + reportDigest + "/report.json";
var htmlPath = "resources/" + htmlDigest + "/html.png";
assert(
  combined.markdown.includes("one") && combined.markdown.includes("two"),
  "combined Markdown omitted selected source content"
);
assert(
    combined.markdown.includes("最新译文") &&
    combined.markdown.includes("未改译文") &&
    combined.markdown.includes("未改伴读") &&
    combined.markdown.includes("导读正文"),
    "combined Markdown omitted a checked overlay category"
  );
assert(
  combined.markdown.includes("> **伴读**\\n>\\n> 未改伴读") &&
    combined.markdown.includes(
      "> **导读 · 阅读提示**\\n>\\n> 导读正文\\n>\\n> - 第一项"
    ) && combined.markdown.includes("> ```text\\n> 示例\\n> ```"),
  "combined Markdown did not quote companion and guide content"
);
assert(
  combined.markdown.includes("> $$\\n> q(z)=-1。\\n> $$") &&
    !combined.markdown.includes("> $$q(z)=-1。$$"),
  "combined Markdown did not canonicalize legacy companion display math"
);
assert(
  combined.markdown.includes("> [报告][asset]") &&
    combined.markdown.includes("> [asset]: " + reportPath),
  "combined package did not preserve a quoted local reference link"
);
assert(
  combined.manifest.resources.length === 1 &&
    combined.manifest.resources[0].path === reportPath,
  "all-latest package did not limit resources to selected referenced content"
);
var guideOnlyPackage = helpers.buildMarkdownPackage(
  "all", new Set(["guide"])
);
assert(
  guideOnlyPackage.manifest.resources.length === 1 &&
    guideOnlyPackage.manifest.resources[0].path === reportPath,
  "guide-only package did not retain only its referenced resource"
);
var companionOnlyPackage = helpers.buildMarkdownPackage(
  "all", new Set(["companion"])
);
assert(
  companionOnlyPackage.manifest.resources.length === 0,
  "companion-only package retained unrelated publication resources"
);
var plainSupplements = helpers.buildPlainMarkdown(
  "all", new Set(["source", "guide"])
);
assert(
  plainSupplements.includes("> 报告") &&
    !plainSupplements.includes(reportPath) &&
    !plainSupplements.includes("[asset]:"),
  "plain Markdown did not degrade a quoted local reference link"
);
assert(!combined.markdown.includes("新增笔记"), "combined Markdown included an unchecked role");
var staleRole = helpers.buildMarkdownPackage(
  "all", new Set(["source", "retired-dynamic-role"])
);
assert(
  staleRole.manifest.selected_content.join(",") === "source",
  "all-latest manifest retained a role absent from the current selection"
);
var changesPackage = helpers.buildMarkdownPackage(
  "changed", new Set(["source", "translation", "note"])
);
var changes = changesPackage.markdown;
assert(changes.includes("最新译文") && changes.includes("新增笔记"), "changed package omitted selected changes");
assert(!changes.includes("未改译文") && !changes.includes("one"), "changed package included unchanged or source content");
assert(
  changes.includes("## 改动标题") && !changes.includes("## 译文") &&
    changes.includes("> **笔记**\\n>\\n> 新增笔记") &&
    changes.includes("> [asset]: " + reportPath) &&
    changes.includes('<img src="' + htmlPath + '" alt="HTML image">'),
  "changed package did not preserve translation titles or quote notes"
);
assert(
  changesPackage.manifest.selected_content.join(",") === "translation,note",
  "changed manifest content selection does not match emitted roles"
);
assert(
  changesPackage.manifest.resources.length === 2 &&
    changesPackage.manifest.resources.map(function (item) {
      return item.path;
    }).join(",") === [reportPath, htmlPath].join(","),
  "changed package did not limit resources to referenced content"
);
var plainChanges = helpers.buildPlainMarkdown(
  "changed", new Set(["source", "translation", "note"])
);
assert(
  plainChanges.includes("最新译文") && plainChanges.includes("新增笔记"),
  "plain changed Markdown omitted selected changes"
);
assert(
  !plainChanges.includes("未改译文") && !plainChanges.includes("one"),
  "plain changed Markdown included unchanged or source content"
);
assert(
  plainChanges.includes("> **笔记**\\n>\\n> 新增笔记"),
  "plain changed Markdown did not quote note content"
);
assert(
  plainChanges.includes("> 报告") &&
    !plainChanges.includes(reportPath) && !plainChanges.includes("[asset]:"),
  "plain changed Markdown retained a quoted local reference dependency"
);
assert(
  plainChanges.includes("[Figure: HTML image]") &&
    !plainChanges.includes(htmlPath),
  "plain changed Markdown did not strip a rewritten HTML image"
);
var exported = helpers.exportRevisionState();
assert(exported.revisions.length === 6, "full export omitted a revision history entry");
assert(
  exported.selected_revision_digests.join(",") === [
    revised.semantic_digest,
    unchanged.semantic_digest,
    companion.semantic_digest,
    guide.semantic_digest,
    note.semantic_digest
  ].join(","),
  "full export selected digest order changed"
);
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_builds_complete_portable_markdown_package_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    markdown_it = _text("markdown-it/markdown-it.min.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        "module = undefined; exports = undefined; define = undefined;\n"
        + markdown_it
        + "\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcReaderTest = {
    state: state,
    setupMarkdown: setupMarkdown,
    buildMarkdownPackage: buildMarkdownPackage,
    buildPlainMarkdown: buildPlainMarkdown,
    buildStoredZip: buildStoredZip,
    rewriteMarkdownResourceTargets: rewriteMarkdownResourceTargets,
    markdownReferencedResourcePaths: markdownReferencedResourcePaths,
    stripPortableMarkdownResources: stripPortableMarkdownResources,
    portableResourceBasename: portableResourceBasename,
    portableResourceTarget: portableResourceTarget
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function revision(fragmentId, digest, target, body, priority, deleted) {
  return {
    schema_version: "alc.render.fragment_revision.v3",
    fragment_id: fragmentId,
    revision: 2,
    parent_semantic_digest: "f".repeat(64),
    anchor: {
      kind: "block",
      target_id: target,
      related_blocks: [{block_id: target}]
    },
    priority: priority,
    role: "translation",
    language: "zh-CN",
    title: null,
    citation_ids: [],
    appearance: null,
    deleted: Boolean(deleted),
    provenance: {producer: "alc-render-browser"},
    markdown_body: body,
    semantic_digest: digest
  };
}
function bytesEqual(left, right) {
  if (left.length !== right.length) return false;
  return left.every(function (value, index) { return value === right[index]; });
}
function storedZipEntries(bytes) {
  var view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  var decoder = new TextDecoder();
  var entries = new Map();
  var offset = 0;
  while (view.getUint32(offset, true) === 0x04034b50) {
    var size = view.getUint32(offset + 18, true);
    var nameSize = view.getUint16(offset + 26, true);
    var extraSize = view.getUint16(offset + 28, true);
    var nameStart = offset + 30;
    var dataStart = nameStart + nameSize + extraSize;
    var name = decoder.decode(bytes.slice(nameStart, nameStart + nameSize));
    entries.set(name, {
      crc32: view.getUint32(offset + 14, true),
      bytes: bytes.slice(dataStart, dataStart + size)
    });
    offset = dataStart + size;
  }
  assert(view.getUint32(offset, true) === 0x02014b50, "ZIP central directory is missing");
  return entries;
}

var imageDigest = "a".repeat(64);
var reportDigest = "b".repeat(64);
var blocks = [
  {
    block_id: "heading", ordinal: 0, kind: "heading", payload: {
      text: "Source title", level: 1
    }
  },
  {
    block_id: "paragraph", ordinal: 1, kind: "paragraph", payload: {
      text: "Fallback x report",
      inline_spans: [
        {kind: "text", text: "Fallback "},
        {kind: "math", tex: "x"},
        {kind: "text", text: " "},
        {kind: "link", text: "report", target: "report.json"}
      ]
    }
  },
  {
    block_id: "list", ordinal: 2, kind: "list", payload: {
      ordered: false,
      items: [{text: "one", inline_spans: [{kind: "text", text: "one"}]}]
    }
  },
  {
    block_id: "code", ordinal: 3, kind: "code", payload: {
      text: "value = ```", language: "python"
    }
  },
  {
    block_id: "source-list", ordinal: 4, kind: "list", payload: {
      ordered: true,
      items: [{
        text: "first\ncontinued",
        inline_spans: [{kind: "text", text: "first\ncontinued"}]
      }]
    }
  },
  {
    block_id: "equation", ordinal: 4, kind: "equation", payload: {
      tex: "y=1", display: true, label: "old"
    }
  },
  {
    block_id: "table", ordinal: 5, kind: "table", payload: {
      headers: ["A|B", "C\\D"],
      rows: [["line 1\nline 2", "value"]],
      caption: "Source table"
    }
  },
  {
    block_id: "figure", ordinal: 6, kind: "figure", payload: {
      asset_digest: imageDigest,
      alt_text: "A diagram",
      caption: "Source caption",
      target: "images/private.png",
      logical_name: "figure.png"
    }
  },
  {
    block_id: "linked", ordinal: 7, kind: "paragraph", payload: {
      text: "Source linked paragraph", inline_spans: []
    }
  },
  {
    block_id: "page", ordinal: 8, kind: "paragraph", payload: {
      text: "<!-- PDF_PAGE: 2 -->", inline_spans: []
    }
  },
  {
    block_id: "comment", ordinal: 9, kind: "paragraph", payload: {
      text: "<!-- internal parser marker -->", inline_spans: []
    }
  }
];
var preferredHeading = revision(
  "translation-heading-a", "1".repeat(64), "heading", "# 译题\n", 10
);
var laterHeading = revision(
  "translation-heading-b", "2".repeat(64), "heading", "# 次选题\n", 10
);
var list = revision(
  "translation-list", "3".repeat(64), "list", "- 甲\n", 10
);
var code = revision(
  "translation-code", "8".repeat(64), "code",
  "````\nvalue = ```\n````\n", 10
);
var equation = revision(
  "translation-equation", "7".repeat(64), "equation", "$$\ny=1\n$$\n", 10
);
var figure = revision(
  "translation-figure", "4".repeat(64), "figure", "译图注\n", 10
);
var linked = revision(
  "translation-linked", "5".repeat(64), "linked",
  "参见 [报告](report.json)、[网站](https://example.test) 与 `[_](report.json)`.\n\n" +
    "![Remote diagram](https://example.test/diagram.png)\n\n" +
    "<img src=\"report.json\" alt=\"HTML diagram\">\n\n" +
    "[![Nested remote](https://example.test/nested.png)](report.json)\n\n" +
    "<img title=\"a > b\" alt=\"Quoted diagram\"> trailing\n\n" +
    "`<img src=\"report.json\" alt=\"Inline code image\">`\n\n" +
    "> [quoted-asset]: report.json \"Quoted title\"\n" +
    "> [quoted-report][quoted-asset]\n\n" +
    "```text\n[report]: resources/" + reportDigest + "/report.json\n```\n\n" +
    "[report]\n\n" +
    "~~~text\n[raw](report.json)\n~~~\n\n    [indent](report.json)\n\n" +
    "BIB inline [Smith 2020](#bib.bib1).\n\n" +
    "BIB unmatched ` and [Smith 2020](#bib.bib1).\n\n" +
    "BIB destination [Smith 2020](\n#bib.bib1).\n\n" +
    "BIB label [Smith\n2020](#bib.bib1).\n\n" +
    "BIB title [Smith 2020](#bib.bib1\n \"Paper\").\n\n" +
    "[Jones 2021][legacy-bib]\n\n" +
    "[legacy-bib]: #bib.bib2\n\n" +
    "![Reference figure](#bib.bib3)\n\n" +
    "[^asset]: report.json\n",
  10
);
var deletedParagraph = revision(
  "translation-paragraph", "6".repeat(64), "paragraph", "", 1, true
);
var helpers = globalThis.__alcReaderTest;
helpers.setupMarkdown();
helpers.state.payload = {
  publication: {
    publication_digest: "c".repeat(64),
    source_document: {
      document_digest: "d".repeat(64),
      blocks: blocks,
      metadata: {
        equation_label_reconciliation: {
          equation: {effective_label: "(7)"}
        },
        document_notes: {
          schema_version: "ac.document.document_notes.v1",
          items: [
            {kind: "metadata", text: "Metadata note", before_block_id: "code"},
            {kind: "metadata", text: "Marker-bound note", before_block_id: "page"},
            {kind: "source_page", page_number: 2, before_block_id: "code"}
          ]
        }
      }
    },
    outline: [],
    glossary: [
      {entry_id: "term-reader", term: "Reader", translated_term: "读者", definition: "[术语附件](report.json)", anchor_ids: ["paragraph"], citations: []},
      {entry_id: "term-opaque", extra: "kept"}
    ],
    bibliography: [
      {evidence_id: "ref-1", title: "Reference", source: "https://example.test/ref", dois: ["10.1/x"], arxiv_ids: ["1234.5678"], cached_document: null},
      {evidence_id: "ref-alias", title: "Duplicate", source: "https://example.test/ref/", dois: ["10.1/x", "10.2/y"], arxiv_ids: ["1234.5678"]},
      {title: "Title only", year: 2024},
      {title: "Title only", year: 2025},
      {opaque: "reference-data"}
    ],
    labels: {document_title: "Portable", glossary: "术语表", references: "参考文献"},
    reader_profile: {title: "Portable", target_language: "zh-CN"}
  },
  source_identity: {rich_document_digest: "d".repeat(64)},
  resources: [
    {
      artifact_digest: imageDigest,
      media_type: "image/png",
      logical_name: "figure.png",
      size: 2,
      data_uri: "data:image/png;base64,AAE="
    },
    {
      artifact_digest: reportDigest,
      media_type: "application/json",
      logical_name: "report.json",
      size: 3,
      data_uri: "data:application/json;base64,e30K"
    }
  ]
};
helpers.state.selected = new Map([
  [laterHeading.fragment_id, laterHeading],
  [preferredHeading.fragment_id, preferredHeading],
  [list.fragment_id, list],
  [code.fragment_id, code],
  [equation.fragment_id, equation],
  [figure.fragment_id, figure],
  [linked.fragment_id, linked],
  [deletedParagraph.fragment_id, deletedParagraph]
]);

(async function () {
  var localeCompare = String.prototype.localeCompare;
  String.prototype.localeCompare = function () {
    throw new Error("portable export used locale-sensitive ordering");
  };
  var first;
  var second;
  try {
    first = helpers.buildMarkdownPackage(
      "all", new Set(["translation", "glossary", "references"])
    );
    second = helpers.buildMarkdownPackage(
      "all", new Set(["translation", "glossary", "references"])
    );
  } finally {
    String.prototype.localeCompare = localeCompare;
  }
  var markdown = first.markdown;
  var imagePath = "resources/" + imageDigest + "/figure.png";
  var reportPath = "resources/" + reportDigest + "/report.json";
  assert(markdown.startsWith("# 译题\n"), "preferred translated heading was not first");
  assert(!markdown.includes("次选题"), "lower-precedence translation was exported");
  assert(markdown.includes("Fallback $x$ [report](" + reportPath + ")"), "source fallback lost inline structure");
  assert(markdown.includes("- 甲"), "selected list translation was omitted");
  assert(markdown.includes("1. first\n   continued"), "source list continuation indentation is wrong");
  assert(markdown.includes("````python\nvalue = ```\n````"), "source code fence was not preserved");
  assert(markdown.includes("$$\ny=1\n$$\n\nEquation label: (7)"), "effective equation label was omitted");
  assert(markdown.includes("| A\\|B | C\\\\D |"), "table headers were not escaped");
  assert(markdown.includes("| line 1<br>line 2 | value |"), "table newlines were not portable");
  assert(markdown.includes("![A diagram](" + imagePath + ")"), "figure resource path was not packaged");
  assert(markdown.includes("译图注") && !markdown.includes("Source caption"), "translated figure caption was not recombined");
  assert(markdown.includes("[报告](" + reportPath + ")"), "fragment resource link was not rewritten");
  assert(
    markdown.includes("> [quoted-asset]: " + reportPath + " \"Quoted title\"") &&
      markdown.includes("> [quoted-report][quoted-asset]"),
    "blockquote reference definition was not rewritten"
  );
  assert(markdown.includes("[网站](https://example.test)"), "external link was rewritten");
  assert(
    markdown.includes("BIB inline Smith 2020.") &&
      markdown.includes("BIB unmatched ` and Smith 2020.") &&
      markdown.includes("BIB destination Smith 2020.") &&
      markdown.includes("BIB label Smith\n2020.") &&
      markdown.includes("BIB title Smith 2020.") &&
      markdown.includes("Jones 2021") &&
      markdown.includes("Reference figure") &&
      !markdown.includes("#bib.bib") &&
      !markdown.includes("!Reference figure"),
    "Markdown package retained or corrupted a legacy bibliography link"
  );
  assert(markdown.includes("`[_](report.json)`"), "inline code was rewritten");
  assert(markdown.includes("[raw](report.json)"), "fenced code was rewritten");
  assert(markdown.includes("    [indent](report.json)"), "indented code was rewritten");
  assert(markdown.includes("[^asset]: report.json"), "footnote definition was rewritten");
  assert(markdown.includes("> Metadata note") && !markdown.includes("Document page"), "document-note boundary changed");
  assert(markdown.includes("> Marker-bound note"), "note before a technical marker was dropped");
  assert(!markdown.includes("PDF_PAGE") && !markdown.includes("internal parser marker"), "technical marker leaked into Markdown");
  assert(markdown.includes("## 术语表") && markdown.includes("Reader / 读者"), "glossary was omitted");
  assert(
    markdown.includes("[术语附件](" + reportPath + ")"),
    "glossary definition resource link was not rewritten"
  );
  assert(markdown.includes('"extra":"kept"'), "unknown glossary data was dropped");
  assert(!markdown.includes('"anchor_ids"'), "glossary leaked internal anchor metadata");
  assert(markdown.includes("## 参考文献"), "bibliography was omitted");
  assert(!markdown.includes('"cached_document"'), "bibliography leaked internal cache metadata");
  assert(markdown.includes('"opaque":"reference-data"'), "unknown bibliography data was dropped");
  assert((markdown.match(/[*][*]Title only[*][*]/g) || []).length === 2, "title-only references collapsed");
  assert(markdown.includes("DOI: 10.2/y"), "bibliography aliases lost a DOI");
  assert(markdown.match(/https:\/\/example[.]test\/ref/g).length === 1, "bibliography aliases were not deduplicated");

  var manifest = first.manifest;
  assert(manifest.schema_version === "alc.render.markdown_export.v1", "manifest schema is wrong");
  assert(manifest.document === "document.md", "manifest document path is wrong");
  assert(
    manifest.selected_content.join(",") === "translation,glossary,references",
    "default complete package did not retain appendix selections"
  );
  assert(manifest.resources.length === 2, "manifest omitted a referenced resource");
  assert(manifest.selected_translation_revision_digests.join(",") === [
    preferredHeading.semantic_digest,
    list.semantic_digest,
    code.semantic_digest,
    equation.semantic_digest,
    figure.semantic_digest,
    linked.semantic_digest
  ].join(","), "manifest translation selection is not in source order");
  assert(
    manifest.selected_revision_digests.join(",") ===
      manifest.selected_translation_revision_digests.join(","),
    "complete manifest did not expose all selected revisions"
  );

  var bilingual = helpers.buildMarkdownPackage(
    "all", new Set(["source", "translation"])
  );
  assert(
    bilingual.manifest.selected_content.join(",") === "source,translation",
    "combined manifest content selection is wrong"
  );
  assert(
    (bilingual.markdown.match(/[*][*]译文(?: ·[^*]+)?[*][*]/g) || []).length === 0,
    "combined Markdown included a translation role label"
  );
  assert(
    bilingual.markdown.includes("Source caption") &&
      bilingual.markdown.includes("译图注"),
    "combined source and translation figure captions were not both exported"
  );
  assert(
    bilingual.markdown.split("![A diagram](" + imagePath + ")").length === 2,
    "combined source and translation duplicated the figure asset"
  );
  assert(
    !bilingual.markdown.includes("## 术语表") &&
      !bilingual.markdown.includes("## 参考文献"),
    "unchecked appendices were included in combined Markdown"
  );
  var glossaryOnlyPackage = helpers.buildMarkdownPackage(
    "all", new Set(["glossary"])
  );
  var glossaryOnly = glossaryOnlyPackage.markdown;
  assert(
    glossaryOnly.startsWith("## 术语表") &&
      !glossaryOnly.includes("Source title") &&
      !glossaryOnly.includes("## 参考文献"),
    "glossary-only export included document or bibliography content"
  );
  assert(
    glossaryOnlyPackage.manifest.resources.length === 1 &&
      glossaryOnlyPackage.manifest.resources[0].path === reportPath,
    "glossary-only package omitted its referenced resource"
  );
  var referencesOnlyPackage = helpers.buildMarkdownPackage(
    "all", new Set(["references"])
  );
  var referencesOnly = referencesOnlyPackage.markdown;
  assert(
    referencesOnly.startsWith("## 参考文献") &&
      !referencesOnly.includes("Source title") &&
      !referencesOnly.includes("## 术语表"),
    "references-only export included document or glossary content"
  );
  assert(
    referencesOnlyPackage.manifest.resources.length === 0,
    "references-only package retained unrelated publication resources"
  );
  var plain = helpers.buildPlainMarkdown(
    "all", new Set(["translation"])
  );
  assert(!plain.includes("!["), "plain Markdown retained image syntax");
  assert(
    !plain.includes("## 术语表") && !plain.includes("## 参考文献"),
    "plain Markdown included unchecked appendices"
  );
  assert(
    !plain.includes(imagePath) && !plain.includes("](" + reportPath + ")"),
    "plain Markdown retained a packaged resource dependency"
  );
  assert(
      plain.includes("[Figure: A diagram]") &&
      plain.includes("[Figure: Remote diagram]") &&
      plain.includes("[Figure: HTML diagram]") && plain.includes("译图注"),
    "plain Markdown lost the readable figure description or caption"
  );
  assert(
    plain.includes("[Figure: Nested remote]") &&
      plain.includes("[Figure: Quoted diagram] trailing") &&
      !plain.includes('title="a > b"'),
    "plain Markdown retained a nested or quoted-attribute image"
  );
  assert(
    plain.includes("\n[report]\n"),
    "a fenced pseudo reference definition changed plain body text"
  );
  assert(
    plain.includes("参见 报告、[网站](https://example.test)") &&
      plain.includes("`[_](report.json)`") &&
      plain.includes("`<img src=\"report.json\" alt=\"Inline code image\">`") &&
      plain.includes("[raw](report.json)") &&
      plain.includes("    [indent](report.json)"),
    "plain Markdown did not degrade local links or preserve external/code links"
  );
  assert(
    plain.includes("BIB inline Smith 2020.") &&
      plain.includes("BIB unmatched ` and Smith 2020.") &&
      plain.includes("BIB destination Smith 2020.") &&
      plain.includes("BIB label Smith\n2020.") &&
      plain.includes("BIB title Smith 2020.") &&
      plain.includes("Jones 2021") &&
      plain.includes("Reference figure") &&
      !plain.includes("#bib.bib") &&
      !plain.includes("!Reference figure"),
    "plain Markdown retained or corrupted a legacy bibliography link"
  );

  assert(first.archive.type === "application/zip", "archive media type is wrong");
  var firstBytes = new Uint8Array(await first.archive.arrayBuffer());
  var secondBytes = new Uint8Array(await second.archive.arrayBuffer());
  assert(bytesEqual(firstBytes, secondBytes), "identical exports were not byte deterministic");
  var entries = storedZipEntries(firstBytes);
  assert(entries.size === 4, "ZIP entry count is wrong");
  assert(entries.has("document.md") && entries.has("manifest.json"), "ZIP metadata files are missing");
  assert(entries.has(imagePath) && entries.has(reportPath), "ZIP resource entries are missing");
  assert(entries.get(imagePath).crc32 === 0x36de2269, "ZIP entry CRC-32 is wrong");
  assert(bytesEqual(entries.get(imagePath).bytes, new Uint8Array([0, 1])), "image bytes changed");
  assert(new TextDecoder().decode(entries.get(reportPath).bytes) === "{}\n", "report bytes changed");
  var rejectedLongName = false;
  try {
    helpers.buildStoredZip([{
      path: "x".repeat(0x10000),
      bytes: new Uint8Array([1])
    }]);
  } catch (_error) {
    rejectedLongName = true;
  }
  assert(rejectedLongName, "ZIP accepted a filename larger than its 16-bit field");
  assert(
    helpers.portableResourceBasename("figure #1(draft).png") ===
      "figure--1-draft-.png",
    "portable basename retained Markdown or URL delimiters"
  );
  assert(
    Array.from(
      helpers.portableResourceBasename("a😀" + "b".repeat(159))
    )[0] === "😀",
    "portable basename split an astral Unicode character"
  );
  var navigationAliases = new Map([
    ["https://example.test", "resources/external"],
    ["#section", "resources/anchor"],
    ["/absolute", "resources/absolute"],
    ["?query", "resources/query"],
    ["report.json", reportPath]
  ]);
  ["https://example.test", "#section", "/absolute", "?query"].forEach(
    function (target) {
      assert(
        helpers.portableResourceTarget(target, navigationAliases) === target,
        "navigation target was rewritten as a resource"
      );
    }
  );
  assert(
    helpers.portableResourceTarget("report.json", navigationAliases) === reportPath,
    "relative resource alias was not rewritten"
  );
  console.log(Buffer.from(firstBytes).toString("base64"));
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
'''
    )

    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    archive = base64.b64decode(completed.stdout.strip(), validate=True)
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        assert bundle.testzip() is None
        assert bundle.namelist() == [
            "document.md",
            "manifest.json",
            f"resources/{'a' * 64}/figure.png",
            f"resources/{'b' * 64}/report.json",
        ]
        assert bundle.read(f"resources/{'a' * 64}/figure.png") == b"\x00\x01"
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["schema_version"] == "alc.render.markdown_export.v1"


def test_reader_scans_nested_revision_directories_with_bounded_concurrency() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        """
globalThis.window = globalThis;
"""
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {collectMarkdownFiles: collectMarkdownFiles};
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var active = 0;
var maximum = 0;
function directory(name) {
  return {
    kind: "directory",
    name: name,
    values: async function* () {
      active += 1;
      maximum = Math.max(maximum, active);
      await new Promise(function (resolve) { setTimeout(resolve, 5); });
      yield {
        kind: "file",
        name: "revision-" + name + ".md",
        getFile: function () { throw new Error("file bytes were read during enumeration"); }
      };
      active -= 1;
    }
  };
}
var directories = Array.from({length: 24}, function (_value, index) {
  return directory(String(24 - index).padStart(2, "0"));
});
var root = {
  values: async function* () {
    for (var index = 0; index < directories.length; index += 1) {
      yield directories[index];
    }
  }
};
(async function () {
  var files = await globalThis.__alcReaderTest.collectMarkdownFiles(root);
  assert(maximum === 8, "directory enumeration was not bounded at eight");
  assert(files.length === 24, "directory enumeration lost files");
  var paths = files.map(function (entry) { return entry.path.join("/"); });
  var sorted = paths.slice().sort();
  assert(paths.join(",") === sorted.join(","), "directory results were not deterministic");
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_export_panel_syncs_external_changes_before_building_roles() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    openExportPanel: openExportPanel,
    prepareGlossary: prepareGlossary,
    renderExportOptions: renderExportOptions,
    semanticDigest: semanticDigest,
    stableStringify: stableStringify
  };
}());

function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
var source = {
  source_format: "markdown",
  media_type: "text/markdown",
  artifact_digest: "a".repeat(64),
  size: 4,
  rich_document_digest: "b".repeat(64)
};
var anchor = {
  kind: "block",
  target_id: "block-1",
  related_blocks: [{
    block_id: "block-1",
    kind: "paragraph",
    ordinal: 0,
    locator: {line_start: 1},
    content_fingerprint: "c".repeat(64)
  }]
};
helpers.state.payload = {
  source_identity: source,
  block_fingerprints: {"block-1": "c".repeat(64)},
  revisions: [],
  diagnostics: [],
  publication: {
    source_document: {
      blocks: [{
        block_id: "block-1",
        kind: "paragraph",
        ordinal: 0,
        locator: {line_start: 1},
        payload: {text: "source"}
      }]
    },
    outline: [],
    glossary: [{term: "Reader", translated_term: "读者", definition: "A reader"}],
    bibliography: [{evidence_id: "ref-1", title: "Reference"}],
    labels: {},
    reader_profile: {title: "Reader", target_language: "en"}
  }
};
helpers.state.embeddedRevisions = [];
helpers.state.activeFragmentIds = new Set();
helpers.state.readerShellReady = false;
helpers.state.initialSelectedDigests = new Map();

globalThis.print = function () {};
var contentOptions = [];
var scopeInput = {value: "changed", checked: true, disabled: false};
var otherScopeInput = {value: "all", checked: false, disabled: false};
var packageModeInput = {value: "package", checked: true, disabled: false};
var fileModeInput = {value: "file", checked: false, disabled: false};
var nodes = {
  "alc-export": {
    attrs: {},
    setAttribute: function (name, value) { this.attrs[name] = value; }
  },
  "alc-export-panel": {hidden: true},
  "alc-export-role-options": {
    replaceChildren: function () { contentOptions = []; },
    appendChild: function (child) { contentOptions.push(child); }
  },
  "alc-export-markdown-package": {disabled: false, hidden: false},
  "alc-export-markdown-label": {textContent: ""},
  "alc-export-html": {disabled: false, hidden: false},
  "alc-export-pdf": {disabled: false, hidden: false},
  "alc-storage-status": {textContent: "", dataset: {}, hidden: true}
};
globalThis.document = {
  getElementById: function (id) { return nodes[id]; },
  querySelector: function (selector) {
    if (selector.includes("alc-export-scope")) {
      return scopeInput.checked ? scopeInput : otherScopeInput;
    }
    if (selector.includes("alc-export-markdown-mode")) {
      return fileModeInput.checked ? fileModeInput : packageModeInput;
    }
    throw new Error("unexpected selector: " + selector);
  },
  querySelectorAll: function (selector) {
    if (selector.includes("alc-export-scope")) {
      return [scopeInput, otherScopeInput];
    }
    if (selector.includes("alc-export-markdown-mode")) {
      return [packageModeInput, fileModeInput];
    }
    throw new Error("unexpected selector: " + selector);
  },
  createElement: function (tag) {
    return {
      tagName: tag,
      children: [],
      textContent: "",
      disabled: false,
      addEventListener: function () {},
      appendChild: function (child) {
        this.children.push(child);
        if (child.textContent) this.textContent += child.textContent;
      }
    };
  }
};

(async function () {
  await helpers.prepareGlossary();
  var metadata = {
    schema_version: "alc.render.fragment_revision.v3",
    source: source,
    fragment_id: "external-note",
    revision: 1,
    parent_semantic_digest: null,
    anchor: anchor,
    priority: 110,
    role: "note",
    language: "en",
    title: "External note",
    citation_ids: [],
    appearance: null,
    deleted: false,
    provenance: {producer: "alc-render-browser"}
  };
  var markdown = "new external change";
  var digest = await helpers.semanticDigest(metadata, markdown);
  var encoded = "<!-- ALC:FRAGMENT-JSON:BEGIN -->\\n" +
    helpers.stableStringify(metadata) +
    "\\n<!-- ALC:FRAGMENT-JSON:END -->\\n" + markdown;
  var file = {
    kind: "file",
    name: "revision-000001-" + digest + ".md",
    getFile: function () {
      return Promise.resolve({
        size: encoded.length,
        lastModified: 1,
        text: function () { return Promise.resolve(encoded); }
      });
    }
  };
  var fragments = {
    values: async function* () { yield file; }
  };
  helpers.state.directory = {
    getDirectoryHandle: function (name) {
      if (name === "glossary") {
        return Promise.reject(Object.assign(new Error("missing"), {name: "NotFoundError"}));
      }
      assert(name === "fragments", "export sync requested the wrong directory");
      return Promise.resolve(fragments);
    }
  };
  helpers.state.exportStandaloneSupported = true;
  assert(contentOptions.length === 0, "fixture unexpectedly started with content options");
  await helpers.openExportPanel();
  assert(
    helpers.state.selected.get("external-note").semantic_digest === digest,
    "opening export did not synchronize the external latest revision"
  );
  assert(
    contentOptions.length === 4 &&
      contentOptions[0].textContent === "Source" &&
      contentOptions[1].textContent === "Note" &&
      contentOptions[2].textContent === "Glossary" &&
      contentOptions[3].textContent === "References",
    "export content options were not rendered after synchronization"
  );
  assert(
    contentOptions[0].children[0].checked &&
      contentOptions[0].children[0].disabled,
    "changed-only scope did not retain and disable the source selection"
  );
  assert(
    contentOptions[1].children[0].checked &&
      !contentOptions[1].children[0].disabled,
    "changed note was not selected and available"
  );
  assert(
    contentOptions[2].children[0].checked &&
      contentOptions[2].children[0].disabled &&
      contentOptions[3].children[0].checked &&
      contentOptions[3].children[0].disabled,
    "changed-only scope did not retain and disable appendix selections"
  );
  assert(
    nodes["alc-export"].attrs["aria-expanded"] === "true",
    "synchronized export panel did not remain open"
  );
  assert(
    !nodes["alc-export-html"].hidden && !nodes["alc-export-html"].disabled,
    "Markdown scope incorrectly changed the independent HTML action"
  );
  assert(
    !nodes["alc-export-pdf"].hidden && !nodes["alc-export-pdf"].disabled,
    "Markdown scope incorrectly changed the independent PDF action"
  );
  assert(
    !nodes["alc-export-markdown-package"].hidden &&
      !nodes["alc-export-markdown-package"].disabled,
    "changed-only Markdown package was not available for a checked change"
  );
  assert(
    nodes["alc-export-markdown-label"].textContent === "Export Markdown",
    "default package mode did not use the generic Markdown action label"
  );
  packageModeInput.checked = false;
  fileModeInput.checked = true;
  helpers.renderExportOptions();
  assert(
    nodes["alc-export-markdown-label"].textContent === "Export Markdown",
    "single-file mode changed the generic Markdown action label"
  );
  scopeInput.checked = false;
  otherScopeInput.checked = true;
  helpers.renderExportOptions();
  assert(
    !nodes["alc-export-html"].hidden && !nodes["alc-export-html"].disabled,
    "all-latest scope did not restore the full HTML action"
  );
  assert(
    !nodes["alc-export-markdown-package"].hidden &&
      !nodes["alc-export-markdown-package"].disabled,
    "all-latest scope did not restore the complete package action"
  );
  assert(
    contentOptions[0].children[0].checked &&
      !contentOptions[0].children[0].disabled,
    "all-latest scope did not restore the retained source selection"
  );
  assert(
    !contentOptions[2].children[0].disabled &&
      !contentOptions[3].children[0].disabled,
    "all-latest scope did not restore appendix selections"
  );
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )

    completed = subprocess.run(
        [node, "-"],
        input=instrumented,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_reader_rebuilds_directory_state_and_guards_revision_lineage() -> None:
    javascript = _text("reader.js")

    assert (
        "state.embeddedRevisions = (state.payload.revisions || []).slice()"
        in javascript
    )
    assert "state.embeddedRevisions.forEach(addRevision)" in javascript
    assert "state.activeFragmentIds.has(fragmentId)" in javascript
    assert "browserCreatedHistory(values)" in javascript
    assert "var revisions = new Map();" in javascript
    assert "var DIRECTORY_READ_CONCURRENCY = 8;" in javascript
    assert "Math.min(DIRECTORY_READ_CONCURRENCY, files.length)" in javascript
    assert "commitDirectorySnapshot(" in javascript
    assert "await loadDirectoryRevisions(handle)" in javascript
    assert "current.semantic_digest !== base.semantic_digest" in javascript
    assert "nextChildren.length > 0" in javascript
    assert "!state.activeDraft && !state.activeGlossaryDraft" in javascript
    assert "throw new Error(labels().historyChanged)" in javascript
    assert "var folder = await fragmentsDirectory(true);" in javascript
    assert "async function fragmentsDirectory(create)" in javascript
    assert "getDirectoryHandle(fragmentId" not in javascript
    assert "fragmentDirectory(metadata.fragment_id" not in javascript
    assert "Array.isArray(state.payload.glossary_revisions)" not in javascript
    glossary_save = javascript[
        javascript.index("async function persistGlossaryEditor") :
        javascript.index("function deleteEditor")
    ]
    assert glossary_save.index("loadAllPayload(false);") < glossary_save.index(
        "prepareGlossaryPropagation(draft, entry, editedAt)"
    )
    assert glossary_save.index(
        "var previousSelected = new Map(state.selected);"
    ) < glossary_save.index(
        "refreshChangedSelections(previousSelected);"
    ) < glossary_save.index(
        "refreshGlossarySurfaces(previousGlossary);"
    )
    directory_loader = javascript[
        javascript.index("async function loadDirectoryRevisions") :
        javascript.index("function commitDirectorySnapshot")
    ]
    assert directory_loader.index("loadAllPayload(false);") < directory_loader.index(
        "var revisions = new Map();"
    )
    assert directory_loader.count("state.embeddedRevisions.forEach") == 1


def test_reader_enforces_strict_browser_revision_contract() -> None:
    javascript = _text("reader.js")

    assert "validateCurrentSourceIdentity();" in javascript
    assert "validateSourceIdentity(state.payload.source_identity)" in javascript
    assert "state.sourceIndexes = {" in javascript
    assert "var blocks = indexes.blocksById;" in javascript
    assert "validateAnchor(metadata.anchor)" in javascript
    assert "validateIntegerJson(metadata, \"fragment revision\")" in javascript
    assert "Number.isSafeInteger(value)" in javascript
    assert "anchor related block differs from the rich source" in javascript
    assert "assertKnownCitations(revisionEditable.citation_ids)" in javascript


def test_reader_uses_low_distraction_controls_and_inline_editor() -> None:
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")

    for reader_facing_term in (
        "添加外挂",
        "编辑外挂",
        "新建外挂",
        "另存为新版本",
        "Add overlay",
        "Edit overlay",
        "New overlay",
        "Save as new revision",
    ):
        assert reader_facing_term not in javascript
    assert '"alc-editor-cancel").textContent = strings.cancel' in javascript
    assert '"alc-editor-save").textContent = strings.save' in javascript
    assert "await restoreDirectoryHandle();" in javascript
    assert "await setupEditor();" in javascript
    assert "alc-history-compare" in javascript
    assert "historyRevisionLabel" in javascript
    assert "restoreHistoricalRevision" in javascript
    assert (
        '"alc-note-button alc-icon-button", "+", labels().addNote'
        in javascript
    )
    assert "alc-edit-button" not in javascript
    assert "beginInlineEdit" in javascript
    assert "openAdvancedEditor" in javascript
    assert "renderGlossaryRow" in javascript
    assert "alc-glossary-inline-input" in javascript
    assert "alc-glossary-inline-definition" in javascript
    assert "focusGlossaryInlineEditor" in javascript
    assert "renderGlossaryDefinition" in javascript
    assert "markdownPlainText(entry.definition" in javascript
    assert "renderGlossaryCardActions" in javascript
    assert "playGlossarySpeech" in javascript
    assert "alc-glossary-card-actions" in stylesheet
    assert "alc-glossary-inline-column-header" in stylesheet
    assert ".alc-glossary-edit" not in stylesheet
    assert "alc-fragment-actions alc-inline-actions" in javascript
    assert 'glossaryTerm: traditional ? "術語" : "术语"' in javascript
    assert "GLOSSARY_DISPLAY_WEIGHT" not in javascript
    assert "strings.glossaryTerm + \" · v\"" in javascript
    assert 'glossarySourceReadOnly: "原文（不可修改）"' in javascript
    assert "预览与更多设置" not in javascript
    assert "Preview and more settings" not in javascript
    assert '"你已修改当前内容，是否保存？"' in javascript
    assert 'saveBeforeExit: "You changed the current content. Save it?"' in javascript
    assert "可以保存修改并退出" not in javascript
    assert "Save the changes before leaving this editor" not in javascript
    assert 'dialog.dataset.editorKind = glossaryMode ? "glossary" : "fragment"' in javascript
    assert 'control.setAttribute("aria-label", labelText)' in javascript
    assert "alc-glossary-inline-label" not in javascript
    assert "alc-glossary-inline-label" not in stylesheet
    assert "alc-glossary-inline-column" in javascript
    assert "background: var(--alc-translation-bg);" in stylesheet
    assert "alc-glossary-inline-source-value" in stylesheet
    assert "alc-glossary-inline-mobile-actions" in javascript
    assert "alc-glossary-inline-desktop-actions" in javascript
    assert 'event.target.closest(".alc-glossary-translation")' in javascript
    assert 'focusField === "translation" ?' in javascript
    assert (
        '"textarea", "alc-inline-markdown alc-glossary-inline-definition"'
        in javascript
    )
    assert "height: 8rem;" in stylesheet
    assert "max-height: 8rem;" in stylesheet
    assert "#alc-editor-glossary-source" in stylesheet
    assert "background: #e7eaed;" in stylesheet
    assert "cursor: not-allowed;" in stylesheet
    assert "align-items: center;" in stylesheet
    assert (
        ".alc-inline-actions.alc-glossary-inline-mobile-actions { display: none; }"
        in stylesheet
    )
    assert "grid-template-rows: auto auto;" in stylesheet
    assert "height: auto;" in stylesheet
    assert ".alc-glossary-inline-input:focus-visible" not in stylesheet
    assert ".alc-glossary-inline-definition:focus-visible" not in stylesheet
    assert ".alc-dialog-form::-webkit-scrollbar { width: 6px; }" in stylesheet
    assert "scrollbar-color: transparent transparent;" in stylesheet
    assert "rgb(79 120 150 / 55%)" in stylesheet
    assert ".alc-dialog-form:focus-within::-webkit-scrollbar-thumb" in stylesheet
    assert ".alc-glossary-row.is-inline-editing" in stylesheet
    assert ".alc-glossary-inline-input" in stylesheet
    assert ".alc-glossary-inline-definition" in stylesheet
    assert "html { scroll-behavior: auto; }" in stylesheet
    assert "html { scroll-behavior: smooth; }" not in stylesheet
    assert ".alc-storage-status" in stylesheet
    assert "left: 50%;" in stylesheet
    assert "transform: translateX(-50%);" in stylesheet
    assert ".alc-editor-error" in stylesheet
    assert '.alc-dialog-fields input[aria-invalid="true"]' in stylesheet
    assert 'showGlossaryValidationError(labels().glossaryTranslatedRequired)' in javascript
    assert "!activeGlossaryDraftValid()" not in javascript[
        javascript.index("function updateDraftSaveButtons") :
        javascript.index("function assertEditorBaseCurrent")
    ]
    assert "openNewSectionEditor" not in javascript
    assert ".alc-history-compare" in stylesheet
    assert ".alc-section-note-button" not in stylesheet
    assert ".alc-icon-button" in stylesheet
    assert "function labelToolButton(button, label)" in javascript
    assert "trigger.textContent = strings.view" not in javascript
    assert "trigger.textContent = strings.listen" not in javascript
    assert "trigger.textContent = strings.export" not in javascript
    assert ".alc-tool-icon-button" in stylesheet
    assert ".alc-tool-icon" in stylesheet
    assert "scrollbar-color: transparent transparent;" in stylesheet
    assert ".alc-contents nav::-webkit-scrollbar { width: 6px; }" in stylesheet
    assert ".alc-contents nav:hover::-webkit-scrollbar-thumb" in stylesheet
    assert "background: rgb(79 120 150 / 55%);" in stylesheet
    assert "position: fixed" in stylesheet
    assert "width: min(29rem, calc(100vw - 2rem))" in stylesheet
    assert "height: min(39.5rem, calc(100dvh - 2rem))" in stylesheet
    assert '.alc-dialog[data-editor-kind="glossary"] { height: fit-content; }' in stylesheet
    assert '.alc-dialog[data-editor-kind="glossary"] .alc-dialog-form' in stylesheet
    assert "newSaveLocation" in javascript
    assert "changeSaveLocation" in javascript
    assert "buildStandaloneExportHtml" in javascript
    assert "collectMarkdownFiles" in javascript
    initialize = javascript[javascript.index("async function initialize()"):]
    assert "captureExportTemplate();" not in initialize
    assert "root.outerHTML" in javascript
    assert "readingArea.replaceChildren();" in javascript
    assert "header.replaceChildren();" in javascript
    assert "contents.replaceChildren();" in javascript
    assert '--alc-translation-bg: #eaf1f8;' in stylesheet
    assert '--alc-note-fg: #f9fafb;' in stylesheet
    assert '--alc-note-bg: #111827;' in stylesheet
    assert 'var COLOR_PRESETS = [' in javascript
    assert "setupReaderSettings();" in javascript
    assert "readerPreferenceSnapshot" in javascript
    assert 'body.dataset.alcReaderLayout = next.layout' in javascript
    assert '"--alc-source-font"' in javascript
    assert '"--alc-target-font"' in javascript
    assert '"--alc-font-scale"' in javascript
    assert '"--alc-reader-line-height"' in javascript
    assert '"--alc-reader-supplement-line-height"' in javascript
    assert '"--alc-reader-block-padding"' in javascript
    assert '"--alc-reader-source-block-padding"' in javascript
    assert '"--alc-reader-supplement-block-padding"' in javascript
    assert '"--alc-reader-block-gap"' in javascript
    assert '(1.55 * next.lineHeight / 1.65).toFixed(3)' in javascript
    assert (
        'Math.max(0, 0.8 * (next.blockSpacing - 100) / 100).toFixed(3)'
        in javascript
    )
    assert '"--alc-reader-width"' in javascript
    assert 'blockSpacing: 100' in javascript
    assert 'data.alcReaderBlockSpacing' in javascript
    assert 'readerLineHeight: traditional ? "行間距" : "行间距"' in javascript
    assert 'readerBlockSpacing: traditional ? "段間距" : "段间距"' in javascript
    assert 'traditional ? "同類型與優先級的樣式" : "同类型与优先级的样式"' in javascript
    assert 'traditional ? "字體顏色" : "字体颜色"' in javascript
    assert 'traditional ? "背景顏色" : "背景颜色"' in javascript
    assert '"alc-settings-block-spacing": String(preferences.blockSpacing)' in javascript
    assert '--alc-reader-block-padding: .4rem;' in stylesheet
    assert '--alc-reader-source-block-padding: .3rem;' in stylesheet
    assert '--alc-reader-supplement-block-padding: .45rem;' in stylesheet
    assert '--alc-reader-block-gap: 0rem;' in stylesheet
    assert 'padding: var(--alc-reader-block-padding) .65rem;' in stylesheet
    assert ".alc-dialog .alc-settings-close {" in stylesheet
    assert ".alc-dialog .alc-settings-close:hover {" in stylesheet
    assert ".alc-dialog .alc-settings-close svg {" in stylesheet
    assert (
        ".alc-editor-grid {\n"
        "  display: grid;\n"
        "  grid-template-columns: minmax(0, 1fr);\n"
        "  min-height: 11rem;"
    ) in stylesheet
    assert (
        ".alc-editor-pane textarea {\n"
        "  min-height: 11rem;\n"
        "  height: 11rem;"
    ) in stylesheet
    assert ".alc-editor-grid { min-height: 9rem; }" in stylesheet
    assert "min-height: min(11rem, 24dvh);" in stylesheet
    assert "height: min(11rem, 24dvh);" in stylesheet
    assert "min(22rem, 48dvh)" not in stylesheet
    assert (
        'padding: var(--alc-reader-source-block-padding) .15rem;'
        in stylesheet
    )
    assert 'margin-top: var(--alc-reader-block-gap);' in stylesheet
    assert 'row-gap: var(--alc-reader-block-gap);' in stylesheet
    assert (
        'line-height: var(--alc-reader-supplement-line-height);'
        in stylesheet
    )
    assert (
        'padding: var(--alc-reader-supplement-block-padding) .65rem;'
        in stylesheet
    )
    assert '".alc-select-listbox, .alc-custom-select"' in javascript
    assert 'wrapper.closest("dialog[open]") || document.body' in javascript
    assert (
        '".alc-settings-field, .alc-speech-field, .alc-dialog-fields label"'
        in javascript
    )
    assert "installCustomSelect(role);" in javascript
    assert javascript.count("syncCustomSelect(role);") == 2
    assert 'wrapper.dataset.compact = "true";' in javascript
    assert '".alc-settings-panel, .alc-speech-dock"' in javascript
    assert "localStorage" not in javascript
    assert "contain: inline-size;" in stylesheet
    assert ".alc-speech-player-title {\n  display: block;" in stylesheet
    assert (
        ".alc-speech-player-transport {\n"
        "  display: flex;\n"
        "  gap: .12rem;\n"
        "  align-items: center;\n"
        "  justify-content: center;"
    ) in stylesheet
    assert ".alc-speech-player-progress {\n  min-height: 1.3em;" in stylesheet
    assert ".alc-speech-status {\n  position: absolute;" in stylesheet
    assert "#alc-speech-panel-player {\n  margin-top: .35rem;" in stylesheet
    assert ".alc-tool-panel-header {" in stylesheet
    assert ".alc-settings-panel {\n  position: absolute;" in stylesheet
    assert stylesheet.count("width: min(22rem, calc(100vw - 1rem));") == 2
    assert "@media (max-width: 30rem)" not in stylesheet
    assert "width: min(25rem, calc(100vw - .5rem));" not in stylesheet
    assert "function positionToolPanel(panel)" in javascript
    assert "document.documentElement.clientWidth || window.innerWidth" in javascript
    assert 'panel.style.maxWidth = Math.max(0, viewportWidth - 16) + "px";' in javascript
    assert 'rectangle.right - (viewportWidth - 8)' in javascript
    assert 'panel.style.transform = "translateX(-" + overflow + "px)";' in javascript
    assert javascript.count(
        'window.addEventListener("resize", function () { positionToolPanel(panel); });'
    ) == 4
    assert ".alc-export-format-section .alc-export-action { justify-self: end; }" in stylesheet
    assert ".alc-export-format-section .alc-export-action { align-self: end; }" in stylesheet
    assert (
        ".alc-export-panel .alc-export-action {\n"
        "  position: relative;\n"
        "  display: inline-flex;"
    ) in stylesheet
    assert "min-height: 2.25rem;\n  padding: .3rem .5rem;" in stylesheet
    assert ".alc-export-panel .alc-export-action::before {" in stylesheet
    assert "inset: -.25rem 0;" in stylesheet
    assert "html:lang(zh) .alc-view-options" in stylesheet
    assert "html:lang(zh) .alc-speech-role-options" in stylesheet
    assert 'automaticVoiceSelection: "Automatic (default: {voice})"' in javascript
    assert "function speechVoiceDescription(voice)" in javascript
    assert (
        'loopNone: \'<path d="M3 7h15"></path>'
        '<path d="m14 3 4 4-4 4"></path>\' +'
        in javascript
    )
    assert '<path d="m4 4 16 16"></path>' not in javascript
    assert "function positionSpeechRateMenu(player)" in javascript
    assert 'menu.style.width = triggerRect.width + "px";' in javascript
    assert "spaceAbove >= menuRect.height + spacing" in javascript
    assert 'player.dataset.playerKind === "dock"' in javascript
    assert 'menu.style.maxHeight = docked ? "none"' in javascript
    assert 'menu.style.bottom = "auto";' in javascript
    assert ".alc-speech-dock .alc-speech-rate-menu" in stylesheet
    assert 'rate-menu[data-layout="grid"]' in stylesheet
    assert ".alc-speech-dock .alc-speech-player-transport { gap: .25rem; }" in stylesheet
    assert ".alc-speech-panel {\n  overflow-x: hidden;\n  overflow-y: auto;" in stylesheet
    assert (
        ".alc-speech-panel .alc-speech-player-transport {\n"
        "    flex-wrap: nowrap;\n"
        "    gap: .08rem;\n"
        "    justify-content: center;"
    ) in stylesheet
    assert (
        '.alc-speech-panel .alc-speech-player-button[data-speech-action="play"] {'
        "\n    width: 2.15rem;"
    ) in stylesheet
    assert ".alc-speech-dock .alc-speech-player-button,\n" in stylesheet
    assert ".alc-speech-dock .alc-speech-rate-option {\n  min-height: 2rem" in stylesheet
    assert ".alc-speech-panel .alc-speech-rate-option { min-height: 44px" not in stylesheet
    assert '@media (max-width: 26.25rem)' in stylesheet
    assert 'data-speech-action="loop"] {\n    display: none !important;' in stylesheet
    assert '@media (max-width: 23.75rem)' in stylesheet
    assert 'data-speech-action="stop"] {\n    display: none !important;' in stylesheet
    assert '@media (max-width: 21.25rem)' in stylesheet
    assert 'data-speech-action="beginning"] {\n    display: none !important;' in stylesheet
    assert "min-height: 2.25rem !important;" in stylesheet
    assert 'button[data-speech-action="close"]::before' in stylesheet
    assert "right: .85rem;" in stylesheet
    assert "text-overflow: ellipsis;" in stylesheet
    assert "border-left: 2px solid #d0a747;" in stylesheet
    assert ".alc-card-actions {" in stylesheet
    assert "opacity: 0;\n  pointer-events: none;" in stylesheet
    assert "opacity: .85;\n  pointer-events: auto;" in stylesheet
    assert "setupTouchCardActions(source);" in javascript
    assert "setupTouchCardActions(card);" in javascript
    assert ".is-touch-actions-revealed > .alc-card-actions" in stylesheet
    assert "width: 44px;\n    min-width: 44px;" in stylesheet
    touch_actions = stylesheet[
        stylesheet.index(
            ".is-touch-actions-revealed > .alc-card-actions { gap: 0; }"
        ) : stylesheet.index(".alc-source-card {", stylesheet.index(
            ".is-touch-actions-revealed > .alc-card-actions { gap: 0; }"
        ))
    ]
    assert "@media" not in touch_actions
    assert "gap: .75rem;" not in stylesheet
    assert "gap: .08rem;" in stylesheet
    assert "right: 2.35rem;" not in stylesheet
    assert 'last-child:is([data-role="companion"], [data-role="guide"])' in stylesheet
    assert ") > .alc-note-button {\n  bottom: .4rem;" in stylesheet
    assert "bottom: -.3rem;" not in stylesheet
    assert "@media (max-width: 899px), (hover: none), (pointer: coarse)" not in stylesheet
    assert ".alc-note-button {\n    width: 2rem;" not in stylesheet
    assert "inset: -.375rem;" in stylesheet
    assert ".alc-lanes:not(.has-parallel-translation) > .alc-source-card" in stylesheet
    assert ".alc-book-header > h1.is-speaking" in stylesheet
    assert "width: 44px;\n    min-width: 44px;" in stylesheet
    assert "height: 2.2rem;\n    min-height: 2.2rem;" in stylesheet
    assert "margin-left: auto;" in stylesheet
    assert "> .alc-translated-title.is-inline-editing" in stylesheet
    assert "padding: 3.2rem 0 .65rem;" in stylesheet
    assert ".alc-promoted-title-row > .alc-lanes {\n  padding-top: 1.5rem;" in stylesheet
    assert ".alc-promoted-title-row > .alc-lanes > .alc-source-card { display: none; }" in stylesheet
    assert "width: min(33.5rem, calc(100% - 2rem));" in stylesheet
    assert "grid-template-columns: minmax(10rem, 1fr) max-content;" in stylesheet
    assert 'speaker: \'<path d="M11 5 6 9H2v6h4l5 4V5Z"></path>\'' in javascript
    assert 'M4 10h4l4-3v10l-4-3H4Z' not in javascript
    assert 'd="m18 5-10 7 10 7Z"' in javascript
    assert 'speechRate: "倍速"' in javascript
    assert 'width="12" height="12"' in javascript
    assert 'd="M3 11V9a3 3 0 0 1 3-3h14"' in javascript
    assert 'd="M21 13v2a3 3 0 0 1-3 3H4"' in javascript
    assert 'd="M11 10.5 13 9v6"' in javascript
    assert 'select.tabIndex = -1;' in javascript
    assert 'select.setAttribute("aria-hidden", "true")' in javascript
    assert 'document.addEventListener("click", attemptInlineDraftExit, true)' in javascript
    assert 'window.addEventListener("beforeunload", guardUnsavedDraftBeforeUnload)' in javascript
    assert "min-height: 2.25rem;\n  padding: .35rem .7rem;" in stylesheet
    assert ".alc-unsaved-dialog button[data-initial-focus]:focus-visible" in stylesheet
    assert "#alc-editor-glossary-source" in stylesheet
    assert "cursor: text" in stylesheet
    math_display = stylesheet[
        stylesheet.index(".math-display {") :
        stylesheet.index(".alc-equation-row {")
    ]
    assert "overflow-x: auto" in math_display
    assert "scrollbar-color: transparent transparent" in math_display
    assert "scrollbar-width: thin" in math_display
    assert ".math-display::-webkit-scrollbar { height: 6px; }" in math_display
    assert ".math-display:hover" in math_display
    assert ".math-display:hover::-webkit-scrollbar-thumb" in math_display
    assert "root._alcSpeechQueue === queue" in javascript
    assert "var items = document.createDocumentFragment();" in javascript
    assert "width: 1.1rem;\n  height: 1.1rem;" in stylesheet
    assert "stroke-width: 2;" in stylesheet
    assert 'pattern="#[0-9A-Fa-f]{6}"' not in javascript
    assert (
        ".alc-source-card {\n"
        "  padding: var(--alc-reader-source-block-padding) .15rem;\n"
        "  background: transparent;\n"
        "}"
    ) in stylesheet


def test_touch_card_actions_reveal_before_content_activation_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcReaderTest = {
    setupTouchCardActions: setupTouchCardActions
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
function fakeCard() {
  var classes = new Set();
  var listeners = {};
  return {
    dataset: {},
    listeners: listeners,
    classList: {
      add: function (name) { classes.add(name); },
      remove: function (name) { classes.delete(name); },
      contains: function (name) { return classes.has(name); }
    },
    addEventListener: function (name, handler, capture) {
      listeners[name] = {handler: handler, capture: Boolean(capture)};
    }
  };
}
globalThis.document = {querySelectorAll: function () { return []; }};
var card = fakeCard();
var content = {closest: function () { return null; }};
globalThis.__alcReaderTest.setupTouchCardActions(card);
card.listeners.pointerdown.handler({pointerType: "touch", target: content});
assert(
  card.classList.contains("is-touch-actions-revealed"),
  "first touch did not reveal card actions"
);
assert(
  card.dataset.alcSuppressTouchClick === "true",
  "first touch did not suppress content activation"
);
var prevented = false;
var stopped = false;
var immediate = false;
assert(card.listeners.click.capture, "touch click suppression is not capture-phase");
card.listeners.click.handler({
  preventDefault: function () { prevented = true; },
  stopPropagation: function () { stopped = true; },
  stopImmediatePropagation: function () { immediate = true; }
});
assert(prevented && stopped && immediate, "first touch click was not suppressed");
assert(
  card.dataset.alcSuppressTouchClick === undefined,
  "touch click suppression survived its one intended click"
);
card.listeners.pointerdown.handler({pointerType: "touch", target: content});
assert(
  card.dataset.alcSuppressTouchClick === undefined,
  "second touch was incorrectly suppressed after actions became visible"
);
'''
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_visibility_is_dynamic_ephemeral_and_book_focused() -> None:
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")

    assert "function setupVisibility()" in javascript
    assert "state.payload.selected_roles || []" in javascript
    assert "Array.from(state.selected.values())" in javascript
    assert "state.hiddenRoles =" not in javascript
    assert "localStorage" not in javascript
    assert 'visibilityOption("source", labels().original' in javascript
    assert "roleLabel(role)" in javascript
    assert "function updateVisibilityStyles(channels)" in javascript
    assert "data-role-slot" in javascript
    apply_visibility = javascript[javascript.index("function applyVisibility") :]
    apply_visibility = apply_visibility[: apply_visibility.index("function updateVisibilityStyles")]
    assert "querySelectorAll" not in apply_visibility
    assert "getBoundingClientRect" not in apply_visibility
    assert "loadAllPayload(false);" not in javascript[
        javascript.index("function setupVisibility()") :
        javascript.index("function setupSpeech()")
    ]
    assert ".alc-focused-reading .alc-book-header" in stylesheet
    assert "72ch" in stylesheet
    assert "margin-block: .2em" in stylesheet
    assert ".alc-visibility-empty" in stylesheet


def test_reader_equation_rows_and_css_lanes_are_bounded() -> None:
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")

    assert 'element("div", "alc-equation-row")' in javascript
    assert "decorateOverlayEquation(rendered, fragment)" in javascript
    assert "fragmentTex !== sourceTex" in javascript
    assert "effectiveEquationLabel(block, block.payload || {})" in javascript
    assert "grid-template-columns: minmax(0, 1fr) max-content" in stylesheet
    assert "white-space: nowrap" in stylesheet
    assert "function setupLaneResponsiveness" not in javascript
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in stylesheet
    assert (
        ".alc-lanes {\n"
        "    grid-template-columns: minmax(0, 1fr);\n"
        "    row-gap: calc(.4rem + var(--alc-reader-block-gap));\n"
        "    column-gap: .4rem;\n"
        "  }"
    ) in stylesheet


def test_matching_overlay_equation_inherits_effective_label_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcReaderTest = {
    state: state,
    decorateOverlayEquation: decorateOverlayEquation
  };
}());
function FakeNode(tag, className) {
  this.tagName = tag;
  this.className = className || "";
  this.children = [];
  this.dataset = {};
  this.parentElement = null;
  this.textContent = "";
  this.classList = {
    owner: this,
    contains: function (name) {
      return this.owner.className.split(/\s+/).includes(name);
    }
  };
}
FakeNode.prototype.appendChild = function (child) {
  child.parentElement = this;
  this.children.push(child);
  return child;
};
FakeNode.prototype.replaceWith = function (replacement) {
  var index = this.parentElement.children.indexOf(this);
  this.parentElement.children[index] = replacement;
  replacement.parentElement = this.parentElement;
  this.parentElement = null;
};
Object.defineProperty(FakeNode.prototype, "firstElementChild", {
  get: function () { return this.children[0] || null; }
});
globalThis.document = {
  createElement: function (tag) { return new FakeNode(tag); }
};
var helpers = globalThis.__alcReaderTest;
var block = {
  block_id: "eq-1",
  kind: "equation",
  payload: {tex: "x = y", label: "(2)"}
};
helpers.state.payload = {
  resources: [],
  publication: {
    source_document: {
      blocks: [block],
      metadata: {
        equation_label_reconciliation: {
          "eq-1": {effective_label: "(7)"}
        }
      }
    },
    outline: []
  }
};
helpers.state.indexedPayload = helpers.state.payload;
helpers.state.sourceIndexes = {
  blocksById: new Map([["eq-1", block]]),
  resourceCount: 0
};
function renderedEquation(tex) {
  var rendered = new FakeNode("div", "alc-markdown");
  var math = new FakeNode("div", "math math-display");
  math.dataset.tex = tex;
  rendered.appendChild(math);
  return rendered;
}
var fragment = {anchor: {kind: "block", target_id: "eq-1"}};
var matching = renderedEquation("\n x = y \n");
helpers.decorateOverlayEquation(matching, fragment);
if (matching.children[0].className !== "alc-equation-row") {
  throw new Error("matching translated equation did not receive a row");
}
if (
  matching.children[0].children[1].className !== "alc-equation-label" ||
  matching.children[0].children[1].textContent !== "(7)"
) {
  throw new Error("matching translated equation missed its effective label");
}
var changed = renderedEquation("x = z");
helpers.decorateOverlayEquation(changed, fragment);
if (!changed.children[0].classList.contains("math-display")) {
  throw new Error("changed overlay equation inherited a source number");
}
'''
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_progressively_hydrates_navigation_find_and_print_content() -> None:
    javascript = _text("reader.js")
    stylesheet = _text("reader.css")

    assert "MAX_BLOCKS_PER_RENDER_CHUNK = 36" in javascript
    assert "buildRenderChunks(" in javascript
    assert "new IntersectionObserver" in javascript
    assert "window.requestIdleCallback(work)" in javascript
    assert "}, 2000);" in javascript
    assert "deadline.timeRemaining() < 12" in javascript
    assert "window.setTimeout(work, 250)" in javascript
    assert '"wheel", "touchstart", "keydown", "pointerdown"' in javascript
    assert "armHashCalibration(window.location.hash);" in javascript
    assert "recalibrateHashTarget();" in javascript
    assert 'window.addEventListener("beforeprint", renderAllChunks)' in javascript
    assert 'runExport({kind: "pdf"})' in javascript
    assert "renderAllChunks();\n        closeExportPanel(false);\n        window.print();" in javascript
    assert "min-height: 2.75rem;" in stylesheet
    assert "width: 8.5rem;" in stylesheet
    assert "html:lang(zh) .alc-export-panel .alc-export-action { width: 8rem; }" in stylesheet
    assert ".alc-export-action-primary" not in stylesheet
    assert "activateHashTarget(href, true)" in javascript
    assert (
        'if (targetId === "alc-book-header") {'
        in javascript
    )
    title_branch = javascript[javascript.index('if (targetId === "alc-book-header") {'):]
    title_branch = title_branch[:title_branch.index("return true;")]
    assert "scrollToHashTarget(targetId);" in title_branch
    assert "scrollToReaderTop();" not in title_branch
    assert "refreshChangedSelections(previousSelected);" in javascript
    assert "refreshChunkForAnchor(revision.anchor);" in javascript
    assert 'document.body.dataset.alcRenderComplete = String(complete)' in javascript
    assert "state.bibliographyIndexCache" in javascript
    assert "state.glossarySurfaceCache[layer]" in javascript
    assert javascript.count("renderReader();") == 1
    assert ".alc-render-chunk:not(.is-rendered)" in stylesheet
    assert "content-visibility: auto" in stylesheet
    assert "content-visibility: visible !important" in stylesheet


def test_reader_lazily_loads_v2_payload_and_exports_v1_snapshot() -> None:
    javascript = _text("reader.js")

    assert '"alc.render.reader_payload.v2"' in javascript
    assert (
        "loadPayloadForBlockRange(chunk.block_start, chunk.block_end)"
        in javascript
    )
    assert "state.payloadChunks.forEach(loadPayloadChunk)" in javascript
    assert "(state.payload.resources || []).forEach(hydrateResource)" in javascript
    run_export = javascript[
        javascript.index("async function runExport") :
        javascript.index("function orderedExportCategories")
    ]
    assert 'loadAllPayload(request.kind !== "markdown-package");' in run_export
    portable_resources = javascript[
        javascript.index("function portableMarkdownResources") :
        javascript.index("function portableResourceBasename")
    ]
    assert "hydrateResource(value.resource)" in portable_resources
    assert 'payload.schema_version = "alc.render.reader_payload.v1"' in javascript
    assert ".alc-render-reader-chunk, .alc-render-reader-resource" in javascript


def test_markdown_export_hydrates_only_included_v2_resources_under_node() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + r'''
  globalThis.__alcReaderTest = {
    state: state,
    loadAllPayload: loadAllPayload,
    portableMarkdownResources: portableMarkdownResources
  };
}());
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
var helpers = globalThis.__alcReaderTest;
var keepDigest = "a".repeat(64);
var skipDigest = "b".repeat(64);
var accesses = [];
var payloads = {
  "keep-payload": {
    schema_version: "alc.render.reader_resource.v1",
    resource: {
      artifact_digest: keepDigest,
      media_type: "image/png",
      logical_name: "keep.png",
      size: 1,
      data_uri: "data:image/png;base64,AA=="
    }
  },
  "skip-payload": {
    schema_version: "alc.render.reader_resource.v1",
    resource: {
      artifact_digest: skipDigest,
      media_type: "image/png",
      logical_name: "skip.png",
      size: 1,
      data_uri: "data:image/png;base64,AQ=="
    }
  }
};
globalThis.document = {
  getElementById: function (id) {
    accesses.push(id);
    return {textContent: JSON.stringify(payloads[id])};
  }
};
helpers.state.payloadVersion = "v2";
helpers.state.payloadChunks = [];
helpers.state.payload = {
  resources: [
    {
      artifact_digest: keepDigest,
      media_type: "image/png",
      logical_name: "keep.png",
      size: 1,
      payload_id: "keep-payload"
    },
    {
      artifact_digest: skipDigest,
      media_type: "image/png",
      logical_name: "skip.png",
      size: 1,
      payload_id: "skip-payload"
    }
  ]
};
helpers.loadAllPayload(false);
assert(accesses.length === 0, "plain Markdown eagerly hydrated resources");
var included = new Set(["resources/" + keepDigest + "/keep.png"]);
var result = helpers.portableMarkdownResources(
  helpers.state.payload.resources, included
);
assert(
  accesses.join(",") === "keep-payload",
  "package export hydrated an unselected resource"
);
assert(
  result.manifest.length === 1 && result.manifest[0].logical_name === "keep.png",
  "selected resource was not packaged"
);
'''
    )

    subprocess.run(
        [node, "-"],
        input=instrumented,
        check=True,
        capture_output=True,
        text=True,
    )


def test_reader_hydrates_external_revision_anchor_before_validation() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    parser = javascript[
        javascript.index("async function parseRevisionFile") :
        javascript.index("async function semanticDigest")
    ]
    assert parser.index("loadPayloadForRevisionMetadata(metadata);") < parser.index(
        "validateRevisionMetadata(metadata);"
    )
    directory_loader = javascript[
        javascript.index("async function loadDirectoryRevisions") :
        javascript.index("function commitDirectorySnapshot")
    ]
    outcomes = directory_loader.index("var outcomes =")
    embedded = directory_loader.index(
        "state.embeddedRevisions.forEach(function (revision)"
    )
    assert 0 <= embedded < outcomes
    assert directory_loader.count(
        "state.embeddedRevisions.forEach(function (revision)"
    ) == 1
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        "globalThis.crypto = require('node:crypto').webcrypto;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    parseRevisionFile: parseRevisionFile,
    semanticDigest: semanticDigest,
    stableStringify: stableStringify
  };
}());
(async function () {
  var helpers = globalThis.__alcReaderTest;
  var fingerprint = "a".repeat(64);
  var source = {
    artifact_digest: "1".repeat(64),
    media_type: "text/html",
    rich_document_digest: "2".repeat(64),
    size: 10,
    source_format: "html"
  };
  var locator = {
    column_end: 1,
    column_start: 1,
    line_end: 8,
    line_start: 8,
    selector: "#target",
    source_format: "html",
    source_id: "target"
  };
  var manifests = [
    {block_id: "block-unrelated", kind: "paragraph", ordinal: 0},
    {block_id: "block-target", kind: "paragraph", ordinal: 1}
  ];
  var descriptors = [{
    chunk_id: "chunk-unrelated",
    block_start: 0,
    block_end: 1,
    payload_id: "payload-unrelated"
  }, {
    chunk_id: "chunk-target",
    block_start: 1,
    block_end: 2,
    payload_id: "payload-target"
  }];
  var chunks = {
    "payload-unrelated": {
      schema_version: "alc.render.reader_chunk.v1",
      chunk_id: "chunk-unrelated",
      block_start: 0,
      block_end: 1,
      blocks: [{
        block_id: "block-unrelated", kind: "paragraph", ordinal: 0,
        locator: Object.assign({}, locator, {selector: "#unrelated"}),
        payload: {text: "unrelated"}
      }],
      block_fingerprints: {"block-unrelated": "c".repeat(64)},
      revisions: []
    },
    "payload-target": {
      schema_version: "alc.render.reader_chunk.v1",
      chunk_id: "chunk-target",
      block_start: 1,
      block_end: 2,
      blocks: [{
        block_id: "block-target", kind: "paragraph", ordinal: 1,
        locator: locator, payload: {text: "target"}
      }],
      block_fingerprints: {"block-target": fingerprint},
      revisions: []
    }
  };
  globalThis.document = {
    body: {dataset: {}},
    getElementById: function (id) {
      return chunks[id] ? {textContent: JSON.stringify(chunks[id])} : null;
    }
  };
  helpers.state.payloadVersion = "v2";
  helpers.state.payload = {
    schema_version: "alc.render.reader_payload.v2",
    source_identity: source,
    block_manifest: manifests,
    block_fingerprints: {},
    reader_chunks: descriptors,
    resources: [],
    diagnostics: [],
    selected_roles: [],
    publication: {
      source_document: {blocks: manifests.slice(), metadata: {}},
      outline: [],
      bibliography: [],
      glossary: [],
      labels: {},
      reader_profile: {}
    }
  };
  helpers.state.payloadChunks = descriptors;
  helpers.state.payloadChunksById = new Map(descriptors.map(function (item) {
    return [item.chunk_id, item];
  }));
  helpers.state.payloadChunkByBlockId = new Map([
    ["block-unrelated", descriptors[0]],
    ["block-target", descriptors[1]]
  ]);
  helpers.state.loadedPayloadChunkIds = new Set();
  helpers.state.loadingPayloadChunkIds = new Set();
  helpers.state.embeddedRevisions = [];
  helpers.state.revisions = new Map();
  helpers.state.revisionDigests = new Map();
  helpers.state.selected = new Map();
  helpers.state.activeFragmentIds = new Set();
  helpers.state.sourceIndexes = null;
  helpers.state.indexedPayload = null;
  helpers.state.sourceIdentityJson = null;
  var metadata = {
    anchor: {
      kind: "block",
      related_blocks: [{
        block_id: "block-target",
        content_fingerprint: fingerprint,
        kind: "paragraph",
        locator: locator,
        ordinal: 1
      }],
      target_id: "block-target"
    },
    appearance: null,
    citation_ids: [],
    deleted: false,
    fragment_id: "external-note",
    language: "zh-CN",
    parent_semantic_digest: "b".repeat(64),
    priority: 110,
    provenance: {producer: "alc-render-browser"},
    revision: 2,
    role: "note",
    schema_version: "alc.render.fragment_revision.v3",
    source: source,
    title: "External note"
  };
  var markdown = "external revision";
  var digest = await helpers.semanticDigest(metadata, markdown);
  var encoded = "<!-- ALC:FRAGMENT-JSON:BEGIN -->\\n" +
    helpers.stableStringify(metadata) +
    "\\n<!-- ALC:FRAGMENT-JSON:END -->\\n" + markdown;
  var parsed = await helpers.parseRevisionFile(
    encoded, "revision-000002-" + digest + ".md"
  );
  if (parsed.fragment_id !== "external-note") {
    throw new Error("external revision was not parsed after anchor hydration");
  }
  if (!helpers.state.loadedPayloadChunkIds.has("chunk-target")) {
    throw new Error("external revision did not hydrate its anchor chunk");
  }
  if (helpers.state.loadedPayloadChunkIds.has("chunk-unrelated")) {
    throw new Error("external revision hydrated an unrelated chunk");
  }
  if (!helpers.state.payload.publication.source_document.blocks[1].locator) {
    throw new Error("anchor hydration did not replace the block manifest");
  }
})().catch(function (error) {
  console.error(error.stack || error);
  process.exitCode = 1;
});
"""
    )
    subprocess.run(
        [node, "-"], input=instrumented, check=True, capture_output=True, text=True
    )


def test_reader_hydration_waits_for_quiet_idle_budget_and_activity_reset() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is unavailable")
    javascript = _text("reader.js")
    startup = javascript.rfind("\n  if (document.readyState")
    assert startup > 0
    instrumented = (
        "globalThis.window = globalThis;\n"
        + javascript[:startup]
        + """
  globalThis.__alcReaderTest = {
    state: state,
    scheduleIdleHydration: scheduleIdleHydration,
    noteHydrationActivity: noteHydrationActivity
  };
}());
var helpers = globalThis.__alcReaderTest;
var timers = [];
var idle = [];
var cancelled = [];
globalThis.document = {body: {dataset: {alcRenderComplete: "false"}}};
window.setTimeout = function (callback, delay) {
  timers.push({callback: callback, delay: delay});
  return timers.length;
};
window.clearTimeout = function (handle) { cancelled.push(handle); };
window.requestIdleCallback = function (callback) {
  idle.push(callback);
  return 91;
};
window.cancelIdleCallback = function (handle) { cancelled.push(handle); };
helpers.scheduleIdleHydration();
if (timers.length !== 1 || timers[0].delay !== 2000 || idle.length !== 0) {
  throw new Error("hydration did not wait for two seconds of quiet");
}
timers[0].callback();
if (idle.length !== 1) throw new Error("quiet hydration did not request idle work");
idle[0]({timeRemaining: function () { return 11; }});
if (idle.length !== 2) throw new Error("short idle budget rendered a chunk");
helpers.state.hashCalibration = {targetId: "block-1"};
helpers.noteHydrationActivity();
if (helpers.state.hashCalibration !== null) {
  throw new Error("reader activity did not release hash calibration");
}
if (timers.length !== 2 || timers[1].delay !== 2000 || !cancelled.length) {
  throw new Error("reader activity did not pause and restart quiet hydration");
}
"""
    )
    subprocess.run(
        [node, "-"], input=instrumented, check=True, capture_output=True, text=True
    )


def test_reader_preserves_source_text_and_glossary_rendering_contracts() -> None:
    javascript = _text("reader.js")

    assert "removeVisibleHtmlTags(heading)" in javascript
    assert "removeVisibleHtmlTags(table)" in javascript
    assert "removeVisibleHtmlTags(figure)" in javascript
    assert 'decorateGlossary(original, "source")' in javascript
    assert 'decorateGlossary(translated, "target")' in javascript
    assert "equation_label_reconciliation" in javascript
    assert "reconciliation.effective_label.trim()" in javascript


def test_reader_uses_explicit_outline_for_navigation_and_section_anchors() -> None:
    javascript = _text("reader.js")

    assert (
        "renderContents(contents, publication.outline || [], strings)"
        in javascript
    )
    assert "sectionAnchors: sectionAnchors" in javascript
    assert "sectionAnchors.get(target)" in javascript
    assert "appendTocTitle(link, section.title);" in javascript
    assert "function appendTocTitle(parent, value)" in javascript
    assert "parent.appendChild(document.createTextNode" in javascript
    assert "typeset(parent);" in javascript
    assert 'safeToken(section.anchor_block_id)' in javascript
