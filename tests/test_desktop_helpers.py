# -*- coding: utf-8 -*-
"""Тесты helper-функций desktop-control: VK-коды и выбор окна. Без реального ввода."""
import importlib.util
from pathlib import Path

import pytest


def load_desktop():
    path = (Path(__file__).resolve().parents[1] / "skills" / "custom"
            / "desktop-control" / "skill.py")
    spec = importlib.util.spec_from_file_location("desktop_skill_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def desk():
    return load_desktop()


def test_vk_mapping(desk):
    assert desk._vk_for("ctrl") == 0x11
    assert desk._vk_for("CTRL") == 0x11
    assert desk._vk_for("enter") == 0x0D
    assert desk._vk_for("f5") == 0x74
    assert desk._vk_for("a") == 0x41
    assert desk._vk_for("5") == 0x35
    assert desk._vk_for("unknown-key") == 0
    assert desk._vk_for("") == 0


def test_send_hotkey_order_and_release(desk, monkeypatch):
    events = []
    monkeypatch.setattr(desk, "_key_event",
                        lambda vk, up=False: events.append((vk, up)))
    assert desk._send_hotkey(["ctrl", "s"]) is True
    assert events == [(0x11, False), (ord("S"), False),
                      (ord("S"), True), (0x11, True)]


def test_send_hotkey_all_invalid(desk, monkeypatch):
    monkeypatch.setattr(desk, "_key_event", lambda vk, up=False: None)
    assert desk._send_hotkey(["nope1", "nope2"]) is False


class FakeWin:
    def __init__(self, title, visible=True):
        self.title = title
        self.visible = visible
        self.width = 100
        self.height = 100
        self.left = 0
        self.top = 0


class FakeGw:
    def __init__(self, wins):
        self._wins = wins

    def getAllWindows(self):
        return self._wins


def test_find_window_case_insensitive_and_shortest(desk):
    gw = FakeGw([
        FakeWin("Visual Studio Code — очень длинный заголовок проекта"),
        FakeWin("Visual Studio Code"),
        FakeWin("Блокнот"),
    ])
    w = desk._find("visual studio", gw)
    assert w is not None and w.title == "Visual Studio Code"


def test_find_window_no_match(desk):
    gw = FakeGw([FakeWin("Блокнот")])
    assert desk._find("хром", gw) is None
    assert desk._find("", gw) is None
