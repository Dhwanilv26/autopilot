# Autopilot — AI Coding Agent

> A terminal-based AI agent that understands entire codebases, executes complex multi-step tasks, manages long-running workflows, and operates autonomously within controlled safety limits. Built from scratch in pure Python, so no LangChain, and no abstractions you don't control.

---

## System Architecture

![System Architecture](./system_architecture.png)

The architecture is organised into seven layers that communicate through well-defined data, control, and context flows:

- **User & CLI Interface** — terminal input, prompt_toolkit, command history, Rich-rendered output
- **Agent Core** — the orchestration loop, subagent system, retry/backoff, loop detection, and execution state
- **Tool System** — every environment interaction is a typed tool call; no raw side effects
- **LLM Layer** — OpenRouter, local models (Ollama/LMStudio), custom endpoints, streaming and non-streaming
- **Safety & Approval** — risk detection, path validation, shell safety, approval policies
- **Context Management** — compaction, pruning, token tracking, continuity across long sessions
- **Persistence** — session manager, checkpoint system, local storage layer

---

## Overview

Autopilot implements a complete agent system from first principles:

- Custom agent loop with full execution control
- Typed tool calling system with pre-execution validation
- Context management — compaction and pruning for long sessions
- Session and checkpoint persistence — save, resume, restore any state
- Subagents for isolated execution of complex sub-workflows
- MCP-based extensibility — connect any external tool server
- Safety and approval controls at every execution boundary

The system runs continuously until a task is completed or safely terminated, maintaining correctness and avoiding uncontrolled behaviour throughout.

---

## Installation

Install from PyPI:

```bash
pip install autopilot-agent
```

PyPI page: https://pypi.org/project/autopilot/

---

## Configuration

Create a `.env` file in your project root. Choose one of the following provider options.

**Option 1 — OpenRouter**

```bash
OPENROUTER_API_KEY=your_api_key
BASE_URL=https://openrouter.ai/api/v1
```

**Option 2 — Local model (Ollama, LMStudio, or any OpenAI-compatible endpoint)**

```bash
BASE_URL=http://localhost:11434/v1
```

---

## Usage

```bash
autopilot
```

Starts the interactive CLI. Type a task in plain English and the agent takes it from there.

---

## Agent Loop

The core execution loop is fully custom-built. On each iteration it:

1. Interprets user intent and decomposes the task into steps
2. Selects the appropriate tool from the registered tool system
3. Validates arguments before execution
4. Executes the action and captures structured output
5. Updates context, checks for loop conditions, and decides the next step

The loop runs until the task is marked complete, a safety condition is triggered, or the user interrupts.

---

## Tool System

All environment interaction is done strictly through tools — no direct filesystem or shell access outside the tool boundary. This makes every action auditable, approvable, and reversible.

**File operations**

| Tool | Description |
|---|---|
| `read_file` | Read file contents with line range control |
| `write_file` | Create or overwrite a file |
| `edit_file` | Precise string replacement within a file |

**Search and navigation**

| Tool | Description |
|---|---|
| `grep` | Content search with pattern matching |
| `glob` | File discovery by pattern |
| `list_dir` | Directory listing with tree view |

**Execution**

| Tool | Description |
|---|---|
| `shell` | Run commands, scripts, and capture output |

**Web**

| Tool | Description |
|---|---|
| `web_search` | Search the web |
| `web_fetch` | Fetch and extract content from URLs |

**Planning and memory**

| Tool | Description |
|---|---|
| `todos` | Task tracking with priority and status |
| `memory` | Persistent key-value store across turns |

---

## Context Management

Designed for large codebases and long-running sessions where the raw conversation history would exceed the model's context window.

**Compaction** summarises older interactions into a dense representation that preserves meaning without keeping every raw token. **Pruning** removes tool outputs that are no longer relevant to the current task. Token usage is tracked continuously, and compaction is triggered automatically before the context limit is reached. The agent maintains full task continuity without losing thread.

---

## Safety and Approval System

Every action goes through a risk evaluation before execution. The approval policy controls how much autonomy the agent is given.

| Policy | Behaviour |
|---|---|
| `auto` | Executes all tool calls without prompting |
| `on-request` | Prompts for confirmation on flagged operations |
| `never` | Blocks all tool execution — planning only |
| `yolo` | No restrictions, no confirmations |

