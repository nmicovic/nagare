# Problem Report: tmux display-popup Opens New Window Instead of Overlay

## Desired Behavior

When a Claude Code hook fires a notification (e.g. `permission_prompt`), nagare should show a **popup overlay** on top of the user's current tmux session using `tmux display-popup`. The popup should appear as a floating window on top of the existing pane content — the same way `prefix + g` opens the nagare picker.

## Actual Behavior

The popup opens as a **new tmux window** (full-size, replaces the current view) instead of a floating overlay. The notification content renders correctly inside this window, but the UX is wrong — it takes over the screen instead of overlaying.

## What Works

- Running `tmux display-popup -w 60% -h 30% -E 'nagare popup-notif ...'` **directly from a shell inside tmux** works perfectly as an overlay.
- Running the exact same command via `tmux run-shell -t nagare: -b "..."` from a shell also works.
- The `nagare popup-notif` Textual TUI app itself renders correctly (tested by capturing stderr output).
- Manual simulation with `CLAUDECODE=1 TMUX=...,1 TMUX_PANE=%1` env vars AND calling `subprocess.Popen(["tmux", "display-popup", "-t", client_name, ...])` from Python works as overlay.

## What Doesn't Work

When the **real Claude Code hook** fires `nagare hook-state`, which eventually calls `send_popup()` in `src/nagare/notifications/deliver.py`, the display-popup always creates a new window. This happens regardless of:

1. Using `-t session_name` targeting
2. Using `-c client_tty` targeting
3. Using `-t client_name` targeting (e.g. `/dev/pts/0`)
4. Using `tmux run-shell -b` to execute inside tmux server context
5. Using `tmux run-shell -t nagare: -b` with explicit session targeting
6. Overriding TMUX env var to point to the correct session index
7. Stripping TMUX/TMUX_PANE env vars entirely
8. Using `-S socket_path` to bypass env var issues
9. Writing a shell script that sets correct env and executing via run-shell
10. Using `subprocess.Popen` with fire-and-forget (no blocking)

## Environment

- tmux 3.4
- WSL2 (Linux 6.6.87.2-microsoft-standard-WSL2)
- Python 3.14+
- Textual TUI framework for popup app
- Claude Code hooks fire commands via subprocess with stdin JSON

## Hook Call Chain

```
Claude Code detects permission_prompt
  → fires hook command: /path/to/nagare hook-state
    → reads JSON from stdin
    → writes state file to ~/.local/share/nagare/states/<id>.json
    → calls _maybe_notify() → _deliver() → send_popup()
      → subprocess.Popen(["tmux", "display-popup", "-t", client_name, ...])
        → OPENS NEW WINDOW instead of overlay
```

The hook subprocess environment:
```
TMUX=/tmp/tmux-1000/default,1604,1    (points to frankmobile session, index 1)
TMUX_PANE=%1                           (frankmobile's pane)
CLAUDECODE=1                           (set by Claude Code)
```

The user is viewing session `nagare` (session index 0) on client `/dev/pts/0`.

## Key Observation

The **exact same Python code** that fails from the real hook works when called from a simulated hook context (`CLAUDECODE=1` + fake TMUX vars). This suggests something unique about the real Claude Code hook subprocess environment that we haven't identified — possibly:

1. Claude Code does something to the process that affects tmux's client resolution
2. The hook subprocess is in a different process group or session leader state
3. Claude Code may intercept or modify child process behavior
4. There may be a timing issue — the hook fires while Claude is in a specific state that affects tmux
5. The process tree depth (Claude Code → hook → Python → Popen → tmux) may cause tmux to lose client context

## Current Code

The delivery function is in `src/nagare/notifications/deliver.py`, function `send_popup()`. It currently uses:

```python
subprocess.Popen(
    ["tmux", "display-popup", "-t", client_name, "-w", "60%", "-h", "30%", "-E", popup_cmd],
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    stdin=subprocess.DEVNULL,
)
```

Where `client_name` comes from `tmux list-clients -F '#{client_name}'`.

## Things NOT Yet Tried

- Using `os.setsid()` before Popen to create a new process session
- Using `start_new_session=True` in Popen kwargs
- Daemonizing the display-popup call (double-fork)
- Using `nohup` wrapper
- Using `at now` or `systemd-run` to schedule the popup outside the hook's process tree
- Writing to a named pipe / fifo that a background watcher reads and executes
- Using tmux's own hook system (`set-hook`) to trigger the popup from inside tmux
- Investigating what Claude Code does to its subprocess environment beyond CLAUDECODE=1
