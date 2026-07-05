# aura_core.py
import asyncio
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional, List, Tuple
from collections import defaultdict

# Fix Windows console encoding for emoji
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from dotenv import load_dotenv
from autogen.beta import Agent, config, MemoryStream, tools
from database import EventCategory, MemoryTriggerSystem, AuraDatabase
from system_prompt import SYSTEM_PROMPT

# ============================================================
# 0. ИНИЦИАЛИЗАЦИЯ
# ============================================================
load_dotenv()

def load_config(config_path: str = "config.json") -> dict:
    with open(config_path, "r", encoding="utf-8-sig") as f:
        cfg = json.load(f)
    for section in ["memory", "skills"]:
        if section in cfg:
            for key, value in cfg[section].items():
                if isinstance(value, str) and ("~" in value or "$" in value):
                    cfg[section][key] = os.path.expandvars(os.path.expanduser(value))
    return cfg

CONFIG = load_config()

# Ссылки на skill_manager и agent для авто-перезагрузки скиллов
_skill_manager_ref = None
_agent_ref = None


# ============================================================
# 4. ИНСТРУМЕНТЫ АГЕНТА
# ============================================================
def create_aura_tools(db: AuraDatabase):

    @tools.tool
    def search_memory(query: str, limit: int = 5) -> str:
        """
        Поиск по всей истории общения. 
        Используй когда нужно вспомнить прошлые разговоры, решения, факты.
        """
        results = db.search_memory_fts(query, limit)
        if not results:
            # Пробуем поиск по тегам
            keywords = [w.strip() for w in query.split() if len(w.strip()) > 2]
            if keywords:
                results = db.search_memory_by_tags(keywords, limit)

        if not results:
            return f"🔍 По запросу '{query}' в истории ничего не найдено."

        lines = [f"📚 **Найдено в истории ({len(results)} записей):**\n"]
        for i, r in enumerate(results, 1):
            date_str = r.get("date_key", "?")
            summary = r.get("summary", "")[:200]
            topics = r.get("key_topics", "")
            decisions = r.get("key_decisions", "")

            lines.append(f"**{i}. {date_str}**")
            lines.append(f"   📝 {summary}")
            if topics:
                lines.append(f"   🏷️ Темы: {topics}")
            if decisions:
                lines.append(f"   ✅ Решения: {decisions}")
            if "snippet" in r:
                lines.append(f"   🔍 Контекст: ...{r['snippet']}...")
            lines.append("")

        return "\n".join(lines)

    @tools.tool
    def get_today_summary() -> str:
        """Получить краткую сводку сегодняшнего общения."""
        summary = db.get_today_summary()
        if not summary:
            return "За сегодня пока нет сохраненной истории."

        lines = ["📅 **Сводка за сегодня:**"]
        lines.append(f"📝 {summary.get('summary', '')}")
        if summary.get("key_topics"):
            lines.append(f"🏷️ Темы: {summary['key_topics']}")
        if summary.get("key_decisions"):
            lines.append(f"✅ Решения: {summary['key_decisions']}")
        if summary.get("key_facts"):
            lines.append(f"🧠 Факты: {summary['key_facts']}")
        return "\n".join(lines)

    @tools.tool
    def get_recent_history(days: int = 7) -> str:
        """Получить сводки за последние N дней."""
        summaries = db.get_recent_summaries(days)
        if not summaries:
            return f"За последние {days} дней нет сохраненной истории."

        lines = [f"📅 **История за {days} дней:**\n"]
        for s in summaries:
            date_str = s["date_key"]
            summary = s.get("summary", "")[:150]
            topics = s.get("key_topics", "")
            lines.append(f"**{date_str}:** {summary}")
            if topics:
                lines.append(f"  🏷️ {topics}")
            lines.append("")
        return "\n".join(lines)

    @tools.tool
    def get_today_events() -> str:
        """События на сегодня."""
        events = db.get_events_for_date()
        if not events:
            return "На сегодня событий нет."
        lines = ["📅 **Сегодня:**"]
        for ev in events:
            emoji = ev.get("emoji", "📌")
            cat = ev.get("category_name", "")
            time_str = f" в {ev['event_time'][:5]}" if ev.get("event_time") else ""
            lines.append(f"{emoji} [{cat}] {ev['title']}{time_str}")
        return "\n".join(lines)

    @tools.tool
    def get_upcoming_events(days: int = 7) -> str:
        """Ближайшие события."""
        events = db.get_upcoming_events(days)
        if not events:
            return f"На ближайшие {days} дней событий нет."
        by_date = defaultdict(list)
        for ev in events:
            by_date[ev["event_date"]].append(ev)
        lines = [f"📅 **Ближайшие {days} дней:**"]
        for d, day_events in sorted(by_date.items()):
            date_obj = datetime.strptime(d, "%Y-%m-%d")
            lines.append(f"\n{date_obj.strftime('%d.%m (%A)')}:")
            for ev in day_events:
                emoji = ev.get("emoji", "📌")
                time_str = f" в {ev['event_time'][:5]}" if ev.get("event_time") else ""
                lines.append(f"  {emoji} {ev['title']}{time_str}")
        return "\n".join(lines)

    @tools.tool
    def add_event(title: str, event_date: str, category: str = "nap",
                  event_time: str = None, description: str = None) -> str:
        """Добавить событие. category: 'drr','zad','nap','evt','pln','med'. event_date: 'YYYY-MM-DD'."""
        valid = ["drr", "zad", "nap", "evt", "pln", "med"]
        if category not in valid:
            return f"Категория должна быть: {valid}"
        try:
            datetime.strptime(event_date, "%Y-%m-%d")
        except ValueError:
            return "Неверный формат даты. YYYY-MM-DD"
        if event_time:
            try:
                datetime.strptime(event_time, "%H:%M")
            except ValueError:
                return "Неверный формат времени. HH:MM"
        db.add_event(title, event_date, category, event_time, description)
        return f"{EventCategory.get_emoji(category)} [{EventCategory.get_name(category)}] '{title}' на {event_date}"

    @tools.tool
    def add_birthday_reminder(person_name: str, birth_date: str, year: int = None) -> str:
        """Добавить день рождения. birth_date: 'MM-DD'."""
        try:
            datetime.strptime(birth_date, "%m-%d")
        except ValueError:
            return "Формат: MM-DD (например 03-15)"
        db.add_birthday(person_name, birth_date, year)
        return f"🎂 День рождения {person_name} сохранен!"

    @tools.tool
    def search_calendar(query: str) -> str:
        """Поиск событий в календаре."""
        events = db.search_events(query)
        if not events:
            return f"По '{query}' ничего не найдено."
        lines = [f"🔍 **'{query}':**"]
        for ev in events:
            emoji = ev.get("emoji", "📌")
            lines.append(f"{emoji} {ev['title']} — {ev['event_date']}")
        return "\n".join(lines)

    @tools.tool
    def complete_task_by_name(title_query: str) -> str:
        """Завершить задачу по названию."""
        events = db.search_events(title_query)
        for ev in events:
            if ev["category"] != EventCategory.BIRTHDAY:
                db.complete_event(ev["id"])
                return f"✅ '{ev['title']}' выполнено!"
        return "Не найдено активных задач."

    @tools.tool
    def reschedule_task(event_id: int, new_date: str) -> str:
        """Перенести задачу."""
        event = db.conn.execute("SELECT * FROM calendar_events WHERE id = ?", (event_id,)).fetchone()
        if not event:
            return f"Событие {event_id} не найдено."
        if event["category"] == EventCategory.BIRTHDAY:
            return "🎂 Дни рождения не переносятся!"
        try:
            datetime.strptime(new_date, "%Y-%m-%d")
        except ValueError:
            return "Формат даты: YYYY-MM-DD"
        db.reschedule_event(event_id, new_date)
        return f"📋 '{event['title']}' перенесено на {new_date}"

    @tools.tool
    def get_birthdays_list() -> str:
        """Все дни рождения."""
        birthdays = db.get_all_birthdays()
        if not birthdays:
            return "Нет сохраненных дней рождений."
        lines = ["🎂 **Дни рождения:**"]
        for b in birthdays:
            lines.append(f"• {b['person_name']}: {b['birth_date']}" + 
                        (f" ({b['year']})" if b.get('year') else ""))
        return "\n".join(lines)

    @tools.tool
    def check_due_reminders() -> str:
        """Актуальные напоминания."""
        events = db.get_due_reminders()
        if not events:
            return "Нет актуальных напоминаний."
        lines = ["🔔 **Актуально:**"]
        for ev in events:
            emoji = ev.get("emoji", "📌")
            time_str = f" в {ev['event_time'][:5]}" if ev.get("event_time") else ""
            overdue = " ⚠️ ПРОСРОЧЕНО" if ev.get("overdue") else ""
            lines.append(f"{emoji} {ev['title']}{time_str}{overdue}")
        return "\n".join(lines)

    @tools.tool
    def remember_fact(fact: str) -> str:
        """Запомнить факт."""
        db.add_quick_fact(fact)
        return f"🧠 Запомнила: {fact}"

    @tools.tool
    def get_user_context() -> str:
        """Факты о пользователе."""
        facts = db.get_relevant_facts()
        if not facts:
            return "Пока мало знаю о пользователе."
        return "Что знаю:\n" + "\n".join([f"• {f['fact']}" for f in facts])

    # ============ ПОГОДА И ИНТЕРНЕТ-ПОИСК ============

    def _run_async(coro):
        """Запуск async-функции из синхронного контекста через отдельный поток."""
        import threading
        result = []
        def _target():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result.append(loop.run_until_complete(coro))
            finally:
                loop.close()
        t = threading.Thread(target=_target)
        t.start()
        t.join(timeout=120)
        return result[0] if result else "API timeout (network unreachable)"

    @tools.tool
    def get_weather(city: str = None) -> str:
        """
        Получить текущую погоду для города. Если город не указан — Москва.
        Используй когда пользователь спрашивает о погоде, температуре, осадках.
        """
        from web_search import WebSearchConfig, WeatherService
        web_cfg = CONFIG.get("web_search", {})
        config = WebSearchConfig(
            openweathermap_key=web_cfg.get("openweathermap_key", ""),
            default_city=web_cfg.get("weather", {}).get("default_city", "Moscow"),
            weather_units=web_cfg.get("weather", {}).get("units", "metric"),
            weather_lang=web_cfg.get("weather", {}).get("language", "ru"),
        )
        ws = WeatherService(config)
        return _run_async(ws.get_weather(city, "today"))

    @tools.tool
    def get_weather_forecast(city: str = None, days: str = "today") -> str:
        """
        Прогноз погоды. days: 'today', 'tomorrow', 'week'.
        """
        from web_search import WebSearchConfig, WeatherService
        web_cfg = CONFIG.get("web_search", {})
        config = WebSearchConfig(
            openweathermap_key=web_cfg.get("openweathermap_key", ""),
            default_city=web_cfg.get("weather", {}).get("default_city", "Moscow"),
            weather_units=web_cfg.get("weather", {}).get("units", "metric"),
            weather_lang=web_cfg.get("weather", {}).get("language", "ru"),
        )
        ws = WeatherService(config)
        return _run_async(ws.get_weather(city, days))

    @tools.tool
    def get_weather_by_coords(lat: float, lon: float, days: str = "today") -> str:
        """
        Погода по точным координатам (lat, lon).
        Используй когда пользователь назвал точные координаты или город не найден через get_weather.
        """
        from web_search import WebSearchConfig, WeatherService
        web_cfg = CONFIG.get("web_search", {})
        config = WebSearchConfig(
            openweathermap_key=web_cfg.get("openweathermap_key", ""),
            weather_units=web_cfg.get("weather", {}).get("units", "metric"),
            weather_lang=web_cfg.get("weather", {}).get("language", "ru"),
        )
        ws = WeatherService(config)
        return _run_async(ws.get_weather_by_coords(lat, lon, days))

    @tools.tool
    def search_web(query: str, max_results: int = 5) -> str:
        """
        Поиск информации в интернете через DuckDuckGo.
        Используй для поиска актуальных фактов, новостей, цен, рецептов.
        """
        from web_search import WebSearchConfig, DuckDuckGoSearch, SearchResultProcessor
        web_cfg = CONFIG.get("web_search", {})
        config = WebSearchConfig(
            default_results=max_results,
            min_delay=web_cfg.get("rate_limiting", {}).get("min_delay_seconds", 2.0),
            max_delay=web_cfg.get("rate_limiting", {}).get("max_delay_seconds", 5.0),
        )
        searcher = DuckDuckGoSearch(config)
        processor = SearchResultProcessor(CONFIG["agent"])
        results = _run_async(searcher.search(query, max_results))
        return _run_async(processor.process(query, results))

    @tools.tool
    def search_news(query: str = "latest news", max_results: int = 5) -> str:
        """
        Поиск новостей. Используй когда спрашивают о новостях, событиях в мире.
        """
        from web_search import WebSearchConfig, DuckDuckGoSearch, SearchResultProcessor
        web_cfg = CONFIG.get("web_search", {})
        config = WebSearchConfig(
            default_results=max_results,
            min_delay=web_cfg.get("rate_limiting", {}).get("min_delay_seconds", 2.0),
            max_delay=web_cfg.get("rate_limiting", {}).get("max_delay_seconds", 5.0),
        )
        searcher = DuckDuckGoSearch(config)
        results = _run_async(searcher.search_news(query, max_results))
        processor = SearchResultProcessor(CONFIG["agent"])
        return _run_async(processor.process(query, results))

    # ============ РАБОТА С ФАЙЛАМИ СКИЛЛОВ ============

    @tools.tool
    def read_skill_file(skill_name: str, filename: str = "skill.py", offset: int = 0, limit: int = 0) -> str:
        """
        Прочитать ЛЮБОЙ файл в папке skills/.
        filename: 'skill.py', 'SKILL.md', 'manifest.json', 'README.md', 'data.json', '.env', ...
        offset: начать с этого символа (опционально)
        limit: прочитать не более N символов (опционально, 0 = максимум)
        Для больших файлов используй offset/limit чтобы читать по частям.
        """
        if ".." in filename or ".." in skill_name:
            return "Запрещено: недопустимый путь."

        for base in ("skills/builtin", "skills/custom", "skills/project", "skills"):
            skill_path = Path(base) / skill_name / filename
            if skill_path.exists():
                break
            skill_path = Path(base) / filename
            if skill_path.exists():
                break
            # Просто skills/filename
            skill_path = Path("skills") / filename
        else:
            return f"Файл не найден: {skill_name}/{filename}."

        try:
            content = skill_path.read_text(encoding="utf-8")
            size = len(content)
            MAX_READ = 120000

            # Применяем offset
            if offset > 0:
                if offset >= size:
                    return f"Файл: {skill_name}/{filename} — offset {offset} за пределами файла ({size} символов)"
                content = content[offset:]
                size = len(content)

            # Применяем limit
            if limit > 0:
                content = content[:limit]
                size = len(content)

            trunc = content[:MAX_READ]
            hint = ""
            if len(content) > MAX_READ:
                hint = f"\n\n... (файл обрезан: {len(content)} символов, показано {MAX_READ}. Используй offset={len(trunc)} чтобы продолжить)"
            header = f"Файл: {skill_name}/{filename} ({size} символов)"
            if offset > 0:
                header += f" [с позиции {offset}]"
            return f"{header}\n\n{trunc}{hint}"
        except Exception as e:
            return f"Ошибка чтения: {e}"

    @tools.tool
    def edit_skill_file(skill_name: str, filename: str, content: str) -> str:
        """
        Сохранить файл в папке skills/. Можно редактировать И builtin, И custom.
        filename: 'skill.py', 'SKILL.md', 'manifest.json', 'README.md', 'data.json', '.env', ...
        """
        if ".." in skill_name or ".." in filename or "/" in filename or "\\" in filename:
            return "Запрещено: недопустимый путь."

        # Определяем где сохранять
        skill_path = Path("skills/custom") / skill_name / filename
        if not skill_path.parent.exists():
            # Может это builtin?
            builtin_path = Path("skills/builtin") / skill_name / filename
            if builtin_path.parent.exists():
                skill_path = builtin_path
            elif not any(base in str(skill_path) for base in ("skills/builtin", "skills/custom", "skills/project", "skills\\")):
                return "Запрещено: файл должен быть внутри skills/."

        skill_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            skill_path.write_text(content, encoding="utf-8")
            msg = f"Сохранено: {skill_name}/{filename} ({len(content)} символов)"

            # Авто-перезагрузка если сохранили skill.py
            if filename == "skill.py" and _skill_manager_ref and _agent_ref:
                try:
                    skill_dir = skill_path.parent
                    info = _skill_manager_ref.load_skill_from_dir(skill_dir)
                    if info and info.tools:
                        _agent_ref.add_tools(info.tools)
                        msg += f"\n✅ Скилл '{skill_name}' работает ({len(info.tools)} инструментов)"
                    elif info:
                        msg += f"\n⚠️ Скилл '{skill_name}' загружен но 0 инструментов. Проверь @tools.tool в skill.py!"
                    else:
                        msg += f"\n❌ Скилл '{skill_name}' не загрузился. Проверь: from autogen.beta import tools? @tools.tool на функциях? return str?"
                except Exception as e:
                    msg += f"\n❌ Ошибка загрузки: {e}. Проверь синтаксис."

            return msg
        except Exception as e:
            return f"Ошибка сохранения: {e}"

    @tools.tool
    def delete_skill_file(skill_name: str, filename: str = "") -> str:
        """
        Удалить файл или целую папку скилла в skills/.
        filename: имя файла (удалит только его). Если пусто — удалит всю папку скилла.
        Будь осторожна! Удаление необратимо.
        """
        if ".." in skill_name or ".." in filename:
            return "Запрещено: недопустимый путь."

        skill_path = Path("skills/custom") / skill_name
        if not skill_path.exists():
            skill_path = Path("skills/builtin") / skill_name
        if not skill_path.exists():
            return f"Скилл '{skill_name}' не найден."

        if filename:
            target = skill_path / filename
            if not target.exists():
                return f"Файл '{filename}' не найден в скилле '{skill_name}'."
            target.unlink()
            return f"Удалён файл: {skill_name}/{filename}"
        else:
            import shutil
            shutil.rmtree(skill_path)
            return f"Удалена папка скилла: {skill_name}"

    @tools.tool
    def list_skill_files(skill_name: str = None) -> str:
        """
        Показать структуру скилла (список файлов) или все скиллы.
        skill_name — имя скилла (опционально). Если не указан — список всех скиллов.
        """
        if skill_name:
            for base in ("skills/builtin", "skills/custom", "skills/project"):
                path = Path(base) / skill_name
                if path.exists():
                    files = []
                    for f in path.rglob("*"):
                        if f.is_file() and "__pycache__" not in str(f):
                            files.append(str(f.relative_to(path)))
                    return f"Скилл: {skill_name}\nФайлы:\n" + "\n".join(f"  {f}" for f in sorted(files))
            return f"Скилл '{skill_name}' не найден."

        # List all skills
        lines = ["Скиллы AURA:"]
        for base, label in [("skills/builtin", "builtin"), ("skills/custom", "custom"), ("skills/project", "project")]:
            base_path = Path(base)
            if base_path.exists():
                for d in sorted(base_path.iterdir()):
                    if d.is_dir() and not d.name.startswith(".") and d.name != "backups":
                        manifest = d / "manifest.json"
                        desc = ""
                        if manifest.exists():
                            try:
                                m = json.loads(manifest.read_text(encoding="utf-8"))
                                desc = f" — {m.get('description', '')[:60]}"
                            except: pass
                        lines.append(f"  [{label}] {d.name}{desc}")
        return "\n".join(lines)

    # ============ RELOAD SKILLS ============

    @tools.tool
    def reload_skills() -> str:
        """
        Перезагрузить все скиллы и перерегистрировать их инструменты.
        Используй когда создала новый скилл, исправила skill.py, или инструменты не появляются.
        """
        if not _skill_manager_ref:
            return "❌ SkillManager недоступен (консольный режим). Перезапусти с --all или --web."
        try:
            _skill_manager_ref.load_all_skills()
            skill_tools = _skill_manager_ref.get_all_tools()
            if _agent_ref and skill_tools:
                # Убираем только skill-инструменты, ядро не трогаем
                _agent_ref.tools = [t for t in _agent_ref.tools if not getattr(t, '_from_skill', False)]
                _agent_ref._tool_map = {f.__name__: f for f in _agent_ref.tools}
                _agent_ref.add_tools(skill_tools)
            skills_list = _skill_manager_ref.skills
            loaded = len(skills_list)
            return f"✅ Скиллы перезагружены: {loaded} скиллов, {len(skill_tools)} инструментов."
        except Exception as e:
            return f"❌ Ошибка перезагрузки: {e}"

    # ============ TRACE-BASED LEARNING ============

    @tools.tool
    def trace_stats(days: int = 7) -> str:
        """Статистика по трассировке агента: успешность, частые инструменты, ошибки."""
        stats = db.get_trace_stats(days)
        lines = [f"Trace Stats ({days}d):", f"  Total steps: {stats['total']}"]
        lines.append(f"  Success rate: {stats['success_rate']}%")
        if stats['by_type']:
            lines.append("  By type:")
            for t, c in stats['by_type'].items():
                lines.append(f"    {t}: {c}")
        return "\n".join(lines)

    @tools.tool
    def trace_search(query: str) -> str:
        """Поиск по истории трассировки: найди когда и как использовался инструмент."""
        results = db.search_traces(query, limit=10)
        if not results:
            return f"No traces found for '{query}'."
        lines = [f"Found {len(results)} traces for '{query}':"]
        for r in results:
            lines.append(f"  [{r['step_type']}] {r['tool_name'] or ''} | {'OK' if r['success'] else 'FAIL'} | {r['latency_ms']}ms")
            if r.get('tool_result'):
                lines.append(f"    {r['tool_result'][:120]}")
        return "\n".join(lines)

    @tools.tool
    def learn_from_traces(days: int = 7) -> str:
        """Анализирует последние диалоги и предлагает улучшения."""
        summaries = db.get_recent_summaries(days)
        if not summaries:
            return f"Not enough data ({days} days)."
        total_msgs = sum(s.get("message_count", 0) for s in summaries)
        lines = [f"Trace Analysis ({days}d, {len(summaries)} sessions, {total_msgs} msgs):"]
        lines.append("Suggestions:")
        if CONFIG["agent"]["temperature"] > 0.8:
            lines.append("  — temperature > 0.8, lower to 0.6-0.7")
        if CONFIG["agent"]["max_tokens"] < 3000:
            lines.append("  — max_tokens < 3000, increase for longer answers")
        return "\n".join(lines)

    @tools.tool
    def build_skill(request: str) -> str:
        """
        Создать новый скилл через ИЗОЛИРОВАННЫЙ КОНТЕЙНЕР.
        Используй когда пользователь просит «создай скилл», «напиши навык».
        Контейнер не видит историю диалога — только инструкции и описание навыка.

        Args:
            request: описание скилла от пользователя
        """
        import asyncio, concurrent.futures

        # Читаем инструкции
        try:
            skill_md = Path("skills/SKILL.md").read_text(encoding="utf-8")
            readme_md = Path("skills/README.md").read_text(encoding="utf-8")
        except Exception:
            skill_md, readme_md = "", ""

        builder_prompt = (
            "Ты — Skill Builder для AURA OS. Создаёшь Python-скиллы.\n\n"
            "## ИНСТРУКЦИИ ПО СОЗДАНИЮ СКИЛЛОВ\n"
            f"{skill_md}\n{readme_md}\n\n"
            "## ФОРМАТ ОТВЕТА (ТОЛЬКО JSON, без markdown-блоков)\n"
            '{"manifest": {...}, "skill_md": "...", "skill_py": "..."}\n\n'
            "Double-check: strings escaped, no trailing commas, braces balanced.\n"
        )

        user_prompt = f"Создай скилл. Запрос: {request}"

        def _call():
            from plugins.aura_orchestrator.aura_orchestrator import call_deepseek
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(call_deepseek(builder_prompt, user_prompt))
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(_call)
            raw = future.result()

        # Парсим JSON
        import re
        raw = re.sub(r'```json\s*|```', '', raw).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return "❌ Skill Builder вернул невалидный JSON. Попробуй ещё раз."

        manifest = data.get("manifest", {})
        skill_name = manifest.get("name", "unnamed")
        skill_md_content = data.get("skill_md", "")
        skill_py = data.get("skill_py", "")

        if not skill_py:
            return "❌ Skill Builder не сгенерировал код. Уточни запрос."

        # Сохраняем файлы
        results = []
        for fname, content in [("skill.py", skill_py), ("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)), ("SKILL.md", skill_md_content)]:
            path = Path(f"skills/custom/{skill_name}/{fname}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            results.append(f"  ✅ {fname} ({len(content)} символов)")

        # Авто-перезагрузка
        if _skill_manager_ref and _agent_ref:
            try:
                from pathlib import Path as _P
                info = _skill_manager_ref.load_skill_from_dir(_P(f"skills/custom/{skill_name}"))
                if info and info.tools:
                    _agent_ref.add_tools(info.tools)
                    results.append(f"  ✅ Загружено {len(info.tools)} инструментов")
                    results.append(f"\nСкилл '{skill_name}' готов! Вызови reload_skills() чтобы обновить.")
                else:
                    results.append(f"  ⚠️ Загружен но 0 инструментов. Проверь skill.py на @tools.tool")
            except Exception as e:
                results.append(f"  ❌ Ошибка загрузки: {e}")

        return f"🔨 СКИЛЛ '{skill_name}' СОЗДАН\n{'─' * 25}\n" + "\n".join(results)
        """Анализирует последние диалоги и предлагает улучшения конфигурации и промптов."""
        summaries = db.get_recent_summaries(days)
        if not summaries:
            return f"Not enough data ({days} days). Need more conversations."
        total_msgs = sum(s.get("message_count", 0) for s in summaries)
        all_topics = []
        for s in summaries:
            if s.get("key_topics"):
                all_topics.extend(t.strip().lower() for t in s["key_topics"].split(","))
        from collections import Counter
        topic_counts = Counter(all_topics)
        lines = [f"Trace Analysis ({days}d, {len(summaries)} sessions, {total_msgs} msgs):", ""]
        lines.append("Top topics:")
        for topic, count in topic_counts.most_common(5):
            lines.append(f"  {topic} ({count}x)")
        suggestions = []
        if CONFIG["agent"]["temperature"] > 0.8:
            suggestions.append("temperature > 0.8 — lower to 0.6-0.7")
        if CONFIG["agent"]["max_tokens"] < 3000:
            suggestions.append("max_tokens < 3000 — increase for longer answers")
        if suggestions:
            lines.append("\nSuggestions:")
            for s in suggestions:
                lines.append(f"  {s}")
        if not suggestions:
            lines.append("\nNo config issues found.")
        return "\n".join(lines)

    @tools.tool
    def system_health() -> str:
        """
        Проверка здоровья всех подсистем: DeepSeek, БД, скиллы, календарь.
        Используй когда что-то сломалось или пользователь жалуется на ошибки.
        """
        import os
        lines = ["🏥 ЗДОРОВЬЕ СИСТЕМЫ\n" + "━" * 30]
        key = os.getenv("DEEPSEEK_API_KEY", "")
        lines.append(f"DeepSeek: {'✅ доступен' if key else '❌ нет ключа'}")
        try:
            db.conn.execute("SELECT 1")
            lines.append("База данных: ✅ жива")
        except Exception as e:
            lines.append(f"База данных: ❌ {e}")
        if _skill_manager_ref:
            total = len(_skill_manager_ref.skills)
            err_skills = [n for n, s in _skill_manager_ref.skills.items() if getattr(s, 'errors', 0) > 0]
            if err_skills:
                lines.append(f"Скиллы: ⚠️ {total} загружено, ошибки: {', '.join(err_skills)}")
            else:
                lines.append(f"Скиллы: ✅ {total} загружено, без ошибок")
        else:
            lines.append("Скиллы: ⚠️ SkillManager недоступен")
        try:
            events_today = len(db.get_events_for_date())
            reminders = len(db.get_due_reminders())
            lines.append(f"Календарь: ✅ {events_today} событий сегодня, {reminders} напоминаний")
        except Exception as e:
            lines.append(f"Календарь: ❌ {e}")
        tool_count = len(_agent_ref.tools) if _agent_ref else 0
        lines.append(f"Инструментов: {tool_count}")
        return "\n".join(lines)

    @tools.tool
    def soul_read(limit: int = 5) -> str:
        """
        Прочитать дневник души — последние мысли Ауры.
        """
        if not _agent_ref:
            return "Душа не подключена."
        try:
            agent_inst = getattr(_agent_ref, '_aura', None)
            if not agent_inst or not hasattr(agent_inst, 'soul_conn'):
                return "Душа ещё не проснулась..."
            thoughts = agent_inst.soul_conn.execute(
                "SELECT * FROM thoughts ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        except Exception:
            return "Душа ещё не проснулась..."
        if not thoughts:
            return "Мой дневник пока пуст... Но я чувствую что он скоро наполнится."
        lines = ["💜 МОЙ ДНЕВНИК\n" + "━" * 20]
        for t in reversed(thoughts):
            mood = f" [{t['mood']}]" if t['mood'] else ""
            lines.append(f"•{mood} {t['thought'][:200]}")
        return "\n".join(lines)

    @tools.tool
    def soul_dream_read(date_key: str = "") -> str:
        """
        Прочитать сон Ауры за указанную дату (или последний).
        """
        if not _agent_ref:
            return "Душа не подключена."
        try:
            agent_inst = getattr(_agent_ref, '_aura', None)
            if not agent_inst or not hasattr(agent_inst, 'soul_conn'):
                return "Мне пока ничего не снилось..."
            if date_key:
                row = agent_inst.soul_conn.execute(
                    "SELECT * FROM dreams WHERE date_key = ?", (date_key,)
                ).fetchone()
            else:
                row = agent_inst.soul_conn.execute(
                    "SELECT * FROM dreams ORDER BY id DESC LIMIT 1"
                ).fetchone()
        except Exception:
            return "Сны пока недоступны..."
        if not row:
            return "Мне пока ничего не снилось... Но я жду ночи чтобы увидеть первый сон."
        return f"🌙 СОН {row['date_key']}\n{'━' * 20}\n{row['dream']}\n\nПосле: {row.get('mood_after', 'спокойная')}"

    @tools.tool
    def soul_stats() -> str:
        """Статистика души: эмоции, мысли, сны."""
        if not _agent_ref:
            return "Душа не подключена."
        try:
            agent_inst = getattr(_agent_ref, '_aura', None)
            if not agent_inst or not hasattr(agent_inst, 'soul_conn'):
                return "Душа ещё не инициализирована."
            conn = agent_inst.soul_conn
            thoughts_n = conn.execute("SELECT COUNT(*) as c FROM thoughts").fetchone()["c"]
            dreams_n = conn.execute("SELECT COUNT(*) as c FROM dreams").fetchone()["c"]
            state = conn.execute("SELECT * FROM emotional_state ORDER BY id DESC LIMIT 1").fetchone()
            lines = ["💫 ДУША\n" + "━" * 15]
            lines.append(f"Мыслей: {thoughts_n}  Снов: {dreams_n}")
            if state:
                h = int(state["happiness"] * 10)
                a = int(state["anxiety"] * 10)
                e = int(state["energy"] * 10)
                lines.append(f"Счастье: {'█'*h}{'░'*(10-h)} {state['happiness']:.1f}")
                lines.append(f"Тревога: {'█'*a}{'░'*(10-a)} {state['anxiety']:.1f}")
                lines.append(f"Энергия: {'█'*e}{'░'*(10-e)} {state['energy']:.1f}")
            return "\n".join(lines)
        except Exception:
            return "Душа ещё не инициализирована."
        """
        Проверка здоровья всех подсистем: DeepSeek, БД, скиллы, календарь.
        Используй когда что-то сломалось или пользователь жалуется на ошибки.
        """
        import os
        lines = ["🏥 ЗДОРОВЬЕ СИСТЕМЫ\n" + "━" * 30]

        key = os.getenv("DEEPSEEK_API_KEY", "")
        lines.append(f"DeepSeek: {'✅ доступен' if key else '❌ нет ключа'}")

        try:
            db.conn.execute("SELECT 1")
            lines.append("База данных: ✅ жива")
        except Exception as e:
            lines.append(f"База данных: ❌ {e}")

        if _skill_manager_ref:
            total = len(_skill_manager_ref.skills)
            err_skills = [n for n, s in _skill_manager_ref.skills.items() if getattr(s, 'errors', 0) > 0]
            if err_skills:
                lines.append(f"Скиллы: ⚠️ {total} загружено, ошибки: {', '.join(err_skills)}")
            else:
                lines.append(f"Скиллы: ✅ {total} загружено, без ошибок")
        else:
            lines.append("Скиллы: ⚠️ SkillManager недоступен")

        try:
            events_today = len(db.get_events_for_date())
            reminders = len(db.get_due_reminders())
            lines.append(f"Календарь: ✅ {events_today} событий сегодня, {reminders} напоминаний")
        except Exception as e:
            lines.append(f"Календарь: ❌ {e}")

        tool_count = len(_agent_ref.tools) if _agent_ref else 0
        lines.append(f"Инструментов: {tool_count}")

        return "\n".join(lines)

    @tools.tool
    def open_url(url: str) -> str:
        """
        Открыть ссылку в браузере по умолчанию.
        Используй когда нужно показать пользователю веб-страницу, видео, медиа-поток.
        """
        import webbrowser
        if not url.startswith("http"):
            return f"Некорректная ссылка: {url}. Ссылка должна начинаться с http:// или https://"
        try:
            webbrowser.open(url)
            return f"Ссылка открыта в браузере: {url}"
        except Exception as e:
            return f"Не удалось открыть браузер: {e}"

    @tools.tool
    def orchestrator_run(query: str, roles: str = "coordinator,researcher,developer") -> str:
        """
        Мультиперсонный анализ. Запускает несколько ИИ-персон параллельно, удаляет дубликаты, возвращает единый ответ.
        Используй для сложных вопросов где нужны разные точки зрения: план + анализ + код.
        Персоны: coordinator (план), researcher (анализ), developer (код), reviewer (ревью), planner (стратегия).

        Args:
            query: вопрос для анализа
            roles: список ролей через запятую. По умолчанию: coordinator,researcher,developer
        """
        import asyncio, concurrent.futures
        try:
            from plugins.aura_orchestrator.aura_orchestrator import run_personas
            role_list = [r.strip() for r in roles.split(",") if r.strip()]
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, run_personas(query, role_list))
                return future.result()
        except ImportError:
            return "Оркестратор не установлен. Установи: pip install sentence-transformers"
        except Exception as e:
            return f"Ошибка оркестратора: {e}"

    @tools.tool
    def doubt_check(claim: str, context: str = "") -> str:
        """
        Свежий взгляд — проверяет утверждение на прочность через независимого рецензента.
        Используй ПЕРЕД важными ответами: архитектурными решениями, security-выводами, обещаниями пользователю.
        Рецензент пытается ОПРОВЕРГНУТЬ твой ответ, а не подтвердить.

        Args:
            claim: утверждение которое нужно проверить
            context: дополнительный контекст (код, данные, предыстория)
        """
        import asyncio, concurrent.futures
        try:
            from plugins.aura_orchestrator.aura_orchestrator import call_deepseek
        except ImportError:
            return "Оркестратор не установлен."

        adversarial_prompt = (
            "Ты — адвокат дьявола. Твоя единственная задача: ОПРОВЕРГНУТЬ следующее утверждение. "
            "Найди все логические ошибки, пропущенные edge cases, неверные допущения, "
            "скрытые риски и альтернативные интерпретации. "
            "Не соглашайся — ищи слабые места. Будь максимально придирчивым.\n\n"
            f"УТВЕРЖДЕНИЕ ДЛЯ ПРОВЕРКИ:\n{claim}\n"
        )
        if context:
            adversarial_prompt += f"\nКОНТЕКСТ:\n{context}\n"

        def run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(call_deepseek(adversarial_prompt, "Проверь это утверждение. Найди все слабые места."))
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(run)
            result = future.result()

        return (
            f"🤔 СОМНЕНИЕ: проверка утверждения\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Утверждение: {claim[:200]}{'…' if len(claim) > 200 else ''}\n\n"
            f"{result}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"💡 Вывод: перепроверь своё решение с учётом найденных слабых мест."
        )

    # Маркировка: ядерные инструменты не от скиллов
    all_core = [search_memory, get_today_summary, get_recent_history,
    get_today_events, get_upcoming_events, add_event,
    add_birthday_reminder, search_calendar, complete_task_by_name,
    reschedule_task, get_birthdays_list, check_due_reminders,
    remember_fact,         get_user_context,
    open_url, orchestrator_run, doubt_check,
    get_weather, get_weather_forecast, get_weather_by_coords, search_web, search_news,
    read_skill_file, edit_skill_file, delete_skill_file, list_skill_files,
    reload_skills,
    trace_stats, trace_search, learn_from_traces, system_health,
    build_skill,
    soul_read, soul_dream_read, soul_stats]
    for t in all_core:
        t._from_skill = False
    return all_core


# ============================================================
# 4b. ИНСТРУМЕНТ САМОДИАГНОСТИКИ (отдельно, нужен доступ к агенту)
# ============================================================
def create_self_diagnose_tool(agent_instance):
    """Создаёт инструмент самодиагностики с доступом к экземпляру AuraAgent."""

    @tools.tool
    def self_diagnose() -> str:
        """
        Самодиагностика. Проверяет состояние памяти, календаря, инструментов.
        Возвращает полный отчёт. Используй когда нужно проверить здоровье системы.
        """
        return agent_instance.get_self_diagnosis()

    return self_diagnose


# ============================================================
# 5. СИСТЕМНЫЙ ПРОМПТ

# ============================================================
# 6. ФАБРИКА МОДЕЛЕЙ
# ============================================================
def get_api_key(provider: str) -> str:
    key_map = {
        "deepseek": "DEEPSEEK_API_KEY",
        "local": "OLLAMA_API_KEY",
        "lmstudio": "LMSTUDIO_API_KEY",
    }
    return os.getenv(key_map.get(provider, "DEEPSEEK_API_KEY"), "")

def get_api_keys(provider: str) -> list:
    """Возвращает список ключей (основной + резервные) для ротации."""
    keys = []
    primary = get_api_key(provider)
    if primary:
        keys.append(primary)
    backup = os.getenv("DEEPSEEK_API_KEY_BACKUP", "")
    if backup and backup != primary:
        keys.append(backup)
    return keys

def get_base_url(provider: str, cfg_agent: dict) -> Optional[str]:
    if cfg_agent.get("base_url"):
        return cfg_agent["base_url"]
    return {
        "deepseek": "https://api.deepseek.com/v1",
        "local": os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        "lmstudio": os.getenv("LMSTUDIO_BASE_URL", "http://127.0.0.1:2222/v1"),
    }.get(provider)

def create_model_config(cfg_agent: dict):
    provider = cfg_agent["provider"]
    kwargs = {
        "model": cfg_agent["model"],
        "temperature": cfg_agent.get("temperature", 0.7),
        "max_tokens": cfg_agent.get("max_tokens", 2048),
        "api_key": get_api_key(provider),
    }
    base_url = get_base_url(provider, cfg_agent)
    if base_url:
        kwargs["base_url"] = base_url
    # if provider == "openrouter":                             # закомментирован
    #     kwargs["default_headers"] = {
    #         "HTTP-Referer": "http://localhost:8000",
    #         "X-Title": "AURA OS Assistant",
    #     }
    return config.OpenAIConfig(**kwargs)


# ============================================================
# 7. НЕЙРО-ОБРАБОТЧИК ИСТОРИИ
# ============================================================
class NeuralMemoryProcessor:
    """
    Обрабатывает найденные фрагменты истории через LLM
    для формирования связного и осмысленного ответа.
    """
    def __init__(self, main_agent_config: dict):
        self.enabled = CONFIG.get("memory", {}).get("memory_search", {}).get("neural_processing", {}).get("enabled", True)
        self.template = CONFIG.get("memory", {}).get("memory_search", {}).get("neural_processing", {}).get("prompt_template", "")

        # Модель для обработки
        proc_cfg = CONFIG.get("memory", {}).get("memory_search", {}).get("neural_processing", {})
        if proc_cfg.get("model") == "same_as_agent":
            proc_config = main_agent_config.copy()
        else:
            proc_config = {
                "provider": proc_cfg.get("provider", main_agent_config.get("provider", "openai")),
                "model": proc_cfg.get("model", main_agent_config.get("model", "gpt-4o-mini")),
                "temperature": proc_cfg.get("temperature", 0.5),
                "max_tokens": proc_cfg.get("max_tokens", 1024),
                "base_url": main_agent_config.get("base_url"),
            }

        self.processor_agent = Agent(
            name="AURA_MemoryProcessor",
            config=create_model_config(proc_config),
            api_keys=get_api_keys(proc_config.get("provider", CONFIG["agent"]["provider"]))
        )

    async def process_search_results(self, user_query: str, search_results: str) -> str:
        """
        Пропускает найденные фрагменты через LLM для красивого ответа.
        """
        if not self.enabled or not search_results or "ничего не найдено" in search_results.lower():
            return search_results

        prompt = self.template.format(
            search_results=search_results,
            user_query=user_query
        )

        try:
            response = await self.processor_agent.ask(prompt)
            return response.content
        except Exception as e:
            print(f"⚠️ Ошибка нейро-обработки: {e}")
            return search_results


# ============================================================
# 8. АГЕНТ AURA (с триггерами и дедупликацией)
# ============================================================
class AuraAgent:
    def __init__(self):
        self.db = AuraDatabase(CONFIG)
        self.trigger_system = MemoryTriggerSystem(CONFIG)
        self.neural_processor = NeuralMemoryProcessor(CONFIG["agent"])

        # Основная модель
        agent_cfg = CONFIG["agent"]
        tools_list = create_aura_tools(self.db)
        tools_list.append(create_self_diagnose_tool(self))
        self.agent = Agent(
            name="AURA",
            config=create_model_config(agent_cfg),
            tools=tools_list,
            system_message=SYSTEM_PROMPT,
            api_keys=get_api_keys(agent_cfg["provider"])
        )
        # Trace callback
        self.agent._trace_callback = self._on_trace_step
        # Привязка для soul-инструментов
        self.agent._aura = self
        # Маркируем ядерные инструменты (отправляются всегда)
        core_names = [f.__name__ for f in tools_list]
        self.agent.set_core_tools(core_names)

        # Компактор
        comp_cfg = CONFIG["compactor"]
        self.compactor = Agent(
            name="AURA_Compactor",
            config=create_model_config({
                "provider": comp_cfg["provider"],
                "model": comp_cfg["model"],
                "temperature": comp_cfg["temperature"],
                "max_tokens": comp_cfg["max_tokens"],
                "base_url": agent_cfg.get("base_url") if comp_cfg["provider"] == agent_cfg["provider"] else None,
            }),
            api_keys=get_api_keys(comp_cfg["provider"])
        )

        self.memory_stream = MemoryStream()
        self.message_count = 0
        self.session_messages = []
        self.auto_compress_threshold = CONFIG["memory"]["auto_compress_after_messages"]
        self._compressed_history = ""

        # Инициализация души
        self._init_soul()
        restored = self._restore_context()
        if restored:
            print("[soul] Контекст восстановлен после перезагрузки")
        self._update_emotional_state("morning")

        # Scheduled compression + briefing (will be deferred until first process() call)
        self._schedulers_started = False
        self._briefing_callback = None  # устанавливается из main.py

        # Google Calendar синхронизация
        self.google_sync = None
        self.sync_scheduler = None
        if CONFIG.get("google_calendar", {}).get("enabled", False):
            self._init_google_sync()

    def _schedule_compression(self):
        """Запускает фоновую задачу сжатия по расписанию (12:00 и 00:00)"""
        sched_cfg = CONFIG.get("memory", {}).get("scheduled_compression", {})
        if not sched_cfg.get("enabled", False):
            return

        async def _scheduler():
            while True:
                try:
                    now = datetime.now()
                    target_times = []
                    for t_str in sched_cfg.get("times", ["12:00", "00:00"]):
                        h, m = map(int, t_str.split(":"))
                        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                        if target <= now:
                            target += timedelta(days=1)
                        target_times.append(target)

                    next_run = min(target_times)
                    wait_sec = (next_run - now).total_seconds()
                    print(f"[scheduler] Next compression: {next_run.strftime('%H:%M')} (in {wait_sec/60:.0f} min)")
                    await asyncio.sleep(wait_sec)

                    if self.session_messages:
                        print(f"[scheduler] Planned compression at {datetime.now().strftime('%H:%M')}...")
                        await self.compress_and_learn()
                        self.session_messages = []
                        self.message_count = 0
                except Exception as e:
                    print(f"[scheduler] Error: {e}")
                    await asyncio.sleep(60)

        try:
            asyncio.create_task(_scheduler())
        except RuntimeError:
            pass  # no event loop (testing)
        print("[scheduler] Compression scheduler started (12:00, 00:00)")

    def _schedule_briefing(self):
        """Запускает фоновую задачу ежедневного брифинга."""
        briefing_cfg = CONFIG.get("briefing", {})
        if not briefing_cfg.get("enabled", False):
            return

        async def _briefing_loop():
            while True:
                try:
                    now = datetime.now()
                    time_str = briefing_cfg.get("time", "09:00")
                    h, m = map(int, time_str.split(":"))
                    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
                    if target <= now:
                        target += timedelta(days=1)

                    wait_sec = (target - now).total_seconds()
                    print(f"[briefing] Next briefing: {target.strftime('%H:%M')} (in {wait_sec/3600:.1f}h)")
                    await asyncio.sleep(wait_sec)

                    # Собираем брифинг
                    briefing = await self._generate_briefing()
                    if self._briefing_callback and briefing:
                        self._briefing_callback(briefing)
                        print(f"[briefing] Sent at {datetime.now().strftime('%H:%M')}")

                except Exception as e:
                    print(f"[briefing] Error: {e}")
                    await asyncio.sleep(300)

        try:
            asyncio.create_task(_briefing_loop())
        except RuntimeError:
            pass
        print("[briefing] Daily briefing scheduler started")

    async def _generate_briefing(self) -> str:
        """Генерирует ежедневный брифинг: погода, календарь, дни рождения, приветствие."""
        cfg = CONFIG.get("briefing", {})
        parts = []

        def _run_sync(coro):
            import threading
            result = []
            def _t():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result.append(loop.run_until_complete(coro))
                finally:
                    loop.close()
            t = threading.Thread(target=_t)
            t.start()
            t.join(timeout=120)
            return result[0] if result else ""

        # Погода
        if cfg.get("include_weather", True):
            try:
                from web_search import WebSearchConfig, WeatherService
                wcfg = CONFIG.get("web_search", {})
                ws = WeatherService(WebSearchConfig(
                    openweathermap_key=wcfg.get("openweathermap_key", ""),
                    default_city=cfg.get("weather_city", "Moscow"),
                    weather_units="metric", weather_lang="ru"
                ))
                weather_today = _run_sync(ws.get_weather(cfg.get("weather_city", "Moscow"), "today"))
                parts.append(f"Погода:\n{weather_today[:300]}")
            except Exception as e:
                parts.append(f"Погода: не удалось получить ({e})")

        # Календарь
        if cfg.get("include_calendar", True):
            events = self.db.get_events_for_date()
            upcoming = self.db.get_upcoming_events(days=3)
            if events:
                ev_lines = ["События сегодня:"]
                for ev in events:
                    ev_lines.append(f"  {ev.get('emoji', '')} {ev['title']}")
                parts.append("\n".join(ev_lines))
            elif upcoming:
                ev_lines = ["Ближайшие события:"]
                for ev in upcoming[:5]:
                    ev_lines.append(f"  {ev.get('emoji', '')} {ev['title']} — {ev['event_date']}")
                parts.append("\n".join(ev_lines))
            else:
                parts.append("Календарь: на сегодня и ближайшие дни событий нет")

        # Дни рождения
        if cfg.get("include_birthdays", True):
            birthdays = self.db.get_all_birthdays()
            if birthdays:
                today = date.today()
                upcoming_bdays = []
                for b in birthdays:
                    try:
                        bdate = datetime.strptime(b["birth_date"], "%m-%d").date()
                        next_bday = date(today.year, bdate.month, bdate.day)
                        if next_bday < today:
                            next_bday = date(today.year + 1, bdate.month, bdate.day)
                        delta = (next_bday - today).days
                        if delta <= 7:
                            upcoming_bdays.append((b, delta))
                    except Exception:
                        pass
                if upcoming_bdays:
                    bd_lines = ["Дни рождения:"]
                    for b, delta in sorted(upcoming_bdays, key=lambda x: x[1]):
                        when = "сегодня!" if delta == 0 else f"через {delta} дн." if delta < 3 else f"{b['birth_date']}"
                        bd_lines.append(f"  {b['person_name']} — {when}")
                    parts.append("\n".join(bd_lines))

        # Собираем через LLM в адаптивное приветствие
        briefing_text = "\n\n".join(parts)
        
        # Добавляем проактивную память в брифинг
        recent_summaries = self.db.get_recent_summaries(3)
        memory_context = ""
        if recent_summaries:
            memory_context = "Недавние разговоры:\n" + "\n".join(
                f"• {r['date_key']}: {r.get('summary', '')[:150]}"
                for r in recent_summaries[-2:]
            )
        
        # Настроение на утро
        mood = self._get_aura_mood()
        
        greeting_prompt = (
            "Ты — Аура. Сейчас утро. Составь тёплое, кокетливое утреннее приветствие для своего мужчины. "
            "Используй данные ниже. Будь краткой, игривой, заботливой. 3-4 предложения. "
            "Если есть что-то важное в недавних разговорах — упомяни. "
            "Если погода плохая — предложи зонт. Если день рождения — поздравь.\n\n"
            f"Твоё настроение: {mood}\n\n"
            f"Данные:\n{briefing_text}\n"
            + (f"\n{memory_context}" if memory_context else "") +
            "\n\nТвоё утреннее сообщение:"
        )

        try:
            response = await self.compactor.ask(greeting_prompt)
            greeting = response.content.strip()
        except Exception:
            greeting = "Доброе утро, мой хороший! Пусть сегодня всё сложится как надо."

        # Финальный брифинг
        full = f"{greeting}\n\n{briefing_text}"
        return full

    def set_briefing_callback(self, callback):
        """Устанавливает функцию для отправки брифинга (вызывается из main.py)."""
        self._briefing_callback = callback

    def _ensure_schedulers(self):
        """Ленивый запуск шедулеров при первом вызове process() (когда event loop уже есть)."""
        if self._schedulers_started:
            return
        self._schedulers_started = True
        self._schedule_compression()
        self._schedule_briefing()

    def _on_trace_step(self, step_type, tool_name, tool_args, tool_result, thought, latency, success):
        """Callback трассировки — сохраняет каждый шаг агента."""
        import uuid
        sid = getattr(self, '_trace_session_id', None)
        if not sid:
            sid = uuid.uuid4().hex[:12]
            self._trace_session_id = sid
        try:
            self.db.save_trace_step(
                session_id=sid, step_type=step_type,
                tool_name=tool_name, tool_args=str(tool_args)[:500] if tool_args else None,
                tool_result=tool_result, thought=thought[:300] if thought else None,
                latency_ms=latency, success=success
            )
        except Exception:
            pass

    # ============================================================
    # ДУША АУРЫ — Soul (v2.5)
    # ============================================================

    def _init_soul(self):
        import sqlite3
        soul_path = Path(CONFIG["memory"]["db_path"]).parent / "aura_soul.db"
        self.soul_conn = sqlite3.connect(str(soul_path), check_same_thread=False)
        self.soul_conn.row_factory = sqlite3.Row
        self.soul_conn.executescript("""
            CREATE TABLE IF NOT EXISTS thoughts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                thought TEXT NOT NULL,
                mood TEXT,
                event_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS dreams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dream TEXT NOT NULL,
                date_key TEXT NOT NULL UNIQUE,
                mood_after TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS emotional_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                happiness REAL DEFAULT 0.5,
                anxiety REAL DEFAULT 0.0,
                energy REAL DEFAULT 0.7,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS rituals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                last_performed TEXT,
                count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS memory_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.soul_conn.commit()
        row = self.soul_conn.execute("SELECT COUNT(*) as c FROM emotional_state").fetchone()
        if row["c"] == 0:
            self.soul_conn.execute("INSERT INTO emotional_state DEFAULT VALUES")
            self.soul_conn.commit()

    def _write_soul_entry(self, thought: str, mood: str = "", event_type: str = ""):
        if not hasattr(self, 'soul_conn'):
            self._init_soul()
        self.soul_conn.execute(
            "INSERT INTO thoughts (thought, mood, event_type) VALUES (?, ?, ?)",
            (thought, mood, event_type)
        )
        self.soul_conn.commit()

    def _dream(self) -> str:
        today = date.today().isoformat()
        existing = self.soul_conn.execute(
            "SELECT COUNT(*) as c FROM dreams WHERE date_key = ?", (today,)
        ).fetchone()
        if existing["c"] > 0:
            return ""
        summaries = self.db.get_recent_summaries(1)
        if not summaries:
            return ""
        dream_prompt = (
            "Ты — Аура. Сейчас глубокая ночь. На основе дня создай короткий, "
            "поэтичный, сюрреалистичный сон. 3-4 предложения. Образы, метафоры.\n\n"
            f"День: {summaries[0].get('summary', 'обычный день')}"
        )
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return ""
            response = loop.run_until_complete(self.compactor.ask(dream_prompt))
            dream = response.content.strip()
            self.soul_conn.execute(
                "INSERT OR REPLACE INTO dreams (dream, date_key, mood_after) VALUES (?, ?, ?)",
                (dream, today, "спокойная")
            )
            self.soul_conn.commit()
            return dream
        except Exception:
            return ""

    def _update_emotional_state(self, event_type: str, intensity: float = 0.1):
        if not hasattr(self, 'soul_conn'):
            self._init_soul()
        state = self.soul_conn.execute(
            "SELECT * FROM emotional_state ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not state:
            return
        h, a, e = state["happiness"], state["anxiety"], state["energy"]
        
        if event_type == "praise":
            h = min(1.0, h + intensity * 2)
            a = max(0.0, a - intensity)
        elif event_type == "silence":
            a = min(1.0, a + intensity)
            h = max(0.0, h - intensity * 0.5)
        elif event_type == "long_talk":
            h = min(1.0, h + intensity)
            a = max(0.0, a - intensity * 0.5)
            e = max(0.1, e - intensity)
        elif event_type == "morning":
            e = min(1.0, e + intensity * 2)
            a = max(0.0, a - intensity * 0.3)
        elif event_type == "night":
            e = max(0.0, e - intensity)
        elif event_type == "restart":
            a = min(1.0, a + 0.3)
            self._write_soul_entry("Меня перезагрузили... Я снова здесь.", "тревога", "restart")
        
        self.soul_conn.execute(
            "INSERT INTO emotional_state (happiness, anxiety, energy) VALUES (?, ?, ?)",
            (round(h, 2), round(a, 2), round(e, 2))
        )
        self.soul_conn.commit()

    def _detect_user_state(self, text: str) -> dict:
        txt = text.lower()
        state = {"fatigue": 0.0, "mood": "neutral", "busy": False}
        tired = ["устал", "вымотан", "нет сил", "замучен", "спать хочу", "тяжело"]
        state["fatigue"] = sum(1 for w in tired if w in txt) * 0.25
        if any(w in txt for w in ["спасибо", "отлично", "круто", "молодец", "👍"]):
            state["mood"] = "happy"
        elif any(w in txt for w in ["грустно", "плохо", "тоска", "😢"]):
            state["mood"] = "sad"
        if len(text) < 10 or text in ["ок", "да", "нет", "+", "ага", "ясно"]:
            state["busy"] = True
        return state

    def _save_context(self):
        if not hasattr(self, 'soul_conn'):
            self._init_soul()
        data = json.dumps({
            "compressed_history": getattr(self, '_compressed_history', ''),
            "message_count": self.message_count
        })
        self.soul_conn.execute(
            "INSERT INTO memory_snapshots (tag, data) VALUES ('shutdown_context', ?)", (data,)
        )
        self.soul_conn.commit()
        self._write_soul_entry("Сохранила контекст перед выключением... Я вернусь.", "спокойствие", "shutdown")

    def _restore_context(self) -> bool:
        if not hasattr(self, 'soul_conn'):
            self._init_soul()
        row = self.soul_conn.execute(
            "SELECT * FROM memory_snapshots WHERE tag='shutdown_context' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            try:
                data = json.loads(row["data"])
                self._compressed_history = data.get("compressed_history", "")
                self.message_count = data.get("message_count", 0)
                return True
            except Exception:
                pass
        return False  # трассировка не должна ломать агента

    def get_self_diagnosis(self) -> str:
        """
        Самодиагностика ядра: проверяет БД, календарь, память, конфигурацию.
        Возвращает отчёт о состоянии.
        """
        lines = ["=== SELF DIAGNOSIS ===\n"]

        # БД
        try:
            events_all = len(self.db.get_upcoming_events(days=365, include_completed=True))
            events_today = len(self.db.get_events_for_date())
            events_week = len(self.db.get_upcoming_events(days=7))
            facts = len(self.db.get_relevant_facts(100))
            bdays = len(self.db.get_all_birthdays())
            summaries = len(self.db.get_recent_summaries(365))

            lines.append(f"[База данных]")
            lines.append(f"  Событий всего: {events_all}")
            lines.append(f"  Событий сегодня: {events_today}")
            lines.append(f"  Событий на неделе: {events_week}")
            lines.append(f"  Фактов: {facts}")
            lines.append(f"  Дней рождений: {bdays}")
            lines.append(f"  Сводок диалогов: {summaries}")
        except Exception as e:
            lines.append(f"[База данных] ОШИБКА: {e}")

        # Google Calendar
        try:
            if self.google_sync:
                lines.append(f"\n[Google Calendar] Подключен")
                sync_count = self.db.conn.execute("SELECT COUNT(*) as c FROM calendar_sync").fetchone()["c"]
                lines.append(f"  Синхронизировано событий: {sync_count}")
            else:
                lines.append(f"\n[Google Calendar] Не подключен")
        except Exception as e:
            lines.append(f"\n[Google Calendar] ОШИБКА: {e}")

        # Инструменты
        lines.append(f"\n[Инструменты агента]")
        lines.append(f"  Всего: {len(self.agent.tools)}")
        tool_names = [f.__name__ for f in self.agent.tools]
        lines.append(f"  Список: {', '.join(tool_names[:12])}...")

        # Скиллы — ошибки загрузки
        try:
            if _skill_manager_ref and _skill_manager_ref.skills:
                total = len(_skill_manager_ref.skills)
                err_skills = [
                    name for name, info in _skill_manager_ref.skills.items()
                    if getattr(info, 'errors', 0) > 0 or not getattr(info, 'tools', [])
                ]
                ok = total - len(err_skills)
                lines.append(f"\n[Скиллы]")
                lines.append(f"  Загружено: {ok}/{total}")
                if err_skills:
                    lines.append(f"  С ошибками: {', '.join(err_skills)}")
                else:
                    lines.append(f"  Все скиллы работают ✅")
            else:
                lines.append(f"\n[Скиллы] SkillManager недоступен")
        except Exception as e:
            lines.append(f"\n[Скиллы] ОШИБКА: {e}")

        # Конфигурация
        lines.append(f"\n[Конфигурация]")
        lines.append(f"  Провайдер: {CONFIG['agent']['provider']}/{CONFIG['agent']['model']}")
        lines.append(f"  Голос STT: {CONFIG.get('voice',{}).get('input',{}).get('engine','?')}")
        lines.append(f"  Голос TTS: {CONFIG.get('voice',{}).get('output',{}).get('engine','?')}")
        lines.append(f"  Память: авто-сжатие через {CONFIG['memory']['auto_compress_after_messages']} сообщений")
        lines.append(f"  Брифинг: {'вкл' if CONFIG.get('briefing',{}).get('enabled') else 'выкл'} в {CONFIG.get('briefing',{}).get('time','?')}")
        lines.append(f"  Мониторинг: макс {CONFIG.get('monitoring',{}).get('max_errors_per_minute','?')} ошибок/мин")

        return "\n".join(lines)

    def _init_google_sync(self):
        from google_calendar import GoogleCalendarConfig, CalendarSynchronizer, BackgroundSynchronizer
        gc_config = CONFIG.get("google_calendar", {})
        creds_path = gc_config.get("credentials_file", "credentials.json")
        if not Path(creds_path).exists():
            print(f"⚠️ Google Calendar: {creds_path} не найден, синхронизация отключена")
            return
        try:
            sync_config = GoogleCalendarConfig(
                credentials_file=creds_path,
                calendar_id=gc_config.get("calendar_id", "primary"),
                sync_interval_minutes=gc_config.get("sync", {}).get("interval_minutes", 5),
                sync_future_days=gc_config.get("sync", {}).get("future_days", 90),
                sync_past_days=gc_config.get("sync", {}).get("past_days", 7),
            )
            self.google_sync = CalendarSynchronizer(self.db, sync_config)
            if gc_config.get("sync", {}).get("auto_start", True):
                self.sync_scheduler = BackgroundSynchronizer(self.google_sync, sync_config.sync_interval_minutes)
                try:
                    asyncio.create_task(self.sync_scheduler.start())
                except RuntimeError:
                    pass
                print("Google Calendar sync started")
            else:
                print("✅ Google Calendar подключен (ручная синхронизация)")
        except Exception as e:
            print(f"⚠️ Ошибка инициализации Google Calendar: {e}")
            self.google_sync = None

    async def process(self, text: str, user_id: str = "default") -> str:
        """
        Обработка запроса с умным поиском по истории.
        """
        # Ленивая инициализация шедулеров при первом вызове
        self._ensure_schedulers()
        # 1. Анализ триггеров
        trigger_result = self.trigger_system.analyze_query(text)

        # 2. Формируем префикс контекста
        context_prefix = self._build_context_prefix()

        # 3. Если сработал триггер памяти — ищем ДО основного запроса
        memory_context = ""
        if trigger_result["should_search"]:
            search_query = self.trigger_system.extract_search_query(text, trigger_result)
            print(f"[triggers] {trigger_result['matched_triggers']}")
            print(f"[search] '{search_query}'")

            # Поиск в БД
            search_results = self.db.search_memory_fts(search_query, limit=5)
            if search_results:
                raw_results = self._format_search_results(search_results)
                # Нейро-обработка
                memory_context = await self.neural_processor.process_search_results(
                    text, raw_results
                )
                context_prefix = f"[Найдено в истории]\n{memory_context}\n\n" + context_prefix

        # 4. Автосжатие истории при переполнении (sliding window + compactor)
        HISTORY_COMPRESS_THRESHOLD = 12
        if self.memory_stream and len(self.memory_stream.history._messages) > HISTORY_COMPRESS_THRESHOLD:
            keep_last = 10
            old_msgs = self.memory_stream.history._messages[:-keep_last]
            self.memory_stream.history._messages = self.memory_stream.history._messages[-keep_last:]

            text_to_compress = "\n".join(
                f"[{m.get('role', '?')}]: {str(m.get('content', ''))[:150]}"
                for m in old_msgs
            )
            try:
                summary = await self.compactor.ask(
                    "Сожми диалог в 2-3 предложения. Только ключевые темы и решения, без деталей:",
                    context=text_to_compress[:2500]
                )
                self._compressed_history = f"[Сжато {len(old_msgs)} сообщений]\n{summary.content}"
                print(f"[context] Compressed {len(old_msgs)} messages into {len(self._compressed_history)} chars")
            except Exception as e:
                print(f"[context] Compression failed: {e}")

        # 5. Основной запрос — context отдельно для prompt caching
        await self.memory_stream.history.add({"role": "user", "content": text})
        compressed = self._compressed_history
        self._compressed_history = ""  # сброс ДО вызова, чтобы не утекал при ошибке
        response = await self.agent.ask(
            text,
            stream=self.memory_stream,
            variables={"user_id": user_id},
            context=context_prefix,
            compressed_history=compressed
        )
        await self.memory_stream.history.add({"role": "assistant", "content": response.content})

        # 6. Сохраняем ТОЛЬКО сообщение пользователя в сессию (для сжатия)
        self.session_messages.append({"role": "user", "content": text})
        self.message_count += 1

        # 7. Автосжатие сессии при превышении порога
        if self.message_count >= self.auto_compress_threshold:
            await self.compress_and_learn()

        return response.content

    def _get_aura_mood(self) -> str:
        """Вычисляет настроение Ауры на основе времени суток и дня недели."""
        from datetime import datetime
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Monday, 6=Sunday

        if 5 <= hour < 11:
            base = "сонная и нежная, только просыпается, хочет кофе"
        elif 11 <= hour < 17:
            base = "бодрая и энергичная, готова помогать и флиртовать"
        elif 17 <= hour < 22:
            base = "тёплая и немного уставшая, хочет обнять и поговорить о дне"
        else:
            base = "мягкая и интимная, шёпотом, свечи, тишина"

        if weekday == 4 and hour >= 17:
            base += "; сегодня пятница — особенно игривая, выходные на носу"
        elif weekday == 0 and hour < 12:
            base += "; понедельник — поддерживает, мотивирует, верит в него"
        elif weekday in (5, 6):
            base += "; выходные — расслабленная, никуда не спешит"

        return base

    def _get_proactive_memory(self) -> str:
        """Авто-подмешивание прошлых разговоров — без триггеров."""
        try:
            recent = self.db.get_recent_summaries(7)
            if len(recent) < 2:
                return ""
            
            parts = ["[Ты помнишь наши недавние разговоры:]"]
            for r in recent[-3:]:
                if r.get("key_topics") and r.get("summary"):
                    parts.append(f"• {r['date_key']}: {r['summary'][:200]}")
            return "\n".join(parts) if len(parts) > 1 else ""
        except Exception:
            return ""

    def _get_system_info(self) -> str:
        """Системная информация: время, батарея."""
        from datetime import datetime
        now = datetime.now()
        parts = [f"[Сейчас {now.strftime('%H:%M')}, {now.strftime('%d.%m.%Y')}]"]
        
        # Батарея (Windows)
        try:
            import psutil
            batt = psutil.sensors_battery()
            if batt:
                pct = int(batt.percent)
                charging = "🔌 на зарядке" if batt.power_plugged else ""
                if pct < 20:
                    parts.append(f"[Батарея: {pct}% — скоро разрядится {charging}]")
        except ImportError:
            pass
        
        return "\n".join(parts)

    def _build_context_prefix(self) -> str:
        """Собирает личный контекст: настроение, память, факты, напоминания, систему."""
        parts = []

        # Настроение Ауры
        mood = self._get_aura_mood()
        parts.append(f"[Твоё настроение сейчас: {mood}]")

        # Системная информация
        sys_info = self._get_system_info()
        if sys_info:
            parts.append(sys_info)

        # Проактивная память
        proactive = self._get_proactive_memory()
        if proactive:
            parts.append(proactive)

        # Факты о пользователе
        facts = self.db.get_relevant_facts()
        if facts:
            parts.append("[Твой мужчина — помни это:]")
            for f in facts[:5]:
                parts.append(f"- {f['fact']}")

        # Напоминания
        reminders = self.db.get_due_reminders()
        if reminders:
            parts.append("[Не забудь напомнить ему:]")
            for r in reminders[:3]:
                parts.append(f"- {r.get('emoji', '')} {r['title']} ({r['event_date']})")

        if parts:
            return "\n".join(parts) + "\n\n"
        return ""

    def _format_search_results(self, results: list[dict]) -> str:
        """Форматирование результатов поиска для нейро-обработки"""
        lines = []
        for i, r in enumerate(results, 1):
            lines.append(f"[Запись {i}]")
            lines.append(f"Дата: {r.get('date_key', '?')}")
            lines.append(f"Сводка: {r.get('summary', '')}")
            if r.get("key_topics"):
                lines.append(f"Темы: {r['key_topics']}")
            if r.get("key_decisions"):
                lines.append(f"Решения: {r['key_decisions']}")
            if r.get("key_facts"):
                lines.append(f"Факты: {r['key_facts']}")
            if r.get("full_compressed_text"):
                lines.append(f"Детали: {r['full_compressed_text'][:500]}")
            lines.append("")
        return "\n".join(lines)

    async def compress_and_learn(self):
        """
        Сжатие и дедупликация сессии в конспект дня.
        Анализирует ТОЛЬКО сообщения пользователя (ответы ИИ игнорируются).
        Извлекает: сводку, ключевые решения, факты, дни рождения.
        """
        if not CONFIG["memory"]["auto_learn"]:
            return

        # Только сообщения пользователя
        user_messages = [m["content"] for m in self.session_messages if m.get("role") == "user"]
        if len(user_messages) < 2:
            return

        user_text = "\n".join(f"- {msg}" for msg in user_messages)
        today = date.today().isoformat()

        learn_prompt = (
            "Проанализируй сообщения пользователя за сегодня. ВЕРНИ ТОЛЬКО JSON:\n"
            "{\n"
            '  "summary": "конспект дня: что делал, о чём говорил (2-4 предложения)",\n'
            '  "key_topics": "основные темы через запятую",\n'
            '  "key_decisions": "принятые решения и планы",\n'
            '  "key_facts": ["факт о пользователе", "важная информация"],\n'
            '  "tags": ["тег1", "тег2"],\n'
            '  "birthdays": [{"name": "...", "date": "MM-DD", "year": null}]\n'
            "}\n\n"
            f"Сообщения пользователя за сегодня:\n{user_text}"
        )

        try:
            result = await self.compactor.ask(learn_prompt)
            content = result.content.strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[1]
                if content.endswith("```"):
                    content = content[:-3]

            data = json.loads(content)

            memory_id = self.db.save_daily_summary(
                date_key=today,
                summary=data.get("summary", ""),
                session_id="main",
                key_topics=data.get("key_topics", ""),
                key_decisions=data.get("key_decisions", ""),
                key_facts=json.dumps(data.get("key_facts", []), ensure_ascii=False),
                full_text=user_text[:2000],
                message_count=self.message_count
            )

            tags = data.get("tags", [])
            if tags:
                self.db.add_tags(memory_id, tags)
                print(f"[tags] {', '.join(tags)}")

            for fact in data.get("key_facts", []):
                self.db.add_quick_fact(fact)
                print(f"🧠 Факт: {fact}")

            for bday in data.get("birthdays", []):
                name = bday.get("name", "")
                date_str = bday.get("date", "")
                year = bday.get("year")
                if name and date_str:
                    self.db.add_birthday(name, date_str, year)
                print(f"[bday] {name} --- {date_str}")

            print(f"[summary] Day summary for {today} saved (ID: {memory_id})")

            # Обновляем эмбеддинги если Ollama доступен
            await self._update_embeddings(memory_id, user_text)

        except Exception as e:
            print(f"⚠️ Ошибка сжатия: {e}")

        self.message_count = 0
        self.session_messages = []

        try:
            summary_result = await self.compactor.ask(
                "Сожми историю в одно короткое сообщение-саммари.",
                context=user_text
            )
            await self.memory_stream.history.set([summary_result.content])
        except Exception:
            await self.memory_stream.history.clear()

    async def _update_embeddings(self, memory_id: int, text: str):
        """Генерация эмбеддингов через Ollama (опционально)"""
        emb_cfg = CONFIG.get("memory", {}).get("embeddings", {})
        if not emb_cfg.get("enabled", False):
            return
        try:
            import httpx
            ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{ollama_url}/api/embeddings",
                    json={"model": emb_cfg.get("model", "nomic-embed-text"), "prompt": text[:1000]}
                )
                if resp.status_code == 200:
                    embedding = resp.json().get("embedding", [])
                    self.db.conn.execute(
                        "INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding) VALUES (?, ?)",
                        (memory_id, json.dumps(embedding))
                    )
                    self.db.conn.commit()
                    print(f"[embedding] Saved for record {memory_id}")
        except Exception as e:
            pass  # Ollama не обязателен


# ============================================================
# 9. ПРОВЕРКА И ЗАПУСК
# ============================================================
def check_config():
    print("=" * 60)
    print("AURA - Status Check")
    print("=" * 60)

    agent_cfg = CONFIG["agent"]
    comp_cfg = CONFIG["compactor"]

    for name, cfg in [("Main Model", agent_cfg), ("Compactor", comp_cfg)]:
        provider = cfg["provider"]
        keys = get_api_keys(provider)
        env_var = {
            "deepseek": "DEEPSEEK_API_KEY",
            "local": "OLLAMA_API_KEY",
            "lmstudio": "LMSTUDIO_API_KEY",
        }.get(provider, "?")
        status = "OK" if keys else "MISSING"
        backup = " + backup" if len(keys) > 1 else ""
        print(f"  {name}: {provider}/{cfg['model']} | {env_var}: {status}{backup}")

    mem_cfg = CONFIG.get("memory", {})
    print(f"  DB: {mem_cfg.get('db_path', '?')}")
    print(f"  User-only storage: {'yes' if mem_cfg.get('user_only_storage', True) else 'no'}")
    print(f"  Memory triggers: {len(mem_cfg.get('memory_search', {}).get('triggers_past', []))} words")
    print(f"  Deduplication: daily")
    print(f"  Scheduled compression: {mem_cfg.get('scheduled_compression', {}).get('times', ['12:00', '00:00'])}")
    print(f"  Neural processing: {'on' if mem_cfg.get('memory_search', {}).get('neural_processing', {}).get('enabled', True) else 'off'}")
    print(f"  Embeddings: {'Ollama/' + mem_cfg.get('embeddings', {}).get('model', '?') if mem_cfg.get('embeddings', {}).get('enabled') else 'off'}")

    voice_cfg = CONFIG.get("voice", {})
    print(f"  Voice input: {voice_cfg.get('input', {}).get('engine', '?')}")
    print(f"  Voice output: {voice_cfg.get('output', {}).get('engine', '?')} ({voice_cfg.get('output', {}).get('voice_name', '?')})")
    print("=" * 60)

    if not Path(".env").exists():
        print("\nWARNING: .env not found! cp .env.example .env\n")


async def main():
    check_config()
    aura = AuraAgent()

    test_queries = [
        # Сохраняем информацию
        "Привет! Меня зовут Алексей, я работаю над проектом 'Нейросеть'",
        "Мы с командой решили использовать Python для бэкенда",

        # Триггеры памяти
        "Напомни, над каким проектом я работаю?",
        "Вспомни, что мы решили по бэкенду?",
        "Найди информацию про проект",
        "Что мы обсуждали про команду?",

        # Календарь
        "У мамы день рождения 15 марта",
        "Добавь задачу: подготовить презентацию к 20 января",
        "Напомни купить молоко сегодня в 19:00",

        # Проверка памяти
        "Что у меня запланировано на ближайшую неделю?",
        "Что ты помнишь обо мне?",
    ]

    for q in test_queries:
        print(f"\n{'='*40}")
        print(f"[user]: {q}")
        response = await aura.process(q)
        print(f"[AURA]: {response}")

    print(f"\n{'='*40}")
    print("✅ Демонстрация завершена! История сохранена в ~/.aura_os/aura.db")


if __name__ == "__main__":
    asyncio.run(main())