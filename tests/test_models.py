from nagare.models import AgentType, Session, SessionStatus


def test_session_creation():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        window_index=0,
        pane_index=0,
        status=SessionStatus.IDLE,
    )
    assert session.name == "my-project"
    assert session.session_id == "$1"
    assert session.path == "/home/user/projects/my-project"
    assert session.window_index == 0
    assert session.pane_index == 0
    assert session.status == SessionStatus.IDLE


def test_session_display_name():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        window_index=0,
        pane_index=0,
        status=SessionStatus.IDLE,
    )
    assert session.display == "[#00D26A]●[/] my-project"


def test_session_status_icons():
    idle = Session(name="a", session_id="$1", path="/tmp", window_index=0, pane_index=0, status=SessionStatus.IDLE)
    waiting = Session(name="b", session_id="$2", path="/tmp", window_index=0, pane_index=0, status=SessionStatus.WAITING_INPUT)
    running = Session(name="c", session_id="$3", path="/tmp", window_index=0, pane_index=0, status=SessionStatus.RUNNING)
    dead = Session(name="d", session_id="$4", path="/tmp", window_index=0, pane_index=0, status=SessionStatus.DEAD)

    assert idle.status_icon == "[#00D26A]●[/]"
    assert waiting.status_icon == "[#db4b4b]●[/]"
    assert running.status_icon == "[#e0af68]●[/]"
    assert dead.status_icon == "[#565f89]●[/]"


def test_agent_types():
    claude = Session(name="a", session_id="$1", path="/tmp", window_index=0, pane_index=0,
                     status=SessionStatus.IDLE, agent_type=AgentType.CLAUDE)
    opencode = Session(name="b", session_id="$2", path="/tmp", window_index=0, pane_index=0,
                       status=SessionStatus.IDLE, agent_type=AgentType.OPENCODE)
    assert claude.agent_icon == "[#da7756]C[/]"
    assert claude.agent_label == "Claude"
    assert opencode.agent_icon == "[#00e5ff]O[/]"
    assert opencode.agent_label == "OpenCode"


def test_default_agent_type():
    session = Session(name="a", session_id="$1", path="/tmp", window_index=0, pane_index=0,
                      status=SessionStatus.IDLE)
    assert session.agent_type == AgentType.CLAUDE
