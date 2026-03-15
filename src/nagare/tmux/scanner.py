from nagare.models import AgentType, Session, SessionStatus
from nagare.state import load_all_states
from nagare.tmux import run_tmux
from nagare.tmux.status import detect_status, parse_details

_HOOK_STATE_MAP = {
    "working": SessionStatus.RUNNING,
    "waiting_input": SessionStatus.WAITING_INPUT,
    "idle": SessionStatus.IDLE,
    "dead": SessionStatus.DEAD,
}

# Process names we recognize as AI agents
_AGENT_PROCESSES = {
    "claude": AgentType.CLAUDE,
    "opencode": AgentType.OPENCODE,
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


def _find_agent_panes(pane_output: str) -> list[tuple[int, int, AgentType]]:
    """Find ALL panes running recognized AI agents.

    Returns list of (window_index, pane_index, agent_type).
    """
    results = []
    for line in pane_output.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            cmd = parts[2].strip()
            agent_type = _AGENT_PROCESSES.get(cmd)
            if agent_type is not None:
                results.append((int(parts[0]), int(parts[1]), agent_type))
    return results


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
        agents = _find_agent_panes(pane_output)
        for window_index, pane_index, agent_type in agents:
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
                agent_type=agent_type,
                details=details,
                last_message=last_message,
            ))
    return sessions
