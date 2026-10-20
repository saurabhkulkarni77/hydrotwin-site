"""Station-page integrity: every deploy-time patch is installed exactly
once, and the baked data axis is the 25-year axis (n=9131 from 2001-10-01).

The expected marker counts below are the *single-install signature* of
the dev build, locked in from a census of all 28 pages on 2026-10-19
(the hydrotwin-lab suite's approach, extended with the dev-only
patchers: monthly/yearly outlooks, Compare panels, the monthly
Flow & forecast treatment, the 3D chart, cache-busting, and the
live-stall fix). Each patcher's idempotency marker must appear with
exactly this count on every page of its class; a missing install drops
the count, a duplicated install raises it — either fails CI. The drift
panel is anchored on its canonical div, `<div id="ht-drift-panel">`,
which the drift patcher itself uses as its only safe skip check.
"""
import json

import pytest

from conftest import AXIS_N, AXIS_START, MODELS, STATIONS, read_page

CLASSIC_MARKERS = {
    "ht-statsview v1": 2,            # Statistics Data view (classic only)
    "ht-soilsnow v1": 2,             # soil/snow day-panel rows (classic only)
    "ht-3dchart v1": 2,              # 3D forecast chart in Data view (classic only)
    "ht-corr v1": 2,                 # multi-factor correlation section + boot
    "ht-dacp v1": 1,                 # DACP daily intervals
    "ht-weekly v1": 1,               # weekly outlook section (classic form)
    "ht-monthly v1": 1,              # monthly outlook section
    "ht-yearly v1": 1,               # yearly outlook section
    "ht-ffmo v1": 1,                 # monthly Flow & forecast treatment
    "ht-cmpwm v1": 1,                # weekly + monthly compare panel
    "ht-cmpy v1": 1,                 # yearly compare panel
    "ht-fullforms v1": 1,            # model full-form glossary block
    "ht-uiux v1": 1,                 # UI enhancer
    "ht-livefix v2": 1,              # live-stall fix wrappers
    "ht-liveall v2": 1,              # one Live action for all charts + old weights
    "ht-noclim v1": 1,               # climatology removed from the UI (display only)
    "ht-cachebust v1": 3,            # per-deploy build stamp (3 stamps)
    '<div id="ht-drift-panel">': 1,  # drift panel (canonical anchor)
    'id="hts-top"': 1,               # statsview layout root
    'id="hts-sec-weekly"': 1,        # weekly section in the stats layout
    'id="hts-sec-monthly"': 1,       # monthly section in the stats layout
    'id="hts-sec-yearly"': 1,        # yearly section in the stats layout
    'id="htdc-on"': 1,               # DACP band toggle control
    'id="htwk-live"': 1,             # weekly outlook Live button
    'id="htmo-live"': 1,             # monthly outlook Live button
    'id="htyr-live"': 1,             # yearly outlook Live button
    'id="htffmo-live"': 1,           # monthly F&F treatment Live button
}

THREED_MARKERS = {
    "ht-dacp v1": 1,                 # DACP daily intervals
    "ht-weekly v1": 2,               # weekly outlook panel (3D form)
    "ht-monthly v1": 1,              # monthly outlook panel
    "ht-yearly v1": 1,               # yearly outlook section
    "ht-ffmo v1": 1,                 # monthly Flow & forecast treatment
    "ht-cmpwm v1": 1,                # weekly + monthly compare panel
    "ht-cmpy v1": 1,                 # yearly compare panel
    "ht-uiux v1": 2,                 # UI enhancer
    "ht-live-gap v1": 2,             # true-live gap fill (3D only)
    "ht-ablfix v1": 1,               # ablation readout fix (3D only)
    "ht-livefix v2": 1,              # live-stall fix wrappers
    "ht-liveall v2": 1,              # one Live action for all charts + old weights
    "ht-noclim v1": 1,               # climatology removed from the UI (display only)
    "ht-cachebust v1": 3,            # per-deploy build stamp (3 stamps)
    '<div id="ht-drift-panel">': 1,  # drift panel (canonical anchor)
    'id="htdc-on"': 1,               # DACP band toggle control
    'id="htwk-canvas"': 1,           # weekly outlook canvas
    'id="htwk-live"': 1,             # weekly outlook Live button
    'id="htmo-live"': 1,             # monthly outlook Live button
    'id="htyr-live"': 1,             # yearly outlook Live button
    'id="htffmo-live"': 1,           # monthly F&F treatment Live button
}

# Patches that must NOT leak across page classes.
CLASSIC_FORBIDDEN = ("ht-live-gap v1", "ht-ablfix v1")
THREED_FORBIDDEN = ("ht-statsview v1", "ht-soilsnow v1", "ht-3dchart v1",
                    "ht-corr v1", "ht-fullforms v1", 'id="hts-top"')


def _extract_ht_data(html):
    """window.HT_DATA is a strict-JSON object literal; extract and parse it."""
    i = html.find("window.HT_DATA=")
    assert i >= 0, "window.HT_DATA assignment not found"
    j = html.find("{", i)
    depth, in_str, esc = 0, False, False
    for k in range(j, len(html)):
        c = html[k]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return json.loads(html[j:k + 1])
    raise AssertionError("HT_DATA object is unbalanced")


@pytest.mark.parametrize("station", STATIONS)
def test_classic_page_markers(repo_root, station):
    html = read_page(repo_root, station, "")
    for marker, expected in CLASSIC_MARKERS.items():
        assert html.count(marker) == expected, (
            f"{station} classic: marker {marker!r} found "
            f"{html.count(marker)}x, expected {expected}x")
    for marker in CLASSIC_FORBIDDEN:
        assert marker not in html, f"{station} classic: unexpected {marker!r}"


@pytest.mark.parametrize("station", STATIONS)
def test_3d_page_markers(repo_root, station):
    html = read_page(repo_root, station, "-3d")
    for marker, expected in THREED_MARKERS.items():
        assert html.count(marker) == expected, (
            f"{station} 3d: marker {marker!r} found "
            f"{html.count(marker)}x, expected {expected}x")
    for marker in THREED_FORBIDDEN:
        assert marker not in html, f"{station} 3d: unexpected {marker!r}"


@pytest.mark.parametrize("station", STATIONS)
@pytest.mark.parametrize("kind", ["", "-3d"])
def test_page_axis_fragments(repo_root, station, kind):
    html = read_page(repo_root, station, kind)
    assert html.count(f'"start":"{AXIS_START}"') == 1
    assert html.count(f'"n":{AXIS_N}') == 1


@pytest.mark.parametrize("station", STATIONS)
def test_classic_ht_data_parses(repo_root, station):
    data = _extract_ht_data(read_page(repo_root, station, ""))
    assert data["start"] == AXIS_START
    assert data["n"] == AXIS_N
    assert data["station"]["stationId"] == f"USGS-{station}"
    assert data["models"] == MODELS
    for series in ("tmax", "tmin", "tmean", "precip", "flow"):
        assert len(data[series]) == AXIS_N, f"{station}: {series} length"
    assert len(data["pred"]) == len(MODELS)


def test_all_station_pages_exist(repo_root):
    pages = sorted(p.name for p in (repo_root / "stations").glob("*.html"))
    expected = sorted(
        [f"USGS-{s}.html" for s in STATIONS]
        + [f"USGS-{s}-3d.html" for s in STATIONS])
    assert pages == expected
