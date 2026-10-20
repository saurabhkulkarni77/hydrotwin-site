"""Baked-data contracts: every per-station sidecar JSON parses and matches
its station axis/schema, and the drift bake/report are internally
consistent.

Families covered (the sidecar families present on the dev branch):
  soilsnow/<site>.json  - daily soil/snow series on the full 9131-day axis
  weekly/<site>.json    - weekly-outlook baked forecasts (12 weekly leads)
  monthly/<site>.json   - monthly-outlook baked forecasts (6 monthly leads)
  yearly/<site>.json    - yearly-outlook baked forecasts (12 x 30-day leads)
  dacp/<site>.json      - daily DACP conformal quantiles, levels 70/80/90/95
  dacpw/<site>.json     - weekly DACP conformal quantiles, same levels
  dacpm/<site>.json     - monthly DACP conformal quantiles, same levels
  dacpy/<site>.json     - yearly DACP conformal quantiles, same levels
  corr/<site>.json      - multi-factor correlation matrix (ht-corr v1)
  chart3d/<site>.json   - 3D chart payload (axis series + baked forecasts)
  drift/drift_bake.json + drift/drift_report.json - baked drift analysis

Ported from the hydrotwin-lab suite; monthly/yearly/dacpm/dacpy/chart3d
contracts are the dev extension. When a new sidecar family is added to
the repo, add its contract here.
"""
import json

import pytest

from conftest import AXIS_END, AXIS_N, AXIS_START, MODELS, STATIONS

DRIFT_FEATURES = {"tmax_c", "tmin_c", "tmean_c", "precip_mm", "log10_flow"}
DACP_LEVELS = [70, 80, 90, 95]
OUTLOOK_LEADS = {"weekly": 12, "monthly": 6, "yearly": 12}
OUTLOOK_V = {"weekly": "ht-weekly v1", "monthly": "ht-monthly v1",
             "yearly": "ht-yearly v1"}


