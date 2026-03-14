import logging
import os
import sys
import time
import signal
from pathlib import Path

from nagare.config import load_config
from nagare.models import SessionStatus
from nagare.notifications.base import NotificationBackend
from nagare.notifications.store import NotificationStore
from nagare.notifications.tmux import TmuxNotificationBackend
from nagare.tmux import run_tmux
from nagare.tmux.scanner import scan_sessions

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
PID_FILE = DATA_DIR / "daemon.pid"
STORE_PATH = DATA_DIR / "notifications.json"
LOG_PATH = DATA_DIR / "daemon.log"

log = logging.getLogger("nagare.daemon")


def _get_active_session() -> str | None:
    """Get the name of the tmux session the user is currently viewing."""
    try:
        result = run_tmux("display-message", "-p", "#{session_name}")
        return result if result else None
    except Exception:
        return None


class SessionMonitor:

    def __init__(self, backend: NotificationBackend, store: NotificationStore) -> None:
        self._backend = backend
        self._store = store
        self._prev_status: dict[str, SessionStatus] = {}

    def poll(self) -> None:
        sessions = scan_sessions()
        active = _get_active_session()
        log.debug("polled %d sessions, active=%s", len(sessions), active)
        for session in sessions:
            prev = self._prev_status.get(session.name)
            if session.status != prev:
                log.info("%s: %s -> %s", session.name,
                         prev.value if prev else "new", session.status.value)
            if session.status == SessionStatus.WAITING_INPUT and prev != SessionStatus.WAITING_INPUT:
                if session.name == active:
                    log.info("skipping notification for active session: %s", session.name)
                else:
                    msg = f"{session.name} is waiting for input"
                    log.info("notifying: %s", msg)
                    self._backend.notify(msg, session.name, "high")
                    self._store.add(session.name, msg)
            self._prev_status[session.name] = session.status


def run_daemon() -> None:
    config = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    pid = os.getpid()
    PID_FILE.write_text(str(pid))
    log.info("daemon started (pid=%d, poll=%ds)", pid, config.poll_interval)

    backend = TmuxNotificationBackend(duration=config.notification_duration)
    store = NotificationStore(STORE_PATH)
    monitor = SessionMonitor(backend, store)

    def handle_signal(sig, frame):
        log.info("received signal %s, shutting down", sig)
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while True:
            try:
                monitor.poll()
            except Exception:
                log.exception("error during poll")
            time.sleep(config.poll_interval)
    finally:
        log.info("daemon stopped")
        PID_FILE.unlink(missing_ok=True)
