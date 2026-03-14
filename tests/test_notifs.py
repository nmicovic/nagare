from unittest.mock import patch
from textual.widgets import ListView
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
        lv = app.query_one("#notif-list", ListView)
        assert len(lv.children) == 2


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


@patch("nagare.notifs.STORE_PATH", None)
async def test_settings_tab_renders(tmp_path):
    store = _make_store(tmp_path)
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import TabbedContent, Switch
        tabs = app.query_one(TabbedContent)
        assert tabs is not None
        # Settings tab should have Switch widgets
        switches = app.query(Switch)
        assert len(switches) > 0


@patch("nagare.notifs.STORE_PATH", None)
@patch("nagare.notifs.save_notification_config")
async def test_settings_toggle_saves(mock_save, tmp_path):
    store = _make_store(tmp_path)
    app = NotifsApp(store=store)
    async with app.run_test() as pilot:
        await pilot.pause()
        from textual.widgets import Switch
        # Find the master enabled switch and toggle it
        switch = app.query_one("#cfg-enabled", Switch)
        switch.value = False
        await pilot.pause()
        # save_notification_config should have been called
        mock_save.assert_called()
        # The saved config should have enabled=False
        saved_config = mock_save.call_args[0][0]
        assert saved_config.enabled is False
