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
- **Agent messaging** — send messages between Claude Code sessions via MCP server

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

# Install hooks, MCP server, and plugins
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
| `Enter` | Jump to session / Load saved session |
| `↑/↓` | Navigate |
| `Tab` | Toggle list/grid view |
| `Ctrl+y` | Allow (approve permission) |
| `Ctrl+a` | Allow always |
| `Ctrl+f` | Star/unstar session (pinned to top) |
| `F2` | Rename session |
| `Ctrl+s` | Show/hide saved (unloaded) sessions |
| `Ctrl+d` | Delete saved session from registry |
| `Ctrl+n` | New session (full form) |
| `Ctrl+r` | Quick prototype |
| `Ctrl+w` | Unload agent (kill pane) |
| `Ctrl+x` | Kill entire tmux session |
| `Ctrl+l` | Send prompt to highlighted session (inline) |
| `Ctrl+g` | Send prompt via `$EDITOR` (neovim, etc.) |
| `Ctrl+o` | Cycle sort (status/name/agent) |
| `Ctrl+b` | Agent mailbox (message history) |
| `Ctrl+e` | Open config in editor |
| `Ctrl+t` | Cycle theme |
| `Ctrl+p` | Command palette (search all actions) |
| `F1` | Help |
| `Esc` | Close |

### Saved sessions (`Ctrl+s`)

Press `Ctrl+s` to reveal unloaded sessions below the active ones. Star sessions with `Ctrl+f` to pin them to the top. Sessions are auto-discovered from running agents and remembered across restarts.

- `Enter` on a saved session loads it (creates tmux + agent with `-c`)
- `Ctrl+d` deletes a saved session from the registry
- `Ctrl+s` again hides the saved section

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

### Agent messaging

Send messages between Claude Code sessions. One agent can ask another agent a question and get a response — useful when frontend and backend agents need to coordinate.

Powered by a nagare MCP server that `nagare setup` registers automatically. Each Claude Code session gets access to messaging tools.

**MCP tools:**

| Tool | Description |
|------|-------------|
| `list_agents` | List available sessions with status |
| `send_message` | Fire-and-forget message |
| `send_message_and_wait` | Send and block until response |
| `check_messages` | Check inbox + late responses |
| `reply` | Respond to a message |

**Slash commands** (available in any Claude Code session):

| Command | Usage |
|---------|-------|
| `/nagare-ls` | List available agents |
| `/nagare-send` | `/nagare-send cosmiclab-backend Check the API docs` |
| `/nagare-send-wait` | `/nagare-send-wait cosmiclab-backend Give me the API docs` |
| `/nagare-inbox` | Check inbox and late responses |

**Mailbox viewer** (`Ctrl+b` in picker) — split-pane view with filter, compact message list, and full markdown-rendered detail panel.

**How it works:**
1. Sender calls `send_message` or `send_message_and_wait`
2. Message is written to `~/.local/share/nagare/messages/<target>/`
3. `tmux send-keys` nudges the target agent (must be IDLE)
4. Target calls `check_messages`, reads the request, calls `reply`
5. Sender receives the response (or picks it up later via `check_messages`)

### Remote prompting

Send prompts to any agent session without leaving the picker:

- **`Ctrl+l`** — inline prompt with markdown highlighting. Enter sends, Ctrl+Enter for newlines, Esc cancels.
- **`Ctrl+g`** — opens `$EDITOR` (e.g. neovim) with a temp `.md` file. Write your prompt, save and quit — content is sent to the agent via `tmux send-keys`.

Both methods send the text directly to the agent's tmux pane as if you typed it yourself.

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

[sounds]
enabled = true
pack = "peon"              # openpeon sound pack name
volume = 0.7

[voice]
enabled = true
engine = "edge-tts"        # auto, say, piper, edge-tts, espeak, wsl-sapi
voice = "en-US-AriaNeural"
volume = 0.8

[voice.templates]
task_complete = "{session} is done"
input_required = "{session} needs you"
session_end = "Farewell commander"
```

### Sound packs (CESP / openpeon)

Play sound effects on agent events using [openpeon](https://openpeon.com) community sound packs — from Warcraft peons to Cartman to GLaDOS.

```bash
nagare sounds list                    # Show installed packs
nagare sounds install peon            # Install from registry (100+ packs)
nagare sounds install southpark_cartman
nagare sounds test peon               # Play one sound per category
```

Events: `session.start`, `task.acknowledge`, `task.complete`, `input.required`, `session.end`. Each toggleable in config. Per-session pack overrides supported.

### Voice notifications (TTS)

Speak contextual messages when agents need attention. Auto-detects the best available engine:

| Engine | Quality | Internet | Install |
|--------|---------|----------|---------|
| **edge-tts** | Excellent (neural) | Required | `uv add edge-tts` |
| **piper-tts** | Good (neural) | Offline | `pip install piper-tts` + model |
| **espeak-ng** | Robotic | Offline | `apt install espeak-ng` |
| **say** | Good | Offline | Built into macOS |

300+ voices available with edge-tts (`edge-tts --list-voices`). Configure templates with `{session}` placeholder for the session name.

Per-session voice/engine overrides supported:
```toml
[voice.sessions.cosmiclab-backend]
voice = "en-GB-SoniaNeural"
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

MCP server (per session) → message files → tmux send-keys → target agent
```

Key components:

- **Scanner** — discovers agents across all tmux sessions via `list-panes -a`
- **Hooks** — Claude Code lifecycle events write state files for real-time detection
- **OpenCode plugin** — TypeScript plugin writes state files in the same format
- **State reader** — resolves conflicts when multiple sessions share the same project path
- **Notification delivery** — toast, bell, OS notify, popup with FIFO watcher for overlay support
- **MCP server** — per-session stdio server for inter-agent messaging via file-based mailbox

## Development

```bash
uv run pytest          # Run tests
uv run nagare pick     # Run the picker
uv run nagare setup    # Install/update hooks and plugins
```

Logs: `~/.local/share/nagare/nagare.log` (1MB rotating)

## License

MIT
