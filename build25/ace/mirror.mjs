// Mirror check: extract the ACTUAL retrieval functions shipped in
// helper/ht-helper.js (norm, scoredList, retrieve, relevant and the
// gate STOP set) and run them over a question file, so ace_eval.py
// can prove its Python mirror agrees with production JavaScript on
// every battery question before any ACE number is trusted.
//
// Usage: node mirror.mjs <ht-helper.js> <ht-index.json> <questions.json>
//   questions.json: [{"q": "..."}, ...]
// Stdout: [{"q", "gate": bool, "kw": [{"id", "score"}, ... top 10]}]
import { readFileSync } from 'fs';

const [helperPath, indexPath, qPath] = process.argv.slice(2);
const src = readFileSync(helperPath, 'utf8');
const i0 = src.indexOf('function norm(s)');
const i1 = src.indexOf('var SUGGESTIONS');
if (i0 < 0 || i1 < 0 || i1 <= i0) {
  console.error('could not locate retrieval block in ht-helper.js');
  process.exit(2);
}
const code = src.slice(i0, i1);
const INDEX = JSON.parse(readFileSync(indexPath, 'utf8'));
const factory = new Function('INDEX',
  code + '\nreturn { norm, scoredList, retrieve, relevant };');
const api = factory(INDEX);
const questions = JSON.parse(readFileSync(qPath, 'utf8'));
const out = questions.map(({ q }) => ({
  q,
  gate: api.relevant(q),
  kw: api.scoredList(q).slice(0, 10).map(([s, e]) => ({ id: e.id, score: s })),
}));
console.log(JSON.stringify(out));
