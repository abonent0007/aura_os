# -*- coding: utf-8 -*-
"""Тесты auras-whisper: целостность пулов, битый файл истории, логика решений."""
import importlib.util
import random
import unittest.mock as mock
from pathlib import Path

import pytest


def load_whisper():
    path = (Path(__file__).resolve().parents[1] / "skills" / "builtin"
            / "auras-whisper" / "skill.py")
    spec = importlib.util.spec_from_file_location("whisper_skill_t", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def whisper(tmp_path, monkeypatch):
    mod = load_whisper()
    monkeypatch.setattr(mod, "_DATA", tmp_path / "whisper_data.json")
    return mod


def test_pools_integrity(whisper):
    pools = [whisper.TENDER_WHISPERS, whisper.PLAYFUL_WHISPERS, whisper.CARING_WHISPERS,
             whisper.INSPIRING_WHISPERS, whisper.MISSING_YOU_WHISPERS,
             whisper.MORNING_WHISPERS, whisper.EVENING_WHISPERS,
             whisper.MEMORY_WHISPERS]
    pools += list(whisper.WEATHER_WHISPERS.values())
    for pool in pools:
        assert pool, "пустой пул"
        for line in pool:
            assert isinstance(line, str) and line.strip()


def test_weather_pool_balanced(whisper):
    all_lines = [x for lst in whisper.WEATHER_WHISPERS.values() for x in lst]
    rain = whisper.WEATHER_WHISPERS["rain"]
    assert "wind" in whisper.WEATHER_WHISPERS
    assert "fog" in whisper.WEATHER_WHISPERS
    assert len(rain) / len(all_lines) <= 0.25, "дождь снова доминирует"


def test_load_history_corrupt_file(whisper):
    whisper._DATA.write_text("{broken", encoding="utf-8")
    assert whisper._load_history() == {"whispers": []}


def test_generate_writes_history_and_caps(whisper):
    for _ in range(105):
        whisper.whisper_generate("tender")
    data = whisper._load_history()
    assert len(data["whispers"]) == 100
    assert all(w["text"].strip() for w in data["whispers"])


def test_decide_silence(whisper):
    out = whisper.whisper_decide(time_since_last_hours=5)
    assert "Шептать: да" in out
    assert "missing_you" in out


def test_decide_not_needed(whisper):
    whisper._save_history({"whispers": [{"tone": "tender", "text": "x", "ts": "t"}]})
    with mock.patch.object(random, "random", return_value=0.99):
        out = whisper.whisper_decide(time_since_last_hours=0.5,
                                     is_morning=False, is_evening=False)
    assert "не нужен" in out.lower()


def test_quick_with_none_mood(whisper):
    """Внешние данные: LLM может передать user_mood=None — не должно падать."""
    out = whisper.whisper_quick(tone="tender", user_mood=None, hours_since_last=5)
    assert isinstance(out, str) and out.startswith("🤫")


def test_quick_mood_override(whisper):
    with mock.patch.object(random, "random", return_value=0.0):
        out = whisper.whisper_quick(tone="playful", user_mood="tired", hours_since_last=0)
    assert out.startswith("🤫")
