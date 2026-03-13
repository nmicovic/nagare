from textual.widgets import Static

from nagare.models import Session


class SessionDetail(Static):

    DEFAULT_CSS = """
    SessionDetail {
        height: auto;
        padding: 1 1;
        border-top: solid $accent;
    }
    """

    def __init__(self) -> None:
        super().__init__("")

    def update_session(self, session: Session | None) -> None:
        if session is None:
            self.update("[dim]No session selected[/dim]")
            return

        lines = [
            f"[b]{session.name}[/b]",
            f"[dim]{session.path}[/dim]",
            "",
            f"Status   {session.status_icon} {session.status_label}",
        ]

        d = session.details
        if d.git_branch:
            lines.append(f"Branch   [cyan]{d.git_branch}[/cyan]")
        if d.model:
            lines.append(f"Model    {d.model}")
        if d.context_usage:
            lines.append(f"Context  {d.context_usage}")

        self.update("\n".join(lines))
