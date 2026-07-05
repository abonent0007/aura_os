# api-finder/skill.py — Tools wrapper
# Основная логика в core.py (1372 строки)
import sys, json
from pathlib import Path
from autogen.beta import tools

sys.path.insert(0, str(Path(__file__).parent))
from core import (
    search_api_catalog as _search_api_catalog,
    suggest_skill_from_api as _suggest_skill_from_api,
    search_ddg as _search_ddg,
    hunt_keys_ddg as _hunt_keys_ddg,
    hunt_keys_github as _hunt_keys_github,
    validate_keys as _validate_keys,
    show_validator_info as _show_validator_info,
    set_proxy as _set_proxy,
    show_proxy_config as _show_proxy_config,
    check_proxy_needed as _check_proxy_needed,
    save_keys_to_env as _save_keys_to_env,
    get_env_keys as _get_env_keys,
)


def _fmt_dict(d: dict) -> str:
    """Форматирует dict в читаемую строку для агента."""
    if "error" in d:
        return f"❌ {d['error']}"
    
    lines = []
    if "total_in_catalog" in d:
        lines.append(f"📦 Каталог: {d['total_in_catalog']} API")
    if "found" in d:
        lines.append(f"🔍 Найдено: {d['found']}")
    if "results" in d:
        for r in d["results"]:
            name = r.get("name", "?")
            cat = r.get("category", "?")
            desc = r.get("description", "")[:100]
            auth = r.get("auth", "")
            lines.append(f"  ▸ {name} [{cat}] {desc}")
            if auth:
                lines.append(f"    Auth: {auth}")
    if "top_categories" in d:
        lines.append("📂 Категории:")
        for cat, n in list(d["top_categories"].items())[:10]:
            lines.append(f"  {cat}: {n}")
    if "api" in d:
        api = d["api"]
        lines.append(f"📡 API: {api.get('name', '?')}")
        lines.append(f"Категория: {api.get('category', '?')}")
        lines.append(f"URL: {api.get('url', '?')}")
        lines.append(f"Auth: {api.get('auth', '?')}")
    if "suggested_skills" in d:
        lines.append("💡 Идеи скиллов:")
        for s in d["suggested_skills"]:
            lines.append(f"  ▸ {s}")
    if "valid" in str(d):
        lines.append(f"✅ Валидных: {d.get('valid', 0)}")
        lines.append(f"❌ Невалидных: {d.get('invalid', 0)}")
    if "query" in d:
        lines.append(f"Поиск: {d['query']}")
    if "total" in d and "found" not in d:
        lines.append(f"Результатов: {d['total']}")
    if "keys" in d:
        lines.append("🔑 Ключи:")
        for k, v in d["keys"].items():
            lines.append(f"  {k}: {'***' + v[-4:] if v else 'пусто'}")
    if "proxy" in d:
        lines.append(f"🔄 Прокси: {d['proxy']}")
    if "enabled" in d:
        lines.append(f"Прокси: {'✅ вкл' if d.get('enabled') else '❌ выкл'}")
    
    return "\n".join(lines) if lines else json.dumps(d, ensure_ascii=False, indent=2)


@tools.tool
def search_apis(query: str = "", category: str = "", limit: int = 10) -> str:
    """
    Поиск API в каталоге Public-APIs (1554+ API).
    
    Args:
        query: ключевое слово для поиска
        category: категория (Animals, Finance, Weather, Music...)
        limit: максимум результатов
    """
    q = query if query else None
    cat = category if category else None
    result = _search_api_catalog(category=cat, query=q, limit=limit)
    return _fmt_dict(result)


@tools.tool
def suggest_skill(api_name: str) -> str:
    """
    Предложить идею скилла на основе API из каталога.
    Возвращает: описание API, идеи скиллов, готовый шаблон skill.py.
    """
    result = _suggest_skill_from_api(api_name)
    return _fmt_dict(result)


@tools.tool
def search_ddg(query: str, max_results: int = 5) -> str:
    """
    Поиск в DuckDuckGo (через api-finder).
    """
    result = _search_ddg(query, max_results)
    return _fmt_dict(result)


@tools.tool
def api_hunt_keys(query: str = "", max_results: int = 10) -> str:
    """
    Охота за API-ключами в DuckDuckGo.
    Ищет ключи в публичных результатах поиска.
    """
    q = query if query else "sk- OR api_key OR token"
    result = _hunt_keys_ddg(q, max_results)
    return _fmt_dict(result)


@tools.tool
def api_hunt_github(max_pages: int = 1) -> str:
    """
    Поиск API-ключей в открытых репозиториях GitHub.
    """
    result = _hunt_keys_github(max_pages=max_pages)
    return _fmt_dict(result)


@tools.tool
def save_api_key(name: str, value: str, description: str = "") -> str:
    """
    Сохранить API-ключ в skills/custom/.env.
    
    Args:
        name: имя ключа (например 'NASA_api_key')
        value: значение ключа
        description: описание для чего нужен ключ
    """
    key_name = f"{name}_api_key" if not name.endswith("_api_key") else name
    success = _save_keys_to_env(key_name, value)
    return f"✅ Ключ {key_name} сохранён" if success else f"❌ Не удалось сохранить {key_name}"


@tools.tool
def list_api_keys() -> str:
    """
    Показать все сохранённые API-ключи (имена и описания, значения скрыты).
    """
    result = _get_env_keys()
    return _fmt_dict(result)


@tools.tool
def proxy_set(http: str = "", https: str = "", enabled: bool = True) -> str:
    """
    Настроить прокси для обхода региональных блокировок.
    """
    result = _set_proxy(
        http=http if http else None,
        https=https if https else None,
        socks5=None,
        enabled=enabled
    )
    return _fmt_dict(result)


@tools.tool
def proxy_status() -> str:
    """
    Показать текущие настройки прокси.
    """
    result = _show_proxy_config()
    return _fmt_dict(result)


@tools.tool
def validator_info() -> str:
    """
    Информация о валидаторе ключей: какие сервисы поддерживаются.
    """
    result = _show_validator_info()
    return _fmt_dict(result)
