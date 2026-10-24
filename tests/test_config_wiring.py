# -*- coding: utf-8 -*-
"""Тесты связки config_manager ↔ модули: значение берётся из config.json и обновляется на лету."""
import importlib.util
import json
import os
import random
import unittest.mock as mock
from pathlib import Path

import pytest

import config_manager as cm


_TICK = [0]


def _write_cfg(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # Явные монотонные mtime: у часов Windows грубая гранулярность (~15 мс),
    # из-за чего две записи подряд могут получить одинаковую метку.
    _TICK[0] += 1
    stamp = 1_000_000_000.0 + _TICK[0]
    os.utime(path, (stamp, stamp))


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    _write_cfg(p, {})
    monkeypatch.setattr(cm, "_PATH", p)
    monkeypatch.setattr(cm, "_cache", {})
    monkeypatch.setattr(cm, "_stamp", None)
    return p


def _load(rel_path, name):
    path = Path(__file__).resolve().parents[1] / rel_path
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def whisper_mod(tmp_path):
    mod = _load("skills/builtin/auras-whisper/skill.py", "whisper_wiring")
    mod._DATA = tmp_path / "whisper_wiring.json"
    return mod


def test_agent_truncate_uses_config(cfg):
    from autogen.beta.agent import _truncate_result
    _write_cfg(cfg, {"agent": {"default_result_limit": 50}})
    out = _truncate_result("выдуманный_инструмент", "x" * 500)
    assert "обрезан" in out
    assert len(out) < 500


def test_whisper_threshold_live_update(cfg, whisper_mod):
    w = whisper_mod
    w._save_history({"whispers": [{"tone": "tender", "text": "x", "ts": "t"}]})

    _write_cfg(cfg, {"whisper": {"silence_hours": 2}})
    assert "Шептать: да" in w.whisper_decide(time_since_last_hours=2.5)

    # внешняя правка конфига — подхватывается без перезапуска
    _write_cfg(cfg, {"whisper": {"silence_hours": 10}})
    with mock.patch.object(random, "random", return_value=0.99):
        out = w.whisper_decide(time_since_last_hours=2.5,
                               is_morning=False, is_evening=False)
    assert "не нужен" in out.lower()


def test_google_ai_reads_config(cfg):
    mod = _load("skills/custom/google-ai/skill.py", "google_ai_wiring")
    _write_cfg(cfg, {"google_ai": {"cdp_port": 1234, "timeout_sec": 42,
                                   "max_chars": 999, "helper_path": r"D:\tmp\h.py"}})
    assert mod._cdp_port() == 1234
    assert mod._timeout() == 42
    assert mod._max_out() == 999
    assert str(mod._helper()).endswith("h.py")


def test_desktop_reads_config(cfg):
    mod = _load("skills/custom/desktop-control/skill.py", "desktop_wiring")
    _write_cfg(cfg, {"desktop_control": {"failsafe": False, "pause_sec": 0.5}})
    assert mod._cfg_failsafe() is False
    assert mod._cfg_pause() == 0.5
    _write_cfg(cfg, {"desktop_control": {"failsafe": "false"}})
    assert mod._cfg_failsafe() is False  # строковый "false" тоже понимается
