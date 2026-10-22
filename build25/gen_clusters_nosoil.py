#!/usr/bin/env python3
"""Station clustering with basin traits, NO soil (ht-clusters v1,
nosoil variant).

Offline bake: groups the 14 stations by flow regime from the full daily
record (2001-10-01..2026-09-30, data25) plus NRCS snow means,
EXTENDED with basin traits from the USGS NLDI bake
in ~/workspace/hydrotwin_map_basin/basins.json (the same data the 3D
Watershed panel and the homepage pin hover card use).
Variant of gen_clusters_basin.py with the two NRCS soil traits
(mean soil moisture, mean soil temperature) REMOVED at the user's
order ("dont use any soil features", 2026-10-21): 11 traits remain
(6 flow + 2 snow + 3 basin). Soil values are not computed, not
recorded in the sidecar, and not named in any feature definition.
Removing them costs the k = 5 continuity the basin bake enjoyed:
silhouette now climbs to k = 6 (0.417 against 0.350 at k = 5, a gap
of 0.067, well outside the 0.02 rule), because Billings, no longer
tied to the interior group by its cold soils, stands alone on its
snow regime. The basin traits are:

  log10_area  - log10 of the NLDI basin (watershed) area, km2
  log10_dm    - log10 of the downstream mainstem path length, km
                (NLDI navigation; the returned path is capped near
                400 km, so long rivers pile up at the cap: read it as
                "far inland" versus a shorter run to the sea)
  spec_q      - log10 of specific discharge: the station mean flow
                (data25, cfs) per km2 of basin area

A fourth candidate, log10 of the upstream path length, was DROPPED:
the NLDI upstream navigation is capped at 150 km and every one of the
14 stations lands between 147 and 156 km (std of the log10 trait is
0.007), so the trait is a near constant artifact of the cap, not basin
information; worse, standardizing it would inflate those few km of
join noise into a full weight trait.

Method: k-means (k-means++ init, 400 restarts, fixed seed) for
k = 3..6, scored by mean silhouette; k = 5 is kept whenever its
silhouette is within 0.02 of the best (continuity with the shipped
section), otherwise the argmax wins. Ward hierarchical clustering
(scipy) cut at the same k supplies the dendrogram. The sidecar also
carries a PCA projection of the same standardized features (first two
components, per-cluster convex hulls) and a geographic layer: station
lat/lon plus the US nation outline and projected station positions
taken from the homepage's own map asset (window.MAP in index.html,
us-atlas states-albers-10m), so the section can draw the actual
clusters in feature space and on a map. The sidecar also carries a
k_options block: for EVERY k tried (3 to 6), the silhouette score,
the full partition, and a description derived mechanically from how
that partition differs from the chosen one (which chosen groups it
merges, which stations move); no regime names are invented for the
non chosen values. Output schema is identical to
clusters/clusters.json (plus the basin traits in features /
feature_defs / centroids and the k_options block) so the existing
renderer consumes it unchanged.

Run from the repo root: python3 build25/gen_clusters_nosoil.py
(data25 is located via HT_DATA25, default ~/workspace/hydrotwin_25yr/data25;
the homepage is located via HT_INDEX, default ./index.html;
the basin bake via HT_BASINS, default
~/workspace/hydrotwin_map_basin/basins.json;
output via HT_OUT, default ~/workspace/hydrotwin_clusters/clusters_nosoil.json)
"""
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import dendrogram, fcluster, linkage
from scipy.spatial import ConvexHull
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
# Exactly one key place per cluster of the basin bake, so the lookup
# in main() is unambiguous. Numbers in the blurbs are the computed
# centroids / member values of the final bake; gen prints the
# centroids so the copy can be checked against them.
# Nosoil bake partition (k = 6, 11 traits; the k rule picks 6, see
# the docstring):
#   Hermann, Baton Rouge, Lees Ferry, The Dalles   (Giant mainstems)
#   Little Falls, Louisville                       (Eastern rain belt)
#   Freeport                                       (Sierra snowmelt)
#   Trenton, Branford                              (Warm coastal rivers)
#   St. Paul, Dallas, Austin, Otowi                (Interior rivers)
#   Billings                                       (Northern snowmelt,
#        a singleton now that soil no longer ties it to the interior)
LABELS = {
    'Baton Rouge': (
        'Giant mainstems',
        'Steady giants, snowmelt buffered',
        'The continent\u2019s big plumbing, now measured by basin '
        'as well as flow. These four drain the largest watersheds '
        'of the fourteen, about 280,000 to 2.9 million km\u00b2, '
        'and run the biggest mean flows, about 12,000 to '
        '550,000 cfs, yet they are the steadiest rivers here '
        '(flow CV 0.27 to 0.70): snow on the ground half the year '
        'or more in the headwaters and a long river below each '
        'gauge smooth the year, and the crest comes late, in '
        'May to July.'),
    'Louisville': (
        'Eastern rain belt',
        'Rain fed, late winter peak',
        'Big eastern rivers with no snowpack to speak of. Winter '
        'rain drives a sharp March crest and the strongest '
        'seasonal swing of any large river group, the flow is '
        'flashy for rivers of this size (flow CV 0.88 to 1.29), '
        'and their basins wring a generous flow from every square '
        'kilometre (0.38 and 0.58 cfs per km\u00b2).'),
    'Freeport': (
        'Sierra snowmelt',
        'Deepest snowpack, a class of its own',
        'The Sacramento at Freeport drains the Sierra Nevada and '
        'matches no other station: the deepest average snowpack of '
        'the fourteen (about 7.8 in of snow water), an early '
        'crest in March as the pack begins to go, a generous '
        '0.34 cfs from every square kilometre of basin, and the '
        'shortest run of river below the gauge, only 69 km to '
        'the Delta.'),
    'Trenton': (
        'Warm coastal rivers',
        'Small basins, close to the sea',
        'Two warm, rain fed rivers on the smallest basins of the '
        'fourteen after Dallas (about 17,600 and 18,900 km\u00b2). '
        'The sea is close, with only 126 to 164 km of river below '
        'the gauges, snow never enters the picture, and the flow '
        'jumps with storms (flow CV 0.85 to 0.97), cresting in '
        'spring. Each square kilometre yields generously, and '
        'Trenton yields the most of all fourteen stations, '
        '0.76 cfs per km\u00b2.'),
    'St. Paul': (
        'Interior rivers',
        'Far from the sea, lean and flashy',
        'The far inland group: big interior basins (about 16,000 '
        'to 95,000 km\u00b2) with a long river below every gauge '
        '(398 km or more of mapped channel) that yield little '
        'flow for their size, 0.01 to 0.19 cfs per km\u00b2; '
        'Austin is the leanest of all fourteen. Otowi rides the '
        'mountain snowmelt while St. Paul, Dallas and Austin run '
        'snow free, and as a group these are the flashiest '
        'rivers here (flow CV 0.89 to 2.41), cresting in May '
        'to June.'),
    'Billings': (
        'Northern snowmelt',
        'Snow most of the year, June crest',
        'The Yellowstone at Billings forms a regime of its own. '
        'Snow lies on its basin '
        'more days than at any other station (about 73% of the '
        'year), its seasonal swing is the largest of the '
        'fourteen, with the monthly mean flow rising and falling '
        'by almost a full log unit across the year, and the '
        'crest waits until June. A mid size basin of about '
        '29,500 km\u00b2 with 400 km of river below the gauge, '
        'a flashy flow (CV 1.24) and a middling yield of '
        '0.23 cfs per km\u00b2.'),
}
COLORS = ['#4db2ff', '#5fd68a', '#ff8a5c', '#b48ce8', '#ffd24d',
          '#ff6b9d']  # 6th color: the nosoil bake runs at k = 6


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


