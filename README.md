<h1 align="center">nagare 流れ</h1>
<p align="center">A tmux-integrated session manager for AI coding agents.<br>Monitor, switch, and control multiple Claude Code and OpenCode sessions from a single interface.</p>

<p align="center">
  <img src="images/nagare-logo-glowing.jpg" alt="nagare" width="550">
</p>

## What it does

When you run multiple AI agents across tmux sessions, nagare gives you:

- **Session picker** (`prefix + g`) — searchable list of all agent sessions with live-streaming pane previews
- **Grid overview** (`Tab`) — see all sessions simultaneously in a tiled grid
- **Notifications** — toast, bell, OS notifications, and popup overlays when agents need your attention
- **Quick actions** — approve permissions, kill sessions, rename, and create new sessions without leaving the picker
- **Session manager** (`Ctrl+s`) — persistent registry of your projects, load/unload sessions in bulk
- **Token tracking** — per-session and total token usage from Claude Code transcripts

## Supported agents

| Agent | Detection | State tracking |
|-------|-----------|---------------|
| **Claude Code** | Process name `claude` | Hook-based (real-time) |
| **OpenCode** | Process name `opencode` | Plugin-based (real-time) |

Sessions are identified by colored icons: **C** for Claude, **O** for OpenCode.

## Install

Requires Python 3.14+, [uv](https://github.com/astral-sh/uv), and tmux.

```bash
git clone git@github.com:nmicovic/nagare.git
cd nagare
uv sync

# Install hooks and plugins
uv run nagare setup
```

Add to your `~/.tmux.conf`:

```bash
# Session picker (fullscreen)
bind g display-popup -w100% -h100% -E "/path/to/nagare/.venv/bin/nagare pick"

# Notification center
bind e display-popup -w60% -h60% -E "/path/to/nagare/.venv/bin/nagare notifs"
```

Reload tmux: `tmux source-file ~/.tmux.conf`

## Usage

### Picker (`prefix + g`)

The main interface. Two views:

**List view** — session list on the left, live preview on the right. Each session shows agent type, status, path, git branch, session age, and conversation topic.

**Grid view** (`Tab`) — tiled grid showing all sessions streaming simultaneously. Adaptive columns (1-3) based on session count.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Enter` | Jump to session |
| `↑/↓` | Navigate |
| `Tab` | Toggle list/grid |
| `Ctrl+y` | Allow (approve permission) |
| `Ctrl+a` | Allow always |
| `F2` | Rename session |
| `Ctrl+s` | Session manager |
| `Ctrl+n` | New session |
| `Ctrl+r` | Quick prototype |
| `Ctrl+w` | Kill agent pane |
| `Ctrl+x` | Kill tmux session |
| `Ctrl+o` | Cycle sort (status/name/agent) |
| `Ctrl+e` | Open config in editor |
| `Ctrl+t` | Cycle theme |
| `Ctrl+p` | Command palette |
| `F1` | Help |
| `Esc` | Close |

### Session manager (`Ctrl+s`)

Persistent registry of your projects. Load multiple sessions at once:

1. Open picker → `Ctrl+s`
2. Select a session → `Enter` to load (starts tmux + agent with `-c` to continue)
3. Select another → `Enter` to load
4. `Esc` → back to picker with new sessions visible

Sessions are auto-discovered from running tmux agents and remembered across restarts.

### Quick prototype (`Ctrl+r`)

Fast session creation for throwaway projects:

1. Type a name (e.g. `streaming_test`)
2. Pick agent (Claude/OpenCode)
3. Enter → creates `~/Prototypes/streaming_test/`, starts tmux session, launches agent

Configurable root path in `[picker]` section of config.

### Notifications

Four delivery methods, configurable per event type:

| Method | Description |
|--------|-------------|
| **Toast** | tmux status bar message |
| **Bell** | Terminal bell |
| **OS Notify** | Native notification (supports WSL via `wsl-notify-send`) |
| **Popup** | Rich TUI overlay with session preview |

Two event types:

- **needs_input** — agent needs permission or user action
- **task_complete** — agent finished after working longer than `min_working_seconds`

Configure via `Ctrl+e` (config file) or the notification center settings tab (`prefix + e` → tab 2).

### Notification center (`prefix + e`)

Two tabs:

- **Notifications** — view, dismiss, jump to sessions
- **Settings** — toggle notification methods interactively

## Configuration

Config file: `~/.config/nagare/config.toml`

```toml
[notifications]
enabled = true

[notifications.needs_input]
toast = true
bell = true
os_notify = true
popup = true
popup_timeout = 8

[notifications.task_complete]
toast = true
bell = false
os_notify = false
popup = false
min_working_seconds = 30

# Silence a specific session
# [notifications.sessions.playground]
# enabled = false

[picker]
quick_project_path = "~/Prototypes"

[animation]
jump_animation = "flash"  # flash, pulse, fade, sweep, shrink, none

[appearance]
theme = "tokyonight"
```

## Themes

10 built-in themes, cycle with `Ctrl+t`:

tokyonight, tokyonight-storm, tokyonight-light, catppuccin-mocha, catppuccin-latte, gruvbox-dark, gruvbox-light, nord, dracula, solarized-dark

## Architecture

```
Claude Code hooks → hooks.py → state files → scanner → picker UI
OpenCode plugin  → state files ↗

Picker poll (2s) → scan sessions → update list/grid
Preview poll (configurable) → tmux capture-pane → live preview
```

Key components:

- **Scanner** — discovers agents across all tmux sessions via `list-panes -a`
- **Hooks** — Claude Code lifecycle events write state files for real-time detection
- **OpenCode plugin** — TypeScript plugin writes state files in the same format
- **State reader** — resolves conflicts when multiple sessions share the same project path
- **Notification delivery** — toast, bell, OS notify, popup with FIFO watcher for overlay support

## Development

```bash
uv run pytest          # Run tests
uv run nagare pick     # Run the picker
uv run nagare setup    # Install/update hooks and plugins
```

Logs: `~/.local/share/nagare/nagare.log` (1MB rotating)

## License

MIT
