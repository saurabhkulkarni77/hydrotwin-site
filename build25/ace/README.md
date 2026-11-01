# ACE for the HydroTwin helper bot

An implementation of **ACE — Agentic Context Engineering** (Zhang et
al., arXiv:2510.04618, ICLR 2026) adapted to this bot. The paper's
finding: a Generator / Reflector / Curator loop that evolves a
versioned context "playbook" from execution feedback — no weight
updates, no labelled supervision — beat strong baselines by +10.6%
on agent benchmarks and +8.6% on finance tasks, and matched a top
production agent with a smaller open model. This bot is the same
shape: a small open model (Qwen2.5-3B-Instruct, llama.cpp in
Lambda) over a retrieval index, so the "context" ACE evolves here
is the index's keyword layer, learned from the bot's own measured
failures.

## The loop, as implemented here

| ACE role | Here |
| --- | --- |
| Generator | The bot pipeline itself: client keyword scoring + relevance gate, then the Lambda hybrid rerank (w_cos 0.95), mirrored exactly by `ace_lib.py` and proven against the shipped JavaScript (`mirror.mjs`). |
| Task set | `batteries/` — the project's gate battery (39), the hybrid experiment's paraphrase battery (56, dev/held-out split), and an explainer battery (20) for the six explainer entries. |
| Reflector | `ace_reflect.py` — deterministic diagnosis of every failure (ranks, pool membership, uncovered words, failure taxonomy) from actual retrieved-vs-expected data, plus the project's own Qwen2.5-3B proposing new keywords. Every proposal is validated by code: short, new, and grounded (every word appears in the question or the entry's own title/text) with at least one distinctive word. |
| Curator | `ace_curate.py` — deterministic: valid proposals only, one bullet per entry per cycle, max 3 keywords per entry per cycle, every bullet tagged with its evidence questions and failure classes. |
| Playbook | `playbook.json` — versioned data; `playbook_changelog.md` records every promotion and rejection with the measured numbers. |
| Promotion gate | `run_cycle.py` — a candidate ships only if the gate battery stays perfect, held-out hybrid top-1/top-3 and explainer hybrid top-1 do not drop, and retrieval measurably improves. Otherwise the candidate is rejected and logged. |

## How the playbook reaches the site

`build25/gen_helper_index.py` merges `playbook.json` at index build
time: each `entry_keywords` bullet appends its keywords to that
entry's keyword list. Nothing else changes — entry titles and texts
are untouched, so the embedding asset (`helper/ht-emb.bin`, built
from "title. text") is unaffected, and the merge is fully described
by the playbook file alone. `note` bullets are auditable knowledge
for humans and change no retrieval.

## Running a cycle

```sh
# prerequisites: an ht-index.json (from the repo root after
# gen_helper_index.py, or the live file), HT_LLAMA_SERVER /
# HT_EMBED_MODEL pointing at llama.cpp + the bge-small GGUF for
# embeddings, and (for --llm) a local llama-server on :18094
# serving the production Qwen2.5-3B GGUF.
python3 ace_eval.py --index helper/ht-index.json \
    --check-mirror --helper helper/ht-helper.js   # trust, but verify
python3 run_cycle.py --index helper/ht-index.json --cycle 1 --llm
```

Cycle artefacts (eval before/after, reflection, candidate, report)
land in `runs/cycle<N>/`. Every reported number is computed by the
run that reports it — the project's no-hardcoded-results rule
applies to this tooling too.

## Honest limits

* The playbook can only ADD keywords. Failures caused by ambient
  competition (an unrelated entry scoring on generic words) or by
  embedding-side confusion between near-identical sibling panels
  are recorded by the Reflector but are not keyword-fixable; they
  stay in the cycle reports as known residue.
* Keyword additions are double-edged in this scoring (+9 for an
  exact phrase, but +3 whenever any single keyword word appears in
  a question). That is why proposals are validated for
  distinctiveness and why the promotion gate, not the Reflector,
  has the final word.
