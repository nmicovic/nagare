import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = str(Path.home() / ".config" / "nagare" / "config.toml")


@dataclass(frozen=True)
class NotificationEventConfig:
    toast: bool = True
    bell: bool = False
    os_notify: bool = False
    popup: bool = False
    popup_timeout: int = 10
    min_working_seconds: int = 0


# Default instances for each event type
_NEEDS_INPUT_DEFAULTS = dict(
    toast=True, bell=True, os_notify=True, popup=False,
    popup_timeout=10, min_working_seconds=0,
)

_TASK_COMPLETE_DEFAULTS = dict(
    toast=True, bell=False, os_notify=False, popup=False,
    popup_timeout=10, min_working_seconds=30,
)


@dataclass(frozen=True)
class NotificationConfig:
    enabled: bool = True
    needs_input: NotificationEventConfig = field(
        default_factory=lambda: NotificationEventConfig(**_NEEDS_INPUT_DEFAULTS)
    )
    task_complete: NotificationEventConfig = field(
        default_factory=lambda: NotificationEventConfig(**_TASK_COMPLETE_DEFAULTS)
    )
    sessions: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class NagareConfig:
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    notification_duration: int = 3000
    picker_width: str = "80%"
    picker_height: str = "80%"
    theme: str = "tokyonight"


def _parse_event_config(
    data: dict, defaults: dict,
) -> NotificationEventConfig:
    merged = {**defaults, **{k: v for k, v in data.items()}}
    return NotificationEventConfig(**merged)


def load_config() -> NagareConfig:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return NagareConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    notifs = data.get("notifications", {})
    picker = data.get("picker", {})
    appearance = data.get("appearance", {})

    # Parse event configs from nested tables
    needs_input_data = notifs.get("needs_input", {})
    task_complete_data = notifs.get("task_complete", {})

    needs_input = _parse_event_config(needs_input_data, _NEEDS_INPUT_DEFAULTS)
    task_complete = _parse_event_config(task_complete_data, _TASK_COMPLETE_DEFAULTS)

    # Parse per-session overrides
    sessions: dict[str, dict] = {}
    sessions_data = notifs.get("sessions", {})
    for session_name, session_settings in sessions_data.items():
        sessions[session_name] = dict(session_settings)

    notification_config = NotificationConfig(
        enabled=notifs.get("enabled", True),
        needs_input=needs_input,
        task_complete=task_complete,
        sessions=sessions,
    )

    return NagareConfig(
        notifications=notification_config,
        notification_duration=notifs.get("duration", 3000),
        picker_width=picker.get("popup_width", "80%"),
        picker_height=picker.get("popup_height", "80%"),
        theme=appearance.get("theme", "tokyonight"),
    )


def save_theme(theme_name: str) -> None:
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        content = path.read_text()
        if re.search(r"^\[appearance\]", content, re.MULTILINE):
            content = re.sub(
                r'(^\[appearance\].*?theme\s*=\s*)"[^"]*"',
                rf'\1"{theme_name}"',
                content,
                flags=re.MULTILINE | re.DOTALL,
            )
        else:
            content = content.rstrip() + f'\n\n[appearance]\ntheme = "{theme_name}"\n'
    else:
        content = f'[appearance]\ntheme = "{theme_name}"\n'

    path.write_text(content)
