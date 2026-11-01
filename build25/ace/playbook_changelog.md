# ACE playbook — changelog

The playbook is versioned data. Every version change is recorded
here with the cycle that produced it, the failures that motivated
each bullet, and the measured eval delta that justified promotion
(or the rejection, when a candidate fails the promotion gate).
Nothing enters the playbook silently: ace_curate.py writes the
candidate, run_cycle.py measures it, and only a passing candidate
replaces playbook.json.

## v0 — 2026-11-01
Empty playbook. The baseline: the bot exactly as shipped (keyword
retrieval + relevance gate client-side, hybrid rerank in Lambda,
index with the six explainer entries).

## v1 — cycle 1 (PROMOTED)

Measured on the full battery set in the same run (see runs/cycle1/report.md):

- gate: 39/39 -> 39/39
- paraphrase held-out hybrid top-1: 0.393 -> 0.464
- retrieval-all hybrid top-1: 0.579 -> 0.632; keyword top-1: 0.263 -> 0.289

- `pb-1001` station-06214500-data += ['yellowstone river forecast', 'geyser park', 'famous geyser'] (evidence: the gateway to the famous geyser park; the station in Big Sky Country)
- `pb-1002` station-09380000-3d += ['ground table', 'canyon station', 'daily forecast'] (evidence: open the interactive scene for the canyon station)
- `pb-1003` panel-08158000-hts-sec-drift += ['river drift', 'austin station', 'colorado drift'] (evidence: is the Austin model getting worse over time)
- `pb-1004` panel-01646500-hts-sec-monthly += ['next half year', 'potomac river outlook', 'long view'] (evidence: the long view for the next half year at the Potomac)
- `pb-1005` panel-08057000-hts-sec-drift += ['trinity river', 'dallas station', 'drift monitoring'] (evidence: where do I see if the model quality is slipping for Dallas)
- `pb-1006` station-03294500-data += ['horse race', 'bourbon'] (evidence: the station in the city famous for its horse race and bourbon)
- `pb-1007` station-14105700-data += ['7 day forecast', 'columbia river forecast'] (evidence: the gorge station in the Pacific Northwest)
- `pb-1008` station-07374000-data += ['mighty river', 'delta station'] (evidence: the last station before the delta on the mighty river)
- `pb-1009` panel-08057000-hts-sec-hydro += ['90 day', 'full flow'] (evidence: the chart that plots discharge history for Dallas)
- `pb-1010` panel-11447650-hts-sec-featimp += ['river model', 'discharge flow'] (evidence: which inputs matter most for predicting the Sacramento flow)
- `pb-1011` panel-08057000-hts-sec-charts3d += ['data charts 3d', 'trinity river'] (evidence: the rotatable version of the flow history chart for Dallas)
- `pb-1012` panel-08057000-hts-sec-featimp += ['trinity river model', 'flow inputs'] (evidence: what drives the Trinity river flow the most)
- `pb-1013` panel-08158000-hts-sec-fc += ['colorado', 'forecast'] (evidence: show me the week ahead fan of possible flows for Austin)
- `pb-1014` station-02320500-data += ['river statistics'] (evidence: the swampy blackwater river in the Sunshine State)
- `pb-1015` station-08158000-data += ['lone star state'] (evidence: the other big river station in the Lone Star State, in its capital city)
- `pb-1016` station-08313000-data += ['3d charts'] (evidence: the numbers and charts page for the desert southwest river)
- `pb-1017` panel-08057000-hts-sec-fc += ['trinity river'] (evidence: what will the flow be over the coming week in Dallas)
- `pb-1018` panel-09380000-hts-sec-ablation += ['forecast error'] (evidence: what happens to the Lees Ferry predictions if you drop some inputs)
- `pb-1019` howto-panels += ['3d view'] (evidence: how do I open one of the hidden sections on a station page)
- `pb-1020` howto-precip += ['3d'] (evidence: will it rain at the station on the day I pick)
- `pb-1021` station-11447650-data += ['freeport california'] (evidence: the west coast station where the river meets the capital region)

## cycle 2 candidate v2 — REJECTED

Failed the promotion gate (guards: G1 gate perfect FAIL; G2 heldout hy top3 PASS; G3 explainer hy top1 PASS; G4 heldout hy top1 PASS). Playbook unchanged. Detail in runs/cycle2/report.md.

