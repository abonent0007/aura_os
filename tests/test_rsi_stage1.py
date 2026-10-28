# -*- coding: utf-8 -*-
"""Этап 1 RSI: трейсы (M1), вики (M7), рефлексия (M2)."""
import asyncio
import json

import pytest

from aura.rsi import ExperienceWiki, ReflectionEngine, ReflectionError, TraceLogger


# ── M1 ─────────────────────────────────────────────────────────

def test_trace_log_and_read(tmp_path):
    t = TraceLogger(root=str(tmp_path))
    e1 = t.task("s1", "привет")
    e2 = t.tool_result("s1", "get_weather", "ok", success=True, latency_ms=10)
    assert e1.startswith("evt_") and e2 != e1

    rows = t.read("s1")
    assert [r["kind"] for r in rows] == ["task", "tool_result"]
    assert rows[0]["payload"]["text"] == "привет"
    assert rows[1]["payload"]["success"] is True


def test_trace_digest_has_event_ids(tmp_path):
    t = TraceLogger(root=str(tmp_path))
    t.task("s2", "x")
    t.error("s2", "boom")
    digest = t.digest("s2")
    assert len(digest) == 2
    assert all(d["event_id"].startswith("evt_") for d in digest)


def test_trace_rotates(tmp_path):
    t = TraceLogger(root=str(tmp_path), max_mb=0.0002)  # ~200 байт
    for i in range(6):
        t.task("s3", f"сообщение {i} " + "y" * 60)
    assert (tmp_path / "s3.1.jsonl").exists()


# ── M7 ─────────────────────────────────────────────────────────

def test_wiki_write_and_retrieve(tmp_path):
    w = ExperienceWiki(root=str(tmp_path), top_k=3)
    w.write_lesson("Погода падала", "MET.no таймаут", "кэш координат",
                   "сработал fallback", "latency -1s", tags=["weather"])
    found = w.retrieve("почему падала погода")
    assert found and found[0]["title"] == "Погода падала"
    assert found[0]["slug"]


def test_wiki_dedupes_by_diff_hash(tmp_path):
    w = ExperienceWiki(root=str(tmp_path))
    a = w.write_lesson("Раз", "p", "h", "r", diff_hash="abc123")
    b = w.write_lesson("Два", "p2", "h2", "r2", diff_hash="abc123")
    assert a["slug"] == b["slug"]
    assert b.get("duplicate") is True
    assert len(list(tmp_path.glob("*.md"))) == 1


# ── M2 ─────────────────────────────────────────────────────────

def _trace_with_events(tmp_path, session="s1"):
    t = TraceLogger(root=str(tmp_path))
    e1 = t.task(session, "посчитай погоду")
    e2 = t.tool_result(session, "get_weather", "timeout", success=False)
    t.final_outcome(session, "не смогла")
    return t, e1, e2


def test_reflect_validates_evidence(tmp_path):
    trace, e1, e2 = _trace_with_events(tmp_path)
    t = TraceLogger(root=str(tmp_path))
    t.root = trace.root

    wiki = ExperienceWiki(root=str(tmp_path / "wiki"))
    engine = ReflectionEngine(wiki=wiki, root=str(tmp_path / "refl"),
                              config={"reflection": {"max_events": 80}})
    engine.trace = trace

    async def fake_llm(system, user):
        return json.dumps({
            "problems": [
                {"id": "p1", "statement": "погода упала", "evidence": [e2], "impact": "high"},
                {"id": "p2", "statement": "выдумка", "evidence": ["evt_nope"], "impact": "low"},
            ],
            "hypotheses": [{"id": "h1", "statement": "кэшировать", "target_file": "config.json#agent.tool_router", "confidence": 0.7}],
            "suggested_mutations": [{"hypothesis_id": "h1", "target_file": "config.json#agent.tool_router", "change_summary": "добавить кэш"}],
        })

    result = asyncio.run(engine.reflect("s1", llm=fake_llm, save=False))
    assert [p["id"] for p in result["problems"]] == ["p1"]
    assert result["dropped_problems"] == 1
    assert result["hypotheses"][0]["target_file"] == "config.json#agent.tool_router"


def test_reflect_rejects_broken_json(tmp_path):
    trace, _, _ = _trace_with_events(tmp_path)
    engine = ReflectionEngine(wiki=ExperienceWiki(root=str(tmp_path / "w")),
                              root=str(tmp_path / "r"),
                              config={"reflection": {}})
    engine.trace = trace

    async def bad_llm(system, user):
        return "это не json"

    with pytest.raises((ReflectionError, json.JSONDecodeError)):
        asyncio.run(engine.reflect("s1", llm=bad_llm, save=False))


def test_reflect_requires_trace(tmp_path):
    engine = ReflectionEngine(wiki=ExperienceWiki(root=str(tmp_path / "w")),
                              root=str(tmp_path / "r"),
                              config={"reflection": {}})
    engine.trace = TraceLogger(root=str(tmp_path / "traces"))
    with pytest.raises(ReflectionError):
        asyncio.run(engine.reflect("no-such-session", save=False))


# ── M7 из рефлексии ────────────────────────────────────────────

def test_save_lessons_writes_and_dedupes(tmp_path):
    wiki = ExperienceWiki(root=str(tmp_path))
    engine = ReflectionEngine(wiki=wiki, root=str(tmp_path / "r"),
                              config={"reflection": {}})
    result = {
        "problems": [{"statement": "погода падала"}],
        "hypotheses": [{"statement": "кэшировать геокодинг", "confidence": 0.6}],
    }
    first = engine.save_lessons(result)
    assert len(first) == 1 and wiki.list_lessons()
    second = engine.save_lessons(result)
    assert second[0].get("duplicate") is True
    assert len(wiki.list_lessons()) == 1


def test_error_text_heuristic():
    from aura_core import _looks_like_error

    assert _looks_like_error("Погода недоступна: источники не ответили.")
    assert _looks_like_error("API timeout (network unreachable)")
    assert not _looks_like_error("🌤 Погода — Москва, +7, ясно")
