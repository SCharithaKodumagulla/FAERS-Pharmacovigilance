#!/bin/bash
# Verify the downloaded FAERS archives against the committed SHA-256 manifest.
#
# The archives themselves are gitignored (~1.3 GB of re-fetchable public FDA
# data), so this manifest is what makes the input data reproducible: anyone can
# run scripts/download_faers.sh and prove they got byte-identical files.
#
# Usage:  scripts/verify_manifest.sh
# Exit 0 = all 20 quarters present and matching; non-zero otherwise.

set -u
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$REPO_ROOT/scripts/faers_manifest.sha256"

if [[ ! -f "$MANIFEST" ]]; then
  echo "ERROR: manifest not found at $MANIFEST" >&2
  exit 2
fi

cd "$REPO_ROOT/data/raw" || { echo "ERROR: data/raw missing — run scripts/download_faers.sh" >&2; exit 2; }

expected=$(wc -l < "$MANIFEST" | tr -d ' ')
present=$(ls faers_ascii_*.zip 2>/dev/null | wc -l | tr -d ' ')

if [[ "$present" -eq 0 ]]; then
  echo "No archives in data/raw/. Run: scripts/download_faers.sh" >&2
  exit 1
fi

echo "Verifying $present/$expected archives against manifest…"
if shasum -a 256 --check --status "$MANIFEST" 2>/dev/null; then
  echo "OK: all $expected FAERS archives match the manifest."
  exit 0
fi

# Not a clean pass — report exactly which files are the problem.
echo "MISMATCH or MISSING files:" >&2
shasum -a 256 --check "$MANIFEST" 2>&1 | grep -v ': OK$' >&2
exit 1
