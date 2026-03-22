"""Icon sets for nagare — emoji (default) and ASCII (compatible).

Usage:
    from nagare.icons import icons
    print(icons.folder, icons.timer)

Call `load_icons()` on app mount to refresh from config.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class IconSet:
    folder: str
    git_branch: str
    timer: str
    tokens: str
    window: str
    process: str
    pane_size: str
    load: str
    memory: str
    server: str
    message: str
    search: str


EMOJI = IconSet(
    folder="📁",
    git_branch="",
    timer="⏱",
    tokens="🪙",
    window="🪟",
    process="⚙",
    pane_size="📐",
    load="📊",
    memory="🧠",
    server="🖥",
    message="💬",
    search="🔍",
)

ASCII = IconSet(
    folder=">",
    git_branch="*",
    timer="@",
    tokens="$",
    window="#",
    process="*",
    pane_size="[]",
    load="~",
    memory="M",
    server="S",
    message=">",
    search="/",
)

icons: IconSet = EMOJI


def load_icons() -> IconSet:
    """Load the icon set from config and set as active."""
    global icons
    try:
        from nagare.config import load_config
        config = load_config()
        if config.icon_style == "ascii":
            icons = ASCII
        else:
            icons = EMOJI
    except Exception:
        icons = EMOJI
    return icons
