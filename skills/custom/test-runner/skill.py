"""
Test-runner skill for AURA OS.
Запускает тесты инфраструктуры: infographic-generator, browser-automation, freelance-manager.

Smoke-тест — быстрый (импорты).
Full-тест — полный прогон через run_tests.py.
"""

import subprocess
import sys
from pathlib import Path
from autogen.beta import tools

SKILL_DIR = Path(__file__).parent


@tools.tool
def run_smoke_test() -> str:
    """Быстрый smoke-тест — проверяет импорты критических библиотек.
    Без создания файлов, без запуска браузера. ~1 секунда."""
    results = []

    # Pillow
    try:
        from PIL import Image, ImageDraw, ImageFont  # noqa: F401
        results.append("✅ Pillow — OK")
    except ImportError as e:
        results.append(f"❌ Pillow — {e}")

    # matplotlib
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt  # noqa: F401
        results.append("✅ matplotlib — OK")
    except ImportError as e:
        results.append(f"❌ matplotlib — {e}")

    # Playwright
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        results.append("✅ Playwright — OK")
    except ImportError as e:
        results.append(f"❌ Playwright — {e}")

    return "\n".join(results)


@tools.tool
def run_all_tests() -> str:
    """Полный прогон всех тестов через run_tests.py.
    Создаёт тестовые изображения, запускает headless-браузер, проверяет JSON-хранилище.
    Может занять до 120 секунд."""
    runner = SKILL_DIR / "run_tests.py"
    if not runner.exists():
        return "❌ run_tests.py не найден"

    try:
        result = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(SKILL_DIR.parent),  # корень skills/
        )
        output = result.stdout
        if result.stderr:
            output += "\n\n[STDERR]\n" + result.stderr
        return output or "⚠️ Тесты завершились без вывода"
    except subprocess.TimeoutExpired:
        return "❌ Превышен таймаут (120 секунд)"
    except Exception as e:
        return f"❌ Ошибка запуска: {e}"
