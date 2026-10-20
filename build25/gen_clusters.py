#!/usr/bin/env python3
"""Station clustering for the HydroTwin Data view (ht-clusters v1).

Offline bake: groups the 14 stations by flow regime from the full daily
record (2001-10-01..2026-09-30, data25) plus NRCS soil/snow means.

Features per station (standardized before clustering):
  mean_log10_flow  - mean of log10 daily flow (cfs)
  cv_flow          - std/mean of daily flow (flashiness)
  lowflow_frac     - share of days below 10% of the station's median flow
  peak_month       - month of highest monthly-mean log flow (sin/cos pair)
  seas_amp         - max-min of monthly-mean log10 flow
  mean_sms         - mean soil moisture (%)        [NRCS]
  mean_stmp        - mean soil temperature (F)     [NRCS]
  mean_swe         - mean snow water equivalent (in) [NRCS]
  snow_frac        - share of days with SWE > 0    [NRCS]

Method: k-means (k-means++ init, 400 restarts, fixed seed) for k = 3..5,
k chosen by mean silhouette score; Ward hierarchical clustering
(scipy) cut at the same k supplies the dendrogram. Output:
clusters/clusters.json (one shared sidecar for all station pages).

Run from the repo root: python3 build25/gen_clusters.py
(data25 is located via HT_DATA25, default ~/workspace/hydrotwin_25yr/data25)
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial.distance import pdist, squareform

DATA25 = Path(os.environ.get(
    'HT_DATA25', Path.home() / 'workspace/hydrotwin_25yr/data25'))
SEED = 20261020

NAMES = {
    '01463500': ('Delaware River', 'Trenton'),
    '01646500': ('Potomac River', 'Little Falls'),
    '02320500': ('Suwannee River', 'Branford'),
    '03294500': ('Ohio River', 'Louisville'),
    '05331000': ('Mississippi River', 'St. Paul'),
    '06214500': ('Yellowstone River', 'Billings'),
    '06934500': ('Missouri River', 'Hermann'),
    '07374000': ('Mississippi River', 'Baton Rouge'),
    '08057000': ('Trinity River', 'Dallas'),
    '08158000': ('Colorado River', 'Austin'),
    '08313000': ('Rio Grande', 'Otowi'),
    '09380000': ('Colorado River', 'Lees Ferry'),
    '11447650': ('Sacramento River', 'Freeport'),
    '14105700': ('Columbia River', 'The Dalles'),
}
SITES = sorted(NAMES)

# Display copy per cluster, keyed by a signature member (place name).
# Numbers in the blurbs are the computed centroids of the final bake;
# gen prints the centroids so the copy can be checked against them.
LABELS = {
    'Baton Rouge': (
        'Giant mainstems',
        'Steady giants, snowmelt-buffered',
        'The continent\u2019s big plumbing. Mean flows run from about '
        '12,000 to 550,000 cfs, yet these are the steadiest rivers of '
        'the fourteen (flow CV 0.27\u20130.70): upstream snowmelt and '
        'reservoirs smooth the year, and the crest comes late, in '
        'May\u2013July.'),
    'Louisville': (
        'Eastern rain belt',
        'Wet soils, late-winter peak',
        'Big eastern rivers with no snowpack to speak of. Their soils '
        'are the wettest of the fourteen (about 31\u201336% moisture) '
        'and winter rain drives a sharp March crest \u2014 the '
        'strongest seasonal swing of any large-river group.'),
    'Austin': (
        'Warm and flashy',
        'Rain-driven, no snow',
        'Warm, snow-free basins where rain alone sets the flow. This '
        'is the flashiest group (flow CV 0.86\u20132.41): modest '
        'rivers that jump with storms and sag between them, cresting '
        'in spring. Austin swings hardest of all fourteen stations.'),
    'Billings': (
        'Northern snowmelt',
        'Cold soils, early-summer peak',
        'Cold-soil northern and mountain basins. Snow is a standing '
        'feature of the headwaters (on the ground half the year or '
        'more at the Billings and Otowi gauges), soils stay cold '
        '(about 44\u201347 \u00b0F), and the rivers crest in '
        'May\u2013June '
        'as the pack melts. Billings shows the largest seasonal '
        'swing of all fourteen stations.'),
    'Freeport': (
        'Sierra snowmelt',
        'Deepest snowpack, a class of its own',
        'The Sacramento at Freeport drains the Sierra Nevada and '
        'matches no other station: the deepest average snowpack of '
        'the fourteen (about 7.8 in of snow water), cold soils, and '
        'an early crest in March as the pack begins to go.'),
}
COLORS = ['#4db2ff', '#5fd68a', '#ff8a5c', '#b48ce8', '#ffd24d']


def station_features():
    nrcs = pd.read_csv(DATA25 / 'nrcs_daily.csv', dtype={'site': str})
    feats, monthly = {}, {}
    for site in SITES:
        d = pd.read_csv(DATA25 / 'daily' / f'{site}_daily.csv',
                        parse_dates=['date'])
        dl = d.dropna(subset=['flow_cfs'])
        dl = dl[dl.flow_cfs > 0].copy()
        dl['logf'] = np.log10(dl.flow_cfs)
        mm = dl.groupby(dl.date.dt.month)['logf'].mean().reindex(
            range(1, 13))
        monthly[site] = [round(float(v), 4) for v in mm.values]
        f = dl.flow_cfs
        n = nrcs[nrcs.site == site]
        feats[site] = {
            'mean_log10_flow': float(dl.logf.mean()),
            'mean_flow_cfs': float(f.mean()),
            'cv_flow': float(f.std() / f.mean()),
            'lowflow_frac': float((f < 0.10 * f.median()).mean()),
            'peak_month': int(mm.idxmax()),
            'seas_amp': float(mm.max() - mm.min()),
            'mean_sms': float(n.sms_pct.mean()),
            'mean_stmp': float(n.stmp_f.mean()),
            'mean_swe': float(n.swe_in.mean()),
            'snow_frac': float((n.swe_in > 0).mean()),
        }
    return feats, monthly


def kmeans(Z, k, restarts=400):
    rng = np.random.default_rng(SEED)
    best = None
    for _ in range(restarts):
        idx = [int(rng.integers(len(Z)))]
        for _ in range(k - 1):
            d2 = np.min(((Z[:, None, :] - Z[idx][None]) ** 2).sum(-1),
                        axis=1)
            p = d2 / d2.sum() if d2.sum() > 0 else None
            idx.append(int(rng.choice(len(Z), p=p)))
        C = Z[idx].copy()
        lab = np.zeros(len(Z), dtype=int)
        for _ in range(300):
            lab = np.argmin(((Z[:, None, :] - C[None]) ** 2).sum(-1),
                            axis=1)
            nC = np.array([Z[lab == j].mean(0) if (lab == j).any()
                           else C[j] for j in range(k)])
            if np.allclose(nC, C):
                break
            C = nC
        sse = float(((Z - C[lab]) ** 2).sum())
        if best is None or sse < best[0]:
            best = (sse, lab.copy(), C.copy())
    return best


def silhouette(Z, lab):
    D = squareform(pdist(Z))
    s = np.zeros(len(Z))
    for i in range(len(Z)):
        same = (lab == lab[i])
        same[i] = False
        a = D[i, same].mean() if same.any() else 0.0
        b = min(D[i, lab == c].mean() for c in set(lab.tolist())
                if c != lab[i])
        s[i] = (b - a) / max(a, b) if max(a, b) > 0 else 0.0
    return float(s.mean())


def main():
    feats, monthly = station_features()
    F = pd.DataFrame(feats).T
    cols = ['mean_log10_flow', 'cv_flow', 'lowflow_frac', 'seas_amp',
            'mean_sms', 'mean_stmp', 'mean_swe', 'snow_frac']
    X = np.column_stack([
        F[c].values for c in cols[:3]]
        + [np.sin(2 * np.pi * F.peak_month.values / 12),
           np.cos(2 * np.pi * F.peak_month.values / 12)]
        + [F[c].values for c in cols[3:]])
    Z = (X - X.mean(0)) / X.std(0, ddof=1)

    sil, parts = {}, {}
    for k in (3, 4, 5):
        _, lab, _ = kmeans(Z, k)
        sil[k] = silhouette(Z, lab)
        parts[k] = lab
    k = max(sil, key=sil.get)
    lab = parts[k]
    print('silhouette:', {kk: round(v, 3) for kk, v in sil.items()},
          '-> k =', k)

    Zl = linkage(Z, method='ward')
    ward_lab = fcluster(Zl, t=k, criterion='maxclust')
    leaves = dendrogram(Zl, no_plot=True)['leaves']
    merges = [[int(a), int(b), round(float(d), 4), int(n)]
              for a, b, d, n in Zl]
    cut = float((Zl[len(Zl) - k][2] + Zl[len(Zl) - k + 1][2]) / 2) \
        if len(Zl) - k + 1 < len(Zl) else float(Zl[-1][2] * 1.05)

    # Order clusters by centroid mean flow, largest first.
    cents = {}
    for c in range(k):
        m = [i for i, l in enumerate(lab) if l == c]
        cents[c] = {col: float(F.iloc[m][col].mean()) for col in
                    ['mean_log10_flow', 'mean_flow_cfs', 'cv_flow',
                     'lowflow_frac', 'peak_month', 'seas_amp', 'mean_sms',
                     'mean_stmp', 'mean_swe', 'snow_frac']}
    order = sorted(range(k), key=lambda c: -cents[c]['mean_log10_flow'])
    remap = {old: new for new, old in enumerate(order)}

    clusters = []
    for old in order:
        new = remap[old]
        members = [SITES[i] for i, l in enumerate(lab) if l == old]
        sig = next(NAMES[s][1] for s in members if NAMES[s][1] in LABELS)
        label, tag, blurb = LABELS[sig]
        curve = np.mean([monthly[s] for s in members], axis=0)
        clusters.append({
            'id': new, 'label': label, 'tag': tag, 'blurb': blurb,
            'color': COLORS[new], 'members': members,
            'centroid': {c2: round(v, 3) for c2, v in cents[old].items()},
            'monthly_log10': [round(float(v), 4) for v in curve],
        })

    stations = {}
    for i, site in enumerate(SITES):
        stations[site] = {
            'name': f'{NAMES[site][0]} at {NAMES[site][1]}',
            'river': NAMES[site][0], 'place': NAMES[site][1],
            'cluster': remap[int(lab[i])],
            'ward_cluster': int(ward_lab[i]),
            'monthly_log10': monthly[site],
            'features': {c2: round(float(F.loc[site, c2]), 4) for c2 in
                         ['mean_log10_flow', 'mean_flow_cfs', 'cv_flow',
                          'lowflow_frac', 'peak_month', 'seas_amp',
                          'mean_sms', 'mean_stmp', 'mean_swe',
                          'snow_frac']},
        }

    out = {
        'version': 'ht-clusters v1',
        'data_window': '2001-10-01..2026-09-30 (daily)',
        'method': ('k-means on standardized regime features '
                   '(k-means++, 400 restarts); Ward hierarchical '
                   'clustering for the dendrogram, cut at the same k'),
        'k': k,
        'silhouette': {str(kk): round(v, 3) for kk, v in sil.items()},
        'silhouette_chosen': round(sil[k], 3),
        'feature_defs': {
            'mean_log10_flow': 'mean of log10 daily flow (cfs)',
            'cv_flow': 'std / mean of daily flow (flashiness)',
            'lowflow_frac': 'share of days below 10% of median flow',
            'peak_month': 'month of highest monthly-mean log flow',
            'seas_amp': 'max - min monthly-mean log10 flow',
            'mean_sms': 'mean soil moisture (%) - NRCS',
            'mean_stmp': 'mean soil temperature (F) - NRCS',
            'mean_swe': 'mean snow water equivalent (in) - NRCS',
            'snow_frac': 'share of days with SWE > 0 - NRCS',
        },
        'clusters': clusters,
        'stations': stations,
        'dendrogram': {
            'merges': merges,
            'leaf_order': [int(x) for x in leaves],
            'leaf_sites': SITES,
            'cut_height': round(cut, 4),
            'max_height': round(float(Zl[-1][2]), 4),
        },
    }
    dest = Path('clusters/clusters.json')
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f'wrote {dest} ({dest.stat().st_size} bytes)')
    for c in clusters:
        print(f"  [{c['id']}] {c['label']} -- "
              f"{[NAMES[s][1] for s in c['members']]}")
        print(f"       centroid: {c['centroid']}")


if __name__ == '__main__':
    main()
