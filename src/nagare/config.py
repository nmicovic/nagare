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
class AnimationConfig:
    jump_animation: str = "flash"  # flash, pulse, fade, sweep, shrink, none
    flash_duration: float = 0.2
    pulse_duration: float = 0.4
    fade_duration: float = 0.25
    sweep_duration: float = 0.2
    shrink_duration: float = 0.3


_ANIMATION_DEFAULTS = dict(
    jump_animation="flash",
    flash_duration=0.2,
    pulse_duration=0.4,
    fade_duration=0.25,
    sweep_duration=0.2,
    shrink_duration=0.3,
)


@dataclass(frozen=True)
class SoundsConfig:
    enabled: bool = False
    pack: str = "peon"
    volume: float = 0.7
    session_start: bool = True
    task_acknowledge: bool = False  # fires on every prompt, can be noisy
    task_complete: bool = True
    input_required: bool = True
    session_end: bool = False
    sessions: dict[str, dict] = field(default_factory=dict)  # per-session overrides


_SOUNDS_DEFAULTS = dict(
    enabled=False, pack="peon", volume=0.7,
    session_start=True, task_acknowledge=False, task_complete=True,
    input_required=True, session_end=False,
)


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    engine: str = "auto"  # auto, say, piper, edge-tts, espeak, wsl-sapi
    voice: str = ""  # engine-specific voice name
    speed: int = 160  # words per minute
    volume: float = 0.8
    session_start: bool = False
    task_acknowledge: bool = False
    task_complete: bool = True
    input_required: bool = True
    session_end: bool = False
    templates: dict[str, str] = field(default_factory=dict)
    sessions: dict[str, dict] = field(default_factory=dict)


_VOICE_DEFAULTS = dict(
    enabled=False, engine="auto", voice="", speed=160, volume=0.8,
    session_start=False, task_acknowledge=False, task_complete=True,
    input_required=True, session_end=False,
)


@dataclass(frozen=True)
class NagareConfig:
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    animation: AnimationConfig = field(default_factory=AnimationConfig)
    sounds: SoundsConfig = field(default_factory=SoundsConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    notification_duration: int = 3000
    picker_width: str = "80%"
    picker_height: str = "80%"
    grid_refresh_interval: float = 0.5
    quick_project_path: str = "~/Prototypes"
    icon_style: str = "emoji"  # "emoji" or "ascii"
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

    # Parse animation config
    anim_data = data.get("animation", {})
    anim_merged = {**_ANIMATION_DEFAULTS, **anim_data}
    animation_config = AnimationConfig(**anim_merged)

    # Parse sounds config
    sounds_data = data.get("sounds", {})
    sounds_sessions: dict[str, dict] = {}
    for sname, sval in sounds_data.get("sessions", {}).items():
        sounds_sessions[sname] = dict(sval)
    sounds_merged = {**_SOUNDS_DEFAULTS}
    for k in _SOUNDS_DEFAULTS:
        if k in sounds_data and k != "sessions":
            sounds_merged[k] = sounds_data[k]
    sounds_config = SoundsConfig(**sounds_merged, sessions=sounds_sessions)

    # Parse voice config
    voice_data = data.get("voice", {})
    voice_sessions: dict[str, dict] = {}
    for sname, sval in voice_data.get("sessions", {}).items():
        voice_sessions[sname] = dict(sval)
    voice_templates: dict[str, str] = {}
    for tname, tval in voice_data.get("templates", {}).items():
        voice_templates[tname] = str(tval)
    voice_merged = {**_VOICE_DEFAULTS}
    for k in _VOICE_DEFAULTS:
        if k in voice_data and k not in ("sessions", "templates"):
            voice_merged[k] = voice_data[k]
    voice_config = VoiceConfig(**voice_merged, templates=voice_templates, sessions=voice_sessions)

    return NagareConfig(
        notifications=notification_config,
        animation=animation_config,
        sounds=sounds_config,
        voice=voice_config,
        notification_duration=notifs.get("duration", 3000),
        picker_width=picker.get("popup_width", "80%"),
        picker_height=picker.get("popup_height", "80%"),
        grid_refresh_interval=picker.get("grid_refresh_interval", 0.5),
        quick_project_path=picker.get("quick_project_path", "~/Prototypes"),
        icon_style=appearance.get("icon_style", "emoji"),
        theme=appearance.get("theme", "tokyonight"),
    )


def save_notification_config(notif_config: NotificationConfig) -> None:
    """Write the notification config back to the TOML file.

    Preserves non-notification sections (appearance, picker, etc.)
    by reading the file, stripping all [notifications*] sections,
    and rewriting them from the dataclass.
    """
    path = Path(CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Read existing content and strip notification sections
    other_lines: list[str] = []
    if path.exists():
        in_notif_section = False
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if stripped.startswith("[notifications"):
                in_notif_section = True
                continue
            elif stripped.startswith("[") and not stripped.startswith("[notifications"):
                in_notif_section = False
            if not in_notif_section:
                other_lines.append(line)

    # Remove trailing blank lines from other sections
    while other_lines and not other_lines[-1].strip():
        other_lines.pop()

    def _bool(v: bool) -> str:
        return "true" if v else "false"

    notif_lines = [
        "[notifications]",
        f"enabled = {_bool(notif_config.enabled)}",
        "",
        "[notifications.needs_input]",
        f"toast = {_bool(notif_config.needs_input.toast)}",
        f"bell = {_bool(notif_config.needs_input.bell)}",
        f"os_notify = {_bool(notif_config.needs_input.os_notify)}",
        f"popup = {_bool(notif_config.needs_input.popup)}",
        f"popup_timeout = {notif_config.needs_input.popup_timeout}",
        f"min_working_seconds = {notif_config.needs_input.min_working_seconds}",
        "",
        "[notifications.task_complete]",
        f"toast = {_bool(notif_config.task_complete.toast)}",
        f"bell = {_bool(notif_config.task_complete.bell)}",
        f"os_notify = {_bool(notif_config.task_complete.os_notify)}",
        f"popup = {_bool(notif_config.task_complete.popup)}",
        f"popup_timeout = {notif_config.task_complete.popup_timeout}",
        f"min_working_seconds = {notif_config.task_complete.min_working_seconds}",
    ]

    # Write per-session overrides
    for session_name, overrides in notif_config.sessions.items():
        notif_lines.append("")
        notif_lines.append(f"[notifications.sessions.{session_name}]")
        for key, value in overrides.items():
            if isinstance(value, bool):
                notif_lines.append(f"{key} = {_bool(value)}")
            elif isinstance(value, int):
                notif_lines.append(f"{key} = {value}")
            else:
                notif_lines.append(f'{key} = "{value}"')

    # Combine: notifications first, then other sections
    parts = []
    if notif_lines:
        parts.append("\n".join(notif_lines))
    if other_lines:
        parts.append("\n".join(other_lines))

    path.write_text("\n\n".join(parts) + "\n")


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
