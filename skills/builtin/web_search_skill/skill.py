# web_search_skill/skill.py — Встроенный скилл интернет-поиска

from datetime import datetime

from autogen.beta import tools


@tools.tool
def get_current_timestamp() -> str:
    """Возвращает текущую метку времени."""
    return datetime.now().isoformat()

@tools.tool
def format_search_query(topic: str, limit: int = 5) -> str:
    """Форматирует поисковый запрос. limit — количество результатов."""
    return f"Поиск: {topic} (лимит: {limit})"
