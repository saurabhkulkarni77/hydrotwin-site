# ACE cycle 4 — repair of playbook v2 (post-ship smoke defect)

After v2 shipped, the live browser smoke caught two defects the
39-question gate battery did not cover:

1. "what is the best pizza in town" was ANSWERED instead of refused:
   cycle 2's keyword 'wine town' (Hermann station) put the ordinary
   word "town" into the gate vocabulary. The same flip hit "best
   restaurant in town" and "movies playing in town" probes.
2. The flagship question "Where is the river in California?" now
   topped the Sacramento feature-importance panel (52) instead of
   the Sacramento station 3D entry (51): single-keyword ablation
   shows cycle 1's 'river model' on that panel is sufficient alone
   to flip it (+3 on any "river" question).

Response, all measured: the gate battery was extended with the
project's two canonical refusal-smoke questions (39 -> 41 tasks;
v1 scores 41/41 on it, v2 scores 40/41). ace_repair.py attributed
defect 1 to 'wine town' by ablation; it was removed and its
validated residue 'wine' substituted. Defect 2's keyword 'river
model' was removed from pb-1010 (its evidence question remains
served by cycle 2's 'flow model' / 'inputs matter' on the same
entry, and by 'discharge flow').

Repaired candidate v3, measured in full: gate 41/41; every
retrieval metric identical to v2 (held-out hybrid top-1 0.643,
retrieval hybrid top-1 0.737, keyword top-1 0.368, explainer
hybrid top-1 1.000); flagship California top-1 restored to
station-11447650-3d.

Decision: the standard promotion rule (run_cycle.decide) reports
guards {'G1 gate perfect': True, 'G2 heldout hy top3': True, 'G3 explainer hy top1': True, 'G4 heldout hy top1': True} and improvements {'I1 retrieval hy top1': False, 'I2 retrieval kw top1 +0.03, hy not down': False} — no improvement
over v2, because the repair only removes defects. But the
incumbent v2 itself FAILS the current gate guard (40/41), so it
is not a valid playbook to keep. Under the repair rule stated
for this cycle before the eval ran (restore gate perfection and
the flagship ranking, give back no measured gain), the decision
is PROMOTE: v3 replaces v2.
