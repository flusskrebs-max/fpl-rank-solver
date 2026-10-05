#!/usr/bin/env bash
# Replace vendor/open-fpl-solver with a fresh copy of upstream at REF (default: main).
# Usage: scripts/update_upstream.sh [ref]
# Afterwards: review `git diff --stat vendor/`, run `uv run pytest`, then commit.
set -euo pipefail

REF="${1:-main}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --quiet https://github.com/solioanalytics/open-fpl-solver.git "$TMP/src"
git -C "$TMP/src" checkout --quiet "$REF"
SHA=$(git -C "$TMP/src" rev-parse HEAD)
DATE=$(git -C "$TMP/src" log -1 --format=%cs)

rm -rf "$ROOT/vendor/open-fpl-solver"
mkdir -p "$ROOT/vendor"
git -C "$TMP/src" archive --format=tar --prefix=open-fpl-solver/ HEAD | tar -x -C "$ROOT/vendor"
echo "$SHA $DATE" > "$ROOT/vendor/.open-fpl-solver-commit"

echo "Vendored open-fpl-solver at $SHA ($DATE)."
echo "Next: git diff --stat vendor/  &&  uv run pytest"
