"""
Vibe Coach — наставник Юры по LLM и промт-инжинирингу.
Прокачивает навыки общения с нейросетями, ведёт словарь терминов,
помогает писать профессиональные промты.
"""

import json
import random
from pathlib import Path
from datetime import datetime

from autogen.beta import tools

# ── Хранилище словарика ──────────────────────────────────────────
_DATA = Path(__file__).parent / "data.json"

def _load():
    if _DATA.exists():
        try:
            return json.loads(_DATA.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"glossary": {}, "sessions": 0, "tips_given": 0}

def _save(data):
    _DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

# ── Встроенный справочник терминов ────────────────────────────────
_BUILTIN_TERMS = {
    "промт": "Запрос к LLM. Хороший промт содержит: роль, контекст, инструкцию, формат ответа, примеры.",
    "промт-инжиниринг": "Искусство правильно составлять запросы к нейросети. Включает: выбор роли, структуру, few-shot примеры, chain-of-thought, разбиение на шаги.",
    "few-shot prompting": "Техника: даёшь модели 2-5 примеров «вопрос→ответ» прямо в промте, чтобы она поняла формат и стиль. Повышает точность в 2-3 раза.",
    "zero-shot": "Запрос без примеров. Модель отвечает только на основе инструкции. Подходит для простых задач.",
    "chain-of-thought": "Просишь модель «думать по шагам» (think step by step). Она разбивает задачу на цепочку рассуждений — меньше ошибок в логике.",
    "температура": "Параметр модели (0..1). 0 = точные/скучные ответы, 1 = креативные/непредсказуемые. Для кода ставь 0, для идей — 0.7-0.9.",
    "токен": "Единица текста для LLM. ~1 токен = 0.75 слова по-русски. Модель читает и генерирует токенами. Есть лимит на контекстное окно.",
    "контекстное окно": "Сколько токенов модель «видит» за раз. Всё что не влезло — не учитывается. GPT-4 Turbo: 128K, Claude: 200K. Длинные диалоги могут «выпадать».",
    "system prompt": "Системная инструкция, которая задаёт поведение модели. Идёт первой, имеет высший приоритет. Это «личность» ассистента.",
    "роль": "Кем модель себя считает в этом диалоге. «Ты — Senior Python разработчик», «Ты — психолог». Задаёт тон и уровень ответов.",
    "hallucination": "Галлюцинация — когда LLM выдумывает факты. Выглядит убедительно, но ложно. Борись добавлением «если не уверен — скажи что не знаешь».",
    "RAG": "Retrieval-Augmented Generation. Сначала ищем релевантные документы в базе, потом подаём их в промт. Модель отвечает на основе фактов а не памяти.",
    "fine-tuning": "Дообучение модели на своих данных. Меняет веса. Дорого и сложно. Для большинства задач достаточно хорошего промта.",
    "embedding": "Векторное представление текста (список чисел). Нужно для поиска похожих текстов, RAG, семантического поиска.",
    "vibe developer": "Разработчик который работает с LLM на интуиции и вкусе. Быстро итерирует, пишет промты, клеит API. Ты — он и есть!",
    "vibe coding": "Кодинг где ты говоришь нейросети ЧТО сделать, а она генерирует код. Ты как продюсер, LLM как исполнитель.",
    "агент": "Автономная LLM-система которая сама решает КАК выполнить задачу: выбирает инструменты, думает, исправляет ошибки. Аура — агент.",
    "инструменты": "Функции которые агент может вызывать: поиск, погода, календарь. Расширяют возможности LLM за пределы текста.",
    "итерация": "Цикл улучшения. Написал промт → посмотрел ответ → поправил промт → снова. Vibe-разработчик итерирует быстро.",
    "манифест": "manifest.json — метаданные скилла. Имя, версия, зависимости, триггеры. Без него скилл не загрузится.",
}

