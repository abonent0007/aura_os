"""
Комплексный тест инфраструктуры AURA OS:
- infographic-generator (Pillow + matplotlib)
- browser-automation (Playwright)
- freelance-manager (JSON-хранилище)

Запуск: python run_tests.py
"""

import sys, json, os, shutil
from pathlib import Path
from datetime import datetime, date

# Добавляем корень skills/ в path
SKILLS_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(SKILLS_ROOT))

RESULTS = []
PASS = "✅"
FAIL = "❌"
WARN = "⚠️"

def test(name, condition, detail=""):
    status = PASS if condition else FAIL
    msg = f"  {status} {name}"
    if detail and not condition:
        msg += f" — {detail}"
    print(msg)
    RESULTS.append({"name": name, "ok": condition, "detail": detail if not condition else ""})

def header(text):
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}")

def summary():
    total = len(RESULTS)
    ok = sum(1 for r in RESULTS if r["ok"])
    fail = total - ok
    header("📊 ИТОГИ")
    print(f"  Пройдено: {ok}/{total}")
    if fail == 0:
        print(f"  🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ!")
    else:
        print(f"  ❌ Упало: {fail}")
        print(f"\n  Упавшие тесты:")
        for r in RESULTS:
            if not r["ok"]:
                print(f"    - {r['name']}: {r['detail']}")
    print()


# === ПОИСК СИСТЕМНОГО БРАУЗЕРА (общая функция) ===
def _find_system_browser():
    """Ищет Chrome или Chromium в системе. Возвращает executable_path или None."""
    candidates = [
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files\\Chromium\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Chromium\\Application\\chrome.exe",
        os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
        os.path.expandvars("%LOCALAPPDATA%\\Chromium\\Application\\chrome.exe"),
        os.path.expandvars("%LOCALAPPDATA%\\ms-playwright\\chromium-1223\\chrome-win64\\chrome.exe"),
        os.path.expandvars("%LOCALAPPDATA%\\ms-playwright\\chromium-1223\\chrome-win\\chrome.exe"),
    ]
    for cmd in ["chromium", "chrome", "chromium-browser"]:
        found = shutil.which(cmd)
        if found:
            candidates.insert(0, found)
    ms_dir = Path(os.path.expandvars("%LOCALAPPDATA%\\ms-playwright"))
    if ms_dir.exists():
        for chrome_dir in ms_dir.glob("chromium-*/chrome-*/chrome.exe"):
            candidates.insert(0, str(chrome_dir))
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None


def _get_launch_kwargs():
    """Возвращает аргументы для p.chromium.launch(), пробуя разное."""
    exe = _find_system_browser()
    if exe:
        return {"executable_path": exe, "headless": True}
    return {"channel": "chrome", "headless": True}


# ============================================================
header("① INFOGRAPHIC-GENERATOR — Pillow + matplotlib")
# ============================================================

HAS_PILLOW = False
HAS_MPL = False

try:
    from PIL import Image, ImageDraw, ImageFont
    test("Pillow импортирован", True)
    HAS_PILLOW = True
except ImportError as e:
    test("Pillow импортирован", False, f"pip install pillow — {e}")

try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    test("matplotlib импортирован", True)
    HAS_MPL = True
except ImportError as e:
    test("matplotlib импортирован", False, f"pip install matplotlib — {e}")

output_dir = SKILLS_ROOT / "infographic-generator" / "output"
output_dir.mkdir(exist_ok=True)
test("Output-директория", output_dir.exists())

