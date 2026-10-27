#!/usr/bin/env python3
"""NPPAD cloud runner — train all 8 models at the official Task E protocol
and write the cloud outputs.

Protocol (identical to the shipped official file pred_E_S1test.csv):
t0 = 20 s, W = 60 s, realistic 88 channels (8 oracle removed), package split
rule (seed 2026; 725 train / 242 val / 244 test).

REAL training for every model — no saved probabilities are read:
  LogReg            StandardScaler + LogisticRegression(max_iter=5000, C=1.0)
                    on RAW summary features (study fit_logreg, inputs="raw").
  LogReg+           same pipeline on LOGGED (LogHeavy) summary features; C
                    chosen on validation macro-F1 over (1, 10, 100, 1000),
                    first-best wins ties (package convention).
  Random Forest     RandomForestClassifier(n_estimators=400, random_state=2026,
                    class_weight="balanced_subsample") on RAW summary features
                    (the shipped-sheet spec in predictions_all_models.py).
  CNN / GRU         package CNN1D / GRUNet + fit_net with the tuned
                    hyperparameters (best_hp.json), seeds 0/1/2, probabilities
                    averaged (deep_models.py).
  MultiRocket+HYDRA aeon MultiRocketHydraClassifier(random_state=2026) on the
                    scaled windows, with the study's short-series fix
                    (zero-pad scaled windows to length 12, channel-major).
  ConvTran          study implementation (deep_models.py), seeds 0/1/2,
                    probabilities averaged.
  InceptionTime     aeon InceptionTimeClassifier(n_epochs=100, batch_size=64,
                    random_state=2026) — needs the TensorFlow environment;
                    if TensorFlow is unavailable the model is recorded as
                    failed in results.json/status.json, never faked.

Outputs (in --out, default ./outputs):
  pred_E_S1test.csv   the new official file: 8 blocks x 244 rows in canonical
                      order, columns model,label,severity,file,y_pred,p_<12>
  pred_<Model>_W60_test.csv   one sheet per model (same format)
  results.json        per-model macro-F1 / accuracy / val macro-F1 / seconds /
                      source note, plus run metadata and split counts
  status.json         {state: running|done|failed, stage, updated_utc, ...}
                      rewritten at every stage so the app can poll it

Usage:
  NPPAD_DATA_ROOT=<Operation_csv_data folder> python train_all.py [--out DIR]
                      [--models LogReg,GRU,...]
Data download/extract is the caller's job (see run.sh / the workflow).
"""
import argparse
import json
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nppad_data as D

W, T0 = 60, 20.0
CLASSES = D.CLASSES
DISPLAY = {"LogReg": "LogReg", "LogRegPlus": "LogReg+", "RandomForest": "Random Forest",
           "CNN": "CNN", "GRU": "GRU", "MultiRocketHydra": "MultiRocket+HYDRA",
           "ConvTran": "ConvTran", "InceptionTime": "InceptionTime"}
COMBINED_ORDER = ["LogReg", "LogRegPlus", "RandomForest", "CNN", "GRU",
                  "MultiRocketHydra", "ConvTran", "InceptionTime"]
# Verification anchors: the shipped sheets at this protocol (t0=20 ceiling).
ANCHORS = {m: 0.189182 for m in COMBINED_ORDER}
ANCHORS["RandomForest"] = 0.187691


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Status:
    def __init__(self, out_dir):
        self.path = out_dir / "status.json"
        self.data = {"state": "running", "stage": "starting", "updated_utc": utcnow(),
                     "protocol": {"t0": T0, "W": W, "vars": "realistic", "seed": D.SEED},
                     "models_done": [], "models_failed": []}

    def write(self, **kw):
        self.data.update(kw)
        self.data["updated_utc"] = utcnow()
        self.path.write_text(json.dumps(self.data, indent=1))


