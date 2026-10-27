# NPPAD cloud runner — pipeline

Trains **all 8 models for real** at the official Task E protocol
(t0 = 20 s, W = 60 s, realistic 88 channels, package split rule, seed 2026)
from the public dataset and writes the cloud outputs:

- `pred_E_W60_test.csv` — the new official file (8 blocks × 244 rows, `model` column)
- `pred_<Model>_W60_test.csv` — one sheet per model
- `results.json` — per-model macro-F1 / accuracy / validation macro-F1 / timings
- `status.json` — live run state for the Results Explorer's polling UI

## Files

- `nppad_data.py` — the study's data module (logic-identical to
  `adv_data.py` / the package starter notebook), adapted only so the data
  root comes from `NPPAD_DATA_ROOT` and no study-machine splits file is
  asserted. Split counts are verified in `train_all.py` (725/242/244).
- `deep_models.py` — CNN/GRU exactly as the package shipped them
  (`CNN1D`/`GRUNet`/`fit_net`, tuned HP from `best_hp.json`, seeds 0/1/2,
  probabilities averaged) plus the study's ConvTran implementation
  (seeds 0/1/2, averaged).
- `train_all.py` — orchestrator. LogReg / LogReg+ / Random Forest follow
  the shipped-sheet specs in `predictions_all_models.py`; MultiRocket+HYDRA
  and InceptionTime follow the study's aeon specs (incl. the zero-pad-to-12
  short-series fix). No saved probabilities are read anywhere — a model
  that cannot train (e.g. TensorFlow missing for InceptionTime) is recorded
  as failed in `results.json`/`status.json`, never substituted.
- `run.sh` — download → train → upload entry point (upload only when AWS
  credentials are present).
- `requirements.txt` — the study pins.

## Run locally

```bash
pip install -r requirements.txt
pip install torch==2.14.1+cpu --index-url https://download.pytorch.org/whl/cpu
./run.sh        # downloads the dataset from the public S3 URL itself
```

Verification anchors at this protocol (the t0 = 20 information ceiling):
macro-F1 ≈ 0.189182 per model, Random Forest 0.187691. A fresh cloud run
should land on or extremely near these values; `results.json` records the
anchor next to each measured value.
