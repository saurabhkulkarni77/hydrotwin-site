"""NPPAD-Edge on AWS Lambda — public demo endpoint.

Wraps the NPPAD-Edge pure-NumPy runtime (MultiRocket+HYDRA accident
classifier for the NPPAD nuclear-plant dataset, packaged for
space-like limited-compute conditions) behind a Lambda Function URL.

Cold start: the uplink bundle is SHA-256-verified against its
manifest (nppad_edge.bundle.load_bundle -> verify_bundle) before any
model is loaded — a corrupted bundle is refused, exactly as on the
edge payload. The in-memory weight digest recorded at load is
re-checked on every demo call (the payload's memory checker).

API (Function URL, payload format 2.0):
  GET  /                              -> self-test / demo (see below)
  POST {"demo": true}                 -> self-test / demo
  POST {"demo": true, "demo_windows": K}  -> demo over K windows (1..240)
  POST {"sample_index": N}            -> classify packaged test window N
                                         (0..239, W=60 s, 88 channels)
  POST {"window": [[...], ...]}       -> classify a raw window:
                                         6 rows x 88 cols  -> W=60 model
                                         12 rows x 88 cols -> W=120 model

Demo returns: bundle integrity result, live macro-F1 / accuracy /
latency on a strided subset of the 240 packaged test windows, peak
RSS, and the full-test-set figures recorded in the bundle's model
card at packaging time.
"""
from __future__ import annotations

import base64
import json
import os
import resource
import time

# Single-threaded, like the edge payload's compute budget.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np

from nppad_edge.bundle import load_bundle, read_manifest
from nppad_edge.data import CLASSES

BASE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_DIR = os.path.join(BASE, "bundle")
DEMO_NPZ = os.path.join(BASE, "demo_data", "test_windows_w60.npz")
DEFAULT_DEMO_WINDOWS = 60

_STATE: dict = {}


def _init() -> dict:
    """Cold start: verify (SHA-256) + load the bundle, load demo data."""
    if _STATE:
        return _STATE
    t0 = time.time()
    # load_bundle(verify=True) runs verify_bundle(): every bundle file's
    # SHA-256 must match manifest.json or IntegrityError is raised.
    primary60, fallback60 = load_bundle(BUNDLE_DIR, 60, verify=True)
    primary120, _ = load_bundle(BUNDLE_DIR, 120, verify=True)
    manifest = read_manifest(BUNDLE_DIR)
    z = np.load(DEMO_NPZ)
    demo_X, demo_y = z["X"], z["y"]
    card = json.loads(open(os.path.join(BUNDLE_DIR, "model_card.json")).read())
    _STATE.update(
        primary60=primary60, fallback60=fallback60, primary120=primary120,
        manifest=manifest, demo_X=demo_X, demo_y=demo_y, card=card,
        cold_start_s=round(time.time() - t0, 3),
        bundle_bytes=sum(rec["bytes"] for rec in manifest["files"].values()),
    )
    return _STATE


def _scores(model, window) -> tuple[dict, float]:
    t0 = time.time()
    p = model.predict_proba(np.asarray(window, dtype=np.float32))
    ms = (time.time() - t0) * 1000.0
    return {c: round(float(v), 6) for c, v in zip(model.classes, p)}, ms


def _classify(model, window, extra: dict) -> dict:
    scores, ms = _scores(model, window)
    pred = max(scores, key=scores.get)
    out = {
        "predicted_class": pred,
        "confidence": scores[pred],
        "scores": scores,
        "latency_ms": round(ms, 2),
        "model": model.name,
    }
    out.update(extra)
    return out


def _macro_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    f1s = []
    for c in range(len(CLASSES)):
        tp = int(((y_pred == c) & (y_true == c)).sum())
        fp = int(((y_pred == c) & (y_true != c)).sum())
        fn = int(((y_pred != c) & (y_true == c)).sum())
        pr = tp / (tp + fp) if tp + fp else 0.0
        rc = tp / (tp + fn) if tp + fn else 0.0
        f1s.append(2 * pr * rc / (pr + rc) if pr + rc else 0.0)
    return float(np.mean(f1s))


