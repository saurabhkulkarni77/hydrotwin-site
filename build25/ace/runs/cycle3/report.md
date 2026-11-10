# ACE cycle 3 — repair of the rejected cycle-2 candidate

Cycle 2's candidate improved retrieval strongly (held-out hybrid top-1
0.464 -> 0.643) but broke promotion guard G1 (gate 39/39 -> 37/39): three
new keywords carried words that are ordinary off-topic vocabulary —
'last station' flipped "Who won the football game last night?" and
'capital city' / 'nation s capital' flipped "What is the capital of
France?". ace_repair.py attributed each break by single-keyword ablation
against the base playbook, removed the three culprit keywords, and
substituted validated distinctive residue words ('nation' for Potomac,
'city' for Austin; 'last station' had no valid residue). The repaired
candidate was re-measured in full and put through the same promotion
rule (run_cycle.decide) against playbook v1 as measured in cycle 2.

| run | gate | paraphrase held-out hy top1 | hy top3 | retrieval hy top1 | retrieval kw top1 | explainer hy top1 |
| --- | --- | --- | --- | --- | --- | --- |
| playbook v1 (before) | 39/39 | 0.464 | 0.607 | 0.632 | 0.289 | 1.000 |
| repaired candidate v2 | 39/39 | 0.643 | 0.714 | 0.737 | 0.368 | 1.000 |

Promotion guards: G1 gate perfect PASS; G2 heldout hy top3 PASS; G3 explainer hy top1 PASS; G4 heldout hy top1 PASS
Improvements: I1 retrieval hy top1 YES; I2 retrieval kw top1 +0.03, hy not down YES

**Decision: PROMOTED** — repaired candidate becomes playbook v2.
