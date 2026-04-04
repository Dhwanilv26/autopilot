# Autopilot — AI Coding Agent (Built from First Principles)

Autopilot is a terminal-based AI agent that can **understand codebases, execute tasks using tools, manage long-running workflows, and operate autonomously within controlled limits**.

It is built entirely in Python **without using frameworks like LangChain**, focusing on **control, transparency, and reliability**.

---

## Overview

This project implements a **complete agent system from scratch**, including:

* Custom agent loop
* Tool calling system
* Context management (compaction + pruning)
* Session and checkpoint persistence
* Sub-agents for complex tasks
* MCP-based extensibility
* Safety and approval controls

The system is designed to run continuously until tasks are completed, while maintaining correctness and avoiding uncontrolled behavior.

---

## Features

### Core Functionality

* Interactive CLI mode for continuous workflows
* Single-run mode for one-off tasks
* Streaming and non-streaming LLM responses
* Multi-turn conversations with tool execution
* Retry mechanism with exponential backoff
* Configurable model, temperature, and behavior

---

### Agent Loop

* Fully custom-built agent execution loop
* Iteratively:

  * understands user input
  * selects tools
  * executes actions
  * updates context
* Runs until the task is completed or safely terminated

---

### Tool System

The agent interacts with the environment strictly through tools.

#### File Operations

* Read files (`read_file`)
* Write new files (`write_file`)
* Edit files (`edit_file`)

#### Directory & Search

* List directories (`list_dir`)
* Search by pattern (`glob`)
* Search by content (`grep`)

#### Execution

* Run shell commands (`shell`)

#### Web Access

* Web search (`web_search`)
* Fetch web pages (`web_fetch`)

#### Planning & Memory

* Task tracking (`todos`)
* Persistent memory (`memory`)

---

### Context Management

Handles long-running conversations and large codebases:

* **Compaction**: summarizes past interactions
* **Pruning**: removes unnecessary tool outputs
* Token usage tracking
* Maintains continuity across long sessions

---

### Safety and Approval System

* Multiple approval policies:

  * `auto`
  * `on-request`
  * `never`
  * `yolo`
* Detection of risky operations
* Path validation for file access
* User confirmation before mutating actions
* Safe handling of shell commands

---

### Session and Checkpoint Management

* Save full session state
* Resume previous sessions
* Create checkpoints during execution
* Restore system to any checkpoint
* Persistent storage across runs

---

### Subagents

* Ability to spawn specialized agents for complex tasks
* Built-in use cases:

  * codebase investigation
  * code review
* Isolated execution contexts
* Configurable tool access and limits

---

### MCP Integration (Model Context Protocol)

* Connect external MCP servers
* Use third-party tools dynamically
* Supports:

  * stdio transport
  * HTTP / SSE transport
* Enables extensibility without modifying core system

---

### Loop Detection

* Detects repeated or stuck behavior
* Prevents infinite execution loops
* Injects corrective prompts to recover

---

### Hooks System

* Execute scripts at key stages:

  * before/after agent execution
  * before/after tool calls
* Useful for logging, automation, and integrations

---

### Configuration System

* Configurable working directory
* Tool allowlisting
* Developer instructions
* User instructions
* Shell policies
* MCP server configuration
* Model configuration

---

### User Interface (Terminal UI)

Built using Rich and prompt_toolkit:

* Real-time streaming responses
* Structured tool output visualization
* Command system for interaction
* Clean terminal rendering

#### Commands

```
/help
/config
/tools
/mcp
/stats
/save
/sessions
/resume
/checkpoint
/checkpoints
/restore
/history
/history-clear
```

---

### Command History

* Persistent history across sessions
* Arrow key navigation (↑ ↓)
* Auto-suggestions
* History trimming and clearing

---

## Architecture

```
CLI (Click + prompt_toolkit)
        ↓
Agent Loop
        ↓
LLM (OpenRouter / local models)
        ↓
Tool Registry
        ↓
Tool Execution
        ↓
Context Manager
        ↓
TUI (Rich)
```

---

## Tech Stack

* Language: Python
* LLM Access: OpenRouter / local models
* CLI: Click, prompt_toolkit
* UI: Rich
* Architecture: Custom (no LangChain)

---

## Design Decisions

* Built without LangChain to maintain full control
* Tools are the only interface to the environment
* Context is actively managed (not passively accumulated)
* Safety is enforced through approval layers
* System is designed for long-running autonomous tasks

---

## Setup

### 1. Clone Repository

```bash
git clone <your-repo-url>
cd autopilot
```

---

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 3. Configure Environment

Create a `.env` file:

#### Using OpenRouter

```
OPENROUTER_API_KEY=your_api_key
BASE_URL=https://openrouter.ai/api/v1
```

#### Using Local Models

```
BASE_URL=http://localhost:11434/v1
```

---

### 4. Run

```bash
python main.py
```

---

## Example Usage

```
Create a file test.txt with content "hello world"
```

```
Search for all functions related to authentication
```

```
Refactor project structure and update imports
```

---

## Scope of the Project

This project covers the full lifecycle of building an AI agent system:

* LLM integration
* CLI application design
* Tool system architecture
* Context management
* Safety systems
* Multi-agent orchestration
* Persistence and recovery
* Extensibility through MCP

---

## Summary

Autopilot demonstrates how to build a **complete AI agent system from scratch**, focusing on:

* reliability
* control
* extensibility

It is designed as a foundation for building **real-world autonomous coding agents** without relying on high-level frameworks.
