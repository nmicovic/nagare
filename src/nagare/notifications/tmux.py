from nagare.notifications.base import NotificationBackend
from nagare.tmux import run_tmux


class TmuxNotificationBackend(NotificationBackend):

    def __init__(self, duration: int = 2000) -> None:
        self._duration = duration

    def notify(self, message: str, session_name: str, urgency: str) -> None:
        run_tmux("display-message", "-d", str(self._duration), f"\u26a1 {message}")
