"""Create new tmux sessions with AI agents."""

from pathlib import Path

from nagare.log import logger
from nagare.tmux import run_tmux


def create_session(
    path: str,
    name: str | None = None,
    agent: str = "claude",
    continue_session: bool = True,
) -> str:
    """Create a new tmux session and launch an AI agent in it.

    Args:
        path: Working directory for the session.
        name: Session name. Auto-generated from path basename if None.
        agent: Agent to launch ("claude" or "opencode").
        continue_session: If True, launch with -c to continue previous session.

    Returns:
        The session name that was created.

    Raises:
        ValueError: If path doesn't exist or isn't a directory.
        RuntimeError: If session creation fails.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.is_dir():
        raise ValueError(f"Path does not exist or is not a directory: {path}")

    if name is None:
        name = resolved.name

    # Ensure unique session name
    name = _unique_session_name(name)

    # Create tmux session
    run_tmux("new-session", "-d", "-s", name, "-c", str(resolved))
    logger.info("created session %s at %s", name, resolved)

    # Launch agent
    flag = " -c" if continue_session else ""
    cmd = f"{agent}{flag}"
    run_tmux("send-keys", "-t", name, cmd, "Enter")
    logger.info("launched %s in session %s", cmd, name)

    return name


def _unique_session_name(name: str) -> str:
    """Ensure the session name doesn't conflict with existing tmux sessions."""
    existing = set()
    try:
        raw = run_tmux("list-sessions", "-F", "#{session_name}")
        existing = set(raw.splitlines())
    except Exception:
        pass

    if name not in existing:
        return name

    for i in range(2, 100):
        candidate = f"{name}-{i}"
        if candidate not in existing:
            return candidate

    return f"{name}-{id(name)}"


def list_directories(partial: str, max_results: int = 10) -> list[str]:
    """List directories matching a partial path for autocomplete.

    Handles ~ expansion and returns up to max_results matches.
    """
    expanded = Path(partial).expanduser()

    if partial.endswith("/"):
        # List subdirectories of the given path
        parent = expanded
        prefix = ""
    else:
        parent = expanded.parent
        prefix = expanded.name

    if not parent.is_dir():
        return []

    results = []
    try:
        for entry in sorted(parent.iterdir()):
            if not entry.is_dir():
                continue
            if entry.name.startswith("."):
                continue
            if prefix and not entry.name.lower().startswith(prefix.lower()):
                continue
            # Reconstruct path with ~ if the original used it
            full = str(entry)
            home = str(Path.home())
            if full.startswith(home):
                full = "~" + full[len(home):]
            results.append(full + "/")
            if len(results) >= max_results:
                break
    except PermissionError:
        pass

    return results
