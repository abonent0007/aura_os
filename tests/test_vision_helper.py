# -*- coding: utf-8 -*-
"""Тесты vision_describe: бюджет токенов и один fallback-ретрай при пустом content."""
import types

from utils import vision_describe


class _Msg:
    def __init__(self, content):
        self.content = content


class _Resp:
    def __init__(self, content, finish="stop"):
        self.choices = [types.SimpleNamespace(message=_Msg(content), finish_reason=finish)]
        self.usage = types.SimpleNamespace(completion_tokens=10)


class _Comp:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class _Client:
    def __init__(self, script):
        self.chat = types.SimpleNamespace(completions=_Comp(script))


def test_retry_on_empty_content():
    client = _Client([_Resp(None), _Resp("На экране открыт OpenCode.")])
    text, meta = vision_describe("AAA", "image/png", "что на экране?", client=client)
    assert text == "На экране открыт OpenCode."
    calls = client.chat.completions.calls
    assert len(calls) == 2
    assert calls[0]["max_tokens"] >= 3000
    assert calls[1]["max_tokens"] >= calls[0]["max_tokens"]
    assert meta["first"]["limit"] >= 3000
    assert meta["retry"]["limit"] >= 5000


def test_no_retry_when_content_present():
    client = _Client([_Resp("Вижу браузер и редактор.")])
    text, _meta = vision_describe("AAA", "image/png", "что?", client=client)
    assert text == "Вижу браузер и редактор."
    assert len(client.chat.completions.calls) == 1


def test_empty_after_retry_returns_empty():
    client = _Client([_Resp(None), _Resp("   ")])
    text, _meta = vision_describe("AAA", "image/png", "что?", client=client)
    assert text == ""
