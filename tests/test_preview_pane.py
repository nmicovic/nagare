from textual.app import App, ComposeResult
from nagare.widgets.preview_pane import PreviewPane


class PreviewApp(App):
    def compose(self) -> ComposeResult:
        yield PreviewPane()


async def test_preview_pane_update():
    app = PreviewApp()
    async with app.run_test() as pilot:
        pane = app.query_one(PreviewPane)
        pane.update_content("hello\nworld")
        await pilot.pause()
        assert pane is not None


async def test_preview_pane_empty():
    app = PreviewApp()
    async with app.run_test() as pilot:
        pane = app.query_one(PreviewPane)
        pane.update_content("")
        await pilot.pause()
        assert pane is not None
