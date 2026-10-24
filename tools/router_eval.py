# -*- coding: utf-8 -*-
"""Golden set для tool-router: Recall@K на реальных запросах.

Ожидание — список допустимых подстрок в именах инструментов (у запроса может
быть несколько валидных инструментов). Считаем только те кейсы, где нужный
инструмент НЕ входит в always-on ядро — иначе метрика завышена.

Запуск: python tools/router_eval.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from loguru import logger

logger.remove()  # не шуметь загрузкой скиллов

from autogen.beta.agent import Agent, DEFAULT_ALWAYS_ON, _is_greeting
from autogen.beta.config import OpenAIConfig
from aura_core import CONFIG, create_aura_tools
from database import AuraDatabase
from skill_manager import SkillManager

# (запрос, [допустимые подстроки имён инструментов])
GOLDEN = [
    ("сделай скриншот экрана", ["screenshot"]),
    ("какие окна сейчас открыты", ["list_windows"]),
    ("отправь последний скриншот в телеграм", ["telegram_send_photo"]),
    ("найди свежие заказы на фрилансе", ["hunter_"]),
    ("покажи мои заказы", ["hunter_orders", "freelance_list"]),
    ("включи радио", ["radio"]),
    ("какой у меня гороскоп", ["natal_chart", "current_sky", "moon_phase"]),
    ("сделай инфографику", ["ig_create"]),
    ("покажи список скиллов", ["list_skill_files"]),
    ("прочитай файл skill.py", ["read_skill_file"]),
    ("напиши код на python", ["project_", "start_code_session"]),
    ("запусти тесты проекта", ["run_all_tests", "run_smoke_test"]),
    ("какие акции растут", ["get_stock_price", "analyze_stock"]),
    ("напомни выпить воды", ["care_remind_water"]),
    ("какое сегодня число", ["get_today_date"]),
    ("запусти проект", ["project_build"]),
    ("перезагрузи скиллы", ["reload_skills"]),
    ("покажи мои дни рождения", ["get_birthdays_list"]),
    ("дай прогноз погоды на неделю", ["get_weather_forecast"]),
    ("покажи статистику души", ["soul_stats"]),
    ("запиши настроение", ["record_mood"]),
    ("найди ключи API", ["hunt_key", "list_api_keys"]),
]

NEGATIVE = ["привет", "доброе утро"]


def build_agent():
    db = AuraDatabase(CONFIG)
    core = create_aura_tools(db)
    core_names = [f.__name__ for f in core]

    sm = SkillManager()
    sm.load_all_skills()
    skill_tools, triggers = sm.get_tools_with_triggers()

    cfg = OpenAIConfig(model="t", api_key="sk-test", base_url="https://x/v1")
    agent = Agent(config=cfg, tools=list(core) + list(skill_tools), system_message="")
    agent.set_core_tools(core_names)
    agent.add_tools([], triggers)
    return agent


def schema_chars(agent, names):
    total = 0
    for n in names:
        fn = agent._tool_map.get(n)
        if fn:
            total += len(json.dumps(
                {"name": n, "description": (fn.__doc__ or "")[:300]},
                ensure_ascii=False,
            ))
            total += len(json.dumps(
                list((fn.__annotations__ or {}).keys()), ensure_ascii=False))
    return total


def run(agent, cap):
    hits, misses, counts, chars = 0, [], [], 0
    for query, expected in GOLDEN:
        selected = agent._select_tool_names(query, cap=cap)
        names = {n.lower() for n in selected}
        hit = any(exp.lower() in n for exp in expected for n in names)
        hits += int(hit)
        counts.append(len(selected))
        chars += schema_chars(agent, selected)
        if not hit:
            misses.append((query, expected, sorted(selected)))
    neg = [len(agent._select_tool_names(q)) for q in NEGATIVE]
    recall = hits / len(GOLDEN) * 100
    return {
        "cap": cap,
        "recall": recall,
        "hits": hits,
        "avg_tools": sum(counts) / len(counts),
        "max_tools": max(counts),
        "avg_chars": chars / len(GOLDEN),
        "neg_tools": neg,
        "misses": misses,
    }


def main():
    agent = build_agent()
    total = len(agent.tools)
    always_on = {n for n in DEFAULT_ALWAYS_ON if n in agent._tool_map}
    print(f"Инструментов всего: {total} | always-on: {len(always_on)} (+find_tools)")
    print(f"Golden set: {len(GOLDEN)} запросов, негативных: {len(NEGATIVE)}\n")

    results = [run(agent, cap) for cap in (16, 22, 28)]
    for r in results:
        print(f"cap={r['cap']:>2}: Recall@K {r['hits']}/{len(GOLDEN)} = "
              f"{r['recall']:.0f}% | tools avg {r['avg_tools']:.1f} "
              f"max {r['max_tools']} | схем ~{r['avg_chars'] / 1000:.1f}k симв. | "
              f"на приветствие {r['neg_tools']}")

    best = max(results, key=lambda r: (r["recall"], -r["avg_tools"]))
    print(f"\nЛучший по recall/экономии: cap={best['cap']}")
    if best["misses"]:
        print("\nПРОМАХИ:")
        for query, expected, sample in best["misses"]:
            print(f"  «{query}» → ждали {expected}; было: {sample}")


if __name__ == "__main__":
    main()
