# -*- coding: utf-8 -*-
"""M7: Experience Wiki — уроки между сессиями.

Markdown-файлы + index.json. Поиск — по пересечению основ слов (без внешних
зависимостей и без эмбеддингов). Дедуп — по diff_hash.
"""
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from .config import load_config, rsi_paths

_WORD_RE = re.compile(r"[a-zA-Zа-яА-ЯёЁ0-9_]{3,}")


def _stems(text: str) -> set:
    out = set()
    for word in _WORD_RE.findall((text or "").lower()):
        out.add(word[:5])
        out.add(re.sub(r"[аяоеёиыуьюй]+$", "", word))
    return {s for s in out if len(s) >= 3}


def _slugify(title: str) -> str:
    latin = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
    if latin:
        return latin[:48]
    return "lesson-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:8]


class ExperienceWiki:
    def __init__(self, root: str = None, top_k: int = None):
        cfg = load_config()
        self.root = Path(root) if root else rsi_paths()["wiki"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        self.top_k = int(top_k if top_k is not None else cfg.get("wiki", {}).get("top_k", 5))
        self._entries = self._load_index()

    def _load_index(self) -> list:
        try:
            if self.index_path.exists():
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                return data.get("lessons", [])
        except Exception:
            pass
        return []

    def _save_index(self) -> None:
        self.index_path.write_text(
            json.dumps({"lessons": self._entries}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_lesson(self, title: str, problem: str, hypothesis: str,
                     result: str, metric: str = "", diff_hash: str = None,
                     tags: list = None) -> dict:
        """Пишет урок. Дубли (по diff_hash или title) не создаёт."""
        for entry in self._entries:
            if entry.get("title") == title or (diff_hash and entry.get("diff_hash") == diff_hash):
                entry["duplicate"] = True
                return entry

        slug = _slugify(title)
        base, i = slug, 2
        while (self.root / f"{slug}.md").exists():
            slug = f"{base}-{i}"
            i += 1

        created = datetime.now().isoformat(timespec="seconds")
        body = (
            f"# {title}\n\n"
            f"- created: {created}\n"
            f"- tags: {', '.join(tags or [])}\n"
            f"- diff_hash: {diff_hash or '—'}\n\n"
            f"## Проблема\n{problem}\n\n"
            f"## Гипотеза\n{hypothesis}\n\n"
            f"## Что сработало / нет\n{result}\n\n"
            f"## Метрика\n{metric or '—'}\n"
        )
        path = self.root / f"{slug}.md"
        path.write_text(body, encoding="utf-8")

        entry = {
            "slug": slug,
            "title": title,
            "tags": list(tags or []),
            "created": created,
            "diff_hash": diff_hash,
            "file": path.name,
        }
        self._entries.append(entry)
        self._save_index()
        return entry

    def retrieve(self, query: str, top_k: int = None) -> list:
        """Top-K релевантных уроков по пересечению основ слов."""
        q = _stems(query)
        if not q:
            return []
        scored = []
        for entry in self._entries:
            path = self.root / entry.get("file", "")
            try:
                text = path.read_text(encoding="utf-8") if path.exists() else ""
            except Exception:
                text = ""
            doc = _stems(f"{entry.get('title', '')} {' '.join(entry.get('tags', []))} {text}")
            if not doc:
                continue
            score = len(q & doc) / (len(doc) ** 0.5)
            if score > 0:
                scored.append((score, entry, text))
        scored.sort(key=lambda x: (-x[0], x[1].get("slug", "")))
        limit = top_k if top_k is not None else self.top_k
        out = []
        for score, entry, text in scored[:limit]:
            excerpt = re.sub(r"\s+", " ", text)[:300]
            out.append({**entry, "score": round(score, 3), "excerpt": excerpt})
        return out

    def list_lessons(self) -> list:
        return list(self._entries)
