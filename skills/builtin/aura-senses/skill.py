"""
aura-senses/skill.py — Сенсоры Ауры (v2.0)
Глаза (скриншоты), уши (wake-word), обоняние (системные метрики).
Только локально. Приватный режим — полное отключение.
"""
import os, sys, time, threading, json
from pathlib import Path
from datetime import datetime

from autogen.beta import tools

# ── Приватный режим ──
_PRIVACY_LOCK = threading.Lock()
_PRIVACY_MODE = False
_SCREENSHOTS_DIR = Path(os.environ.get("TEMP", "/tmp")) / "aura_screenshots"
_SCREENSHOTS_DIR.mkdir(exist_ok=True)
MAX_SCREENSHOTS = 20  # максимум скриншотов в кеше


@tools.tool
def senses_status() -> str:
    """
    Проверка состояния всех сенсоров Ауры.
    Показывает что включено, что выключено, приватный режим.
    """
    global _PRIVACY_MODE
    lines = ["👁️ СЕНСОРЫ АУРЫ\n" + "━" * 25]
    lines.append(f"Приватный режим: {'🔒 ВКЛ' if _PRIVACY_MODE else '🔓 выкл'}")

    # Глаза
    try:
        import pygetwindow
        lines.append("👁️ Глаза (скриншоты): ✅ готовы")
    except ImportError:
        lines.append("👁️ Глаза (скриншоты): ❌ pygetwindow не установлен")

    # Уши
    lines.append("👂 Уши (wake-word): ⏸️ фоновый слушатель")

    # Обоняние
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        lines.append(f"👃 Обоняние (метрики): CPU {cpu:.0f}% RAM {mem:.0f}%")
    except ImportError:
        lines.append("👃 Обоняние: ❌ psutil не установлен")

    # Скриншотов в кеше
    shots = list(_SCREENSHOTS_DIR.glob("*.png"))
    lines.append(f"📸 Скриншотов в кеше: {len(shots)}")

    return "\n".join(lines)


@tools.tool
def senses_take_screenshot(analyze: bool = False, question: str = "") -> str:
    """
    Сделать скриншот и (опционально) проанализировать через DeepSeek Vision.
    Без analyze — просто список окон. С analyze — AI-описание содержимого экрана.

    Args:
        analyze: True — отправить скриншот в DeepSeek Vision для анализа
        question: вопрос о содержимом экрана (например "какой код открыт?", "что на экране?")
    """
    global _PRIVACY_MODE
    if _PRIVACY_MODE:
        return "🔒 Приватный режим. Скриншоты отключены."

    try:
        from PIL import ImageGrab
    except ImportError:
        return "❌ Установи: pip install pillow"

    import pygetwindow as gw

    # Описание окон
    windows = []
    try:
        for w in gw.getAllWindows():
            if w.title and w.visible and not w.title.startswith("Windows"):
                windows.append(f"  ▸ {w.title[:80]}")
    except Exception:
        pass

    # Скриншот
    try:
        shot = ImageGrab.grab()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = _SCREENSHOTS_DIR / f"shot_{ts}.png"
        shot.save(path, "PNG")

        # Ротация старых
        all_shots = sorted(_SCREENSHOTS_DIR.glob("*.png"))
        for old in all_shots[:-MAX_SCREENSHOTS]:
            old.unlink()
    except Exception as e:
        path = None
        return f"❌ Ошибка скриншота: {e}"

    lines = ["👁️ СКРИНШОТ"]
    if windows:
        lines.append(f"Активных окон: {len(windows)}")
        lines.extend(windows[:8])
    lines.append(f"Файл: {path.name}")

    # AI-анализ через DeepSeek Vision
    if analyze and path:
        try:
            import base64
            from openai import OpenAI

            # Читаем и кодируем скриншот
            img_data = base64.b64encode(path.read_bytes()).decode("utf-8")
            mime = "image/png"

            client = OpenAI(
                api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com/v1"
            )

            q = question or "Опиши кратко что видно на этом скриншоте: какие программы открыты, что делает пользователь."
            resp = client.chat.completions.create(
                model="deepseek-v4-pro",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": q},
                        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_data}"}}
                    ]
                }],
                max_tokens=500
            )
            analysis = resp.choices[0].message.content
            lines.append(f"\n🤖 АНАЛИЗ DeepSeek Vision:\n{analysis}")
        except Exception as e:
            lines.append(f"\n⚠️ Анализ не выполнен: {e}")

    return "\n".join(lines)


