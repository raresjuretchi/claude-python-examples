"""Send one message to Claude and print the reply.

    python -m claude_examples.hello "Explain landing zones in two sentences"
"""
from claude_examples.common import DEFAULT_MODEL, MAX_TOKENS, get_client, prompt_from_args, text_of


def ask(client, prompt: str, model: str = DEFAULT_MODEL) -> str:
    message = client.messages.create(
        model=model,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    return text_of(message)


def main() -> None:
    prompt = prompt_from_args("Say hello and tell me one surprising fact about octopuses.")
    print(ask(get_client(), prompt))


if __name__ == "__main__":
    main()