def write_sheet(out_dir, model, meta, proba):
    proba = np.asarray(proba, dtype=np.float64)
    assert proba.shape == (len(meta), len(CLASSES)), (model, proba.shape)
    df = meta.copy()
    df.insert(0, "model", DISPLAY[model])
    df["y_pred"] = [CLASSES[i] for i in proba.argmax(1)]
    for j, c in enumerate(CLASSES):
        df[f"p_{c}"] = proba[:, j]
    cols = ["model", "label", "severity", "file", "y_pred"] + [f"p_{c}" for c in CLASSES]
    path = out_dir / f"pred_{model}_W60_test.csv"
    df[cols].to_csv(path, index=False)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--models", default=None, help="comma list; default = all 8")
    args = ap.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    want = args.models.split(",") if args.models else list(COMBINED_ORDER)

    status = Status(out_dir)
    status.write(stage="loading data")
    run_t0 = time.time()
    results = {"protocol": {"t0": T0, "W": W, "vars": "realistic", "n_channels": len(D.VARS_REAL),
                            "seed": D.SEED},
               "splits": {k: int(v) for k, v in D.SPLIT_COUNTS.items()},
               "data_root": str(D.DATA_ROOT), "started_utc": utcnow(), "models": {}}
    print("split counts:", results["splits"], flush=True)
    assert results["splits"] == {"train": 725, "val": 242, "test": 244}, results["splits"]

    status.write(stage="building windows")
    d = D.make_data(W, D.VARS_REAL, t0=T0)
    meta = d["mte"].reset_index(drop=True)
    yte, yva = d["yte"], d["yva"]
    assert len(meta) == 244
    (Xtr_s, ytr, _), (Xva_s, _, _), (Xte_s, _, _) = d["tr"], d["va"], d["te"]
    Xtr_r, Xva_r, Xte_r = d["raw"]
    Xtr_l, Xva_l, Xte_l = d["logged"]

    def record(model, proba, seconds, source, val_f1=None):
        pred = proba.argmax(1)
        row = {"model": DISPLAY[model], "macro_F1": float(D.macro_f1(yte, pred)),
               "accuracy": float(D.acc(yte, pred)),
               "val_macro_F1": (None if val_f1 is None else float(val_f1)),
               "n_test": int(len(yte)), "seconds": float(seconds), "source": source,
               "anchor_macro_F1": ANCHORS[model]}
        results["models"][model] = row
        write_sheet(out_dir, model, meta, proba)
        print(f"{model}: macro-F1 {row['macro_F1']:.6f} acc {row['accuracy']:.6f} "
              f"(anchor {ANCHORS[model]:.6f}) [{source}]", flush=True)
        status.data["models_done"] = [m for m in COMBINED_ORDER if m in results["models"]]
        status.write(stage=f"trained {model}", results_so_far=results["models"])
        return row

    def attempt(model, fn):
        if model not in want:
            return
        status.write(stage=f"training {model}")
        t = time.time()
        try:
            proba, val_f1, source = fn()
            record(model, proba, time.time() - t, source, val_f1)
        except Exception as e:  # recorded honestly; never substitute saved probs
            results["models"][model] = {"model": DISPLAY[model], "error": f"{type(e).__name__}: {e}"}
            status.data["models_failed"] = [m for m in results["models"]
                                            if "error" in results["models"][m]]
            status.write(stage=f"training {model}", results_so_far=results["models"])
            print(f"{model} FAILED: {e}", flush=True)
            traceback.print_exc()

    # ---- classical: LogReg / LogReg+ / Random Forest ----------------------
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    def logreg_proba(clf, X_raw):
        p = np.zeros((len(X_raw), D.N_CLASSES))
        p[:, clf.classes_] = clf.predict_proba(D.summary_features(X_raw))
        return p

    def do_logreg():
        clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, C=1.0))
        clf.fit(D.summary_features(Xtr_r), ytr)
        return logreg_proba(clf, Xte_r), None, "retrained (raw summary features, C=1.0)"

    def do_logregplus():
        best = None
        for C in (1.0, 10.0, 100.0, 1000.0):
            clf = make_pipeline(StandardScaler(), LogisticRegression(max_iter=5000, C=C))
            clf.fit(D.summary_features(Xtr_l), ytr)
            vf1 = float(D.macro_f1(yva, logreg_proba(clf, Xva_l).argmax(1)))
            if best is None or vf1 > best[0]:
                best = (vf1, C, clf)
        vf1, C, clf = best
        return logreg_proba(clf, Xte_l), vf1, f"retrained (logged summary features, C={C:g} by val)"

    def do_rf():
        Ftr, Fte = D.summary_features(Xtr_r), D.summary_features(Xte_r)
        rf = RandomForestClassifier(n_estimators=400, n_jobs=2, random_state=D.SEED,
                                    class_weight="balanced_subsample")
        rf.fit(Ftr, ytr)
        p = np.zeros((len(Xte_r), D.N_CLASSES))
        p[:, rf.classes_] = rf.predict_proba(Fte)
        return p, None, "retrained (raw summary features, 400 trees)"

    attempt("LogReg", do_logreg)
    attempt("LogRegPlus", do_logregplus)
    attempt("RandomForest", do_rf)

    # ---- deep: CNN / GRU / ConvTran (lazy import: a missing torch must be
    # recorded as those models' failure, not crash the whole run) ----------
    def do_cnn():
        import deep_models
        p, vf1 = deep_models.train_cnn_gru("CNN", d)
        return p, vf1, "retrained (package CNN1D, tuned HP, seeds 0/1/2 mean)"

    def do_gru():
        import deep_models
        p, vf1 = deep_models.train_cnn_gru("GRU", d)
        return p, vf1, "retrained (package GRUNet, tuned HP, seeds 0/1/2 mean)"

    def do_convtran():
        import deep_models
        p, vf1 = deep_models.train_convtran_ensemble(d)
        return p, vf1, "retrained (study ConvTran, seeds 0/1/2 mean)"

    attempt("CNN", do_cnn)
    attempt("GRU", do_gru)
    attempt("ConvTran", do_convtran)

    # ---- advanced: MultiRocket+HYDRA / InceptionTime ----------------------
    def pad12(X):
        T = X.shape[1]
        return X if T >= 12 else np.pad(X, ((0, 0), (0, 12 - T), (0, 0)))

    def do_rocket():
        from aeon.classification.convolution_based import MultiRocketHydraClassifier
        to_aeon = lambda X: np.ascontiguousarray(pad12(X).transpose(0, 2, 1))
        clf = MultiRocketHydraClassifier(random_state=2026)
        clf.fit(to_aeon(Xtr_s), ytr)
        return clf.predict_proba(to_aeon(Xte_s)), None, \
            "retrained (aeon MultiRocketHydraClassifier, scaled windows zero-padded to 12)"

    def do_inception():
        import tensorflow  # noqa: F401  (hard requirement; absence = honest failure)
        from aeon.classification.deep_learning import InceptionTimeClassifier
        to_aeon = lambda X: np.ascontiguousarray(X.transpose(0, 2, 1))
        clf = InceptionTimeClassifier(n_epochs=100, batch_size=64, random_state=2026, verbose=False)
        clf.fit(to_aeon(Xtr_s), ytr)
        return clf.predict_proba(to_aeon(Xte_s)), None, \
            "retrained (aeon InceptionTimeClassifier, 100 epochs)"

    attempt("MultiRocketHydra", do_rocket)
    attempt("InceptionTime", do_inception)

    # ---- stack the official file ------------------------------------------
    status.write(stage="stacking official file")
    frames, missing = [], []
    for model in COMBINED_ORDER:
        sheet = out_dir / f"pred_{model}_W60_test.csv"
        if sheet.exists():
            frames.append(pd.read_csv(sheet))
        else:
            missing.append(model)
    combined_path = None
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined_path = out_dir / "pred_E_S1test.csv"
        combined.to_csv(combined_path, index=False)
        print(f"combined: {len(combined)} rows from {len(frames)} models -> {combined_path}", flush=True)

    results["finished_utc"] = utcnow()
    results["seconds_total"] = float(time.time() - run_t0)
    results["official_file"] = (str(combined_path) if combined_path else None)
    results["official_rows"] = (int(len(frames) * 244) if frames else 0)
    results["missing_models"] = missing
    (out_dir / "results.json").write_text(json.dumps(results, indent=1))

    failed = [m for m in results["models"] if "error" in results["models"][m]]
    state = "done" if not failed and not missing else "failed"
    status.write(state=state, stage="done" if state == "done" else "finished with failures",
                 results=results["models"], official_file="pred_E_S1test.csv",
                 official_rows=results["official_rows"])
    print(json.dumps({"state": state, "failed": failed, "missing": missing,
                      "official_rows": results["official_rows"]}, indent=1))
    return 0 if state == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
