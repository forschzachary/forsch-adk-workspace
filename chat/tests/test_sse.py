from forsch.adk_chat.sse import iter_sse_content


def test_extracts_content_deltas_and_stops_on_done():
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"}}]}',
        'data: {"choices":[{"delta":{"content":"lo"}}]}',
        'data: {"choices":[{"delta":{}}]}',
        'data: [DONE]',
    ]
    assert list(iter_sse_content(lines)) == ["Hel", "lo"]


def test_ignores_blank_and_non_data_lines():
    assert list(iter_sse_content(["", ": ping", 'data: {"choices":[{"delta":{"content":"x"}}]}'])) == ["x"]
