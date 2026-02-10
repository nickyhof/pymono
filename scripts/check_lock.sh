#!/usr/bin/env bash
# Check that uv.lock is in sync with pyproject.toml files.
# Fails if someone changed a pyproject.toml without running `uv lock`.
set -euo pipefail

echo "Checking uv.lock is up to date..."
if uv lock --check 2>&1; then
    echo "✅ uv.lock is in sync."
else
    echo "❌ uv.lock is out of date. Run 'uv lock' to update."
    exit 1
fi
