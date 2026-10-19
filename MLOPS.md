# MLOps — Level 2 on the dev branch

The **dev branch** of this repo runs the same Level-2 MLOps setup
(CI + CD + CT) that was built for `hydrotwin-lab` (Oct 2026), ported
here on 2026-10-19 and adapted to the dev build. The dev site is a
baked static site (28 station pages + per-station data sidecars) whose
"models" are the forecast artifacts baked into those pages. Heavy
training lives in `hydrotwin-models`; everything that can be checked,
gated, monitored, and released *here* is automated here.

Dev site: http://hydrotwin-site-dev-2026.s3-website-us-east-1.amazonaws.com/
Status page: [`mlops.html`](http://hydrotwin-site-dev-2026.s3-website-us-east-1.amazonaws.com/mlops.html)

## Concept map

| Level-2 concept | Implemented as | Where |
|---|---|---|
| CI — code tests | pytest suite runs on every PR and push to `dev` | `.github/workflows/ci.yml`, `tests/` |
| CI — site integrity tests | every station page must carry each deploy-time patch marker with its exact single-install count (census of all 28 pages, 2026-10-19); HT_DATA must parse with n=9131 from 2001-10-01 | `tests/test_site_integrity.py` |
| CI — data contracts | every sidecar JSON (dacp/, dacpw/, dacpm/, dacpy/, weekly/, monthly/, yearly/, soilsnow/, corr/, chart3d/) parses and matches its station axis/schema; drift bake/report consistency | `tests/test_data_contracts.py` |
| CI — link/asset checks | every relative href/src in the baked pages resolves to a repo file | `tests/test_links.py` |
| Model registry | versioned registry of all 10 models: stage (production/candidate), pooled daily + weekly RMSE, data window, artifact locations | `models/registry.json` |
| Validation gate | PRs touching `models/**` fail if a production-stage model's pooled RMSE regresses >1% vs the frozen baselines, unless the PR carries the `allow-regression` label | `models/gate.py`, `models/baselines.json`, `.github/workflows/model-gate.yml` |
| Monitoring | drift (PSI from `drift/drift_bake.json`), freshness (drift-report window vs data axis; DACP reach), and sidecar coverage recomputed from baked data; opens/updates one `mlops-monitor` issue on breach, silent otherwise | `monitor/monitor.py`, `.github/workflows/monitor.yml` |
| Continuous training (CT) | request + validation side here (honest stub); training itself runs in `hydrotwin-models` (`daily-retrain.yml` with pre-training `drift_check.py`); post-retrain metrics re-enter through the gate | `.github/workflows/retrain.yml`, `retrain/` |
| CD — site deploy | pushes to `dev` run the deploy-time patchers and sync the tree to the dev S3 bucket (unchanged pipeline) | `.github/workflows/deploy-dev.yml` |
| CD — releases | version tags (or manual dispatch) build the dev site ZIP (no `.github/`) and publish a GitHub Release with generated notes | `.github/workflows/release.yml` |
| Environments | production = this repo's `main` (CloudFront + Pages); dev = this branch (S3); lab = `hydrotwin-lab` (Pages). Promotion is dev-first, human-approved | `ENVIRONMENTS.md` |

## What the port changed vs the lab original

* **Branch scoping.** CI and the model gate trigger on `dev` (the lab
  originals trigger on its `main`). The status workflow pins its
  checkout to `dev`: on `workflow_run` events a bare checkout would
  take the default branch, which does not carry this overlay.
* **Marker census extended** for the dev-only patchers the lab
  snapshot predates: monthly/yearly outlooks, weekly+monthly and
  yearly Compare panels, the monthly Flow & forecast treatment
  (ht-ffmo), the classic 3D chart, cache-busting (ht-cachebust),
  and the live-stall fix (ht-livefix v2).
* **Data contracts extended** to the dev sidecar families: dacpm/,
  dacpy/, monthly/, yearly/, chart3d/. Two documented dev facts the
  contracts encode: the drift report's baseline window is the full
  record since the 2026-10-19 drift fix (recent = WY2026), and
  dacpy/03294500 legitimately has zero yearly calibration windows.
* **Monitor coverage** checks all ten sidecar families (chart3d
  carries its station id as `station.stationId`).
* **Status page** reports the dev pipeline, including the latest
  "Deploy DEV to AWS S3" run.

## The gate, in one paragraph

`models/baselines.json` freezes the accepted build's pooled metrics
(25-year build, test era WY2025–26: daily champion PILSTMv1 0.2703,
weekly champion Transformer 0.4857 — protocol-A benchmark values,
unchanged by the 2026-10-19 drift-fix retrain). A PR that updates
`models/registry.json` with worse production numbers fails the gate
unless a maintainer deliberately labels it `allow-regression` — the
label re-runs the gate in warning mode, so the acceptance is visible
in the PR's check history.

## Monitoring thresholds

* PSI > 0.25 on any feature = drift breach (project convention:
  <0.10 stable, 0.10–0.25 watch, >0.25 drift). At port time the baked
  drift data shows 10 of 14 stations above 0.25 on log10_flow —
  genuine post-drift-fix regime change, so the monitor *will* file
  its tracking issue on its first dev run; that is the system working.
* Drift report's recent window must end on the data-axis end
  (2026-09-30 for the current build).
* Daily DACP sidecars must reach within 14 days of the axis end.
* Every sidecar family must hold exactly one file per station.

## Status page (public visibility)

The system above is visible on the dev site itself at
[`mlops.html`](http://hydrotwin-site-dev-2026.s3-website-us-east-1.amazonaws.com/mlops.html)
(linked from the homepage's help panel): automation triggers, the
model registry table, the latest drift-monitoring findings, and the
latest run state of every workflow. The page is data-driven — it is
pre-rendered from `mlops-status.json` (both files are regenerated
together by `monitor/gen_status.py` + `monitor/gen_page.py`), a
snapshot built from `models/registry.json` + `models/baselines.json`,
the baked drift data and sidecars, the latest GitHub Actions runs,
and the `mlops-monitor` tracking issue. `.github/workflows/status.yml`
re-runs the generator and commits the refreshed snapshot (with
`[skip ci]`) whenever the CI, gate, monitor, retrain or release
workflows complete, and on manual dispatch; the page shows the
snapshot's generation time and flags itself when the snapshot is
stale.

## Honest limitations (dev-specific)

* The training stage is a validated handoff, not a training run —
  this repo intentionally contains no training code or data pipeline.
* GitHub **scheduled** workflows only run from a repo's default
  branch. The monitor's weekly cron is therefore armed only once
  this overlay is promoted to `main`; on dev the monitor runs on
  manual dispatch (and the status page refreshes on its completion).
* The status snapshot commits back with `GITHUB_TOKEN`, and token
  pushes do not start new workflow runs — so after an automatic
  snapshot refresh lands on `dev`, the S3 copy of the page updates
  on the next deploy (push or manual `deploy-dev` dispatch).
* The S3 sync in `deploy-dev.yml` publishes the whole tree except
  `.git/`, `.github/` and `build25/` — the same exposure the lab
  repo has on GitHub Pages (tests/, models/, monitor/, retrain/ are
  web-visible). Nothing in those folders is secret; they are the
  public audit trail of the pipeline.
