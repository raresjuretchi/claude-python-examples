import json

import pytest

from claude_examples import chat, hello, stream, tool_use
from claude_examples.common import text_of
from tests.fakes import FakeClient, message, text, thinking, tool_use as tool_block


def test_text_of_skips_thinking_blocks():
    assert text_of(message(thinking(), text("Hello"), text(" world"))) == "Hello world"


def test_hello_sends_prompt_and_returns_text():
    client = FakeClient([message(text("Hi!"))])
    assert hello.ask(client, "hello", model="m") == "Hi!"
    call = client.messages.calls[0]
    assert call["model"] == "m"
    assert call["messages"] == [{"role": "user", "content": "hello"}]


def test_stream_collects_chunks():
    printed = []
    client = FakeClient(stream_chunks=["Hel", "lo"])
    result = stream.stream_reply(client, "hi", out=lambda *a, **k: printed.append(a))
    assert result == "Hello"


def test_conversation_keeps_history():
    client = FakeClient([message(text("one")), message(text("two"))])
    convo = chat.Conversation(client)
    assert convo.send("first") == "one"
    assert convo.send("second") == "two"
    roles = [m["role"] for m in convo.messages]
    assert roles == ["user", "assistant", "user", "assistant"]
    assert client.messages.calls[1]["system"] == chat.SYSTEM


@pytest.mark.parametrize("expr,expected", [("2 + 3 * 4", 14), ("2,340 * 0.185", 432.9), ("-(2 ** 3)", -8)])
def test_calculate(expr, expected):
    assert tool_use.calculate(expr) == pytest.approx(expected)


@pytest.mark.parametrize("expr", ["__import__('os')", "open('x')", "2 ** 10000"])
def test_calculate_rejects_unsafe_input(expr):
    with pytest.raises(ValueError):
        tool_use.calculate(expr)


def test_current_time_rejects_unknown_zone():
    with pytest.raises(ValueError):
        tool_use.current_time("Mars/Olympus")


def test_tool_loop_runs_tools_and_returns_answer():
    client = FakeClient([
        message(thinking(), tool_block("t1", "calculate", {"expression": "2340 * 0.185"}), stop_reason="tool_use"),
        message(text("It is 432.9."), stop_reason="end_turn"),
    ])
    answer = tool_use.run(client, "What is 18.5% of 2340?", log=lambda *_: None)
    assert answer == "It is 432.9."

    second_call = client.messages.calls[1]["messages"]
    assert second_call[1]["role"] == "assistant"
    result = second_call[2]["content"][0]
    assert result["type"] == "tool_result" and result["tool_use_id"] == "t1"
    assert json.loads(result["content"])["result"] == pytest.approx(432.9)
    assert result["is_error"] is False


def test_tool_errors_are_reported_not_raised():
    content, is_error = tool_use.run_tool("current_time", {"timezone": "Nowhere/Land"})
    assert is_error and content.startswith("Error:")


def test_tool_loop_gives_up_after_max_rounds():
    loop_reply = message(tool_block("t", "calculate", {"expression": "1+1"}), stop_reason="tool_use")
    client = FakeClient([loop_reply] * 3)
    with pytest.raises(RuntimeError):
        tool_use.run(client, "loop", max_rounds=3, log=lambda *_: None)