Additional safety mechanisms:

- **Risk detection** — flags destructive or irreversible shell commands before they run
- **Path validation** — prevents reads and writes outside the declared working directory
- **Command safety layer** — evaluates shell commands against a risk model before execution
- **User confirmation** — prompts on critical operations when `on-request` is active

---

## Session and Checkpoints

The agent's full execution state — conversation history, tool call log, todos, memory, current task — can be saved and restored at any point.

- **Sessions** — save a complete session and resume it in a future run
- **Checkpoints** — snapshot the state mid-task and restore any previous snapshot
- **Persistent continuity** — long multi-day workflows survive restarts without losing context

---

## Subagents

For tasks too complex for a single linear loop, Autopilot can spawn specialised subagents in isolated execution contexts. Each subagent gets its own tool set, context window, and task scope, then reports its result back to the parent agent.

Useful for:

- Large codebase refactors where different modules need independent analysis
- Parallel code review and audit tasks
- Deep root-cause investigations that need isolated exploration
- Any workflow where separation of concerns reduces error propagation

---

## MCP Integration

Autopilot supports the Model Context Protocol for dynamic tool extension without modifying the core system. Any MCP-compatible tool server can be connected at startup.

- **Transport support** — stdio (local processes) and HTTP/SSE (remote servers)
- **Dynamic registration** — tools discovered at connection time and registered into the tool system automatically
- **Schema forwarding** — full input schemas including types, enums, and descriptions are passed to the model to minimise argument errors

---

## Loop Detection

The agent monitors its own execution trace for stuck or repetitive patterns — calling the same tool with the same arguments repeatedly, producing no observable progress. When a loop is detected:

- Execution is paused
- The agent generates a self-correction prompt
- If correction fails, the loop is terminated safely with a diagnostic message

This prevents runaway token consumption on stuck tasks.

---

## Terminal UI

Built on [Rich](https://github.com/Textualize/rich) and [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit).

- Streaming token output rendered live
- Structured tool call panels — arguments on start, results and diffs on completion
- Syntax-highlighted file contents and diffs
- Colour-coded tool kinds (read, write, shell, network, memory)
- Todos rendered as priority-grouped Rich tables
- Subagent output rendered as nested Markdown panels

---

## Commands

| Command | Description |
|---|---|
| `/help` | Show help and usage |
| `/config` | View current configuration |
| `/model` | Switch the active model |
| `/tools` | List all registered tools |
| `/mcp` | Show connected MCP servers and their tools |
| `/stats` | Session analytics — token usage, tool calls, timing |
| `/save` | Save the current session |
| `/resume` | Resume a previously saved session |
| `/checkpoint` | Create a checkpoint at the current state |
| `/restore` | Restore a previous checkpoint |
| `/history` | Browse conversation and tool call history |
| `/exit` | Exit the agent |

---

## Tech Stack

- **Language** — Python 3.11+
- **LLM access** — OpenRouter, Ollama, LMStudio, any OpenAI-compatible endpoint
- **Terminal UI** — Rich, prompt_toolkit
- **Tool extensibility** — MCP (Model Context Protocol)
- **No agent framework** — the loop, tool system, context manager, and safety layer are all written from scratch for full control and transparency

---

## High-Impact Use Cases

### Full codebase refactoring

```
"Migrate this entire project from JavaScript to TypeScript and fix all type errors"
```

The agent maps the project structure, updates `tsconfig` and build configs, converts files in dependency order, resolves import paths, fixes type errors iteratively, and verifies consistency across the codebase — without you touching a single file.

### End-to-end feature implementation

```
"Add JWT authentication with refresh tokens"
```

The agent analyses the existing architecture, creates middleware and route handlers, updates database models, wires the auth layer into existing endpoints, and writes the relevant tests.

### Deep debugging and root cause analysis

```
"Find why this API randomly fails under load in production"
```

The agent traces execution paths through the codebase, inspects related modules and configurations, identifies race conditions or resource contention, and proposes targeted fixes.

### Codebase audit and technical debt review

```
"Audit this project for security issues and outdated dependencies"
```

A subagent is spawned per module, each performing isolated analysis. Results are aggregated into a prioritised report with specific file references and suggested remediations.