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
    def __init__(self, name="Agent", config=None, tools=None, system_message="", api_keys=None):
        self.name = name
        self.config = config or OpenAIConfig()
        self.tools = tools or []
        self.system_message = system_message
        self._tool_map = {f.__name__: f for f in self.tools}
        self._core_tools = set()       # всегда отправляются
        self._trigger_map = {}         # tool_name → [trigger_words]
        self._tool_cache = {}          # tool_name → openai_tool_def (кеш)
        self._api_keys = api_keys or [self.config.api_key]
        self._current_key_idx = 0
        self._key_health = {}
        self._trace_callback = None
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
        context: str = "",
        compressed_history: str = ""
    ) -> AgentResponse:
        """
        ReAct agent: Thought → Action → Observation loop.
        context — динамический контекст (факты, напоминания).
        """
        messages = self._build_messages(text, stream, context, compressed_history)

        # ── УМНАЯ ФИЛЬТРАЦИЯ ИНСТРУМЕНТОВ ──
        openai_tools = []
        if self.tools:
            # Кешируем tool definitions (первый вызов — строим, потом из кеша)
            if not self._tool_cache:
                self._tool_cache = {f.__name__: function_to_openai_tool(f) for f in self.tools}
            # Обновляем кеш для новых инструментов
            for f in self.tools:
                if f.__name__ not in self._tool_cache:
                    self._tool_cache[f.__name__] = function_to_openai_tool(f)

            txt_lower = text.lower()
            _HI = ["привет", "здравствуй", "как дела", "спокойной ночи", "доброе утро", "добрый вечер", "спасибо", "ок", "ага", "да", "нет"]
            if len(text) < 50 and any(text.lower().startswith(p) for p in _HI):
                openai_tools = []
            else:
                openai_tools = [self._tool_cache[f.__name__] for f in self.tools
                    if f.__name__ in self._core_tools or any(w in txt_lower for w in self._trigger_map.get(f.__name__, []))]
                if not openai_tools:
                    openai_tools = list(self._tool_cache.values())  # fallback: все

        # ReAct: максимум 30 циклов Thought→Action→Observation
        for cycle in range(30):
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = "auto"

            # Сигнал трею: Аура думает...
            try:
                from plugins.aura_tray import get_tray
                tray = get_tray()
                if tray: tray.set_status("thinking")
            except Exception: pass

            try:
                t0 = __import__('time').time()
                response = await self.client.chat.completions.create(**kwargs)
                latency = int((__import__('time').time() - t0) * 1000)
                if self._trace_callback:
                    self._trace_callback("inference", None, None, None,
                                        response.choices[0].message.content, latency, True)
                # Сигнал трею: DeepSeek ответил — онлайн
                try:
                    from plugins.aura_tray import get_tray
                    tray = get_tray()
                    if tray: tray.set_status("online")
                except Exception: pass
            except openai.APIStatusError as e:
                if self._trace_callback:
                    self._trace_callback("error", None, None, str(e), None, 0, False)
                if self._is_auth_error(e.status_code):
                    print(f"[key-rotation] Key error {e.status_code}, rotating...")
                    self._mark_key_failure()
                    if self._rotate_key():
                        continue
                # Сигнал трею: потеря связи
                try:
                    from plugins.aura_tray import get_tray
                    tray = get_tray()
                    if tray: tray.set_status("offline")
                except Exception: pass
                return AgentResponse(content=f"API error {e.status_code}: {e.message}")
            except Exception as e:
                if self._trace_callback:
                    self._trace_callback("error", None, None, str(e), None, 0, False)
                return AgentResponse(content=f"Connection error: {e}")

            choice = response.choices[0]
            msg = choice.message

            # Thought: LLM reasoning (content before tool call)
            thought = msg.content or ""

            # Action: инструменты
            if msg.tool_calls and self.tools:
                # Компактный формат: аргументы урезаны, кроме файловых операций
                def _compact_args(tc):
                    fn = tc.function.name
                    args = tc.function.arguments
                    if fn in ("edit_skill_file", "project_write"):
                        return args
                    return args[:200] if len(args) > 200 else args

                assistant_msg = {
                    "role": "assistant",
                    "content": thought[:500] if thought else "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": _compact_args(tc)}
                        }
                        for tc in msg.tool_calls
                    ]
                }
                if hasattr(msg, 'reasoning_content') and msg.reasoning_content:
                    assistant_msg["reasoning_content"] = msg.reasoning_content
                messages.append(assistant_msg)

                # Execute tools and collect Observations
                observations = []
                # Parallel tool execution (DeepSeek supports concurrent calls)
                if len(msg.tool_calls) > 1:
                    import asyncio as _asyncio

                    async def _exec_one(tc):
                        tool_name = tc.function.name
                        tool_fn = self._tool_map.get(tool_name)
                        if tool_fn:
                            try:
                                args = json.loads(tc.function.arguments)
                                loop = _asyncio.get_event_loop()
                                result = await loop.run_in_executor(None, lambda: tool_fn(**args) if args else tool_fn())
                                return tc.id, str(result), True
                            except Exception as e:
                                return tc.id, f"Error: {e}", False
                        return tc.id, f"Tool '{tool_name}' not available", False

                    results = await _asyncio.gather(*[_exec_one(tc) for tc in msg.tool_calls])
                    for tid, result, success in results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": result[:2000]
                        })
                        if self._trace_callback:
                            self._trace_callback("tool_call", tid[:8], None, result, None, 0, success)
                else:
                    # Sequential for single tool
                    for tc in msg.tool_calls:
                        tool_name = tc.function.name
                        tool_fn = self._tool_map.get(tool_name)
                        if tool_fn:
                            try:
                                args = json.loads(tc.function.arguments)
                                t0 = __import__('time').time()
                                result = tool_fn(**args) if args else tool_fn()
                                latency = int((__import__('time').time() - t0) * 1000)
                                tool_result = str(result)
                                if self._trace_callback:
                                    self._trace_callback("tool_call", tool_name,
                                                        tc.function.arguments, tool_result, None, latency, True)
                            except Exception as e:
                                tool_result = f"Error ({tool_name}): {e}"
                                if self._trace_callback:
                                    self._trace_callback("tool_call", tool_name,
                                                        tc.function.arguments, tool_result, None, 0, False)
                        else:
                            tool_result = f"Tool '{tool_name}' not available. Try another approach."

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": tool_result[:2000]
                        })

                # Если только один инструмент и он вернул простой ответ — можем завершить
                if len(msg.tool_calls) == 1 and cycle >= 0:
                    continue  # даём LLM шанс ответить с результатом

                continue  # ещё цикл

            # Final answer (нет tool calls)
            return AgentResponse(content=thought)

        return AgentResponse(content="Это очень сложная задача, но я могу продолжить! Только скажи мне «продолжай» — и я доведу её до конца.")

    def _build_messages(self, text: str, stream: MemoryStream = None, context: str = "", compressed_history: str = "") -> list:
        """
        Сверх-компактный контекст:
        1. SYSTEM_PROMPT — кешируется DeepSeek
        2. Контекст + сжатая история — склеены
        3. История — последние 6 сообщений (3 обмена)
        4. Сообщение пользователя
        """
        messages = []

        # 1. Статический системный промпт
        if self.system_message:
            messages.append({"role": "system", "content": self.system_message})

        # 2. Контекст + сжатая история — склеиваем в одно сообщение
        extra = []
        if compressed_history and compressed_history.strip():
            extra.append(compressed_history)
        if context and context.strip():
            extra.append(context)
        if extra:
            messages.append({"role": "system", "content": "\n".join(extra)})

        # 3. История — последние 6 сообщений (3 вопроса + 3 ответа)
        if stream and stream.history._messages:
            for m in stream.history._messages[-6:]:
                # Фильтруем: пропускаем большие tool-результаты
                if m.get("role") == "tool" and len(m.get("content", "")) > 500:
                    m = dict(m)
                    m["content"] = m["content"][:500] + "..."
                messages.append(m)

        # 4. Сообщение пользователя
        messages.append({"role": "user", "content": text})

        return messages

    def set_core_tools(self, tool_names: list):
        """Отметить инструменты как ядерные (отправляются всегда)."""
        self._core_tools = set(tool_names)

    def add_tools(self, new_tools: List[Callable], triggers: dict = None):
        """Добавить инструменты с триггерными словами (опционально)."""
        existing = set(self._tool_map.keys())
        for f in new_tools:
            if f.__name__ in existing:
                print(f"[tools] SKIP duplicate: {f.__name__}")
                continue
            f._from_skill = True  # маркировка: инструмент от скилла
            self.tools.append(f)
            self._tool_map[f.__name__] = f
            existing.add(f.__name__)
        if triggers:
            self._trigger_map.update(triggers)
