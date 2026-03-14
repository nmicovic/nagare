import os
from dataclasses import replace
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Input, ListView, ListItem, Static, Switch, TabbedContent, TabPane,
)

from nagare.config import (
    NotificationConfig, NotificationEventConfig,
    load_config, save_notification_config,
)
from nagare.notifications.store import NotificationStore
from nagare.themes import THEMES
from nagare.tmux import run_tmux

STORE_PATH = Path.home() / ".local" / "share" / "nagare" / "notifications.json"

# Ordered list of setting definitions: (widget_id, label, section_header_or_None)
_SETTINGS = [
    ("section", "Master", None),
    ("cfg-enabled", "Notifications enabled", "bool"),
    ("section", "Needs Input  [dim]— when Claude needs your action[/dim]", None),
    ("cfg-ni-toast", "Toast", "bool"),
    ("cfg-ni-bell", "Bell", "bool"),
    ("cfg-ni-os-notify", "OS Notify", "bool"),
    ("cfg-ni-popup", "Popup", "bool"),
    ("cfg-ni-popup-timeout", "Popup timeout (seconds)", "int"),
    ("section", "Task Complete  [dim]— when Claude finishes a long task[/dim]", None),
    ("cfg-tc-toast", "Toast", "bool"),
    ("cfg-tc-bell", "Bell", "bool"),
    ("cfg-tc-os-notify", "OS Notify", "bool"),
    ("cfg-tc-popup", "Popup", "bool"),
    ("cfg-tc-popup-timeout", "Popup timeout (seconds)", "int"),
    ("cfg-tc-min-working", "Min working seconds", "int"),
]


def _format_notification(notif) -> tuple[str, str]:
    dot = "●" if not notif.read else " "
    icon = "✅" if "finished" in notif.message.lower() else "⏳"
    line1 = f"{dot} {icon} [b]{notif.session_name}[/b]  {notif.message}"
    ts = notif.timestamp[:19].replace("T", " ")
    line2 = f"   [dim]{ts}[/dim]"
    return line1, line2


def _get_setting_value(nc: NotificationConfig, widget_id: str) -> bool | int:
    """Get the current value for a setting by widget ID."""
    _map = {
        "cfg-enabled": nc.enabled,
        "cfg-ni-toast": nc.needs_input.toast,
        "cfg-ni-bell": nc.needs_input.bell,
        "cfg-ni-os-notify": nc.needs_input.os_notify,
        "cfg-ni-popup": nc.needs_input.popup,
        "cfg-ni-popup-timeout": nc.needs_input.popup_timeout,
        "cfg-tc-toast": nc.task_complete.toast,
        "cfg-tc-bell": nc.task_complete.bell,
        "cfg-tc-os-notify": nc.task_complete.os_notify,
        "cfg-tc-popup": nc.task_complete.popup,
        "cfg-tc-popup-timeout": nc.task_complete.popup_timeout,
        "cfg-tc-min-working": nc.task_complete.min_working_seconds,
    }
    return _map[widget_id]


def _make_setting_item(widget_id: str, label: str, kind: str, value: bool | int) -> ListItem:
    """Create a ListItem with label on left and switch/input on right."""
    if kind == "bool":
        control = Switch(value=value, id=widget_id)
    else:
        control = Input(str(value), id=widget_id, classes="setting-input")
    return ListItem(
        Horizontal(
            Static(f"  {label}", classes="setting-label"),
            control,
            classes="setting-row",
        ),
    )


def _make_section_header(label: str) -> ListItem:
    """Create a non-interactive section header ListItem."""
    return ListItem(
        Static(f"  [b]{label}[/b]", classes="section-header"),
        disabled=True,
    )


