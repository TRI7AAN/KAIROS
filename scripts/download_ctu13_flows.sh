#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

download_verified() {
  local url="$1"
  local output="$2"
  local bytes="$3"
  local sha256="$4"
  mkdir -p "$(dirname "$output")"
  if [[ ! -f "$output" || "$(stat -c %s "$output")" -ne "$bytes" ]]; then
    curl --fail --location --retry 4 --continue-at - --output "$output" "$url"
  fi
  test "$(stat -c %s "$output")" -eq "$bytes"
  echo "$sha256  $output" | sha256sum -c -
}

download_verified   "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-47/detailed-bidirectional-flow-labels/capture20110816.binetflow"   "data/raw/ctu13_scenario6/capture20110816.binetflow"   76780048   "801800eeda9a5a44868b1e3e492f93dc6d52b5d14566c1d8431c9e85d0d2adaa"

download_verified   "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-52/detailed-bidirectional-flow-labels/capture20110818-2.binetflow"   "data/raw/ctu13_scenario11/capture20110818-2.binetflow"   14596615   "cee542d4b5efe4fa1cd59b87ece5aaea9a13d8f0abe56cd07cee31590736428c"

download_verified \
  "https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-53/detailed-bidirectional-flow-labels/capture20110819.binetflow" \
  "data/raw/ctu13_scenario12/capture20110819.binetflow" \
  44718958 \
  "1098f0addacedc321c7baefad63ef0d9a0f26630d0155087d37e8da770dd9f2e"
