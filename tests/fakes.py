"""Tiny stand-ins for the Anthropic client so tests run offline without an API key."""
from types import SimpleNamespace


def text(t):
    return SimpleNamespace(type="text", text=t)


def thinking(t="..."):
    return SimpleNamespace(type="thinking", thinking=t)


def tool_use(id_, name, input_):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=input_)


def message(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


class FakeMessages:
    def __init__(self, replies=(), stream_chunks=()):
        self.replies = list(replies)
        self.stream_chunks = list(stream_chunks)
        self.calls = []

    def create(self, **kwargs):
        # Snapshot the message list: callers keep appending to the same list.
        self.calls.append({**kwargs, "messages": list(kwargs.get("messages", []))})
        return self.replies.pop(0)

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        chunks = self.stream_chunks

        class _Stream:
            text_stream = iter(chunks)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        return _Stream()


class FakeClient:
    def __init__(self, replies=(), stream_chunks=()):
        self.messages = FakeMessages(replies, stream_chunks)
