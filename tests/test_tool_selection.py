# -*- coding: utf-8 -*-
"""Выбор инструментов: always-on ядро, триггеры, потолок."""
from autogen.beta.agent import Agent, DEFAULT_ALWAYS_ON, _match_stems
from autogen.beta.config import OpenAIConfig


def _cfg():
    return OpenAIConfig(model="t", api_key="sk-test", base_url="https://x/v1")


def _tool(name, doc="", trigger=None):
    def fn() -> str:
        return "ok"
    fn.__name__ = name
    fn.__doc__ = doc
    return fn


def _agent(tools, triggers=None):
    agent = Agent(config=_cfg(), tools=list(tools), system_message="")
    agent.set_core_tools([f.__name__ for f in tools])
    agent.add_tools([], triggers or {})
    return agent


def test_greeting_sends_no_tools():
    a = _agent([_tool("search_memory", "Поиск по истории")])
    assert a._select_tool_names("привет") == set()
    assert a._select_tool_names("доброе утро!") == set()


def test_always_on_is_small_and_present():
    a = _agent([_tool(n, "описание") for n in DEFAULT_ALWAYS_ON])
    selected = a._select_tool_names("расскажи что-нибудь")
    assert "search_memory" in selected
    assert "find_tools" in selected
    # always-on не раздувается: 13 + find_tools
    assert len(selected) <= len(DEFAULT_ALWAYS_ON) + 1


def test_trigger_matches_morphology():
    tools = [_tool("care_remind_water", "Напомнить выпить воды"),
             _tool("care_remind_tea", "Напомнить про чай")]
    a = _agent(tools, {"care_remind_water": ["вода"], "care_remind_tea": ["чай"]})
    assert "care_remind_water" in a._select_tool_names("напомни выпить воды")


def test_cap_is_strict():
    tools = [_tool("search_memory", "Поиск по истории")]
    tools += [_tool(f"tool_{i}", f"Инструмент номер {i}") for i in range(30)]
    a = _agent(tools, {f"tool_{i}": ["тест"] for i in range(30)})
    a.set_core_tools(["search_memory"])  # always-on меньше потолка
    selected = a._select_tool_names("тест тест тест", cap=8)
    assert len(selected) <= 8
    assert "search_memory" in selected


def test_curated_trigger_project_write():
    tools = [_tool("project_write", "Записать файл проекта"),
             _tool("project_read", "Прочитать файл проекта")]
    a = _agent(tools)
    assert "project_write" in a._select_tool_names("напиши код на python")


def test_stems_cover_short_words():
    stems = _match_stems("выпить воды")
    assert "вод" in stems
    assert _match_stems("погоду") & _match_stems("погода")
