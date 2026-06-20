"""Shared runtime helpers: resilient Runner calls, trace URLs, evidence persistence.

The deck's production checklist lists a fallback path [SDK 105]; a small org TPM cap makes 429s
routine, so we retry with bounded backoff rather than crash. Evidence persistence implements
"if you cannot trace it, you cannot govern it" [Intro 94], [SDK 83-86] → [[tracing-and-evidence]].
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import openai
from agents import Runner

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def run_with_retry(*args, **kwargs):
    """`Runner.run` with bounded exponential backoff on transient API errors."""
    delay = 3.0
    last_exc: Exception | None = None
    for _ in range(5):
        try:
            return await Runner.run(*args, **kwargs)
        except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as exc:
            last_exc = exc
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)
    raise last_exc  # type: ignore[misc]


def trace_url(trace_id: str) -> str:
    return f"https://platform.openai.com/traces/trace?trace_id={trace_id}"


def write_evidence(packet: dict, out_dir: str | Path, name: str) -> Path:
    """Persist an evidence packet as JSON. Returns the path."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.json"
    path.write_text(json.dumps(packet, indent=2, default=str), encoding="utf-8")
    return path
