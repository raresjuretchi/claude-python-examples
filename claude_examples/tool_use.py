"""Let Claude call your own Python functions (tool use).

    python -m claude_examples.tool_use "What is 18.5% of 2,340 and what time is it in Tokyo?"

The loop: send the request with tool definitions → if Claude stops with
"tool_use", run the requested tools and send the results back → repeat until
Claude answers in plain text.
"""
from __future__ import annotations

import ast
import datetime as dt
import json
import operator
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from claude_examples.common import DEFAULT_MODEL, MAX_TOKENS, get_client, prompt_from_args, text_of

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calculate(expression: str) -> float:
    """Safely evaluate an arithmetic expression (no names, no calls)."""

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            left, right = ev(node.left), ev(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("exponent too large")
            return _OPS[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.operand))
        raise ValueError("only numbers and + - * / // % ** are allowed")

    return ev(ast.parse(expression.replace(",", ""), mode="eval"))


def current_time(timezone: str) -> str:
    try:
        return dt.datetime.now(ZoneInfo(timezone)).strftime("%Y-%m-%d %H:%M %Z")
    except ZoneInfoNotFoundError:
        raise ValueError(f"unknown time zone {timezone!r}; use an IANA name like Europe/Madrid")


TOOLS = [
    {
        "name": "calculate",
        "description": (
            "Evaluates an arithmetic expression and returns the numeric result. Use it for any "
            "calculation instead of doing math in your head. Supports + - * / // % ** and "
            "parentheses; thousands separators are ignored. Percentages must be written as "
            "multiplication, e.g. 18.5% of 2340 → 2340 * 0.185."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "e.g. (2340 * 0.185) + 12"}},
            "required": ["expression"],
        },
    },
    {
        "name": "current_time",
        "description": (
            "Returns the current local date and time in a given IANA time zone, such as "
            "Europe/Madrid or Asia/Tokyo. Use it whenever the user asks what time or date it is "
            "somewhere. It does not convert arbitrary times."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"timezone": {"type": "string", "description": "IANA zone, e.g. Asia/Tokyo"}},
            "required": ["timezone"],
        },
    },
]

HANDLERS = {"calculate": calculate, "current_time": current_time}


def run_tool(name: str, args: dict) -> tuple[str, bool]:
    """Run a tool and return (content, is_error)."""
    try:
        return json.dumps({"result": HANDLERS[name](**args)}), False
    except Exception as exc:  # report errors back to Claude instead of crashing
        return f"Error: {exc}", True


def run(client, prompt: str, model: str = DEFAULT_MODEL, max_rounds: int = 8, log=print) -> str:
    messages: list[dict] = [{"role": "user", "content": prompt}]
    for _ in range(max_rounds):
        response = client.messages.create(model=model, max_tokens=MAX_TOKENS, tools=TOOLS, messages=messages)
        if response.stop_reason != "tool_use":
            return text_of(response)
        # Keep Claude's full turn (text, thinking and tool calls) in the history.
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                content, is_error = run_tool(block.name, block.input)
                log(f"  [tool] {block.name}({block.input}) -> {content}")
                results.append({"type": "tool_result", "tool_use_id": block.id,
                                "content": content, "is_error": is_error})
        messages.append({"role": "user", "content": results})
    raise RuntimeError(f"no final answer after {max_rounds} tool rounds")


def main() -> None:
    prompt = prompt_from_args("What is 18.5% of 2,340, and what time is it in Tokyo right now?")
    print(run(get_client(), prompt))


if __name__ == "__main__":
    main()
