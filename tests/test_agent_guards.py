# -*- coding: utf-8 -*-
"""Тесты критических функций agent.py: гарды, обрезка, ошибки, ReAct-переходы."""
import asyncio
import json

from autogen.beta.agent import (
    Agent,
    _is_greeting,
    _strip_pseudo_calls,
    _PSEUDO_TOOL_RE,
    _truncate_result,
    _human_error,
)
from autogen.beta.config import OpenAIConfig
from autogen.beta import tools as tao


# ── фейковый OpenAI-клиент ────────────────────────────────────────────────

class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.type = "function"
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeResponse:
    def __init__(self, content=None, tool_calls=None):
        self.choices = [type("C", (), {"message": FakeMessage(content, tool_calls)})()]


class FakeCompletions:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.calls = []
        self._comp = FakeCompletions(script)
        self._comp.calls = self.calls
        self.chat = type("Chat", (), {"completions": self._comp})()


CALLED = []


@tao.tool
def echo_tool(text: str = "") -> str:
    """Эхо-инструмент."""
    CALLED.append(text)
    return "эхо:" + text


@tao.tool
def bite_tool(size: int = 1) -> str:
    """Кусь-инструмент (по триггеру)."""
    return f"кусь x{size}"


def make_agent(tools=None):
    cfg = OpenAIConfig(model="test-model", api_key="sk-test",
                       base_url="https://example.invalid/v1")
    return Agent(name="t", config=cfg, tools=list(tools or []), system_message="sys")


def run_ask(agent, text):
    return asyncio.run(agent.ask(text))


# псевдо-вызовы (собираем из частей — спец-токены не пишем буквально)
BAR = "\uff5c\uff5c"
OPEN_DSML = "<" + BAR + "DSML" + BAR + " calls>"
INVOKE_DSML = "<" + BAR + "DSML" + BAR + ' invoke name="senses_take_screenshot">'
CLOSE_DSML = "</" + BAR + "DSML" + BAR + " calls>"
PLAIN = '<tool calls>\n<invoke name="desktop_list_windows">\n</invoke>\n</tool calls>'
DSML_TEXT = "Окей, секунду...\n" + OPEN_DSML + "\n" + INVOKE_DSML + "\n" + CLOSE_DSML


# ── гарды ─────────────────────────────────────────────────────────────────

def test_greeting_only_exact():
    assert _is_greeting("Привет!")
    assert _is_greeting("да")
    assert _is_greeting("  Да… ")
    assert not _is_greeting("да конечно смотри")
    assert not _is_greeting("")
    assert not _is_greeting("привет, что нового?")


def test_pseudo_regex_matches_plain():
    assert _PSEUDO_TOOL_RE.search(PLAIN)


def test_pseudo_regex_matches_dsml():
    assert _PSEUDO_TOOL_RE.search(DSML_TEXT)


def test_strip_plain_keeps_surrounding_text():
    text = "Сейчас гляну.\n" + PLAIN + "\nГотово."
    cleaned = _strip_pseudo_calls(text)
    assert "invoke" not in cleaned.lower()
    assert cleaned.startswith("Сейчас гляну.")
    assert cleaned.endswith("Готово.")


def test_strip_dsml_marker_and_blocks():
    cleaned = _strip_pseudo_calls(DSML_TEXT)
    assert "DSML" not in cleaned
    assert "invoke" not in cleaned
    assert cleaned == "Окей, секунду..."


def test_strip_no_markup_unchanged():
    assert _strip_pseudo_calls("просто текст") == "просто текст"


# ── лимиты и ошибки ───────────────────────────────────────────────────────

def test_truncate_default_limit():
    out = _truncate_result("echo_tool", "x" * 5000)
    assert len(out) < 5000
    assert "обрезан" in out


def test_truncate_google_ai_keeps_more():
    text = "y" * 5000
    assert _truncate_result("google_ai", text) == text


def test_human_error_mapping():
    class APITimeoutError(Exception):
        pass

    class APIConnectionError(Exception):
        pass

    assert "моргнула" in _human_error(APITimeoutError("x"))
    assert "сети" in _human_error(APIConnectionError("Connection error."))
    assert "дёргаем" in _human_error(Exception("429 Too Many Requests"))
    assert _human_error(ValueError("boom")) != ""


# ── ReAct-переходы (фейковый клиент) ──────────────────────────────────────

def test_normal_final_answer():
    fake = FakeClient([FakeResponse(content="Привет, хороший!")])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.client = fake
    resp = run_ask(agent, "расскажи про наш проект")
    assert resp.content == "Привет, хороший!"
    assert len(fake.calls) == 1
    assert "tools" in fake.calls[0]


def test_greeting_sends_no_tools():
    fake = FakeClient([FakeResponse(content="Привет!")])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.client = fake
    resp = run_ask(agent, "да")
    assert resp.content == "Привет!"
    assert "tools" not in fake.calls[0]


def test_tool_execution_loop():
    CALLED.clear()
    tc = FakeToolCall("call_1", "echo_tool", json.dumps({"text": "прив"}))
    fake = FakeClient([
        FakeResponse(content="Сейчас.", tool_calls=[tc]),
        FakeResponse(content="Готово: эхо:прив"),
    ])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.client = fake
    resp = run_ask(agent, "повтори прив")
    assert CALLED == ["прив"]
    assert resp.content == "Готово: эхо:прив"
    second_msgs = fake.calls[1]["messages"]
    assert any(m.get("role") == "tool" and "эхо:прив" in m.get("content", "")
               for m in second_msgs)


def test_pseudo_retry_uses_required_and_all_tools():
    fake = FakeClient([
        FakeResponse(content="Секунду...\n" + PLAIN),
        FakeResponse(content="Чистый ответ."),
    ])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.add_tools([bite_tool], {"bite_tool": ["кусь"]})
    agent.client = fake
    resp = run_ask(agent, "расскажи историю")
    assert len(fake.calls) == 2
    first_names = {t["function"]["name"] for t in fake.calls[0]["tools"]}
    second_names = {t["function"]["name"] for t in fake.calls[1]["tools"]}
    assert first_names == {"echo_tool"}
    assert second_names == {"echo_tool", "bite_tool"}
    assert fake.calls[1]["tool_choice"] == "required"
    assert resp.content == "Чистый ответ."


def test_dsml_pseudo_retry():
    fake = FakeClient([
        FakeResponse(content=DSML_TEXT),
        FakeResponse(content="Нашла окно, всё чисто."),
    ])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.add_tools([bite_tool], {"bite_tool": ["кусь"]})
    agent.client = fake
    resp = run_ask(agent, "посмотри окна")
    assert len(fake.calls) == 2
    assert fake.calls[1]["tool_choice"] == "required"
    assert resp.content == "Нашла окно, всё чисто."


def test_tools_sorted_for_prompt_cache():
    fake = FakeClient([FakeResponse(content="Ок.")])
    agent = make_agent([bite_tool, echo_tool])  # обратный алфавитный порядок
    agent.set_core_tools(["echo_tool", "bite_tool"])
    agent.client = fake
    run_ask(agent, "обычный текст без триггеров")
    names = [t["function"]["name"] for t in fake.calls[0]["tools"]]
    assert names == sorted(names)


def test_pseudo_sanitized_when_no_retry_possible():
    fake = FakeClient([FakeResponse(content="Секунду...\n" + PLAIN)])
    agent = make_agent([echo_tool])
    agent.set_core_tools(["echo_tool"])
    agent.client = fake
    resp = run_ask(agent, "просто текст")
    assert len(fake.calls) == 1
    assert "invoke" not in resp.content.lower()
    assert "Секунду" in resp.content
