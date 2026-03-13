from abc import ABC, abstractmethod
from collections.abc import Callable

from nagare.models import Session


class SessionTransport(ABC):

    @abstractmethod
    def get_content(self, session: Session) -> str:
        """Get current pane content (for preview mode)."""

    @abstractmethod
    def send_keys(self, session: Session, key: str, character: str | None) -> None:
        """Forward a key event to the session."""

    @abstractmethod
    def start_streaming(self, session: Session, callback: Callable[[str], None]) -> None:
        """Begin high-frequency content updates."""

    @abstractmethod
    def stop_streaming(self) -> None:
        """Stop high-frequency updates."""
