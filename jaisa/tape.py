"""Tape's work: a voice note in, Dadi's words out, each with its second.

AWS Transcribe batch, mr-IN (Marathi), through the aws CLI on profile
`hackathon`. The audio and the transcript go to one private bucket
(JAISA_BUCKET) and are never written into the repo. Transcribe writes Marathi
numbers as words; Pothi's lexicon reads them.
"""

import json
import os
import re
import subprocess
import tempfile
import time
import uuid

from .check import Word

BUCKET = os.environ.get("JAISA_BUCKET", "")
VOCABULARY = os.environ.get("JAISA_VOCABULARY", "")
_AWS_ENV = {"AWS_PROFILE": "hackathon", "AWS_REGION": "ap-south-1"}
MAX_BYTES = 20 * 1024 * 1024  # Switch's own default attachment cap
MAX_SECONDS = 600
_FORMATS = {"ogg": "ogg", "oga": "ogg", "opus": "ogg", "mp3": "mp3", "m4a": "mp4", "mp4": "mp4", "wav": "wav", "flac": "flac", "webm": "webm", "amr": "amr"}


def _aws(*args, stdin: bytes = None) -> bytes:
    env = {**os.environ, **{k: os.environ.get(k, v) for k, v in _AWS_ENV.items()}}
    proc = subprocess.run(["aws", *args], input=stdin, capture_output=True, env=env, timeout=300)
    if proc.returncode != 0:
        raise RuntimeError(f"aws {args[0]} {args[1]}: exit {proc.returncode}: {proc.stderr.decode()[:300]}")
    return proc.stdout


def media_format(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in _FORMATS:
        raise ValueError(f"not a voice note: .{ext}")
    return _FORMATS[ext]


def probe(audio: bytes) -> float:
    """Seconds of audio, read from the bytes by ffprobe, never from the filename
    or mimetype. ValueError if it isn't audio we take."""
    if not 0 < len(audio) <= MAX_BYTES:
        raise ValueError("size")
    # a file, not a pipe: ffprobe needs to seek to find an Ogg's duration
    with tempfile.NamedTemporaryFile(prefix="tape-") as f:
        f.write(audio)
        f.flush()
        proc = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", f.name],
            capture_output=True, timeout=30,
        )
    try:
        info = json.loads(proc.stdout or b"{}")
        seconds = float(info["format"]["duration"])
    except (ValueError, KeyError, TypeError):
        raise ValueError("not audio") from None
    if proc.returncode != 0 or not any(st.get("codec_type") == "audio" for st in info.get("streams", [])):
        raise ValueError("not audio")
    if any(st.get("codec_type") == "video" for st in info.get("streams", [])):
        raise ValueError("has video")
    if not 0 < seconds <= MAX_SECONDS:
        raise ValueError("length")
    return seconds


def words(transcript: dict) -> list:
    """Transcribe's output JSON -> Words. Punctuation items are dropped.

    A custom-vocabulary phrase comes back as one hyphenated token ("पाव-किलो",
    seen live Thu 5 Nov). It is split into its words, each at the token's start,
    so Pothi's lexicon sees "पाव" (a number) and "किलो" (a unit)."""
    out = []
    for item in transcript.get("results", {}).get("items", []):
        if item.get("type") != "pronunciation":
            continue
        alts = item.get("alternatives") or [{}]
        t = round(float(item.get("start_time", 0)), 2)
        for w in str(alts[0].get("content", "")).strip().split("-"):
            if w.strip():
                out.append(Word(len(out), w.strip(), t))
    return out


def transcribe(audio: bytes, filename: str, poll: float = 5, timeout: float = 900, vocabulary: str = None) -> list:
    if not BUCKET:
        raise RuntimeError("JAISA_BUCKET is not set")
    fmt = media_format(filename)
    job = f"jaisa-{uuid.uuid4().hex[:12]}"
    key = f"audio/{job}.{filename.rsplit('.', 1)[-1].lower()}"
    _aws("s3", "cp", "-", f"s3://{BUCKET}/{key}", "--sse", "AES256", "--only-show-errors", stdin=audio)
    args = [
        "transcribe", "start-transcription-job",
        "--transcription-job-name", job,
        "--language-code", "mr-IN",
        "--media-format", fmt,
        "--media", f"MediaFileUri=s3://{BUCKET}/{key}",
        "--output-bucket-name", BUCKET,
        "--output-key", f"transcripts/{job}.json",
    ]
    vocabulary = VOCABULARY if vocabulary is None else vocabulary
    if vocabulary:
        args += ["--settings", f"VocabularyName={vocabulary}"]
    _aws(*args)
    deadline = time.monotonic() + timeout
    while True:
        status = json.loads(_aws("transcribe", "get-transcription-job", "--transcription-job-name", job))
        state = status["TranscriptionJob"]["TranscriptionJobStatus"]
        if state == "COMPLETED":
            break
        if state == "FAILED":
            raise RuntimeError(f"transcribe {job}: {status['TranscriptionJob'].get('FailureReason', '')[:300]}")
        if time.monotonic() > deadline:
            raise TimeoutError(f"transcribe {job}: still {state}")
        time.sleep(poll)
    raw = _aws("s3", "cp", f"s3://{BUCKET}/transcripts/{job}.json", "-", "--only-show-errors")
    return words(json.loads(raw))


# The tape document Tape writes into the room: one word per line, "[i] seconds word".
_DOC_LINE = re.compile(r"^\[(\d+)\]\s+(\d+(?:\.\d+)?)\s+(\S+)$")


def to_doc(tape) -> str:
    return "\n".join(f"[{w.i}] {w.t:.2f} {w.w}" for w in tape)


def from_doc(text: str) -> list:
    """Parse a tape document. Any line out of shape or out of order -> ValueError."""
    tape = []
    for line in text.strip().splitlines():
        m = _DOC_LINE.match(line.strip())
        if not m or int(m.group(1)) != len(tape):
            raise ValueError(f"tape line {len(tape)} is malformed")
        tape.append(Word(len(tape), m.group(3), float(m.group(2))))
    return tape


def mmss(t: float) -> str:
    t = int(t)
    return f"{t // 60:02d}:{t % 60:02d}"
