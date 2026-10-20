# Continuous training (CT) — how it works for HydroTwin

The **dev branch** of `hydrotwin-site` is the project's integration
surface, not the training plant. Continuous training is therefore
split honestly across repos:

| Stage | Where it runs | How |
|---|---|---|
| Data refresh (USGS / NRCS / Open-Meteo) | `hydrotwin-models` | `daily-retrain.yml` data steps |
| Pre-training drift gate | `hydrotwin-models` | `drift_check.py` runs after refresh, before training (warnings; `--strict` to block) |
| Training (all 10 models, all data) | `hydrotwin-models` | weekly, Sundays 08:00 UTC, and on demand |
| Export (ONNX / params / baked forecasts) | `hydrotwin-models` → `hydrotwin-site` | artifacts baked into station pages on the dev branch first |
| Metric validation gate | **this repo (dev)** | `models/gate.py` in `.github/workflows/model-gate.yml` |
| Site/data regression tests | **this repo (dev)** | `tests/` in `.github/workflows/ci.yml` |
| Drift & freshness monitoring | **this repo (dev)** | `monitor/monitor.py` in `.github/workflows/monitor.yml` |
| Promotion | human | dev → production (main), a separate explicit decision |

## Requesting a retrain from here

Run the **CT — retrain handoff (stub)** workflow
(`.github/workflows/retrain.yml`, manual dispatch). It validates the
request against `models/registry.json` (known model, data window that
extends — never shrinks — the registered window) and writes the
handoff summary. It does **not** train anything itself; the actual
run happens in `hydrotwin-models`. Keeping the request and the heavy
compute in different repos is deliberate.

## Retrain triggers in the full system

1. **Schedule** — weekly retrain in `hydrotwin-models`.
2. **Drift breach** — the monitor in this repo files an
   `mlops-monitor` issue when a station's baked PSI exceeds 0.25;
   that issue is the human-visible trigger to request a retrain.
3. **Manual** — dispatch the handoff workflow here, then the
   training workflow in `hydrotwin-models`.

## After a retrain

Candidate metrics are computed on the frozen test era (WY2025–26) and
entered into `models/registry.json` via a pull request. The PR must
pass the validation gate (no production-stage pooled RMSE regression
> 1% vs `models/baselines.json`, unless deliberately accepted with
the `allow-regression` label) and the CI suite before the new build
is deployed on dev.
