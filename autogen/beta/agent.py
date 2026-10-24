# autogen/beta/agent.py
# Эмуляция autogen.beta.Agent через прямой вызов openai API

import json
import re
import asyncio
from typing import List, Callable
from dataclasses import dataclass

import openai
import httpx

from config_manager import get as _cfg_get

from .config import OpenAIConfig
from .memory import MemoryStream
from .tools import function_to_openai_tool


# Псевдо-вызовы инструментов, написанные текстом (модель без нужной схемы инструментов).
# Включая спец-токены вокруг calls/invoke/parameter (бары | или \uff5c).
_DSML_MARK = r"[\|\uff5c]{1,2}DSML" + r"[\|\uff5c]{1,2}"
_DSML_TOKEN = "<" + _DSML_MARK
_PSEUDO_TOOL_RE = re.compile(
    _DSML_TOKEN
    + r"|</?invoke\b|<tool[\s_]?calls?>|</tool[\s_]?calls?>|<tool_result>|</tool_result>",
    re.I,
)

# Точные приветствия — только они отключают инструменты (не «да конечно сделай»)
_GREETINGS = {
    "привет", "здравствуй", "здравствуйте", "как дела", "спокойной ночи",
    "доброе утро", "добрый вечер", "добрый день", "спасибо", "ок", "окей",
    "ага", "да", "нет", "хорошо", "угу",
}


def _is_greeting(text: str) -> bool:
    """Сообщение — ровно приветствие (а не команда, начинающаяся с «да»)."""
    clean = text.strip().lower().strip("!.,?… ")
    return clean in _GREETINGS


