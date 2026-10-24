# -*- coding: utf-8 -*-
"""Тесты telegram_bridge: chat_id, отправка файлов, лимиты, 429-повтор."""
import json
from pathlib import Path

import pytest

import telegram_bridge as tb


class _Resp:
    def __init__(self, status=200, payload=None, text=""):
        self.status_code = status
        self._payload = payload or {"ok": True, "result": {}}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, data=None, files=None):
        self.calls.append({"url": url, "data": data, "files": files})
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123:TEST")
    monkeypatch.setenv("TELEGRAM_BASE_URL", "https://relay.example/bot")


def test_no_chat_id(tmp_path):
    out = tb.send_photo(str(tmp_path / "x.png"), state_path=tmp_path / "state.json")
    assert "chat_id" in out


def test_missing_file(tmp_path):
    state = tmp_path / "state.json"
    tb.remember_chat(42, state)
    out = tb.send_document(str(tmp_path / "nope.pdf"), state_path=state)
    assert "не найден" in out.lower()


def test_send_photo_success_and_multipart(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    state = tmp_path / "state.json"
    tb.remember_chat(42, state)
    client = _Client([_Resp()])
    out = tb.send_photo(str(img), "скриншот", client=client, state_path=state)
    assert out.startswith("✅")
    call = client.calls[0]
    assert "/sendPhoto" in call["url"] and "123:TEST" in call["url"]
    assert call["data"]["chat_id"] == "42"
    assert "photo" in call["files"]


def test_send_document_success(tmp_path):
    f = tmp_path / "report.pdf"
    f.write_bytes(b"%PDF-1.4 test")
    state = tmp_path / "state.json"
    tb.remember_chat(7, state)
    client = _Client([_Resp()])
    out = tb.send_document(str(f), client=client, state_path=state)
    assert out.startswith("✅")
    assert "document" in client.calls[0]["files"]


def test_photo_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(tb, "PHOTO_LIMIT", 10)
    img = tmp_path / "big.png"
    img.write_bytes(b"x" * 20)
    state = tmp_path / "state.json"
    tb.remember_chat(1, state)
    out = tb.send_photo(str(img), state_path=state)
    assert "лимит" in out.lower()


def test_non_image_for_photo(tmp_path):
    f = tmp_path / "note.txt"
    f.write_text("hi", encoding="utf-8")
    state = tmp_path / "state.json"
    tb.remember_chat(1, state)
    out = tb.send_photo(str(f), state_path=state)
    assert "не изображение" in out


def test_429_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(tb.time, "sleep", lambda *_: None)
    f = tmp_path / "doc.bin"
    f.write_bytes(b"data")
    state = tmp_path / "state.json"
    tb.remember_chat(5, state)
    client = _Client([
        _Resp(429, {"ok": False, "description": "Too Many Requests",
                    "parameters": {"retry_after": 1}}),
        _Resp(200, {"ok": True}),
    ])
    out = tb.send_document(str(f), client=client, state_path=state)
    assert out.startswith("✅")
    assert len(client.calls) == 2


def test_state_corrupt(tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{broken", encoding="utf-8")
    assert tb.last_chat(state) is None
    tb.remember_chat(9, state)
    assert tb.last_chat(state) == 9


def test_send_text(tmp_path):
    state = tmp_path / "state.json"
    tb.remember_chat(3, state)
    client = _Client([_Resp()])
    out = tb.send_text("привет", client=client, state_path=state)
    assert out.startswith("✅")
    assert "/sendMessage" in client.calls[0]["url"]


def test_split_short():
    assert tb.split_text("привет") == ["привет"]
    assert tb.split_text("") == []


def test_split_long_paragraphs():
    text = "абзац " * 1200
    parts = tb.split_text(text)
    assert len(parts) >= 2
    assert all(len(p) <= tb.TG_TEXT_LIMIT for p in parts)
    norm = lambda s: s.replace("\n", "").replace(" ", "")
    assert norm("".join(parts)) == norm(text)


def test_split_keeps_code_fence_balanced():
    code = "```python\nprint('hi')\n```\n" + "абзац " * 400
    parts = tb.split_text(code, limit=1200)
    for p in parts:
        if "```" in p:
            assert p.count("```") % 2 == 0


def test_deny_sensitive_files(tmp_path):
    state = tmp_path / "state.json"
    tb.remember_chat(1, state)
    for name in (".env", "credentials.json", "id_rsa.key", "aura.db"):
        f = tmp_path / name
        f.write_text("secret", encoding="utf-8")
        out = tb.send_document(str(f), client=_Client([_Resp()]), state_path=state)
        assert "секрет" in out.lower(), name
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    key = ssh / "config"
    key.write_text("x", encoding="utf-8")
    out = tb.send_document(str(key), client=_Client([_Resp()]), state_path=state)
    assert "секрет" in out.lower()


def test_send_text_multi_chunk(tmp_path):
    state = tmp_path / "state.json"
    tb.remember_chat(8, state)
    client = _Client([_Resp(), _Resp(), _Resp()])
    out = tb.send_text("слово " * 2000, client=client, state_path=state)
    assert "частей" in out
    assert len(client.calls) >= 2
    assert all(len(c["data"]["text"]) <= tb.TG_TEXT_LIMIT for c in client.calls)
