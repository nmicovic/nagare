# nagare (流れ - "flow")

## Project Overview

nagare is a tmux-integrated CLI tool for managing multiple Claude Code sessions. It provides a rich TUI picker for switching between sessions, live-streaming previews of what each session is doing, real-time state detection via Claude Code hooks, and tmux notifications when sessions need attention.

The core workflow: the user runs many Claude Code instances across tmux sessions simultaneously. nagare lets them see all sessions at a glance, monitor progress, get notified when input is needed, and jump to the right session instantly — all from a single keybinding (`prefix + g`).

## Architecture

### Systems

- **Picker (`pick.py`, `pick.tcss`)** — The main TUI. Split-pane layout: left side has a searchable session list + dashboard stats, right side has session details + live-streaming tmux pane preview. Launched as a fullscreen tmux popup. Refreshes session states every 2s and preview every 1s.

- **Hook Handler (`hooks.py`)** — Receives Claude Code lifecycle events (UserPromptSubmit, Stop, Notification, PreToolUse, SessionStart, SessionEnd) via stdin JSON. Writes state files to `~/.local/share/nagare/states/<session_id>.json`. Determines notification event type (`needs_input` or `task_complete`), loads config, resolves per-session overrides, and dispatches to delivery functions. Cleans up stale dead state files on new session start.

- **Notification Delivery (`notifications/deliver.py`)** — Four delivery methods: `send_toast()` (tmux status bar), `send_bell()` (terminal bell), `send_os_notify()` (native OS notification with WSL detection), `send_popup()` (rich popup TUI via tmux display-popup). All fire-and-forget with silent error handling.

- **Popup Notification (`popup_notif.py`)** — Small Textual TUI launched by `tmux display-popup`. Shows status icon, session name, event details, Claude's last message. Enter jumps to session, Esc dismisses, auto-dismisses after configurable timeout with countdown.

- **Notification Store (`notifications/store.py`)** — JSON-file backed store for notification history with read/unread tracking.

- **State Reader (`state.py`)** — Reads hook-written state files keyed by project path (cwd). Resolves conflicts when multiple sessions share the same cwd by preferring live states over dead ones, and most recent timestamps among equals.

- **Scanner (`tmux/scanner.py`)** — Discovers tmux sessions, finds Claude Code panes across all windows (`list-panes -s`), combines hook state with pane-scraping fallback for status detection.

- **Status Detection (`tmux/status.py`)** — Fallback pane content scraping when hooks haven't fired yet. Detects idle prompts, choice/confirmation dialogs, running spinners.

- **History (`history.py`)** — Reads `~/.claude/history.jsonl` for conversation topics per project.

- **Notification Center (`notifs.py`)** — ListView-based TUI for viewing stored notifications. Launched via `prefix + e`.

- **Themes (`themes.py`)** — Multiple tokyonight variants + other themes. Cyclable with `Ctrl+t` in picker.

### State Flow

```
Claude Code hooks → stdin JSON → hooks.py → state files (JSON)
                                          → config check (per-event, per-session)
                                          → delivery: toast / bell / os_notify / popup
                                          → notification store (JSON)

Picker poll (2s) → scanner.py → state.py (read state files) → UI update
Picker poll (1s) → tmux capture-pane → preview panel update
```

### Notification Events

- **needs_input** — Claude needs user action (permission prompt, elicitation dialog). Configurable: toast, bell, os_notify, popup.
- **task_complete** — Claude finished after working longer than `min_working_seconds` (default 30s). Prevents spam from quick responses.

### Session Status Semantics

- **NEEDS INPUT** (red) — Claude is waiting for user action (permission prompt, elicitation dialog)
- **WORKING** (yellow) — Claude is actively processing (after user prompt submit or tool use)
- **IDLE** (green) — Claude finished and is at the prompt
- **DEAD** (gray) — Session ended

## Tech Stack

- **Language:** Python (3.14+)
- **Project Manager:** `uv` — use `uv` for all dependency management, virtual environments, and running scripts. Do NOT use pip or poetry.
- **TUI Framework:** [Textual](https://textual.textualize.io/) — core framework for all UI. Uses its own CSS dialect for layout/theming, Rich markup for styled text, message passing for events, `set_interval` for polling.
- **Core Dependencies:** `tmux`, `claude` (Claude Code CLI), Unix shell

## User Preferences

- **Theme:** tokyonight. Colors should blend with this palette.
- **IDLE green:** `#00D26A` for both icon and label text.
- **Status icons:** Rich-styled `●` characters (not emoji) for theme consistency.
- **Terse responses:** Don't over-explain, just do the work.
- **Commit often:** Commit after completing each logical feature.

## CLI Commands

- `nagare pick` (default) — open the session picker TUI
- `nagare notifs` — open the notification center
- `nagare setup` — install Claude Code hooks into `~/.claude/settings.json`
- `nagare hook-state` — internal: called by Claude Code hooks

## tmux Integration

- `prefix + g` — fullscreen popup with session picker
- `prefix + e` — 60% popup with notification center
- Hooks installed in `~/.claude/settings.json` for all relevant Claude Code events

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

## Maintaining This File

Keep this CLAUDE.md updated with a brief overview of the project — goals, user preferences, high-level view of the systems, and any conventions. When systems are added, removed, or significantly changed, update the Architecture section accordingly.