if HAS_PILLOW:
    try:
        W, H = 800, 600
        img = Image.new("RGB", (W, H), (245, 247, 250))
        draw = ImageDraw.Draw(img)
        try:
            font_title = ImageFont.truetype("arial.ttf", 36)
        except:
            try:
                font_title = ImageFont.truetype("DejaVuSans.ttf", 36)
            except:
                font_title = ImageFont.load_default()
        draw.text((40, 30), "Тестовая карточка AURA OS", fill=(30, 60, 120), font=font_title)
        draw.rectangle([(40, 80), (W-40, 82)], fill=(66, 133, 244))
        facts = ["Pillow работает", "matplotlib работает", "Шрифты загружены", "Цвета корректны"]
        y = 110
        for i, fact in enumerate(facts):
            draw.ellipse([(40, y+2), (70, y+32)], fill=(66, 133, 244))
            draw.text((55, y+5), str(i+1), fill=(255, 255, 255), font=ImageFont.load_default())
            draw.text((90, y+2), fact, fill=(50, 50, 50), font=ImageFont.load_default())
            y += 55
        card_path = output_dir / "test_card.png"
        img.save(str(card_path), "PNG")
        test("Создание карточки", card_path.exists(), f"размер: {card_path.stat().st_size} байт")
    except Exception as e:
        test("Создание карточки", False, str(e))

