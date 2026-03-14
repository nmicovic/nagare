import json
import shutil
from pathlib import Path

from nagare.config import NagareConfig, load_config, CONFIG_PATH

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def generate_tmux_config(config: NagareConfig | None = None) -> str:
    if config is None:
        config = load_config()
    return (
        "# nagare - Claude Code session manager\n"
        f'bind g display-popup -w{config.picker_width} -h{config.picker_height} -E "nagare pick"\n'
        'bind e display-popup -w60% -h60% -E "nagare notifs"\n'
    )


def _get_nagare_bin() -> str:
    """Find the nagare binary path."""
    path = shutil.which("nagare")
    if path:
        return path
    # Fallback to the venv bin
    venv_bin = Path(__file__).resolve().parents[2] / ".venv" / "bin" / "nagare"
    if venv_bin.exists():
        return str(venv_bin)
    return "nagare"


def _install_hooks() -> bool:
    """Add nagare hooks to Claude Code settings.json."""
    nagare_bin = _get_nagare_bin()
    hook_command = f"{nagare_bin} hook-state"

    nagare_hooks = {
        "UserPromptSubmit": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
        ],
        "Notification": [
            {
                "matcher": "idle_prompt|permission_prompt|elicitation_dialog",
                "hooks": [{"type": "command", "command": hook_command, "timeout": 5}],
            }
        ],
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
        ],
        "SessionStart": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5}]}
        ],
    }

    if not CLAUDE_SETTINGS_PATH.exists():
        print(f"Claude Code settings not found at {CLAUDE_SETTINGS_PATH}")
        return False

    try:
        settings = json.loads(CLAUDE_SETTINGS_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to read Claude Code settings: {e}")
        return False

    hooks = settings.setdefault("hooks", {})

    # For each event, add nagare hooks if not already present
    for event, hook_groups in nagare_hooks.items():
        existing = hooks.get(event, [])
        # Check if nagare hook already installed
        already_installed = any(
            any("nagare hook-state" in h.get("command", "") for h in group.get("hooks", []))
            for group in existing
        )
        if not already_installed:
            existing.extend(hook_groups)
            hooks[event] = existing

    settings["hooks"] = hooks
    CLAUDE_SETTINGS_PATH.write_text(json.dumps(settings, indent=2))
    return True


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

    # Install Claude Code hooks
    print("\nInstalling Claude Code hooks...")
    if _install_hooks():
        print("Hooks installed in ~/.claude/settings.json")
    else:
        print("Could not install hooks automatically.")

    print("\nAdd these lines to your ~/.tmux.conf:\n")
    print(generate_tmux_config())
    print("Then reload tmux config: tmux source-file ~/.tmux.conf")
