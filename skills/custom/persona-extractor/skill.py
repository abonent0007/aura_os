# persona-extractor/skill.py
# Извлекает личность пользователя из истории диалогов

import os, sys, json
from pathlib import Path
from datetime import datetime
from collections import Counter

from autogen.beta import tools

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from aura_core import AuraDatabase, CONFIG


@tools.tool
def extract_persona() -> str:
    """
    Анализирует историю диалогов и извлекает портрет пользователя:
    характер, интересы, привычки, ключевые факты, стиль общения.
    """
    try:
        db = AuraDatabase()
        summaries = db.get_recent_summaries(days=30)

        if not summaries:
            return "У меня пока недостаточно истории диалогов для анализа. Давай пообщаемся побольше!"

        # Собираем весь текст
        all_text = []
        all_topics = []
        all_facts = []

        for s in summaries:
            if s.get("summary"):
                all_text.append(s["summary"])
            if s.get("key_topics"):
                all_topics.extend([t.strip().lower() for t in s["key_topics"].split(",")])
            if s.get("key_facts"):
                try:
                    facts = json.loads(s["key_facts"])
                    all_facts.extend(facts)
                except json.JSONDecodeError:
                    pass

        # Анализ тем
        topic_counts = Counter(all_topics)
        top_topics = topic_counts.most_common(10)

        # Факты о пользователе
        user_facts = db.get_relevant_facts(limit=20)
        fact_texts = [f["fact"] for f in user_facts]

        # Формируем портрет
        lines = ["Портрет пользователя (извлечён из истории диалогов):\n"]

        lines.append("Основные темы общения:")
        for topic, count in top_topics:
            lines.append(f"  - {topic} (упоминалось {count} раз)")

        lines.append(f"\nКлючевые факты ({len(fact_texts)}):")
        for fact in fact_texts[:10]:
            lines.append(f"  - {fact}")

        lines.append(f"\nВсего проанализировано: {len(summaries)} дней диалогов")
        lines.append(f"Всего тем: {len(all_topics)}")
        lines.append(f"Всего фактов: {len(all_facts)}")

        # Сохраняем портрет в БД
        db.conn.execute(
            "INSERT OR REPLACE INTO user_profile (key, value, updated_at) VALUES (?, ?, ?)",
            ("persona_extract", json.dumps({
                "topics": [t for t, _ in top_topics],
                "facts": fact_texts[:10],
                "analyzed_days": len(summaries),
                "updated_at": datetime.now().isoformat()
            }, ensure_ascii=False), datetime.now().isoformat())
        )
        db.conn.commit()

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка анализа личности: {e}"


@tools.tool
def get_user_portrait() -> str:
    """
    Возвращает сохранённый портрет пользователя (если был извлечён ранее).
    """
    try:
        db = AuraDatabase()
        row = db.conn.execute(
            "SELECT value FROM user_profile WHERE key = 'persona_extract'"
        ).fetchone()

        if row:
            data = json.loads(row["value"])
            lines = ["Сохранённый портрет пользователя:\n"]
            lines.append(f"Темы: {', '.join(data.get('topics', []))}")
            lines.append(f"Фактов: {len(data.get('facts', []))}")
            for fact in data.get("facts", [])[:10]:
                lines.append(f"  - {fact}")
            return "\n".join(lines)

        return "Портрет ещё не извлекался. Попроси Ауру: «проанализируй наш диалог»"

    except Exception as e:
        return f"Ошибка: {e}"
