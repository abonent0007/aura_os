"""
pet_sounds.py — Звуки питомца Ауры
Генерирует мурлыканье и чириканье через numpy → WAV в памяти.
Воспроизведение через winsound (стандартная библиотека Windows).
"""
import io
import threading
import wave

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False


def _generate_purr_wav(duration: float = 2.5, volume: float = 0.35) -> bytes:
    """Мурлыканье: несущая ~25 Гц + гармоники, амплитудная модуляция ~5 Гц."""
    if not HAS_NUMPY:
        return b""

    sr = 22050
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Несущая + гармоники (мягкий рокот)
    carrier = (
        np.sin(2 * np.pi * 25 * t) * 0.6
        + np.sin(2 * np.pi * 50 * t) * 0.3
        + np.sin(2 * np.pi * 75 * t) * 0.1
    )

    # Амплитудная модуляция ~5 Гц (прерывистость мурлыканья)
    modulation = 0.7 + 0.3 * np.sin(2 * np.pi * 5 * t + 1.3)

    # Плавное нарастание и затухание (чтобы не щёлкало)
    fade_in = np.minimum(1.0, t / 0.15)
    fade_out = np.minimum(1.0, (duration - t) / 0.3)

    signal = carrier * modulation * fade_in * fade_out * volume
    pcm = (signal * 32767).astype(np.int16)
    return _pcm_to_wav(pcm, sr)


def _generate_chirp_wav(duration: float = 0.35, volume: float = 0.3) -> bytes:
    """Чирик: быстрый восходящий свист (для подмигивания)."""
    if not HAS_NUMPY:
        return b""

    sr = 22050
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)

    # Восходящая частота 800 → 1600 Гц
    freq = 800 + 800 * (t / duration)
    phase = 2 * np.pi * np.cumsum(freq) / sr

    fade_in = np.minimum(1.0, t / 0.03)
    fade_out = np.minimum(1.0, (duration - t) / 0.08)

    signal = np.sin(phase) * fade_in * fade_out * volume
    pcm = (signal * 32767).astype(np.int16)
    return _pcm_to_wav(pcm, sr)


def _pcm_to_wav(pcm, sample_rate: int) -> bytes:
    """Упаковка PCM в WAV-контейнер (RIFF заголовок)."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def play_purr(duration: float = 2.5) -> bool:
    """Воспроизвести мурлыканье в фоновом потоке. Возвращает True если запущено."""
    if not (HAS_NUMPY and HAS_WINSOUND):
        return False

    wav_bytes = _generate_purr_wav(duration)
    if not wav_bytes:
        return False

    def _play():
        try:
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()
    return True


def play_chirp() -> bool:
    """Воспроизвести чирик."""
    if not (HAS_NUMPY and HAS_WINSOUND):
        return False

    wav_bytes = _generate_chirp_wav()
    if not wav_bytes:
        return False

    def _play():
        try:
            winsound.PlaySound(wav_bytes, winsound.SND_MEMORY | winsound.SND_ASYNC)
        except Exception:
            pass

    threading.Thread(target=_play, daemon=True).start()
    return True


def generate_purr_bytes(duration: float = 2.5) -> bytes:
    """Для тестов: вернуть WAV-байты мурлыканья."""
    return _generate_purr_wav(duration)


def generate_chirp_bytes() -> bytes:
    """Для тестов: вернуть WAV-байты чирика."""
    return _generate_chirp_wav()


if __name__ == "__main__":
    ok = play_purr()
    print(f"Purr played: {ok}")
