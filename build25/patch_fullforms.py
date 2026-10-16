#!/usr/bin/env python3
"""Model full forms in the classic Data view (ht-fullforms v1).

Shows the full form next to every short model name in the Data view and
its panels, WITHOUT changing any option value, JS key, or data payload
(display text only):

  - forecast model selector (#hts-model): option labels become
    "GP Matérn — Gaussian Process (Matérn kernel)" (values stay the
    model index, exactly as before);
  - weekly outlook model selector (#htwk-model): same label pattern
    (values stay the model name);
  - RMSE-by-lead table, feature-ablation readout rows, weekly
    leaderboard rows and the DACP readout line: full form appended to
    the rendered name;
  - the static tables (station + pooled leaderboards, drift concept
    table): "<td>NAME</td>" cells gain the full form, as does the
    "Best at this station" bold note;
  - ONE glossary block listing all 10 full forms, inserted at the top
    of the forecast panel (hts-sec-fc).

Canonical full forms (PILSTM verified against the project source:
hydrotwin_colab/train_pilstm.py -- "Physics-Informed LSTM (PILSTM)").

Only classic Data view pages are patched (ht-statsview marker, not
-3d). Every targeted code snippet was verified to occur exactly once
per classic page; the patcher FAILS loudly rather than writing a page
whose anchors do not match. Idempotent: pages carrying the marker are
skipped.
Run from the repo root: python3 build25/patch_fullforms.py
"""
import re
import sys
from pathlib import Path

MARKER = "ht-fullforms v1"

FULL = {
    "ARIMA": "Autoregressive Integrated Moving Average",
    "SARIMA": "Seasonal Autoregressive Integrated Moving Average",
    "GP Matérn": "Gaussian Process (Matérn kernel)",
    "GP RBF": "Gaussian Process (Radial Basis Function kernel)",
    "LSTM": "Long Short-Term Memory network",
    "Transformer": "Transformer (self-attention neural network)",
    "TFT": "Temporal Fusion Transformer",
    "PatchTST": "Patch Time-Series Transformer",
    "GCN": "Graph Convolutional Network",
    "PILSTMv1": "Physics-Informed LSTM, version 1",
}
# JS object literal with the same map, inlined into the label builders
# (self-contained: no load-order assumptions, values/keys untouched).
FFOBJ = "{" + ",".join(f"'{k}':'{v}'" for k, v in FULL.items()) + "}"


def ff(var):
    return (f"(function (F) {{ return F[{var}] ? {var} + ' \\u2014 ' + F[{var}] : {var}; }})({FFOBJ})")


# (old, new, expected count) -- JS display builders
JS_EDITS = [
    ("o.textContent = n;",
     f"o.textContent = {ff('n')};", 1),
    ("return '<option value=\"' + m + '\">' + m + '</option>';",
     f"return '<option value=\"' + m + '\">' + {ff('m')} + '</option>';", 1),
    ("'<tr data-m=\"' + m + '\"><td>' + n + '</td>'",
     f"'<tr data-m=\"' + m + '\"><td>' + {ff('n')} + '</td>'", 1),
    ("'<span>' + n + '</span><b>' + abl[n].toFixed(4)",
     f"'<span>' + {ff('n')} + '</span><b>' + abl[n].toFixed(4)", 1),
    ("'><td>' + n + (ref ? ' (reference)' : '') + '</td>",
     f"'><td>' + {ff('n')} + (ref ? ' (reference)' : '') + '</td>", 1),
    ("var name = P.models[S.model];",
     f"var name = P.models[S.model]; var dname = {ff('name')};", 1),
    ("el.textContent = name + '",
     "el.textContent = dname + '", 3),
]

GLOSSARY = (
    '\n  <!-- ht-fullforms v1 -->\n'
    '  <div class="hts-glossary" id="hts-model-glossary" '
    'style="font-size:12px;line-height:1.6;color:#9FB3C8;background:#101E30;'
    'border:1px solid #22344C;border-radius:8px;padding:8px 12px;margin:10px 0">'
    '<b style="color:#E6EDF5">Model full names:</b> '
    + "; ".join(f"{k} \u2014 {v}" for k, v in FULL.items())
    + ".</div>"
)
FC_HEAD_RE = re.compile(
    r'(<section class="hts-sec" id="hts-sec-fc">\s*<h2>7-day forecast</h2>)')


def post_checks(s: str) -> str | None:
    for token in (MARKER, 'id="hts-model-glossary"', "ht-statsview v1",
                  "ht-drift-panel", 'id="ht-drift-panel"', "window.HT_DATA",
                  'id="hts-sec-fc"', 'id="hts-sec-models"'):
        if token not in s:
            return f"FAIL post-check missing {token}"
    if s.count(MARKER) != 1 or s.count('id="hts-model-glossary"') != 1:
        return "FAIL post-check: glossary duplication"
    for name in FULL:
        if f"<td>{name}</td>" in s:
            return f"FAIL post-check: unexpanded cell <td>{name}</td> remains"
    for old, _new, _cnt in JS_EDITS:
        if old.startswith("var name = "):
            continue  # this edit extends the line; the old text is its prefix
        if old in s:
            return f"FAIL post-check: old snippet remains: {old[:40]}..."
    if "var dname = " not in s:
        return "FAIL post-check: DACP display name not installed"
    return None


def patch(path: Path) -> str:
    s = path.read_text(encoding="utf-8")
    if MARKER in s:
        return "skip (marker)"
    if "ht-statsview v1" not in s:
        return "skip (not a Data view page)"
    # anchor verification first: refuse to write a page that does not
    # match the expected layout exactly
    for old, _new, cnt in JS_EDITS:
        got = s.count(old)
        if got != cnt:
            return f"FAIL anchor {old[:44]!r}: {got} occurrences (want {cnt})"
    if len(FC_HEAD_RE.findall(s)) != 1:
        return "FAIL anchor: forecast section head not found once"
    td_counts = {}
    for name in FULL:
        td_counts[name] = s.count(f"<td>{name}</td>")
        if td_counts[name] == 0:
            return f"FAIL anchor: no static cell for {name}"
    # --- apply ---
    for old, new, _cnt in JS_EDITS:
        s = s.replace(old, new)
    for name, full in FULL.items():
        s = s.replace(f"<td>{name}</td>", f"<td>{name} \u2014 {full}</td>")
        s = s.replace(f"<b>{name}</b>", f"<b>{name} \u2014 {full}</b>")
    s = FC_HEAD_RE.sub(lambda m: m.group(1) + GLOSSARY, s, count=1)
    bad = post_checks(s)
    if bad:
        return bad
    path.write_text(s, encoding="utf-8")
    return "patched (td cells: " + ",".join(str(td_counts[n]) for n in FULL) + ")"


def main():
    root = Path("stations")
    files = sorted(p for p in root.glob("USGS-*.html") if not p.name.endswith("-3d.html"))
    if not files:
        print("no classic station pages found under stations/", file=sys.stderr)
        return 1
    bad = 0
    for p in files:
        r = patch(p)
        print(f"{p.name}: {r}")
        if r.startswith("FAIL"):
            bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
