# -*- coding: utf-8 -*-
"""Тесты config_manager: кэш, автообновление при изменении файла, устойчивость к мусору."""
import json
import os

import pytest

import config_manager as cm


@pytest.fixture()
def cfg_file(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    p.write_text(json.dumps({"a": {"b": 1}, "x": "v1"}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(cm, "_PATH", p)
    monkeypatch.setattr(cm, "_cache", {})
    monkeypatch.setattr(cm, "_stamp", None)
    return p


def _bump_mtime(path, delta=2.0):
    st = os.stat(path)
    os.utime(path, (st.st_atime, st.st_mtime + delta))


def test_missing_file_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(cm, "_PATH", tmp_path / "nope.json")
    monkeypatch.setattr(cm, "_cache", {})
    monkeypatch.setattr(cm, "_stamp", None)
    assert cm.get("a.b", 42) == 42
    assert cm.get_all() == {}


def test_nested_and_default(cfg_file):
    assert cm.get("a.b") == 1
    assert cm.get("a.missing", "def") == "def"
    assert cm.get("nope.deep", None) is None
    assert cm.get("") is None


def test_refresh_on_external_change(cfg_file):
    assert cm.get("x") == "v1"
    cfg_file.write_text(json.dumps({"a": {"b": 2}, "x": "v2"}), encoding="utf-8")
    _bump_mtime(cfg_file)
    # внешняя правка (как PUT /api/config) подхватывается без reload()
    assert cm.get("x") == "v2"
    assert cm.get("a.b") == 2


def test_same_mtime_serves_cache(cfg_file):
    assert cm.get("x") == "v1"
    st = os.stat(cfg_file)
    cfg_file.write_text(json.dumps({"x": "v2"}), encoding="utf-8")
    os.utime(cfg_file, (st.st_atime, st.st_mtime))  # mtime не изменился
    assert cm.get("x") == "v1"


def test_invalid_json_keeps_last_good(cfg_file):
    assert cm.get("x") == "v1"
    cfg_file.write_text("{ broken json", encoding="utf-8")
    _bump_mtime(cfg_file)
    assert cm.get("x") == "v1"  # не падаем и держим последнюю валидную копию


def test_reload_forces_reread(cfg_file):
    assert cm.get("x") == "v1"
    cfg_file.write_text(json.dumps({"x": "v9"}), encoding="utf-8")
    st = os.stat(cfg_file)
    os.utime(cfg_file, (st.st_atime, st.st_mtime))
    assert cm.reload().get("x") == "v9"
