"""Notification delivery functions.

Each function is fire-and-forget: exceptions are silently swallowed so
that a notification failure never crashes the hook handler.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from nagare.tmux import run_tmux


def send_toast(message: str, duration: int = 3000) -> None:
    """Send a tmux status-bar toast notification."""
    try:
        run_tmux("display-message", "-d", str(duration), message)
    except Exception:
        pass


def send_bell() -> None:
    """Send a terminal bell to trigger OS/terminal alerts."""
    try:
        subprocess.run(
            ["tmux", "run-shell", "printf '\\a'"],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def detect_os_notify_cmd() -> list[str] | None:
    """Detect the best OS notification command available.

    Returns the command list to invoke, or None if nothing is available.
    """
    if os.environ.get("WSL_DISTRO_NAME"):
        if shutil.which("wsl-notify-send"):
            return ["wsl-notify-send"]
        return None

    if shutil.which("notify-send"):
        return ["notify-send"]

    return None


def send_os_notify(title: str, message: str) -> None:
    """Send a native OS notification. Silently skips if unavailable."""
    try:
        cmd = detect_os_notify_cmd()
        if cmd is None:
            return
        subprocess.run(
            [*cmd, title, message],
            capture_output=True,
            text=True,
        )
    except Exception:
        pass


def send_popup(
    session_name: str,
    event_type: str,
    message: str,
    working_seconds: int = 0,
    popup_timeout: int = 10,
) -> None:
    """Launch the nagare popup-notif TUI inside a tmux display-popup."""
    try:
        nagare_bin = shutil.which("nagare")
        if nagare_bin is None:
            return

        cmd_parts = [
            nagare_bin,
            "popup-notif",
            "--session", session_name,
            "--event", event_type,
            "--message", message,
            "--timeout", str(popup_timeout),
        ]
        if working_seconds:
            cmd_parts.extend(["--duration", str(working_seconds)])

        run_tmux(
            "display-popup",
            "-w60%",
            "-h30%",
            "-E",
            *cmd_parts,
        )
    except Exception:
        pass
