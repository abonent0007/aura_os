# -*- coding: utf-8 -*-
"""Dry-run RSI (M3 -> M4 -> M5): патч, песочница, вердикт. Ничего не применяет.

Пример:
  python tools/rsi_dry_run.py --target system_prompt.py \
      --summary "добавить правило" --new-file new_prompt.txt --tests tests/test_context_no_duplicate.py
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aura.rsi.evaluator import Evaluator  # noqa: E402
from aura.rsi.mutation import MutationEngine, MutationError  # noqa: E402
from aura.rsi.sandbox import SandboxRunner  # noqa: E402


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--summary", default="dry-run mutation")
    ap.add_argument("--new-file", help="файл с новым содержимым целевого файла")
    ap.add_argument("--tests", default="tests/")
    args = ap.parse_args()

    new_content = None
    if args.new_file:
        new_content = Path(args.new_file).read_text(encoding="utf-8")

    engine = MutationEngine()
    try:
        meta = await engine.propose(args.target, args.summary, new_content=new_content)
    except MutationError as e:
        print(json.dumps({"stage": "mutation", "error": str(e)}, ensure_ascii=False))
        return 1

    patch = Path(meta["patch_path"]).read_text(encoding="utf-8")
    sandbox = SandboxRunner().run(patch, tests=args.tests)
    verdict = Evaluator().evaluate(sandbox, diff_lines=meta["diff_lines"])

    print(json.dumps({
        "mut_id": meta["mut_id"],
        "target": meta["target_file"],
        "diff_lines": meta["diff_lines"],
        "persona": meta["persona"],
        "auto_allowed": meta["auto_allowed"],
        "sandbox": {k: sandbox.get(k) for k in
                    ("ok", "crashed", "stage", "passed", "failed", "duration_s")},
        "verdict": verdict,
    }, ensure_ascii=False, indent=2))
    return 0 if verdict["passes"] else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
