from nagare.models import Session, SessionStatus


def test_session_creation():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        pane_index=0,
        status=SessionStatus.ALIVE,
    )
    assert session.name == "my-project"
    assert session.session_id == "$1"
    assert session.path == "/home/user/projects/my-project"
    assert session.pane_index == 0
    assert session.status == SessionStatus.ALIVE


def test_session_display_name():
    session = Session(
        name="my-project",
        session_id="$1",
        path="/home/user/projects/my-project",
        pane_index=0,
        status=SessionStatus.ALIVE,
    )
    assert session.display == "● my-project"


def test_session_status_icons():
    alive = Session(name="a", session_id="$1", path="/tmp", pane_index=0, status=SessionStatus.ALIVE)
    dead = Session(name="b", session_id="$2", path="/tmp", pane_index=0, status=SessionStatus.DEAD)

    assert alive.status_icon == "●"
    assert dead.status_icon == "○"
