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
`#bib.bibN`. A validated `ac.document.source_target_manifest.v1` may bind each
authored reference alias to its exact one-item LIST block. Older sources
without that metadata resolve bibliography links only when every citation
validates against one list in a structured `References` or `Bibliography`
section. The Reader loads and focuses the canonical target, restoring Source
visibility when needed; unresolved links become unavailable text. Legacy
structural `#S...` links use the same validated manifest when the rich source
provides one. That manifest is authoritative: omitted aliases do not merge
with fallback inference. Older sources without the metadata key fall back only
when the exact alias identifies one unique source block locator.
Resolved links use the same progressive navigation and focus behavior. Large
structural targets use a subtle background state rather than an outer focus
box that can be clipped by the lane; keyboard focus remains visibly indicated;
missing or ambiguous structural targets retain their authored plain text with
no link affordance or diagnostic suffix. In a wide
side-by-side view, equal-length source and translation reference lists also
share per-item rows. Complex, mismatched, narrow, and stacked layouts keep the
ordinary block flow. Split one-item bibliography blocks align the first and
last translated flow margins by authoritative bibliography identity, not by
matching citation text.

RichDocument v3 `list_path` metadata remains authoritative across flat prose,
equation, table, Figure, and code blocks owned by one authored list item. The
Reader draws a marker only for segment zero at each list depth; later segments
keep the same gutter without repeating a marker. Markdown exports preserve the
same ownership with CommonMark continuation indentation. RichDocument v2
sources without `list_path` retain their existing list rendering.

Validated `ac.document.source_front_matter.v1` entries render at their exact
block insertion point. An authored byline immediately after the primary title
is promoted into the book header and preserves author order, affiliation
markers, ORCID links, contacts, and ordered affiliation occurrences. When the
entry includes authoritative `creator_flow`, the Reader resolves its exact
author/contact/affiliation slots and renders the authored creator grouping in
source order: one column on narrow screens and at most two columns on wider
screens. Repeated affiliation occurrences remain presentation only; semantic
author-to-affiliation association still comes from normalized markers. The older
`reader_profile.authors` list remains only a fallback for documents without
structured front matter.

Validated `ac.document.source_notes.v1` metadata binds each marker through
`owner_block_id` plus its typed payload anchor. The Reader never scans owner
text or uses `owner_locator` for routing. Source note bodies render once below
their owner with a keyboard-accessible marker/backlink pair. A translation
Fragment may bind one note through exact provenance
`source_note_translation = {schema_version, note_id}`; it keeps the ordinary
`translation` role but is excluded from block translation selection and shown
only beside that note. Its owner translation receives the same exact superscript
marker when the translation contains the editable `[^note_id]` token. The token
is recognized only in ordinary translated text, not inside links, code, or math;
duplicates fail closed, and moving it in the Markdown editor moves the rendered
marker with the revision. Mirrored Tables instead reuse the validated source
cell coordinates and retarget the exact cloned marker. Translated note bodies
use ordinary editable Fragment surfaces, begin with a backlink marker, and use
the translation appearance. Source-note rows, source markers, and translation
markers share the owner block's progressive chunk, so both marker-to-note and
note-to-exact-marker hashes remain navigable. The Fragment anchor must target
the note owner, and a second Fragment claiming the same note fails closed.
Markdown exports
include structured front matter plus source/translated notes as labeled
blockquotes.

Validated `ac.document.source_presentation.v1` metadata is authoritative when
present. The Reader joins rich views by exact block/field coordinates, renders
typed heading, caption, Table-cell, paragraph, and LIST-item math/links, and
overlays authored strong/emphasis ranges without inferring from visible text.
Classification, abstract, and acknowledgements roles retain their exact source
semantics. Heading payload levels are authoritative for Reader hierarchy and
portable Markdown; the consumer does not replace them with role-specific CSS
levels. Exact classification relations compose
the authored heading, separator, and ordered value blocks into one source and
translation surface; related value blocks are not rendered again. Editing a
classification value keeps its separately versioned heading as a read-only
prefix on the same line inside the composite editor; editing the heading itself remains a
separate revision operation. The composed translation exposes one relation-level
speech/edit action group at the end of the surface; per-revision hover controls
do not obscure the inline label or value. Figure and
Table captions share one descriptor and keep authored before/after/embedded
placement plus start/center/end alignment in both lanes. A neutral alignment
stays a consumer default rather than being guessed. Merged Table cells preserve
validated source geometry. Origin-cell presentation removes the synthetic full
grid, applies only validated physical rule edges, and preserves authored
left/center/right/start/end alignment in both source and translation Tables.
Rule provenance does not imply a pixel thickness or dashed/double style, and
raw TeX padding remains a safe Reader default. Translation heading typography
follows the source Reader hierarchy instead of trusting an independently
authored Markdown heading depth.
Older documents without this optional metadata retain their plain payload
rendering; invalid present metadata fails closed.

