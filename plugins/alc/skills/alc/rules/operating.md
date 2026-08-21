# Operating rules

- Treat a user-supplied project directory as the project root. Do not append an
  attempt directory or replace it with a new build root.
- Keep durable workflow state under `<project-dir>/.alc/`; keep generic AC
  document cache under `.ac/cache/ac-document` or an explicit
  `AC_DOCUMENT_CACHE`.
- Use public CLI/API status, validation, result, resume, and stop surfaces.
  Do not infer state by editing private run files unless the owning command
  explicitly returns an editable recovery path.
- Preserve frozen source and translation identity. Do not silently substitute
  another paper, edition, PDF, or translation.
- Do not stop a valid run because it is long or quiet. Use status or host
  background execution.
- Deliver visible HTML or source artifacts in addition to hidden state.
