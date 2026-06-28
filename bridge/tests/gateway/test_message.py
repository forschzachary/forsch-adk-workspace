from forsch.adk_bridge.gateway.message import CanonicalMessage


def test_minimal_message_defaults():
    m = CanonicalMessage(source="discord", sender="discord:42", text="hello")
    assert m.source == "discord"
    assert m.sender == "discord:42"
    assert m.text == "hello"
    assert m.target is None
    assert m.session_id is None
    assert m.attachments == []
    assert m.raw is None


def test_attachments_are_independent_per_instance():
    a = CanonicalMessage(source="sms", sender="+15551234567", text="x")
    b = CanonicalMessage(source="sms", sender="+15559999999", text="y")
    a.attachments.append("file://1")
    assert b.attachments == []


def test_existing_buffers_are_renderers():
    from forsch.adk_bridge.gateway.adapter import Renderer
    from forsch.adk_bridge.bridge import StreamBuffer, TextBuffer
    assert isinstance(TextBuffer(), Renderer)
    class _Chan:
        id = 1
    assert isinstance(StreamBuffer(_Chan()), Renderer)
