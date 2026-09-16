# Model weights

`world_model_v1.pt` (603KB) and the `baseline_*.joblib` scaler/models are
committed directly (choice (a): final weights are well under ~100MB).

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
