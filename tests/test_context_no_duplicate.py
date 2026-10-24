# -*- coding: utf-8 -*-
"""Контекст: текущая реплика не должна попадать в промпт дважды."""


class FakeHistory:
    def __init__(self, messages):
        self._messages = messages


class FakeStream:
    def __init__(self, messages):
        self.history = FakeHistory(messages)


def _agent():
    from autogen.beta.agent import Agent
    from autogen.beta.config import OpenAIConfig

    return Agent(config=OpenAIConfig(model="t", api_key="sk-test",
                                     base_url="https://x/v1"),
                 tools=[], system_message="sys")


def _user_texts(messages):
    return [m["content"] for m in messages if m.get("role") == "user"]


def test_duplicate_last_user_message_is_skipped():
    agent = _agent()
    stream = FakeStream([
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "привет!"},
        {"role": "user", "content": "как дела"},
    ])
    messages = agent._build_messages("как дела", stream=stream)
    assert _user_texts(messages) == ["привет", "как дела"]


def test_normal_history_kept():
    agent = _agent()
    stream = FakeStream([
        {"role": "user", "content": "привет"},
        {"role": "assistant", "content": "привет!"},
    ])
    messages = agent._build_messages("как дела", stream=stream)
    assert _user_texts(messages) == ["привет", "как дела"]


def test_same_text_from_past_is_not_dropped():
    agent = _agent()
    stream = FakeStream([
        {"role": "user", "content": "как дела"},
        {"role": "assistant", "content": "хорошо"},
    ])
    messages = agent._build_messages("как дела", stream=stream)
    assert _user_texts(messages) == ["как дела", "как дела"]
