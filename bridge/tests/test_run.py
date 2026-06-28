import asyncio
from forsch.adk_bridge.run import tokens_from_events


class _Part:
    def __init__(self, text): self.text = text
class _Content:
    def __init__(self, parts): self.parts = parts
class _Event:
    def __init__(self, texts, final=False, partial=False):
        self.content = _Content([_Part(t) for t in texts]) if texts else None
        self.partial = partial
        self._final = final
    def is_final_response(self): return self._final


async def _agen(events):
    for e in events:
        yield e

async def _collect(agen):
    return [t async for t in tokens_from_events(agen)]


def test_streaming_yields_deltas_not_final_aggregate():
    # Real ADK SSE shape: partial deltas, then a final event repeating the FULL text.
    # The final aggregate must NOT be re-emitted (that was the double-reply bug).
    events = [
        _Event(["Hel"], partial=True),
        _Event(["lo"], partial=True),
        _Event(["Hello"], final=True),
    ]
    assert asyncio.run(_collect(_agen(events))) == ["Hel", "lo"]


def test_non_streaming_emits_final_text_once():
    # No partial deltas (non-streaming run): the final event is the only text-bearer.
    events = [_Event(["Hello"], final=True)]
    assert asyncio.run(_collect(_agen(events))) == ["Hello"]
