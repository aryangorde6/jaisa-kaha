"""Lekhak's brain: one Bedrock call that turns Tape's numbered words into a draft.

The draft holds word citations, not quantities. Pothi checks every one of
them against the tape, so nothing here is trusted. Calls go through the aws
CLI (profile `hackathon`, Mumbai). The request goes in a mode-600 temp file,
deleted after the call, so the transcript never shows up in a process list
or a log.
"""

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

MODEL = os.environ.get("LEKHAK_MODEL", "qwen.qwen3-235b-a22b-2507-v1:0")
PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
_AWS_ENV = {"AWS_PROFILE": "hackathon", "AWS_REGION": "ap-south-1"}


def numbered(tape) -> str:
    return " ".join(f"[{w.i}]{w.w}" for w in tape)


def prompt(name: str, tape) -> str:
    template = (PROMPTS / f"{name}.txt").read_text()
    return template.replace("{words}", numbered(tape)).replace("{text}", " ".join(w.w for w in tape))


def prompt_hash(name: str) -> str:
    return hashlib.sha256((PROMPTS / f"{name}.txt").read_bytes()).hexdigest()


def converse(text: str, model: str = MODEL, max_tokens: int = 2000) -> str:
    request = {
        "modelId": model,
        "messages": [{"role": "user", "content": [{"text": text}]}],
        "inferenceConfig": {"temperature": 0, "maxTokens": max_tokens},
    }
    env = {**os.environ, **{k: os.environ.get(k, v) for k, v in _AWS_ENV.items()}}
    # mkstemp makes the file 0600; the CLI can't read the request from stdin
    with tempfile.NamedTemporaryFile("w", suffix=".json", prefix="lekhak-") as f:
        json.dump(request, f)
        f.flush()
        proc = subprocess.run(
            ["aws", "bedrock-runtime", "converse", "--cli-input-json", f"file://{f.name}", "--output", "json"],
            capture_output=True,
            text=True,
            env=env,
            timeout=180,
        )
    if proc.returncode != 0:
        # stderr names the error class; it never holds the transcript
        raise RuntimeError(f"bedrock {model}: exit {proc.returncode}: {proc.stderr.strip()[:300]}")
    out = json.loads(proc.stdout)
    return "".join(c.get("text", "") for c in out["output"]["message"]["content"])


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$")


def parse(text: str):
    """The draft as a dict, or None. Takes the outermost {...}, fences or not."""
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        draft = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return draft if isinstance(draft, dict) else None


def write_draft(tape, model: str = MODEL):
    """(draft or None, raw model text)."""
    raw = converse(prompt("lekhak-v1", tape), model)
    return parse(raw), raw
