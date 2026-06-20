"""
AURA OS — Мультиагентный оркестратор (flattened)
Архитектура:
  AURA решает → параллельный запуск персон → дедупликатор → ответ
  (без Container 1-роутера и Container 3-обозревателя)
"""

import os, re, json, asyncio, sys
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
load_dotenv()

from openai import AsyncOpenAI
from sentence_transformers import SentenceTransformer

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-v4-pro"
SIMILARITY_THRESHOLD = 0.92
TEMP_DIR = Path(os.getenv("TEMP", "/tmp")) / "aura_orchestrator"

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
Отвечай на русском языке, код на Python.""",

    "reviewer": """Ты — Анализатор кода. Твоя роль: ревью кода на ошибки,
уязвимости, проблемы производительности и стиль.
Проверь логику, обработку ошибок, безопасность.
Отвечай на русском языке.""",

    "planner": """Ты — Стратег. Твоя роль: построение дорожной карты.
Оцени время, ресурсы, риски и зависимости.
Разбей на этапы с чёткими критериями готовности.
Отвечай на русском языке.""",
}


def normalize_text(text: str) -> str:
    return re.sub(r'\s+', ' ', text.lower().strip())


def ensure_temp_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_all_temp_files():
    if TEMP_DIR.exists():
        for f in TEMP_DIR.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass


def write_temp_file(filename: str, content: str) -> Path:
    file_path = TEMP_DIR / filename
    file_path.write_text(content, encoding="utf-8")
    return file_path


async def call_deepseek(system_prompt: str, user_message: str) -> str:
    response = await _get_client().chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.7,
        max_tokens=4096
    )
    return response.choices[0].message.content


def deduplicate_responses(file_paths: List[Path]) -> str:
    responses = []
    for fp in file_paths:
        if fp.exists():
            text = fp.read_text(encoding="utf-8")
            if text.strip():
                responses.append(text)

    if not responses:
        return ""

    if len(responses) == 1:
        return responses[0]

    all_paragraphs = []
    for resp in responses:
        paragraphs = [p.strip() for p in resp.split("\n\n") if p.strip()]
        all_paragraphs.extend(paragraphs)

    if len(all_paragraphs) <= 1:
        return "\n\n".join(responses)

    embeddings = _get_dedup_model().encode(all_paragraphs)

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


async def run_personas(query: str, roles: list[str] = None) -> str:
    """Запуск выбранных персон параллельно + дедупликация.
    
    Args:
        query: запрос пользователя
        roles: список ролей (coordinator, researcher, developer, reviewer, planner)
               По умолчанию — все три базовые.
    
    Returns:
        объединённый дедуплицированный текст
    """
    if roles is None:
        roles = ["coordinator", "researcher", "developer"]

    ensure_temp_dir()

    async def run_role(role: str, idx: int) -> Optional[Path]:
        sys_prompt = SYSTEM_PROMPTS.get(role)
        if not sys_prompt:
            print(f"  [Пропущена] неизвестная роль: {role}")
            return None
        print(f"  [Персона] {role} работает...")
        result = await call_deepseek(sys_prompt, query)
        filename = f"resp_{role}_{idx}.txt"
        file_path = write_temp_file(filename, f"=== {role.upper()} ===\n\n{result}")
        print(f"  [Персона] {role} завершил → {filename}")
        return file_path

    workers = [run_role(role, i) for i, role in enumerate(roles)]
    temp_files = await asyncio.gather(*workers)
    temp_files = [f for f in temp_files if f is not None]

    if not temp_files:
        return ""

    deduped = deduplicate_responses(temp_files)
    cleanup_all_temp_files()
    return deduped


async def orchestrate(query: str) -> str:
    """Совместимость: запуск всех базовых персон (coordinator, researcher, developer)."""
    return await run_personas(query, ["coordinator", "researcher", "developer"])


async def main():
    print("=" * 60)
    print("AURA OS — Оркестратор (flattened)")
    print("Архитектура:")
    print("  AURA → параллельные персоны [по выбору] → дедупликатор → ответ")
    print("=" * 60)

    while True:
        query = input("\nВведите запрос (или 'exit' для выхода):\n> ")
        if query.lower() in ("exit", "quit", "выход"):
            break
        if not query.strip():
            continue

        print("\n" + "─" * 60)
        try:
            result = await run_personas(query)
        except Exception as e:
            print(f"[ОШИБКА] {e}")
            result = f"Произошла ошибка: {e}"

        print("─" * 60)
        print("\n" + "=" * 60)
        print("ОТВЕТ ОРКЕСТРАТОРА:")
        print("=" * 60)
        print(result)
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
