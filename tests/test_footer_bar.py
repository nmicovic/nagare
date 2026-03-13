from textual.app import App, ComposeResult
from nagare.widgets.footer_bar import FooterBar


class FooterApp(App):
    def compose(self) -> ComposeResult:
        yield FooterBar()


async def test_footer_browse_mode():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        footer.set_browse_mode()
        await pilot.pause()
        text = str(footer.render())
        assert "Ctrl+]" in text


async def test_footer_interactive_mode():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        footer.set_interactive_mode()
        await pilot.pause()
        text = str(footer.render())
        assert "Ctrl+]" in text
        assert "forwarded" in text.lower()
