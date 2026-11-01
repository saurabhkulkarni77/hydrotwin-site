"""HydroTwin helper-bot inference Lambda.

Hosts an open source instruct model (GGUF Q4_K_M, stored in a private
S3 bucket; MODEL_KEY selects the file — Qwen3-4B-Instruct-2507 since
2026-11-01) behind llama.cpp, invoked only through the Lambda
Function URL by the dev site's helper bot.

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
        "stop": ["<|im_end|>", "<|im_start|>"],
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
            "-r", "<|im_end|>",
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

    try:
        answer = _generate(_build_prompt(question, entries))
    except subprocess.TimeoutExpired:
        return _reply(502, {"error": "generation timed out"})
    except Exception as exc:  # model load / binary failure: bot falls back
        return _reply(502, {"error": "inference failed: %s" % exc})

    if not answer:
        return _reply(502, {"error": "empty generation"})
    return _reply(200, {"answer": answer, "model": MODEL_NAME})
