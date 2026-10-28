# -*- coding: utf-8 -*-
"""Непрерывность диалога: реплики, темы, сжатие, зрение."""
import asyncio
from types import SimpleNamespace

import pytest

from aura_core import AuraAgent
from database import AuraDatabase


@pytest.fixture
def db(tmp_path):
    cfg = {"memory": {"db_path": str(tmp_path / "aura_test.db")}}
    database = AuraDatabase(cfg)
    yield database
    database.conn.close()


def _turns(name):
    return " ".join(f"Реплика номер {i}. " + "текст " * 40 for i in range(name))


# ── Реплики ────────────────────────────────────────────────────

def test_dialogue_turns_roundtrip(db):
    db.add_dialogue_turn("user", "привет")
    db.add_dialogue_turn("assistant", "привет, как ты?")
    db.add_dialogue_turn("user", "нормально")

    recent = db.get_recent_turns("main", limit=2)
    assert [t["role"] for t in recent] == ["assistant", "user"]
    assert recent[-1]["content"] == "нормально"
    assert db.count_dialogue_turns("main") == 3


def test_search_turns_fts(db):
    db.add_dialogue_turn("user", "Вчера мы говорили про погоду в Москве")
    db.add_dialogue_turn("assistant", "Да, обещала проверить дождь")
    found = db.search_turns_fts("погоду")
    assert found and "погоду" in found[0]["content"].lower()


def test_prune_dialogue_max_turns(db):
    for i in range(10):
        db.add_dialogue_turn("user", f"сообщение {i}")
    removed = db.prune_dialogue("main", max_turns=5, days=30)
    assert removed == 5
    assert db.count_dialogue_turns("main") == 5
    assert db.get_recent_turns("main", 1)[0]["content"] == "сообщение 9"


# ── Незакрытые темы ────────────────────────────────────────────

def _stub(db, gap=None):
    return SimpleNamespace(db=db, _session_id="main", _last_gap_minutes=gap)


def test_extract_and_close_question_topic(db):
    stub = _stub(db)
    AuraAgent._extract_open_topics(stub, "Хочешь, расскажу про дождь?", role="assistant")
    topics = db.get_open_topics("main")
    assert len(topics) == 1 and topics[0]["kind"] == "question"

    AuraAgent._close_matching_topics(stub, "да, расскажи")
    assert db.get_open_topics("main") == []


def test_promise_topic_detected(db):
    stub = _stub(db)
    AuraAgent._extract_open_topics(stub, "Хорошо, я проверю расписание и напишу.", role="assistant")
    topics = db.get_open_topics("main")
    assert topics and topics[0]["kind"] == "promise"


def test_open_topics_block_only_after_pause(db):
    stub = _stub(db, gap=10)
    db.add_open_topic("question", "Ты дочитал книгу?", "main")
    assert AuraAgent._open_topics_block(stub) == ""

    stub._last_gap_minutes = 200
    block = AuraAgent._open_topics_block(stub)
    assert "Незакрытые темы" in block and "книгу" in block


# ── Один вопрос ────────────────────────────────────────────────

def test_single_question_guard():
    text = "Ты дома? Может, поужинаем вместе? Я приготовила суп."
    fixed, count = AuraAgent._enforce_single_question(text)
    assert count == 1
    assert fixed.count("?") == 1
    assert "поужинаем вместе." in fixed


def test_single_question_keeps_separated_questions():
    text = "Ты дома? Я приготовила суп. Может, поужинаем?"
    fixed, count = AuraAgent._enforce_single_question(text)
    assert count == 0 and fixed.count("?") == 2


# ── Сжатие ─────────────────────────────────────────────────────

class FakeCompactor:
    async def ask(self, prompt, context=""):
        return SimpleNamespace(content="Кратко: обсуждали проект, погоду и планы на завтра.")


def test_summarize_history_reduces_context(db):
    for i in range(60):
        db.add_dialogue_turn("user", f"Реплика {i}: " + "подробности " * 30)
    stub = SimpleNamespace(db=db, _session_id="main",
                           compactor=FakeCompactor(), _compressed_history="")

    result = asyncio.run(AuraAgent.summarize_history(stub, keep_last=10))
    assert "Сжато 50 реплик" in result

    summary = db.get_latest_dialogue_summary("main")
    assert summary is not None
    assert summary["tokens_after"] * 2 <= summary["tokens_before"]


# ── Зрение ─────────────────────────────────────────────────────

def test_vision_trigger_detection():
    stub = SimpleNamespace()
    assert AuraAgent._should_auto_look(stub, "посмотри, что у меня на экране")
    assert AuraAgent._should_auto_look(stub, "видишь, я открыл редактор?")
    assert not AuraAgent._should_auto_look(stub, "не смотри на экран, приватно")
    assert not AuraAgent._should_auto_look(stub, "привет, как дела?")
