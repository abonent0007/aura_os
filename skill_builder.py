# skill_builder.py
"""
Нейро-генератор скиллов для AURA OS.
Позволяет облачной LLM создавать, тестировать и отлаживать скиллы.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple

from loguru import logger

from autogen.beta import Agent, config as ag_config
from skill_manager import (
    SkillManager, SkillValidator, SkillLoader,
    CUSTOM_DIR, SKILLS_DIR
)
from rollback_manager import RollbackManager
from system_monitor import SystemMonitor


# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
SKILL_BUILDER_PROMPT = """You are Skill Builder for AURA OS. Create working Python skills.

## OUTPUT FORMAT (STRICT)
Return ONLY valid JSON. No markdown blocks, no backticks, no text outside JSON:
{"manifest": {...}, "skill_md": "...", "skill_py": "..."}

Double-check: all strings properly escaped, no trailing commas, braces balanced.

## manifest.json SPEC
{
  "name": "snake_case_name",
  "version": "1.0.0",
  "author": "AURA AI",
  "description": "One-line description",
  "category": "automation|productivity|entertainment|tools|integration",
  "dependencies": [],
  "python_version": ">=3.10",
  "triggers": ["trigger1", "trigger2"],
  "permissions": ["network", "filesystem"],
  "auto_created": true,
  "stability": "testing",
  "created_at": "ISO_DATE"
}

## SKILL.md SPEC
Russian-language markdown: what, how, examples. Keep under 500 chars.

## skill.py SPEC (CRITICAL)
Python module with @tools.tool functions. Every tool returns str.

### Imports (use EXACTLY these, no others unless essential):
from autogen.beta import tools          # REQUIRED for @tools.tool
import httpx                            # for HTTP (NOT requests!)
import json                             # for JSON
from datetime import datetime, date     # for dates

### ANTI-PATTERNS (NEVER use these):
- import requests  →  use httpx instead (sync blocks event loop)
- import urllib    →  use httpx
- asyncio.run()    →  DON'T use inside tools (breaks in running loop)
- os.system()      →  use subprocess
- input()          →  tools cannot prompt user
- print()          →  return string instead
- emoji in output  →  use plain text only

### CORRECT TOOL TEMPLATE:
```python
from autogen.beta import tools
import httpx, json

@tools.tool
def my_tool(param: str = "default") -> str:
    \"\"\"What this tool does. When to use it.\"\"\"
    try:
        # Your logic here
        result = do_something(param)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {e}"
```

### HTTP CALLS (use this pattern):
```python
def _fetch(url):
    import threading, asyncio
    result = []
    def _run():
        loop = asyncio.new_event_loop()
        async def _get():
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(url)
                return r.text
        try:
            result.append(loop.run_until_complete(_get()))
        finally:
            loop.close()
    t = threading.Thread(target=_run); t.start(); t.join(20)
    return result[0] if result else ""
```

### VALIDATION CHECKLIST (verify before output):
[ ] manifest.name uses snake_case (lowercase, underscores, no hyphens)
[ ] skill_py imports ONLY allowed modules
[ ] All functions decorated with @tools.tool
[ ] Every tool has docstring
[ ] No asyncio.run(), no requests, no input()
[ ] All strings in JSON properly escaped (quotes, backslashes, newlines)
[ ] No markdown fences around JSON output
[ ] JSON is complete (no truncation)

