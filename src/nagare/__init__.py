import os
import sys


def main() -> None:
    if not os.environ.get("COLORTERM"):
        os.environ["COLORTERM"] = "truecolor"

    args = sys.argv[1:]
    command = args[0] if args else "pick"

    if command == "pick":
        attach_target = None
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
            elif isinstance(result, str) and result.startswith("attach:"):
                attach_target = result.removeprefix("attach:")
                break
            else:
                break
        # Outside tmux: attach after app has fully exited
        if attach_target:
            import subprocess
            subprocess.run(["tmux", "attach-session", "-t", attach_target])
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
                from nagare.tmux import switch_to_session
                switch_to_session(name)
                print(f"Created session: {name}")
            except (ValueError, RuntimeError) as e:
                print(f"Error: {e}")
                sys.exit(1)
        else:
            # Interactive form
            from nagare.new_session import NewSessionApp
            app = NewSessionApp()
            app.run()
    elif command == "popup-watcher":
        from nagare.notifications.deliver import run_popup_watcher
        run_popup_watcher()
    elif command == "popup-dispatch":
        # Legacy — kept for compatibility but no longer used
        pass
    elif command == "sounds":
        _handle_sounds(args[1:])
    elif command == "setup":
        from nagare.setup import run_setup
        run_setup()
    else:
        print(f"Unknown command: {command}")
        print("Usage: nagare [pick|notifs|new|sounds|popup-notif|setup|hook-state]")
        sys.exit(1)


def _handle_sounds(args: list[str]) -> None:
    """Handle nagare sounds subcommands."""
    sub = args[0] if args else "list"

    if sub == "list":
        from nagare.sounds import get_engine
        engine = get_engine()
        packs = engine.list_installed_packs()
        if not packs:
            print("No sound packs installed.")
            print("Install one: nagare sounds install peon")
            return
        print("Installed sound packs:\n")
        for p in packs:
            cats = ", ".join(p["categories"])
            print(f"  {p['display_name']} ({p['name']})")
            print(f"    {p['sound_count']} sounds — {cats}")
            print()

    elif sub == "install":
        if len(args) < 2:
            print("Usage: nagare sounds install <pack-name>")
            return
        pack_name = args[1]
        _install_sound_pack(pack_name)

    elif sub == "test":
        from nagare.sounds import get_engine, CATEGORIES
        from nagare.config import load_config
        import time
        config = load_config()
        pack_name = args[1] if len(args) > 1 else config.sounds.pack
        engine = get_engine()
        engine.volume = config.sounds.volume
        pack = engine.load_pack(pack_name)
        if not pack:
            print(f"Pack '{pack_name}' not found. Run: nagare sounds list")
            return
        print(f"Testing pack: {pack.display_name}\n")
        for cat in CATEGORIES:
            sounds = pack.categories.get(cat)
            if not sounds:
                alias = pack.aliases.get(cat)
                if alias:
                    sounds = pack.categories.get(alias)
            if sounds:
                engine.play(pack_name, cat)
                labels = [s.get("label", "?") for s in sounds]
                print(f"  {cat}: {', '.join(labels)}")
                time.sleep(1.5)
            else:
                print(f"  {cat}: (no sounds)")
        print("\nDone.")

    else:
        print(f"Unknown sounds command: {sub}")
        print("Usage: nagare sounds [list|install <pack>|test [pack]]")


def _install_sound_pack(pack_name: str) -> None:
    """Download and install a sound pack from the openpeon registry."""
    import json
    import subprocess
    import tempfile
    from nagare.sounds import PACKS_DIR

    print(f"Fetching registry...")
    try:
        result = subprocess.run(
            ["curl", "-fsSL", "https://peonping.github.io/registry/index.json"],
            capture_output=True, text=True, timeout=15,
        )
        registry = json.loads(result.stdout)
    except Exception as e:
        print(f"Failed to fetch registry: {e}")
        return

    # Registry is {"packs": [...]}
    packs = registry.get("packs", registry) if isinstance(registry, dict) else registry

    # Find the pack
    pack_entry = None
    for entry in packs:
        if entry.get("name") == pack_name:
            pack_entry = entry
            break

    if not pack_entry:
        print(f"Pack '{pack_name}' not found in registry.")
        print("Available packs:")
        for entry in packs[:20]:
            print(f"  {entry['name']} — {entry.get('display_name', '')}")
        if len(packs) > 20:
            print(f"  ...and {len(packs) - 20} more")
        return

    repo = pack_entry["source_repo"]
    ref = pack_entry["source_ref"]
    src_path = pack_entry["source_path"]
    size = pack_entry.get("total_size_bytes", 0)
    size_mb = size / 1024 / 1024 if size else 0

    print(f"Installing {pack_entry.get('display_name', pack_name)}")
    print(f"  Source: {repo}@{ref}/{src_path}")
    if size_mb:
        print(f"  Size: {size_mb:.1f} MB")

    PACKS_DIR.mkdir(parents=True, exist_ok=True)
    dest = PACKS_DIR / pack_name

    with tempfile.TemporaryDirectory() as tmpdir:
        url = f"https://github.com/{repo}/archive/refs/tags/{ref}.tar.gz"
        try:
            subprocess.run(
                ["curl", "-fsSL", url, "-o", f"{tmpdir}/pack.tar.gz"],
                check=True, timeout=30,
            )
            subprocess.run(
                ["tar", "xzf", f"{tmpdir}/pack.tar.gz", "-C", tmpdir],
                check=True, timeout=15,
            )
        except subprocess.CalledProcessError as e:
            print(f"Download failed: {e}")
            return

        # Find the extracted directory
        import glob
        extracted = glob.glob(f"{tmpdir}/*/")
        if not extracted:
            print("Failed to extract pack.")
            return

        src = os.path.join(extracted[0], src_path)
        if not os.path.exists(src):
            print(f"Pack path '{src_path}' not found in archive.")
            return

        # Copy to packs dir
        import shutil
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)

    if (dest / "openpeon.json").exists():
        print(f"\nInstalled to {dest}")
        print(f"Enable in config: [sounds] enabled = true, pack = \"{pack_name}\"")
    else:
        print("Warning: openpeon.json not found in pack.")