NUMWORDS = {1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five',
            6: 'six'}


def join_names(items):
    items = list(items)
    if len(items) <= 1:
        return ''.join(items)
    if len(items) == 2:
        return items[0] + ' and ' + items[1]
    return ', '.join(items[:-1]) + ', and ' + items[-1]


def describe_k(kk, silv, groups, chosen_named, k_chosen, n_tried):
    """One paragraph describing the partition at kk, written against
    the chosen partition. groups: list of place name lists at kk.
    chosen_named: (label, frozenset of places) at the chosen k, in
    sidecar order. Everything stated is computed from the two
    partitions: pure merges of chosen groups, stations added to a
    chosen group, or a leftover group named by its members and the
    chosen groups it draws from. No invented labels, no hyphens."""
    if kk == k_chosen:
        singles = [next(iter(m)) for _, m in chosen_named
                   if len(m) == 1]
        tail = ''
        if singles:
            tail = (', with ' + join_names(singles) +
                    ' each standing alone as a group of one')
        return (f'Silhouette {silv:.3f}, the best of the '
                f'{NUMWORDS[n_tried]} values tried{tail}.')
    gsets = [frozenset(g) for g in groups]
    clauses = []  # (chosen groups merged, group size, text)
    covered = set()
    for g in gsets:
        full = [(lab, m) for lab, m in chosen_named if m <= g]
        partial = [(lab, m & g) for lab, m in chosen_named
                   if (m & g) and not m <= g]
        if any(g == m for _, m in chosen_named):
            covered.add(g)
        elif len(full) >= 2 and not partial:
            if len(full) == 2:
                big, small = sorted(full, key=lambda t: -len(t[1]))
                if len(small[1]) == 1:
                    text = f'{next(iter(small[1]))} joins {big[0]}'
                else:
                    text = (f'{full[0][0]} and {full[1][0]} merge '
                            'into one group')
            else:
                text = (join_names([lab for lab, _ in full]) +
                        ' merge into one group')
            clauses.append((len(full), len(g), text))
            covered.add(g)
        elif len(full) == 1 and partial:
            extra = sorted(set().union(*[p for _, p in partial]))
            clauses.append((1, len(g), join_names(extra) +
                            f' join {full[0][0]}'))
            covered.add(g)
    for g in gsets:
        if g not in covered:
            labs = [lab for lab, m in chosen_named if m & g]
            clauses.append((0, len(g), 'one group gathers ' +
                            join_names(sorted(g)) + ' out of ' +
                            join_names(labs)))
    clauses.sort(key=lambda t: (-t[0], -t[1]))
    body = join_names([c[2] for c in clauses])
    text = (f'Silhouette {silv:.3f}. ' +
            body[0].upper() + body[1:] + '.')
    unchanged = [lab for lab, m in chosen_named
                 if any(g == m for g in gsets)]
    if len(unchanged) == 1:
        text += f' {unchanged[0]} is unchanged.'
    elif unchanged:
        text += (f' The other {NUMWORDS[len(unchanged)]} groups, ' +
                 join_names(unchanged) + ', are unchanged.')
    return text


