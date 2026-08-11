#!/bin/bash
# Robust FAERS quarterly ZIP downloader with integrity check + retry.
# - skips files that already pass `unzip -t`
# - uses curl --retry for transient errors
# - verifies each ZIP after download; if bad, deletes and retries up to MAX_RETRIES
# - logs to /tmp/faers_download_robust.log
#
# Downloads FAERS 2020Q1-2024Q4 into data/raw/ (gitignored - these archives are
# public FDA data, re-fetchable, and far too large to version). After the run,
# verify against the committed manifest:  scripts/verify_manifest.sh

set -u
# Script lives in scripts/; the archives belong in data/raw/
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$REPO_ROOT/data/raw"
cd "$REPO_ROOT/data/raw"

LOG=/tmp/faers_download_robust.log
MAX_RETRIES=3
: > "$LOG"

verify_zip() {
  unzip -tq "$1" >/dev/null 2>&1
}

download_one() {
  local fn="$1"
  local url="https://fis.fda.gov/content/Exports/${fn}"

  # already good?
  if [[ -f "$fn" ]] && verify_zip "$fn"; then
    local sz=$(ls -lh "$fn" | awk '{print $5}')
    echo "SKIP   $fn (already valid, $sz)" | tee -a "$LOG"
    return 0
  fi

  local attempt=0
  while (( attempt < MAX_RETRIES )); do
    attempt=$((attempt + 1))
    echo "FETCH  $fn (attempt $attempt/$MAX_RETRIES)" | tee -a "$LOG"
    rm -f "$fn"
    # curl: follow redirects, retry transient errors, fail on 4xx/5xx,
    # connect timeout 30s, max-time 30 min per file
    curl --silent --show-error \
         --location \
         --fail \
         --retry 5 \
         --retry-delay 10 \
         --retry-max-time 300 \
         --connect-timeout 30 \
         --max-time 1800 \
         -o "$fn" \
         "$url" 2>>"$LOG"
    local rc=$?
    if (( rc != 0 )); then
      echo "  curl rc=$rc, retrying after 15s" | tee -a "$LOG"
      sleep 15
      continue
    fi
    if verify_zip "$fn"; then
      local sz=$(ls -lh "$fn" | awk '{print $5}')
      echo "OK     $fn ($sz)" | tee -a "$LOG"
      return 0
    fi
    echo "  integrity FAILED, retrying after 15s" | tee -a "$LOG"
    sleep 15
  done
  echo "GIVEUP $fn after $MAX_RETRIES attempts" | tee -a "$LOG"
  return 1
}

failed=()
for year in 2020 2021 2022 2023 2024; do
  for quarter in q1 q2 q3 q4; do
    fn="faers_ascii_${year}${quarter}.zip"
    if ! download_one "$fn"; then
      failed+=("$fn")
    fi
  done
done

echo "" | tee -a "$LOG"
echo "===== DONE =====" | tee -a "$LOG"
echo "verified-good files:" | tee -a "$LOG"
ls -lh faers_ascii_*.zip | tee -a "$LOG"
echo "" | tee -a "$LOG"
if (( ${#failed[@]} > 0 )); then
  echo "FAILED (${#failed[@]}):" | tee -a "$LOG"
  printf '  %s\n' "${failed[@]}" | tee -a "$LOG"
  exit 1
fi
echo "all 20 quarters present and verified." | tee -a "$LOG"
