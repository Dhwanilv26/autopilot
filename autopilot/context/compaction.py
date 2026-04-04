from typing import Any

from autopilot.client.llm_client import LLMClient
from autopilot.client.response import StreamEventType, TokenUsage
from autopilot.context.manager import ContextManager
from autopilot.prompts.system import get_compaction_prompt


class ChatCompactor:
    def __init__(self, client: LLMClient) -> None:
        self.client = client

    def _format_history_for_compaction(self, messages: list[dict[str, Any]]) -> str:
        # tool → 2000 chars
        # assistant → 3000 chars
        # user → 1500 chars

        output = ['Here is the conversation that needs to be continued: \n']

        for msg in messages:
            # we are running through each msg (so sabka hi role and content hoga na)
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                continue

            if role == "tool":
                # not adding actual toolcall to save TOKENS ofc
                # tool role mai actual tool output hoga
                tool_id = msg.get("tool_call_id", "unknown")

                truncated = content[:2000] if len(content) > 2000 else content

                if len(content) > 2000:
                    truncated += "\n... [tool output truncated]"

                output.append(f"[Tool result ({tool_id})]:\n{truncated}")

            elif role == "assistant":
                # ONLY ASSISTANT HAS THE CAPABILITIES TO CALL THE TOOLS BASED ON ITS REASONING CAPABILITES (SEE SCHEMA @ EOF)
                tool_details = []
                truncated = ""
                if content:
                    truncated = content[:3000] if len(content) > 3000 else content

                    if len(content) > 3000:
                        truncated += "\n... [response truncateed]"

                output.append(f"Assistant: \n{truncated}")
                if msg.get("tool_calls"):
                    for tc in msg["tool_calls"]:
                        func = tc.get("function", {})
                        name = func.get("name", "unknown")
                        args = func.get("arguments", "{}")

                        if len(args) > 500:
                            args = args[:500]
                        tool_details.append(f" {name}({args})")

                output.append("assistant called tools:\n" + "\n".join(tool_details))

            else:  # user role
                truncated = content[:1500] if len(content) > 1500 else content
                if len(content) > 1500:
                    truncated += "\n... [response truncated]"
                output.append(f"user:\n{truncated}")

        return "\n\n---\n\n".join(output)

    async def compress(self, context_manager: ContextManager) -> tuple[str | None, TokenUsage | None]:
        # returning summary and tokenusage
        messages = context_manager.get_messages()

        if len(messages) < 3:
            return None, None

        compression_messages = [
            {
                "role": "system",
                "content": get_compaction_prompt()
            },
            {
                "role": "user",
                "content": self._format_history_for_compaction(messages)
            }
        ]

        try:
            summary = ""
            usage = None
            # telling agent to run for the compressed messages now and return the summary and the token usage
            async for event in self.client.chat_completion(
                compression_messages,
                stream=False
            ):
                if event.type == StreamEventType.MESSAGE_COMPLETE:
                    usage = event.usage
                    if event.text_delta:
                        summary += event.text_delta.content

            if not summary or not usage:
                return None, None

            return summary, usage
        except Exception:
            return None, None


# {
#     "role": "assistant",
#     "content": None,  # or partial text
#     "tool_calls": [
#         {
#             "id": "call_1",
#             "type": "function",
#             "function": {
#                 "name": "get_weather",
#                 "arguments": "{\"city\": \"Ahmedabad\"}"
#             }
#         }
#     ]
# }
