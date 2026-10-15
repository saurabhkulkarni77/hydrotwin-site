#!/usr/bin/env python3
"""Bake the 25-year retrain's model tables into the 3D station pages (dev only).

1) CMP_RMSE leaderboard: replaced with the 25yr pooled test RMSEs (mean
   per-station test RMSE, log-flow). LiveAR keeps its own score (in-browser
   learner, not part of the retrain). Ranks recomputed over the full table.
2) ABLATION (Compare panel feature-subset switcher): replaced PER PAGE with
   that station's own values from the 25yr ablation run
   (ablation_results25.json: 6/7/8/9 feat x GP Matern, Transformer, LSTM, GCN).
   Any missing cell falls back to that subset/model's pooled mean.

Idempotent: pages already carrying the new values are left untouched.
Run from the repo root: python3 build25/patch_stats.py
"""
import json
import re
import sys
from pathlib import Path

NEW_BLOCK = """const CMP_RMSE = {
  'GP Matérn': { rmse: 0.2900, rank: 8 },
  'Transformer': { rmse: 0.2737, rank: 3 },
  'GP RBF': { rmse: 0.2858, rank: 6 },
  'TFT': { rmse: 0.2760, rank: 4 },
  'PILSTMv1': { rmse: 0.2703, rank: 1 },
  'LSTM': { rmse: 0.2723, rank: 2 },
  'LiveAR': { rmse: 0.2956, rank: 9 },
  'GCN': { rmse: 0.2848, rank: 5 },
  'PatchTST': { rmse: 0.2896, rank: 7 },
  'SARIMA': { rmse: 0.6745, rank: 10 },
  'ARIMA': { rmse: 0.6832, rank: 11 },
};"""

PAT = re.compile(r"const CMP_RMSE = \{.*?\n\};", re.S)
ABL_PAT = re.compile(r"const ABLATION = \{.*?\};", re.S)

