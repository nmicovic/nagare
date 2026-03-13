import re

_SPECIAL_KEYS: dict[str, str] = {
    "enter": "Enter",
    "tab": "Tab",
    "shift+tab": "BTab",
    "backspace": "BSpace",
    "escape": "Escape",
    "space": "Space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "PPage",
    "pagedown": "NPage",
    "delete": "DC",
}

_CTRL_RE = re.compile(r"^ctrl\+([a-z])$")

INTERCEPTED_KEYS = frozenset({
    "ctrl+right_square_bracket",
})


def textual_to_tmux(key: str, character: str | None) -> tuple[str, ...] | None:
    if key in INTERCEPTED_KEYS:
        return None
    if key in _SPECIAL_KEYS:
        return ("send-keys", _SPECIAL_KEYS[key])
    ctrl_match = _CTRL_RE.match(key)
    if ctrl_match:
        letter = ctrl_match.group(1)
        return ("send-keys", f"C-{letter}")
    if character and len(character) == 1:
        return ("send-keys", "-l", character)
    return None
