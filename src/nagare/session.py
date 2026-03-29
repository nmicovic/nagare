"""Create new tmux sessions with AI agents."""

from pathlib import Path

from nagare.config import load_config
from nagare.log import logger
from nagare.tmux import run_tmux


def resolve_path(path: str) -> str:
    """Resolve a path, treating bare names as quick projects.

    If path has no '/' or '~', treat it as a subdirectory of
    the configured quick_project_path.
    """
    if "/" not in path and "~" not in path:
        config = load_config()
        return f"{config.quick_project_path}/{path}"
    return path


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
        agent: Agent to launch ("claude", "opencode", or "gemini").
        continue_session: If True, launch with -c to continue previous session.

    Returns:
        The session name that was created.

    Raises:
        ValueError: If path doesn't exist or isn't a directory.
        RuntimeError: If session creation fails.
    """
    path = resolve_path(path)
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        resolved.mkdir(parents=True, exist_ok=True)
        logger.info("created directory %s", resolved)
    if not resolved.is_dir():
        raise ValueError(f"Path is not a directory: {path}")

    if name is None:
        name = resolved.name

    # Check if tmux session already exists
    existing = set()
    try:
        existing = set(run_tmux("list-sessions", "-F", "#{session_name}").splitlines())
    except Exception:
        pass

    if name in existing:
        # Session exists — just launch agent in it
        logger.info("reusing existing tmux session %s", name)
    else:
        # Create new tmux session
        name = _unique_session_name(name)
        run_tmux("new-session", "-d", "-s", name, "-c", str(resolved))
        logger.info("created session %s at %s", name, resolved)

    # Launch agent (gemini auto-resumes, no -c flag needed)
    flag = " -c" if continue_session and agent != "gemini" else ""
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
