from unittest.mock import patch
from nagare.tmux.scanner import scan_sessions, _parse_sessions, _find_agent_panes, _parse_all_panes
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


def test_find_agent_panes_claude():
    pane_output = "0:0:zsh\n0:1:claude\n0:2:zsh"
    assert _find_agent_panes(pane_output) == [(0, 1, AgentType.CLAUDE)]


def test_find_agent_panes_opencode():
    pane_output = "0:0:zsh\n0:1:opencode"
    assert _find_agent_panes(pane_output) == [(0, 1, AgentType.OPENCODE)]


def test_find_agent_panes_in_second_window():
    pane_output = "0:0:zsh\n1:0:zsh\n1:1:claude"
    assert _find_agent_panes(pane_output) == [(1, 1, AgentType.CLAUDE)]


def test_find_agent_panes_not_found():
    pane_output = "0:0:zsh\n0:1:vim"
    assert _find_agent_panes(pane_output) == []


def test_find_agent_panes_multiple():
    pane_output = "0:0:claude\n1:0:opencode\n2:0:zsh"
    results = _find_agent_panes(pane_output)
    assert len(results) == 2
    assert (0, 0, AgentType.CLAUDE) in results
    assert (1, 0, AgentType.OPENCODE) in results


def test_parse_all_panes_empty():
    assert _parse_all_panes("") == {}


def test_parse_all_panes_filters_agents():
    raw = "proj-a:0:0:claude\nproj-a:0:1:zsh\nproj-b:0:0:opencode"
    result = _parse_all_panes(raw)
    assert result == {
        "proj-a": [(0, 0, AgentType.CLAUDE)],
        "proj-b": [(0, 0, AgentType.OPENCODE)],
    }


def test_parse_all_panes_multiple_agents_same_session():
    raw = "proj:0:0:claude\nproj:1:0:opencode"
    result = _parse_all_panes(raw)
    assert result == {
        "proj": [(0, 0, AgentType.CLAUDE), (1, 0, AgentType.OPENCODE)],
    }


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions_claude(mock_run):
    mock_run.side_effect = [
        # list-sessions
        "proj-a:$1:/home/user/a\nproj-b:$2:/home/user/b",
        # list-panes -a (single call for all sessions)
        "proj-a:0:0:claude\nproj-b:0:0:zsh",
        # capture-pane for proj-a (no hook state, needs fallback)
        "Do you want to proceed?\n ❯ 1. Yes\n   2. No\n\n Esc to cancel",
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
        # list-panes -a
        "oc-proj:0:0:opencode",
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
        # list-panes -a (single call)
        "claude-proj:0:0:claude\noc-proj:0:0:opencode",
        # capture-pane for claude-proj
        "❯\n",
        # capture-pane for oc-proj
        "some output\n",
    ]
    sessions = scan_sessions()
    assert len(sessions) == 2
    agents = {s.agent_type for s in sessions}
    assert agents == {AgentType.CLAUDE, AgentType.OPENCODE}


@patch("nagare.tmux.scanner.run_tmux")
def test_scan_sessions_with_hook_state_skips_capture(mock_run):
    """When hook state exists, capture-pane should be skipped."""
    mock_run.side_effect = [
        # list-sessions
        "proj-a:$1:/home/user/a",
        # list-panes -a
        "proj-a:0:0:claude",
        # No capture-pane call expected — hook state covers it
    ]
    with patch("nagare.tmux.scanner.load_all_states") as mock_states:
        from nagare.state import SessionState
        mock_states.return_value = {
            "/home/user/a": SessionState(
                state="working",
                session_id="abc",
                cwd="/home/user/a",
                event="UserPromptSubmit",
                notification_type="",
                last_message="doing stuff",
                timestamp="2026-01-01T00:00:00",
            ),
        }
        sessions = scan_sessions()
        assert len(sessions) == 1
        assert sessions[0].status == SessionStatus.RUNNING
        assert sessions[0].last_message == "doing stuff"
        # Only list-sessions + list-panes -a, no capture-pane
        assert mock_run.call_count == 2
