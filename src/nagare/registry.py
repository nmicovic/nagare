"""Session registry — persistent list of known sessions."""

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

from nagare.log import logger

REGISTRY_PATH = Path.home() / ".local" / "share" / "nagare" / "sessions.json"


@dataclass
class RegisteredSession:
    name: str
    path: str
    agent: str = "claude"
    last_accessed: str = ""
    starred: bool = False

    def touch(self) -> None:
        self.last_accessed = datetime.now(timezone.utc).isoformat()


class SessionRegistry:
    def __init__(self, path: Path = REGISTRY_PATH) -> None:
        self._path = path
        self._sessions: list[RegisteredSession] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                data = json.loads(self._path.read_text())
                self._sessions = [RegisteredSession(**s) for s in data]
            except (json.JSONDecodeError, OSError, TypeError):
                self._sessions = []

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([asdict(s) for s in self._sessions], indent=2))

    def list_all(self) -> list[RegisteredSession]:
        return list(self._sessions)

    def find(self, name: str) -> RegisteredSession | None:
        for s in self._sessions:
            if s.name == name:
                return s
        return None

    def find_by_path(self, path: str) -> RegisteredSession | None:
        for s in self._sessions:
            if s.path == path:
                return s
        return None

    def register(self, name: str, path: str, agent: str = "claude") -> RegisteredSession:
        """Add or update a session in the registry."""
        existing = self.find(name)
        if existing:
            existing.path = path
            existing.agent = agent
            existing.touch()
        else:
            existing = RegisteredSession(name=name, path=path, agent=agent)
            existing.touch()
            self._sessions.append(existing)
        self._save()
        logger.debug("registered session %s at %s", name, path)
        return existing

    def remove(self, name: str) -> None:
        self._sessions = [s for s in self._sessions if s.name != name]
        self._save()

    def toggle_star(self, name: str) -> bool:
        """Toggle starred status. Returns new starred state."""
        s = self.find(name)
        if s:
            s.starred = not s.starred
            self._save()
            return s.starred
        return False

    def is_starred(self, name: str) -> bool:
        s = self.find(name)
        return s.starred if s else False

    def touch(self, name: str) -> None:
        s = self.find(name)
        if s:
            s.touch()
            self._save()

    def auto_discover(self) -> int:
        """Import sessions from currently running tmux agent panes."""
        from nagare.tmux.scanner import scan_sessions
        count = 0
        for session in scan_sessions():
            if not self.find(session.name):
                self.register(session.name, session.path, session.agent_type.value)
                count += 1
        return count
