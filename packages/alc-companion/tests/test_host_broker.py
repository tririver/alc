from __future__ import annotations

import subprocess
import shlex
from pathlib import Path

from ac_llm import (
    AcRuntimeEnvironment,
    HostRequest,
    HostResponseStatus,
)
from alc_companion.host_broker import CompanionSourceHostBroker


def _environment() -> AcRuntimeEnvironment:
    return AcRuntimeEnvironment(
        {
            "AC_HOME": None,
            "AC_RUNTIME_HOME": None,
            "AC_DOCUMENT_CACHE": None,
            "PATH": "/usr/bin:/bin",
        }
    )


def test_broker_executes_only_registered_read_command(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker = CompanionSourceHostBroker(_environment())
    command = [
        "ac-document",
        "read-cached-source-range",
        "--document-ref",
        "{}",
        "--cache-root",
        str(tmp_path),
        "--text-only",
        "1",
        "10",
    ]
    broker.register_commands({"argv": command})
    calls: list[tuple[str, ...]] = []

    def fake_run(argv, **_kwargs):
        calls.append(tuple(argv))
        return subprocess.CompletedProcess(argv, 0, b"source", b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    response = broker.execute(
        HostRequest(
            "read-1",
            " ".join(shlex.quote(item) for item in command),
            "read source",
        ),
        workspace=tmp_path,
    )

    assert response.status is HostResponseStatus.COMPLETED
    assert response.result["stdout"] == "source"
    assert calls == [tuple(command)]
    refused = broker.execute(
        HostRequest("write-1", "rm -rf data", "write"),
        workspace=tmp_path,
    )
    assert refused.status is HostResponseStatus.REFUSED
    assert calls == [tuple(command)]


def test_broker_allows_only_bounded_term_for_registered_search(
    monkeypatch,
    tmp_path: Path,
) -> None:
    broker = CompanionSourceHostBroker(_environment())
    template = [
        "ac-document",
        "search-full-text",
        "--document-ref",
        "{}",
        "--cache-root",
        str(tmp_path),
        "--term",
        "<term>",
    ]
    broker.register_commands({"argv": template})
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda argv, **_kwargs: subprocess.CompletedProcess(
            argv, 0, b"match", b""
        ),
    )

    command = [*template[:-1], "symbiotic star"]
    response = broker.execute(
        HostRequest(
            "search-1",
            " ".join(shlex.quote(item) for item in command),
            "search",
        ),
        workspace=tmp_path,
    )
    assert response.status is HostResponseStatus.COMPLETED
    refused = broker.execute(
        HostRequest(
            "search-2",
            " ".join(
                shlex.quote(item)
                for item in [*template[:-1], "x" * 1001]
            ),
            "search",
        ),
        workspace=tmp_path,
    )
    assert refused.status is HostResponseStatus.REFUSED
