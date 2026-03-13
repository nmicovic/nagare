from unittest.mock import patch
from nagare.notifs import NotifsApp
from nagare.notifications.store import NotificationStore


def _make_store(tmp_path, items=None):
    store = NotificationStore(tmp_path / "notifs.json")
    if items:
        for session_name, message in items:
            store.add(session_name, message)
    return store


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_shows_list(tmp_path):
    store = _make_store(tmp_path, [("cosmo-ai", "Waiting for input"), ("proj-b", "Waiting for input")])
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import OptionList
        option_list = app.query_one(OptionList)
        assert option_list.option_count == 2


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_dismiss_all(tmp_path):
    store = _make_store(tmp_path, [("a", "msg1"), ("b", "msg2")])
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("D")
        await pilot.pause()
        assert store.list_all() == []


@patch("nagare.notifs.STORE_PATH", None)
async def test_notifs_escape_exits(tmp_path):
    store = _make_store(tmp_path)
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.press("escape")
        await pilot.pause()
