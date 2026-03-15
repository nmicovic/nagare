"""Notification delivery functions.

Each function is fire-and-forget: exceptions are silently swallowed so
that a notification failure never crashes the hook handler.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from nagare.log import logger
from nagare.tmux import run_tmux


def _find_nagare_bin() -> str | None:
    """Find the nagare binary, checking PATH and known venv location."""
    found = shutil.which("nagare")
    if found:
        return found
    venv_bin = Path(__file__).resolve().parents[3] / ".venv" / "bin" / "nagare"
    if venv_bin.exists():
        return str(venv_bin)
    return None


def _get_client_name() -> str | None:
    """Get the name of the first attached tmux client."""
    try:
        result = run_tmux("list-clients", "-F", "#{client_name}")
        if result:
            return result.splitlines()[0]
    except Exception:
        pass
    return None


def send_toast(message: str, duration: int = 3000) -> None:
    """Send a tmux status-bar toast notification to the user's client."""
    try:
        client = _get_client_name()
        if client:
            run_tmux("display-message", "-t", client, "-d", str(duration), f"🔴 {message}")
        else:
            run_tmux("display-message", "-d", str(duration), f"🔴 {message}")
    except Exception:
        pass


def send_bell() -> None:
    """Send a terminal bell to trigger OS/terminal alerts."""
    try:
        subprocess.run(
            ["tmux", "run-shell", "printf '\\a'"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        pass


def detect_os_notify_cmd() -> list[str] | None:
    """Detect the best OS notification command available."""
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
            timeout=5,
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
    """Launch the nagare popup-notif TUI via tmux display-popup.

    Note: when called from a hook subprocess, this opens as a new tmux
    window rather than a popup overlay. This is a tmux limitation —
    display-popup only creates overlays from pane-descendant processes.
    The notification content still displays correctly.
    """
    try:
        nagare_bin = _find_nagare_bin()
        if nagare_bin is None:
            logger.warning("send_popup: nagare binary not found")
            return

        client = _get_client_name()
        if client is None:
            logger.warning("send_popup: no tmux client found")
            return

        logger.info("send_popup: session=%s event=%s client=%s", session_name, event_type, client)

        safe_msg = message.replace('"', '\\"').replace("'", "")
        safe_name = session_name.replace('"', "").replace("'", "")

        popup_cmd = (
            f'{nagare_bin} popup-notif'
            f' --session "{safe_name}"'
            f' --event {event_type}'
            f' --message "{safe_msg}"'
            f' --timeout {popup_timeout}'
        )
        if working_seconds:
            popup_cmd += f" --duration {working_seconds}"

        subprocess.Popen(
            ["tmux", "display-popup", "-t", client, "-w", "90%", "-h", "90%", "-E", popup_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass
