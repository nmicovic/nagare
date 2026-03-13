from nagare.tmux import run_tmux


def capture_pane(session_name: str, pane_index: int) -> str:
    return run_tmux("capture-pane", "-t", f"{session_name}:{pane_index}", "-p", "-e")
