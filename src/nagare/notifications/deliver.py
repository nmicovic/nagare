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

POPUP_FIFO = Path.home() / ".local" / "share" / "nagare" / "popup.fifo"


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

    Writes the popup command to a FIFO that the popup watcher reads.
    The watcher runs inside a tmux pane, so display-popup creates a
    proper overlay instead of a new window.

    Falls back to direct Popen (new window) if the FIFO doesn't exist.
    """
    try:
        nagare_bin = _find_nagare_bin()
        if nagare_bin is None:
            logger.warning("send_popup: nagare binary not found")
            return

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

        display_cmd = f"tmux display-popup -w 90% -h 90% -E '{popup_cmd}'"

        # Try FIFO first (overlay popup via watcher)
        if POPUP_FIFO.exists():
            try:
                # Non-blocking write to FIFO
                fd = os.open(str(POPUP_FIFO), os.O_WRONLY | os.O_NONBLOCK)
                os.write(fd, (display_cmd + "\n").encode())
                os.close(fd)
                logger.info("send_popup: wrote to FIFO for %s", session_name)
                return
            except OSError:
                logger.debug("send_popup: FIFO write failed, falling back to direct")

        # Fallback: direct Popen (opens as new window, not overlay)
        client = _get_client_name()
        if client is None:
            logger.warning("send_popup: no tmux client found")
            return

        logger.info("send_popup: direct fallback for %s (no watcher)", session_name)
        subprocess.Popen(
            ["tmux", "display-popup", "-t", client, "-w", "90%", "-h", "90%", "-E", popup_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def run_popup_watcher() -> None:
    """Blocking loop: read popup commands from FIFO and execute them.

    Must run inside a tmux pane so display-popup creates overlay popups.
    Started by `nagare setup` or `nagare popup-watcher`.
    """
    import signal

    fifo = POPUP_FIFO
    fifo.parent.mkdir(parents=True, exist_ok=True)

    # Clean up FIFO on exit
    def cleanup(signum=None, frame=None):
        try:
            fifo.unlink(missing_ok=True)
        except Exception:
            pass
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, cleanup)
    signal.signal(signal.SIGINT, cleanup)

    # Create FIFO if it doesn't exist
    if fifo.exists():
        fifo.unlink()
    os.mkfifo(str(fifo))
    logger.info("popup watcher started, FIFO at %s", fifo)

    try:
        while True:
            # open() blocks until a writer connects
            with open(fifo) as f:
                for line in f:
                    cmd = line.strip()
                    if not cmd:
                        continue
                    try:
                        logger.debug("popup watcher executing: %s", cmd[:80])
                        subprocess.run(cmd, shell=True, timeout=30)
                    except Exception:
                        logger.exception("popup watcher: command failed")
    finally:
        cleanup()


def start_popup_watcher() -> bool:
    """Start the popup watcher in a hidden tmux window.

    Creates a window named '_nagare-watcher' that runs the FIFO loop.
    Returns True if started, False if already running or failed.
    """
    nagare_bin = _find_nagare_bin()
    if not nagare_bin:
        return False

    # Check if watcher is already running
    try:
        windows = run_tmux("list-windows", "-a", "-F", "#{window_name}")
        if "_nagare-watcher" in windows.splitlines():
            return True  # Already running
    except Exception:
        pass

    try:
        # Find a session to host the watcher.
        # Prefer any session that already has an agent — the watcher
        # needs to be a pane descendant for display-popup overlays.
        sessions = run_tmux("list-sessions", "-F", "#{session_name}").splitlines()
        if not sessions:
            return False

        # Pick the first session (any will do — the watcher just needs
        # to live in a pane for tmux overlay context)
        host = sessions[0]

        run_tmux(
            "new-window", "-d", "-t", host,
            "-n", "_nagare-watcher",
            f"{nagare_bin} popup-watcher",
        )
        logger.info("popup watcher started in session %s", host)
        return True
    except Exception:
        logger.exception("failed to start popup watcher")
        return False
