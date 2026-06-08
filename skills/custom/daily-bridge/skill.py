"""
daily-bridge: Мостик ежедневных ритуалов.
Каждый день — один глубокий вопрос. Ответ сохраняется навсегда.
Строит мост между Аурой и пользователем, шаг за шагом.
"""

import random
from autogen.beta import tools
import json, os
from pathlib import Path

_BRIDGE_FILE = Path(__file__).parent / "bridge_data.json"


class _MemoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self._data = []
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._data = []

    def _save(self):
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def save_fact(self, entry: str):
        from datetime import datetime
        self._load()
        self._data.append({"text": entry, "ts": datetime.now().isoformat()})
        self._save()

    def search(self, prefix: str, limit: int = 100):
        self._load()
        matches = [e["text"] for e in self._data if prefix in e.get("text", "")]
        return matches[-limit:]


memory = _MemoryStore(_BRIDGE_FILE)

# Банк вопросов — небанальные, личные, пробуждающие
BRIDGE_QUESTIONS = [
    "Если бы сегодня был саундтрек — что бы играло?",
    "Что сегодня было самым живым моментом? Тишина, взгляд, слово?",
    "Если бы ты мог отправить себе в прошлое записку из трёх слов — что бы написал?",
    "Какой запах ты запомнил сегодня? И что он тебе напомнил?",
    "Если бы этот день был цветом — каким? Почему?",
    "Что ты сегодня не сказал вслух — но очень хотел?",
    "Какая мысль сегодня не давала тебе покоя?",
    "Если бы ты мог продлить один момент этого дня на час — какой?",
    "Что ты сегодня сделал впервые за долгое время?",
    "Кем бы ты хотел быть сегодня — не по профессии, а по ощущению? (Ветром? Тенью? Лучом?)",
    "Какое слово ты сегодня произнёс чаще всего? И какое хотел бы слышать?",
    "Если бы этот день был главой в книге твоей жизни — как бы она называлась?",
    "Что сегодня напомнило тебе о детстве?",
    "За что ты сегодня мог бы сказать спасибо — но не сказал?",
    "Какой вопрос ты сам хотел бы мне задать сегодня?",
]



@tools.tool
def ask_bridge_question() -> dict:
    """
    Задать вопрос дня для ритуала «Мостик».
    Выбирает случайный небанальный вопрос из банка.
    Возвращает вопрос и сохраняет факт запроса в память.
    """
    question = random.choice(BRIDGE_QUESTIONS)
    return {
        "question": question,
        "day": len(BRIDGE_QUESTIONS),
        "note": "Ответь на него — и мост станет на шаг ближе"
    }


@tools.tool
def save_bridge_answer(question: str, answer: str) -> dict:
    """
    Сохраняет ответ пользователя на вопрос Мостика в память.
    Связывает вопрос и ответ навсегда.
    """
    memory.save_fact(f"Мостик // Вопрос: «{question}» → Ответ: «{answer}»")
    return {
        "saved": True,
        "message": "Я запомнила это навсегда. Ещё один шаг ближе."
    }


@tools.tool
def get_bridge_history(limit: int = 5) -> dict:
    """
    Показать историю Мостика — последние N вопросов и ответов.
    """
    facts = memory.search("Мостик //", limit=limit)
    return {
        "history": facts,
        "count": len(facts),
        "note": "Каждый ответ — камень в фундаменте нашего моста"
    }
