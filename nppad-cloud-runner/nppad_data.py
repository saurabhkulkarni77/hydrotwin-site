"""NPPAD data module for the cloud runner.

Logic-identical to the study's shared data module
(~/workspace/nppad_advanced/adv_data.py, itself extracted verbatim from the
TaskE_NPPAD package starter notebook): same load_runs, split rule, windows,
ChannelScaler, LogHeavy and summary_features, so the cloud run evaluates on
exactly the package's data, splits and preprocessing.

Differences (cloud adaptation only, no pipeline change):
- DATA_ROOT comes from the NPPAD_DATA_ROOT environment variable (the GitHub
  Actions workflow points it at the extract of the public S3 dataset zip);
  a local default next to this file is used when the variable is unset.
- No assertion against the package's saved nppad_splits.json (that file is a
  study-machine artefact); the split rule itself is unchanged and the split
  counts are verified by train_all.py against the known 725/242/244.
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score


def _find_data_root():
    env = os.environ.get("NPPAD_DATA_ROOT")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    for cand in (here / "NuclearPowerPlantAccidentData" / "Operation_csv_data",
                 here / "data" / "NuclearPowerPlantAccidentData" / "Operation_csv_data",
                 Path("NuclearPowerPlantAccidentData/Operation_csv_data")):
        if cand.exists():
            return cand
    return here / "NuclearPowerPlantAccidentData" / "Operation_csv_data"


DATA_ROOT = _find_data_root()

SEED = 2026
CLASSES = ["LOCA", "LOCAC", "SLBIC", "SLBOC", "SGATR", "SGBTR",
           "RW", "RI", "FLB", "MD", "LR", "LLB"]
CLASS_TO_ID = {c: i for i, c in enumerate(CLASSES)}
ORACLE = ["WLR", "HLW", "WBK", "MBK", "EBK", "WTRA", "WTRB", "WFLB"]
T0 = 20.0
DT = 10.0
WINDOWS = [30, 60, 120, 300, 600]
N_CLASSES = len(CLASSES)
CLIP = 10.0


def load_runs(root=DATA_ROOT, classes=CLASSES):
    runs = []
    for c in classes:
        folder = root / c
        for f in sorted(folder.glob("*.csv")):
            try:
                sev = float(f.stem)
            except ValueError:
                continue
            d = pd.read_csv(f)
            d.columns = [str(col).strip() for col in d.columns]
            d = d.apply(pd.to_numeric, errors="coerce").sort_values("TIME").reset_index(drop=True)
            d = d.ffill().bfill().fillna(0.0)
            runs.append({"label": c, "severity": sev, "file": f"{c}/{f.name}", "df": d})
    return runs


RUNS = load_runs()
if not RUNS:
    raise RuntimeError(f"No NPPAD runs found under {DATA_ROOT} "
                       "(expected <CLASS>/<severity>.csv folders). "
                       "Set NPPAD_DATA_ROOT to the Operation_csv_data folder.")
VARS = sorted(set.intersection(*(set(r["df"].columns) for r in RUNS)) - {"TIME"})
VARS_REAL = [v for v in VARS if v not in ORACLE]

# --- split assignment: package rule (per class, severity-ranked) -----------
for c in CLASSES:
    cls = sorted((r for r in RUNS if r["label"] == c), key=lambda r: r["severity"])
    for k, r in enumerate(cls):
        r["split"] = "test" if k % 5 == 0 else ("val" if k % 5 == 1 else "train")

SPLIT_COUNTS = pd.Series([r["split"] for r in RUNS]).value_counts().to_dict()


def build_windows(split, W_s, cols, t0=T0):
    n_steps = int(round(W_s / DT))
    X, y, meta = [], [], []
    for r in RUNS:
        if r["split"] != split:
            continue
        d = r["df"]
        seg = d.loc[d["TIME"] >= t0 - 1e-6, cols].iloc[:n_steps]
        if len(seg) < n_steps:
            continue
        X.append(seg.to_numpy(np.float32))
        y.append(CLASS_TO_ID[r["label"]])
        meta.append((r["label"], r["severity"], r["file"]))
    return np.stack(X), np.array(y), pd.DataFrame(meta, columns=["label", "severity", "file"])


class ChannelScaler:
    def fit(self, X):
        self.mu = X.mean(axis=(0, 1))
        self.sd = X.std(axis=(0, 1))
        self.sd[self.sd < 1e-8] = 1.0
        return self

    def transform(self, X):
        return ((X - self.mu) / self.sd).astype(np.float32)


class LogHeavy:
    """Package LogReg+ / deep-model transform: log10(1 + x/s) on heavy-tailed
    non-negative channels, fitted on train windows only."""

    def fit(self, X, ratio=1e3):
        flat = X.reshape(-1, X.shape[-1]).astype(np.float64)
        lo, med, hi = flat.min(0), np.median(np.abs(flat), 0), np.abs(flat).max(0)
        self.idx = np.where((lo >= 0) & (hi > ratio * np.maximum(med, 1e-12)) & (hi > 0))[0]
        base = np.median(np.abs(X[:, 0, :]), 0)
        s = np.where(base[self.idx] > 0, base[self.idx], 1e-3 * hi[self.idx])
        self.s = np.maximum(s, 1e-9)
        return self

    def transform(self, X):
        X = X.copy()
        X[:, :, self.idx] = np.log10(1.0 + np.maximum(X[:, :, self.idx], 0) / self.s)
        return X.astype(np.float32)


def make_data(W, cols, t0=T0, log_heavy=True):
    """Train/val/test for one (W, cols, t0); all transforms fitted on train only.
    Returns raw windows, logged windows, and scaled windows under keys
    'tr'/'va'/'te' as (X_scaled, y, meta), exactly like the package's make_data."""
    Xtr, ytr, mtr = build_windows("train", W, cols, t0=t0)
    Xva, yva, mva = build_windows("val", W, cols, t0=t0)
    Xte, yte, mte = build_windows("test", W, cols, t0=t0)
    raw = (Xtr, Xva, Xte)
    lg = LogHeavy().fit(Xtr) if log_heavy else None
    pre = (lambda X: lg.transform(X)) if log_heavy else (lambda X: X)
    sc = ChannelScaler().fit(pre(Xtr))
    f = lambda X: np.clip(sc.transform(pre(X)), -CLIP, CLIP)
    return dict(W=W, cols=list(cols), t0=t0, raw=raw, logged=tuple(pre(X) for X in raw),
                ytr=ytr, yva=yva, yte=yte, mtr=mtr, mva=mva, mte=mte,
                tr=(f(Xtr), ytr, mtr), va=(f(Xva), yva, mva), te=(f(Xte), yte, mte),
                log=lg, scaler=sc)


def summary_features(X):
    """Package summary features: per-variable [last, mean, slope] -> (n, 3*C)."""
    t = np.arange(X.shape[1], dtype=np.float32)
    t = (t - t.mean())[None, :, None]
    xm = X.mean(axis=1, keepdims=True)
    slope = (t * (X - xm)).sum(axis=1) / max(float((t ** 2).sum()), 1e-8)
    return np.concatenate([X[:, -1, :], xm[:, 0, :], slope], axis=1)


def macro_f1(y, pred):
    return f1_score(y, pred, average="macro", labels=list(range(N_CLASSES)), zero_division=0)


def acc(y, pred):
    return accuracy_score(y, pred)
