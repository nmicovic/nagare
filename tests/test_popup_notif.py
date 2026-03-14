from nagare.popup_notif import PopupNotifApp


async def test_popup_shows_needs_input():
    app = PopupNotifApp(
        session_name="prod",
        event_type="needs_input",
        message="Bash(git push)",
        popup_timeout=60,
    )
    async with app.run_test() as pilot:
        await pilot.pause()
        # Just verify it renders without crashing


async def test_popup_shows_task_complete():
    app = PopupNotifApp(
        session_name="nagare",
        event_type="task_complete",
        message="Done.",
        working_seconds=154,
        popup_timeout=60,
    )
    async with app.run_test() as pilot:
        await pilot.pause()


async def test_popup_escape_exits():
    app = PopupNotifApp(
        session_name="test",
        event_type="needs_input",
        message="test",
        popup_timeout=60,
    )
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
