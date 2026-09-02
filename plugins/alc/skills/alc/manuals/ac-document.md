# ALC Document Quick Start

`ac-document` owns provider-neutral source import, deterministic parsing,
content-addressed document references, structural reads, literal text/equation
search, keyword inventory, rich-document export, and document-cache
administration. It does not identify papers, query arXiv/INSPIRE, or traverse
citations. An optional ARC installation owns those academic capabilities.

Commands return the standard ALC JSON envelope. Check `status`, `warnings`,
`error`, then `data`. The cache defaults to `.ac/cache/ac-document` below the
launch directory; set `AC_DOCUMENT_CACHE` or pass `--cache-root` consistently.

## Run ALC Document

Use `ac-document` on `PATH`, the portable Skill launcher, or the source-checkout
development fallback:

```bash
ac-document --help
<skill-dir>/scripts/alc-runtime ac-document --help
<alc-venv>/bin/ac-document --help
```

## Import, Parse, and Export

Import one local Markdown, HTML, flattened TeX, or PDF source:

```bash
ac-document import-source source.md
ac-document parse-local source.md --validator source.pdf
```

Export the neutral `RichDocument` workspace consumed by `alc-render`:

```bash
ac-document export-rich-document source.md \
  --validator source.pdf --output-dir publication
```

The export contains `rich-source.json`, `metadata.json`, and copied resources.
Do not hand-edit resource identities after export.

## Acquire a Direct HTML Source

For one direct public HTML URL, use the explicit acquisition command through
the ALC runtime rather than a local import command. It materializes a local
primary and a materialized export containing an
`ac.document.html_source_bundle.v1` bundle; it is not an implicit parser
network operation:

```bash
<skill-dir>/scripts/alc-runtime ac-document acquire-html-bundle <html-url> \
  --output-dir <materialization-dir>
```

The command atomically publishes `<materialization-dir>/source.html`,
`<materialization-dir>/manifest.json`, and any materialized local resources.

When the source will feed a Companion, retain that one primary and materialized
export, then run:

```bash
alc-companion build <materialization-dir>/source.html \
  --html-source-manifest <materialization-dir>/manifest.json
```

Do not use this generic route to classify academic sources: optional installed
ARC may first recognize and materialize an academic URL, but must return the
same ACF bundle contract to ALC.

Build an approximate durable keyword inventory from a local source:

```bash
ac-document extract-keywords source.md --project-dir run/keywords
```

## Frozen Cached Reads

Operations such as import/cache return a `CachedDocumentRef`. Preserve its JSON
and the cache root to make provider-free reads against the exact source digest,
parser contract, and parsed-document digest:

```bash
ac-document get-table-of-contents --document-ref '<ref JSON>'
ac-document get-section --document-ref '<ref JSON>' "Conclusion"
ac-document read-cached-source-range --document-ref '<ref JSON>' 10 30
ac-document search-full-text --document-ref '<ref JSON>' --term "phrase"
ac-document search-equations --document-ref '<ref JSON>' --term "2.1"
```

These commands never discover or download a paper. If the source is identified
only by arXiv, DOI, INSPIRE, URL, or academic title, the ALC Skill may suggest
using optional ARC first; it must not install ARC silently.

## Cache Administration

List neutral derived entries, then select exact document or entry IDs. Removal
is a dry run unless `--yes` is supplied:

```bash
ac-document cache list
ac-document cache remove --entry-id '<exact entry id>'
ac-document cache remove --entry-id '<exact entry id>' --yes
```

Paper provider-response cache, academic identities, portable paper-cache
archives, and refresh remain outside AC Document and ALC.

Generic run controls are available as `ac-document status`, `stop`, and
`validate` for document workflows that publish durable runs.

## Help

```bash
ac-document --help
ac-document <command> --help
```
