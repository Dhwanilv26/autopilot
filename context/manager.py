from typing import Any
from client.response import TokenUsage
from config.config import Config
from prompts.system import get_system_prompt
from dataclasses import dataclass, field
from tools.base import Tool
from utils.text import count_tokens
from datetime import datetime


@dataclass
class MessageItem:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    token_count: int | None = None
    pruned_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"role": self.role}

        if self.tool_call_id:
            result["tool_call_id"] = self.tool_call_id

        if self.tool_calls:
            result["tool_calls"] = self.tool_calls

        if self.content:
            result["content"] = self.content

        return result


class ContextManager:
    PRUNE_PROTECT_TOKENS = 40_000  # keeping 40K tokens of the most recent tool outputs
    PRUNE_MINIMUM_TOKENS = 20_000  # last mai context ke pass 20K tool_call output ke tokens to hone hi chahiye

    def __init__(self, config: Config, user_memory: str | None, tools: list[Tool] | None) -> None:

        self.config = config

        self._system_prompt = get_system_prompt(config, user_memory, tools)

        self._messages: list[MessageItem] = []

        # ✅ tracking usage
        self._latest_usage = TokenUsage(0, 0, 0, 0)   # last LLM call
        self._total_usage = TokenUsage(0, 0, 0, 0)    # cumulative session usage

    @property
    def message_count(self) -> int:
        return len(self._messages)

    @property
    def total_usage(self) -> TokenUsage:
        return self._total_usage or TokenUsage(0, 0, 0, 0)

    @total_usage.setter
    def total_usage(self, value):
        self._total_usage = value
        # -------------------------------
        # Message Adders
        # -------------------------------

    def add_user_message(self, content: str) -> None:
        item = MessageItem(
            role="user",
            content=content,
            token_count=count_tokens(content, model=self.config.model_name or "openrouter/free")
        )
        self._messages.append(item)

    def add_assistant_message(self, content: str, tool_calls: list[dict[str, Any]] | None = None) -> None:
        if not content and not tool_calls:
            return

        item = MessageItem(
            role="assistant",
            content=content or "",
            token_count=count_tokens(
                content or "", model=self.config.model_name or "openrouter/free"),
            tool_calls=tool_calls or []
        )
        self._messages.append(item)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        item = MessageItem(
            role="tool",
            content=content,
            tool_call_id=tool_call_id,
            token_count=count_tokens(content, model=self.config.model_name or "openrouter/free")
        )
        self._messages.append(item)

    def get_messages(self) -> list[dict[str, Any]]:
        messages = []

        if self._system_prompt:
            messages.append({
                "role": "system",
                "content": self._system_prompt
            })

        for item in self._messages:
            messages.append(item.to_dict())

        return messages

    def _estimate_context_tokens(self) -> int:
        """
        Better approximation of actual context size.
        Uses stored token_count instead of latest_usage.
        """
        total = 0

        if self._system_prompt:
            total += count_tokens(self._system_prompt,
                                  model=self.config.model_name or "openrouter/free")

        for msg in self._messages:
            if msg.token_count:
                total += msg.token_count

        return total

    def needs_compression(self) -> bool:
        context_limit = self.config.model.context_window
        # this checks what amount of tokens I am about to send to the lLM, and not accounting the previous history and all
        # and in the next request we are always sending everything, as nothing gets stored in the memory
        # ✅ FIX: use estimated input tokens instead of latest_usage.total_tokens
        current_tokens = self._estimate_context_tokens()

        return current_tokens > (context_limit * 0.8)

    # -------------------------------
    # Usage Tracking
    # -------------------------------

    def set_latest_usage(self, usage: TokenUsage):
        self._latest_usage = usage

    def add_usage(self, usage: TokenUsage):
        if self._total_usage is None:
            self._total_usage = TokenUsage(0, 0, 0, 0)
        self._total_usage += usage

    def replace_context_with_summary(self, summary: str) -> None:
        self._messages = []

        continuation_content = f"""# Context Restoration (Previous Session Compacted)

        The previous conversation was compacted due to context length limits. Below is a detailed summary of the work done so far. 

        **CRITICAL: Actions listed under "COMPLETED ACTIONS" are already done. DO NOT repeat them.**

        ---

        {summary}

        ---

        Resume work from where we left off. Focus ONLY on the remaining tasks."""

        summary_item = MessageItem(
            role="user",
            content=continuation_content,
            token_count=count_tokens(continuation_content,
                                     self.config.model_name or "openrouter/free")
        )

        self._messages.append(summary_item)

        # just gaslighting the LLM that you have done this
        ack_content = """I've reviewed the context from the previous session. I understand:
- The original goal and what was requested
- Which actions are ALREADY COMPLETED (I will NOT repeat these)
- The current state of the project
- What still needs to be done

I'll continue with the REMAINING tasks only, starting from where we left off."""

        ack_item = MessageItem(
            role="assistant",
            content=ack_content,
            token_count=count_tokens(ack_content, self.config
                                     .model_name or "openrouter/free")
        )

        self._messages.append(ack_item)
        # needed, because if the last role is assistant, the LLM may not stream, so need a user role for the last message
        continue_content = (
            "Continue with the REMAINING work only. Do NOT repeat any completed actions. "
            "Proceed with the next step as described in the context above."
        )

        continue_item = MessageItem(
            role="user",
            content=continue_content,
            token_count=count_tokens(continue_content, self.config.model_name or "openrouter/free")
        )

        self._messages.append(continue_item)

    def prune_tool_outputs(self) -> int:

        user_message_count = sum(1 for msg in self._messages if msg.role == "user")

        if user_message_count < 2:
            return 0

        total_tokens: int = 0
        pruned_tokens: int = 0
        to_prune: list[MessageItem] = []

        # assistant role sirf tool call karega, usme itne tokens nai udte
        # tool role mai tool_call output hota hai, that costs a lot more tokens, to usko prune karna padega
        for msg in reversed(self._messages):
            if msg.role == "tool" and msg.tool_call_id:
                if msg.pruned_at:
                    break  # we dont wanna prune same messages
                tokens = msg.token_count or count_tokens(
                    msg.content, self.config.model_name or "openrouter/free")
                total_tokens += tokens

                if total_tokens > self.PRUNE_PROTECT_TOKENS:
                    # agar total_tokens 40K se bahd gaye to voh ud jaayenge, recent tool outputs will be safe
                    pruned_tokens += tokens
                    to_prune.append(msg)

        if pruned_tokens < self.PRUNE_MINIMUM_TOKENS:
            # insufficient tokens to prune (20K se kam tokens hai to pruning is not worthy)
            return 0

        pruned_count: int = 0

        for msg in to_prune:
            msg.content = '[Old tool result content cleared]'
            msg.pruned_at = datetime.now()
            msg.token_count = count_tokens(msg.content, self.config.model_name or "openrouter/free")
            pruned_count += 1

        return pruned_count

    def clear(self) -> None:
        self._messages = []
        self.total_usage = None  # type: ignore

    async def load_from_snapshot(self, snapshot) -> None:
        """
        Rebuild context state from a snapshot by replaying messages.
        """

        if not snapshot or not getattr(snapshot, "messages", None):
            return
        # Optional: clear existing state before loading
        self.clear()

        # Restore usage safely
        usage = getattr(snapshot, "total_usage", None)
        if usage:
            # handle dict → object case
            if isinstance(usage, dict):
                usage = TokenUsage(**usage)
            self.total_usage = usage  # type: ignore

        # Local references (micro-optimization)
        add_user = self.add_user_message
        add_assistant = self.add_assistant_message
        add_tool = self.add_tool_result

        for msg in snapshot.messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                continue

            elif role == "user":
                add_user(content)

            elif role == "assistant":
                add_assistant(content, msg.get("tool_calls"))

            elif role == "tool":
                add_tool(
                    msg.get("tool_call_id", ""),
                    content
                )
