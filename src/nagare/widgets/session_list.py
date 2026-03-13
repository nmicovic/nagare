from textual.widgets import ListView, ListItem, Label
from textual.message import Message

from nagare.models import Session


class SessionList(ListView):

    class SessionHighlighted(Message):
        def __init__(self, session: Session) -> None:
            super().__init__()
            self.session = session

    def __init__(self) -> None:
        super().__init__()
        self._sessions: list[Session] = []

    @property
    def selected_session(self) -> Session | None:
        if self.index is not None and self._sessions:
            return self._sessions[self.index]
        return None

    def update_sessions(self, sessions: list[Session]) -> None:
        prev_name = self.selected_session.name if self.selected_session else None
        self._sessions = sessions
        self.clear()
        for session in sessions:
            self.append(ListItem(Label(f"{session.display}  [dim]{session.path}[/dim]")))
        if not sessions:
            return
        # Restore selection by name
        if prev_name:
            for i, s in enumerate(sessions):
                if s.name == prev_name:
                    self.index = i
                    return
        self.index = 0

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        session = self.selected_session
        if session:
            self.post_message(self.SessionHighlighted(session))
