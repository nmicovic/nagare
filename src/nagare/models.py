from dataclasses import dataclass
from enum import Enum


class SessionStatus(Enum):
    WAITING_INPUT = "waiting_input"
    RUNNING = "running"
    IDLE = "idle"
    DEAD = "dead"


STATUS_ICONS: dict[SessionStatus, str] = {
    SessionStatus.WAITING_INPUT: "🔴",
    SessionStatus.RUNNING: "🟡",
    SessionStatus.IDLE: "🟢",
    SessionStatus.DEAD: "⚪",
}


STATUS_LABELS: dict[SessionStatus, str] = {
    SessionStatus.WAITING_INPUT: "Waiting for input",
    SessionStatus.RUNNING: "Working",
    SessionStatus.IDLE: "Idle",
    SessionStatus.DEAD: "Exited",
}


@dataclass(frozen=True)
class SessionDetails:
    git_branch: str = ""
    model: str = ""
    context_usage: str = ""


@dataclass(frozen=True)
class Session:
    name: str
    session_id: str
    path: str
    window_index: int
    pane_index: int
    status: SessionStatus
    details: SessionDetails = SessionDetails()
    last_message: str = ""

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS[self.status]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def display(self) -> str:
        return f"{self.status_icon} {self.name}"
