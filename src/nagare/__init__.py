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
    elif command == "daemon":
        from nagare.daemon import run_daemon
        run_daemon()
    elif command == "setup":
        from nagare.setup import run_setup
        run_setup()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nagare [pick|notifs|daemon|setup]")
        sys.exit(1)