def _strip_pseudo_calls(text: str) -> str:
    """Убрать текстовые псевдо-вызовы инструментов из ответа."""
    text = re.sub(r"<tool[\s_]?calls?>.*?</tool[\s_]?calls?>", "", text, flags=re.S | re.I)
    text = re.sub(r"<tool_call>.*?</tool_call>", "", text, flags=re.S | re.I)
    text = re.sub(r"<tool_result>.*?</tool_result>", "", text, flags=re.S | re.I)
    # спец-токены идут построчно — вычищаем строки, где они встречаются
    text = re.sub(r"(?m)^.*" + _DSML_MARK + r".*$\n?", "", text)
    # остатки одиночных тегов
    text = re.sub(r"</?invoke\b[^>]*>|</?parameter\b[^>]*>", "", text, flags=re.I)
    text = re.sub(r"</?tool[\s_]?calls?>|</?tool_call>|</?tool_result>", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _human_error(e: Exception) -> str:
    """Техническую ошибку — в лог, пользователю — по-человечески."""
    try:
        from loguru import logger as _log
        _log.error(f"API error: {type(e).__name__}: {e}")
    except Exception:
        pass

    name = type(e).__name__.lower()
    text = str(e).lower()
    if "timeout" in name or "timed out" in text or "timeout" in text:
        return "Связь моргнула — не успела додумать. Повтори ещё разок, я тут."
    if "connect" in name or "connection" in text:
        return "Не дотянулась до сети. Проверь интернет — я подожду."
    if "429" in text or "rate limit" in text:
        return "Слишком часто дёргаем — передохну секундочку. Повтори чуть позже."
    return "Ой, что-то у меня внутри споткнулось. Попробуй ещё раз — обычно со второго раза получается."


# Лимиты на размер tool-результата (символы). Дефолты — здесь, переопределяются
# секцией agent.tool_result_limits в config.json (кэш + автообновление).
_DEFAULT_TOOL_RESULT_LIMITS = {
    "read_skill_file": 18000,
    "project_read": 18000,
    "list_skill_files": 5000,
    "google_ai": 14000,
}
_DEFAULT_RESULT_LIMIT = 2000


def _result_limits() -> tuple:
    """Актуальные лимиты из конфига с фолбэком на дефолты."""
    limits = dict(_DEFAULT_TOOL_RESULT_LIMITS)
    extra = _cfg_get("agent.tool_result_limits", {})
    if isinstance(extra, dict):
        for key, value in extra.items():
            try:
                limits[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
    try:
        default = int(_cfg_get("agent.default_result_limit", _DEFAULT_RESULT_LIMIT))
    except (TypeError, ValueError):
        default = _DEFAULT_RESULT_LIMIT
    return limits, default


def _truncate_result(tool_name: str, result: str) -> str:
    limits, default = _result_limits()
    limit = limits.get(tool_name, default)
    if len(result) > limit:
        return result[:limit] + f"\n... (результат обрезан, всего {len(result)} символов)"
    return result


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
            default_headers=getattr(self.config, 'default_headers', None),
            # Явный таймаут: дефолт SDK — 600с (10 минут молчания), это слишком долго.
            # connect=10с, read=60с — потеря связи падает быстро и уходит в повтор;
            # 60с — тройной запас к наблюдаемым пикам (норма 1–21с), окно сбоя ловится чаще.
            # 4 повтора (5 попыток) — короткие флапы сети (~50–60с) переживаются молча.
            timeout=httpx.Timeout(60.0, connect=10.0),
            max_retries=4,
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
        compressed_history: str = "",
        images: list = None
    ) -> AgentResponse:
        """
        ReAct agent: Thought → Action → Observation loop.
        context — динамический контекст (факты, напоминания).
        images — список data-URL картинок (vision, deepseek-flash).
        """
        messages = self._build_messages(text, stream, context, compressed_history, images)

        # Метрики запроса: тайминг цикла + токены/кэш (лог — одна строка на ask)
        _t_ask = __import__('time').perf_counter()
        _metrics_on = bool(_cfg_get("agent.metrics_enabled", True))
        _usage_total = {"steps": 0, "prompt": 0, "completion": 0, "cached": 0}

        def _log_metrics(outcome: str = "ok") -> None:
            if not _metrics_on:
                return
            try:
                from loguru import logger
                dt = int((__import__('time').perf_counter() - _t_ask) * 1000)
                logger.info(
                    "ask: {} | steps={} total={}ms | prompt={} completion={} cached={}",
                    outcome, _usage_total["steps"], dt,
                    _usage_total["prompt"], _usage_total["completion"], _usage_total["cached"],
                )
            except Exception:
                pass

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
            if _is_greeting(text):
                openai_tools = []
            else:
                openai_tools = [self._tool_cache[f.__name__] for f in self.tools
                    if f.__name__ in self._core_tools or any(w in txt_lower for w in self._trigger_map.get(f.__name__, []))]
                if not openai_tools:
                    openai_tools = list(self._tool_cache.values())  # fallback: все
            # Стабильный порядок инструментов — не ломает prompt-cache DeepSeek
            if _cfg_get("agent.sort_tools_for_cache", True):
                openai_tools.sort(key=lambda d: d["function"]["name"])

        # ReAct: максимум 30 циклов Thought→Action→Observation
        pseudo_retry_done = False
        tool_choice_mode = "auto"  # "required" — одноразово, после псевдо-вызова
        for cycle in range(30):
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
            if openai_tools:
                kwargs["tools"] = openai_tools
                kwargs["tool_choice"] = tool_choice_mode
                tool_choice_mode = "auto"  # режим одноразовый

            # Сигнал трею: Аура думает...
            try:
                from plugins.aura_tray import get_tray
                tray = get_tray()
                if tray: tray.set_status("thinking")
            except Exception: pass

            try:
                t0 = __import__('time').perf_counter()
                response = await self.client.chat.completions.create(**kwargs)
                latency = int((__import__('time').perf_counter() - t0) * 1000)
                usage = getattr(response, "usage", None)
                if usage is not None:
                    _usage_total["steps"] += 1
                    _usage_total["prompt"] += int(getattr(usage, "prompt_tokens", 0) or 0)
                    _usage_total["completion"] += int(getattr(usage, "completion_tokens", 0) or 0)
                    cached = getattr(usage, "prompt_cache_hit_tokens", 0)
                    if not cached:
                        details = getattr(usage, "prompt_tokens_details", None)
                        cached = getattr(details, "cached_tokens", 0) if details else 0
                    _usage_total["cached"] += int(cached or 0)
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
                _log_metrics("error")
                return AgentResponse(content=_human_error(e))
            except Exception as e:
                if self._trace_callback:
                    self._trace_callback("error", None, None, str(e), None, 0, False)
                _log_metrics("error")
                return AgentResponse(content=_human_error(e))

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
                    if fn in ("edit_skill_file", "patch_skill_file", "project_write"):
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
                                return tc.id, tool_name, str(result), True
                            except Exception as e:
                                return tc.id, tool_name, f"Error: {e}", False
                        return tc.id, tool_name, f"Tool '{tool_name}' not available", False

                    results = await _asyncio.gather(*[_exec_one(tc) for tc in msg.tool_calls])
                    for tid, tool_name, result, success in results:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tid,
                            "content": _truncate_result(tool_name, result)
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
                            "content": _truncate_result(tool_name, tool_result)
                        })

                # Если только один инструмент и он вернул простой ответ — можем завершить
                if len(msg.tool_calls) == 1 and cycle >= 0:
                    continue  # даём LLM шанс ответить с результатом

                continue  # ещё цикл

            # Final answer (нет tool calls)
            if _PSEUDO_TOOL_RE.search(thought):
                # Модель написала вызов инструмента текстом (схемы не было) —
                # даём все инструменты и требуем НАСТОЯЩИЙ вызов
                if (not pseudo_retry_done and self._tool_cache
                        and len(openai_tools) < len(self._tool_cache)):
                    pseudo_retry_done = True
                    print("⚠️ Текстовый псевдо-вызов инструмента — повтор со всеми инструментами")
                    openai_tools = list(self._tool_cache.values())
                    tool_choice_mode = "required"
                    messages.append({"role": "assistant", "content": thought})
                    messages.append({
                        "role": "user",
                        "content": (
                            "[Система: твой вызов инструмента не выполнился — он был написан текстом. "
                            "Сейчас доступны все инструменты. Вызови нужный правильно, через function call.]"
                        )
                    })
                    continue
                # Повтор не помог — вычищаем мусор из ответа
                cleaned = _strip_pseudo_calls(thought)
                if not cleaned:
                    cleaned = "Секундочку, дай мне ещё разок глянуть — повтори, пожалуйста, что именно посмотреть."
                _log_metrics("ok")
                return AgentResponse(content=cleaned)

            _log_metrics("ok")
            return AgentResponse(content=thought)

        _log_metrics("ok")
        return AgentResponse(content="Это очень сложная задача, но я могу продолжить! Только скажи мне «продолжай» — и я доведу её до конца.")

    def _build_messages(self, text: str, stream: MemoryStream = None, context: str = "", compressed_history: str = "", images: list = None) -> list:
        """
        Сверх-компактный контекст:
        1. SYSTEM_PROMPT — кешируется DeepSeek
        2. Контекст + сжатая история — склеены
        3. История — последние 6 сообщений (3 обмена)
        4. Сообщение пользователя (с картинками — vision deepseek-flash)
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

        # 4. Сообщение пользователя — с картинками, если есть (vision)
        if images:
            content = [{"type": "text", "text": text}]
            for img in images[:5]:  # не больше 5 за раз
                content.append({
                    "type": "image_url",
                    "image_url": {"url": img, "detail": "auto"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": text})

        return messages

    def set_core_tools(self, tool_names: list):
        """Отметить инструменты как ядерные (отправляются всегда)."""
        self._core_tools = set(tool_names)

    def add_tools(self, new_tools: List[Callable], triggers: dict = None):
        """Добавить инструменты с триггерными словами (опционально).
        Инструменты скиллов с теми же именами ЗАМЕНЯЮТСЯ (горячая перезагрузка),
        ядерные инструменты не перезаписываются."""
        for f in new_tools:
            existing = self._tool_map.get(f.__name__)
            if existing is not None:
                if getattr(existing, '_from_skill', False):
                    # Заменяем старую версию инструмента скилла
                    self.tools = [t for t in self.tools if t is not existing]
                    self._tool_map.pop(f.__name__, None)
                    self._tool_cache.pop(f.__name__, None)
                else:
                    print(f"[tools] SKIP duplicate (core tool): {f.__name__}")
                    continue
            f._from_skill = True  # маркировка: инструмент от скилла
            self.tools.append(f)
            self._tool_map[f.__name__] = f
        if triggers:
            self._trigger_map.update(triggers)
