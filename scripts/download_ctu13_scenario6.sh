#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "${script_dir}/.." && pwd)"
output_dir="${repo_dir}/data/raw/ctu13_pcap/scenario06_donbot"
archive="${output_dir}/capture20110816.truncated.pcap.bz2"
extracted="${output_dir}/capture20110816.truncated.pcap"
url="https://mcfp.felk.cvut.cz/publicDatasets/CTU-Malware-Capture-Botnet-47/capture20110816.truncated.pcap.bz2"
archive_bytes=602748112
archive_sha256="3a32c85783a773867c96f2988701b81b267cda4648bf174890f4bbd43c518be5"
extracted_bytes=3284726956
extracted_sha256="19ea13096693f4d81acd36fd24897084f3ef702f9b4fa96ee7bd785209f9e7af"

mkdir -p "${output_dir}"

if [[ ! -f "${archive}" || "$(stat -c %s "${archive}")" -ne "${archive_bytes}" ]]; then
    curl --fail --location --retry 4 --continue-at - \
        --output "${archive}" "${url}"
fi

test "$(stat -c %s "${archive}")" -eq "${archive_bytes}"
echo "${archive_sha256}  ${archive}" | sha256sum -c -

if [[ ! -f "${extracted}" ]]; then
    bzip2 --decompress --keep "${archive}"
fi

test "$(stat -c %s "${extracted}")" -eq "${extracted_bytes}"
echo "${extracted_sha256}  ${extracted}" | sha256sum -c -
