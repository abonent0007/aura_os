"""
Мультиагентный оркестратор AURA OS (DeepSeek Edition)
Один API-ключ DeepSeek, иерархическая архитектура:
Оркестратор → [Координатор|Исследователь|Разработчик] → Дедупликатор → Обозреватель → Пользователь
Все временные файлы (включая контейнер 1) удаляются после выдачи ответа.
В истории диалогов сохраняется только ответ от контейнера 3 (Обозреватель).
"""

import os, re, json, asyncio, sys
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

# ─── НАСТРОЙКИ (ключи из .env) ────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-v4-pro"
SIMILARITY_THRESHOLD = 0.92
TEMP_DIR = Path(os.getenv("TEMP", "/tmp")) / "aura_orchestrator"
# ──────────────────────────────────────────────────────────────────

client = None
dedup_model = None


def _get_client():
    global client
    if client is None:
        client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)
    return client


def _get_dedup_model():
    global dedup_model
    if dedup_model is None:
        dedup_model = SentenceTransformer('all-MiniLM-L6-v2')
    return dedup_model

# ─── СИСТЕМНЫЕ ПРОМТЫ ────────────────────────────────────────────

ORCHESTRATOR_PROMPT = """Ты — Оркестратор. Проанализируй запрос пользователя и определи, 
какие домены нужно активировать. Доступные роли:
- coordinator (план и архитектура решения)
- researcher (глубокий анализ, альтернативы, подводные камни)
- developer (код, реализация, синтаксис)

Для каждой необходимой роли сформулируй уточнённый запрос.
Выведи результат строго в формате JSON без комментариев:
{
  "tasks": [
    {"role": "coordinator", "query": "уточнённый запрос"},
    {"role": "researcher", "query": "уточнённый запрос"},
    {"role": "developer", "query": "уточнённый запрос"}
  ]
}"""

SYSTEM_PROMPTS = {
    "coordinator": """Ты — Координатор. Твоя роль: видеть общую картину задачи.
Разбей задачу на подзадачи, определи зависимости и порядок выполнения.
Выдай структурированный план действий. Не пиши код — только план и архитектуру.
Отвечай на русском языке.""",

    "researcher": """Ты — Исследователь. Твоя роль: глубокий анализ вопроса.
Найди неочевидные связи, альтернативные подходы, подводные камни.
Предложи минимум 2 разных способа решения. Будь критичен и объективен.
Отвечай на русском языке.""",

    "developer": """Ты — Разработчик. Твоя роль: практическая реализация.
Пиши работающий код на Python. Проверяй синтаксис и логику.
Комментируй ключевые решения. Код должен быть готов к запуску.
Отвечай на русском языке, код на Python."""
}

REVIEWER_PROMPT = """Ты — Обозреватель. Твоя задача: взять сырые рассуждения
от Координатора, Исследователя и Разработчика и создать единый осмысленный ответ.

Правила:
1. Структурируй ответ: План → Анализ → Реализация → Вывод.
2. Если в коде есть ошибки — исправь их и укажи, что исправил.
3. Убери противоречия между частями.
4. Если фрагменты кода нужно объединить — сделай это, сохранив функциональность.
5. Итоговый ответ должен быть готов к выдаче пользователю без доработок.
6. Пиши на русском, код оставляй на Python."""

# ─── ИСТОРИЯ ДИАЛОГА (хранится в памяти сессии) ──────────────────
conversation_history: List[Dict[str, str]] = []


def save_to_history(role: str, content: str):
    """Сохраняет сообщение в историю диалога (только финальные ответы)."""
    conversation_history.append({"role": role, "content": content})


def get_history_context() -> str:
    """Возвращает историю диалога в виде строки для промта."""
    if not conversation_history:
        return "Предыдущего диалога нет."
    
    lines = ["### ИСТОРИЯ ДИАЛОГА ###"]
    for msg in conversation_history:
        role_label = "Пользователь" if msg["role"] == "user" else "AURA"
        lines.append(f"[{role_label}]: {msg['content'][:300]}...")
    return "\n".join(lines)