# === ABLATION DATA (generated from ablation_results25.json; do not hand-edit) ===
ABLATION_DATA = {
 "01463500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.3517,
   "Transformer": 0.3382,
   "LSTM": 0.3432,
   "GCN": 0.3514
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.3517,
   "Transformer": 0.3406,
   "LSTM": 0.3423,
   "GCN": 0.358
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.354,
   "Transformer": 0.3558,
   "LSTM": 0.3532,
   "GCN": 0.3522
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.354,
   "Transformer": 0.3469,
   "LSTM": 0.354,
   "GCN": 0.3486
  }
 },
 "01646500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.4265,
   "Transformer": 0.4037,
   "LSTM": 0.4141,
   "GCN": 0.4189
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.4265,
   "Transformer": 0.3952,
   "LSTM": 0.4174,
   "GCN": 0.4335
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.4366,
   "Transformer": 0.4227,
   "LSTM": 0.4325,
   "GCN": 0.4172
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.4366,
   "Transformer": 0.422,
   "LSTM": 0.44,
   "GCN": 0.4306
  }
 },
 "02320500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.0667,
   "Transformer": 0.0725,
   "LSTM": 0.0779,
   "GCN": 0.0814
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.0667,
   "Transformer": 0.0768,
   "LSTM": 0.077,
   "GCN": 0.079
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.0672,
   "Transformer": 0.0798,
   "LSTM": 0.0835,
   "GCN": 0.0808
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.0672,
   "Transformer": 0.075,
   "LSTM": 0.0779,
   "GCN": 0.0857
  }
 },
 "03294500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.4047,
   "Transformer": 0.3808,
   "LSTM": 0.3892,
   "GCN": 0.4048
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.4047,
   "Transformer": 0.3886,
   "LSTM": 0.3875,
   "GCN": 0.4054
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.399,
   "Transformer": 0.3972,
   "LSTM": 0.3822,
   "GCN": 0.4019
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.399,
   "Transformer": 0.3864,
   "LSTM": 0.3823,
   "GCN": 0.3935
  }
 },
 "05331000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.1812,
   "Transformer": 0.1864,
   "LSTM": 0.1866,
   "GCN": 0.1913
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.1812,
   "Transformer": 0.1709,
   "LSTM": 0.1825,
   "GCN": 0.1912
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.1796,
   "Transformer": 0.1759,
   "LSTM": 0.1873,
   "GCN": 0.1914
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.1796,
   "Transformer": 0.1876,
   "LSTM": 0.1861,
   "GCN": 0.1936
  }
 },
 "06214500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.1961,
   "Transformer": 0.1714,
   "LSTM": 0.1668,
   "GCN": 0.2191
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.181,
   "Transformer": 0.1699,
   "LSTM": 0.1649,
   "GCN": 0.214
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.1821,
   "Transformer": 0.1756,
   "LSTM": 0.1669,
   "GCN": 0.2211
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.1711,
   "Transformer": 0.1748,
   "LSTM": 0.1695,
   "GCN": 0.2171
  }
 },
 "06934500": {
  "6feat": {
   "GP Mat\u00e9rn": 0.2417,
   "Transformer": 0.2304,
   "LSTM": 0.2353,
   "GCN": 0.2713
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.2406,
   "Transformer": 0.2334,
   "LSTM": 0.2391,
   "GCN": 0.2714
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.2407,
   "Transformer": 0.2329,
   "LSTM": 0.2297,
   "GCN": 0.2674
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.235,
   "Transformer": 0.2366,
   "LSTM": 0.2299,
   "GCN": 0.2768
  }
 },
 "07374000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.1032,
   "Transformer": 0.1086,
   "LSTM": 0.1118,
   "GCN": 0.1314
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.1008,
   "Transformer": 0.1141,
   "LSTM": 0.1111,
   "GCN": 0.1312
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.1042,
   "Transformer": 0.1126,
   "LSTM": 0.1171,
   "GCN": 0.1301
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.1014,
   "Transformer": 0.1011,
   "LSTM": 0.1097,
   "GCN": 0.1295
  }
 },
 "08057000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.6897,
   "Transformer": 0.6912,
   "LSTM": 0.6887,
   "GCN": 0.7091
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.6897,
   "Transformer": 0.6942,
   "LSTM": 0.6687,
   "GCN": 0.7152
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.6935,
   "Transformer": 0.6905,
   "LSTM": 0.7128,
   "GCN": 0.7109
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.6935,
   "Transformer": 0.6863,
   "LSTM": 0.6855,
   "GCN": 0.7156
  }
 },
 "08158000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.535,
   "Transformer": 0.5441,
   "LSTM": 0.5432,
   "GCN": 0.5442
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.535,
   "Transformer": 0.5134,
   "LSTM": 0.5275,
   "GCN": 0.5587
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.5388,
   "Transformer": 0.5272,
   "LSTM": 0.5088,
   "GCN": 0.577
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.5388,
   "Transformer": 0.5571,
   "LSTM": 0.5125,
   "GCN": 0.5539
  }
 },
 "08313000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.257,
   "Transformer": 0.2654,
   "LSTM": 0.269,
   "GCN": 0.2528
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.2568,
   "Transformer": 0.2528,
   "LSTM": 0.3084,
   "GCN": 0.2582
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.2575,
   "Transformer": 0.2599,
   "LSTM": 0.2689,
   "GCN": 0.2556
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.2569,
   "Transformer": 0.2664,
   "LSTM": 0.2726,
   "GCN": 0.2565
  }
 },
 "09380000": {
  "6feat": {
   "GP Mat\u00e9rn": 0.0737,
   "Transformer": 0.0632,
   "LSTM": 0.0728,
   "GCN": 0.0722
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.0722,
   "Transformer": 0.0619,
   "LSTM": 0.0893,
   "GCN": 0.081
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.0675,
   "Transformer": 0.0626,
   "LSTM": 0.063,
   "GCN": 0.0795
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.0671,
   "Transformer": 0.0663,
   "LSTM": 0.0685,
   "GCN": 0.1032
  }
 },
 "11447650": {
  "6feat": {
   "GP Mat\u00e9rn": 0.2099,
   "Transformer": 0.2156,
   "LSTM": 0.2004,
   "GCN": 0.2142
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.2115,
   "Transformer": 0.2056,
   "LSTM": 0.2049,
   "GCN": 0.2209
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.2101,
   "Transformer": 0.2092,
   "LSTM": 0.2106,
   "GCN": 0.2077
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.2108,
   "Transformer": 0.211,
   "LSTM": 0.2097,
   "GCN": 0.2173
  }
 },
 "14105700": {
  "6feat": {
   "GP Mat\u00e9rn": 0.1199,
   "Transformer": 0.1155,
   "LSTM": 0.1225,
   "GCN": 0.1182
  },
  "7feat": {
   "GP Mat\u00e9rn": 0.118,
   "Transformer": 0.1135,
   "LSTM": 0.1159,
   "GCN": 0.1183
  },
  "8feat": {
   "GP Mat\u00e9rn": 0.1174,
   "Transformer": 0.1157,
   "LSTM": 0.1146,
   "GCN": 0.1187
  },
  "9feat": {
   "GP Mat\u00e9rn": 0.1168,
   "Transformer": 0.115,
   "LSTM": 0.1136,
   "GCN": 0.117
  }
 }
}
ABLATION_MEANS = {
 "6feat": {
  "GP Mat\u00e9rn": 0.2755,
  "Transformer": 0.2705,
  "LSTM": 0.273,
  "GCN": 0.2843
 },
 "7feat": {
  "GP Mat\u00e9rn": 0.274,
  "Transformer": 0.2665,
  "LSTM": 0.274,
  "GCN": 0.2883
 },
 "8feat": {
  "GP Mat\u00e9rn": 0.2749,
  "Transformer": 0.2727,
  "LSTM": 0.2737,
  "GCN": 0.2865
 },
 "9feat": {
  "GP Mat\u00e9rn": 0.2734,
  "Transformer": 0.2737,
  "LSTM": 0.2723,
  "GCN": 0.2885
 }
}
# === END ABLATION DATA ===

