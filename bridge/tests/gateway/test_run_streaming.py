import asyncio
from types import SimpleNamespace as NS
from forsch.adk_bridge.run import tokens_from_events


def _part(text, thought=False):
    return NS(text=text, thought=thought)


def _event(parts, partial=False, final=False):
    return NS(content=NS(parts=parts), partial=partial, is_final_response=lambda: final)


async def _aiter(*events):
    for e in events:
        yield e


async def _collect(agen):
    return [t async for t in agen]


def test_streaming_excludes_thought_parts():
    ev = _event([_part("reasoning about it", thought=True), _part("The answer.", thought=False)], partial=True)
    fin = _event([], final=True)
    out = asyncio.run(_collect(tokens_from_events(_aiter(ev, fin))))
    assert out == ["The answer."]


def test_nonstreaming_final_excludes_thought_parts():
    fin = _event([_part("thinking", thought=True), _part("Final answer.", thought=False)], partial=False, final=True)
    out = asyncio.run(_collect(tokens_from_events(_aiter(fin))))
    assert out == ["Final answer."]
