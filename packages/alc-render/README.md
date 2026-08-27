# alc-render

`alc-render` owns ALC's immutable Markdown overlay contracts and standalone
reader delivery. A publication contains its frozen rich source document and
refers to immutable fragment revision and resource files, so it does not depend
on an unrecorded caller-supplied source.

## Quick start

When `ac-document` and `alc-render` are installed on `PATH`, build a source-only
reader with:

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

`export-rich-document` accepts local Markdown, HTML, or flattened single-file
TeX. Add `--validator note.pdf` when a PDF should validate fidelity or page
mapping. It creates the rich source, metadata, and verified resource tree; the
caller should not hand-copy resources or construct the metadata resource array.
The output directory must be new or empty.

A publication with no overlay Layers is valid. To include existing Layers,
repeat `--layer publication/<layer>.json` on `compose` in publication order.
Each Layer and every fragment revision it references must already be below the
directory containing the output `publication.json`; moving only a Layer is not
enough.

If bare commands are unavailable in an installed ALC Skill, use its runtime:

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

`ac-document export-rich-document` prints a JSON object containing the
exported source, metadata, resources, document digest, and parse warnings.

Successful `alc-render` commands print flat JSON objects with these exact
fields:

| Command | Result fields |
| --- | --- |
| `compose` | `publication`, `publication_digest`, `source_document_digest`, `layer_count` |
| `render` | `html`, `publication_digest`, `selected_revision_digests`, `warnings` |
| `validate` | `publication`, `publication_digest`, `warnings`, plus `html` when supplied and `browser` when requested |
| `standalone-html` | `html` |

Ordinary validation checks the publication and, when supplied, its rendered
HTML. `--browser` requires `--html` and adds a local Chromium behavior check.
`standalone-html` is a separate utility for embedding the local assets of an
existing HTML bundle; it does not compose or validate an ALC publication.

Fragment revisions use strict JSON front matter between ALC-specific
delimiters. YAML is not accepted. The v2 contract added an optional paired
foreground/background appearance; the reader treats it as a declaration for
the fragment's `(role, priority)` group, not as per-fragment styling. A newer
browser declaration applies to every selected fragment in that group. The v3
contract adds an immutable deletion tombstone. Readers remain compatible with
v1 and v2 revisions. Fragment priorities are positive integers; block and
section are the only anchor kinds. A publication with no overlay layers is
valid, and a source plus translation layer can be rendered and exported without
a Companion layer.

The initial public API includes:

- frozen source, anchor, fragment revision, layer, and publication value
  objects;
- exact JSON document codecs;
- canonical fragment semantic digests and JSON-front-matter Markdown codecs;
- revision resolution with diagnostics for malformed files, dangling
  revisions, and forks.

New immutable revisions are stored as
`fragments/revision-<number>-<semantic-digest>.md`. The validated JSON front
matter owns fragment identity; directory names below `fragments/` are opaque
storage organization and are never interpreted as semantic IDs.

Standalone HTML and command-line delivery are built on these contracts. For
large publications, the reader renders an initial reading view first, loads
nearby chunks on demand, and completes the remaining chunks during browser idle
time. Contents links and URL fragments render their target before scrolling;
printing renders every remaining chunk before the browser creates its preview.
The reader never unloads a rendered chunk. On desktop, drag the right edge of
the contents sidebar to resize it between 12rem and the smaller of 32rem or 45%
of the viewport. Dragging 2rem past the minimum collapses it; the contents
button restores its last width for the current page. Dragging right from the
minimum resizes normally. The width is not persisted.

By default, the reader places source and translation side by side on wide
screens and stacks them on narrow screens. The settings panel can also use the
stacked layout on wide screens. Guide and companion fragments span the full
reading width, while figures and translated captions remain aligned. When a
translated document title is available, it appears with the source title in the
page header.

The More settings panel controls translation layout, edit activation, English
and Chinese font stacks, display scale, line height, and content width.
Double-click editing is the default. These preferences affect the current
reader rather than fragment source, and a Single HTML export captures their
current values.

The edit activation setting opens a translation, companion, guide, or note body
on a single or double click. The inline controls save or discard the single
active draft. Clicking elsewhere after making a change asks whether to save or
discard it; keyboard-activated clicks use the same guard. The browser also
warns before leaving the page with an unsaved draft. Overlay Markdown follows
CommonMark and supports pipe tables. Advanced opens the complete title,
Markdown, preview, metadata, and history editor without discarding the draft.
Browser editing saves from the revision snapshot already loaded in the reader.
Reading mode shows the fragment role and shows its revision number only when it
is greater than 1; inline editing shows the role, priority, and revision.
Advanced also offers paired color presets, synchronized color pickers and
`#RRGGBB` fields, plus a reset to the role default. One color applies to every
fragment with the same role and priority; changing priority creates or joins a
separate color group. Notes use black with white text by default.
Version history appears only after a fragment has more than one revision.
Advanced places Delete at the left edge and groups Cancel with Save on the
right. Delete appends an empty tombstone revision, hides the element, and
retains every earlier immutable revision. Empty notes are treated as deleted;
saving a note after clearing both title and Markdown writes the same tombstone.
The Add control at that source anchor reopens the latest hidden fragment and its
history, so content can be restored or replaced without discarding its lineage.
Save remains disabled while normalized content is unchanged, and the defensive
no-op path chooses no directory and creates no revision. Selecting another
fragment cancels a clean draft immediately. If the active draft has unsaved
changes, the reader keeps it, scrolls it into view, and focuses its editor. A
changed save appends and verifies one immutable revision file, then updates only
the affected fragment and render chunk; it does not rescan the fragments tree.
Files added by another process are incorporated, with fork diagnostics when
needed, the next time the reader connects to or restores the project directory.
That refresh enumerates nested fragment directories in bounded concurrent
batches and reads changed files with bounded concurrency.
Toolbar status messages clear automatically after ten seconds.

