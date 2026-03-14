import json
from pathlib import Path

_HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"
_MIN_MESSAGE_LEN = 12


def load_conversation_topics() -> dict[str, str]:
    """Return a mapping of project path -> last meaningful user message."""
    if not _HISTORY_PATH.exists():
        return {}

    topics: dict[str, str] = {}
    try:
        with open(_HISTORY_PATH) as f:
            for line in f:
                entry = json.loads(line)
                project = entry.get("project", "")
                display = entry.get("display", "")
                if project and display and len(display) >= _MIN_MESSAGE_LEN:
                    topics[project] = display
    except (OSError, json.JSONDecodeError):
        return topics

    return topics
