# autogen/beta/agent.py
# Эмуляция autogen.beta.Agent через прямой вызов openai API

import json
import asyncio
from typing import Optional, List, Callable
from dataclasses import dataclass

import openai

from .config import OpenAIConfig
from .memory import MemoryStream
from .tools import function_to_openai_tool


@dataclass
class AgentResponse:
    """Ответ агента."""
    content: str
    body: str = ""

    def __post_init__(self):
        self.body = self.content


class Agent:
    """
    Агент с поддержкой function calling (инструменты) и авто-ротацией API-ключей.
    Совместим с autogen.beta.Agent API.
    """

    def __init__(
        self,
        name: str = "Agent",
        config: OpenAIConfig = None,
        tools: List[Callable] = None,
        system_message: str = "",
        api_keys: list = None
    ):
        self.name = name
        self.config = config or OpenAIConfig()
        self.tools = tools or []
        self.system_message = system_message
        self._tool_map = {f.__name__: f for f in self.tools}

        # Ротация ключей: основной + резервные
        self._api_keys = api_keys or [self.config.api_key]
        self._current_key_idx = 0
        self._key_health = {}  # key → {'failures': int, 'last_fail': timestamp}

        self._init_client()

    def _init_client(self):
        """Создаёт клиент с текущим ключом."""
        key = self._api_keys[self._current_key_idx] if self._api_keys else self.config.api_key
        self.client = openai.AsyncOpenAI(
            api_key=key,
            base_url=self.config.base_url or "https://api.deepseek.com/v1",
            default_headers=getattr(self.config, 'default_headers', None)
        )

    def _rotate_key(self) -> bool:
        """Переключает на следующий рабочий ключ. Возвращает True если есть живой ключ."""
        import time
        now = time.time()

        # Пробуем все ключи, начиная со следующего
        for _ in range(len(self._api_keys)):
            self._current_key_idx = (self._current_key_idx + 1) % len(self._api_keys)
            key = self._api_keys[self._current_key_idx]

            # Пропускаем ключи с >3 ошибками за последние 5 минут
            health = self._key_health.get(key, {"failures": 0, "last_fail": 0})
            if health["failures"] >= 3 and (now - health["last_fail"]) < 300:
                continue

            self._init_client()
            return True

        # Все ключи нездоровы — сбрасываем счётчики и пробуем первый
        self._key_health = {}
        self._current_key_idx = 0
        self._init_client()
        return True

    def _mark_key_failure(self):
        """Отмечает текущий ключ как проблемный."""
        import time
        key = self._api_keys[self._current_key_idx] if self._api_keys else ""
        if key:
            h = self._key_health.get(key, {"failures": 0, "last_fail": 0})
            h["failures"] += 1
            h["last_fail"] = time.time()
            self._key_health[key] = h

    def _is_auth_error(self, status_code: int) -> bool:
        """Проверяет, является ли ошибка авторизационной (ключ невалиден/исчерпан)."""
        return status_code in (401, 403, 429)

    async def ask(
        self,
        text: str,
        stream: MemoryStream = None,
        variables: dict = None,
        context: str = ""
    ) -> AgentResponse:
        """
        Основной метод: отправляет запрос модели и возвращает ответ.
        context — динамический контекст (факты, напоминания), добавляется отдельно от system.
        """
        messages = self._build_messages(text, stream, context)

        openai_tools = None
        if self.tools:
            openai_tools = [function_to_openai_tool(f) for f in self.tools]

        for _ in range(3):  # максимум 3 цикла tool calling
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            try:
                response = await self.client.chat.completions.create(**kwargs)
            except openai.APIStatusError as e:
                if self._is_auth_error(e.status_code):
                    print(f"[key-rotation] Key error {e.status_code}, rotating...")
                    self._mark_key_failure()
                    if self._rotate_key():
                        continue
                # Не auth-ошибка — возвращаем как есть
                return AgentResponse(content=f"API error {e.status_code}: {e.message}")
            except Exception as e:
                return AgentResponse(content=f"Connection error: {e}")

            choice = response.choices[0]
            msg = choice.message

            # Если модель хочет вызвать инструмент
            if msg.tool_calls and self.tools:
                assistant_msg = {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        }
                        for tc in msg.tool_calls
                    ]
                }
                # DeepSeek thinking mode: preserve reasoning_content
                if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                    assistant_msg["reasoning_content"] = msg.reasoning_content
                messages.append(assistant_msg)

                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    tool_fn = self._tool_map.get(tool_name)
                    if tool_fn:
                        try:
                            args = json.loads(tc.function.arguments)
                            result = tool_fn(**args) if args else tool_fn()
                            tool_result = str(result)
                        except Exception as e:
                            tool_result = f"Tool error ({tool_name}): {e}"

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result[:2000]
                        })
                continue  # продолжаем цикл — модель получит результаты

            # Финальный ответ
            content = msg.content or ""
            return AgentResponse(content=content)

        return AgentResponse(content="Извини, произошёл сбой при обработке запроса. Попробуй переформулировать вопрос.")

    def _build_messages(self, text: str, stream: MemoryStream = None, context: str = "") -> list:
        """
        Оптимизировано для prompt caching:
        1. SYSTEM_PROMPT — первый, статический → кешируется DeepSeek
        2. Контекст (факты/напоминания) — отдельно, короткий
        3. История диалога — последние 20 сообщений
        4. Сообщение пользователя
        """
        messages = []

        # 1. Статический системный промпт — кешируется
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})

        # 2. Динамический контекст — короткий, меняется
        if context and context.strip():
            messages.append({"role": "system", "content": f"[Текущий контекст]\n{context}"})

        # 3. История диалога
        if stream and stream.history._messages:
            for m in stream.history._messages[-20:]:
                messages.append(m)

        # 4. Сообщение пользователя
        messages.append({"role": "user", "content": text})

        return messages

    def add_tools(self, new_tools: List[Callable]):
        """Добавить инструменты к агенту (для интеграции скиллов)."""
        self.tools.extend(new_tools)
        for f in new_tools:
            self._tool_map[f.__name__] = f
