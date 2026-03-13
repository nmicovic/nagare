# Interactive Mode Design

## Overview

Replace the suspend/attach flow with inline terminal rendering. The right pane becomes an interactive terminal view — keystrokes forwarded to tmux, pane content captured at high frequency. You never leave nagare.

## Interaction Model

Two panes: **left (session list + detail)** and **right (terminal view)**. Exactly one is active at a time, indicated by a `$primary` colored border. Inactive pane gets a `$surface` border.

**Left pane active (default):**
- j/k navigates sessions
- Right pane shows read-only preview, refreshed every 3s
- Ctrl+] switches to right pane (enters interactive mode)
- r refreshes, t opens theme picker, q quits

**Right pane active (interactive mode):**
- All keystrokes forwarded to tmux via `send-keys`
- Pane capture runs at ~200ms
- Ctrl+[ switches back to left pane
- Right pane reverts to preview mode (3s refresh)

**Session switching:**
- Only possible from left pane
- Always returns to preview mode
- Must Ctrl+] again to interact with newly selected session

## Transport Abstraction

```
NagareApp
    ↓
SessionTransport (ABC)
    - get_content(session) -> str
    - send_keys(session, keys) -> None
    - start_streaming(session, callback) -> None
    - stop_streaming() -> None
    ↓
PollingTransport (now)        ControlTransport (future)
  capture-pane + timer          tmux -CC protocol
```

**PollingTransport:**
- `get_content` → `tmux capture-pane -p -e`
- `send_keys` → `tmux send-keys` with key mapping
- `start_streaming` → 200ms timer calling capture-pane
- `stop_streaming` → cancel timer

## Key Forwarding

Textual key events → tmux send-keys syntax:

| Textual event | tmux command |
|---|---|
| Regular char (a, 1, /) | `send-keys -l "a"` |
| Enter | `send-keys Enter` |
| Tab | `send-keys Tab` |
| Backspace | `send-keys BSpace` |
| Arrow keys | `send-keys Up/Down/Left/Right` |
| Ctrl+C | `send-keys C-c` |
| Ctrl+D | `send-keys C-d` |
| Escape | `send-keys Escape` |
| Space | `send-keys Space` |

Ctrl+[ and Ctrl+] intercepted by nagare, never forwarded.

## Refresh Timers

**Session scan (3s, always):** discover/update all sessions
**Preview capture (3s, left pane active):** capture selected session's pane
**Streaming capture (200ms, right pane active):** high-frequency capture for interactive session

Transitions:
- Ctrl+] → stop preview, start streaming
- Ctrl+[ → stop streaming, start preview
- j/k session switch → already in preview mode

## Footer

Reactive — changes based on active pane:
- Left active: `↑/k Up  ↓/j Down  Ctrl+] Interact  r Refresh  t Theme  q Quit`
- Right active: `Ctrl+[ Back to sessions    All input forwarded to session`
