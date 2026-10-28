# -*- coding: utf-8 -*-
"""Этап 2 RSI: whitelist, мутации, песочница, вердикт."""
import asyncio
from pathlib import Path

import pytest

from aura.rsi.evaluator import Evaluator
from aura.rsi.mutation import MutationEngine, MutationError, is_allowed
from aura.rsi.sandbox import SandboxRunner

ROOT = Path(__file__).resolve().parents[1]


def _prompt() -> str:
    return (ROOT / "system_prompt.py").read_text(encoding="utf-8")


def test_whitelist_rules():
    assert is_allowed("system_prompt.py")
    assert is_allowed("skills/custom/foo/SKILL.md")
    assert not is_allowed("aura_core.py")
    assert not is_allowed(".env")
    assert not is_allowed("../outside.py")


def test_rejects_outside_whitelist(tmp_path):
    engine = MutationEngine(root=str(tmp_path))
    with pytest.raises(MutationError):
        asyncio.run(engine.propose("aura_core.py", "x", new_content="hack"))


def test_rejects_empty_diff(tmp_path):
    engine = MutationEngine(root=str(tmp_path))
    with pytest.raises(MutationError):
        asyncio.run(engine.propose("system_prompt.py", "x", new_content=_prompt()))


def test_rejects_too_large_diff(tmp_path):
    engine = MutationEngine(root=str(tmp_path))
    huge = _prompt() + "\n" + "\n".join(f"# line {i}" for i in range(300))
    with pytest.raises(MutationError):
        asyncio.run(engine.propose("system_prompt.py", "x", new_content=huge))


def test_propose_saves_candidate_and_persona_flag(tmp_path):
    engine = MutationEngine(root=str(tmp_path))
    meta = asyncio.run(engine.propose(
        "system_prompt.py", "добавить правило", new_content=_prompt() + "\n# rsi\n"))
    assert (tmp_path / meta["mut_id"] / "patch.diff").exists()
    assert (tmp_path / meta["mut_id"] / "meta.json").exists()
    assert meta["persona"] is True
    assert meta["auto_allowed"] is False


def test_sandbox_applies_patch_and_runs_tests(tmp_path):
    repo = tmp_path / "repo"
    (repo / "tests").mkdir(parents=True)
    (repo / "system_prompt.py").write_text("X = 1\n", encoding="utf-8")
    (repo / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8")

    patch = ("--- a/system_prompt.py\n+++ b/system_prompt.py\n"
             "@@ -1 +1 @@\n-X = 1\n+X = 2\n")
    result = SandboxRunner(repo_root=str(repo)).run(
        patch, tests="tests/test_ok.py")
    assert result["crashed"] is False, result
    assert result["failed"] == 0, result
    assert result["passed"] >= 1


def test_sandbox_rejects_patch_outside_whitelist():
    patch = ("--- a/aura_core.py\n+++ b/aura_core.py\n@@ -1 +1 @@\n"
             "-old\n+new\n")
    result = SandboxRunner().run(patch, tests="tests/test_context_no_duplicate.py")
    assert result["crashed"] is True
    assert "вне whitelist" in result["error"]


def test_evaluator_verdicts():
    ev = Evaluator()
    ok = ev.evaluate({"crashed": False, "passed": 5, "failed": 0}, diff_lines=10)
    assert ok["passes"]

    bad = ev.evaluate({"crashed": False, "passed": 5, "failed": 1}, diff_lines=10)
    assert not bad["passes"]

    reg = ev.evaluate({"crashed": False, "passed": 5, "failed": 0},
                      diff_lines=10, recall=0.90, recall_baseline=0.95)
    assert not reg["passes"] and "recall" in reg["reason"]
