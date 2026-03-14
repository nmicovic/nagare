import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

CONFIG_PATH = str(Path.home() / ".config" / "nagare" / "config.toml")


@dataclass(frozen=True)
class NagareConfig:
    notification_backend: str = "tmux"
    notification_duration: int = 3000
    picker_width: str = "80%"
    picker_height: str = "80%"
    theme: str = "tokyonight"


def load_config() -> NagareConfig:
    path = Path(CONFIG_PATH)
    if not path.exists():
        return NagareConfig()

    with open(path, "rb") as f:
        data = tomllib.load(f)

    notifs = data.get("notifications", {})
    picker = data.get("picker", {})
    appearance = data.get("appearance", {})

    return NagareConfig(
        notification_backend=notifs.get("backend", "tmux"),
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
