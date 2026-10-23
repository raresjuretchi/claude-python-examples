# Claude Python Examples

[![CI](https://github.com/raresjuretchi/claude-python-examples/actions/workflows/ci.yml/badge.svg)](https://github.com/raresjuretchi/claude-python-examples/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

Small, runnable scripts showing the essentials of the [Claude API](https://platform.claude.com/docs) with the official `anthropic` Python SDK: a single request, streaming, a multi-turn chat and tool use (letting Claude call your own Python functions).

## Quick start

```bash
git clone https://github.com/raresjuretchi/claude-python-examples.git
cd claude-python-examples
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your key in .env
python -m claude_examples.hello "Explain a cloud landing zone in two sentences"
```

Get an API key from the [Claude Console](https://platform.claude.com/).

## The scripts

| Script | What it shows |
|---|---|
| `python -m claude_examples.hello "…"` | One request, one reply |
| `python -m claude_examples.stream "…"` | Streaming the reply as it is generated |
| `python -m claude_examples.chat` | Multi-turn chat in the terminal, with a system prompt |
| `python -m claude_examples.tool_use "…"` | Tool use: Claude calls a safe calculator and a time-zone clock |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | Your API key (required) |
| `CLAUDE_MODEL` | `claude-opus-5-5` | Model ID; try `claude-sonnet-5-5` or `claude-haiku-5-5` for lower cost |
| `CLAUDE_MAX_TOKENS` | `8192` | Output budget per reply, including the model's thinking |

## How the tool-use loop works

1. Send the conversation plus the tool definitions (`TOOLS` in `tool_use.py`).
2. If the reply stops with `stop_reason == "tool_use"`, run each requested tool locally.
3. Append Claude's whole turn and a `tool_result` block per call, then send again.
4. Stop when Claude answers in plain text.

Tool errors are sent back to Claude as `is_error` results rather than crashing the script, so it can correct itself.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use a fake client, so they run offline and need no API key.

## Maintenance

A scheduled workflow checks the pinned dependencies once a week at a random time, bumps them when the tests still pass and records the result in [MAINTENANCE.md](MAINTENANCE.md).

<!-- maintenance:start -->
**Last maintenance:** not run yet
<!-- maintenance:end -->

## License

MIT — see [LICENSE](LICENSE).