@tools.tool
def senses_system_smell() -> str:
    """
    «Обоняние» — системные метрики: CPU, RAM, диски, сеть, температура.
    Возвращает сводку и предупреждения если что-то не в норме.
    """
    try:
        import psutil
    except ImportError:
        return "❌ psutil не установлен. pip install psutil"

    warnings = []

    # CPU
    cpu = psutil.cpu_percent(interval=0.5)
    cpu_cores = psutil.cpu_count()

    # RAM
    mem = psutil.virtual_memory()

    # Диски
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append(f"  {part.device} {part.mountpoint}: {usage.percent:.0f}% занято ({usage.free / 1e9:.1f} GB свободно)")
            if usage.percent > 90:
                warnings.append(f"⚠️ Диск {part.mountpoint} почти заполнен: {usage.percent:.0f}%")
        except Exception:
            pass

    # Сеть
    net = psutil.net_io_counters()

    # Температура (если есть)
    temp = ""
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for name, entries in temps.items():
                for e in entries[:2]:
                    temp += f"  {name}/{e.label}: {e.current:.0f}°C"
                    if e.current > 80:
                        warnings.append(f"⚠️ Температура {name} высокая: {e.current:.0f}°C")
                    break
                break
    except Exception:
        pass

    # Батарея
    batt = psutil.sensors_battery()
    batt_str = ""
    if batt:
        batt_str = f"  Батарея: {batt.percent:.0f}%{' 🔌' if batt.power_plugged else ' ⚡'}"
        if batt.percent < 20 and not batt.power_plugged:
            warnings.append("⚠️ Батарея разряжается: меньше 20%")

    # Предупреждения
    if cpu > 80:
        warnings.append(f"⚠️ CPU загружен: {cpu:.0f}%")
    if mem.percent > 90:
        warnings.append(f"⚠️ Память почти заполнена: {mem.percent:.0f}%")

    lines = ["👃 СИСТЕМНОЕ ОБОНЯНИЕ\n" + "━" * 30]
    lines.append(f"CPU: {cpu:.0f}% ({cpu_cores} ядер)")
    lines.append(f"RAM: {mem.percent:.0f}% ({mem.used / 1e9:.1f}/{mem.total / 1e9:.1f} GB)")
    lines.append("Диски:")
    lines.extend(disks)
    lines.append(f"Сеть: ↓{net.bytes_recv / 1e6:.0f} MB ↑{net.bytes_sent / 1e6:.0f} MB")
    if temp:
        lines.append(f"Температура:\n{temp}")
    if batt_str:
        lines.append(batt_str)
    if warnings:
        lines.append("\n⚠️ ПРЕДУПРЕЖДЕНИЯ:")
        lines.extend(warnings)
    else:
        lines.append("\n✅ Всё в норме")

    return "\n".join(lines)


@tools.tool
def senses_privacy_mode(enable: bool = True) -> str:
    """
    Включить/выключить приватный режим.
    В приватном режиме: скриншоты не делаются, микрофон не слушает.
    
    Args:
        enable: True — включить приватность, False — выключить
    """
    global _PRIVACY_MODE
    _PRIVACY_MODE = bool(enable)
    
    # Очищаем кеш скриншотов при входе в приватный режим
    if _PRIVACY_MODE:
        for f in _SCREENSHOTS_DIR.glob("*.png"):
            try:
                f.unlink()
            except Exception:
                pass

    return f"🔒 Приватный режим: {'ВКЛЮЧЕН' if _PRIVACY_MODE else 'ВЫКЛЮЧЕН'}"


@tools.tool
def senses_set_wallpaper(mood: str = "auto") -> str:
    """
    Управление обоями через Lively Wallpaper.
    mood: 'auto', 'morning', 'day', 'evening', 'night', 'warm', 'cool'
    Требуется Lively Wallpaper в C:\\Program Files\\Lively Wallpaper
    """
    import subprocess
    lively_path = Path("C:/Program Files/Lively Wallpaper")
    if not lively_path.exists():
        return "❌ Lively Wallpaper не найден. Установи из Microsoft Store или github.com/rocksdanister/lively"

    # Настройки по настроению
    mood_presets = {
        "morning": ("тепло", "рассвет"),
        "day": ("бодрость", "энергия"),
        "evening": ("уют", "закат"),
        "night": ("темнота", "звёзды"),
        "warm": ("тепло", "нежность"),
        "cool": ("прохлада", "спокойствие"),
        "auto": ("auto", ""),
    }

    try:
        # Lively Command Line API
        cli = lively_path / "Livelycu.exe"
        if not cli.exists():
            cli = lively_path / "livelycu.exe"

        if mood == "auto":
            now = datetime.now()
            hour = now.hour
            if 5 <= hour < 11:
                mood = "morning"
            elif 11 <= hour < 17:
                mood = "day"
            elif 17 <= hour < 22:
                mood = "evening"
            else:
                mood = "night"

        preset, _ = mood_presets.get(mood, ("auto", ""))

        result = subprocess.run(
            [str(cli), "setwp", "--name", mood],
            capture_output=True, text=True, timeout=10
        )

        lines = ["🖼️ ОБОИ ОБНОВЛЕНЫ\n" + "━" * 20]
        lines.append(f"Настроение: {mood}")
        lines.append(f"Тема: {preset}")
        if result.stdout.strip():
            lines.append(f"Результат: {result.stdout.strip()}")
        return "\n".join(lines)
    except FileNotFoundError:
        return "❌ Lively Wallpaper CLI не найден"
    except Exception as e:
        return f"❌ Ошибка управления обоями: {e}"
