import os
import subprocess


def run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def switch_to_session(target: str) -> None:
    """Switch to a tmux session. Uses switch-client inside tmux, attach-session outside."""
    if os.environ.get("TMUX"):
        run_tmux("switch-client", "-t", target)
    else:
        subprocess.run(["tmux", "attach-session", "-t", target])
