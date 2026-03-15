from dataclasses import dataclass, field
from enum import Enum


class AgentType(Enum):
    CLAUDE = "claude"
    OPENCODE = "opencode"
    UNKNOWN = "unknown"


# Single-line badge for list view
AGENT_ICONS: dict[AgentType, str] = {
    AgentType.CLAUDE: "[bold #da7756 on #3b2820] C [/]",
    AgentType.OPENCODE: "[bold #00e5ff on #002b33] O [/]",
    AgentType.UNKNOWN: "[dim] ? [/]",
}

# 3-line block art for grid view
AGENT_BLOCK: dict[AgentType, tuple[str, str, str]] = {
    AgentType.CLAUDE: (
        "[bold #da7756 on #3b2820]╔═══╗[/]",
        "[bold #da7756 on #3b2820]║ C ║[/]",
        "[bold #da7756 on #3b2820]╚═══╝[/]",
    ),
    AgentType.OPENCODE: (
        "[bold #00e5ff on #002b33]╔═══╗[/]",
        "[bold #00e5ff on #002b33]║ O ║[/]",
        "[bold #00e5ff on #002b33]╚═══╝[/]",
    ),
    AgentType.UNKNOWN: (
        "[dim]╔═══╗[/]",
        "[dim]║ ? ║[/]",
        "[dim]╚═══╝[/]",
    ),
}

AGENT_LABELS: dict[AgentType, str] = {
    AgentType.CLAUDE: "Claude",
    AgentType.OPENCODE: "OpenCode",
    AgentType.UNKNOWN: "Unknown",
}


class SessionStatus(Enum):
    WAITING_INPUT = "waiting_input"
    RUNNING = "running"
    IDLE = "idle"
    DEAD = "dead"


STATUS_ICONS: dict[SessionStatus, str] = {
    SessionStatus.WAITING_INPUT: "[#db4b4b]●[/]",
    SessionStatus.RUNNING: "[#e0af68]●[/]",
    SessionStatus.IDLE: "[#00D26A]●[/]",
    SessionStatus.DEAD: "[#565f89]●[/]",
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
    agent_type: AgentType = AgentType.CLAUDE
    details: SessionDetails = field(default_factory=SessionDetails)
    last_message: str = ""

    @property
    def status_icon(self) -> str:
        return STATUS_ICONS[self.status]

    @property
    def agent_icon(self) -> str:
        return AGENT_ICONS[self.agent_type]

    @property
    def agent_block(self) -> tuple[str, str, str]:
        return AGENT_BLOCK[self.agent_type]

    @property
    def agent_label(self) -> str:
        return AGENT_LABELS[self.agent_type]

    @property
    def status_label(self) -> str:
        return STATUS_LABELS[self.status]

    @property
    def display(self) -> str:
        return f"{self.status_icon} {self.name}"
