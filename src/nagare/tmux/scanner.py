from nagare.models import Session, SessionStatus
from nagare.tmux import run_tmux


def _parse_sessions(raw: str) -> list[tuple[str, str, str]]:
    if not raw:
        return []
    sessions = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            sessions.append((parts[0], parts[1], parts[2]))
    return sessions


def _find_claude_pane(pane_output: str) -> int | None:
    for line in pane_output.splitlines():
        parts = line.split(":", 1)
        if len(parts) == 2 and parts[1].strip() == "claude":
            return int(parts[0])
    return None


def scan_sessions() -> list[Session]:
    raw = run_tmux("list-sessions", "-F", "#{session_name}:#{session_id}:#{session_path}")
    parsed = _parse_sessions(raw)
    sessions = []
    for name, session_id, path in parsed:
        pane_output = run_tmux("list-panes", "-t", name, "-F", "#{pane_index}:#{pane_current_command}")
        pane_index = _find_claude_pane(pane_output)
        if pane_index is not None:
            sessions.append(Session(
                name=name,
                session_id=session_id,
                path=path,
                pane_index=pane_index,
                status=SessionStatus.ALIVE,
            ))
    return sessions