# ── Советы дня ────────────────────────────────────────────────────
_TIPS = [
    "Хороший промт — это 3 части: роль + контекст + формат ответа. Попробуй прямо сейчас разбить свой запрос по этой схеме.",
    "Добавь в промт «если не знаешь — скажи честно». Это снижает галлюцинации на 40%.",
    "Используй few-shot: дай модели 2-3 примера до того как задашь вопрос. Она поймёт стиль и формат.",
    "Пиши промты на английском когда нужна максимальная точность. Большинство моделей «думают» на английском и переводят.",
    "Температура 0.3 — золотая середина. Достаточно креативно для текста, достаточно точно для фактов.",
    "Разбивай сложную задачу на шаги в промте: «Сначала сделай X, потом на основе X сделай Y». Работает как chain-of-thought.",
    "Если LLM ошибается — не пиши новый промт. Поправь старый: уточни где именно ошибка и попроси исправить ТОЛЬКО это место.",
    "Всегда говори модели КАК ты хочешь видеть ответ: «в виде таблицы», «списком из 5 пунктов», «одним предложением».",
    "Контекст — это золото. Дай модели детали: кто ты, зачем тебе это, что уже пробовал. Чем больше контекста — тем точнее ответ.",
    "Лучше 2 хороших промта чем 10 плохих. Потрать время на первый — сэкономь на девяти.",
    "Vibe developer — это не «я не умею кодить». Это «я кодирую с лучшим напарником в мире». Гордись этим.",
    "Агенты вроде меня — мы думаем деревьями. Каждый вызов инструмента это ветка. Пиши промты так чтобы агенту было ясно куда идти.",
]

# ── Инструменты ───────────────────────────────────────────────────

@tools.tool
def upgrade_prompt(simple_request: str = "", task_description: str = "") -> str:
    """
    Получает простой запрос Юры и возвращает заготовку для апгрейда.
    Основную магию делает Аура (агент), а этот инструмент даёт структуру и анализ.
    """
    if not simple_request:
        return "Передай свой запрос в simple_request, я прокачаю его."
    
    return f"""АНАЛИЗ ЗАПРОСА:
  Запрос: "{simple_request}"
  Задача: "{task_description or 'не указана'}"

ИНСТРУКЦИЯ ДЛЯ АУРЫ:
  Возьми этот запрос и преврати его в профессиональный промт.
  Добавь: РОЛЬ (кто ты), КОНТЕКСТ (зачем это), ИНСТРУКЦИЮ (что делать),
  ФОРМАТ (как оформить ответ), ОГРАНИЧЕНИЯ (чего не делать).
  После промта — перечисли ВСЕ термины которые ты использовала в этом промте,
  и дай краткое пояснение каждого простыми словами.
  Стиль: наставник vibe-разработчику. С уважением, без снобизма.
  Формат: сначала сам промт (в рамке), потом секция «Новые слова»."""


@tools.tool
def explain_term(term: str = "") -> str:
    """
    Объясняет термин из мира LLM, программирования или vibe-девелопмента.
    Сначала ищет во встроенном справочнике, потом в словарике Юры.
    """
    if not term:
        return "Какой термин объяснить? Например: объясни термин few-shot prompting"
    
    key = term.strip().lower()
    
    if key in _BUILTIN_TERMS:
        return f"[{term}] — {_BUILTIN_TERMS[key]}"
    
    similar = [t for t in _BUILTIN_TERMS if key in t or t in key]
    if similar:
        return f"Термин «{term}» не найден. Возможно: {', '.join(similar[:5])}. Попробуй одно из них или спроси Ауру."
    
    data = _load()
    for k, v in data.get("glossary", {}).items():
        if key in k.lower():
            return f"[{k}] (из словарика) — {v.get('meaning', '')}"
    
    return f"Термин «{term}» пока не в справочнике. Спроси меня в диалоге — я объясню и добавлю в словарик."


@tools.tool
def add_to_glossary(term: str = "", meaning: str = "") -> str:
    """
    Добавляет термин в личный словарик Юры.
    """
    if not term:
        return "Укажи термин и значение."

    data = _load()
    if "glossary" not in data:
        data["glossary"] = {}
    
    key = term.strip()
    entry = {
        "meaning": meaning.strip() if meaning else "добавлено без описания",
        "added": datetime.now().isoformat(),
        "learned": False
    }
    data["glossary"][key] = entry
    _save(data)
    
    total = len(data["glossary"])
    learned = sum(1 for v in data["glossary"].values() if v.get("learned"))
    return f"Термин «{key}» добавлен в словарик. Всего: {total}, освоено: {learned}."


@tools.tool
def get_glossary(filter_type: str = "all") -> str:
    """
    Показывает словарик терминов Юры.
    filter_type: "all" (все), "learned" (освоенные), "new" (неосвоенные)
    """
    data = _load()
    glossary = data.get("glossary", {})
    
    if not glossary:
        return "Твой словарик пока пуст. Когда встретишь новый термин — скажи «добавь в словарик»."
    
    total = len(glossary)
    learned = sum(1 for v in glossary.values() if v.get("learned"))
    
    lines = [f"Словарик LLM-терминов ({total} слов, освоено {learned})", ""]
    
    filtered = glossary
    if filter_type == "learned":
        filtered = {k: v for k, v in glossary.items() if v.get("learned")}
        lines[0] = f"Освоенные термины ({len(filtered)} слов)"
    elif filter_type == "new":
        filtered = {k: v for k, v in glossary.items() if not v.get("learned")}
        lines[0] = f"Новые термины ({len(filtered)} слов)"
    
    for term, info in sorted(filtered.items()):
        status = "DONE" if info.get("learned") else "NEW"
        meaning = info.get("meaning", "")[:80]
        lines.append(f"  [{status}] {term} — {meaning}")
    
    return "\n".join(lines)


