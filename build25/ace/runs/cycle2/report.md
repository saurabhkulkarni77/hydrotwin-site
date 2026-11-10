# ACE cycle 2 — report

| run | gate | paraphrase held-out hy top1 | hy top3 | retrieval hy top1 | retrieval kw top1 | explainer hy top1 |
| --- | --- | --- | --- | --- | --- | --- |
| playbook v1 (before) | 39/39 | 0.464 | 0.607 | 0.632 | 0.289 | 1.000 |
| candidate v2 | 37/39 | 0.643 | 0.714 | 0.737 | 0.382 | 1.000 |

Promotion guards: G1 gate perfect FAIL; G2 heldout hy top3 PASS; G3 explainer hy top1 PASS; G4 heldout hy top1 PASS
Improvements: I1 retrieval hy top1 YES; I2 retrieval kw top1 +0.03, hy not down YES

**Decision: REJECTED** — candidate v2 does not replace playbook v1.

New bullets in the candidate:
- `pb-2001` **station-11447650-data** += ['out west', 'west coast', 'river meets'] (evidence: 2 failed questions; classes: WEAK_KEYWORD)
- `pb-2002` **station-08313000-data** += ['charts 3d', 'desert southwest', 'santa'] (evidence: 2 failed questions; classes: WEAK_KEYWORD)
- `pb-2003` **station-08158000-data** += ['big river', 'lone star', 'capital city'] (evidence: 1 failed questions; classes: STATION_CONFUSION, WEAK_KEYWORD)
- `pb-2004` **station-02320500-data** += ['suwannee river sunshine', 'florida sunshine', 'swampy blackwater'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2005` **station-06934500-data** += ['wine town', 'middle country', 'german heritage'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2006` **station-07374000-data** += ['last station', 'delta'] (evidence: 1 failed questions; classes: STATION_CONFUSION)
- `pb-2007` **panel-08057000-hts-sec-hydro** += ['plots history', 'dallas history', 'discharge history'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2008` **panel-06214500-hts-sec-weekly** += ['by week', 'next three', 'months week'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-2009` **panel-08057000-hts-sec-charts3d** += ['flow history', 'rotatable chart'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-2010` **panel3d-02320500-dock** += ['little page', 'card controls', 'day prediction'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2011` **panel-08057000-hts-sec-drift** += ['model quality', 'slipping'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-2012` **panel-08158000-hts-sec-fc** += ['show week', 'possible flows', 'austin forecast'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-2013` **station-14105700-data** += ['gorge station', 'northwest pacific'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2014` **panel-11447650-hts-sec-featimp** += ['flow model', 'inputs matter'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
- `pb-2015` **panel-09380000-hts-sec-ablation** += ['drop inputs', 'some inputs'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2016` **howto-panels** += ['open sections', 'hidden sections'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2017` **howto-precip** += ['date', 'pick'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2018` **station-01463500-data** += ['delaware river data', 'washington army'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2019` **station-01646500-data** += ['nation s capital'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2020` **station-05331000-data** += ['northern city'] (evidence: 1 failed questions; classes: FALSE_REFUSAL)
- `pb-2021` **station-06214500-data** += ['big sky'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2022` **panel-08057000-hts-sec-fc** += ['forecast week'] (evidence: 1 failed questions; classes: WEAK_KEYWORD)
- `pb-2023` **panel-08158000-hts-sec-drift** += ['worse over time'] (evidence: 1 failed questions; classes: PANEL_CONFUSION)