## COMMON ERRORS TO AVOID:
- "requests" module → Use "httpx" with thread wrapper
- Empty JSON response → Always return valid JSON object
- Truncated strings → Escape newlines as \\n, quotes as \\\"
- Missing closing braces → Count your braces!
- Wrong tool decorator → Must be "@tools.tool" exactly
"""


# ============================================================
# 2. ГЕНЕРАТОР СКИЛЛОВ
# ============================================================
class SkillBuilder:
    """
    Создает скиллы с помощью LLM, тестирует, отлаживает.
    """

    MAX_RETRIES = 3
    TEST_TIMEOUT = 30

    def __init__(self, model_config: dict, skill_manager=None, rollback_manager=None, monitor=None):
        self.skill_manager = skill_manager or SkillManager()
        self.rollback_manager = rollback_manager or RollbackManager()
        self.monitor = monitor or SystemMonitor()

        self.builder_agent = Agent(
            name="AURA_SkillBuilder",
            config=ag_config.OpenAIConfig(
                model=model_config.get("model", "deepseek-v4-pro"),
                temperature=0.5,
                max_tokens=4096,
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com/v1"
            )
        )

        self.tester_agent = Agent(
            name="AURA_SkillTester",
            config=ag_config.OpenAIConfig(
                model=model_config.get("model", "deepseek-v4-pro"),
                temperature=0.2,
                max_tokens=2048,
                api_key=os.getenv("DEEPSEEK_API_KEY", ""),
                base_url="https://api.deepseek.com/v1"
            )
        )

    async def build_skill(self, user_request: str) -> Dict:
        """
        Полный цикл создания скилла.
        """
        logger.info(f"🔨 Создание скилла: {user_request[:100]}...")

        self.rollback_manager.create_backup(reason="pre_skill_build", is_automatic=True)

        result = {
            "success": False,
            "skill_name": "",
            "skill_path": "",
            "iterations": 0,
            "errors": [],
            "manifest": None,
        }

        skill_path = None

        for iteration in range(1, self.MAX_RETRIES + 1):
            result["iterations"] = iteration
            logger.info(f"🔄 Попытка {iteration}/{self.MAX_RETRIES}")

            try:
                code_result = await self._generate_skill_code(user_request, iteration, result["errors"])
                if not code_result:
                    continue

                skill_path, skill_name = self._save_skill_to_disk(code_result)
                result["skill_name"] = skill_name
                result["skill_path"] = str(skill_path)
                result["manifest"] = code_result["manifest"]

                valid, error_msg = self._validate_skill(skill_path)
                if not valid:
                    result["errors"].append(f"Валидация: {error_msg}")
                    self._cleanup_skill(skill_path)
                    continue

                test_ok, test_error = await self._test_skill(skill_path, skill_name)
                if not test_ok:
                    result["errors"].append(f"Тест: {test_error}")
                    self._cleanup_skill(skill_path)
                    continue

                load_ok = await self._load_skill(skill_path)
                if not load_ok:
                    result["errors"].append("Ошибка загрузки")
                    self._cleanup_skill(skill_path)
                    continue

                integration_ok = await self._integration_test(skill_name, code_result)
                if not integration_ok:
                    result["errors"].append("Ошибка интеграции")
                    self._unload_and_cleanup(skill_name, skill_path)
                    continue

                result["success"] = True
                logger.info(f"✅ Скилл {skill_name} создан и загружен!")
                self._update_stability(skill_path, "stable")
                break

            except Exception as e:
                error_msg = f"Попытка {iteration}: {str(e)}"
                result["errors"].append(error_msg)
                logger.error(f"❌ {error_msg}")
                if skill_path and skill_path.exists():
                    self._cleanup_skill(skill_path)

        if not result["success"]:
            logger.warning("🔄 Откат изменений...")
            self.rollback_manager.rollback()

        return result

    async def _generate_skill_code(self, user_request: str, iteration: int, previous_errors: List[str]) -> Optional[Dict]:
        prompt = SKILL_BUILDER_PROMPT

        if iteration > 1 and previous_errors:
            prompt += "\n\n## ОШИБКИ ПРЕДЫДУЩЕЙ ПОПЫТКИ\n"
            for err in previous_errors[-3:]:
                prompt += f"- {err}\n"
            prompt += "\nИсправь эти ошибки."

        prompt += f"\n\n## ЗАПРОС ПОЛЬЗОВАТЕЛЯ\n{user_request}"

        response = await self.builder_agent.ask(prompt)
        content = response.content.strip()

        # Remove markdown fences (multiple formats)
        for fence in ["```json", "```", "'''json", "'''"]:
            if content.startswith(fence):
                content = content[len(fence):].strip()
        for fence in ["```", "'''"]:
            if content.endswith(fence):
                content = content[:-len(fence)].strip()

        # Try multiple parse strategies
        data = None
        # 1. Direct parse
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            pass

        # 2. Find JSON object boundaries
        if data is None:
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                try:
                    data = json.loads(content[start:end+1])
                except json.JSONDecodeError:
                    # 3. Fix unescaped newlines in strings
                    import re
                    json_str = content[start:end+1]
                    fixed = re.sub(
                        r'(?<=":\s*")(.*?)(?=")',
                        lambda m: m.group(0).replace('\n', '\\n').replace('\r', ''),
                        json_str, flags=re.DOTALL
                    )
                    try:
                        data = json.loads(fixed)
                    except json.JSONDecodeError:
                        pass

        if data is None:
            logger.error("Failed to parse JSON from LLM response")
            return None

        if not all(k in data for k in ["manifest", "skill_md", "skill_py"]):
            logger.error("Response missing required fields")
            return None

        data["manifest"]["created_at"] = datetime.now().isoformat()
        data["manifest"]["updated_at"] = datetime.now().isoformat()
        return data

    def _save_skill_to_disk(self, code_data: Dict) -> Tuple[Path, str]:
        manifest = code_data["manifest"]
        skill_name = manifest["name"]
        skill_dir = CUSTOM_DIR / skill_name

        if skill_dir.exists():
            shutil.rmtree(skill_dir)

        skill_dir.mkdir(parents=True, exist_ok=True)

        with open(skill_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        with open(skill_dir / "SKILL.md", "w", encoding="utf-8") as f:
            f.write(code_data["skill_md"])

        with open(skill_dir / "skill.py", "w", encoding="utf-8") as f:
            f.write(code_data["skill_py"])

        logger.info(f"📁 Скилл сохранен: {skill_dir}")
        return skill_dir, skill_name

    def _validate_skill(self, skill_path: Path) -> Tuple[bool, str]:
        valid, msg = SkillValidator.validate_skill_dir(skill_path)
        if not valid:
            return False, msg

        valid, msg, _ = SkillValidator.validate_manifest(skill_path / "manifest.json")
        if not valid:
            return False, msg

        valid, msg = SkillValidator.validate_skill_code(skill_path / "skill.py")
        if not valid:
            return False, msg

        return True, "OK"

    async def _test_skill(self, skill_path: Path, skill_name: str) -> Tuple[bool, str]:
        try:
            skill_py = skill_path / "skill.py"
            safe_name = skill_name.replace("-", "_")  # Windows-safe module name
            test_code = (
                "import sys\n"
                f"sys.path.insert(0, {skill_path.parent.as_posix()!r})\n"
                f"sys.path.insert(0, {skill_path.as_posix()!r})\n"
                "try:\n"
                "    import importlib.util\n"
                f"    spec = importlib.util.spec_from_file_location({safe_name!r}, {str(skill_py)!r})\n"
                "    module = importlib.util.module_from_spec(spec)\n"
                "    spec.loader.exec_module(module)\n"
                "    print('OK')\n"
                "except Exception as e:\n"
                "    print(f'ERROR: {e}')\n"
            )
            result = subprocess.run(
                [sys.executable, "-c", test_code],
                capture_output=True, text=True,
                timeout=self.TEST_TIMEOUT
            )

            output = result.stdout.strip()
            if "OK" in output:
                return True, "OK"
            else:
                error_msg = result.stderr.strip() or output
                return False, error_msg[:200]

        except subprocess.TimeoutExpired:
            return False, f"Тест превысил лимит ({self.TEST_TIMEOUT}с)"
        except Exception as e:
            return False, str(e)[:200]

    async def _load_skill(self, skill_path: Path) -> bool:
        try:
            skill_info = self.skill_manager.load_skill_from_dir(skill_path)
            return skill_info is not None
        except Exception as e:
            logger.error(f"Ошибка загрузки: {e}")
            return False

    async def _integration_test(self, skill_name: str, code_data: Dict) -> bool:
        try:
            skill_info = self.skill_manager.skills.get(skill_name)
            if not skill_info:
                return False

            tools = skill_info.tools
            if not tools:
                return False

            import inspect
            for tool in tools:
                if not callable(tool):
                    return False
                sig = inspect.signature(tool)

            return True

        except Exception as e:
            logger.error(f"Ошибка интеграции: {e}")
            return False

    def _cleanup_skill(self, skill_path: Path):
        try:
            if skill_path.exists():
                shutil.rmtree(skill_path)
                logger.debug(f"🗑️ Удален: {skill_path}")
        except Exception as e:
            logger.warning(f"Ошибка очистки: {e}")

    def _unload_and_cleanup(self, skill_name: str, skill_path: Path):
        self.skill_manager.unload_skill(skill_name)
        self._cleanup_skill(skill_path)

    def _update_stability(self, skill_path: Path, stability: str):
        manifest_path = skill_path / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["stability"] = stability
            manifest["updated_at"] = datetime.now().isoformat()
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2, ensure_ascii=False)

    def get_skill_code(self, skill_name: str) -> Optional[str]:
        skill_info = self.skill_manager.skills.get(skill_name)
        if not skill_info or not skill_info.path:
            return None
        skill_py = skill_info.path / "skill.py"
        if skill_py.exists():
            return skill_py.read_text(encoding="utf-8")
        return None


# ============================================================
# 3. ТЕСТ
# ============================================================
async def test_skill_builder():
    print("=" * 60)
    print("🔨 Тест Skill Builder")
    print("=" * 60)

    builder = SkillBuilder({"model": "deepseek-v4-pro"})
    request = "Создай скилл для конвертации валют через открытое API"

    print(f"\n📝 Запрос: {request}")
    print("⏳ Генерация...")
    print("\n⚠️ Раскомментируй код для реального теста (требуется API)")
    # result = await builder.build_skill(request)
    # print result...


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_skill_builder())
