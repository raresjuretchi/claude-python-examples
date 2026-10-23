"""Multi-turn chat in the terminal. The full history is sent on every turn.

    python -m claude_examples.chat
Type 'exit' or press Ctrl+D to quit.
"""
from claude_examples.common import DEFAULT_MODEL, MAX_TOKENS, get_client, text_of

SYSTEM = "You are a concise, friendly assistant. Prefer short answers unless asked for detail."


class Conversation:
    def __init__(self, client, model: str = DEFAULT_MODEL, system: str = SYSTEM):
        self.client = client
        self.model = model
        self.system = system
        self.messages: list[dict] = []

    def send(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        reply = self.client.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=self.system,
            messages=self.messages,
        )
        self.messages.append({"role": "assistant", "content": reply.content})
        return text_of(reply)


def main() -> None:
    chat = Conversation(get_client())
    print(f"Chatting with {chat.model}. Type 'exit' to quit.")
    while True:
        try:
            user = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user.lower() in {"exit", "quit"}:
            break
        if user:
            print(f"\nclaude> {chat.send(user)}")


if __name__ == "__main__":
    main()