FEATURE_NAMES = ['mean_log10_flow', 'cv_flow', 'lowflow_frac',
                 'peak_sin', 'peak_cos', 'seas_amp', 'mean_swe',
                 'snow_frac', 'log10_area', 'log10_dm', 'spec_q']
BASIN_TRAITS = ['log10_area', 'log10_dm', 'spec_q']
BASINS = Path(os.environ.get(
    'HT_BASINS',
    Path.home() / 'workspace/hydrotwin_map_basin/basins.json'))


def homepage_map():
    """Station coordinates + US outline from the homepage map asset.

    index.html embeds window.MAP (us-atlas 3.0 states-albers-10m):
    per-station lat/lon and projected x/y in the 975x610 map space,
    plus the `nation` outline polylines. We keep polylines with >= 3
    points, integer-rounded (the tiny 2-point fragments are dropped),
    which leaves a clean lightweight outline for the sidecar.
    """
    path = Path(os.environ.get('HT_INDEX', 'index.html'))
    s = path.read_text(encoding='utf-8')
    i = s.find('window.MAP=')
    if i < 0:
        raise SystemExit(f'window.MAP not found in {path}')
    blob = s[i + len('window.MAP='):s.find('</script>', i)]
    m = json.loads(blob.rstrip().rstrip(';'))
    outline = []
    for line in m['nation']:
        if len(line) < 3:
            continue
        pts = []
        for x, y in line:
            p = [int(round(x)), int(round(y))]
            if not pts or pts[-1] != p:
                pts.append(p)
        if len(pts) >= 3:
            outline.append(pts)
    stations = {st['site']: {'lat': st['lat'], 'lon': st['lon'],
                             'map_xy': [round(st['x'], 1),
                                        round(st['y'], 1)]}
                for st in m['stations']}
    return {'width': m['width'], 'height': m['height'],
            'source': m['source'], 'outline': outline}, stations


