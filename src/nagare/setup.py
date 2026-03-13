from pathlib import Path

from nagare.config import NagareConfig, load_config, CONFIG_PATH

DATA_DIR = Path.home() / ".local" / "share" / "nagare"


def generate_tmux_config(config: NagareConfig | None = None) -> str:
    if config is None:
        config = load_config()
    return (
        "# nagare - Claude Code session manager\n"
        f'bind g display-popup -w{config.picker_width} -h{config.picker_height} -E "nagare pick"\n'
        'bind n display-popup -w60% -h60% -E "nagare notifs"\n'
    )


def run_setup() -> None:
    config_path = Path(CONFIG_PATH)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "[notifications]\n"
            "backend = \"tmux\"\n"
            "duration = 2000\n"
            "poll_interval = 3\n"
            "\n"
            "[picker]\n"
            "popup_width = \"80%\"\n"
            "popup_height = \"80%\"\n"
        )
        print(f"Created config: {config_path}")
    else:
        print(f"Config already exists: {config_path}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Data directory: {DATA_DIR}")

    print("\nAdd these lines to your ~/.tmux.conf:\n")
    print(generate_tmux_config())
    print("Then reload tmux config: tmux source-file ~/.tmux.conf")