def _demo(n_windows: int) -> dict:
    st = _init()
    X, y = st["demo_X"], st["demo_y"]
    n_windows = max(1, min(int(n_windows), len(y)))
    stride = max(1, len(y) // n_windows)
    idx = list(range(0, len(y), stride))[:n_windows]
    model = st["primary60"]
    preds, lat = [], []
    for i in idx:
        scores, ms = _scores(model, X[i])
        preds.append(CLASSES.index(max(scores, key=scores.get)))
        lat.append(ms)
    preds = np.array(preds)
    lat = np.array(lat)
    w60 = st["card"]["metrics"]["W60"]
    return {
        "service": "nppad-edge",
        "description": "NPPAD accident classifier (MultiRocket+HYDRA, pure "
                       "NumPy) running on AWS Lambda free tier — the "
                       "space-edge deployment demo.",
        "integrity": {
            "bundle_sha256_verified": True,
            "files_checked": len(st["manifest"]["files"]),
            "in_memory_weight_digest_check":
                "PASS" if model.check_memory() else "FAIL",
            "bundle_total_bytes": st["bundle_bytes"],
        },
        "live_evaluation": {
            "windows_evaluated": len(idx),
            "of_packaged_test_windows": int(len(y)),
            "window_seconds": 60,
            "channels": 88,
            "macro_f1": round(_macro_f1(y[idx], preds), 4),
            "accuracy": round(float((preds == y[idx]).mean()), 4),
            "latency_ms_mean": round(float(lat.mean()), 1),
            "latency_ms_p95": round(float(np.percentile(lat, 95)), 1),
        },
        "packaged_full_test_set": {
            "windows": int(w60["n_windows"]["test"]),
            "macro_f1": round(float(w60["edge_bundle_test_macro_F1"]), 4),
            "note": "Measured on all 240 test windows when the bundle "
                    "was packaged (BENCHMARKS.md).",
        },
        "runtime": {
            "peak_rss_mb": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "cold_start_s_incl_sha256_verify": st["cold_start_s"],
            "fallback_model": st["fallback60"].name,
            "fallback_full_test_macro_f1":
                round(float(w60["fallback"]["test_macro_F1"]), 4),
        },
        "try": {
            "classify_packaged_window": 'POST {"sample_index": 0}',
            "classify_raw_window":
                'POST {"window": [[...], ...]}  (6x88 -> W=60, 12x88 -> W=120)',
        },
    }


def _respond(status: int, payload: dict) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def handler(event, context=None):
    try:
        st = _init()
        method = (event.get("requestContext", {}).get("http", {})
                  .get("method", "GET"))
        raw = event.get("body") or ""
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode("utf-8", "replace")
        body = {}
        if raw:
            try:
                body = json.loads(raw)
            except json.JSONDecodeError:
                return _respond(400, {"error": "request body is not valid JSON"})

        if method == "GET" or body.get("demo"):
            return _respond(200, _demo(body.get("demo_windows",
                                                DEFAULT_DEMO_WINDOWS)))

        if "sample_index" in body:
            n = body["sample_index"]
            X, y = st["demo_X"], st["demo_y"]
            if not isinstance(n, int) or not (0 <= n < len(y)):
                return _respond(400, {
                    "error": f"sample_index must be an int in [0, {len(y)})"})
            return _respond(200, _classify(st["primary60"], X[n], {
                "sample_index": n,
                "true_class": CLASSES[int(y[n])],
                "window_seconds": 60,
            }))

        if "window" in body:
            w = np.asarray(body["window"], dtype=np.float32)
            if w.ndim != 2 or w.shape[1] != 88 or not np.isfinite(w).all():
                return _respond(400, {
                    "error": "window must be a T x 88 array of finite "
                             "numbers (88 realistic channels)"})
            if w.shape[0] == 6:
                model, secs = st["primary60"], 60
            elif w.shape[0] == 12:
                model, secs = st["primary120"], 120
            else:
                return _respond(400, {
                    "error": "window must have 6 rows (W=60 s) or 12 rows "
                             "(W=120 s) at 10 s sampling"})
            return _respond(200, _classify(model, w,
                                           {"window_seconds": secs}))

        return _respond(400, {
            "error": "expected {\"sample_index\": N}, {\"window\": [[...]]} "
                     "or {\"demo\": true}"})
    except Exception as exc:  # integrity failures land here too
        return _respond(500, {"error": f"{type(exc).__name__}: {exc}"})