def basin_features(feats):
    """Basin traits from the USGS NLDI bake, aligned to SITES.

    Returns a DataFrame indexed by site with the raw NLDI numbers and
    the three clustering traits. log10 of the upstream path length is
    computed only to be reported and dropped: every station sits at
    the 150 km navigation cap (147 to 156 km), std 0.007 in log10.
    """
    raw = json.loads(BASINS.read_text(encoding='utf-8'))
    missing = [s for s in SITES if s not in raw]
    if missing:
        raise SystemExit(f'basin bake missing stations: {missing}')
    rows = {}
    for site in SITES:
        b = raw[site]
        area, dm, um = float(b['area_km2']), float(b['dm_km']), \
            float(b['um_km'])
        if area <= 0 or dm <= 0 or um <= 0:
            raise SystemExit(f'basin bake has nonpositive values: {site}')
        rows[site] = {
            'area_km2': area, 'dm_km': dm, 'um_km': um,
            'log10_area': float(np.log10(area)),
            'log10_dm': float(np.log10(dm)),
            'log10_um': float(np.log10(um)),
            'spec_q': float(np.log10(
                feats[site]['mean_flow_cfs'] / area)),
        }
    B = pd.DataFrame(rows).T
    print('basin traits (log10):')
    for c in ('log10_area', 'log10_dm', 'log10_um', 'spec_q'):
        print(f'  {c}: min {B[c].min():.3f} max {B[c].max():.3f} '
              f'std {B[c].std():.3f}')
    print('  log10_um DROPPED: near constant at the 150 km NLDI '
          'navigation cap (raw range '
          f"{int(B.um_km.min())} to {int(B.um_km.max())} km), "
          'an artifact, not basin information.')
    return B


