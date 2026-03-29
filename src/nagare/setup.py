import json
import shutil
from pathlib import Path

from nagare.config import NagareConfig, load_config, CONFIG_PATH

DATA_DIR = Path.home() / ".local" / "share" / "nagare"
CLAUDE_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
CLAUDE_JSON_PATH = Path.home() / ".claude.json"
GEMINI_SETTINGS_PATH = Path.home() / ".gemini" / "settings.json"
OPENCODE_PLUGIN_DIR = Path.home() / ".config" / "opencode" / "plugin"
OPENCODE_PLUGIN_SRC = Path(__file__).resolve().parent / "opencode_plugin.ts"

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
popup_timeout = 8

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
popup_timeout = 8
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

# ── Picker ─────────────────────────────────────────────────────
[picker]
# Root directory for quick prototypes (Ctrl+p in picker)
# Just type a name and nagare creates the dir + tmux session + agent
quick_project_path = "~/Prototypes"

# ── Animation ──────────────────────────────────────────────────
[animation]
# Animation when jumping to a session from the picker
# Options: flash, pulse, fade, sweep, shrink, none
jump_animation = "flash"
# Duration in seconds for each animation type (tweak to taste)
flash_duration = 0.2
pulse_duration = 0.4
fade_duration = 0.25
sweep_duration = 0.2
shrink_duration = 0.3

# ── Appearance ─────────────────────────────────────────────────
[appearance]
# Theme name — cycle with Ctrl+t in the picker
# Available: tokyonight, tokyonight-storm, tokyonight-light, catppuccin-mocha,
#            catppuccin-latte, gruvbox-dark, gruvbox-light, nord, dracula, solarized-dark
theme = "tokyonight"
# Icon style: "emoji" (default, colorful) or "ascii" (maximum compatibility)
icon_style = "emoji"

# ── Sounds (CESP / openpeon) ─────────────────────────────────
[sounds]
# Master switch — set to true to enable sound effects
enabled = false
# Active sound pack (install with: nagare sounds install <pack>)
pack = "peon"
# Master volume (0.0 to 1.0)
volume = 0.7
# Per-category toggles
session_start = true
task_acknowledge = false  # fires on every prompt, can be noisy
task_complete = true
input_required = true
session_end = false

# Per-session sound pack overrides:
# [sounds.sessions.cosmiclab-backend]
# pack = "glados"

# ── Voice (TTS notifications) ────────────────────────────────
[voice]
# Master switch — set to true to enable spoken notifications
enabled = false
# TTS engine: auto, say (macOS), piper, edge-tts, espeak, wsl-sapi
engine = "auto"
# Engine-specific voice name (e.g. "en-US-GuyNeural" for edge-tts)
voice = ""
# Speech speed in words per minute
speed = 160
# Volume (0.0 to 1.0)
volume = 0.8
# Per-category toggles
session_start = false
task_acknowledge = false
task_complete = true
input_required = true
session_end = false

# Message templates — use {session} placeholder for the session name
[voice.templates]
session_start = "{session} is online"
task_complete = "{session} finished working"
input_required = "{session} needs your attention"
task_error = "{session} hit an error"

# Per-session voice overrides:
# [voice.sessions.cosmiclab-backend]
# engine = "edge-tts"
# voice = "en-GB-SoniaNeural"
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


def _install_hooks_to_file(
    settings_path: Path,
    nagare_hooks: dict,
    label: str,
    *,
    create_if_missing: bool = False,
) -> bool:
    """Install nagare hooks into an agent's settings.json file.

    Reads existing settings, removes stale nagare hooks, merges fresh ones, writes back.
    """
    if not settings_path.exists():
        if create_if_missing and settings_path.parent.exists():
            settings_path.write_text("{}")
        else:
            print(f"{label} settings not found at {settings_path}")
            return False

    try:
        settings = json.loads(settings_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to read {label} settings: {e}")
        return False

    hooks = settings.setdefault("hooks", {})

    for event, hook_groups in nagare_hooks.items():
        existing = hooks.get(event, [])
        cleaned = [
            group for group in existing
            if not any("nagare hook-state" in h.get("command", "") for h in group.get("hooks", []))
        ]
        cleaned.extend(hook_groups)
        hooks[event] = cleaned

    settings["hooks"] = hooks
    settings_path.write_text(json.dumps(settings, indent=2))
    return True


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

    return _install_hooks_to_file(CLAUDE_SETTINGS_PATH, nagare_hooks, "Claude Code")


def _install_gemini_hooks() -> bool:
    """Add nagare hooks to Gemini CLI settings.json."""
    nagare_bin = _get_nagare_bin()
    hook_command = f"{nagare_bin} hook-state"

    nagare_hooks = {
        "SessionStart": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
        "SessionEnd": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
        "BeforeAgent": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
        "AfterAgent": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
        "BeforeTool": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
        "Notification": [
            {"hooks": [{"type": "command", "command": hook_command, "timeout": 5000}]}
        ],
    }

    return _install_hooks_to_file(
        GEMINI_SETTINGS_PATH, nagare_hooks, "Gemini CLI", create_if_missing=True,
    )


def _install_mcp_server() -> bool:
    """Register the nagare MCP server in ~/.claude.json for inter-agent messaging."""
    if not CLAUDE_JSON_PATH.exists():
        print(f"Claude Code config not found at {CLAUDE_JSON_PATH}")
        return False

    try:
        data = json.loads(CLAUDE_JSON_PATH.read_text())
    except (json.JSONDecodeError, OSError) as e:
        print(f"Failed to read {CLAUDE_JSON_PATH}: {e}")
        return False

    nagare_project = str(Path(__file__).resolve().parents[2])
    uv_bin = shutil.which("uv") or "uv"

    mcp_servers = data.setdefault("mcpServers", {})
    mcp_servers["nagare"] = {
        "command": uv_bin,
        "args": ["run", "--project", nagare_project, "python", "-m", "nagare.mcp_server"],
    }

    CLAUDE_JSON_PATH.write_text(json.dumps(data, indent=2))
    return True


def _install_opencode_plugin() -> bool:
    """Copy the nagare plugin into OpenCode's plugin directory."""
    if not OPENCODE_PLUGIN_SRC.exists():
        print(f"OpenCode plugin source not found: {OPENCODE_PLUGIN_SRC}")
        return False

    OPENCODE_PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = OPENCODE_PLUGIN_DIR / "nagare.ts"
    shutil.copy2(OPENCODE_PLUGIN_SRC, dest)
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

    # Install Gemini CLI hooks
    print("\nInstalling Gemini CLI hooks...")
    if _install_gemini_hooks():
        print("Hooks installed in ~/.gemini/settings.json")
    else:
        print("Could not install Gemini hooks (Gemini CLI may not be installed).")

    # Install MCP server for inter-agent messaging
    print("\nInstalling nagare MCP server...")
    if _install_mcp_server():
        print("MCP server registered in ~/.claude.json")
    else:
        print("Could not install MCP server automatically.")

    # Install OpenCode plugin
    print("\nInstalling OpenCode plugin...")
    if _install_opencode_plugin():
        print(f"Plugin installed: {OPENCODE_PLUGIN_DIR / 'nagare.ts'}")
    else:
        print("Could not install OpenCode plugin.")

    print("\nAdd these lines to your ~/.tmux.conf:\n")
    print(generate_tmux_config())
    print("Then reload tmux config: tmux source-file ~/.tmux.conf")
