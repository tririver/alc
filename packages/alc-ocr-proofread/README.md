# alc-ocr-proofread

`alc-ocr-proofread` compares MinerU page-mapped OCR with complete PDF page
images. It uses `ac-jobs` for durable page work, `ac-llm` for bounded model
calls, and the public `ac-document` PDF renderer.

```bash
alc-ocr-proofread --help
```

```bash
alc-ocr-proofread proofread book.md --pdf book_origin.pdf \
  --content-list book_content_list.json --project-dir project
alc-ocr-proofread status --project-dir project
alc-ocr-proofread resume --project-dir project --input review.json
alc-ocr-proofread reconcile-boundaries --project-dir project \
  --pdf book_origin.pdf
alc-ocr-proofread validate --project-dir project
```

The content list is mandatory and authoritative for page boundaries. The
package does not run OCR or infer page alignment. Every adjacent page pair is
reviewed against both full-page images; confirmed split paragraphs are joined,
while page boundaries remain structured provenance notes. The
`reconcile-boundaries` command adds this review to a verified older delivery
without repeating page proofreading. Private state lives below
`.alc/ocr-proofread/`; successful delivery is `proofread.md`,
`proofread.manifest.json`, `proofread.changes.jsonl`, and
`proofread-assets/`.

## Tests

```bash
python -m pytest packages/alc-ocr-proofread/tests
```
