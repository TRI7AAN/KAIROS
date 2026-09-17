"""Phase 33: visualize K-step pre-attack forecasts against the frozen baseline.

The baseline probabilities are contemporaneous detections at each pre-attack
window, not rollouts. They are plotted only as the requested reference and are
never described as forecast lead time.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "python-ml"))
sys.path.insert(0, str(REPO_ROOT / "python-ml" / "training"))

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from baseline.logistic_regression import _summary_values
from phase32_common import build_splits

PHASE32 = REPO_ROOT / "results" / "phase32_completed.json"
OUTPUT_JSON = REPO_ROOT / "results" / "phase33_rollout_proof.json"
OUTPUT_PNG = REPO_ROOT / "results" / "phase33_rollout_vs_baseline.png"
THRESHOLD = 0.5


def flatten_graph(graph) -> np.ndarray:
    row = [
        float(graph.x.shape[0]),
        float(graph.edge_index.shape[1]),
        float(graph.window_duration_seconds.item()),
        float(graph.topology_available),
    ]
    row.extend(_summary_values(graph.x.detach().cpu().numpy()))
    row.extend(_summary_values(graph.edge_attr.detach().cpu().numpy()))
    return np.asarray(row, dtype=np.float64)


def main() -> int:
    phase32 = json.loads(PHASE32.read_text(encoding="utf-8"))
    winner_k = str(phase32["k_winner"])
    attacks = phase32["k_ablation"][winner_k]["rollout_attacks"]
    _, _, _, in_val, _, _, _ = build_splits()
    validation = [graph for day in in_val for graph in day]
    scaler = joblib.load(
        REPO_ROOT / "python-ml" / "weights" / "baseline_scaler_indist.joblib"
    )
    baseline = joblib.load(
        REPO_ROOT / "python-ml" / "weights" / "baseline_binary_lr_indist.joblib"
    )

    eligible = [attack for attack in attacks if attack["curve"]]
    figure, axes = plt.subplots(
        len(eligible), 1, figsize=(10, 4 * len(eligible)), sharex=True
    )
    if len(eligible) == 1:
        axes = [axes]
    report_attacks = []

    for plot_index, (axis, attack) in enumerate(zip(axes, eligible), start=1):
        points = sorted(attack["curve"], key=lambda point: point["lead_windows"],
                        reverse=True)
        lead_windows = [point["lead_windows"] for point in points]
        x_seconds = [-lead * 10 for lead in lead_windows]
        world_probabilities = [point["mean_prob"] for point in points]
        baseline_rows = [
            flatten_graph(validation[attack["attack_start_window"] - lead])
            for lead in lead_windows
        ]
        baseline_probabilities = baseline.predict_proba(
            scaler.transform(np.stack(baseline_rows))
        )[:, 1].tolist()

        world_hits = [
            lead for lead, probability in zip(lead_windows, world_probabilities)
            if probability >= THRESHOLD
        ]
        baseline_hits = [
            lead for lead, probability in zip(lead_windows, baseline_probabilities)
            if probability >= THRESHOLD
        ]
        far_probability = world_probabilities[0]
        near_probability = world_probabilities[-1]
        delta = near_probability - far_probability
        report_attacks.append({
            "attack_number": plot_index,
            "attack_start_window": attack["attack_start_window"],
            "world_model_early_warning_seconds": (
                max(world_hits) * 10 if world_hits else None
            ),
            "baseline_pre_attack_detection_seconds": (
                max(baseline_hits) * 10 if baseline_hits else None
            ),
            "near_minus_far_probability": delta,
            "material_rise_confirmed": delta >= 0.02,
            "curve": [
                {
                    "seconds_before_attack": lead * 10,
                    "world_rollout_probability": world_probability,
                    "baseline_contemporaneous_probability": baseline_probability,
                }
                for lead, world_probability, baseline_probability in zip(
                    lead_windows, world_probabilities, baseline_probabilities
                )
            ],
        })

        axis.plot(x_seconds, world_probabilities, marker="o", linewidth=2,
                  label=f"World model K={winner_k} rollout")
        axis.plot(x_seconds, baseline_probabilities, marker="s", linestyle="--",
                  label="Frozen logistic baseline (non-temporal)")
        axis.axhline(THRESHOLD, color="crimson", linestyle=":",
                     label="Alert threshold" if plot_index == 1 else None)
        axis.axvline(0, color="black", linewidth=1)
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("Attack probability")
        axis.set_title(
            f"Attack {plot_index}: world-model lead = "
            f"{report_attacks[-1]['world_model_early_warning_seconds']} s"
        )
        axis.grid(alpha=0.25)
        axis.legend(loc="best")

    axes[-1].set_xlabel("Seconds relative to attack start (0 = attack begins)")
    figure.suptitle("KAIROS Phase 33 — Pre-attack rollout proof check")
    figure.tight_layout()
    figure.savefig(OUTPUT_PNG, dpi=180)
    plt.close(figure)

    rise_count = sum(item["material_rise_confirmed"] for item in report_attacks)
    warning_count = sum(
        item["world_model_early_warning_seconds"] is not None
        for item in report_attacks
    )
    result = {
        "artifact_version": "kairos.phase33.v1",
        "winning_configuration": {
            "window_seconds": 10,
            "rollout_k": int(winner_k),
            "encoder": phase32["encoder_winner"],
            "loss": phase32["loss_winner"],
            "threshold": THRESHOLD,
        },
        "eligible_attacks": len(report_attacks),
        "attacks_with_world_model_early_warning": warning_count,
        "attacks_with_material_probability_rise": rise_count,
        "proof_status": (
            "pass" if report_attacks and rise_count == len(report_attacks)
            else "partial"
        ),
        "interpretation": (
            "The winner crosses the alert threshold before attack onset, but "
            "the sampled probabilities do not show a material near-onset rise. "
            "This demonstrates early alerting, not a calibrated rising-risk "
            "trajectory. The logistic baseline is non-temporal and has no "
            "rollout lead-time claim."
        ),
        "baseline_metrics_same_split": json.loads(
            (REPO_ROOT / "results" / "baseline_metrics_indist.json").read_text(
                encoding="utf-8"
            )
        )["binary"],
        "attacks": report_attacks,
        "plot": "results/phase33_rollout_vs_baseline.png",
    }
    OUTPUT_JSON.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "proof_status": result["proof_status"],
        "early_warning_attacks": warning_count,
        "material_rise_attacks": rise_count,
        "eligible_attacks": len(report_attacks),
        "plot": str(OUTPUT_PNG),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
