import httpx
import pytest
from forsch.adk_chat.hubert import build_messages, stream_hubert


def test_build_messages_prepends_soul_system():
    msgs = build_messages("you are hubert", [{"role": "user", "content": "hi"}])
    assert msgs[0] == {"role": "system", "content": "you are hubert"}
    assert msgs[-1] == {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_stream_hubert_yields_content():
    sse = (b'data: {"choices":[{"delta":{"content":"he"}}]}\n\n'
           b'data: {"choices":[{"delta":{"content":"llo"}}]}\n\n'
           b'data: [DONE]\n\n')

    def handler(req):
        assert req.url.path == "/v1/chat/completions"
        assert req.headers["authorization"] == "Bearer K"
        return httpx.Response(200, content=sse)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://lite")
    out = []
    async for tok in stream_hubert(client, "http://lite", "K", "gpt-5.5",
                                   [{"role": "user", "content": "hi"}], system="S"):
        out.append(tok)
    assert "".join(out) == "hello"
    await client.aclose()