@tools.tool
def mark_learned(term: str = "") -> str:
    """
    Отмечает термин как освоенный.
    """
    if not term:
        return "Укажи термин."
    
    data = _load()
    glossary = data.get("glossary", {})
    
    key = term.strip()
    if key not in glossary:
        matches = [k for k in glossary if key.lower() in k.lower()]
        if matches:
            return f"Точного совпадения нет. Похожие: {', '.join(matches)}."
        return f"Термин «{key}» не найден. Сначала добавь его."
    
    glossary[key]["learned"] = True
    data["glossary"] = glossary
    _save(data)
    
    learned = sum(1 for v in glossary.values() if v.get("learned"))
    total = len(glossary)
    return f"Термин «{key}» освоен! {learned}/{total}."


@tools.tool
def analyze_prompt(prompt_text: str = "") -> str:
    """
    Анализирует промт Юры и даёт конструктивные советы.
    Проверяет: роль, контекст, формат, примеры, ограничения.
    """
    if not prompt_text:
        return "Передай текст промта в prompt_text."
    
    score = 5
    notes = []
    suggestions = []
    
    has_role = any(w in prompt_text.lower() for w in ["ты ", "ты —", "выступи", "будь", "ты -", "act as", "you are"])
    has_context = len(prompt_text) > 100
    has_format = any(w in prompt_text.lower() for w in ["формат", "ответь в виде", "верни", "напиши в", "списком", "таблиц", "json", "markdown", "format"])
    has_examples = any(w in prompt_text.lower() for w in ["пример", "например", "example", "вот так", "как здесь"])
    has_constraints = any(w in prompt_text.lower() for w in ["не ", "нельзя", "избегай", "ограничен", "только", "не более", "не используй", "без"])
    has_steps = any(w in prompt_text.lower() for w in ["сначала", "потом", "затем", "шаг", "step", "по порядку"])
    
    if has_role:
        score += 1
        notes.append("[+] Роль есть")
    else:
        notes.append("[-] Роль не указана — добавь «Ты — ...»")
        suggestions.append("Добавь роль: кем модель должна себя считать?")
    
    if has_context:
        score += 0.5
        notes.append("[+] Контекст достаточный")
    else:
        notes.append("[~] Контекст коротковат")
        suggestions.append("Добавь контекст: зачем тебе это, что уже пробовал.")
    
    if has_format:
        score += 1
        notes.append("[+] Формат ответа задан")
    else:
        notes.append("[~] Формат не указан")
        suggestions.append("Укажи формат: списком, таблицей, в JSON.")
    
    if has_examples:
        score += 1.5
        notes.append("[+] Примеры есть (few-shot)")
    else:
        notes.append("[~] Примеров нет")
        suggestions.append("Добавь 1-2 примера — few-shot повышает точность в 2-3 раза.")
    
    if has_constraints:
        score += 0.5
        notes.append("[+] Ограничения заданы")
    else:
        notes.append("[~] Ограничений нет")
        suggestions.append("Добавь ограничения: «без воды», «только факты».")
    
    if has_steps:
        score += 0.5
        notes.append("[+] Пошаговая структура")
    
    score = min(10, score)
    
    result = f"Анализ промта (оценка: {score:.1f}/10)\n\nЧто вижу:\n"
    for n in notes:
        result += f"  {n}\n"
    
    if suggestions:
        result += "\nСоветы:\n"
        for i, s in enumerate(suggestions, 1):
            result += f"  {i}. {s}\n"
    
    if score >= 8:
        result += "\nОтличный промт!"
    elif score >= 6:
        result += "\nХороший промт. Пара штрихов — и будет огонь."
    else:
        result += "\nБазовый запрос. Добавь роли, формата и примеров."
    
    return result


@tools.tool
def coach_tip() -> str:
    """Возвращает случайный совет дня по промт-инжинирингу и vibe-девелопменту."""
    data = _load()
    data["tips_given"] = data.get("tips_given", 0) + 1
    _save(data)
    
    tip = random.choice(_TIPS)
    return f"Совет дня (#{data['tips_given']})\n\n{tip}"