# ─── РАБОТА С ФАЙЛАМИ ────────────────────────────────────────────

def ensure_temp_dir():
    """Создать временную папку, если её нет."""
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_all_temp_files():
    """
    Полная очистка ВСЕХ временных файлов:
    - task_orchestrator.txt (контейнер 1)
    - resp_2a.txt, resp_2b.txt, resp_2c.txt (контейнеры 2)
    - dedup_result.txt (дедупликатор)
    """
    if TEMP_DIR.exists():
        for f in TEMP_DIR.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass  # Файл может быть ещё занят, пропускаем
        print("[Очистка] Все временные файлы удалены (включая контейнер 1).")


def write_temp_file(filename: str, content: str) -> Path:
    """Записать содержимое во временный файл."""
    file_path = TEMP_DIR / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


# ─── ВЫЗОВ DEEPSEEK API ──────────────────────────────────────────

async def call_deepseek(system_prompt: str, user_message: str) -> str:
    """
    Вызов DeepSeek API через единый ключ.
    Автоматически добавляет историю диалога для контекста.
    """
    # Добавляем историю диалога в user_message для связности
    history_context = get_history_context()
    full_message = f"{history_context}\n\n### ТЕКУЩИЙ ЗАПРОС ###\n{user_message}"
    
    response = await _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": full_message}
        ],
        temperature=0.7,
        max_tokens=4096
    )
    return response.choices[0].message.content


# ─── ДЕДУПЛИКАЦИЯ (локальная модель) ─────────────────────────────