def _load(repo_root, *parts):
    with open(repo_root.joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.parametrize("family", ["dacp", "dacpw", "dacpm", "dacpy",
                                    "weekly", "monthly", "yearly",
                                    "soilsnow", "corr", "chart3d", "oldfc"])
def test_sidecar_coverage(repo_root, family):
    files = sorted(p.stem for p in (repo_root / family).glob("*.json"))
    assert files == sorted(STATIONS), f"{family}/ must hold one file per station"


@pytest.mark.parametrize("station", STATIONS)
def test_soilsnow_contract(repo_root, station):
    obj = _load(repo_root, "soilsnow", f"{station}.json")
    assert obj["site"] == station
    assert obj["start"] == AXIS_START
    assert obj["n"] == AXIS_N
    for key in ("sms", "stmp", "swe"):
        assert len(obj[key]) == AXIS_N, f"{station} soilsnow {key} length"


@pytest.mark.parametrize("family", ["weekly", "monthly", "yearly"])
@pytest.mark.parametrize("station", STATIONS)
def test_outlook_contract(repo_root, family, station):
    obj = _load(repo_root, family, f"{station}.json")
    assert obj["site"] == station
    assert obj["v"] == OUTLOOK_V[family]
    assert obj["start"] == AXIS_START
    assert obj["models"] == MODELS
    assert set(obj["rmse_test"]) == set(MODELS)
    assert set(obj["predw"]) == set(MODELS)
    n_issue = len(obj["dates"])
    assert n_issue > 0 and obj["dates"] == sorted(obj["dates"])
    leads = OUTLOOK_LEADS[family]
    for model in MODELS:
        rows = obj["predw"][model]
        assert len(rows) == n_issue
        assert all(len(row) == leads for row in rows), (
            f"{station} {family} {model}: every issue row must carry "
            f"{leads} leads")


@pytest.mark.parametrize("station", STATIONS)
def test_corr_contract(repo_root, station):
    obj = _load(repo_root, "corr", f"{station}.json")
    assert obj["site"] == station
    assert obj["v"] == "ht-corr v1"
    assert obj["start"] == AXIS_START
    assert obj["end"] == AXIS_END
    keys = [v["key"] for v in obj["vars"]]
    assert "logflow" in keys and "flow" in keys
    k = len(keys)
    assert len(obj["matrix"]) == k and all(len(row) == k for row in obj["matrix"])
    for i in range(k):
        assert obj["matrix"][i][i] == 1.0, f"{station} corr diagonal {keys[i]}"
        for j in range(k):
            r = obj["matrix"][i][j]
            assert r is None or -1.0 <= r <= 1.0
            assert obj["n"][i][j] > 0
    assert len(obj["lead1_logflow"]) == k and len(obj["lead1_n"]) == k


@pytest.mark.parametrize("station", STATIONS)
def test_chart3d_contract(repo_root, station):
    obj = _load(repo_root, "chart3d", f"{station}.json")
    assert obj["station"]["stationId"] == f"USGS-{station}"
    assert obj["start"] == AXIS_START
    assert obj["n"] == AXIS_N
    assert obj["models"] == MODELS
    for key in ("flow", "precip", "tmean"):
        assert len(obj[key]) == AXIS_N, f"{station} chart3d {key} length"
    assert len(obj["pred"]) == len(MODELS)
    for row in obj["pred"]:
        assert len(row) == 7, f"{station} chart3d pred row (7 leads)"


@pytest.mark.parametrize("family", ["dacp", "dacpw", "dacpm", "dacpy"])
@pytest.mark.parametrize("station", STATIONS)
def test_dacp_contract(repo_root, family, station):
    obj = _load(repo_root, family, f"{station}.json")
    assert obj["site"] == station
    assert obj["levels"] == DACP_LEVELS
    assert set(obj["q"]) == set(MODELS)
    # Documented exception: dacpy/03294500 has zero yearly calibration
    # windows (the Ohio River station has no valid yearly test windows
    # in this build), so its dates list is legitimately empty.
    if not (family == "dacpy" and station == "03294500"):
        assert len(obj["dates"]) > 0
    assert obj["dates"] == sorted(obj["dates"])
    if obj["dates"]:
        assert obj["dates"][-1] <= AXIS_END


def test_drift_bake_contract(repo_root):
    bake = _load(repo_root, "drift", "drift_bake.json")
    assert sorted(bake) == sorted(STATIONS)
    for station, entry in bake.items():
        feats = entry["data"]["features"]
        assert set(feats) == DRIFT_FEATURES, f"{station} drift features"
        assert all(v >= 0 for v in feats.values()), f"{station} PSI negative"
        # Headline PSI is the worst feature's PSI (stored rounded to 4 dp).
        assert abs(entry["data"]["psi"] - max(feats.values())) < 0.01
        assert entry["data"]["worst"] == max(feats, key=feats.get)
        assert set(entry["models"]) == set(MODELS)


def test_drift_report_contract(repo_root):
    report = _load(repo_root, "drift", "drift_report.json")
    # Dev report format after the 2026-10-19 drift fix: the baseline
    # window is the full record (the AFTER drift panels reference it),
    # and the recent window is WY2026. Concept drift is the protocol
    # A-vs-B comparison on untouched WY2026 windows.
    assert report["windows"]["baseline"] == [AXIS_START, AXIS_END]
    assert report["windows"]["recent"] == ["2025-10-01", AXIS_END]
    assert report["windows"]["recent"][1] == AXIS_END
    assert report["models"] == MODELS
    assert sorted(report["stations"]) == sorted(STATIONS)


@pytest.mark.parametrize("station", STATIONS)
def test_oldfc_contract(repo_root, station):
    """Old-weights sidecars: pre-drift-fix baked forecast tails.

    pred holds the last 400 issue days of the pre-fix HT_DATA.pred
    (commit 0908430a8e), 7 leads per issue, one row set per model.
    """
    obj = _load(repo_root, "oldfc", f"{station}.json")
    assert obj["site"] == station
    assert obj["v"] == "ht-oldfc v1"
    assert obj["src_commit"] == "0908430a8e"
    assert obj["start"] == AXIS_START
    assert obj["n"] == AXIS_N
    assert obj["from_issue"] == AXIS_N - 400
    assert obj["models"] == MODELS
    for model in MODELS:
        rows = obj["pred"][model]
        assert len(rows) == 400
        assert all(len(r) == 7 for r in rows)
