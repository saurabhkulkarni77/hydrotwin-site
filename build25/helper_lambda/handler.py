"""HydroTwin helper-bot inference Lambda.

Hosts an open source instruct model (GGUF Q4_K_M, stored in a private
S3 bucket; MODEL_KEY selects the file — Meta-Llama-3.2-3B-Instruct
since 2026-11-11; Qwen2.5-3B-Instruct before that, and its file stays
in the bucket for rollback) behind llama.cpp, invoked only through
the Lambda
Function URL by the dev site's helper bot.

Hybrid rerank (v3, 2026-11-01): when the request carries the bot's
keyword-scored candidate list, the handler ALSO reranks the whole
site index by embedding similarity and answers from the reranked
top hits. The client-side keyword retrieval stays the instant first
pass and the relevance gate is untouched and entirely client-side;
this layer only reorders. It exists because a 56-question
paraphrase battery (weights tuned on a dev split, verdict read on a
held-out split) measured held-out top-1 accuracy 0.071 for
keyword-only vs 0.500 for this hybrid — see
~/workspace/hydrotwin_dev_build/status.md. Embeddings are
bge-small-en-v1.5 (Q8_0 GGUF, 384-dim, CLS pooling) served by a
second llama-server in embedding mode; entry vectors are
precomputed at site build time (build25/gen_helper_embeddings.py)
and fetched from the site's own helper/ht-emb.bin together with
helper/ht-index.json, with an md5-of-ids check so a stale asset can
never silently scramble the ranking. ANY failure in this layer
(model, asset, server) skips the rerank and the request is served
exactly as v2 — the rerank can never break or delay the answer
path beyond the one call it rides on.

Serving design (v2, 2026-11-01): a persistent llama-server process
per execution environment. The first design spawned llama-completion
per request, which re-read the whole GGUF from /tmp on every call —
fine for the old 0.5B (469 MB, ~4.5 s warm) but measured ~25 s of
fixed overhead per call for a 2-4 GB model on this account's
3008 MB-capped Lambda (a MemorySize raise was refused by account
quota), putting warm answers at 30-40 s. Now the model loads once
per environment; warm requests only pay prompt processing +
generation (~10 s for the 4B). If llama-server is unavailable for
any reason the handler falls back to the original one-shot
llama-completion path, and any failure still returns 502 so the bot
silently keeps its index answer.

Request  JSON: {"question": str, "context": [{"title","text","page"}, ...]}
Response JSON: {"answer": str, "model": str}
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import boto3

MODEL_BUCKET = os.environ.get("MODEL_BUCKET", "hydrotwin-helper-2026")
MODEL_KEY = os.environ.get(
    "MODEL_KEY", "model/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.gguf")
MODEL_NAME = os.environ.get(
    "MODEL_NAME", os.path.basename(MODEL_KEY).replace(".gguf", "")
)

# Chat-template selection, keyed off the model file so a MODEL_KEY
# rollback to a Qwen file restores ChatML with no code change:
# Llama 3 instruct models use the header/<|eot_id|> template, Qwen
# instruct models use ChatML (<|im_start|>/<|im_end|>).
IS_LLAMA = "llama" in MODEL_NAME.lower()
CHAT_STOP = (["<|eot_id|>", "<|end_of_text|>"] if IS_LLAMA
             else ["<|im_end|>", "<|im_start|>"])
CHAT_REVERSE = "<|eot_id|>" if IS_LLAMA else "<|im_end|>"
# llama.cpp threads. The account's Lambda quota caps MemorySize at
# 3008 MB (a raise to 8192 was refused with a ValidationException on
# 2026-11-01), which is about 1.7 vCPU, so 2 threads is the match;
# the workflow passes LLAMA_THREADS explicitly.
LLAMA_THREADS = os.environ.get("LLAMA_THREADS", "2")
TASK_ROOT = os.environ.get("LAMBDA_TASK_ROOT", os.path.dirname(os.path.abspath(__file__)))
LLAMA_BIN = os.path.join(TASK_ROOT, "llama", "llama-completion")
LLAMA_SERVER_BIN = os.path.join(TASK_ROOT, "llama", "llama-server")
LLAMA_LIB = os.path.join(TASK_ROOT, "llama")

SERVER_PORT = 18080
SERVER_URL = "http://127.0.0.1:%d" % SERVER_PORT
SERVER_START_DEADLINE_S = 240
GEN_TIMEOUT_S = 240

# ---------------------------------------------------- hybrid rerank
EMBED_MODEL_KEY = os.environ.get(
    "EMBED_MODEL_KEY", "model/bge-small-en-v1.5-q8_0.gguf"
)
EMBED_MODEL_PATH = os.environ.get("EMBED_MODEL_PATH", "/tmp/embed-model.gguf")
SITE_BASE = os.environ.get(
    "SITE_BASE", "https://d36737oy6jvpd8.cloudfront.net"
).rstrip("/")
EMBED_PORT = 18091
EMBED_URL = "http://127.0.0.1:%d" % EMBED_PORT
EMBED_START_DEADLINE_S = 120
# Battery-tuned on the dev split (title+text entry embeddings, raw
# question, cosine clipped at 0, keyword score max-normalized):
# hybrid = (1 - W_COS) * kw_norm + W_COS * cos.
HYBRID_W_COS = 0.95
MAX_CANDIDATES = 16
RERANK_TOP_N = 3
EMBED_RETRY_COOLDOWN_S = 60

SYSTEM = (
    "You answer questions about locating information in the HydroTwin "
    "hydrology digital twin. Use only the site entries provided; never "
    "invent pages, panels or stations. Be brief: 2 or 3 short sentences. "
    "Name the page and the panel or control. If the entries do not cover "
    "the question, say plainly what you could not find."
)

MAX_QUESTION_CHARS = 600
MAX_ENTRIES = 3
# Entry text is trimmed: the rephrase only needs the gist of each
# entry — the bot's own index answer keeps the full text on screen
# regardless — and a shorter prompt is faster to process.
MAX_ENTRY_TEXT = 200
MAX_OUTPUT_TOKENS = "128"


def _ensure_model():
    if os.path.exists(MODEL_PATH) and os.path.getsize(MODEL_PATH) > 1_000_000:
        return
    tmp = MODEL_PATH + ".part"
    boto3.client("s3").download_file(MODEL_BUCKET, MODEL_KEY, tmp)
    os.replace(tmp, MODEL_PATH)


def _build_prompt(question, entries):
    lines = []
    for e in entries[:MAX_ENTRIES]:
        title = str(e.get("title", ""))[:160]
        text = str(e.get("text", ""))[:MAX_ENTRY_TEXT]
        page = str(e.get("page", ""))[:120]
        lines.append("- %s: %s (page: %s)" % (title, text, page))
    entries_text = "\n".join(lines) if lines else "(no entries matched)"
    user = "Question: %s\n\nSite index entries:\n%s" % (question, entries_text)
    if IS_LLAMA:
        prompt = (
            "<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n"
            + SYSTEM + "<|eot_id|>"
            "<|start_header_id|>user<|end_header_id|>\n\n"
            + user + "<|eot_id|>"
            "<|start_header_id|>assistant<|end_header_id|>\n\n"
        )
    else:
        prompt = (
            "<|im_start|>system\n" + SYSTEM + "<|im_end|>\n"
            "<|im_start|>user\n" + user + "<|im_end|>\n"
            "<|im_start|>assistant\n"
        )
    return prompt[:7000]


def _clean(out):
    # Defensive cleanup (same as the v1 handler): cut at any chat-token
    # remnant, then strip llama-completion's console marker
    # ("> EOF by user"), which the server path does not emit.
    out = (out or "").split("<|")[0].strip()
    marker = out.rfind("EOF by user")
    if marker != -1:
        out = out[:marker].rstrip().rstrip(">").strip()
    return out


# ------------------------------------------------------- llama-server
_server = {"proc": None}


def _server_healthy():
    proc = _server["proc"]
    if proc is None or proc.poll() is not None:
        return False
    try:
        with urllib.request.urlopen(SERVER_URL + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_server():
    """Start llama-server once per environment and wait for readiness."""
    if _server_healthy():
        return True
    if not os.path.exists(LLAMA_SERVER_BIN):
        return False
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = LLAMA_LIB + ":" + env.get("LD_LIBRARY_PATH", "")
    log = open("/tmp/llama-server.log", "ab")
    proc = subprocess.Popen(
        [
            LLAMA_SERVER_BIN,
            "-m", MODEL_PATH,
            "-c", "2048",
            "-t", LLAMA_THREADS,
            "--host", "127.0.0.1",
            "--port", str(SERVER_PORT),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )
    _server["proc"] = proc
    deadline = time.time() + SERVER_START_DEADLINE_S
    while time.time() < deadline:
        if proc.poll() is not None:
            return False  # died during load; caller falls back to CLI
        if _server_healthy():
            return True
        time.sleep(1.0)
    return False


def _generate_server(prompt):
    body = json.dumps({
        "prompt": prompt,
        "n_predict": int(MAX_OUTPUT_TOKENS),
        "temperature": 0.2,
        "seed": 42,
        "cache_prompt": True,
        "stop": CHAT_STOP,
    }).encode()
    req = urllib.request.Request(
        SERVER_URL + "/completion", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=GEN_TIMEOUT_S) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    return _clean(data.get("content", ""))


# ------------------------------------------------- llama-completion
def _generate_cli(prompt):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = LLAMA_LIB + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.run(
        [
            LLAMA_BIN,
            "-m", MODEL_PATH,
            "-p", prompt,
            "-n", MAX_OUTPUT_TOKENS,
            "-c", "2048",
            "-t", LLAMA_THREADS,
            "--temp", "0.2",
            "--seed", "42",
            "--no-display-prompt",
            "-r", CHAT_REVERSE,
        ],
        capture_output=True,
        text=True,
        timeout=GEN_TIMEOUT_S,
        env=env,
    )
    return _clean(proc.stdout or "")


def _generate(prompt):
    _ensure_model()
    try:
        if _ensure_server():
            return _generate_server(prompt)
    except Exception:
        pass  # any server-path failure falls back to the one-shot CLI
    return _generate_cli(prompt)


# ------------------------------------------------------- rerank layer
_emb_server = {"proc": None}
_emb_data = {"ready": False, "last_try": 0.0, "ids": [], "entries": {},
             "vecs": []}


def _ensure_embed_model():
    if os.path.exists(EMBED_MODEL_PATH) and os.path.getsize(EMBED_MODEL_PATH) > 1_000_000:
        return
    tmp = EMBED_MODEL_PATH + ".part"
    boto3.client("s3").download_file(MODEL_BUCKET, EMBED_MODEL_KEY, tmp)
    os.replace(tmp, EMBED_MODEL_PATH)


def _emb_server_healthy():
    proc = _emb_server["proc"]
    if proc is None or proc.poll() is not None:
        return False
    try:
        with urllib.request.urlopen(EMBED_URL + "/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _ensure_emb_server():
    if _emb_server_healthy():
        return True
    if not os.path.exists(LLAMA_SERVER_BIN):
        return False
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = LLAMA_LIB + ":" + env.get("LD_LIBRARY_PATH", "")
    log = open("/tmp/llama-embed-server.log", "ab")
    proc = subprocess.Popen(
        [
            LLAMA_SERVER_BIN,
            "-m", EMBED_MODEL_PATH,
            "--embedding",
            "--pooling", "cls",
            "-c", "512",
            "-t", LLAMA_THREADS,
            "--host", "127.0.0.1",
            "--port", str(EMBED_PORT),
        ],
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
    )
    _emb_server["proc"] = proc
    deadline = time.time() + EMBED_START_DEADLINE_S
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        if _emb_server_healthy():
            return True
        time.sleep(0.5)
    return False


def _fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ht-helper-lambda"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _load_emb_assets():
    """Fetch the site index + precomputed entry vectors and verify
    they belong together (count + md5 of the id list). Raises on any
    mismatch; the caller treats every failure as 'rerank off'."""
    import hashlib
    import struct
    from array import array

    index = json.loads(_fetch(SITE_BASE + "/helper/ht-index.json").decode("utf-8"))
    entries = index["entries"]
    ids = [str(e.get("id", "")) for e in entries]
    raw = _fetch(SITE_BASE + "/helper/ht-emb.bin")
    if raw[:6] != b"HTEMB1":
        raise ValueError("ht-emb.bin: bad magic")
    n, dim = struct.unpack("<II", raw[6:14])
    if n != len(entries):
        raise ValueError("ht-emb.bin: entry count mismatch")
    if hashlib.md5("\n".join(ids).encode()).digest() != raw[14:30]:
        raise ValueError("ht-emb.bin: id hash mismatch")
    scales = struct.unpack("<%df" % n, raw[30:30 + 4 * n])
    body = raw[30 + 4 * n:30 + 4 * n + n * dim]
    if len(body) != n * dim:
        raise ValueError("ht-emb.bin: truncated vectors")
    vecs = []
    for i in range(n):
        row = array("b")
        row.frombytes(body[i * dim:(i + 1) * dim])
        s = scales[i]
        vecs.append([v * s for v in row])
    _emb_data["ids"] = ids
    _emb_data["entries"] = {e["id"]: e for e in entries}
    _emb_data["vecs"] = vecs
    _emb_data["dim"] = dim


def _ensure_rerank():
    """Best-effort one-time (per environment) rerank setup. Retries
    at most once per cooldown so a not-yet-deployed asset cannot
    latch the layer off for the environment's whole life, and a
    broken asset cannot cause a retry storm."""
    if _emb_data["ready"]:
        return True
    now = time.time()
    if now - _emb_data["last_try"] < EMBED_RETRY_COOLDOWN_S:
        return False
    _emb_data["last_try"] = now
    try:
        _ensure_embed_model()
        _load_emb_assets()
        if not _ensure_emb_server():
            return False
    except Exception:
        return False
    _emb_data["ready"] = True
    return True


def _embed_question(question):
    body = json.dumps({"content": question}).encode()
    req = urllib.request.Request(
        EMBED_URL + "/embedding", data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8", "replace"))
    vec = [float(x) for x in data[0]["embedding"][0]]
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _rerank(question, candidates):
    """Return the top entry ids by hybrid score, or None when the
    rerank layer is unavailable. Pool is the whole index (union):
    candidates contribute their keyword score, everything else
    enters on embedding similarity alone — that recall beyond the
    keyword pool is the measured win."""
    if not _ensure_rerank():
        return None
    kw = {}
    top_score = 0.0
    for c in candidates[:MAX_CANDIDATES]:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("id", ""))
        try:
            score = float(c.get("score", 0))
        except Exception:
            continue
        if cid in _emb_data["entries"] and score > 0:
            kw[cid] = score
            top_score = max(top_score, score)
    qv = _embed_question(question)
    if len(qv) != _emb_data.get("dim", len(qv)):
        return None
    scored = []
    for pos, eid in enumerate(_emb_data["ids"]):
        row = _emb_data["vecs"][pos]
        cos = 0.0
        for a, b in zip(qv, row):
            cos += a * b
        if cos < 0.0:
            cos = 0.0
        kw_norm = (kw.get(eid, 0.0) / top_score) if top_score else 0.0
        scored.append(((1.0 - HYBRID_W_COS) * kw_norm + HYBRID_W_COS * cos, pos))
    scored.sort(key=lambda x: -x[0])  # stable: ties keep index order
    return [_emb_data["ids"][pos] for _, pos in scored[:RERANK_TOP_N]]


def _rss_kb(pid):
    try:
        with open("/proc/%d/status" % pid) as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


def _debug_stats():
    self_kb = _rss_kb(os.getpid())
    child_kb = 0
    try:
        for name in os.listdir("/proc"):
            if not name.isdigit():
                continue
            try:
                with open("/proc/%s/stat" % name) as f:
                    parts = f.read().rsplit(")", 1)[1].split()
                if int(parts[1]) == os.getpid():  # ppid field
                    child_kb += _rss_kb(int(name))
            except Exception:
                continue
    except Exception:
        pass
    return {"rss_self_kb": self_kb, "rss_children_kb": child_kb,
            "emb_ready": bool(_emb_data["ready"])}


def _reply(status, payload):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    try:
        body = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            import base64

            body = base64.b64decode(body).decode("utf-8", "replace")
        req = json.loads(body)
    except Exception:
        return _reply(400, {"error": "invalid JSON body"})

    question = str(req.get("question", "")).strip()[:MAX_QUESTION_CHARS]
    if not question:
        return _reply(400, {"error": "missing question"})
    entries = req.get("context") or []
    if not isinstance(entries, list):
        entries = []
    candidates = req.get("candidates") or []
    if not isinstance(candidates, list):
        candidates = []

    # Hybrid rerank (v3): only when the bot sent its keyword
    # candidates. On success the rephrase is grounded in the
    # reranked top hits and the response carries their order so the
    # bot can adopt it for the answer and the Show me buttons. Any
    # failure leaves `order` None and the request is served exactly
    # as v2 from the client-supplied context.
    order = None
    if candidates:
        try:
            order = _rerank(question, candidates)
        except Exception:
            order = None
    if order:
        reranked = []
        for eid in order:
            e = _emb_data["entries"].get(eid) or {}
            if e:
                reranked.append({
                    "title": e.get("title", ""),
                    "text": e.get("text", ""),
                    "page": e.get("url") or "this page",
                })
        if reranked:
            entries = reranked
        else:
            order = None

    try:
        answer = _generate(_build_prompt(question, entries))
    except subprocess.TimeoutExpired:
        return _reply(502, {"error": "generation timed out"})
    except Exception as exc:  # model load / binary failure: bot falls back
        return _reply(502, {"error": "inference failed: %s" % exc})

    if not answer:
        return _reply(502, {"error": "empty generation"})
    payload = {"answer": answer, "model": MODEL_NAME}
    if order:
        payload["order"] = order
    if req.get("debug"):
        payload["stats"] = _debug_stats()
    return _reply(200, payload)
