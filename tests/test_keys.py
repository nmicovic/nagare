from nagare.transport.keys import textual_to_tmux


def test_regular_char():
    assert textual_to_tmux("a", "a") == ("send-keys", "-l", "a")


def test_enter():
    assert textual_to_tmux("enter", None) == ("send-keys", "Enter")


def test_tab():
    assert textual_to_tmux("tab", None) == ("send-keys", "Tab")


def test_backspace():
    assert textual_to_tmux("backspace", None) == ("send-keys", "BSpace")


def test_escape():
    assert textual_to_tmux("escape", None) == ("send-keys", "Escape")


def test_space():
    assert textual_to_tmux("space", " ") == ("send-keys", "Space")


def test_arrow_up():
    assert textual_to_tmux("up", None) == ("send-keys", "Up")


def test_arrow_down():
    assert textual_to_tmux("down", None) == ("send-keys", "Down")


def test_arrow_left():
    assert textual_to_tmux("left", None) == ("send-keys", "Left")


def test_arrow_right():
    assert textual_to_tmux("right", None) == ("send-keys", "Right")


def test_ctrl_c():
    assert textual_to_tmux("ctrl+c", None) == ("send-keys", "C-c")


def test_ctrl_d():
    assert textual_to_tmux("ctrl+d", None) == ("send-keys", "C-d")


def test_ctrl_l():
    assert textual_to_tmux("ctrl+l", None) == ("send-keys", "C-l")


def test_home():
    assert textual_to_tmux("home", None) == ("send-keys", "Home")


def test_end():
    assert textual_to_tmux("end", None) == ("send-keys", "End")


def test_pageup():
    assert textual_to_tmux("pageup", None) == ("send-keys", "PPage")


def test_pagedown():
    assert textual_to_tmux("pagedown", None) == ("send-keys", "NPage")


def test_delete():
    assert textual_to_tmux("delete", None) == ("send-keys", "DC")


def test_shift_tab():
    assert textual_to_tmux("shift+tab", None) == ("send-keys", "BTab")


def test_unknown_key_returns_none():
    assert textual_to_tmux("ctrl+right_square_bracket", None) is None
