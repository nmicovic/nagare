import subprocess


def attach_session(session_name: str) -> None:
    subprocess.run(["tmux", "attach-session", "-t", session_name])
