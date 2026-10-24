# -*- coding: utf-8 -*-
"""Тесты журнала общего чата."""
from web.chat_bus import ChatJournal


def test_order_ids_and_roles():
    j = ChatJournal()
    a = j.add("user", "привет", "web")
    b = j.add("assistant", "привет!", "web")
    assert a["id"] and b["id"] and a["id"] != b["id"]
    assert a["role"] == "user" and b["role"] == "assistant"
    assert [e["text"] for e in j.history()] == ["привет", "привет!"]


def test_after_id():
    j = ChatJournal()
    a = j.add("user", "1", "x")
    j.add("assistant", "2", "x")
    j.add("user", "3", "x")
    assert [e["text"] for e in j.history(after=a["id"])] == ["2", "3"]
    assert [e["text"] for e in j.history(after="unknown")] == ["1", "2", "3"]


def test_limit_and_ring():
    j = ChatJournal(maxlen=5)
    for i in range(10):
        j.add("user", f"m{i}", "x")
    assert len(j.history(limit=100)) == 5
    assert j.history(limit=2)[-1]["text"] == "m9"
    assert j.history(limit=0)[-1]["text"] == "m9"  # клампится к 1


def test_clear():
    j = ChatJournal()
    j.add("user", "x", "x")
    j.clear()
    assert j.history() == []
