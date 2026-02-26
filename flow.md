🧠 SAMPLE PROMPT

User types:

please read main.py

Assume:

Tool available: read_file(path: str)

Model decides to call tool.

🏗 FULL ARCHITECTURE LAYERS
┌────────────────────────────┐
│          main.py           │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│         agent.py           │
│   (Agent.run async gen)    │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│      llm_client.py         │
│ chat_completion async gen  │
└─────────────┬──────────────┘
              │
              ▼
┌────────────────────────────┐
│     OpenAI Streaming       │
└────────────────────────────┘

Two event systems exist:

OpenAI raw chunk
    ↓
StreamEvent (response.py)
    ↓
AgentEvent (events.py)
    ↓
main.py prints
🔁 COMPLETE FLOW — STEP BY STEP
STEP 0 — Program Starts

📁 main.py

async for event in agent.run(user_input):
    print(event)

So:

main.py is the top-level consumer.

STEP 1 — Agent Starts

📁 agent.py

Inside run():

yield AgentEvent.agent_start(...)

⬆ goes to main.py
⬆ printed

STEP 2 — Agent Calls LLM
async for stream_event in llm_client.chat_completion(...):

Now control moves to:

📁 llm_client.py

STEP 3 — LLMClient Calls OpenAI
response = await client.chat.completions.create(stream=True)

Now OpenAI begins streaming.

STEP 4 — OpenAI Sends Tool Call Start Chunk

Raw chunk from OpenAI:

{
  "choices": [{
    "delta": {
      "tool_calls": [{
        "index": 0,
        "id": "call_abc",
        "function": { "name": "read_file" }
      }]
    }
  }]
}
STEP 5 — LLMClient Reconstructs Tool

📁 _stream_response

if delta.tool_calls:
    tool_calls[0] = {
        id: "call_abc",
        name: "read_file",
        arguments: ""
    }

    yield StreamEvent(TOOL_CALL_START)

So:

StreamEvent(type=TOOL_CALL_START)

⬆ goes to agent.py

STEP 6 — Agent Converts StreamEvent → AgentEvent

📁 agent.py

if event.type == TOOL_CALL_START:
    yield AgentEvent.tool_call_start(...)

⬆ goes to main.py
⬆ printed

STEP 7 — OpenAI Finishes Tool Call

OpenAI sends finish_reason:

finish_reason = "tool_calls"

LLMClient does:

yield StreamEvent(TOOL_CALL_COMPLETE)
yield StreamEvent(MESSAGE_COMPLETE)
STEP 8 — Agent Receives MESSAGE_COMPLETE

Agent sees:

finish_reason == "tool_calls"

This means:

🧠 MODEL WANTS TOOL EXECUTION

STEP 9 — Agent Executes Tool

📁 agent.py

for tool_call in collected_tool_calls:
    result = await tool.execute(...)

Assume tool returns:

File content of main.py

Agent then:

yield AgentEvent.tool_call_complete(...)

⬆ printed in main.py

STEP 10 — Agent Appends Tool Result to Messages

Conversation becomes:

[
  { role: "user", content: "please read main.py" },
  { role: "assistant", tool_calls: [...] },
  { role: "tool", tool_call_id: "call_abc", content: "file content here" }
]
STEP 11 — Agent Calls LLM AGAIN

Recursive loop:

async for stream_event in llm_client.chat_completion(updated_messages):

This is Claude-style tool loop.

STEP 12 — Model Streams Final Answer

OpenAI streams:

Here is the content of main.py:
...

LLMClient yields:

StreamEvent(TEXT_DELTA)

Agent converts:

AgentEvent.text_delta(...)

⬆ printed in main.py

This continues until:

finish_reason = "stop"
STEP 13 — Agent Emits AGENT_END

Agent does:

yield AgentEvent.agent_end(...)

main.py prints it.

Loop exits.

🔁 FULL RECURSIVE LOOP DIAGRAM
User Input
    │
    ▼
Agent.run()
    │
    ├── yield AGENT_START
    │
    ├── call LLM
    │      │
    │      ▼
    │  LLMClient.chat_completion()
    │      │
    │      ▼
    │  OpenAI Stream
    │      │
    │      ▼
    │  StreamEvent(s)
    │      │
    │      ▼
    │  Agent converts to AgentEvent(s)
    │
    ├── if finish_reason == tool_calls
    │       │
    │       ├── execute tools
    │       ├── append tool results
    │       └── call LLM again (recursive)
    │
    └── if finish_reason == stop
            │
            └── yield AGENT_END
🔄 WHERE ASYNC & YIELD FIT
await

Used when:

Calling OpenAI

Executing tool

Waiting for network

It pauses without blocking.

yield

Used when:

Sending event upward

Streaming partial output

Control flow:

yield → pause and send upward
await → pause and wait downward
🔥 FILE RESPONSIBILITIES SUMMARY
File	Responsibility
response.py	LLM transport events
llm_client.py	OpenAI communication
events.py	Agent lifecycle events
agent.py	Tool loop orchestration
main.py	Entry point & printing
🎯 MENTAL MODEL (Final)

Think of it like this:

OpenAI speaks in fragments
LLMClient translates fragments
Agent decides what to do
main.py displays decisions

The agent sits in the middle.

🧠 FINAL ARCHITECTURE MAP (Compact)
main.py
  ↓
Agent.run()  ← AgentEvent layer
  ↓
LLMClient.chat_completion() ← StreamEvent layer
  ↓
OpenAI SDK

Tool execution happens inside Agent layer only.

You now have:

Streaming transport

Tool reconstruction

Agent orchestration

Recursive LLM loop capability

This is exactly how Claude-style systems work internally.