# browser-automation/skill.py
# Headless-браузер на Playwright: скриншоты, парсинг, формы, сбор данных
# Фундамент для автоматизации работы с сайтами

import json, os, threading, re, shutil
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

# === КОНФИГУРАЦИЯ ===
_SCREENSHOTS_DIR = Path(__file__).parent / "screenshots"
_SCREENSHOTS_DIR.mkdir(exist_ok=True)
MAX_PAGES = 3
PAGE_TIMEOUT = 20_000  # мс

# === ПОИСК СИСТЕМНОГО CHROME/CHROMIUM ===
def _find_system_browser():
    """Ищет Chrome или Chromium в системе. Возвращает executable_path или None."""
    # 1. Стандартные пути Windows
    candidates = [
        # Chrome (стабильный)
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
        # Chromium (ручная установка)
        "C:\\Program Files\\Chromium\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Chromium\\Application\\chrome.exe",
        # Local AppData Chrome
        os.path.expandvars("%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe"),
        # Local AppData Chromium
        os.path.expandvars("%LOCALAPPDATA%\\Chromium\\Application\\chrome.exe"),
        # Если Юра распаковал в ms-playwright вручную
        os.path.expandvars("%LOCALAPPDATA%\\ms-playwright\\chromium-1223\\chrome-win64\\chrome.exe"),
        os.path.expandvars("%LOCALAPPDATA%\\ms-playwright\\chromium-1223\\chrome-win\\chrome.exe"),
    ]
    
    # 2. Проверяем через where (Windows)
    for cmd in ["chromium", "chrome", "chromium-browser", "google-chrome"]:
        found = shutil.which(cmd)
        if found:
            candidates.insert(0, found)
    
    # 3. Ищем по маске в ms-playwright
    ms_dir = Path(os.path.expandvars("%LOCALAPPDATA%\\ms-playwright"))
    if ms_dir.exists():
        for chrome_dir in ms_dir.glob("chromium-*/chrome-*/chrome.exe"):
            candidates.insert(0, str(chrome_dir))
        for chrome_dir in ms_dir.glob("chromium-*/Chrome-bin/chrome.exe"):
            candidates.insert(0, str(chrome_dir))
    
    for path in candidates:
        if path and Path(path).exists():
            return path
    return None

def _get_launch_kwargs():
    """
    Возвращает словарь аргументов для p.chromium.launch().
    В приоритете: системный Chrome/Chromium, затем channel="chrome", затем дефолт Playwright.
    """
    # Способ 1: executable_path к найденному браузеру
    exe = _find_system_browser()
    if exe:
        return {"executable_path": exe, "headless": True}
    
    # Способ 2: channel="chrome" — использует системный Google Chrome
    # Работает даже без установленного Playwright Chromium
    try:
        return {"channel": "chrome", "headless": True}
    except:
        pass
    
    # Способ 3: дефолт Playwright (требует playwright install chromium)
    return {"headless": True}

# === ПРОВЕРКА PLAYWRIGHT ===
HAS_PLAYWRIGHT = False
HAS_BROWSER = False
_playwright_error = ""
_browser_launch_kwargs = {}

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    _playwright_error = "Playwright не установлен. Выполни: pip install playwright && playwright install chromium"

if HAS_PLAYWRIGHT:
    try:
        _browser_launch_kwargs = _get_launch_kwargs()
        with sync_playwright() as p:
            browser = p.chromium.launch(**_browser_launch_kwargs)
            browser.close()
            HAS_BROWSER = True
    except Exception as e:
        # Пробуем channel="chrome" если ещё не пробовали
        if _browser_launch_kwargs.get("channel") != "chrome":
            try:
                _browser_launch_kwargs = {"channel": "chrome", "headless": True}
                with sync_playwright() as p:
                    browser = p.chromium.launch(**_browser_launch_kwargs)
                    browser.close()
                    HAS_BROWSER = True
            except:
                pass
        
        if not HAS_BROWSER:
            found_exe = _find_system_browser()
            if found_exe:
                _playwright_error = (
                    f"Браузер найден ({found_exe}), но не запустился.\n"
                    f"Детали: {e}"
                )
            else:
                _playwright_error = (
                    f"Chromium не найден.\n"
                    f"Варианты:\n"
                    f"  1. Установи Google Chrome: https://www.google.com/chrome/\n"
                    f"  2. Или выполни: $env:NODE_TLS_REJECT_UNAUTHORIZED=0; playwright install chromium\n"
                    f"Детали: {e}"
                )


