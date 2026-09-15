#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/.." && pwd)"
output_dir="${repo_dir}/data/raw"
base_url="https://cse-cic-ids2018.s3.amazonaws.com/Processed%20Traffic%20Data%20for%20ML%20Algorithms"

mkdir -p "${output_dir}"

download_and_verify() {
    local filename="$1"
    local expected_bytes="$2"
    local expected_sha256="$3"
    local destination="${output_dir}/${filename}"

    if [[ -f "${destination}" ]]; then
        local actual_bytes
        actual_bytes="$(stat -c %s "${destination}")"

        if [[ "${actual_bytes}" -gt "${expected_bytes}" ]]; then
            echo "Refusing to resume oversized file: ${destination}" >&2
            return 1
        fi

        if [[ "${actual_bytes}" -eq "${expected_bytes}" ]]; then
            if echo "${expected_sha256}  ${destination}" | sha256sum -c -; then
                return 0
            fi
            echo "Checksum mismatch for complete file: ${destination}" >&2
            return 1
        fi
    fi

    curl --fail --location --retry 3 --continue-at - \
        "${base_url}/${filename}" \
        --output "${destination}"

    test "$(stat -c %s "${destination}")" -eq "${expected_bytes}"
    echo "${expected_sha256}  ${destination}" | sha256sum -c -
}

download_and_verify \
    "Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv" \
    358223333 acff8bc61376ee031d80878ee6099e0b1a87a1bd711d8068298421418c9f8147
download_and_verify \
    "Thursday-15-02-2018_TrafficForML_CICFlowMeter.csv" \
    375945899 fa2947a8256d81ee9103ae16139d62d0e17aa23e696ee80d9e76fb51c01c9c4b
download_and_verify \
    "Wednesday-28-02-2018_TrafficForML_CICFlowMeter.csv" \
    209249758 f15e2a12304446058a0186c8ad67de2bd15735a9ba5c70c9a1f4c4242ab06771
download_and_verify \
    "Friday-02-03-2018_TrafficForML_CICFlowMeter.csv" \
    352368373 d96f38e7496aba83475031e6fb8c6fdf1abf6aa1b71325a917798f3c7de93de1
