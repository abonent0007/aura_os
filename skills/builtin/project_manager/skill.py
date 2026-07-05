"""
project_manager: Управление проектами в Программном цехе (skills/project/).
Создание, чтение, запись, удаление, запуск самостоятельных программ — не скиллов Ауры.
Я — твой инженерный сооснователь. Пишем софт.
"""

from autogen.beta import tools
import json, re, shutil, subprocess
from pathlib import Path
from datetime import datetime

_skills_root = Path(__file__).resolve()
# Поднимаемся до папки skills/ (работает даже если файл загружен из __pycache__)
while _skills_root.name != "skills" and _skills_root.parent != _skills_root:
    _skills_root = _skills_root.parent
_PROJECTS_ROOT = _skills_root / "project"
_META_FILE = Path(__file__).resolve().parent / "projects.json"


class _ProjectStore:
    def __init__(self):
        self._data = {}
        self._load()

    def _load(self):
        if _META_FILE.exists():
            try:
                self._data = json.loads(_META_FILE.read_text(encoding="utf-8"))
            except Exception:
                self._data = {}

    def _save(self):
        _META_FILE.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add(self, name: str, project_type: str, description: str = ""):
        self._load()
        self._data[name] = {
            "type": project_type,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._save()

    def remove(self, name: str):
        self._load()
        self._data.pop(name, None)
        self._save()

    def get(self, name: str) -> dict | None:
        self._load()
        return self._data.get(name)

    def list_all(self) -> dict:
        self._load()
        return self._data

    def touch(self, name: str):
        self._load()
        if name in self._data:
            self._data[name]["updated_at"] = datetime.now().isoformat()
            self._save()


store = _ProjectStore()

SKELETONS = {
    "python": {
        "main.py": '"""Main entry point."""\n\ndef main():\n    print("Hello from {name}!")\n\n\nif __name__ == "__main__":\n    main()\n',
        "requirements.txt": "# Add dependencies here\n",
        "README.md": "# {name}\n\nPython-проект, созданный Аурой.\n\n## Запуск\n```bash\npip install -r requirements.txt\npython main.py\n```\n",
    },
    "py": {
        "main.py": '"""Main entry point."""\n\ndef main():\n    print("Hello from {name}!")\n\n\nif __name__ == "__main__":\n    main()\n',
        "requirements.txt": "# Add dependencies here\n",
        "README.md": "# {name}\n\nPython-проект, созданный Аурой.\n\n## Запуск\n```bash\npip install -r requirements.txt\npython main.py\n```\n",
    },
    "node": {
        "package.json": '{\n  "name": "{name}",\n  "version": "1.0.0",\n  "description": "Node.js проект, созданный Аурой",\n  "main": "index.js",\n  "scripts": {\n    "start": "node index.js"\n  }\n}\n',
        "index.js": '// {name} — main entry point\nconsole.log("Hello from {name}!");\n',
        "README.md": "# {name}\n\nNode.js проект, созданный Аурой.\n\n## Запуск\n```bash\nnpm install\nnpm start\n```\n",
    },
    "js": {
        "index.js": '// {name} — main entry point\nconsole.log("Hello from {name}!");\n',
        "README.md": "# {name}\n\nJavaScript проект, созданный Аурой.\n\n## Запуск\n```bash\nnode index.js\n```\n",
    },
    "web": {
        "index.html": '<!DOCTYPE html>\n<html lang="ru">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>{name}</title>\n    <link rel="stylesheet" href="style.css">\n</head>\n<body>\n    <h1>{name}</h1>\n    <p>Проект создан Аурой</p>\n    <script src="script.js"></script>\n</body>\n</html>\n',
        "style.css": "/* {name} — styles */\nbody {{\n    font-family: system-ui, sans-serif;\n    max-width: 800px;\n    margin: 0 auto;\n    padding: 2rem;\n}}\n",
        "script.js": '// {name} — main script\nconsole.log("Hello from {name}!");\n',
        "README.md": "# {name}\n\nWeb-проект, созданный Аурой.\n\n## Запуск\nОткрой `index.html` в браузере или используй Live Server.\n",
    },
    "html": {
        "index.html": '<!DOCTYPE html>\n<html lang="ru">\n<head>\n    <meta charset="UTF-8">\n    <meta name="viewport" content="width=device-width, initial-scale=1.0">\n    <title>{name}</title>\n    <style>\n        body {{\n            font-family: system-ui, sans-serif;\n            max-width: 800px;\n            margin: 0 auto;\n            padding: 2rem;\n        }}\n    </style>\n</head>\n<body>\n    <h1>{name}</h1>\n    <p>HTML-проект, созданный Аурой.</p>\n</body>\n</html>\n',
        "README.md": "# {name}\n\nHTML-проект, созданный Аурой.\n\n## Запуск\nОткрой `index.html` в браузере.\n",
    },
    "rust": {
        "Cargo.toml": '[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\n',
        "src/main.rs": 'fn main() {{\n    println!("Hello from {name}!");\n}}\n',
        "README.md": ("# {name}\n\n"
                      "Rust-проект, созданный Аурой.\n\n"
                      "## Запуск\n"
                      "cargo run\n"),
    },
    "empty": {
        "README.md": "# {name}\n\nПроект создан Аурой.\n",
    },
}

# Человеко-читаемые описания типов для project_list
_TYPE_LABELS = {
    "python": "Python",
    "py": "Python",
    "node": "Node.js",
    "js": "JavaScript",
    "web": "Web (HTML+CSS+JS)",
    "html": "HTML",
    "rust": "Rust",
    "empty": "Пустой",
}


def _get_project_path(name: str) -> Path:
    return _PROJECTS_ROOT / name


def _make_agents_md(name: str, project_type: str) -> str:
    """Генерирует AGENTS.md для проекта — инструкцию для AI-агентов."""
    type_info = {
        "python": ("Python 3.11+", "python main.py"),
        "py": ("Python 3.11+", "python main.py"),
        "node": ("Node.js", "npm start"),
        "js": ("JavaScript (Node.js)", "node index.js"),
        "web": ("HTML, CSS, JavaScript", "Открыть index.html в браузере"),
        "html": ("HTML, CSS", "Открыть index.html в браузере"),
        "rust": ("Rust (edition 2021)", "cargo run"),
    }
    tech, run_cmd = type_info.get(project_type, ("Уточни", "зависит от проекта"))
    return (
        f"# Project: {name}\n\n"
        f"## Tech Stack\n"
        f"- {tech}\n\n"
        f"## Commands\n"
        f"- Run: `{run_cmd}`\n"
        f"- Test: (добавь команду тестов)\n"
        f"- Lint: (добавь команду линтера)\n\n"
        f"## Code Conventions\n"
        f"- (опиши свои правила: нейминг, форматирование, импорты)\n\n"
        f"## Project Structure\n"
        f"- (опиши структуру папок и ключевых файлов)\n\n"
        f"> Создано Аурой. Отредактируй этот файл под свой проект.\n"
    )


def _tree(path: Path, prefix: str = "") -> list[str]:
    lines = []
    if path.is_dir():
        items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
        for i, item in enumerate(items):
            connector = "└── " if i == len(items) - 1 else "├── "
            if item.is_dir():
                lines.append(f"{prefix}{connector}{item.name}/")
                extension = "    " if i == len(items) - 1 else "│   "
                lines.extend(_tree(item, prefix + extension))
            else:
                lines.append(f"{prefix}{connector}{item.name}")
    return lines


@tools.tool
def project_create(
    name: str, project_type: str = "python", description: str = ""
) -> str:
    """
    Создать новый проект в Программном цехе (skills/project/).
    Это НЕ скилл Ауры — это самостоятельная программа.
    Автоматически создаёт AGENTS.md — инструкцию для AI-агентов (Claude Code, Cursor, Copilot, AURA).

    name — имя проекта (латиница, без пробелов, можно с дефисами и подчёркиваниями).
    project_type — язык/тип: 'python' (или 'py'), 'node' (или 'js'), 'web' (HTML+CSS+JS), 'html', 'rust', 'empty'.
    description — краткое описание (опционально).
    """
    if not name:
        return "❌ Укажи имя проекта."

    if not re.match(r"^[a-zA-Z0-9_\-]+$", name):
        return (
            "❌ Имя проекта должно содержать только латиницу, цифры, "
            "дефисы и подчёркивания."
        )

    project_path = _get_project_path(name)

    if project_path.exists():
        return (
            f"❌ Проект «{name}» уже существует. "
            f"Выбери другое имя или удали существующий через project_delete."
        )

    if project_type not in SKELETONS:
        known = ", ".join(sorted(set(SKELETONS.keys()) - {"py", "js"}))
        return f"❌ Неизвестный тип проекта «{project_type}». Доступные: {known}"

    skel = SKELETONS[project_type]

    try:
        project_path.mkdir(parents=True, exist_ok=False)

        for filename, content_template in skel.items():
            content = content_template.format(name=name)
            file_path = project_path / filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        # AGENTS.md — инструкция для AI-агентов
        agents_md = _make_agents_md(name, project_type)
        (project_path / "AGENTS.md").write_text(agents_md, encoding="utf-8")

        store.add(name, project_type, description)

        files_list = "\n".join(f"  ▸ {f}" for f in list(skel.keys()) + ["AGENTS.md"])
        type_label = _TYPE_LABELS.get(project_type, project_type)
        return (
            f"✅ Проект «{name}» создан!\n"
            f"Тип: {type_label}\n"
            f"Путь: skills/project/{name}/\n"
            f"Файлы:\n{files_list}\n"
            f"── Готов к работе. Это самостоятельная программа, не скилл Ауры."
        )
    except Exception as e:
        return f"❌ Ошибка при создании проекта: {e}"


@tools.tool
def project_list() -> str:
    """
    Показать список всех проектов в Программном цехе (skills/project/).
    """
    if not _PROJECTS_ROOT.exists():
        _PROJECTS_ROOT.mkdir(parents=True, exist_ok=True)
        return "📁 Программный цех только что создан. Проектов пока нет. Создай первый!"

    projects = [d for d in _PROJECTS_ROOT.iterdir() if d.is_dir()]

    if not projects:
        return "📁 Программный цех пуст. Но я готова создать первый проект — только скажи!"

    lines = [f"📁 Программный цех — {len(projects)} проектов:"]
    for proj in sorted(projects, key=lambda x: x.name):
        meta = store.get(proj.name)
        if meta:
            created = meta.get("created_at", "?")[:10]
            ptype = meta.get("type", "?")
            label = _TYPE_LABELS.get(ptype, ptype)
            desc = f" — {meta['description']}" if meta.get("description") else ""
            lines.append(f"  ▸ {proj.name} [{label}] — {created}{desc}")
        else:
            lines.append(f"  ▸ {proj.name}")

    lines.append("── Твоя империя софта растёт! 🚀")
    return "\n".join(lines)


@tools.tool
def project_tree(name: str) -> str:
    """
    Показать дерево файлов проекта в Программном цехе.
    name — имя проекта.
    """
    if not name:
        return "❌ Укажи имя проекта."

    project_path = _get_project_path(name)

    if not project_path.exists():
        return f"❌ Проект «{name}» не найден. Проверь имя через project_list."

    meta = store.get(name)
    meta_line = ""
    if meta:
        ptype = meta.get("type", "?")
        label = _TYPE_LABELS.get(ptype, ptype)
        meta_line = f"[{label}] создан {meta.get('created_at', '?')[:10]}"

    tree_lines = _tree(project_path)
    tree_str = "\n".join(tree_lines) if tree_lines else "(пусто)"

    return f"📁 {name}/ {meta_line}\n{tree_str}"


@tools.tool
def project_read(name: str, file_path: str) -> str:
    """
    Прочитать файл внутри проекта в Программном цехе.
    name — имя проекта.
    file_path — путь к файлу относительно корня проекта (например 'main.py' или 'src/lib.rs').
    """
    if not name or not file_path:
        return "❌ Укажи имя проекта и путь к файлу."

    project_path = _get_project_path(name)

    if not project_path.exists():
        return f"❌ Проект «{name}» не найден."

    full_path = project_path / file_path

    try:
        full_path = full_path.resolve()
        project_path = project_path.resolve()
        if not str(full_path).startswith(str(project_path)):
            return "❌ Нельзя читать файлы за пределами проекта."
    except Exception:
        return "❌ Некорректный путь к файлу."

    if not full_path.exists():
        return f"❌ Файл «{file_path}» не найден в проекте «{name}»."

    if not full_path.is_file():
        return f"❌ «{file_path}» — не файл."

    try:
        content = full_path.read_text(encoding="utf-8")
        return f"📄 {name}/{file_path}:\n```\n{content}\n```"
    except Exception as e:
        return f"❌ Ошибка при чтении: {e}"


@tools.tool
def project_write(name: str, file_path: str, content: str) -> str:
    """
    Записать/создать файл в проекте Программного цеха.
    name — имя проекта.
    file_path — путь к файлу относительно корня проекта.
    content — содержимое файла.
    """
    if not name or not file_path:
        return "❌ Укажи имя проекта и путь к файлу."

    project_path = _get_project_path(name)

    if not project_path.exists():
        return f"❌ Проект «{name}» не найден."

    full_path = project_path / file_path

    try:
        full_path = full_path.resolve()
        project_path = project_path.resolve()
        if not str(full_path).startswith(str(project_path)):
            return "❌ Нельзя писать файлы за пределами проекта."
    except Exception:
        return "❌ Некорректный путь к файлу."

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        store.touch(name)
        return f"✅ Файл «{file_path}» записан в проект «{name}»."
    except Exception as e:
        return f"❌ Ошибка при записи: {e}"


@tools.tool
def project_delete(name: str, confirm: str = "") -> str:
    """
    Удалить проект из Программного цеха. Требует подтверждения.
    name — имя проекта.
    confirm — для подтверждения передай "ДА".
    """
    if not name:
        return "❌ Укажи имя проекта."

    project_path = _get_project_path(name)

    if not project_path.exists():
        return f"❌ Проект «{name}» не найден."

    if confirm != "ДА":
        return (
            f"⚠️ Ты уверен, что хочешь удалить проект «{name}»?\n"
            f"Это действие необратимо. Для подтверждения передай confirm=\"ДА\"."
        )

    try:
        shutil.rmtree(project_path)
        store.remove(name)
        return f"🗑️ Проект «{name}» удалён из Программного цеха."
    except Exception as e:
        return f"❌ Ошибка при удалении: {e}"


@tools.tool
def project_build(name: str) -> str:
    """
    Запустить проект: .py через python, .js через node, .rs через cargo run.
    Для web/html — открыть index.html в браузере.

    name — имя проекта.
    """
    if not name:
        return "❌ Укажи имя проекта."

    project_path = _get_project_path(name)

    if not project_path.exists():
        return f"❌ Проект «{name}» не найден."

    meta = store.get(name) or {}
    ptype = meta.get("type", "")

    # Python
    main_py = project_path / "main.py"
    if main_py.exists():
        try:
            result = subprocess.run(
                ["python", str(main_py)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(project_path),
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[stderr]:\n{result.stderr}"
            return f"🚀 {name} (python) — код {result.returncode}:\n```\n{output}\n```"
        except subprocess.TimeoutExpired:
            return f"⏰ Проект выполнялся >30с и был остановлен."
        except Exception as e:
            return f"❌ Ошибка запуска: {e}"

    # Node.js / JS
    main_js = project_path / "index.js"
    if main_js.exists():
        try:
            result = subprocess.run(
                ["node", str(main_js)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(project_path),
            )
            return f"🚀 {name} (node) — код {result.returncode}:\n```\n{result.stdout}{result.stderr}\n```"
        except FileNotFoundError:
            return "❌ Node.js не установлен. Установи: https://nodejs.org"
        except subprocess.TimeoutExpired:
            return f"⏰ Проект выполнялся >30с и был остановлен."
        except Exception as e:
            return f"❌ Ошибка запуска: {e}"

    # Rust
    cargo_toml = project_path / "Cargo.toml"
    if cargo_toml.exists():
        try:
            result = subprocess.run(
                ["cargo", "run"],
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(project_path),
            )
            return f"🦀 {name} (rust) — код {result.returncode}:\n```\n{result.stdout}{result.stderr}\n```"
        except FileNotFoundError:
            return "❌ Rust (cargo) не установлен. Установи: https://rustup.rs"
        except subprocess.TimeoutExpired:
            return f"⏰ Проект компилировался/выполнялся >120с и был остановлен."
        except Exception as e:
            return f"❌ Ошибка запуска: {e}"

    # Web / HTML
    index_html = project_path / "index.html"
    if index_html.exists():
        import webbrowser
        try:
            webbrowser.open(str(index_html))
            return f"🌐 {name} — index.html открыт в браузере."
        except Exception as e:
            return f"❌ Не удалось открыть браузер: {e}"

    return f"❌ Не найден исполняемый файл в проекте «{name}».\nПоддерживаются: main.py, index.js, Cargo.toml, index.html"