## v2 — cycle 3 repair of cycle 2 (PROMOTED)

Cycle 2's raw candidate was rejected (gate guard). Its repaired form —
three gate-breaking keywords removed by ablation attribution
('last station', 'capital city', 'nation s capital'), two validated
residue substitutions ('nation', 'city') — passed every guard.
Measured in the same runs (runs/cycle2 + runs/cycle3 reports):

- gate: 39/39 -> 39/39 (paraphrase gate failures 2 -> 0 across v0->v2)
- paraphrase held-out hybrid top-1: 0.464 -> 0.643; top-3: 0.607 -> 0.714
- retrieval-all hybrid top-1: 0.632 -> 0.737; keyword top-1: 0.289 -> 0.368
- explainer hybrid top-1: 1.000 (unchanged)

- `pb-2001` station-11447650-data += ['out west', 'west coast', 'river meets'] (evidence: the river out west in the Golden State; the west coast station where the river meets the capital region)
- `pb-2002` station-08313000-data += ['charts 3d', 'desert southwest', 'santa'] (evidence: the numbers and charts page for the desert southwest river; the river station a short drive from Santa Fe)
- `pb-2003` station-08158000-data += ['big river', 'lone star', 'city'] [repaired: removed ['capital city'], substituted ['city']] (evidence: the other big river station in the Lone Star State, in its capital city)
- `pb-2004` station-02320500-data += ['suwannee river sunshine', 'florida sunshine', 'swampy blackwater'] (evidence: the swampy blackwater river in the Sunshine State)
- `pb-2005` station-06934500-data += ['wine town', 'middle country', 'german heritage'] (evidence: the German heritage wine town station in the middle of the country)
- `pb-2006` station-07374000-data += ['delta'] [repaired: removed ['last station'], substituted []] (evidence: the last station before the delta on the mighty river)
- `pb-2007` panel-08057000-hts-sec-hydro += ['plots history', 'dallas history', 'discharge history'] (evidence: the chart that plots discharge history for Dallas)
- `pb-2008` panel-06214500-hts-sec-weekly += ['by week', 'next three', 'months week'] (evidence: the next three months week by week for Billings)
- `pb-2009` panel-08057000-hts-sec-charts3d += ['flow history', 'rotatable chart'] (evidence: the rotatable version of the flow history chart for Dallas)
- `pb-2010` panel3d-02320500-dock += ['little page', 'card controls', 'day prediction'] (evidence: the little card on the Suwannee 3D page with today's prediction and the day controls)
- `pb-2011` panel-08057000-hts-sec-drift += ['model quality', 'slipping'] (evidence: where do I see if the model quality is slipping for Dallas)
- `pb-2012` panel-08158000-hts-sec-fc += ['show week', 'possible flows', 'austin forecast'] (evidence: show me the week ahead fan of possible flows for Austin)
- `pb-2013` station-14105700-data += ['gorge station', 'northwest pacific'] (evidence: the gorge station in the Pacific Northwest)
- `pb-2014` panel-11447650-hts-sec-featimp += ['flow model', 'inputs matter'] (evidence: which inputs matter most for predicting the Sacramento flow)
- `pb-2015` panel-09380000-hts-sec-ablation += ['drop inputs', 'some inputs'] (evidence: what happens to the Lees Ferry predictions if you drop some inputs)
- `pb-2016` howto-panels += ['open sections', 'hidden sections'] (evidence: how do I open one of the hidden sections on a station page)
- `pb-2017` howto-precip += ['date', 'pick'] (evidence: will it rain at the station on the day I pick)
- `pb-2018` station-01463500-data += ['delaware river data', 'washington army'] (evidence: where is the gauge that Washington's army story is tied to)
- `pb-2019` station-01646500-data += ['nation'] [repaired: removed ['nation s capital'], substituted ['nation']] (evidence: the station by the nation's capital)
- `pb-2020` station-05331000-data += ['northern city'] (evidence: the northern city that is twinned with Minneapolis)
- `pb-2021` station-06214500-data += ['big sky'] (evidence: the station in Big Sky Country)
- `pb-2022` panel-08057000-hts-sec-fc += ['forecast week'] (evidence: what will the flow be over the coming week in Dallas)
- `pb-2023` panel-08158000-hts-sec-drift += ['worse over time'] (evidence: is the Austin model getting worse over time)
