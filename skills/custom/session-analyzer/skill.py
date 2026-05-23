# session-analyzer/skill.py
# Анализирует сессию диалога: ключевые решения, факты, настроение

import os, sys, json
from pathlib import Path
from datetime import datetime, date

from autogen.beta import tools

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from aura_core import AuraDatabase, CONFIG


@tools.tool
def analyze_today_session() -> str:
    """
    Анализирует сегодняшнюю сессию диалога.
    Извлекает: ключевые решения, факты, настроение, планы, темы.
    """
    try:
        db = AuraDatabase()
        today = date.today().isoformat()
        summary = db.get_today_summary(today)

        if not summary:
            return f"За сегодня ({today}) пока нет сохранённой истории. Давай сначала пообщаемся!"

        lines = [f"Анализ сессии за {today}:\n"]

        if summary.get("summary"):
            lines.append(f"Конспект:\n  {summary['summary']}\n")

        if summary.get("key_topics"):
            lines.append(f"Темы: {summary['key_topics']}")

        if summary.get("key_decisions"):
            lines.append(f"\nКлючевые решения:\n  {summary['key_decisions']}")

        if summary.get("key_facts"):
            try:
                facts = json.loads(summary["key_facts"])
                if facts:
                    lines.append(f"\nНовые факты ({len(facts)}):")
                    for f in facts:
                        lines.append(f"  - {f}")
            except json.JSONDecodeError:
                lines.append(f"\nФакты: {summary['key_facts'][:200]}")

        lines.append(f"\nСообщений в сессии: {summary.get('message_count', 0)}")

        # Статистика по тегам
        tags_row = db.conn.execute(
            "SELECT tag FROM memory_tags WHERE memory_id = ?",
            (summary["id"],)
        ).fetchall()
        if tags_row:
            tags = [t["tag"] for t in tags_row]
            lines.append(f"Теги: {', '.join(tags)}")

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка анализа: {e}"


@tools.tool
def get_session_stats(days: int = 7) -> str:
    """
    Статистика по сессиям за последние N дней:
    количество сообщений, тем, фактов, решений.
    """
    try:
        db = AuraDatabase()
        summaries = db.get_recent_summaries(days)

        if not summaries:
            return f"За последние {days} дней нет сохранённых сессий."

        total_msgs = sum(s.get("message_count", 0) for s in summaries)
        all_topics = set()
        all_tags = []

        for s in summaries:
            if s.get("key_topics"):
                for t in s["key_topics"].split(","):
                    all_topics.add(t.strip().lower())

        # Собираем теги
        for s in summaries:
            tags = db.conn.execute(
                "SELECT tag FROM memory_tags WHERE memory_id = ?",
                (s["id"],)
            ).fetchall()
            all_tags.extend(t["tag"] for t in tags)

        lines = [
            f"Статистика за {days} дней:",
            f"  Сессий: {len(summaries)}",
            f"  Сообщений: {total_msgs}",
            f"  Уникальных тем: {len(all_topics)}",
            f"  Тегов: {len(all_tags)}",
        ]

        if all_topics:
            lines.append(f"\nВсе темы: {', '.join(sorted(all_topics)[:15])}")

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка: {e}"
