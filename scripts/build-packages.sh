#!/usr/bin/env bash
set -euo pipefail

root="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd -P)"
python_bin="${PYTHON:-python3}"
output="${ALC_BUILD_DIR:-$root/local/dist}"

rm -rf "$output"
mkdir -p "$output"

for project in "$root"/packages/alc-*/pyproject.toml; do
  "$python_bin" -m build --outdir "$output" "${project%/pyproject.toml}"
done