def _run_sync(func):
    """Запуск синхронной функции в отдельном потоке, чтобы не блокировать event loop."""
    result = []

    def _t():
        try:
            result.append(func())
        except Exception as e:
            result.append(f"Error: {e}")

    t = threading.Thread(target=_t)
    t.start()
    t.join(timeout=PAGE_TIMEOUT / 1000 + 10)
    return result[0] if result else "Timeout"


# === ИНСТРУМЕНТЫ ===

@tools.tool
def browser_screenshot(url: str, full_page: bool = True, selector: str = "") -> str:
    """
    Делает скриншот веб-страницы.
    url — адрес страницы.
    full_page — если True (по умолчанию), скриншот всей страницы. Если False — только видимая область.
    selector — CSS-селектор для скриншота конкретного элемента (опционально).
    Возвращает путь к сохранённому PNG.
    """
    if not HAS_PLAYWRIGHT or not HAS_BROWSER:
        return f"[Ошибка] {_playwright_error}"

    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch(**_browser_launch_kwargs)
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            try:
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="networkidle")
                page.wait_for_timeout(1000)  # доп. ожидание для анимаций

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                domain = re.sub(r'[^a-zA-Z0-9]', '_', url.split("//")[-1].split("/")[0])[:30]
                filename = f"{domain}_{ts}.png"
                filepath = _SCREENSHOTS_DIR / filename

                if selector:
                    element = page.locator(selector).first
                    element.screenshot(path=str(filepath))
                else:
                    page.screenshot(path=str(filepath), full_page=full_page)

                return f"📸 Скриншот сохранён: {filepath}\nURL: {url}\nРазмер: {filepath.stat().st_size // 1024} КБ"
            except Exception as e:
                return f"[Ошибка скриншота] {url}: {e}"
            finally:
                browser.close()

    return _run_sync(_do)


@tools.tool
def browser_get_text(url: str, selector: str = "", wait_for: str = "") -> str:
    """
    Извлекает текст с веб-страницы (с JavaScript-рендерингом).
    url — адрес страницы.
    selector — CSS-селектор для извлечения конкретного элемента (опционально, по умолчанию — весь body).
    wait_for — ждать появления элемента перед извлечением (опционально).
    Возвращает текст, до 5000 символов.
    """
    if not HAS_PLAYWRIGHT or not HAS_BROWSER:
        return f"[Ошибка] {_playwright_error}"

    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch(**_browser_launch_kwargs)
            page = browser.new_page()
            try:
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="networkidle")

                if wait_for:
                    page.wait_for_selector(wait_for, timeout=PAGE_TIMEOUT)

                if selector:
                    elements = page.locator(selector).all()
                    if not elements:
                        return f"Элемент '{selector}' не найден на {url}"
                    texts = [el.inner_text().strip() for el in elements if el.inner_text().strip()]
                    result = "\n---\n".join(texts)
                else:
                    result = page.locator("body").inner_text().strip()

                # Очистка
                result = re.sub(r'\n{3,}', '\n\n', result)
                result = re.sub(r'[ \t]{3,}', '  ', result)

                if len(result) > 5000:
                    result = result[:5000] + "\n\n... [обрезано, всего символов: {}]".format(
                        len(page.locator("body").inner_text().strip()))

                return f"[Текст страницы {url}]:\n\n{result}"

            except Exception as e:
                return f"[Ошибка извлечения текста] {url}: {e}"
            finally:
                browser.close()

    return _run_sync(_do)


