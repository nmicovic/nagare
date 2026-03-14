import re

from nagare.models import SessionDetails, SessionStatus

# The bare ❯ prompt on its own line means Claude is waiting for user input
_WAITING_PROMPT_RE = re.compile(r"^❯\s*$", re.MULTILINE)

# Patterns that indicate Claude Code is presenting a choice/confirmation
_WAITING_CHOICE_PATTERNS = [
    re.compile(r"❯\s+\d+\.\s+(Yes|No)"),       # Choice prompts: ❯ 1. Yes
    re.compile(r"Do you want to"),               # Confirmation prompts
    re.compile(r"Esc to cancel"),                # Bottom of a prompt menu
]

# Patterns that indicate Claude Code is actively working
_RUNNING_PATTERNS = [
    re.compile(r"\(running\)"),                  # Status bar shows (running)
    re.compile(r"⠋|⠙|⠹|⠸|⠼|⠴|⠦|⠧|⠇|⠏|⠐|⠂"),  # Braille spinners
]


def detect_status(pane_content: str) -> SessionStatus:
    """Detect Claude Code session status by parsing pane content."""
    if not pane_content or not pane_content.strip():
        return SessionStatus.DEAD

    # Check last ~15 lines for patterns (most signals are near the bottom)
    tail = "\n".join(pane_content.splitlines()[-15:])

    # Check for choice/confirmation prompts first (these are WAITING_INPUT)
    for pattern in _WAITING_CHOICE_PATTERNS:
        if pattern.search(tail):
            return SessionStatus.WAITING_INPUT

    # Check if Claude is actively working
    for pattern in _RUNNING_PATTERNS:
        if pattern.search(tail):
            return SessionStatus.RUNNING

    # A bare ❯ prompt means Claude finished — session is idle
    if _WAITING_PROMPT_RE.search(tail):
        return SessionStatus.IDLE

    # If we see the status bar but no prompt, Claude is actively working
    if "⏵⏵" in tail:
        return SessionStatus.RUNNING

    return SessionStatus.IDLE


# Pattern for Claude Code status bar:
# nemke@Cosmo:/path/to/project (git:branch) | Model X.Y | ctx:NN%
_STATUS_BAR_RE = re.compile(
    r"\(git:(?P<branch>[^)]+)\)"
    r"\s*\|\s*(?P<model>[^|]+?)"
    r"\s*\|\s*ctx:(?P<ctx>\d+%)"
)


def parse_details(pane_content: str) -> SessionDetails:
    """Extract git branch, model, and context usage from Claude Code status bar."""
    if not pane_content:
        return SessionDetails()

    # Status bar is near the bottom of the pane
    tail = "\n".join(pane_content.splitlines()[-5:])

    match = _STATUS_BAR_RE.search(tail)
    if match:
        return SessionDetails(
            git_branch=match.group("branch").strip(),
            model=match.group("model").strip(),
            context_usage=match.group("ctx").strip(),
        )
    return SessionDetails()
