# -*- coding: utf-8 -*-
"""Тесты fallback в _formulate_message: ошибки LLM не доставляются как инициативы."""
import asyncio

from plugins.aura_autonomy import AutonomousObserver


def _make():
    o = object.__new__(AutonomousObserver)
    o.aura_agent = None
    o._current_thread_seed = None
    return o


def test_care_break_keeps_warm_fallback():
    o = _make()
    msg = asyncio.run(o._formulate_message("care_break", "VS Code"))
    assert msg and "перерыв" in msg


def test_code_chat_fallback_is_silent_without_llm():
    o = _make()
    msg = asyncio.run(o._formulate_message("code_chat", "VS Code"))
    assert msg == ""
