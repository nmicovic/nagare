from pathlib import Path

from nagare.models import AgentType, Session, SessionDetails, SessionStatus
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

# Node.js agents that need cmdline inspection to identify
_NODE_AGENTS = {"gemini": AgentType.GEMINI}


def _resolve_node_agent(pane_pid: int) -> AgentType | None:
    """Check if a node process in a pane is actually a known agent (e.g. Gemini).

    Reads /proc to find the child process cmdline and checks if it matches
    a known Node.js-based agent.
    """
    try:
        children_path = Path(f"/proc/{pane_pid}/task/{pane_pid}/children")
        child_pids = children_path.read_text().split()
    except (OSError, ValueError):
        return None

    for child_pid in child_pids:
        try:
            cmdline = Path(f"/proc/{child_pid}/cmdline").read_bytes()
            args = cmdline.decode(errors="replace").split("\0")
            for arg in args:
                basename = arg.rsplit("/", 1)[-1] if "/" in arg else arg
                if basename in _NODE_AGENTS:
                    return _NODE_AGENTS[basename]
        except OSError:
            continue
    return None


def _parse_sessions(raw: str) -> list[tuple[str, str, str]]:
    if not raw:
        return []
    sessions = []
    for line in raw.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3:
            sessions.append((parts[0], parts[1], parts[2]))
    return sessions


def _parse_all_panes(raw: str) -> dict[str, list[tuple[int, int, AgentType]]]:
    """Parse `list-panes -a` output into a dict keyed by session name.

    Each value is a list of (window_index, pane_index, agent_type) for agent panes.
    Format: session_name:window_index:pane_index:pane_current_command:pane_pid
    """
    result: dict[str, list[tuple[int, int, AgentType]]] = {}
    if not raw:
        return result
    for line in raw.splitlines():
        parts = line.split(":", 4)
        if len(parts) != 5:
            continue
        session_name, window_idx, pane_idx, cmd, pid = parts
        cmd = cmd.strip()
        agent_type = _AGENT_PROCESSES.get(cmd)
        if agent_type is None and cmd == "node":
            try:
                agent_type = _resolve_node_agent(int(pid))
            except (ValueError, TypeError):
                pass
        if agent_type is not None:
            result.setdefault(session_name, []).append(
                (int(window_idx), int(pane_idx), agent_type)
            )
    return result


def _find_agent_panes(pane_output: str) -> list[tuple[int, int, AgentType]]:
    """Find ALL panes running recognized AI agents.

    Returns list of (window_index, pane_index, agent_type).
    Format: window_index:pane_index:pane_current_command:pane_pid
    """
    results = []
    for line in pane_output.splitlines():
        parts = line.split(":", 3)
        if len(parts) >= 3:
            cmd = parts[2].strip()
            agent_type = _AGENT_PROCESSES.get(cmd)
            if agent_type is None and cmd == "node" and len(parts) == 4:
                try:
                    agent_type = _resolve_node_agent(int(parts[3]))
                except (ValueError, TypeError):
                    pass
            if agent_type is not None:
                results.append((int(parts[0]), int(parts[1]), agent_type))
    return results


def scan_sessions() -> list[Session]:
    raw = run_tmux("list-sessions", "-F", "#{session_name}:#{session_id}:#{session_path}")
    parsed = _parse_sessions(raw)
    hook_states = load_all_states()

    # Single call to get all panes across all sessions
    all_panes_raw = run_tmux(
        "list-panes", "-a",
        "-F", "#{session_name}:#{window_index}:#{pane_index}:#{pane_current_command}:#{pane_pid}",
    )
    all_panes = _parse_all_panes(all_panes_raw)

    sessions = []
    for name, session_id, path in parsed:
        agents = all_panes.get(name, [])
        for window_index, pane_index, agent_type in agents:
            hook_state = hook_states.get(path)

            # Skip capture-pane when hook state exists (capture is only
            # needed for detect_status fallback and parse_details)
            if hook_state is not None:
                status = _HOOK_STATE_MAP.get(hook_state.state, SessionStatus.IDLE)
                last_message = hook_state.last_message
                details = SessionDetails()
            else:
                pane_content = run_tmux(
                    "capture-pane", "-t", f"{name}:{window_index}.{pane_index}", "-p",
                )
                details = parse_details(pane_content)
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
