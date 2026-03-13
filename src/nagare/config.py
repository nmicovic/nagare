import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = str(Path.home() / ".config" / "nagare" / "config.toml")


@dataclass(frozen=True)
class NagareConfig:
    notification_backend: str = "tmux"
    notification_duration: int = 2000
    poll_interval: int = 3
    picker_width: str = "80%"
    picker_height: str = "80%"


def load_config() -> NagareConfig:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return NagareConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    notifs = data.get("notifications", {})
    picker = data.get("picker", {})

    return NagareConfig(
        notification_backend=notifs.get("backend", "tmux"),
        notification_duration=notifs.get("duration", 2000),
        poll_interval=notifs.get("poll_interval", 3),
        picker_width=picker.get("popup_width", "80%"),
        picker_height=picker.get("popup_height", "80%"),
    )
