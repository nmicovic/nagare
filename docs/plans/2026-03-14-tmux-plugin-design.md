# nagare v2: tmux-integrated Claude Code session manager

## Overview

Pivot nagare from a standalone Textual TUI to a tmux-integrated CLI tool. Instead of fighting tmux by embedding sessions, work WITH tmux — provide a smart session picker, background monitoring, and toast notifications, all rendered through tmux's native `display-popup`.

## Architecture

Four CLI commands:

- `nagare pick` — Fuzzy session picker (Textual app inside `display-popup`)
- `nagare notifs` — Notification center (Textual app inside `display-popup`)
- `nagare daemon` — Background process that polls sessions and sends notifications
- `nagare setup` — One-time onboarding (config, keybindings)

## Session Picker (`nagare pick`)

Invoked via tmux: `tmux display-popup -w80% -h80% -E "nagare pick"`

### Layout

- **Top:** Fuzzy search input field, always focused
- **Middle:** Filtered list of sessions with rich formatting per row:
  - Status icon (waiting, running, idle, dead)
  - Session name (bold)
  - Git branch, model, context %
  - Path (dimmed)
- **Bottom:** One-line hint bar (Enter jump, Esc cancel)

### Behavior

- As you type, the list fuzzy-filters in real-time
- Arrow keys / j/k navigate the filtered list
- Enter runs `tmux switch-client -t <session>` and exits (popup closes)
- Escape exits (popup closes, stay where you are)
- Sessions needing attention sort to the top

### Future extensibility ("smart-pick")

- List item rendering and sorting are abstracted so we can later add non-Claude entries (regular tmux sessions, common projects, bookmarks)
- Fuzzy matcher could later rank by urgency, recency, or frequency

## Notification System

### Notification Backend (modular)

Abstract `NotificationBackend` with method: `notify(message, session_name, urgency)`.

Default implementation: `tmux display-message -d 2000`.

Swappable for `notify-send`, `osascript`, webhooks, etc.

### Daemon (`nagare daemon`)

- Runs as a background process
- Polls sessions every 3 seconds using existing scanner + status detection
- Tracks previous status per session
- When a session transitions to `WAITING_INPUT`, fires a notification
- Stores notifications in `~/.local/share/nagare/notifications.json` (timestamp, session name, message, read/unread)
- Writes PID file to `~/.local/share/nagare/daemon.pid` to prevent duplicate instances

### Notification Center (`nagare notifs`)

Invoked via tmux: `tmux display-popup -w60% -h60% -E "nagare notifs"`

- List of recent notifications, newest first
- Unread ones marked with dot/highlight
- Enter jumps to that session (`switch-client`) and marks it read
- Escape closes
- `d` dismisses a single notification
- `D` (shift+d) dismisses all notifications

## Configuration

File: `~/.config/nagare/config.toml`

```toml
[notifications]
backend = "tmux"        # "tmux", "notify-send", "osascript"
duration = 2000         # milliseconds
poll_interval = 3       # seconds

[picker]
popup_width = "80%"
popup_height = "80%"
```

Optional — everything has sensible defaults. Nagare works out of the box without a config file.

## Setup & Onboarding (`nagare setup`)

1. Creates `~/.config/nagare/config.toml` with defaults
2. Creates `~/.local/share/nagare/` for notification storage
3. Prints recommended tmux keybindings:

```
# nagare - Claude Code session manager
bind g display-popup -w80% -h80% -E "nagare pick"
bind n display-popup -w60% -h60% -E "nagare notifs"
```

4. Optionally appends them to `~/.tmux.conf` if user confirms

Daemon startup (add to `.zshrc` / `.bashrc`):

```bash
nagare daemon &
```

## Code Reuse

### Keep

- `models.py` — Session, SessionStatus, SessionDetails
- `tmux/scanner.py` — Session discovery
- `tmux/status.py` — Status detection
- `tmux/__init__.py` — run_tmux helper
- `themes.py` — Theme system

### Drop

- `app.py` — Full-screen NagareApp
- `transport/` — Polling, send-keys
- `widgets/` — All existing widgets (session_list, session_detail, terminal_view, footer_bar, theme_picker)
- `nagare.tcss` — Full-screen layout

### New

- `pick.py` — Picker Textual app
- `notifs.py` — Notification center Textual app
- `daemon.py` — Background monitor
- `setup.py` — Onboarding command
- `config.py` — Config loading (TOML)
- `notifications/base.py` — NotificationBackend ABC
- `notifications/tmux.py` — tmux display-message backend
- `notifications/store.py` — JSON notification storage
