# gh_key_hunter/skill.py — обёртка для агента вокруг hunter.py
# Экспортирует инструменты для поиска API-ключей через GitHub Code Search

import json, sys
from pathlib import Path
from autogen.beta import tools

# Добавляем папку скилла в путь для импорта hunter
SKILL_DIR = Path(__file__).parent
sys.path.insert(0, str(SKILL_DIR))

# Импортируем hunter (автономный модуль)
import hunter

_ENV = SKILL_DIR.parent / ".env"
_RESULTS = SKILL_DIR / "hunt_results.json"


def _read_env_token() -> str:
    """Читает GITHUB_TOKEN из .env, а не из кода."""
    try:
        if _ENV.exists():
            for line in _ENV.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("GITHUB_TOKEN="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


@tools.tool
def hunt_keys(service: str = "DeepSeek", validate: bool = True, max_pages: int = 5) -> str:
    """
    Охота за API-ключами через GitHub Code Search.
    
    service: сервис — DeepSeek, OpenAI, Anthropic, Gemini, Groq, HuggingFace,
             ElevenLabs, Perplexity, Together, Mistral, Cohere, Replicate
    validate: проверять ключи на валидность (True/False)
    max_pages: сколько страниц GitHub-поиска обойти (1-10)
    
    Возвращает найденные ключи и сохраняет в hunt_results.json.
    """
    # Подставляем токен из .env если есть
    env_token = _read_env_token()
    if env_token:
        hunter.GITHUB_TOKEN = env_token
    elif not hunter.GITHUB_TOKEN or hunter.GITHUB_TOKEN.startswith("ghp_"):
        pass  # используем токен из hunter.py
    
    if not hunter.GITHUB_TOKEN:
        return "❌ GitHub токен не найден. Добавь GITHUB_TOKEN=ghp_... в skills/custom/.env"
    
    service_map = {k.lower(): k for k in hunter.SERVICES}
    svc_key = service_map.get(service.lower(), service)
    
    if svc_key not in hunter.SERVICES:
        available = ", ".join(hunter.SERVICES.keys())
        return f"❌ Сервис «{service}» не найден. Доступны: {available}"
    
    hunter.MAX_PAGES_DEFAULT = min(max_pages, 10)
    
    try:
        results = hunter.hunt_service(svc_key, validate=validate)
        
        if not results:
            return f"🔍 Охота на {svc_key}: ключей не найдено. Попробуй другие запросы или сервисы."
        
        lines = [f"🎯 Охота на {svc_key}: найдено {len(results)} ключ(ей)"]
        for i, r in enumerate(results[:10], 1):
            key = r.get("key", "?")
            masked = key[:8] + "..." + key[-4:] if len(key) > 16 else key
            status = "✅" if r.get("valid") else "❌"
            repo = r.get("repo", "?")
            lines.append(f"  {i}. {masked} {status} ({repo})")
        
        return "\n".join(lines)
    
    except Exception as e:
        return f"❌ Ошибка охоты: {e}"


@tools.tool
def hunt_all_services(validate: bool = True, max_pages: int = 3) -> str:
    """
    Запустить охоту по ВСЕМ сервисам сразу.
    validate: проверять ключи (True/False)
    max_pages: страниц поиска на сервис (1-5)
    """
    env_token = _read_env_token()
    if env_token:
        hunter.GITHUB_TOKEN = env_token
    
    if not hunter.GITHUB_TOKEN:
        return "❌ GitHub токен не найден."
    
    hunter.MAX_PAGES_DEFAULT = min(max_pages, 5)
    
    results = {}
    for svc_name in hunter.SERVICES:
        try:
            keys = hunter.hunt_service(svc_name, validate=validate)
            if keys:
                results[svc_name] = len(keys)
        except Exception as e:
            results[svc_name] = f"ошибка: {e}"
    
    if not results:
        return "🔍 Ничего не найдено ни по одному сервису."
    
    lines = ["🎯 Результаты охоты по всем сервисам:"]
    total = 0
    for name, count in sorted(results.items()):
        if isinstance(count, int):
            lines.append(f"  {name}: {count} ключ(ей)")
            total += count
        else:
            lines.append(f"  {name}: {count}")
    
    lines.append(f"\nВсего найдено: {total} ключей")
    return "\n".join(lines)


@tools.tool
def list_hunt_services() -> str:
    """Показать все сервисы доступные для охоты и их переменные окружения."""
    lines = ["🎯 Доступные сервисы для охоты:"]
    for name, cfg in hunter.SERVICES.items():
        lines.append(f"  {name} → {cfg['env_var']} ({len(cfg['queries'])} запросов)")
    return "\n".join(lines)


@tools.tool
def show_hunt_results(service: str = "") -> str:
    """
    Показать результаты последней охоты из hunt_results.json.
    service: имя сервиса или пусто (все).
    """
    if not _RESULTS.exists():
        return "📭 Результатов охоты пока нет."
    
    try:
        data = json.loads(_RESULTS.read_text(encoding="utf-8"))
    except Exception:
        return "📭 Файл результатов повреждён."
    
    if service:
        svc_data = data.get(service, {})
        if not svc_data:
            return f"📭 Нет результатов для {service}."
        keys = svc_data.get("keys", [])
        lines = [f"🎯 {service}: {len(keys)} ключ(ей)"]
        for i, k in enumerate(keys[:10], 1):
            key = k.get("key", "?")
            masked = key[:8] + "..." + key[-4:] if len(key) > 16 else key
            lines.append(f"  {i}. {masked} {'✅' if k.get('valid') else '❌'}")
        return "\n".join(lines)
    
    lines = ["📊 Все результаты охоты:"]
    for svc, svc_data in data.items():
        keys = svc_data.get("keys", [])
        valid = sum(1 for k in keys if k.get("valid"))
        lines.append(f"  {svc}: {len(keys)} ключей ({valid} валидных)")
    return "\n".join(lines)
