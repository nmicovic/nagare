# Notification System Redesign

## Overview

Overhaul nagare's notification system to support multiple delivery methods, configurable per event type and per session, with a rich popup notification TUI.

## Notification Events

Two event types, both driven by Claude Code hooks:

- **needs_input** — fires on `Notification` hook with `permission_prompt` or `elicitation_dialog`. High urgency.
- **task_complete** — fires when state transitions from `working` → `idle` (Stop event), only if Claude was working longer than `min_working_seconds` (default 30s). Hook handler reads existing state file timestamp to calculate working duration.

## Delivery Methods

Four methods, independently toggleable per event type:

- **toast** — `tmux display-message -d {duration}`. Quick, non-intrusive.
- **bell** — writes `\a` to user's active pane via `tmux send-keys`. Triggers terminal/OS alert.
- **os_notify** — native desktop notification. Auto-detects WSL (uses `powershell.exe` or `wsl-notify-send`) vs native Linux (`notify-send`). Silently skips if unavailable.
- **popup** — `tmux display-popup` launching `nagare popup-notif` TUI. Shows status icon, session name, event type, Claude's last message. Esc dismisses, Enter jumps to session, auto-dismisses after configurable timeout.

## Notification Flow

1. Hook fires → `hooks.py` determines event type (needs_input or task_complete)
2. For task_complete: check working duration against `min_working_seconds` threshold
3. Load config, resolve per-session overrides
4. If session has `enabled = false`, stop
5. For each enabled delivery method, fire it
6. Always store notification in JSON store (regardless of delivery config)

## Configuration

```toml
# Master switch for all notifications
# Set to false to completely disable notifications
enabled = true

[notifications.needs_input]
# Show tmux status bar toast (3s non-dismissable message)
toast = true
# Send terminal bell (\a) to trigger OS/terminal alerts
bell = true
# Send native OS desktop notification (notify-send or WSL equivalent)
os_notify = true
# Show rich popup window with full context (steals focus briefly)
popup = false
# Seconds before popup auto-dismisses (only applies if popup = true)
popup_timeout = 10

[notifications.task_complete]
# Show tmux status bar toast when Claude finishes a long task
toast = true
# Send terminal bell on task completion
bell = false
# Send native OS notification on task completion
os_notify = false
# Show rich popup on task completion
popup = false
# Seconds before popup auto-dismisses
popup_timeout = 10
# Only notify if Claude was working longer than this many seconds
# Prevents spam from quick back-and-forth responses
min_working_seconds = 30

# Per-session overrides — only list exceptions to the global defaults.
# Any setting not specified here inherits from the event-type defaults above.
#
# Example: silence a noisy session completely
# [notifications.sessions.playground]
# enabled = false
#
# Example: get full popup treatment for an important session
# [notifications.sessions.production-backend]
# popup = true
# os_notify = true
```

## Popup Notification TUI

Small Textual app (`nagare popup-notif`) launched via `tmux display-popup -w60% -h30% -E`.

Context passed via CLI args: session name, event type, message, working duration.

### needs_input layout:
```
┌──────────────────────────────────────┐
│  🔴  production-backend              │
│  NEEDS PERMISSION                    │
│                                      │
│  💬 Claude wants to run:             │
│     Bash(git push origin main)       │
│                                      │
│  ─────────────────────────────────── │
│  Enter: Jump to session   Esc: Dismiss│
│  Auto-closing in 8s...               │
└──────────────────────────────────────┘
```

### task_complete layout:
```
┌──────────────────────────────────────┐
│  🟢  nagare                          │
│  TASK COMPLETE (worked 2m 34s)       │
│                                      │
│  💬 Done. I've implemented the new   │
│     notification system with all...  │
│                                      │
│  ─────────────────────────────────── │
│  Enter: Jump to session   Esc: Dismiss│
│  Auto-closing in 6s...               │
└──────────────────────────────────────┘
```

Countdown timer ticks every second. On zero, app exits.

## File Changes

### New files
- `notifications/deliver.py` — delivery functions: `send_toast()`, `send_bell()`, `send_os_notify()`, `send_popup()`
- `popup_notif.py` — popup notification TUI app

### Modified files
- `hooks.py` — becomes thin dispatcher: determine event type, load config, resolve overrides, call `deliver_notification()`
- `config.py` — new notification config schema with per-event and per-session settings
- `notifs.py` — migrate from `OptionList` to `ListView` for consistency with picker
- `__init__.py` — add `popup-notif` CLI command

### Deleted files
- `notifications/base.py` — premature ABC abstraction
- `notifications/tmux.py` — replaced by `deliver.py`