Reader prose uses the browser's strict East Asian line-breaking mode, which
keeps common Chinese closing punctuation away from line starts without custom
text segmentation.

The speaker icon (`Listen` tooltip) uses the browser Web Speech API and does not
bundle a voice model or generated audio. Source is selected by default;
translation, companion, guide, note, and dynamically discovered roles can be
selected independently. Source and target content have separate voice choices.
Each automatic option shows the default voice for its profile language, while
playback matches the declared language of the current segment. It may therefore
choose another voice in a mixed-language document.

Playback starts at the first selected, readable segment at the current viewport
and advances in publication order. Each source block or overlay fragment is one
speech segment; ALC does no sentence tokenization. Headings, prose, lists, and
figure or table captions are read, while display equations, code, and table
bodies are skipped. Both players provide the same transport, playlist, 0.5x to
3x rate, and repeat controls. Per-fragment speaker buttons start from that exact
segment. Speaker and edit actions use the same hover/focus disclosure at every
viewport width. On a non-mouse pointer, the first tap on a non-interactive card
surface reveals the same compact actions without activating the card; revealed
touch actions use 44-pixel targets. Voice and playback state remain in the
browser. If the browser reports no voices, the panel shows that condition
without affecting reading or editing.

The browser toolbar calls the directory action `New save location` until a
project directory is available and `Change save location` afterwards. Export
first refreshes that connected directory. A remembered directory handle is
scoped to the immutable source identity, so opening another publication does
not scan revisions from the previous document. The Markdown section owns its
all-latest or latest-changes-only range. Source, translation, guide, companion,
note, and additional selected roles can be combined with checkboxes. The
result can be downloaded either as one resource-free Markdown file or as a
portable Markdown package. Source is unavailable in the changes-only range
because it is immutable. Full-text HTML and PDF actions are independent of the
Markdown range. Directory changes and exports wait until the active draft is
saved or cancelled.

Combined Markdown presents guide, companion, and note fragments as labeled
blockquotes so supplemental content remains visually distinct from source and
translation. Every authored Markdown line is quoted, preserving nested lists,
links, formulas, and fenced code. Translation remains ordinary document
content; unknown dynamic roles retain the generic bold role/title label.
For backward compatibility, a legacy whole-line `$$...$$` formula is rendered
as display math and normalized to line-delimited `$$` when supplemental
Markdown is exported. Fenced and indented code, plus ordinary same-line code
spans, are not rewritten.

An all-latest Markdown package reconstructs `document.md` in source-block
order. When translation is selected without source, a missing one-to-one block
translation falls back to the frozen source block. The downloaded deterministic
ZIP includes a manifest and each validated publication resource actually
referenced by the emitted Markdown below digest-addressed `resources/` paths;
local Markdown links are rewritten to those paths. Source-only code, equations,
tables, and selected figures therefore remain present, while translated figure
captions retain their source image. Glossary
and deduplicated bibliography are separate, default-selected content options;
they are omitted when unchecked and unavailable in the changes-only range.
Bibliography titles remain canonical source titles because the publication
contract has no translated-title field. Footnote syntax is preserved when it
exists in source or fragment Markdown; the render contract has no separate
footnote model from which to reconstruct omitted definitions.
The single-file mode omits Markdown and HTML images, retains readable figure
descriptions and captions, and turns links to bundled local resources into
plain labels. Formulas, code, tables, footnotes, and external links remain
Markdown. The changes-only range exports only checked revisions that differ
from the reader's embedded baseline. Both Markdown package ranges include only
resources referenced by the emitted `document.md`; unchecked content and
unreferenced publication resources are omitted and are not decoded while the
package is assembled. Single-file Markdown does not decode publication resource
payloads.

Resource portability intentionally follows the Markdown shapes emitted by ALC:
inline links and images, same-line reference definitions, and HTML `src`/`href`
attributes outside ordinary code spans or code blocks. Multiline code spans and
multiline or duplicate reference definitions are outside this export contract;
use fenced code and ordinary inline links when a local resource must be
portable.

HTML export contains the complete latest standalone Reader, including its UI
and current appearance snapshot. The PDF action renders all remaining Reader
chunks and opens the browser's Print / Save as PDF dialog for the current
visible content. That PDF is a user-side derivative, not an ALC release
artifact, and ALC does not validate, reproduce, or automatically publish it.

Command help is available without opening the manual:

```bash
alc-render --help
alc-render <command> --help
```

Run the package tests with:

```bash
python -m pytest packages/alc-render/tests
```