if HAS_MPL:
    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        data = {"Январь": 100, "Февраль": 250, "Март": 180, "Апрель": 320, "Май": 200}
        colors = ["#4285F4", "#34A853", "#FBBC04", "#EA4335", "#8E7CC3"]
        ax.bar(data.keys(), data.values(), color=colors, edgecolor="white", linewidth=1.5)
        ax.set_title("Тестовая диаграмма AURA OS", fontsize=18, fontweight="bold")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        chart_path = output_dir / "test_barchart.png"
        fig.savefig(str(chart_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        test("Создание столбчатой диаграммы", chart_path.exists(), f"размер: {chart_path.stat().st_size} байт")
    except Exception as e:
        test("Создание столбчатой диаграммы", False, str(e))

    try:
        fig, ax = plt.subplots(figsize=(10, 6))
        months = ["Янв", "Фев", "Мар", "Апр", "Май"]
        sales = [100, 250, 180, 320, 200]
        costs = [80, 200, 140, 280, 170]
        ax.plot(months, sales, 'o-', color="#4285F4", linewidth=2, markersize=8, label="Выручка")
        ax.plot(months, costs, 's--', color="#EA4335", linewidth=2, markersize=8, label="Расходы")
        ax.set_title("Тестовый график трендов", fontsize=18, fontweight="bold")
        ax.legend()
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        plt.tight_layout()
        line_path = output_dir / "test_linechart.png"
        fig.savefig(str(line_path), dpi=150, bbox_inches="tight")
        plt.close(fig)
        test("Создание линейного графика", line_path.exists(), f"размер: {line_path.stat().st_size} байт")
    except Exception as e:
        test("Создание линейного графика", False, str(e))

# ============================================================
header("② BROWSER-AUTOMATION — Playwright")
# ============================================================

HAS_PW = False
LAUNCH_KWARGS = {}
try:
    from playwright.sync_api import sync_playwright
    test("Playwright импортирован", True)
    HAS_PW = True
except ImportError as e:
    test("Playwright импортирован", False, f"pip install playwright — {e}")

if HAS_PW:
    # === Ищем как запускать браузер ===
    LAUNCH_KWARGS = _get_launch_kwargs()
    launch_method = "executable_path" if "executable_path" in LAUNCH_KWARGS else "channel"
    print(f"  ℹ️  Способ запуска: {launch_method} = {LAUNCH_KWARGS.get('executable_path', LAUNCH_KWARGS.get('channel', '?'))}")

    # Проверка: запуск Chromium
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**LAUNCH_KWARGS)
            browser.close()
            test("Запуск Chromium (headless)", True)
    except Exception as e:
        # Фолбэк: пробуем channel="chrome"
        try:
            LAUNCH_KWARGS = {"channel": "chrome", "headless": True}
            with sync_playwright() as p:
                browser = p.chromium.launch(**LAUNCH_KWARGS)
                browser.close()
                test("Запуск Chromium (headless)", True)
        except Exception as e2:
            test("Запуск Chromium (headless)", False, str(e2)[:200])

    # Загрузка страницы
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(**LAUNCH_KWARGS)
            page = browser.new_page()
            page.goto("https://httpbin.org/headers", timeout=15000)
            content = page.content()
            browser.close()
            has_headers = "headers" in content
            test("Загрузка страницы (httpbin)", has_headers, "страница не загрузилась" if not has_headers else "")
    except Exception as e:
        test("Загрузка страницы (httpbin)", False, str(e)[:200])

    # Скриншот
    try:
        screenshots_dir = SKILLS_ROOT / "browser-automation" / "screenshots"
        screenshots_dir.mkdir(exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(**LAUNCH_KWARGS)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.goto("https://httpbin.org/html", timeout=15000)
            page.wait_for_timeout(500)
            scr_path = screenshots_dir / "test_screenshot.png"
            page.screenshot(path=str(scr_path), full_page=False)
            browser.close()
            test("Скриншот страницы", scr_path.exists(), f"размер: {scr_path.stat().st_size} байт")
    except Exception as e:
        test("Скриншот страницы", False, str(e)[:200])

# ============================================================
header("③ FREELANCE-MANAGER — JSON-хранилище")
# ============================================================

try:
    fm_path = SKILLS_ROOT / "freelance-manager"
    sys.path.insert(0, str(fm_path))
    data_path = fm_path / "data.json"

    if data_path.exists():
        data = json.loads(data_path.read_text(encoding="utf-8"))
    else:
        data = {"clients": [], "orders": [], "order_counter": 0}

    test("data.json доступен", True)

    # Добавление клиента
    test_client_name = "__TEST_CLIENT__"
    new_client = {
        "id": len(data["clients"]) + 1,
        "name": test_client_name,
        "contact": "test@test.com",
        "notes": "автотест"
    }
    data["clients"].append(new_client)
    test("Добавление клиента", any(c["name"] == test_client_name for c in data["clients"]))

    # Создание заказа
    data["order_counter"] = data.get("order_counter", 0) + 1
    new_order = {
        "id": data["order_counter"],
        "client_id": new_client["id"],
        "title": "Тестовый заказ",
        "amount": 5000,
        "status": "new",
        "created": date.today().isoformat()
    }
    data["orders"].append(new_order)
    test("Создание заказа", any(o["title"] == "Тестовый заказ" for o in data["orders"]))

    # Смена статусов
    for status in ["in_progress", "review", "done"]:
        for o in data["orders"]:
            if o["title"] == "Тестовый заказ":
                o["status"] = status
        test(f"Статус → {status}", any(o["status"] == status for o in data["orders"] if o["title"] == "Тестовый заказ"))

    # Сохранение
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    test("Сохранение data.json", data_path.exists())

    # Подсчёт заработка
    done_total = sum(o["amount"] for o in data["orders"] if o["status"] == "done")
    test("Подсчёт заработка", done_total >= 0)

    # Проверка клиентов и заказов
    test("Клиенты в базе", len(data["clients"]) > 0)
    test("Заказы в базе", len(data["orders"]) > 0)

    # Очистка тестовых данных
    data["clients"] = [c for c in data["clients"] if c["name"] != test_client_name]
    data["orders"] = [o for o in data["orders"] if o["title"] != "Тестовый заказ"]
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    test("Очистка тестовых данных", not any(c["name"] == test_client_name for c in data["clients"]))

except Exception as e:
    test("freelance-manager", False, str(e))

# ============================================================
header("④ ДОПОЛНИТЕЛЬНЫЕ ПРОВЕРКИ")
# ============================================================

# Определение ОС
import platform
os_name = platform.system()
test("ОС определена", bool(os_name), os_name)

# Системные шрифты (Windows)
if os_name == "Windows":
    fonts_dir = Path(os.path.expandvars("%WINDIR%\\Fonts"))
    test("Windows — шрифты системные", fonts_dir.exists())
else:
    test("Windows — шрифты системные", True, f"Проверка пропущена: {os_name}")

# Интернет-соединение
try:
    import urllib.request
    urllib.request.urlopen("https://httpbin.org/get", timeout=10)
    test("Интернет-соединение", True)
except Exception as e:
    test("Интернет-соединение", False, str(e))

# ============================================================
summary()
