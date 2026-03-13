from textual.app import App, ComposeResult
from nagare.widgets.terminal_view import TerminalView


class TVApp(App):
    def compose(self) -> ComposeResult:
        yield TerminalView()


async def test_terminal_view_update():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.update_content("hello\nworld")
        await pilot.pause()
        assert tv is not None


async def test_terminal_view_empty():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.update_content("")
        await pilot.pause()
        assert tv is not None


async def test_terminal_view_active_border():
    app = TVApp()
    async with app.run_test() as pilot:
        tv = app.query_one(TerminalView)
        tv.set_active(True)
        await pilot.pause()
        assert tv.has_class("active-pane")
        tv.set_active(False)
        await pilot.pause()
        assert not tv.has_class("active-pane")
