from forsch.adk_chat.claudewrap import map_block


class _Text:  # mimics claude_agent_sdk.TextBlock
    def __init__(self, text): self.text = text
class _Tool:  # mimics ToolUseBlock
    def __init__(self, name, inp): self.name = name; self.input = inp
class _Result:  # mimics ToolResultBlock
    def __init__(self, content): self.content = content


def test_text_block_maps_to_token():
    assert map_block(_Text("hi")) == ("token", "hi")

def test_tool_use_maps_to_tool():
    kind, name, inp = map_block(_Tool("Bash", {"command": "ls"}))
    assert (kind, name) == ("tool", "Bash") and inp == {"command": "ls"}

def test_tool_result_maps_to_result():
    assert map_block(_Result("done"))[0] == "tool_result"

def test_unknown_block_maps_to_none():
    assert map_block(object()) is None
