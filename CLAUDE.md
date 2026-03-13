# nagare (流れ - "flow")

## Project Overview

nagare is a unified CLI tool / workspace manager for managing `tmux` sessions and `ccode` instances. It eliminates friction in context switching and provides intelligent monitoring/notification for background processes across sessions.

See `docs/NAGARE.md` for the full spec.

## Tech Stack

- **Language:** Python (3.14+)
- **Project Manager:** `uv` — use `uv` for all dependency management, virtual environments, and running scripts. Do NOT use pip or poetry.
- **TUI Framework:** [Textual](https://textual.textualize.io/) — this is a **critical dependency**. Textual is the foundation for all UI rendering in this project. Before writing any UI code, you MUST understand Textual's widget system, layout model, reactive attributes, message handling, and CSS-based styling. Read the official docs at https://textual.textualize.io/ when in doubt.
- **Core Dependencies:** `tmux`, `ccode`, Unix shell

## IMPORTANT: Textual Library

Textual is not just another dependency — it is the **core framework** driving the entire user interface of nagare. Every interactive element (session lists, status displays, notifications, dashboards) will be built with Textual.

Key Textual concepts you must be familiar with:
- **App & Screen** lifecycle
- **Widgets** (built-in and custom)
- **CSS styling** (Textual uses its own CSS dialect for layout and theming)
- **Message passing** and event handling
- **Reactive attributes** for state management
- **Command palette** integration
- **Testing** with `pilot` for headless TUI testing

Official docs: https://textual.textualize.io/

## Key Features

- **Session Management:** Create, list, attach to tmux sessions with automatic ccode initialization
- **State Monitoring:** Background daemon polling job status in detached tmux sessions
- **Notification System:** Alerts when sessions need attention (OS notifications, terminal bells, tmux status bar)
- **Smart Jump:** Instant teleport to the most urgent session

## CLI Commands

- `nagare init <project>` — bootstrap new tmux session + ccode
- `nagare ls` — list sessions with status indicators
- `nagare go <project>` — fast switch to project
- `nagare next` — jump to session needing attention
- `nagare daemon` — start background monitor

## Git Conventions

- Do NOT include "Co-Authored-By" lines or any mention of Claude/AI in commit messages.

## Development

```bash
# Add dependencies
uv add <package>

# Run the project
uv run python main.py

# Run tests
uv run pytest
```
