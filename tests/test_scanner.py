from unittest.mock import patch
from nagare.tmux.scanner import scan_sessions, _parse_sessions, _find_agent_pane
from nagare.models import AgentType, Session, SessionStatus


def test_parse_sessions():
    raw = "my-project:$1:/home/user/projects/my-project\nother:$2:/home/user/other"
    result = _parse_sessions(raw)
    assert result == [
        ("my-project", "$1", "/home/user/projects/my-project"),
        ("other", "$2", "/home/user/other"),
    ]


def test_parse_sessions_empty():
    assert _parse_sessions("") == []


def test_find_agent_pane_claude():
    pane_output = "0:0:zsh\n0:1:claude\n0:2:zsh"
    assert _find_agent_pane(pane_output) == (0, 1, AgentType.CLAUDE)


def test_find_agent_pane_opencode():
    pane_output = "0:0:zsh\n0:1:opencode"
    assert _find_agent_pane(pane_output) == (0, 1, AgentType.OPENCODE)


def test_find_agent_pane_in_second_window():
    pane_output = "0:0:zsh\n1:0:zsh\n1:1:claude"
    assert _find_agent_pane(pane_output) == (1, 1, AgentType.CLAUDE)


def test_find_agent_pane_not_found():
    pane_output = "0:0:zsh\n0:1:vim"
    assert _find_agent_pane(pane_output) is None


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions_claude(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "proj-a:$1:/home/user/a\nproj-b:$2:/home/user/b",
        # list-panes -s for proj-a — has claude
        "0:0:claude",
        # capture-pane for proj-a
        "Do you want to proceed?\n ❯ 1. Yes\n   2. No\n\n Esc to cancel",
        # list-panes -s for proj-b — no agent
        "0:0:zsh",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 1
    assert sessions[0].agent_type == AgentType.CLAUDE
    assert sessions[0].status == SessionStatus.WAITING_INPUT


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions_opencode(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "oc-proj:$1:/home/user/oc",
        # list-panes -s — has opencode
        "0:0:opencode",
        # capture-pane
        "some opencode output\n",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 1
    assert sessions[0].agent_type == AgentType.OPENCODE


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions_mixed(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "claude-proj:$1:/home/user/a\noc-proj:$2:/home/user/b",
        # list-panes for claude-proj
        "0:0:claude",
        # capture-pane for claude-proj
        "❯\n",
        # list-panes for oc-proj
        "0:0:opencode",
        # capture-pane for oc-proj
        "some output\n",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 2
    agents = {s.agent_type for s in sessions}
    assert agents == {AgentType.CLAUDE, AgentType.OPENCODE}
