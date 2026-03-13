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
from nagare.tmux.scanner import scan_sessions

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
PID_FILE = DATA_DIR / "daemon.pid"
STORE_PATH = DATA_DIR / "notifications.json"


class SessionMonitor:

    def __init__(self, backend: NotificationBackend, store: NotificationStore) -> None:
        self._backend = backend
        self._store = store
        self._prev_status: dict[str, SessionStatus] = {}

    def poll(self) -> None:
        sessions = scan_sessions()
        for session in sessions:
            prev = self._prev_status.get(session.name)
            if session.status == SessionStatus.WAITING_INPUT and prev != SessionStatus.WAITING_INPUT:
                msg = f"{session.name} is waiting for input"
                self._backend.notify(msg, session.name, "high")
                self._store.add(session.name, msg)
            self._prev_status[session.name] = session.status


def run_daemon() -> None:
    config = load_config()
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Write PID file
    PID_FILE.write_text(str(os.getpid()))

    backend = TmuxNotificationBackend(duration=config.notification_duration)
    store = NotificationStore(STORE_PATH)
    monitor = SessionMonitor(backend, store)

    def handle_signal(sig, frame):
        PID_FILE.unlink(missing_ok=True)
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while True:
            monitor.poll()
            time.sleep(config.poll_interval)
    finally:
        PID_FILE.unlink(missing_ok=True)
