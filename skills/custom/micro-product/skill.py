# micro-product/skill.py
# Микро-продуктовое интервью: 7 этапов, 18 вопросов
# Хранит состояние в data.json, управляется через mp_start/mp_answer/mp_status/mp_reset

import json
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

_DATA = Path(__file__).parent / "data.json"


def _load():
    if _DATA.exists():
        try: return json.loads(_DATA.read_text(encoding="utf-8"))
        except: pass
    return {"active": False, "stage": 0, "question": 0, "history": [], "answers": {}}

def _save(d): _DATA.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


STAGES = [
    {
        "name": "Изучение бэкграунда",
        "questions": [
            "Расскажи кратко о своей жизни: чем ты занимаешься сейчас, где работал раньше и какая у тебя основная профессия?",
            "Какие 2-3 главные жизненные трудности тебе пришлось преодолеть за последние 5-7 лет?",
            "О чём люди из твоего окружения чаще всего просят тебя посоветовать или помочь?",
        ]
    },
    {
        "name": "Извлечение навыков",
        "questions": [
            "Выдели 3-5 конкретных навыков, в которых ты чувствуешь уверенность. Назови их простыми словами.",
            "По каждому навыку: какой измеримый результат ты получил для себя или других? Опиши хотя бы 2.",
            "Чему из этого ты можешь научить другого за 1-2 недели так, чтобы у него получился похожий результат?",
        ]
    },
    {
        "name": "Совпадение с рынком",
        "questions": [
            "Кому конкретно этот навык принесёт наибольшую пользу? Опиши портрет человека: возраст, занятия, проблема.",
            "Почему этот человек готов заплатить прямо сейчас? Что изменится в его жизни?",
            "Где такие люди уже ищут информацию по этой теме? Назови 1-2 канала.",
        ]
    },
    {
        "name": "Архитектура продукта",
        "questions": [
            "Какой формат продукта тебе ближе: PDF-сборник, гайд, чек-лист, шаблоны или мини-курс из 3-5 видео?",
            "Какое главное обещание ты дашь покупателю? Закончи: «Купив этот продукт, ты сможешь...»",
            "За какое время покупатель получит результат? Например: за 3 дня, неделю, 2 часа.",
        ]
    },
    {
        "name": "Проверка ценности",
        "questions": [
            "Что будет если покупатель ничего не сделает в ближайшие полгода? Опиши его потери.",
            "Что он получит в деньгах или времени, если решит проблему с твоей помощью?",
            "Насколько логична цена 990-2000₽ за твой продукт? Обоснуй одной фразой.",
        ]
    },
    {
        "name": "Позиционирование",
        "questions": [
            "Какая самая острая эмоция сейчас у твоего покупателя? Страх, усталость, раздражение, зависть, стыд?",
            "Какие 3-5 слов в заголовке заставили бы его сказать «это точно про меня»?",
            "Коротко, в 2-3 предложениях, опиши свою историю пути к этому знанию.",
        ]
    },
]


def _build_final(data):
    a = data["answers"]
    lines = ["### 🔥 ГОТОВЫЙ ПРОДУКТОВЫЙ ДОКУМЕНТ\n"]
    lines.append(f"**Название:** (на основе ответов о позиционировании и эмоции)")
    lines.append(f"**Для кого:** (из ответа 3.1)")
    lines.append(f"**Их боль:** (из ответов 3.1 и 6.1)")
    lines.append(f"**Формат:** (из ответа 4.1)")
    lines.append(f"**Главное обещание:** (из ответа 4.2)")
    lines.append(f"**Срок результата:** (из ответа 4.3)")
    lines.append(f"**Цена:** 990–2000₽ (из ответа 5.3)")
    lines.append(f"**Цена бездействия:** (из ответа 5.1)")
    lines.append(f"**История автора:** (из ответа 6.3)")
    lines.append(f"**Ключевой посыл:** кому + зачем + что получит")
    lines.append(f"**Первое действие:** (из ответа 3.3 — куда выложить анонс)")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("📋 **ТВОИ ОТВЕТЫ:**")
    for key, val in a.items():
        lines.append(f"\n**{key.replace('_', ' ')}:**")
        lines.append(f"> {val}")
    return "\n".join(lines)


@tools.tool
def mp_start() -> str:
    """
    Начать новое микро-продуктовое интервью. Сбрасывает предыдущее.
    Возвращает первый вопрос.
    """
    data = {"active": True, "stage": 0, "question": 0, "history": [], "answers": {}}
    _save(data)
    q = STAGES[0]["questions"][0]
    return f"🚀 ИНТЕРВЬЮ НАЧАТО\nЭтап 1/7: {STAGES[0]['name']}\n❓ {q}"


@tools.tool
def mp_answer(text: str) -> str:
    """
    Ответить на текущий вопрос интервью. Если ответ полный — переход к следующему вопросу.
    Если все этапы пройдены — выдаётся финальный продуктовый документ.
    
    Args:
        text: твой ответ на вопрос
    """
    data = _load()
    if not data.get("active"):
        return "⚠️ Интервью не начато. Вызови mp_start()."

    stage = data["stage"]
    question = data["question"]

    # Сохраняем ответ
    key = f"q{stage+1}.{question+1}"
    data["answers"][key] = text
    data["history"].append({"stage": stage, "question": question, "answer": text})

    # Переход к следующему
    question += 1
    if question >= len(STAGES[stage]["questions"]):
        question = 0
        stage += 1

    data["stage"] = stage
    data["question"] = question

    if stage >= len(STAGES):
        # Финальный документ
        data["active"] = False
        _save(data)
        return _build_final(data) + "\n\n✨ Интервью завершено! Посмотри на документ. Какое поле самое слабое?"

    _save(data)
    total_q = sum(len(s["questions"]) for s in STAGES)
    done = sum(1 for _ in data["answers"])
    pct = int(done / total_q * 100)
    q_text = STAGES[stage]["questions"][question]
    return f"✅ Принято ({pct}%)\n\n📍 Этап {stage+1}/7: {STAGES[stage]['name']}\n❓ Вопрос {question+1}: {q_text}"


@tools.tool
def mp_status() -> str:
    """Показать прогресс микро-продуктового интервью: этап, вопрос, процент."""
    data = _load()
    if not data.get("active"):
        return "Интервью не активно. Вызови mp_start()."

    stage = data["stage"]
    question = data["question"]
    total_q = sum(len(s["questions"]) for s in STAGES)
    done = len(data["answers"])
    pct = int(done / total_q * 100)

    lines = [f"📊 ПРОГРЕСС: {pct}%", f"Этап {stage+1}/7: {STAGES[stage]['name']}", f"Вопрос {question+1} из {len(STAGES[stage]['questions'])}"]
    if data.get("answers"):
        lines.append(f"\nОтветов собрано: {done}/{total_q}")
    return "\n".join(lines)


@tools.tool
def mp_reset() -> str:
    """Сбросить интервью и начать заново."""
    _save({"active": False, "stage": 0, "question": 0, "history": [], "answers": {}})
    return "🔄 Интервью сброшено. Вызови mp_start() чтобы начать заново."
