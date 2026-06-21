"""Parse OpenAI-compatible chat/completions SSE lines into content deltas."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator


def iter_sse_content(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            return
        try:
            delta = json.loads(payload)["choices"][0].get("delta", {})
        except (ValueError, KeyError, IndexError):
            continue
        text = delta.get("content")
        if text:
            yield text
