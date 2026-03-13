from textual.app import App, ComposeResult
from nagare.widgets.footer_bar import FooterBar


class FooterApp(App):
    def compose(self) -> ComposeResult:
        yield FooterBar()


async def test_footer_renders():
    app = FooterApp()
    async with app.run_test() as pilot:
        footer = app.query_one(FooterBar)
        assert footer is not None
