#!/usr/bin/env bash
# Run with the security tool environment activated. Locks target Python 3.12 on Linux.
set -euo pipefail
lock_repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$lock_repo_root"
lock_options=(--generate-hashes --strip-extras --reuse-hashes --allow-unsafe --no-emit-index-url --no-emit-trusted-host --no-header)
pip-compile "${lock_options[@]}" "$@" --output-file=backend/requirements.txt backend/requirements.in
pip-compile "${lock_options[@]}" "$@" --output-file=backend/requirements-dev.txt backend/requirements-dev.in
pip-compile "${lock_options[@]}" "$@" --output-file=ci/security-requirements.txt ci/security-requirements.in
