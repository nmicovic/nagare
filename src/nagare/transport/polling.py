import threading
from collections.abc import Callable

from nagare.models import Session
from nagare.tmux import run_tmux
from nagare.transport.base import SessionTransport
from nagare.transport.keys import textual_to_tmux


class PollingTransport(SessionTransport):

    def __init__(self) -> None:
        self._streaming: bool = False
        self._stream_timer: threading.Timer | None = None

    def get_content(self, session: Session) -> str:
        return run_tmux("capture-pane", "-t", f"{session.name}:{session.pane_index}", "-p", "-e")

    def send_keys(self, session: Session, key: str, character: str | None) -> None:
        args = textual_to_tmux(key, character)
        if args is None:
            return
        target = f"{session.name}:{session.pane_index}"
        cmd = (args[0], "-t", target) + args[1:]
        run_tmux(*cmd)

    def start_streaming(self, session: Session, callback: Callable[[str], None]) -> None:
        self.stop_streaming()
        self._streaming = True

        def poll() -> None:
            if not self._streaming:
                return
            content = self.get_content(session)
            callback(content)
            if self._streaming:
                self._stream_timer = threading.Timer(0.05, poll)
                self._stream_timer.daemon = True
                self._stream_timer.start()

        self._stream_timer = threading.Timer(0, poll)
        self._stream_timer.daemon = True
        self._stream_timer.start()

    def stop_streaming(self) -> None:
        self._streaming = False
        if self._stream_timer is not None:
            self._stream_timer.cancel()
            self._stream_timer = None
