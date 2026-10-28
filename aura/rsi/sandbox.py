# -*- coding: utf-8 -*-
"""M4: Sandbox Runner — применяет патч к копии проекта и гоняет тесты.

Реальный репозиторий не трогается: работаем во временной копии.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from .config import REPO_ROOT
from .mutation import is_allowed

IGNORE = shutil.ignore_patterns(
    "models", "logs", ".git", ".venv-tts", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".playwright-mcp", ".opencode",
    "*.db", "*.pyc", "*.bak", "backups", ".auras_backups",
    "traces", "reflections", "wiki", "candidates",
)


class SandboxRunner:
    def __init__(self, repo_root: str = None, timeout: int = 300):
        self.repo = Path(repo_root) if repo_root else REPO_ROOT
        self.timeout = int(timeout)

    def run(self, patch_text: str, tests: str = "tests/") -> dict:
        t0 = time.time()
        files = re.findall(r"^\+\+\+ b/(.+)$", patch_text, re.M)
        for f in files:
            if not is_allowed(f):
                return {"ok": False, "crashed": True, "stage": "validate",
                        "error": f"патч трогает вне whitelist: {f}",
                        "files": files, "passed": 0, "failed": 0,
                        "output_tail": "", "duration_s": 0.0}

        tmp = Path(tempfile.mkdtemp(prefix="aura_rsi_sbx_"))
        work = tmp / "repo"
        try:
            shutil.copytree(self.repo, work, ignore=IGNORE)
            apply = subprocess.run(
                ["git", "apply", "-p1", "--whitespace=nowarn"],
                cwd=work, input=patch_text, text=True,
                capture_output=True, timeout=60,
            )
            if apply.returncode != 0:
                return {"ok": False, "crashed": True, "stage": "apply",
                        "error": (apply.stderr or "git apply failed")[:500],
                        "files": files, "passed": 0, "failed": 0,
                        "output_tail": "", "duration_s": time.time() - t0}

            proc = subprocess.run(
                [sys.executable, "-m", "pytest", tests, "-q", "--tb=line",
                 "-p", "no:cacheprovider"],
                cwd=work, capture_output=True, text=True,
                timeout=self.timeout,
                env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8",
                     "PYTHONUTF8": "1"},
            )
            out = (proc.stdout or "") + "\n" + (proc.stderr or "")
            passed = int((re.search(r"(\d+) passed", out) or [0, 0])[1])
            failed = int((re.search(r"(\d+) failed", out) or [0, 0])[1])
            return {
                "ok": proc.returncode == 0 and failed == 0 and passed > 0,
                "crashed": False,
                "stage": "tests",
                "returncode": proc.returncode,
                "passed": passed,
                "failed": failed,
                "files": files,
                "output_tail": out.strip()[-1500:],
                "duration_s": round(time.time() - t0, 1),
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "crashed": True, "stage": "timeout",
                    "error": f"тесты дольше {self.timeout}s", "files": files,
                    "passed": 0, "failed": 0, "output_tail": "",
                    "duration_s": time.time() - t0}
        except Exception as e:
            return {"ok": False, "crashed": True, "stage": "sandbox",
                    "error": f"{type(e).__name__}: {e}", "files": files,
                    "passed": 0, "failed": 0, "output_tail": "",
                    "duration_s": time.time() - t0}
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
