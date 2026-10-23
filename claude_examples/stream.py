"""Stream Claude's reply token by token.

    python -m claude_examples.stream "Write a haiku about cloud migrations"
"""
from claude_examples.common import DEFAULT_MODEL, MAX_TOKENS, get_client, prompt_from_args


def stream_reply(client, prompt: str, model: str = DEFAULT_MODEL, out=print) -> str:
    chunks = []
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            chunks.append(text)
            out(text, end="", flush=True)
    out()
    return "".join(chunks)


def main() -> None:
    stream_reply(get_client(), prompt_from_args("Write a short poem about the Mediterranean sea."))


if __name__ == "__main__":
    main()
