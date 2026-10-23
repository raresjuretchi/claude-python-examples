"""Shared helpers: client creation, model selection and response parsing."""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Override with CLAUDE_MODEL, e.g. claude-sonnet-5-5 or claude-haiku-5-5 for lower cost.
DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-5-5")
# Current models think adaptively before answering; leave room for that.
MAX_TOKENS = int(os.getenv("CLAUDE_MAX_TOKENS", "8192"))


def get_client():
    """Return an Anthropic client; exits with a hint if no API key is set."""
    import anthropic

    if not os.getenv("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key.")
    return anthropic.Anthropic()


def text_of(message) -> str:
    """Join the text blocks of a Message, skipping thinking and tool blocks."""
    return "".join(block.text for block in message.content if getattr(block, "type", None) == "text")


def prompt_from_args(default: str) -> str:
    """Use the command-line arguments as the prompt, or a default."""
    return " ".join(sys.argv[1:]).strip() or default
