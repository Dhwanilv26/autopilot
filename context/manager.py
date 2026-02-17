from prompts.system import get_system_prompt
from dataclasses import dataclass

from utils.text import count_tokens


@dataclass
class MessageItem:
    role: str
    content: str
    token_count: int | None = None


class ContextManager:
    def __init__(self) -> None:
        self._system_prompt = get_system_prompt()
        self._model_name = "nvidia/nemotron-3-nano-30b-a3b:free"
        self._messages = list[MessageItem] = []

    # token count varies for each model and provider
    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role="user",
            content=content,
            token_count=count_tokens(content, model=self._model_name)
        )

        self._messages.append(item)

    def add_assistant_message(self, content: str) -> None:
        item = MessageItem(
            role="assistant",
            content=content or "",
            token_count=count_tokens(content, model=self._model_name)
        )

        self._messages.append(item)
