from abc import ABC, abstractmethod


class NotificationBackend(ABC):

    @abstractmethod
    def notify(self, message: str, session_name: str, urgency: str) -> None:
        """Send a notification to the user."""
