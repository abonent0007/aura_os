# -*- coding: utf-8 -*-
"""M3: Mutation Engine — диффы только по whitelisted-файлам.

Ничего не применяет: складывает кандидата в aura/rsi/candidates/<mut_id>/.
"""
import difflib
import fnmatch
import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path

from .config import REPO_ROOT, load_config, rsi_paths


class MutationError(ValueError):
    pass


def is_allowed(target: str, cfg: dict = None) -> bool:
    """Разрешён ли путь/секция для мутации."""
    cfg = cfg or load_config()
    target = (target or "").replace("\\", "/").lstrip("./")
    if not target or target.startswith("..") or ".." in target.split("/"):
        return False
    if target in (cfg.get("locked") or []):
        return False
    for pattern in cfg.get("whitelist", []):
        if "#" in pattern:
            if target == pattern:
                return True
            continue
        if fnmatch.fnmatch(target, pattern):
            return True
    return False


class MutationEngine:
    def __init__(self, config: dict = None, llm=None, root: str = None):
        self.cfg = config or load_config()
        self.llm = llm
        self.root = Path(root) if root else rsi_paths()["candidates"]
        self.root.mkdir(parents=True, exist_ok=True)

    def _read_target(self, target: str) -> str:
        path = REPO_ROOT / target
        if not path.exists() or not path.is_file():
            raise MutationError(f"файл не найден: {target}")
        return path.read_text(encoding="utf-8")

    async def _ask_new_content(self, target: str, old: str, summary: str) -> str:
        if self.llm is None:
            raise MutationError("llm не задан: передай new_content или llm")
        system = (
            "Ты — мутационный модуль AURA OS. Верни ПОЛНЫЙ новый текст файла "
            "без markdown-обёрток и пояснений. Сохрани стиль и работоспособность."
        )
        user = (f"Файл: {target}\nЗадача: {summary}\n\n"
                f"=== ТЕКУЩИЙ ТЕКСТ ===\n{old[:12000]}")
        return await self.llm(system, user)

    def _make_patch(self, target: str, old: str, new: str) -> str:
        if old == new:
            raise MutationError("пустой дифф: содержимое не изменилось")
        patch = "".join(difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{target}",
            tofile=f"b/{target}",
        ))
        if not patch.strip():
            raise MutationError("пустой дифф")
        return patch

    async def propose(self, target_file: str, change_summary: str,
                      new_content: str = None) -> dict:
        """Готовит кандидата: валидирует whitelist, размер и сохраняет дифф."""
        target = (target_file or "").replace("\\", "/").lstrip("./")
        if not is_allowed(target, self.cfg):
            raise MutationError(f"вне whitelist: {target}")
        if "#" in target:
            raise MutationError("секции JSON пока не поддерживаются (v1)")
        if (self.cfg.get("persona", {}).get("manual_only")
                and target == "system_prompt.py"):
            # не запрет, но помечаем: auto применять нельзя
            persona = True
        else:
            persona = False

        old = self._read_target(target)
        new = new_content
        if new is None:
            new = await self._ask_new_content(target, old, change_summary)

        patch = self._make_patch(target, old, new)
        diff_lines = sum(1 for line in patch.splitlines()
                         if line[:1] in ("+", "-") and not line.startswith(("+++", "---")))
        max_lines = int((self.cfg.get("limits") or {}).get("max_diff_lines", 200))
        if diff_lines > max_lines:
            raise MutationError(f"дифф {diff_lines} строк > лимита {max_lines}")

        mut_id = f"mut_{uuid.uuid4().hex[:10]}"
        out_dir = self.root / mut_id
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "patch.diff").write_text(patch, encoding="utf-8")

        meta = {
            "mut_id": mut_id,
            "created": datetime.now().isoformat(timespec="seconds"),
            "target_file": target,
            "change_summary": change_summary[:500],
            "diff_lines": diff_lines,
            "diff_hash": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            "persona": persona,
            "auto_allowed": not persona,
            "status": "candidate",
            "patch_path": str(out_dir / "patch.diff"),
        }
        (out_dir / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        return meta