MODELS = ["GP Matérn", "Transformer", "LSTM", "GCN"]
SUBSETS = ["6feat", "7feat", "8feat", "9feat"]


def ablation_block(site):
    """JS `const ABLATION = {...};` for one station, with pooled-mean fallback."""
    per = ABLATION_DATA.get(site, {})
    obj = {}
    used_fallback = False
    for sub in SUBSETS:
        row = {}
        for m in MODELS:
            v = per.get(sub, {}).get(m)
            if v is None:
                v = ABLATION_MEANS.get(sub, {}).get(m)
                used_fallback = True
            row[m] = v
        obj[sub] = row
    js = json.dumps(obj, ensure_ascii=True, separators=(",", ":"))
    return f"const ABLATION = {js};", used_fallback


def main():
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("no 3D station pages found (run from repo root)", file=sys.stderr)
        return 1
    n_cmp = n_abl = 0
    fallback_sites = []
    for p in pages:
        site = p.name.replace("USGS-", "").replace("-3d.html", "")
        s = p.read_text(encoding="utf-8")
        orig = s
        # 1) CMP_RMSE pooled leaderboard
        if "PILSTMv1': { rmse: 0.2703, rank: 1 }" not in s:
            s, n = PAT.subn(NEW_BLOCK, s, count=1)
            if n:
                n_cmp += 1
            else:
                print(f"WARNING: no CMP_RMSE block in {p}")
        # 2) ABLATION per-station table
        if ABLATION_DATA:
            block, fb = ablation_block(site)
            if fb:
                fallback_sites.append(site)
            if block not in s:
                s, n = ABL_PAT.subn(lambda _: block, s, count=1)
                if n:
                    n_abl += 1
                else:
                    print(f"WARNING: no ABLATION block in {p}")
        if s != orig:
            p.write_text(s, encoding="utf-8")
    print(f"patch_stats: CMP_RMSE updated on {n_cmp} page(s); ABLATION updated on "
          f"{n_abl} page(s); {len(pages)} 3D pages scanned")
    if fallback_sites:
        print(f"patch_stats: pooled-mean fallback used for station(s): "
              f"{', '.join(fallback_sites)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