@tools.tool
def browser_fill_form(url: str, fields_json: str, submit_selector: str = "") -> str:
    """
    Заполняет поля формы на веб-странице.
    url — адрес страницы с формой.
    fields_json — JSON-строка вида {"селектор": "значение", ...}. Пример: '{"#name": "Иван", "#email": "ivan@mail.ru"}'.
    submit_selector — CSS-селектор кнопки отправки (опционально). Если указан — нажмёт после заполнения.
    Возвращает скриншот результата.
    """
    if not HAS_PLAYWRIGHT or not HAS_BROWSER:
        return f"[Ошибка] {_playwright_error}"

    try:
        fields = json.loads(fields_json)
    except json.JSONDecodeError:
        return "[Ошибка] Невалидный JSON. Пример: '{\"#name\": \"Иван\", \"#email\": \"ivan@mail.ru\"}'"

    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch(**_browser_launch_kwargs)
            page = browser.new_page()
            try:
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="networkidle")

                filled = []
                for sel, val in fields.items():
                    try:
                        page.fill(sel, str(val))
                        filled.append(f"  ✓ {sel} = {val}")
                    except Exception as e:
                        filled.append(f"  ✗ {sel}: {e}")

                if submit_selector:
                    page.click(submit_selector)
                    page.wait_for_timeout(2000)
                    filled.append(f"  ▶ Нажата кнопка: {submit_selector}")

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = _SCREENSHOTS_DIR / f"form_{ts}.png"
                page.screenshot(path=str(filepath), full_page=True)

                return (
                    f"📝 Форма заполнена: {url}\n"
                    + "\n".join(filled)
                    + f"\n📸 Результат: {filepath}"
                )
            except Exception as e:
                return f"[Ошибка заполнения формы] {url}: {e}"
            finally:
                browser.close()

    return _run_sync(_do)


@tools.tool
def browser_click(url: str, selector: str, wait_after: int = 2000) -> str:
    """
    Кликает по элементу на странице и возвращает скриншот результата.
    url — адрес страницы.
    selector — CSS-селектор элемента для клика (например, 'button.submit', 'a.more').
    wait_after — ждать мс после клика (по умолчанию 2000).
    """
    if not HAS_PLAYWRIGHT or not HAS_BROWSER:
        return f"[Ошибка] {_playwright_error}"

    def _do():
        with sync_playwright() as p:
            browser = p.chromium.launch(**_browser_launch_kwargs)
            page = browser.new_page()
            try:
                page.goto(url, timeout=PAGE_TIMEOUT, wait_until="networkidle")

                page.click(selector)
                page.wait_for_timeout(wait_after)

                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                filepath = _SCREENSHOTS_DIR / f"click_{ts}.png"
                page.screenshot(path=str(filepath), full_page=True)
                return f"🖱️ Клик по '{selector}' → {filepath}"
            except Exception as e:
                return f"[Ошибка клика] {url} → '{selector}': {e}"
            finally:
                browser.close()

    return _run_sync(_do)


@tools.tool
def browser_status() -> str:
    """
    Проверяет состояние браузера: доступен ли Playwright, найден ли браузер, как запускается.
    """
    status_lines = []
    status_lines.append(f"Playwright установлен: {'✅' if HAS_PLAYWRIGHT else '❌'}")
    status_lines.append(f"Браузер доступен: {'✅' if HAS_BROWSER else '❌'}")
    
    if HAS_BROWSER:
        kw = _browser_launch_kwargs.copy()
        if "headless" in kw:
            del kw["headless"]
        status_lines.append(f"Способ запуска: {kw}")
    
    exe = _find_system_browser()
    if exe:
        status_lines.append(f"Системный браузер: {exe}")
    
    if _playwright_error:
        status_lines.append(f"Ошибка: {_playwright_error}")
    
    return "\n".join(status_lines)
