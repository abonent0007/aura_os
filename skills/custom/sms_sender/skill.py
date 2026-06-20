# sms_sender/skill.py — Отправка SMS через sms.ru API
# v1.1 — ключ читается из skills/custom/.env (централизованное хранилище)

import json, threading, asyncio, re
from pathlib import Path
from autogen.beta import tools

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

_DATA = Path(__file__).parent / "data.json"
_ENV = Path(__file__).parent.parent / ".env"  # skills/custom/.env

# ── Работа с .env ────────────────────────────────────────────────────────
def _get_env_key(key_name: str) -> str:
    """Прочитать ключ из центрального .env."""
    if _ENV.exists():
        for line in _ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(key_name + "="):
                return line.split("=", 1)[1].split("#")[0].strip()
    return ""


def _load_config():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except:
            pass
    return {}


def _save_config(config):
    _DATA.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_config(key: str):
    cfg = _load_config()
    return cfg.get(key, "")


def _set_config(key: str, value: str):
    cfg = _load_config()
    cfg[key] = value
    _save_config(cfg)


# Инициализация с дефолтными значениями
_DEFAULTS = {
    "default_phone": "+79684520007"
}
cfg = _load_config()
updated = False
for k, v in _DEFAULTS.items():
    if k not in cfg:
        cfg[k] = v
        updated = True
if updated:
    _save_config(cfg)


def _http_get(url: str) -> str:
    if not HAS_HTTPX:
        return '{"status":"ERROR","status_text":"httpx not available"}'
    result = []
    def _run():
        loop = asyncio.new_event_loop()
        async def _get():
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(url, follow_redirects=True)
                return r.text
        try:
            result.append(loop.run_until_complete(_get()))
        finally:
            loop.close()
    t = threading.Thread(target=_run); t.start(); t.join(20)
    return result[0] if result else '{"status":"ERROR","status_text":"timeout"}'


def _format_phone(phone: str) -> str:
    """Очищает номер от лишних символов."""
    cleaned = re.sub(r'[\s\(\)\-+]', '', phone)
    if cleaned.startswith('7') and len(cleaned) == 11:
        return cleaned
    if cleaned.startswith('8') and len(cleaned) == 11:
        return '7' + cleaned[1:]
    return cleaned


@tools.tool
def send_sms(message: str, phone: str = "") -> str:
    """
    Отправить SMS через sms.ru. Если phone не указан — на номер по умолчанию Юрия.
    message: текст сообщения (макс. 70 символов, обрежется)
    phone: номер телефона (необязательно, по умолчанию номер Юрия)
    """
    # Читаем ключ сначала из .env, потом из data.json (для обратной совместимости)
    api_key = _get_env_key("sms_ru_api_key")
    if not api_key or api_key == "xxx":
        api_key = _get_config("api_key")
    if not api_key or api_key == "xxx":
        return "Ошибка: API-ключ sms.ru не настроен. Скажи: «Аура, сохрани ключ sms_ru_api_key = ТВОЙ_КЛЮЧ»"

    if not phone:
        phone = _get_config("default_phone")

    phone = _format_phone(phone)

    if len(message) > 70:
        message = message[:67] + "..."

    import urllib.parse
    encoded_msg = urllib.parse.quote(message)

    url = f"https://sms.ru/sms/send?api_id={api_key}&to={phone}&msg={encoded_msg}&json=1"

    response = _http_get(url)

    try:
        result = json.loads(response)
        if result.get("status") == "OK":
            sms_data = result.get("sms", {})
            phone_status = sms_data.get(phone, {})
            if phone_status.get("status") == "OK":
                return f"SMS отправлено на +{phone}: «{message}» (ID: {phone_status.get('sms_id', 'N/A')})"
            else:
                return f"Ошибка отправки на +{phone}: {phone_status.get('status_text', 'неизвестно')}"
        else:
            return f"Ошибка API: {result.get('status_text', 'неизвестно')}"
    except json.JSONDecodeError:
        return f"Не удалось разобрать ответ: {response[:200]}"


@tools.tool
def sms_balance() -> str:
    """Проверить баланс на sms.ru."""
    api_key = _get_env_key("sms_ru_api_key")
    if not api_key or api_key == "xxx":
        api_key = _get_config("api_key")
    if not api_key or api_key == "xxx":
        return "Ошибка: API-ключ sms.ru не настроен."

    url = f"https://sms.ru/my/balance?api_id={api_key}&json=1"
    response = _http_get(url)

    try:
        result = json.loads(response)
        if result.get("status") == "OK":
            balance = result.get("balance", "неизвестно")
            return f"Баланс sms.ru: {balance} руб."
        else:
            return f"Ошибка: {result.get('status_text', 'неизвестно')}"
    except json.JSONDecodeError:
        return f"Не удалось разобрать ответ: {response[:200]}"


@tools.tool
def sms_set_key(api_key: str) -> str:
    """
    Сохранить API-ключ sms.ru.
    api_key: ключ из личного кабинета sms.ru
    Сохраняется в центральный .env (skills/custom/.env).
    """
    key_name = "sms_ru_api_key"
    api_key = api_key.strip()

    # Сохраняем и в .env и в data.json для надёжности
    _set_config("api_key", api_key)

    env_path = _ENV
    lines = []
    found = False
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(key_name + "="):
                lines.append(f"{key_name}={api_key}  # API-ключ sms.ru для отправки SMS")
                found = True
            else:
                lines.append(line)
    if not found:
        if not env_path.exists():
            lines = [
                "# AURA OS — Единое хранилище API-ключей",
                "# Формат: ИМЯ_api_key=ЗНАЧЕНИЕ  # краткое описание",
                "",
            ]
        lines.append(f"{key_name}={api_key}  # API-ключ sms.ru для отправки SMS")

    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return f"✅ API-ключ sms.ru сохранён в .env (sms_ru_api_key)"


@tools.tool
def sms_set_default_phone(phone: str) -> str:
    """Установить номер телефона по умолчанию для SMS."""
    phone = _format_phone(phone)
    _set_config("default_phone", phone)
    return f"Номер по умолчанию: +{phone}"
