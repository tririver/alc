from __future__ import annotations

from pathlib import Path
import sys


PACKAGE_SRC = Path(__file__).resolve().parents[1] / "src"
ALC_LLM_SRC = Path(__file__).resolve().parents[2] / "ac-llm" / "src"
ALC_DOCUMENT_SRC = Path(__file__).resolve().parents[2] / "ac-document" / "src"
ALC_JOBS_SRC = Path(__file__).resolve().parents[2] / "ac-jobs" / "src"
ALC_TRANSLATE_SRC = (
    Path(__file__).resolve().parents[2] / "alc-translate" / "src"
)
for path in (
    PACKAGE_SRC,
    ALC_LLM_SRC,
    ALC_DOCUMENT_SRC,
    ALC_JOBS_SRC,
    ALC_TRANSLATE_SRC,
):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
