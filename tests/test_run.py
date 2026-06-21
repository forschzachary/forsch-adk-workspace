import asyncio
import types as pytypes
from forsch.adk_bridge.run import tokens_from_events


class _Part:
    def __init__(self, text): self.text = text
class _Content:
    def __init__(self, parts): self.parts = parts
class _Event:
    def __init__(self, texts, final=False):
        self.content = _Content([_Part(t) for t in texts]) if texts else None
        self._final = final
    def is_final_response(self): return self._final


async def _agen(events):
    for e in events:
        yield e


def test_tokens_from_events_yields_text_until_final():
    events = [_Event(["Hel", "lo"]), _Event([" there"]), _Event([], final=True)]
    out = asyncio.run(_collect(_agen(events)))
    assert out == ["Hel", "lo", " there"]


async def _collect(agen):
    return [t async for t in __import__("forsch.adk_bridge.run", fromlist=["tokens_from_events"]).tokens_from_events(agen)]
