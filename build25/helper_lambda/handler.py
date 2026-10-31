"""HydroTwin helper-bot inference Lambda.

Hosts Qwen2.5-0.5B-Instruct (GGUF Q4_K_M, stored in a private S3 bucket)
and runs it with a bundled llama.cpp `llama-completion` binary built for
Amazon Linux 2023. The model is downloaded to /tmp on cold start and
reused on warm starts. No always-on resources; invoked only through the
Lambda Function URL by the dev site's helper bot.

Request  JSON: {"question": str, "context": [{"title","text","page"}, ...]}
Response JSON: {"answer": str, "model": str}
"""

import json
import os
import subprocess

import boto3

MODEL_BUCKET = os.environ.get("MODEL_BUCKET", "hydrotwin-helper-2026")
MODEL_KEY = os.environ.get(
    "MODEL_KEY", "model/qwen2.5-0.5b-instruct-q4_k_m.gguf"
)
MODEL_PATH = os.environ.get("MODEL_PATH", "/tmp/model.gguf")
MODEL_NAME = "qwen2.5-0.5b-instruct-q4_k_m"
TASK_ROOT = os.environ.get("LAMBDA_TASK_ROOT", os.path.dirname(os.path.abspath(__file__)))
LLAMA_BIN = os.path.join(TASK_ROOT, "llama", "llama-completion")
LLAMA_LIB = os.path.join(TASK_ROOT, "llama")

SYSTEM = (
    "You answer questions about locating information in the HydroTwin "
    "hydrology digital twin. Use only the site entries provided; never "
    "invent pages, panels or stations. Be brief: 2 or 3 short sentences. "
    "Name the page and the panel or control. If the entries do not cover "
    "the question, say plainly what you could not find."
)

MAX_QUESTION_CHARS = 600
MAX_ENTRIES = 5
MAX_ENTRY_TEXT = 600
MAX_OUTPUT_TOKENS = "192"
GEN_TIMEOUT_S = 100


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


def _generate(prompt):
    env = dict(os.environ)
    env["LD_LIBRARY_PATH"] = LLAMA_LIB + ":" + env.get("LD_LIBRARY_PATH", "")
    proc = subprocess.run(
        [
            LLAMA_BIN,
            "-m", MODEL_PATH,
            "-p", prompt,
            "-n", MAX_OUTPUT_TOKENS,
            "-c", "2048",
            "-t", "2",
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
    out = proc.stdout or ""
    # Defensive cleanup: cut at any chat-token remnant and trim.
    out = out.split("<|")[0].strip()
    return out


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
        _ensure_model()
        answer = _generate(_build_prompt(question, entries))
    except subprocess.TimeoutExpired:
        return _reply(502, {"error": "generation timed out"})
    except Exception as exc:  # model load / binary failure: bot falls back
        return _reply(502, {"error": "inference failed: %s" % exc})

    if not answer:
        return _reply(502, {"error": "empty generation"})
    return _reply(200, {"answer": answer, "model": MODEL_NAME})
