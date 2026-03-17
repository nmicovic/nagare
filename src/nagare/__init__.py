import os
import sys


def main() -> None:
    if not os.environ.get("COLORTERM"):
        os.environ["COLORTERM"] = "truecolor"

    args = sys.argv[1:]
    command = args[0] if args else "pick"

    if command == "pick":
        while True:
            from nagare.pick import PickerApp
            app = PickerApp()
            result = app.run()
            if result == "new_session":
                from nagare.new_session import NewSessionApp
                form_result = NewSessionApp().run()
                if form_result == "back_to_picker":
                    continue
                break
            elif result == "quick_prototype":
                from nagare.quick_prototype import QuickPrototypeApp
                form_result = QuickPrototypeApp().run()
                if form_result == "back_to_picker":
                    continue
                break
            else:
                break
    elif command == "notifs":
        from nagare.notifs import NotifsApp
        app = NotifsApp()
        app.run()
    elif command == "hook-state":
        from nagare.hooks import handle_hook
        handle_hook()
    elif command == "popup-notif":
        from nagare.popup_notif import run_popup
        run_popup(args[1:])
    elif command == "new":
        from nagare.session import create_session
        import argparse
        parser = argparse.ArgumentParser(prog="nagare new")
        parser.add_argument("path", nargs="?", default=None)
        parser.add_argument("--agent", "-a", default="claude", choices=["claude", "opencode"])
        parser.add_argument("--name", "-n", default=None)
        parser.add_argument("--continue", "-c", dest="continue_session", action="store_true", default=True)
        parser.add_argument("--no-continue", dest="continue_session", action="store_false")
        parsed = parser.parse_args(args[1:])

        if parsed.path:
            # Direct creation
            try:
                name = create_session(
                    path=parsed.path,
                    name=parsed.name,
                    agent=parsed.agent,
                    continue_session=parsed.continue_session,
                )
                from nagare.tmux import run_tmux
                run_tmux("switch-client", "-t", name)
                print(f"Created session: {name}")
            except (ValueError, RuntimeError) as e:
                print(f"Error: {e}")
                sys.exit(1)
        else:
            # Interactive form
            from nagare.new_session import NewSessionApp
            app = NewSessionApp()
            app.run()
    elif command == "popup-dispatch":
        # Legacy — kept for compatibility but no longer used
        pass
    elif command == "setup":
        from nagare.setup import run_setup
        run_setup()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nagare [pick|notifs|new|popup-notif|setup|hook-state]")
        sys.exit(1)