Source and rendered Markdown tables share one responsive overflow region.
Wide tables keep readable cells and can be scrolled horizontally by touch,
pointer, or keyboard; their scrollbar uses the same compact, low-contrast
hover/focus treatment as the contents pane. Compact tables do not add an extra
tab stop. Table data
mirrored into a translation lane keeps the authoritative scientific notation
while its translated caption remains in the authored caption position. A
caption-only historical Table translation still receives the authoritative
source Table geometry instead of dropping the Table; shared caption typography,
margin, and lane padding keep equivalent source/translation Tables aligned.
Current translation producers use this caption-only Table surface directly, so
raw pipe-delimited cell text is never rendered a second time above the mirrored
Table.

Display equation labels use parenthesized source numbering. KaTeX's available
operator breakpoints are enabled for long display equations, with horizontal
overflow retained as the lossless fallback. A bounded semantic macro registry
maps supported source macros such as AASTeX `\\arcdeg` to their equivalent
KaTeX form without rewriting the stored source TeX; unknown macros still follow
the existing visible error fallback. Content links use a distinct accessible
link color; glossary terms keep their separate glossary affordance.

Figure blocks with validated manifest panels render every available panel in
authored order, including compound object/image Figures; parent navigation
never aliases panel zero. Missing or unsupported panels are not fabricated.
When `source_presentation.v1.figures` is present, the Reader joins each Figure
descriptor by exact block ID and each panel by exact index/source ID. Authored
rows, per-row flex source, explicit breaks, display width, and aspect ratio
drive the layout. Rows separated in the source may use different validated
`ltx_flex_size_1|2|3` profiles; the Reader never collapses that mixed-row
provenance into one inferred root column class. For validated `single`/`flex`
layouts, each bilingual lane renders the
same authoritative media layout while retaining its independent source or
translated caption. Every authored row keeps its exact panel count (for
example, a three-panel row stays three columns); panels shrink within that row
instead of being regrouped by viewport width. Display width remains a source
hint rather than a hard image-size cap.
A LaTeXML/ar5iv `ltx_flex_size_2` row retains the source profile's responsive
minimum: it stays two columns when the lane can hold both readable panels and
wraps to one panel per line in a narrower lane. The per-lane Figure canvas is
centered and capped at the source profile's 52rem document width, so a wide
Reader does not enlarge panels beyond the original HTML canvas.
A `neutral` descriptor, or a legacy document with no presentation
metadata, keeps the existing source-order `auto-fit` fallback with a 9rem
minimum. The Reader never infers columns from panel count, caption, or filename.
All images retain `max-width: 100%`, their aspect ratio, and the 38rem height
cap.

Parallel Tables with `before_content` captions synchronize the rendered
caption track so identical source/translation Table geometry begins at the
same vertical position even when the two languages wrap to different line
counts. `after_content` and embedded captions keep their authored placement.
Single HTML mirrors the same panel grid, and Markdown packages include each
available panel as its own digest-addressed resource.

Translation, guide, companion, note, and glossary content can be edited inline.
Single-click or double-click activation follows the Reader setting. Advanced
editing provides Markdown preview and version history. Saving appends an
immutable revision; cancelling leaves the selected revision unchanged. The
Reader warns before leaving an unsaved draft.
Editor labels prefer `reader_profile.target_language`; when that optional value
is absent, one unique selected translation language supplies the locale. Mixed
translation languages do not guess a UI language.

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

Because portable CommonMark has no standard paired-anchor contract for these
legacy source identities, both Markdown modes export exact `#bib.bibN` and
structural `#S...` links as readable labels while preserving code, external,
and resource links. Single HTML keeps validated Reader navigation.
Single HTML resolves exact internal aliases only through the authoritative
structural, bibliography, and source-note indexes. Nested aliases may contain
numeric path segments; no consumer regex reconstructs their meaning.

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