def normalize_text(text: str) -> str:
    """Грубая нормализация: нижний регистр, схлопывание пробелов."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def deduplicate_responses(file_paths: List[Path]) -> str:
    """
    Загружает ответы всех контейнеров 2, удаляет дубликаты
    через эмбеддинги (локальная модель all-MiniLM-L6-v2).
    Возвращает очищенный объединённый текст.
    """
    responses = []
    for fp in file_paths:
        if fp.exists():
            text = fp.read_text(encoding="utf-8")
            if text.strip():
                responses.append(text)

    if not responses:
        return ""

    # Если ответ всего один — дедуплицировать нечего
    if len(responses) == 1:
        return responses[0]

    # Разбиваем на абзацы для тонкого сравнения
    all_paragraphs = []
    for resp in responses:
        paragraphs = [p.strip() for p in resp.split("\n\n") if p.strip()]
        all_paragraphs.extend(paragraphs)

    # Вычисляем эмбеддинги
    embeddings = _get_dedup_model().encode(all_paragraphs)

    # Отбираем уникальные абзацы
    unique_paragraphs = []
    unique_embeddings = []

    for i, emb in enumerate(embeddings):
        is_dup = False
        for ue in unique_embeddings:
            similarity = _get_dedup_model().similarity(
                emb.reshape(1, -1), ue.reshape(1, -1)
            ).item()
            if similarity >= SIMILARITY_THRESHOLD:
                is_dup = True
                break
        if not is_dup:
            unique_paragraphs.append(all_paragraphs[i])
            unique_embeddings.append(emb)

    return "\n\n".join(unique_paragraphs)


# ─── ОСНОВНОЙ ПАЙПЛАЙН ───────────────────────────────────────────

async def orchestrate(user_query: str) -> str:
    """
    Главная функция оркестрации.
    Принимает запрос пользователя, возвращает финальный ответ
    (только он сохраняется в историю диалога).
    """
    ensure_temp_dir()

    # ── КОНТЕЙНЕР 1: Оркестратор ─────────────────────────────────
    print("[Контейнер 1] Оркестратор анализирует запрос...")
    plan_json = await call_deepseek(ORCHESTRATOR_PROMPT, user_query)

    # Сохраняем ответ оркестратора во временный файл (будет удалён)
    write_temp_file("task_orchestrator.txt", plan_json)
    print("[Контейнер 1] План задач сохранён → task_orchestrator.txt")

    # Парсим JSON
    try:
        plan_json_clean = re.sub(r'```json\s*|\s*```', '', plan_json).strip()
        plan = json.loads(plan_json_clean)
        tasks = plan.get("tasks", [])
        if not tasks:
            raise ValueError("Пустой список задач")
    except (json.JSONDecodeError, ValueError):
        # Fallback: используем все три роли
        print("[Контейнер 1] Ошибка парсинга JSON, использую fallback (все 3 роли).")
        tasks = [
            {"role": "coordinator", "query": user_query},
            {"role": "researcher", "query": user_query},
            {"role": "developer", "query": user_query}
        ]

    # ── КОНТЕЙНЕРЫ 2: Параллельный запуск ────────────────────────
    print(f"[Контейнеры 2] Запуск {len(tasks)} исполнителей параллельно...")
    temp_files_2 = []

    async def run_worker(role: str, query: str, idx: int) -> Optional[Path]:
        """Запуск одного контейнера 2 и сохранение результата."""
        sys_prompt = SYSTEM_PROMPTS.get(role, SYSTEM_PROMPTS["researcher"])
        letter = chr(97 + idx)  # a, b, c...
        print(f"  [Контейнер 2{letter}] {role} работает...")

        result = await call_deepseek(sys_prompt, query)

        filename = f"resp_2{letter}.txt"
        file_path = write_temp_file(filename, f"=== РОЛЬ: {role} ===\n\n{result}")
        print(f"  [Контейнер 2{letter}] {role} завершил → {filename}")
        return file_path

    # Параллельный запуск всех контейнеров 2
    workers = [
        run_worker(task["role"], task["query"], i)
        for i, task in enumerate(tasks)
    ]
    temp_files_2 = await asyncio.gather(*workers)
    temp_files_2 = [f for f in temp_files_2 if f is not None]

    # ── ЛОКАЛЬНАЯ МОДЕЛЬ: Дедупликация ───────────────────────────
    print("[Дедупликатор] Запуск локальной модели...")
    deduped_text = deduplicate_responses(temp_files_2)
    dedup_path = write_temp_file("dedup_result.txt", deduped_text)
    paragraph_count = len([p for p in deduped_text.split("\n\n") if p.strip()])
    print(f"[Дедупликатор] Очищено → {dedup_path.name} ({paragraph_count} уникальных блоков)")

    # ── КОНТЕЙНЕР 3: Обозреватель ────────────────────────────────
    print("[Контейнер 3] Обозреватель формирует финальный ответ...")
    final_response = await call_deepseek(REVIEWER_PROMPT, deduped_text)

    # ── ПОЛНАЯ ОЧИСТКА (включая контейнер 1) ─────────────────────
    cleanup_all_temp_files()

    # ── СОХРАНЯЕМ В ИСТОРИЮ ТОЛЬКО ОТВЕТ КОНТЕЙНЕРА 3 ───────────
    # save_to_history("user", user_query)  # опционально
    save_to_history("assistant", final_response)
    print("[История] Ответ контейнера 3 сохранён в истории диалога.")

    return final_response


# ─── ТОЧКА ВХОДА ─────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("AURA OS — Мультиагентный оркестратор (DeepSeek Edition)")
    print("Архитектура:")
    print("  Контейнер 1 (Оркестратор)")
    print("    → Контейнеры 2 [Координатор | Исследователь | Разработчик]")
    print("      → Дедупликатор (локальная модель)")
    print("        → Контейнер 3 (Обозреватель) → Пользователь")
    print("=" * 60)
    print("Все временные файлы удаляются после ответа.")
    print("В истории диалога сохраняется только ответ контейнера 3.")
    print("=" * 60)

    while True:
        query = input("\nВведите запрос (или 'exit' для выхода):\n> ")
        if query.lower() in ("exit", "quit", "выход"):
            print("Завершение работы.")
            break

        if not query.strip():
            continue

        print("\n" + "─" * 60)
        try:
            result = await orchestrate(query)
        except Exception as e:
            print(f"[ОШИБКА] {e}")
            result = f"Произошла ошибка при обработке запроса: {e}"

        print("─" * 60)
        print("\n" + "=" * 60)
        print("ФИНАЛЬНЫЙ ОТВЕТ (от Обозревателя):")
        print("=" * 60)
        print(result)
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())