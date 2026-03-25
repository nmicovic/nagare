# Agent Messaging — Design

## Overview

Inter-agent messaging for nagare via MCP server. Claude Code sessions can send questions to other sessions and receive responses. Uses file-based message storage, tmux send-keys for delivery, and blocking poll for response waiting.

## Architecture

- **MCP server** (`src/nagare/mcp_server.py`) — stdio-based MCP server using the `mcp` Python SDK. Claude Code spawns one per session as a child process.
- **Message store** — JSON files in `~/.local/share/nagare/messages/<target_session>/`. Completed messages stay for history.
- **Delivery** — `tmux send-keys` to type a prompt into the receiver's pane when they're IDLE.
- **Registration** — `nagare setup` adds the MCP server to `~/.claude/settings.json` under `mcpServers`.
- **History UI** — Ctrl+m in the picker opens message history view (future).

## MCP Tools

| Tool | Who | Description |
|------|-----|-------------|
| `list_agents` | anyone | List registered sessions with name, path, agent type, status |
| `ask_agent(target, message, timeout=120)` | sender | Send question, block until response or timeout |
| `check_messages` | receiver | List pending/delivered messages for this session |
| `reply(message_id, content)` | receiver | Write response to a message |

## Message Format

```
~/.local/share/nagare/messages/
  cosmiclab-backend/         # per-target directories
    msg_<uuid>.json
  history/                   # future: for nagare TUI management
```

```json
{
  "id": "msg_<uuid>",
  "from_session": "cosmiclab-frontend",
  "to_session": "cosmiclab-backend",
  "content": "Can you give me the latest API_DOCS.md?",
  "status": "pending",
  "response": null,
  "created_at": "2026-03-24T10:00:00Z",
  "responded_at": null
}
```

Status transitions: `pending` → `delivered` (send-keys fired) → `completed` (response written).

## Flow

```
Sender Claude                      MCP Server                         Receiver Claude
     |                                  |                                    |
     |-- ask_agent("backend", "...") -->|                                    |
     |                                  |-- scan_sessions() → find pane      |
     |                                  |-- check status → must be IDLE      |
     |                                  |-- write msg.json (pending)          |
     |                                  |-- send-keys → "check messages"  -->|
     |                                  |-- update msg.json (delivered)       |
     |                                  |-- poll msg.json every 2s...        |
     |                                  |                                    |-- check_messages()
     |                                  |                                    |-- reads msg.json
     |                                  |                                    |-- reply(id, content)
     |                                  |                                    |-- updates msg.json (completed)
     |                                  |<-- poll finds completed            |
     |<-- returns response -------------|                                    |
```

## Key Decisions

- **IDLE-only delivery**: If target is not IDLE, return error immediately. Don't queue.
- **Blocking poll**: Sender's `ask_agent()` polls every 2s with configurable timeout (default 120s).
- **No cleanup by MCP**: MCP server never deletes messages. History managed by nagare TUI (Ctrl+m in picker).
- **Self-identification**: MCP server resolves "who am I?" by matching its cwd against the session registry.
- **Reuses nagare modules**: scanner, state, registry, run_tmux — no duplication.

## Setup

`nagare setup` adds to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "nagare": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/nagare", "python", "-m", "nagare.mcp_server"]
    }
  }
}
```

## Future

- Ctrl+m in picker: message history view (browse, filter, delete)
- Async `send_message()` for fire-and-forget
- Group messages (broadcast to multiple agents)
