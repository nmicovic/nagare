import os

from nagare.app import NagareApp


def main() -> None:
    # Ensure Textual uses true color (24-bit) rendering.
    # Inside tmux on WSL, COLORTERM is often unset even though
    # Windows Terminal fully supports true color.
    if not os.environ.get("COLORTERM"):
        os.environ["COLORTERM"] = "truecolor"

    app = NagareApp()
    app.run()
