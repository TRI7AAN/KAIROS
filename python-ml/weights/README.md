# Model weights

`world_model_v1.pt` (603KB), the `baseline_*.joblib` scaler/models, and
`shap_surrogate_v1.joblib` (~28MB ExtraTrees SHAP surrogate, R2 ~0.978) are
committed directly (final weights are well under ~100MB).
`world_model_phase32.pt` is intentionally NOT committed: it is only the
pre-Phase-38-finetune backup of `world_model_v1.pt`, reproducible at any time
by re-running `python-ml/training/run_phase36_38_stage_repair.py` against a
pre-finetune checkpoint (the finetuned checkpoint carries
`artifact_version kairos.world-model.v1.phase38-stage` plus the full
`phase38` training record, and `results/phase38_stage_finetune.json` holds
the before/after metrics). Likewise the Phase 32 loss-grid variant
checkpoints (`phase32_*_gnn.pt`, `phase32_flat_winning_loss.pt`) are NOT
committed: they are intermediate ablation artifacts, reproducible via
`python-ml/training/run_phase32_complete.py`, whose committed
`results/phase32_completed.json` records every variant's full training log,
evaluation, and the `winning_checkpoint_source` that was promoted to
`world_model_v1.pt`.

Reproduce from scratch:

1. Downsample the raw CIC-IDS2018 CSVs (seed 42):
   `python3 python-ml/pipeline/downsample_flows.py`
   (see `data/cic_ids_2018_manifest.yaml`, downsampling entry).
2. Export the 10-second graph contracts:
   `java -cp <classes> com.networkwm.graph.CicDatasetExporter <OUT.json> <IN.csv>`
   for each capped CSV into `data/processed/graph_contracts/`
   (`day14/day15/day28/day0302.json`).
3. Train: `python-ml/venv/bin/python python-ml/training/run_fix3_training.py`
   (settings in `python-ml/configs/train_config.yaml`; train on
   day14+day15+day28, validate on whole day0302).
4. Load-test: `python-ml/venv/bin/python
   python-ml/training/load_test_checkpoint.py`
5. Baseline: `PYTHONPATH=python-ml python-ml/venv/bin/python
   python-ml/baseline/run_baseline.py data/processed/graph_contracts/*.json`
