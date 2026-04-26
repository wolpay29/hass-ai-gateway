import re
from pathlib import Path

import yaml

_config = None


def _load():
    global _config
    path = Path(__file__).parent.parent / "menus.yaml"
    with open(path, encoding="utf-8") as f:
        _config = yaml.safe_load(f)


def _cfg() -> dict:
    if _config is None:
        _load()
    return _config


def get_main_menu_layout() -> list[list[str]]:
    return _cfg()["main_menu"]["layout"]


def get_menu(label: str) -> dict | None:
    return _cfg()["menus"].get(label)


def get_all_menus() -> dict:
    return _cfg()["menus"]


def get_all_action_buttons() -> dict[str, dict]:
    """Returns {callback_data: button_config} for every inline action button."""
    actions: dict[str, dict] = {}
    for menu in _cfg()["menus"].values():
        for row in menu.get("rows", []):
            for btn in row:
                if "callback_data" in btn:
                    actions[btn["callback_data"]] = btn
    for row in _cfg().get("battery_notification_menu", {}).get("rows", []):
        for btn in row:
            if "callback_data" in btn:
                actions[btn["callback_data"]] = btn
    return actions



def get_battery_notification_rows() -> list[list[dict]]:
    return _cfg().get("battery_notification_menu", {}).get("rows", [])


def get_main_menu_label_pattern() -> str:
    labels = list(_cfg()["menus"].keys())
    return "^(" + "|".join(re.escape(l) for l in labels) + ")$"
