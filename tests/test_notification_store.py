import json
from nagare.notifications.store import NotificationStore, Notification


def test_add_and_list(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    store.add("proj-b", "Waiting for input")

    notifs = store.list_all()
    assert len(notifs) == 2
    assert notifs[0].session_name == "proj-b"  # newest first
    assert notifs[1].session_name == "cosmo-ai"
    assert notifs[0].read is False


def test_mark_read(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    notifs = store.list_all()
    store.mark_read(notifs[0].id)

    notifs = store.list_all()
    assert notifs[0].read is True


def test_dismiss_one(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "Waiting for input")
    store.add("proj-b", "Waiting for input")
    notifs = store.list_all()
    store.dismiss(notifs[0].id)

    notifs = store.list_all()
    assert len(notifs) == 1
    assert notifs[0].session_name == "cosmo-ai"


def test_dismiss_all(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("cosmo-ai", "msg1")
    store.add("proj-b", "msg2")
    store.dismiss_all()

    assert store.list_all() == []


def test_persistence(tmp_path):
    path = tmp_path / "notifs.json"
    store1 = NotificationStore(path)
    store1.add("cosmo-ai", "Waiting for input")

    store2 = NotificationStore(path)
    notifs = store2.list_all()
    assert len(notifs) == 1
    assert notifs[0].session_name == "cosmo-ai"


def test_empty_store(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    assert store.list_all() == []


def test_unread_count(tmp_path):
    store = NotificationStore(tmp_path / "notifs.json")
    store.add("a", "msg")
    store.add("b", "msg")
    assert store.unread_count() == 2
    notifs = store.list_all()
    store.mark_read(notifs[0].id)
    assert store.unread_count() == 1
