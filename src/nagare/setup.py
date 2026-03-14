import json
import shutil
from pathlib import Path

from nagare.config import NagareConfig, load_config, CONFIG_PATH

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

_DEFAULT_CONFIG = """\
# nagare configuration
# See docs for full reference: https://github.com/nagare/nagare

# ── Notifications ──────────────────────────────────────────────
# Master switch — set to false to disable all notifications
[notifications]
enabled = true

# Notification settings when Claude needs your input
# (permission prompts, elicitation dialogs)
[notifications.needs_input]
# Show a tmux status bar toast (auto-closes after 3 seconds)
toast = true
# Send terminal bell (\\a) — triggers OS/terminal alerts
bell = true
# Send native OS desktop notification (notify-send or WSL equivalent)
os_notify = true
# Show a rich popup window with full context (briefly steals focus)
popup = false
# Seconds before the popup auto-dismisses (only if popup = true)
popup_timeout = 10

# Notification settings when Claude finishes a long-running task
[notifications.task_complete]
# Show a tmux status bar toast on task completion
toast = true
# Send terminal bell on task completion
bell = false
# Send native OS notification on task completion
os_notify = false
# Show rich popup on task completion
popup = false
# Seconds before the popup auto-dismisses
popup_timeout = 10
# Only notify if Claude was working longer than this many seconds
# Prevents notification spam from quick back-and-forth responses
min_working_seconds = 30

# ── Per-Session Overrides ──────────────────────────────────────
# Override notification settings for specific tmux sessions.
# Only list exceptions — unlisted sessions use the defaults above.
#
# Silence a noisy session:
# [notifications.sessions.playground]
# enabled = false
#
# Full popup treatment for an important session:
# [notifications.sessions.production-backend]
# popup = true
# os_notify = true

# ── Appearance ─────────────────────────────────────────────────
[appearance]
# Theme name — cycle with Ctrl+t in the picker
# Available: tokyonight, tokyonight-storm, tokyonight-light, catppuccin-mocha,
#            catppuccin-latte, gruvbox-dark, gruvbox-light, nord, dracula, solarized-dark
theme = "tokyonight"
"""


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
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 10000}]}
        ],
        "Stop": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 10000}]}
        ],
        "Notification": [
            {
                "matcher": "idle_prompt|permission_prompt|elicitation_dialog",
                "hooks": [{"type": "command", "command": hook_command, "timeout": 10000}],
            }
        ],
        "PreToolUse": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 10000}]}
        ],
        "SessionStart": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 10000}]}
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 10000}]}
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
        config_path.write_text(_DEFAULT_CONFIG)
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
