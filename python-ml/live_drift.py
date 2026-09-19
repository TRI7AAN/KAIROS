"""Phase 72: live-window drift/quality guard for the KAIROS world model.

The SAME trained model serves live sequence windows with no architecture
fork: live windows validate against kairos.sequence.v1 and flow through the
existing PredictionService.predict path. This module adds the quality signal
that travels alongside every live prediction.

Quality rule (calibrated on 400 real day0302 windows against a 1,323-window
every-10th training sample; see results/live_drift_calibration.json):

- Per-feature z-scores against the training reference
  (results/live_drift_reference.npz: means/stds over 1,284 graph features).
- degraded:  max|z| > 12  OR  fraction of features with |z| > 5 exceeds 2%.
- unreliable: max|z| > 20 OR  fraction of features with |z| > 5 exceeds 5%.
- otherwise ok. Missing/NaN/Inf fields force unreliable immediately.

The thresholds sit well above the in-distribution envelope (400-window
p99 max|z| = 8.38, p95 frac|z|>5 = 0.0023) and far below a genuine
distribution shift (synthetic 25-sigma shift on 40 features:
max|z| = 25.0, frac|z|>5 = 0.031), so real attacks keep `ok` while
synthetic/extreme shifts trip the guard. The guard is reactive arithmetic,
not a hardcoded verdict: quality is computed from the incoming window.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import math

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = (
    REPO_ROOT / "results" / "live_drift_reference.npz"
)

DEGRADED_MAX_Z = 12.0
DEGRADED_FRAC_Z5 = 0.02
UNRELIABLE_MAX_Z = 20.0
UNRELIABLE_FRAC_Z5 = 0.05


@dataclass(frozen=True)
class QualityReport:
    quality: str
    max_abs_z: float
    mean_abs_z: float
    frac_z_gt_5: float
    frac_z_gt_3: float
    checked_features: int


_REFERENCE_CACHE: dict[str, dict] = {}


def load_reference(
    reference_path: str | Path = DEFAULT_REFERENCE,
) -> dict:
    key = str(reference_path)
    if key not in _REFERENCE_CACHE:
        payload = np.load(Path(reference_path), allow_pickle=False)
        _REFERENCE_CACHE[key] = {
            "means": np.asarray(payload["means"], dtype=np.float64),
            "stds": np.asarray(payload["stds"], dtype=np.float64),
            "names": list(payload["names"]),
        }
    return _REFERENCE_CACHE[key]


def assess_quality(
    row: np.ndarray,
    reference_path: str | Path = DEFAULT_REFERENCE,
) -> QualityReport:
    reference = load_reference(reference_path)
    means = reference["means"]
    stds = reference["stds"]
    values = np.asarray(row, dtype=np.float64).reshape(-1)
    if values.shape[0] != means.shape[0]:
        return QualityReport(
            quality="unreliable",
            max_abs_z=float("inf"),
            mean_abs_z=float("inf"),
            frac_z_gt_5=1.0,
            frac_z_gt_3=1.0,
            checked_features=int(values.shape[0]),
        )
    if not np.all(np.isfinite(values)):
        return QualityReport(
            quality="unreliable",
            max_abs_z=float("inf"),
            mean_abs_z=float("inf"),
            frac_z_gt_5=1.0,
            frac_z_gt_3=1.0,
            checked_features=int(values.shape[0]),
        )
    scale = np.maximum(stds, 1e-9)
    z = np.abs(values - means) / scale
    max_z = float(z.max())
    mean_z = float(z.mean())
    frac5 = float((z > 5).mean())
    frac3 = float((z > 3).mean())
    if not (
        math.isfinite(max_z) and math.isfinite(mean_z)
    ):
        quality = "unreliable"
    elif max_z > UNRELIABLE_MAX_Z or frac5 > UNRELIABLE_FRAC_Z5:
        quality = "unreliable"
    elif max_z > DEGRADED_MAX_Z or frac5 > DEGRADED_FRAC_Z5:
        quality = "degraded"
    else:
        quality = "ok"
    return QualityReport(
        quality=quality,
        max_abs_z=max_z,
        mean_abs_z=mean_z,
        frac_z_gt_5=frac5,
        frac_z_gt_3=frac3,
        checked_features=int(values.shape[0]),
    )
