# -*- coding: utf-8 -*-
"""STT: faster-whisper (ленивая загрузка) + fallback на Vosk."""
import asyncio

from aura_voice import SpeechToText


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, texts):
        self.texts = texts
        self.calls = []

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        return iter([FakeSegment(t) for t in self.texts]), {}


def test_engine_init_is_lazy():
    stt = SpeechToText(engine="faster_whisper")
    assert stt._fw_model is None
    assert stt.fw_model_path.endswith("small")


def test_transcribe_joins_segments():
    stt = SpeechToText(engine="faster_whisper")
    stt._fw_model = FakeModel(["Привет,", "Аура."])
    text = asyncio.run(stt.transcribe_file("x.wav"))
    assert text == "Привет, Аура."
    path, kwargs = stt._fw_model.calls[0]
    assert path == "x.wav"
    assert kwargs["language"] == "ru"


def test_fallback_to_vosk(monkeypatch):
    stt = SpeechToText(engine="faster_whisper")

    def boom(path):
        raise RuntimeError("no model")

    async def fake_vosk(path):
        return "воск"

    stt._fw_transcribe_sync = boom
    monkeypatch.setattr(stt, "_init_vosk",
                        lambda: setattr(stt, "vosk_model", object()))
    monkeypatch.setattr(stt, "_transcribe_vosk", fake_vosk)

    assert asyncio.run(stt.transcribe_file("x.wav")) == "воск"
