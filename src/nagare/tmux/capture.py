import subprocess


def _run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def capture_pane(session_name: str, pane_index: int) -> str:
    return _run_tmux("capture-pane", "-t", f"{session_name}:{pane_index}", "-p", "-e")
