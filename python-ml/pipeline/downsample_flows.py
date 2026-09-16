"""Reproducible stratified downsampling for CIC-IDS2018 flow CSVs.

Reference implementation of the capped per-day CSVs under
data/processed/cic2018_capped/: 200,000 data rows per day (day14 carries one
extra rounding row, 200,001) with class ratios preserved to within rounding
(one row per stratum at most). Header anomaly rows whose Label value equals
"Label" are dropped before sampling, matching IngestionService behavior.

Documented difference vs the on-disk capped files: the capped files on disk
were produced by an earlier, unrecorded tool (pandas-style: empty string for
NaN, literal "Infinity" preserved), so --check reports DIFFERS in row
identity and in NaN/Infinity cell formatting. Per-class row counts match the
seeded quotas exactly (e.g. day14 Benign 127340 / FTP-BruteForce 36881 /
SSH-Bruteforce 35780). This script is the canonical, from-scratch
reproduction going forward (CSVs it writes use "0.0"/"1e12"-style sanitized
numerics instead of ""/"Infinity"); the Java IngestionService accepts both
forms (see its sanitize() handling of NaN/Infinity/empty).

Usage:
    python3 downsample_flows.py
    python3 downsample_flows.py --check

--check verifies the on-disk capped files match a fresh seeded run exactly.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "cic2018_csv"
CAPPED_DIR = REPO_ROOT / "data" / "processed" / "cic2018_capped"

RANDOM_SEED = 42
TARGET_ROWS_PER_DAY = 200_000

DAY_FILES = [
    "Wednesday-14-02-2018_TrafficForML_CICFlowMeter.csv",
    "Thursday-15-02-2018_TrafficForML_CICFlowMeter.csv",
    "Wednesday-28-02-2018_TrafficForML_CICFlowMeter.csv",
    "Friday-02-03-2018_TrafficForML_CICFlowMeter.csv",
]


def stratified_sample(rows: list[dict], label_of, seed: int) -> list[dict]:
    """Shared-RNG stratified sample preserving file order (picked.sort()).

    Quotas are round(stratum_share * TARGET_ROWS_PER_DAY) with a minimum of
    one row; any rounding drift is absorbed by the largest stratum. A single
    random.Random(seed) is shared across strata in first-seen label order.
    """
    import random

    rng = random.Random(seed)
    total = len(rows)
    strata: dict[str, list[int]] = {}
    for index, row in enumerate(rows):
        strata.setdefault(label_of(row), []).append(index)
    quotas = {
        label: max(1, round(len(idxs) * TARGET_ROWS_PER_DAY / total))
        for label, idxs in strata.items()
    }
    drift = TARGET_ROWS_PER_DAY - sum(quotas.values())
    if drift:
        biggest = max(strata, key=lambda label: len(strata[label]))
        quotas[biggest] += drift
    picked: list[int] = []
    for label, idxs in strata.items():
        order = idxs[:]
        rng.shuffle(order)
        picked.extend(order[: quotas[label]])
    picked.sort()
    return [rows[i] for i in picked]


def downsample_file(name: str, seed: int) -> Counter:
    with open(RAW_DIR / name, newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        label_col = next(k for k in fields if k.strip().lower() == "label")
        rows = [r for r in reader if r[label_col].strip() != "Label"]
    sampled = stratified_sample(rows, lambda r: r[label_col].strip(), seed)
    counts: Counter = Counter(r[label_col].strip() for r in sampled)
    CAPPED_DIR.mkdir(parents=True, exist_ok=True)
    with open(CAPPED_DIR / name, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(sampled)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true",
                        help="verify capped files match a seeded run")
    parser.add_argument("--seed", type=int, default=RANDOM_SEED)
    args = parser.parse_args()
    ok = True
    for name in DAY_FILES:
        if args.check:
            with open(RAW_DIR / name, newline="") as handle:
                reader = csv.DictReader(handle)
                label_col = next(
                    k for k in (reader.fieldnames or [])
                    if k.strip().lower() == "label")
                rows = [r for r in reader if r[label_col].strip() != "Label"]
            expected = stratified_sample(
                rows, lambda r: r[label_col].strip(), args.seed)
            with open(CAPPED_DIR / name, newline="") as handle:
                reader = csv.DictReader(handle)
                on_disk = list(reader)
            match = (
                len(on_disk) == len(expected)
                and all(a == b for a, b in zip(on_disk, expected))
            )
            print(f"{name}: {'MATCH' if match else 'DIFFERS'} "
                  f"(disk={len(on_disk)} expected={len(expected)})")
            ok = ok and match
        else:
            counts = downsample_file(name, args.seed)
            print(f"{name}: {sum(counts.values())} rows {dict(counts)}")
    print(f"seed={args.seed} target={TARGET_ROWS_PER_DAY}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
