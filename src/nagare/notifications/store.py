import json
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class Notification:
    id: str
    session_name: str
    message: str
    timestamp: str
    read: bool = False


class NotificationStore:

    def __init__(self, path: Path) -> None:
        self._path = path
        self._notifications: list[Notification] = []
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            data = json.loads(self._path.read_text())
            self._notifications = [Notification(**n) for n in data]

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps([asdict(n) for n in self._notifications]))

    def add(self, session_name: str, message: str) -> None:
        notif = Notification(
            id=str(uuid.uuid4()),
            session_name=session_name,
            message=message,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        self._notifications.append(notif)
        self._save()

    def list_all(self) -> list[Notification]:
        return list(reversed(self._notifications))

    def mark_read(self, notif_id: str) -> None:
        for n in self._notifications:
            if n.id == notif_id:
                n.read = True
                break
        self._save()

    def dismiss(self, notif_id: str) -> None:
        self._notifications = [n for n in self._notifications if n.id != notif_id]
        self._save()

    def dismiss_all(self) -> None:
        self._notifications.clear()
        self._save()

    def unread_count(self) -> int:
        return sum(1 for n in self._notifications if not n.read)