class NotifsApp(App):
    CSS_PATH = "notifs.tcss"
    TITLE = "nagare notifications"

    BINDINGS = [
        Binding("escape", "quit", "Close", show=False),
        Binding("d", "dismiss", "Dismiss", show=False),
        Binding("D", "dismiss_all", "Dismiss All", show=False),
        Binding("1", "show_tab('tab-notifs')", "Notifications", show=False),
        Binding("2", "show_tab('tab-settings')", "Settings", show=False),
    ]

    def __init__(self, store: NotificationStore | None = None) -> None:
        super().__init__()
        self._store = store or NotificationStore(STORE_PATH)
        self._config = load_config()
        self._notif_config = self._config.notifications
        # Track which setting IDs are interactive (not section headers)
        self._setting_ids: list[str] = [
            s[0] for s in _SETTINGS if s[0] != "section"
        ]

    def compose(self) -> ComposeResult:
        nc = self._notif_config

        with TabbedContent(id="tabs"):
            with TabPane("Notifications", id="tab-notifs"):
                yield ListView(id="notif-list")
            with TabPane("Settings", id="tab-settings"):
                yield ListView(id="settings-list")

        yield Static(
            "[b]1[/b] Notifications  [b]2[/b] Settings  │  "
            "[b]Enter[/b] Jump/Toggle  [b]d[/b] Dismiss  [b]D[/b] Dismiss all  [b]Esc[/b] Close",
            id="hint-bar",
        )

    def on_mount(self) -> None:
        config = self._config
        for t in THEMES.values():
            self.register_theme(t)
        self.theme = config.theme if config.theme in THEMES else "tokyonight"

        if not os.environ.get("COLORTERM"):
            os.environ["COLORTERM"] = "truecolor"

        self._rebuild_list()
        self._rebuild_settings()
        # Focus the notification list so arrow keys work immediately
        self.query_one("#notif-list", ListView).focus()

    def _rebuild_list(self) -> None:
        notifs = self._store.list_all()
        lv = self.query_one("#notif-list", ListView)
        lv.clear()
        for notif in notifs:
            line1, line2 = _format_notification(notif)
            item = ListItem(
                Vertical(Static(line1), Static(line2)),
                classes="notif-item",
            )
            lv.append(item)
        if not notifs:
            lv.append(
                ListItem(
                    Vertical(Static("[dim]No notifications[/dim]")),
                    classes="notif-item",
                )
            )

    def _rebuild_settings(self) -> None:
        nc = self._notif_config
        lv = self.query_one("#settings-list", ListView)
        lv.clear()
        for widget_id, label, kind in _SETTINGS:
            if widget_id == "section":
                lv.append(_make_section_header(label))
            else:
                value = _get_setting_value(nc, widget_id)
                lv.append(_make_setting_item(widget_id, label, kind, value))
        # Footer
        lv.append(ListItem(
            Static("  [dim]Changes saved automatically to ~/.config/nagare/config.toml[/dim]"),
            disabled=True,
        ))

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one("#tabs", TabbedContent).active = tab_id
        # Focus the ListView in the target tab so arrows work immediately
        if tab_id == "tab-notifs":
            self.call_after_refresh(self.query_one("#notif-list", ListView).focus)
        elif tab_id == "tab-settings":
            self.call_after_refresh(self.query_one("#settings-list", ListView).focus)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        lv = event.list_view
        if lv.id == "notif-list":
            self._handle_notif_select(lv)
        elif lv.id == "settings-list":
            self._handle_setting_toggle(lv)

    def _handle_notif_select(self, lv: ListView) -> None:
        notifs = self._store.list_all()
        idx = lv.index
        if idx is not None and 0 <= idx < len(notifs):
            notif = notifs[idx]
            self._store.mark_read(notif.id)
            run_tmux("switch-client", "-t", notif.session_name)
            self.exit()

    def _handle_setting_toggle(self, lv: ListView) -> None:
        """Toggle a boolean setting on Enter, or focus the input for numeric."""
        idx = lv.index
        if idx is None:
            return
        item = lv.children[idx]
        # Try to find a Switch in this item
        switches = item.query(Switch)
        if switches:
            switch = switches.first()
            switch.value = not switch.value
            return
        # For Input items, focus the input
        inputs = item.query(Input)
        if inputs:
            inputs.first().focus()

    def action_dismiss(self) -> None:
        lv = self.query_one("#notif-list", ListView)
        idx = lv.index
        notifs = self._store.list_all()
        if idx is not None and 0 <= idx < len(notifs):
            self._store.dismiss(notifs[idx].id)
            self._rebuild_list()

    def action_dismiss_all(self) -> None:
        self._store.dismiss_all()
        self._rebuild_list()

    # ── Settings handlers ──

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle any toggle switch change — update config and save."""
        self._apply_setting(event.switch.id, event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle numeric input changes — validate and save."""
        widget_id = event.input.id
        if widget_id and widget_id.startswith("cfg-"):
            try:
                value = int(event.value)
                if value >= 0:
                    self._apply_setting(widget_id, value)
            except ValueError:
                pass

    def _apply_setting(self, widget_id: str | None, value: bool | int) -> None:
        """Map a widget ID to the config field and save."""
        if not widget_id:
            return

        nc = self._notif_config

        if widget_id == "cfg-enabled":
            self._notif_config = replace(nc, enabled=value)
        elif widget_id == "cfg-ni-toast":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, toast=value))
        elif widget_id == "cfg-ni-bell":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, bell=value))
        elif widget_id == "cfg-ni-os-notify":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, os_notify=value))
        elif widget_id == "cfg-ni-popup":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, popup=value))
        elif widget_id == "cfg-ni-popup-timeout":
            self._notif_config = replace(nc, needs_input=replace(nc.needs_input, popup_timeout=value))
        elif widget_id == "cfg-tc-toast":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, toast=value))
        elif widget_id == "cfg-tc-bell":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, bell=value))
        elif widget_id == "cfg-tc-os-notify":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, os_notify=value))
        elif widget_id == "cfg-tc-popup":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, popup=value))
        elif widget_id == "cfg-tc-popup-timeout":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, popup_timeout=value))
        elif widget_id == "cfg-tc-min-working":
            self._notif_config = replace(nc, task_complete=replace(nc.task_complete, min_working_seconds=value))
        else:
            return

        save_notification_config(self._notif_config)