def main():
    feats, monthly = station_features()
    mapmeta, mapstations = homepage_map()
    missing = [s for s in SITES if s not in mapstations]
    if missing:
        raise SystemExit(f'homepage map missing stations: {missing}')
    F = pd.DataFrame(feats).T
    B = basin_features(feats)
    for c in ('area_km2', 'dm_km', 'um_km') + tuple(BASIN_TRAITS):
        F[c] = B[c]
    cols = ['mean_log10_flow', 'cv_flow', 'lowflow_frac', 'seas_amp',
            'mean_swe', 'snow_frac']
    X = np.column_stack([
        F[c].values for c in cols[:3]]
        + [np.sin(2 * np.pi * F.peak_month.values / 12),
           np.cos(2 * np.pi * F.peak_month.values / 12)]
        + [F[c].values for c in cols[3:]]
        + [F[c].values for c in BASIN_TRAITS])
    Z = (X - X.mean(0)) / X.std(0, ddof=1)

    sil, parts = {}, {}
    for k in (3, 4, 5, 6):
        _, lab, _ = kmeans(Z, k)
        sil[k] = silhouette(Z, lab)
        parts[k] = lab
    best = max(sil, key=sil.get)
    # Continuity rule: keep k = 5 when it is competitive.
    k = 5 if sil[5] >= sil[best] - 0.02 else best
    lab = parts[k]
    print('silhouette:', {kk: round(v, 3) for kk, v in sil.items()},
          '-> k =', k)

    # PCA of the same standardized features (SVD of Z). Sign
    # conventions keep the axes oriented readably bake to bake: PC1
    # loads positively on mean flow, PC2 on mean SWE.
    _, sv, vt = np.linalg.svd(Z, full_matrices=False)
    var_pct = 100.0 * sv ** 2 / np.sum(sv ** 2)
    if vt[0, 0] < 0:
        vt[0] = -vt[0]
    if vt[1, FEATURE_NAMES.index('mean_swe')] < 0:
        vt[1] = -vt[1]
    scores = Z @ vt[:2].T
    pca_xy = {site: [round(float(scores[i, 0]), 3),
                     round(float(scores[i, 1]), 3)]
              for i, site in enumerate(SITES)}
    print('PCA variance % (PC1..PC4):',
          [round(float(v), 1) for v in var_pct[:4]])
    for j in (0, 1):
        top = np.argsort(-np.abs(vt[j]))[:5]
        print(f'  PC{j + 1} top loadings:',
              ', '.join(f'{FEATURE_NAMES[i]} {vt[j][i]:+.2f}'
                        for i in top))

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
                     'lowflow_frac', 'peak_month', 'seas_amp', 'mean_swe',
                     'snow_frac',
                     'area_km2', 'dm_km', 'um_km',
                     'log10_area', 'log10_dm', 'spec_q']}
    order = sorted(range(k), key=lambda c: -cents[c]['mean_log10_flow'])
    remap = {old: new for new, old in enumerate(order)}

    clusters = []
    for old in order:
        new = remap[old]
        members = [SITES[i] for i, l in enumerate(lab) if l == old]
        sig = next(NAMES[s][1] for s in members if NAMES[s][1] in LABELS)
        label, tag, blurb = LABELS[sig]
        curve = np.mean([monthly[s] for s in members], axis=0)
        midx = [SITES.index(s) for s in members]
        if len(midx) >= 3:
            hull = [members[j] for j in
                    ConvexHull(scores[midx]).vertices]
        else:
            hull = list(members)
        clusters.append({
            'id': new, 'label': label, 'tag': tag, 'blurb': blurb,
            'color': COLORS[new], 'members': members, 'hull': hull,
            'centroid': {c2: round(v, 3) for c2, v in cents[old].items()},
            'monthly_log10': [round(float(v), 4) for v in curve],
        })

    # Per k record for the "All k values" part of the section: the
    # partition at every k tried, ordered like the clusters array
    # (biggest mean flow first), with a description derived from
    # how it differs from the chosen partition.
    chosen_named = [(c['label'],
                     frozenset(NAMES[s][1] for s in c['members']))
                    for c in clusters]
    k_options = []
    for kk in sorted(parts):
        bylab = {}
        for i, l in enumerate(parts[kk]):
            bylab.setdefault(int(l), []).append(i)
        glist = sorted(
            bylab.values(),
            key=lambda idxs: -float(np.mean(
                [F.iloc[i]['mean_log10_flow'] for i in idxs])))
        groups_places = [[NAMES[SITES[i]][1] for i in idxs]
                         for idxs in glist]
        k_options.append({
            'k': kk,
            'silhouette': round(sil[kk], 3),
            'chosen': kk == k,
            'description': describe_k(kk, sil[kk], groups_places,
                                      chosen_named, k, len(parts)),
            'groups': groups_places,
        })

    stations = {}
    for i, site in enumerate(SITES):
        stations[site] = {
            'name': f'{NAMES[site][0]} at {NAMES[site][1]}',
            'river': NAMES[site][0], 'place': NAMES[site][1],
            'cluster': remap[int(lab[i])],
            'ward_cluster': int(ward_lab[i]),
            'lat': mapstations[site]['lat'],
            'lon': mapstations[site]['lon'],
            'map_xy': mapstations[site]['map_xy'],
            'pca': pca_xy[site],
            'monthly_log10': monthly[site],
            'features': {c2: round(float(F.loc[site, c2]), 4) for c2 in
                         ['mean_log10_flow', 'mean_flow_cfs', 'cv_flow',
                          'lowflow_frac', 'peak_month', 'seas_amp',
                          'mean_swe',
                          'snow_frac', 'area_km2', 'dm_km', 'um_km',
                          'log10_area', 'log10_dm', 'spec_q']},
        }

    out = {
        'version': 'ht-clusters v1',
        'data_window': '2001-10-01..2026-09-30 (daily)',
        'method': ('k means on standardized regime features plus '
                   'USGS NLDI basin traits (k means++, 400 restarts); '
                   'Ward hierarchical clustering for the dendrogram, '
                   'cut at the same k'),
        'k': k,
        'silhouette': {str(kk): round(v, 3) for kk, v in sil.items()},
        'silhouette_chosen': round(sil[k], 3),
        'k_options': k_options,
        'feature_defs': {
            'mean_log10_flow': 'mean of log10 daily flow (cfs)',
            'cv_flow': 'std / mean of daily flow (flashiness)',
            'lowflow_frac': 'share of days below 10% of median flow',
            'peak_month': 'month of highest monthly-mean log flow',
            'seas_amp': 'max - min monthly-mean log10 flow',
            'mean_swe': 'mean snow water equivalent (in) from NRCS',
            'snow_frac': 'share of days with SWE > 0 from NRCS',
            'area_km2': 'watershed (basin) area, km2, USGS NLDI basin',
            'dm_km': ('downstream mainstem path length, km, USGS '
                      'NLDI navigation (capped near 400 km)'),
            'um_km': ('upstream mainstem path length, km, USGS NLDI '
                      'navigation (capped at 150 km; recorded, not '
                      'used as a trait)'),
            'log10_area': 'log10 of area_km2',
            'log10_dm': 'log10 of dm_km',
            'spec_q': ('log10 of specific discharge: mean flow '
                       '(cfs) per km2 of basin area'),
        },
        'pca': {
            'features': FEATURE_NAMES,
            'variance_pct': [round(float(v), 2) for v in var_pct[:2]],
            'loadings': {
                'pc1': [round(float(v), 3) for v in vt[0]],
                'pc2': [round(float(v), 3) for v in vt[1]],
            },
        },
        'map': mapmeta,
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
    dest = Path(os.environ.get(
        'HT_OUT', Path.home() / 'workspace/hydrotwin_clusters'
        / 'clusters_nosoil.json'))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=1), encoding='utf-8')
    print(f'wrote {dest} ({dest.stat().st_size} bytes)')
    for c in clusters:
        print(f"  [{c['id']}] {c['label']} -- "
              f"{[NAMES[s][1] for s in c['members']]}")
        print(f"       centroid: {c['centroid']}")


if __name__ == '__main__':
    main()
