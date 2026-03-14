from unittest.mock import patch
from nagare.tmux.scanner import scan_sessions, _parse_sessions, _find_claude_pane
from nagare.models import Session, SessionStatus


def test_parse_sessions():
    raw = "my-project:$1:/home/user/projects/my-project\nother:$2:/home/user/other"
    result = _parse_sessions(raw)
    assert result == [
        ("my-project", "$1", "/home/user/projects/my-project"),
        ("other", "$2", "/home/user/other"),
    ]


def test_parse_sessions_empty():
    assert _parse_sessions("") == []


def test_find_claude_pane_found():
    pane_output = "0:0:zsh\n0:1:claude\n0:2:zsh"
    assert _find_claude_pane(pane_output) == (0, 1)


def test_find_claude_pane_in_second_window():
    pane_output = "0:0:zsh\n1:0:zsh\n1:1:claude"
    assert _find_claude_pane(pane_output) == (1, 1)


def test_find_claude_pane_not_found():
    pane_output = "0:0:zsh\n0:1:vim"
    assert _find_claude_pane(pane_output) is None


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "proj-a:$1:/home/user/a\nproj-b:$2:/home/user/b",
        # list-panes -s for proj-a — has claude in window 0, pane 0
        "0:0:claude",
        # capture-pane for proj-a — shows a prompt (waiting for input)
        "Do you want to proceed?\n ❯ 1. Yes\n   2. No\n\n Esc to cancel",
        # list-panes -s for proj-b — no claude
        "0:0:zsh",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 1
    assert sessions[0] == Session(
        name="proj-a",
        session_id="$1",
        path="/home/user/a",
        window_index=0,
        pane_index=0,
        status=SessionStatus.WAITING_INPUT,
    )
