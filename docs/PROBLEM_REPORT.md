# Problem Report: tmux display-popup Opens New Window Instead of Overlay

## Desired Behavior

When a Claude Code hook fires a notification (e.g. `permission_prompt`), nagare should show a **popup overlay** on top of the user's current tmux session using `tmux display-popup`. The popup should appear as a floating window on top of the existing pane content — the same way `prefix + g` opens the nagare picker.

See `expected.png` (popup overlay on top of pane content) vs `what_we_get.png` (full-size new window with blank background).

## Actual Behavior

The popup opens as a **new tmux window** (full-size, replaces the current view) instead of a floating overlay. The notification content renders correctly inside this window, but the UX is wrong — it takes over the screen instead of overlaying.

## The Core Discovery

**`tmux display-popup` only works as an overlay when called from a process that is a DIRECT DESCENDANT of an interactive tmux pane.** Anything else — `run-shell -b`, `#()` status commands, `wait-for` loops started via `run-shell` — all create a new window instead.

This was confirmed through extensive testing:

| Approach | Works as overlay? |
|----------|-------------------|
| Direct shell command in tmux pane | YES |
| Python subprocess.Popen from shell in pane | YES |
| Python subprocess.Popen from Claude Code hook | NO |
| `tmux run-shell -b "tmux display-popup ..."` | NO |
| `tmux run-shell -t session: -b "..."` | NO |
| Shell script with TMUX env override via run-shell | NO |
| `#()` status-right command | NO |
| `tmux wait-for` loop started via `run-shell -b` | NO |
| Hidden pane running watcher via `new-window -d` | NO |
| Write pending file + manual dispatch from pane shell | YES |
| Write pending file + signal wait-for + watcher in run-shell | NO |

The pattern is clear: **only processes that are children of an interactive pane process** can create popup overlays. Everything run by the tmux server itself (run-shell, hooks, status commands) cannot.

## What Works

- Running `tmux display-popup ...` **directly from a shell inside a tmux pane** — always works
- Running `subprocess.Popen(["tmux", "display-popup", ...])` from Python running inside a pane — works
- Writing a pending popup file from the hook, then having a process **running in a pane** read and dispatch it — works
- Simulating the hook environment manually (`CLAUDECODE=1`, fake `TMUX`/`TMUX_PANE`) from a shell in a pane — works (because it's still a pane descendant)

## What Doesn't Work

Everything called from a Claude Code hook subprocess, regardless of:

1. `-t session_name` targeting
2. `-c client_tty` targeting
3. `-t client_name` targeting (e.g. `/dev/pts/0`)
4. `tmux run-shell -b` to execute inside tmux server context
5. `tmux run-shell -t nagare: -b` with explicit session targeting
6. Overriding TMUX env var to point to the correct session index
7. Stripping TMUX/TMUX_PANE env vars entirely
8. Using `-S socket_path` to bypass env var issues
9. Writing a shell script that sets correct env and executing via `run-shell`
10. `subprocess.Popen` with `start_new_session=True`
11. `tmux set-hook -g pane-focus-in` (not a valid hook in tmux 3.4)
12. `#()` in `status-right` — runs as subprocess, not pane descendant
13. `tmux wait-for` signal + background waiter started via `run-shell -b`
14. Hidden `new-window -d` running watcher — the watcher pane works, but it's in the WRONG session context

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
      → [needs to trigger display-popup from pane context]
```

The hook subprocess environment:
```
TMUX=/tmp/tmux-1000/default,1604,1    (points to frankmobile session, index 1)
TMUX_PANE=%1                           (frankmobile's pane)
CLAUDECODE=1                           (set by Claude Code)
```

The user is viewing session `nagare` (session index 0) on client `/dev/pts/0`.

## Current Architecture

`send_popup()` in `src/nagare/notifications/deliver.py` currently:
1. Writes popup data to `~/.local/share/nagare/popup_pending.json`
2. Signals `tmux wait-for -S nagare-popup`
3. A watcher (started via `run-shell -b` or `new-window -d`) is supposed to pick it up

But step 3 fails because the watcher doesn't run in pane-descendant context.

## Ideas NOT Yet Tried

### Approach A: Persistent watcher pane in the USER'S active session
Instead of `new-window -d` (which creates in the wrong session), use `split-window` in the user's current session to create a tiny 1-line pane running the watcher. This pane IS a pane descendant. Challenges:
- Visible to the user (even if 1 line)
- Need to manage lifecycle (restart if killed)
- Need to run in whichever session the user is currently in

### Approach B: tmux `command-prompt` or `confirm-before` hack
These run in proper client context. Could potentially abuse `confirm-before -p "" "display-popup ..."` to get client context. Untested.

### Approach C: tmux key simulation
Have the hook use `tmux send-keys` to simulate a key combo that triggers a keybinding which runs display-popup. The keybinding runs in proper client context. E.g.:
```bash
# In tmux.conf: bind F12 run-shell "nagare popup-dispatch"
# In hook: tmux send-keys -t client F12
```
Challenge: F12 might interfere with the running application.

### Approach D: Named pipe + watcher in .tmux.conf
Add to tmux.conf: a background pane that watches a FIFO. Since tmux.conf starts panes in proper context, this might work.

### Approach E: Abandon display-popup for hooks
Accept that hooks can't create overlay popups. Use toast + OS notification as the primary notification from hooks. Only use display-popup for interactive contexts (keybindings like prefix+g).

### Approach F: systemd-run or at-now
Schedule the display-popup command via `systemd-run --user` or `at now`, which creates a completely independent process. But this still won't be a pane descendant.

### Approach G: Write to the user's shell stdin
Use `tmux send-keys` to type a command into the user's active pane that runs display-popup. Extremely hacky but the command WOULD run in pane context. Would disrupt whatever's in the pane.
