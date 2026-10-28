# -*- coding: utf-8 -*-
"""Бенчмарк Chatterbox Multilingual: загрузка и генерация на CPU/GPU."""
import os
import sys
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")  # веса уже локально

CKPT = r"C:\aura_os\models\chatterbox"
DEVICE = os.getenv("CB_DEVICE", "cpu")
TEXT = ("Привет. Это Аура. Сегодня облачно, плюс одиннадцать, "
        "и мне почему-то хочется, чтобы ты никуда не спешил.")
OUT = os.path.join(os.environ.get("TEMP", "."), "chatterbox_test.wav")

from chatterbox.mtl_tts import ChatterboxMultilingualTTS  # noqa: E402

t0 = time.time()
model = ChatterboxMultilingualTTS.from_local(CKPT, device=DEVICE)
print(f"load: {time.time() - t0:.1f}s | device={DEVICE} | sr={model.sr}", flush=True)

t0 = time.time()
wav = model.generate(TEXT, language_id="ru")
dt = time.time() - t0
print(f"generate: {dt:.1f}s | shape={tuple(wav.shape)}", flush=True)

import soundfile as sf  # noqa: E402

sf.write(OUT, wav.squeeze(0).cpu().numpy(), model.sr)
print(f"saved: {OUT} ({os.path.getsize(OUT)} bytes)", flush=True)
