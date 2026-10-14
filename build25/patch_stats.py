#!/usr/bin/env python3
"""Replace the baked CMP_RMSE leaderboard in the 3D station pages with the
25-year retrain's pooled test RMSEs (mean per-station test RMSE, log-flow).

The table was hardcoded in the pages from a 10-year-era evaluation (GP Matern
rank 1) and was not part of the data/forecast payloads, so the 25yr rebuild
left it stale. LiveAR keeps its own score (it is an in-browser learner, not
part of the retrain). Ranks are recomputed over the full table.

Idempotent: pages already carrying the new values are left untouched.
Run from the repo root: python3 build25/patch_stats.py
"""
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


def main():
    pages = sorted(Path("stations").glob("*-3d.html"))
    if not pages:
        print("no 3D station pages found (run from repo root)", file=sys.stderr)
        return 1
    changed = 0
    for p in pages:
        s = p.read_text(encoding="utf-8")
        if "0.2703" in s and "PILSTMv1': { rmse: 0.2703, rank: 1 }" in s:
            continue
        s2, n = PAT.subn(NEW_BLOCK, s, count=1)
        if n and s2 != s:
            p.write_text(s2, encoding="utf-8")
            changed += 1
        elif not n:
            print(f"WARNING: no CMP_RMSE block in {p}")
    print(f"patch_stats: {changed} page(s) updated, {len(pages)} 3D pages scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
