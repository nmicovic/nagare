import os
import sys


def main() -> None:
    if not os.environ.get("COLORTERM"):
        os.environ["COLORTERM"] = "truecolor"

    args = sys.argv[1:]
    command = args[0] if args else "pick"

    if command == "pick":
        from nagare.pick import PickerApp
        app = PickerApp()
        app.run()
    elif command == "notifs":
        from nagare.notifs import NotifsApp
        app = NotifsApp()
        app.run()
    elif command == "hook-state":
        from nagare.hooks import handle_hook
        handle_hook()
    elif command == "setup":
        from nagare.setup import run_setup
        run_setup()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nagare [pick|notifs|setup|hook-state]")
        sys.exit(1)
