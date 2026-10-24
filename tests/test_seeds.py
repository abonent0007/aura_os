# -*- coding: utf-8 -*-
"""Тесты aura_seeds: relief/compress-переходы, устойчивость к мусору в БД."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from aura_seeds import SeedStore, DEFAULT_RELIEF, format_style_block, COMPRESS_RITUAL


@pytest.fixture()
def store(tmp_conn):
    return SeedStore(tmp_conn)


def test_create_and_live(store):
    sid = store.create_seed(["тема"], ["отклик"], [], [])
    seeds = store.live_seeds()
    assert [s["id"] for s in seeds] == [sid]
    assert seeds[0]["touched"] == ["тема"]


def test_parent_gets_sprout_and_weight(store, tmp_conn):
    parent = store.create_seed(["a"], [], [], [], weight=0.5)
    child = store.create_seed(["b"], [], [], [], parent=parent)
    row = tmp_conn.execute("SELECT sprouts, weight FROM seeds WHERE id = ?", (parent,)).fetchone()
    assert child in json.loads(row[0])
    assert row[1] == pytest.approx(0.6)


def test_pick_unfinished_skips_used_and_empty(store):
    s1 = store.create_seed(["x"], [], [], ["думает"])
    store.create_seed(["z"], ["r"], [], [])       # без открытых концов — не берём
    s2 = store.create_seed(["y"], [], [], ["думает2"])
    store.mark_used(s2)
    picked = store.pick_unfinished()
    assert picked and picked["id"] == s1
    store.mark_used(s1)
    assert store.pick_unfinished() is None


def test_relief_empty_is_default(store):
    assert store.relief() == DEFAULT_RELIEF


def test_relief_bounds_and_shift(store):
    for _ in range(6):
        store.create_seed(["t"], [], ["открыто", "ещё"], ["тянет"])
    r = store.relief()
    assert 3 <= r["max_sentences"] <= 7
    for key in ("seam_pressure", "echo_bias", "pause_bias", "question_bias"):
        assert 0.0 <= r[key] <= 1.0
    assert r["question_bias"] > 0.5


def test_corrupted_json_row_survives(store, tmp_conn):
    tmp_conn.execute(
        "INSERT INTO seeds (id, time, touched, resonated, unresolved, gradient) "
        "VALUES ('s_bad', ?, 'NOT_JSON', '[]', '[]', '[]')",
        (datetime.now(timezone.utc).isoformat(),),
    )
    tmp_conn.commit()
    seeds = store.live_seeds()
    assert any(s["id"] == "s_bad" and s["touched"] == [] for s in seeds)
    r = store.relief()
    assert 3 <= r["max_sentences"] <= 7


def test_compress_merges_group_of_three(store, tmp_conn):
    ids = [store.create_seed(["общая", "тема"], [], [], []) for _ in range(3)]
    for sid in ids:
        tmp_conn.execute("UPDATE seeds SET weight = 0.9 WHERE id = ?", (sid,))
    tmp_conn.commit()
    res = store.compress()
    assert res["compressed"] == 1
    ids_left = {r[0] for r in tmp_conn.execute("SELECT id FROM seeds")}
    assert not (set(ids) & ids_left)
    merged = tmp_conn.execute("SELECT * FROM seeds").fetchone()
    assert merged["id"].startswith("m_")
    assert set(json.loads(merged["touched"])) == {"общая", "тема"}


def test_compress_preserves_used_flag(store, tmp_conn):
    ids = [store.create_seed(["т"], [], [], []) for _ in range(3)]
    for sid in ids:
        tmp_conn.execute(
            "UPDATE seeds SET weight = 0.9, used_for_initiative = 1 WHERE id = ?", (sid,)
        )
    tmp_conn.commit()
    store.compress()
    merged = tmp_conn.execute("SELECT used_for_initiative FROM seeds").fetchone()
    assert merged[0] == 1


def test_compress_if_due(store, tmp_conn):
    store.create_seed(["т"], [], [], [])
    assert store.compress_if_due(days=7) is not None
    assert store.compress_if_due(days=7) is None
    old = (datetime.now() - timedelta(days=8)).isoformat()
    tmp_conn.execute("UPDATE rituals SET last_performed = ? WHERE name = ?",
                     (old, COMPRESS_RITUAL))
    tmp_conn.commit()
    assert store.compress_if_due(days=7) is not None


def test_format_style_block_variants():
    base = format_style_block(dict(DEFAULT_RELIEF))
    assert "своим голосом" in base
    assert "коротче" not in base and "свободнее" not in base

    tight = format_style_block({"max_sentences": 3, "seam_pressure": 0.7,
                                "echo_bias": 0.7, "pause_bias": 0.6,
                                "question_bias": 0.6})
    assert "до 3 предложений" in tight
    assert "свой угол" in tight
    assert "открытыми" in tight
    assert "реже" in tight

    assert "своим голосом" in format_style_block(None)
