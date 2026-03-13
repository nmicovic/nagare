from dataclasses import dataclass
from enum import Enum


class SessionStatus(Enum):
    ALIVE = "alive"
    DEAD = "dead"


STATUS_ICONS: dict[SessionStatus, str] = {
    SessionStatus.ALIVE: "●",
    SessionStatus.DEAD: "○",
}


@dataclass(frozen=True)
class Session:
    name: str
    session_id: str
    path: str
    pane_index: int
    status: SessionStatus

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS[self.status]

    @property
    def display(self) -> str:
        return f"{self.status_icon} {self.name}"
