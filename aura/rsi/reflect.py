# -*- coding: utf-8 -*-
"""M2: Reflection Engine — разбор трейса и гипотезы улучшений.

Вход: трейс сессии + top-K уроков из вики.
Выход: строгий JSON (problems/hypotheses/suggested_mutations), каждая
проблема обязана ссылаться на event_id из трейса.
"""
import json
import os
import re
import uuid
from datetime import datetime
from pathlib import Path

from .config import load_config, rsi_paths
from .trace import TraceLogger
from .wiki import ExperienceWiki

PROMPT_FALLBACK = """Ты — рефлексивный модуль AURA OS. Проанализируй трейс сессии.
Найди реальные проблемы (провалы инструментов, повторы, игнор контекста,
лишние шаги). Каждая проблема ОБЯЗАНА ссылаться на event_id из трейса.
Предложи гипотезы и мутации только по whitelisted-файлам.
Ответ — ТОЛЬКО JSON:
{"problems":[{"id":"p1","statement":"...","evidence":["evt_..."],"impact":"high|medium|low"}],
 "hypotheses":[{"id":"h1","statement":"...","target_file":"...","confidence":0.0}],
 "suggested_mutations":[{"hypothesis_id":"h1","target_file":"...","change_summary":"..."}]}
"""


class ReflectionError(ValueError):
    pass


def _strip_fences(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class ReflectionEngine:
    def __init__(self, wiki: ExperienceWiki = None, root: str = None,
                 llm=None, config: dict = None):
        self.cfg = config or load_config()
        self.root = Path(root) if root else rsi_paths()["reflections"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.trace = TraceLogger()
        self.wiki = wiki if wiki is not None else ExperienceWiki()
        self.llm = llm  # async callable(system, user) -> str

    def _prompt_path(self) -> Path:
        return rsi_paths()["prompts"] / "reflect.md"

    def _system_prompt(self) -> str:
        try:
            path = self._prompt_path()
            if path.exists():
                return path.read_text(encoding="utf-8")
        except Exception:
            pass
        return PROMPT_FALLBACK

    async def _default_llm(self, system: str, user: str) -> str:
        key = os.getenv("DEEPSEEK_API_KEY", "")
        if not key:
            raise ReflectionError("DEEPSEEK_API_KEY не задан — рефлексия недоступна")
        import openai
        from config_manager import get as cfg_get

        rc = self.cfg.get("reflection", {})
        client = openai.AsyncOpenAI(
            api_key=key,
            base_url=cfg_get("agent.base_url", "https://api.deepseek.com/v1"),
            timeout=90,
        )
        resp = await client.chat.completions.create(
            model=rc.get("model") or cfg_get("agent.model", "deepseek-flash"),
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=float(rc.get("temperature", 0.2)),
            max_tokens=int(rc.get("max_tokens", 1800)),
        )
        return resp.choices[0].message.content or ""

    def _validate(self, data: dict, valid_ids: set) -> dict:
        if not isinstance(data, dict):
            raise ReflectionError("ответ не JSON-объект")

        problems, skipped = [], 0
        for p in data.get("problems", []) or []:
            if not isinstance(p, dict):
                continue
            evidence = [e for e in (p.get("evidence") or []) if e in valid_ids]
            if not evidence:
                skipped += 1
                continue
            problems.append({
                "id": str(p.get("id") or f"p{len(problems) + 1}"),
                "statement": str(p.get("statement", ""))[:800],
                "evidence": evidence,
                "impact": p.get("impact", "medium"),
            })

        hypotheses = []
        for h in data.get("hypotheses", []) or []:
            if not isinstance(h, dict) or not str(h.get("statement", "")).strip():
                continue
            hypotheses.append({
                "id": str(h.get("id") or f"h{len(hypotheses) + 1}"),
                "statement": str(h["statement"])[:800],
                "target_file": str(h.get("target_file", ""))[:300],
                "confidence": float(h.get("confidence", 0.5) or 0.5),
            })

        mutations = []
        for m in data.get("suggested_mutations", []) or []:
            if not isinstance(m, dict) or not str(m.get("target_file", "")).strip():
                continue
            mutations.append({
                "hypothesis_id": str(m.get("hypothesis_id", "")),
                "target_file": str(m["target_file"])[:300],
                "change_summary": str(m.get("change_summary", ""))[:800],
            })

        return {
            "problems": problems,
            "hypotheses": hypotheses,
            "suggested_mutations": mutations,
            "dropped_problems": skipped,
        }

    async def reflect(self, session_id: str, llm=None, save: bool = True) -> dict:
        rc = self.cfg.get("reflection", {})
        digest = self.trace.digest(
            session_id,
            max_events=int(rc.get("max_events", 80)),
            max_chars=int(rc.get("max_chars", 12000)),
        )
        if not digest:
            raise ReflectionError(f"нет трейса для сессии {session_id}")

        summary = " ".join(str(e.get("payload", ""))[:200] for e in digest[-10:])
        lessons = self.wiki.retrieve(summary, top_k=int(self.cfg.get("wiki", {}).get("top_k", 5)))

        trace_text = "\n".join(
            f"[{e['event_id']}] {e['kind']}: {e['payload']}" for e in digest
        )
        wiki_text = "\n".join(
            f"- {l['title']}: {l.get('excerpt', '')[:200]}" for l in lessons
        ) or "(пока пусто)"

        user_msg = (
            f"Сессия: {session_id}\n\n"
            f"== ТРЕЙС ==\n{trace_text}\n\n"
            f"== УРОКИ ИЗ ВИКИ ==\n{wiki_text}\n\n"
            f"Верни только JSON по схеме."
        )
        caller = llm or self.llm or self._default_llm
        raw = await caller(self._system_prompt(), user_msg)
        data = json.loads(_strip_fences(raw))

        valid_ids = {e["event_id"] for e in digest}
        result = self._validate(data, valid_ids)
        result.update({
            "reflection_id": f"refl_{uuid.uuid4().hex[:12]}",
            "session_id": session_id,
            "created": datetime.now().isoformat(timespec="seconds"),
            "trace_events": len(digest),
            "wiki_used": [l["slug"] for l in lessons],
            "model": rc.get("model", "deepseek-flash"),
        })

        if save:
            path = self.root / f"{result['reflection_id']}.json"
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                            encoding="utf-8")
            try:
                self.trace.log(session_id, "reflection",
                               {"reflection_id": result["reflection_id"],
                                "problems": len(result["problems"]),
                                "hypotheses": len(result["hypotheses"])})
            except Exception:
                pass
            result["path"] = str(path)
        return result

    def save_lessons(self, result: dict, outcome: str = "pending") -> list:
        """M7: переносит гипотезы рефлексии в вики уроков (с дедупом)."""
        problems = "; ".join(
            p.get("statement", "")[:200] for p in result.get("problems", [])[:3]
        ) or "—"
        written = []
        for h in result.get("hypotheses", []):
            entry = self.wiki.write_lesson(
                title=h.get("statement", "")[:80],
                problem=problems,
                hypothesis=h.get("statement", ""),
                result=outcome,
                metric=f"confidence={h.get('confidence', 0.5)}",
                tags=["rsi", "reflection"],
            )
            written.append(entry)
        return written
