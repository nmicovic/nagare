from nagare.models import Session, SessionStatus
from nagare.state import load_all_states
from nagare.tmux import run_tmux
from nagare.tmux.status import detect_status, parse_details

_HOOK_STATE_MAP = {
    "working": SessionStatus.RUNNING,
    "waiting_input": SessionStatus.WAITING_INPUT,
    "idle": SessionStatus.IDLE,
    "dead": SessionStatus.DEAD,
}


def _parse_sessions(raw: str) -> list[tuple[str, str, str]]:
    if not raw:
        return []
    sessions = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            sessions.append((parts[0], parts[1], parts[2]))
    return sessions


def _find_claude_pane(pane_output: str) -> tuple[int, int] | None:
    for line in pane_output.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and parts[2].strip() == "claude":
            return (int(parts[0]), int(parts[1]))
    return None


def scan_sessions() -> list[Session]:
    raw = run_tmux("list-sessions", "-F", "#{session_name}:#{session_id}:#{session_path}")
    parsed = _parse_sessions(raw)
    hook_states = load_all_states()
    sessions = []
    for name, session_id, path in parsed:
        pane_output = run_tmux(
            "list-panes", "-s", "-t", name,
            "-F", "#{window_index}:#{pane_index}:#{pane_current_command}",
        )
        result = _find_claude_pane(pane_output)
        if result is not None:
            window_index, pane_index = result
            pane_content = run_tmux(
                "capture-pane", "-t", f"{name}:{window_index}.{pane_index}", "-p",
            )
            details = parse_details(pane_content)

            # Prefer hook-based state over pane scraping
            hook_state = hook_states.get(path)
            if hook_state is not None:
                status = _HOOK_STATE_MAP.get(hook_state.state, SessionStatus.IDLE)
                last_message = hook_state.last_message
            else:
                status = detect_status(pane_content)
                last_message = ""

            sessions.append(Session(
                name=name,
                session_id=session_id,
                path=path,
                window_index=window_index,
                pane_index=pane_index,
                status=status,
                details=details,
                last_message=last_message,
            ))
    return sessions
