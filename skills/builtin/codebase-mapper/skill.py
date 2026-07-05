# codebase-mapper/skill.py
# Анализ кодовой базы: структура, импорты, статистика

import os, re, json
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from autogen.beta import tools

ROOT = Path(__file__).parent.parent.parent.parent
SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules",
             "backups", "goodbyedpi", "logs", "models", ".idea", ".vscode"}
SKIP_FILES = {".gitkeep", ".DS_Store", "Thumbs.db"}


def _scan_files(extensions=None):
    """Сканирует файлы проекта."""
    files = []
    for root, dirs, filenames in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for f in filenames:
            if f in SKIP_FILES: continue
            if extensions and not any(f.endswith(ext) for ext in extensions):
                continue
            path = Path(root) / f
            try:
                lines = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
            except Exception:
                lines = 0
            rel = str(path.relative_to(ROOT))
            files.append({"path": rel, "lines": lines, "size": path.stat().st_size})
    return files


@tools.tool
def map_project_structure() -> str:
    """
    Карта структуры проекта: дерево папок с размерами файлов.
    Показывает организацию кодовой базы.
    """
    files = _scan_files()
    total_lines = sum(f["lines"] for f in files)
    total_size = sum(f["size"] for f in files)

    # Group by directory
    tree = defaultdict(list)
    for f in files:
        d = os.path.dirname(f["path"]) or "."
        tree[d].append(f)

    lines = [f"Project: AURA OS"]
    lines.append(f"Files: {len(files)} | Lines: {total_lines:,} | Size: {total_size/1024/1024:.1f} MB")
    lines.append("")

    for d in sorted(tree.keys()):
        files_in_dir = tree[d]
        dir_lines = sum(f["lines"] for f in files_in_dir)
        lines.append(f"{d}/  ({len(files_in_dir)} files, {dir_lines:,} lines)")
        for f in sorted(files_in_dir, key=lambda x: -x["lines"])[:5]:
            kb = f["size"] / 1024
            lines.append(f"  {os.path.basename(f['path']):30s} {f['lines']:>5d} lines  {kb:>6.0f} KB")

    return "\n".join(lines)


@tools.tool
def analyze_imports() -> str:
    """
    Анализ импортов между модулями. Показывает кто от кого зависит.
    """
    py_files = _scan_files([".py"])
    imports = defaultdict(set)

    for f in py_files:
        path = ROOT / f["path"]
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            for match in re.finditer(r'^(?:from|import)\s+(\w+)', content, re.MULTILINE):
                module = match.group(1)
                if module not in ("os", "sys", "re", "json", "time", "datetime",
                                   "pathlib", "typing", "collections", "dataclasses",
                                   "threading", "asyncio", "subprocess", "io", "enum",
                                   "sqlite3", "hashlib", "shutil", "random", "inspect"):
                    imports[os.path.basename(f["path"])].add(module)
        except Exception:
            pass

    lines = ["Module Dependencies:"]
    for file_name in sorted(imports.keys()):
        deps = imports[file_name]
        if deps:
            lines.append(f"  {file_name:30s} → {', '.join(sorted(deps)[:5])}")

    return "\n".join(lines)


@tools.tool
def top_files_by_lines(limit: int = 20) -> str:
    """
    Топ-N файлов по количеству строк кода.
    """
    files = _scan_files([".py", ".js", ".css", ".html", ".json", ".md"])
    sorted_files = sorted(files, key=lambda x: -x["lines"])[:limit]

    lines = [f"Top {limit} files by lines:"]
    for f in sorted_files:
        lines.append(f"  {f['path']:50s} {f['lines']:>6d} lines")

    total = sum(x["lines"] for x in files)
    lines.append(f"\nTotal: {total:,} lines in {len(files)} files")
    return "\n".join(lines)


@tools.tool
def find_duplicate_code(threshold: int = 5) -> str:
    """
    Поиск повторяющихся строк кода (простейший детектор копипасты).
    threshold: минимальное количество повторений строки.
    """
    py_files = _scan_files([".py"])
    line_counts = defaultdict(list)

    for f in py_files:
        path = ROOT / f["path"]
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                stripped = line.strip()
                if len(stripped) > 20 and not stripped.startswith(("#", "//", "/*")):
                    line_counts[stripped].append(os.path.basename(f["path"]))
        except Exception:
            pass

    dupes = {k: v for k, v in line_counts.items() if len(set(v)) >= threshold}
    if not dupes:
        return "No significant code duplication found."

    lines = [f"Duplicate lines (appearing in {threshold}+ files):"]
    for i, (text, files) in enumerate(sorted(dupes.items(), key=lambda x: -len(set(x[1])))[:10]):
        lines.append(f"  [{len(set(files))} files] {text[:80]}...")
    return "\n".join(lines)
