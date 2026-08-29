# alc-render

`alc-render` owns ALC's immutable Markdown overlay contracts and standalone
Reader delivery. A publication contains a frozen rich source and references its
Layer, revision, and resource files.

## Quick start

With `ac-document` and `alc-render` on `PATH`:

```bash
ac-document export-rich-document note.md --output-dir publication

alc-render compose \
  --source publication/rich-source.json \
  --metadata publication/metadata.json \
  --output publication/publication.json

alc-render render \
  --publication publication/publication.json \
  --html publication/reader.html

alc-render validate \
  --publication publication/publication.json \
  --html publication/reader.html
```

`export-rich-document` accepts Markdown, HTML, or flattened single-file TeX.
Pass `--validator note.pdf` to validate fidelity or page mapping against a PDF.
The output directory must be new or empty.

A publication may contain no overlay Layers. To include existing Layers, repeat
`--layer publication/<layer>.json` on `compose` in publication order. Layer and
revision files must remain below the directory that contains
`publication.json`.

When bare commands are unavailable in an installed ALC Skill, use its runtime:

```bash
<skill-dir>/scripts/alc-runtime ac-document export-rich-document --help
<skill-dir>/scripts/alc-runtime alc-render --help
```

From this source checkout, point the launcher at both local repositories:

```bash
export AC_INSTALL_SOURCE=local
export AC_PRODUCT_REPO_ROOT="$PWD"
export AC_FOUNDATION_REPO_ROOT="/path/to/ac-foundation"

plugins/alc/bin/alc-runtime ac-document export-rich-document --help
plugins/alc/bin/alc-runtime alc-render --help
```

Successful commands print flat JSON objects:

| Command | Result fields |
| --- | --- |
| `compose` | `publication`, `publication_digest`, `source_document_digest`, `layer_count` |
| `render` | `html`, `publication_digest`, `selected_revision_digests`, `selected_glossary_revision_digests`, `warnings` |
| `validate` | `publication`, `publication_digest`, `warnings`, plus `html` when supplied and `browser` when requested |
| `standalone-html` | `html` |

`validate --browser` requires `--html` and runs a local Chromium behavior check.
`standalone-html` only embeds the assets of an existing HTML bundle.

## Revision contracts

Fragment revisions use canonical JSON front matter and Markdown bodies. New
revisions are stored as:

```text
fragments/revision-<number>-<semantic-digest>.md
```

The v2 Fragment contract added paired foreground and background appearance for
a `(role, priority)` group. The v3 contract added deletion tombstones. Readers
remain compatible with v1 and v2 revisions. Resolution reports malformed
files, dangling parents, and forks without choosing a conflicting branch.

The public API includes frozen source, anchor, Fragment, Layer, and Publication
values; exact JSON codecs; semantic digests; Markdown codecs; and revision
resolution.

Glossary corrections use a separate history:

```text
glossary/revision-<number>-<semantic-digest>.md
```

The Publication entry is virtual v1 and the first correction is v2. The JSON
front matter stores identity, parent, entry snapshot, and provenance. The
`definition` field is the Markdown body. Legacy canonical `.json` revisions
remain readable.

Only an existing translated-term field and `definition` may change. Entry ID,
source term, anchors, citations, and unknown fields remain unchanged. A blank
translated term is invalid. Definitions support CommonMark and KaTeX with raw
HTML disabled. Entries that contain finite non-integer JSON numbers remain
readable but are browser read-only because Python and JavaScript do not share a
canonical float spelling.

Changing a translated term updates associated `translation`, `companion`, and
`guide` Fragments. It also updates exact occurrences in the definitions of
other glossary entries. Source, note, reference, code, math, URL, citation, and
link-destination content is not rewritten. Persisted mention ranges keep their
owner when translated surfaces overlap.

Propagation members are staged below `glossary-batches/<batch-id>/`. The
initiating glossary revision is written last and acts as the commit marker.
Readers expose the batch only after every referenced Fragment and dependent
glossary revision passes path, digest, parent, and lineage validation.
Definition-only edits create no propagation batch. `edition_digest` remains
Fragment-only for compatibility with `alc-companion`.

## Reader

The standalone Reader progressively renders large publications and completes
all remaining chunks before print. Source and translation are parallel on wide
screens and stacked on narrow screens. More settings controls layout, edit
activation, fonts, scale, spacing, and content width for the current Reader.
A Single HTML export captures the current appearance.

Some older rich sources identify in-document bibliography links as
`#bib.bibN`. The Reader resolves them only when every citation validates
against one list in a structured `References` or `Bibliography` section. It
loads and focuses the canonical target, restoring Source visibility when
needed; unresolved links become unavailable text. Structural `#S...` links are
not inferred. In a wide side-by-side view, equal-length source and translation
reference lists also share per-item rows. Complex, mismatched, narrow, and
stacked layouts keep the ordinary block flow.

Translation, guide, companion, note, and glossary content can be edited inline.
Single-click or double-click activation follows the Reader setting. Advanced
editing provides Markdown preview and version history. Saving appends an
immutable revision; cancelling leaves the selected revision unchanged. The
Reader warns before leaving an unsaved draft.

Glossary source terms are read-only. Translated terms and definitions are
editable, versioned, and reflected immediately in the appendix, tooltips,
linked Fragment text, and exports.

Speech uses the browser Web Speech API. Source and target content have separate
voice choices. Playback follows publication order and skips display equations,
code, and table bodies. Glossary playback reads the source term first, followed
by the translated term and definition.

## Export

Markdown export supports all latest content or latest changes only. Source,
translation, guide, companion, note, glossary, bibliography, and other selected
roles can be included independently. Source is unavailable in the changes-only
scope because it is immutable.

Single-file Markdown removes bundled image dependencies and turns local
resource links into plain labels. The Markdown package contains `document.md`,
a manifest, and only the validated resources referenced by the selected
content. Local resource links are rewritten to digest-addressed `resources/`
paths. Formulas, code, tables, footnotes, and external links remain Markdown.

Because portable CommonMark has no standard list-item anchor syntax, both
Markdown modes export exact legacy `#bib.bibN` links as readable labels while
preserving code, structural `#S...`, external, and resource links. Single HTML
keeps validated Reader navigation.

Guide, companion, and note fragments are exported as labeled blockquotes.
Translation remains ordinary document content. Glossary definitions retain
their Markdown and use the selected glossary revisions.

HTML export contains the complete latest standalone Reader. The PDF action
renders all chunks and opens the browser's Print or Save as PDF dialog.

## Development

Command help:

```bash
alc-render --help
alc-render <command> --help
```

Tests:

```bash
python -m pytest packages/alc-render/tests
```
