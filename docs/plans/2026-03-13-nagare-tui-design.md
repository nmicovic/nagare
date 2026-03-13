# nagare TUI Design

## Overview

nagare is a full-screen Textual TUI that acts as an agent manager for Claude Code sessions running inside tmux. You launch `nagare`, live inside it, and manage all your Claude Code sessions from one place without manual tmux switching.

## Architecture

### Core Loop

1. On launch, scan all tmux sessions for running Claude Code (`claude`) processes
2. Render a two-pane layout: session list (left), preview pane (right)
3. Poll tmux every 2-3 seconds to refresh session states and preview content
4. On Enter, suspend the TUI, attach to that tmux session, resume TUI on detach

### Components

- **SessionScanner** (`tmux/scanner.py`) — discovers tmux sessions with `claude` processes, returns session metadata
- **StatusDetector** (inside scanner, extensible) — determines session state. Phase 1: alive/dead based on `pane_current_command`. Designed for future smart detection (parsing pane content for prompts, errors, idle states)
- **PaneCapture** (`tmux/capture.py`) — grabs the current visible content of a tmux pane via `tmux capture-pane -p -e`
- **NagareApp** (`app.py`) — the main Textual App wiring polling, widgets, and attach flow

### Data Flow

```
tmux ──(tmux CLI)──> SessionScanner ──> session list widget
tmux ──(tmux CLI)──> PaneCapture ──> preview pane widget
tmux ──(tmux CLI)──> StatusDetector ──> status icons
User presses Enter ──> suspend TUI ──> tmux attach ──> resume TUI
```

Everything talks to tmux through its CLI. No sockets, no custom protocols.

## tmux Integration

### Session Discovery

```bash
# List all sessions
tmux list-sessions -F "#{session_name}:#{session_id}:#{session_path}"

# For each session, check panes for claude process
tmux list-panes -t <session> -F "#{pane_index}:#{pane_current_command}"

# Filter: pane_current_command == "claude"
```

### Pane Capture (Preview)

```bash
# Capture visible pane content with ANSI colors
tmux capture-pane -t <session>:<pane_index> -p -e
```

Shows last N lines (the current visible terminal content) in the preview pane.

### Attach (Full Takeover)

1. Suspend the Textual app
2. Run `tmux attach-session -t <session>`
3. User works inside tmux normally
4. User detaches (`Ctrl+b d`)
5. Textual app resumes, refreshes everything

### Status Detection

**Phase 1 (now):**
- `pane_current_command == "claude"` → alive (running)
- `pane_current_command != "claude"` → dead/exited

**Phase 2 (future):**
- Parse pane content for known patterns (prompts, spinners, error messages)
- Infer: idle, executing, waiting for input, crashed

## TUI Layout

```
┌──────────────────┬──────────────────────────────────┐
│  Sessions (30%)  │  Preview Pane (70%)              │
│                  │                                   │
│  ● my-api       │  Last N lines of selected         │
│  ○ frontend     │  session's tmux pane output       │
│  ⚠ backend      │                                   │
│                  │                                   │
│                  │                                   │
├──────────────────┴──────────────────────────────────┤
│ ↑/k Up  ↓/j Down  Enter Attach  q Quit             │
│ Detach from session: Ctrl+b d         r Refresh     │
└─────────────────────────────────────────────────────┘
```

### Session List (Left Pane — 30%)

- Flat list of sessions with Claude Code running
- Each entry: status icon + session name + project directory
- Status icons: `●` running, `○` exited, `⚠` crashed
- Arrow keys / j/k to browse — preview updates as selection moves
- Enter to jump in (full takeover)

### Preview Pane (Right — 70%)

- Displays captured pane content of the currently highlighted session
- Refreshes on selection change and on periodic timer
- Monospace rendering preserving terminal output formatting
- ANSI color support via Textual's Rich integration

### Footer Bar

- Persistent at bottom, always visible
- Row 1: Navigation and actions (↑/k, ↓/j, Enter, q, r)
- Row 2: How to return from attached session (`Ctrl+b d`)
- Keys highlighted/bold, descriptions muted

## Project Structure

```
nagare/
├── main.py                   # Entry point
├── pyproject.toml
├── src/
│   └── nagare/
│       ├── __init__.py
│       ├── app.py            # NagareApp (Textual App)
│       ├── widgets/
│       │   ├── __init__.py
│       │   ├── session_list.py    # Left pane
│       │   ├── preview_pane.py    # Right pane
│       │   └── footer_bar.py     # Bottom controls
│       ├── tmux/
│       │   ├── __init__.py
│       │   ├── scanner.py        # Session discovery + status
│       │   ├── capture.py        # Pane content capture
│       │   └── attach.py         # Suspend/attach/resume
│       └── models.py            # Session dataclass
├── tests/
└── docs/
    └── NAGARE.md
```

**Separation of concerns:**
- `tmux/` — purely subprocess calls to tmux. No UI.
- `widgets/` — purely Textual rendering. No subprocess calls.
- `models.py` — shared data contract between the two layers.
- `app.py` — wires polling, widgets, and attach flow together.

## Decisions & Future Work

| Decision | Rationale |
|----------|-----------|
| Auto-discover sessions | No setup friction, works with existing workflow |
| Full takeover on attach | Reliable, avoids terminal-in-terminal complexity |
| Basic status detection first | Ship fast, extensible interface for smarter detection later |
| Last N lines preview only | Simple, sufficient for glancing — scrollback comes later |
| Flat session list | Won't have dozens of sessions; grouping can be added later |

### Future iterations
- Spawn new Claude Code sessions from within the TUI
- Smart status detection (parsing pane content)
- Scrollable preview pane
- Session grouping (by project, by status)
