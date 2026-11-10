# ACE cycle 1 — report

| run | gate | paraphrase held-out hy top1 | hy top3 | retrieval hy top1 | retrieval kw top1 | explainer hy top1 |
| --- | --- | --- | --- | --- | --- | --- |
| playbook v0 (before) | 39/39 | 0.393 | 0.571 | 0.579 | 0.263 | 1.000 |
| candidate v1 | 39/39 | 0.464 | 0.607 | 0.632 | 0.289 | 1.000 |

Promotion guards: G1 gate perfect PASS; G2 heldout hy top3 PASS; G3 explainer hy top1 PASS; G4 heldout hy top1 PASS
Improvements: I1 retrieval hy top1 YES; I2 retrieval kw top1 +0.03, hy not down no

**Decision: PROMOTED** — candidate v1 replaces playbook v0.

New bullets in the candidate:
- `pb-1001` **station-06214500-data** += ['yellowstone river forecast', 'geyser park', 'famous geyser'] (evidence: 2 failed questions; classes: FALSE_REFUSAL, WEAK_KEYWORD)
- `pb-1002` **station-09380000-3d** += ['ground table', 'canyon station', 'daily forecast'] (evidence: 1 failed questions; classes: STATION_CONFUSION)
- `pb-1003` **panel-08158000-hts-sec-drift** += ['river drift', 'austin station', 'colorado drift'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1004` **panel-01646500-hts-sec-monthly** += ['next half year', 'potomac river outlook', 'long view'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1005` **panel-08057000-hts-sec-drift** += ['trinity river', 'dallas station', 'drift monitoring'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1006` **station-03294500-data** += ['horse race', 'bourbon'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1007` **station-14105700-data** += ['7 day forecast', 'columbia river forecast'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1008` **station-07374000-data** += ['mighty river', 'delta station'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1009` **panel-08057000-hts-sec-hydro** += ['90 day', 'full flow'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1010` **panel-11447650-hts-sec-featimp** += ['river model', 'discharge flow'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1011` **panel-08057000-hts-sec-charts3d** += ['data charts 3d', 'trinity river'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1012` **panel-08057000-hts-sec-featimp** += ['trinity river model', 'flow inputs'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1013` **panel-08158000-hts-sec-fc** += ['colorado', 'forecast'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-1014` **station-02320500-data** += ['river statistics'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1015` **station-08158000-data** += ['lone star state'] (evidence: 1 failed questions; classes: STATION_CONFUSION)
- `pb-1016` **station-08313000-data** += ['3d charts'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1017` **panel-08057000-hts-sec-fc** += ['trinity river'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1018` **panel-09380000-hts-sec-ablation** += ['forecast error'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1019` **howto-panels** += ['3d view'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1020` **howto-precip** += ['3d'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-1021` **station-11447650-data** += ['freeport california'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
