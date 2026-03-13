import subprocess


def run_tmux(*args: str) -> str:
    result = subprocess.run(
        ["tmux", *args],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()
