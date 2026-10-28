# -*- coding: utf-8 -*-
"""M5: Evaluator — независимый вердикт по результату песочницы.

Пороги: тесты зелёные, дифф в лимите, recall не ниже baseline - ε.
"""
from .config import load_config


class Evaluator:
    def __init__(self, config: dict = None):
        self.cfg = config or load_config()
        limits = self.cfg.get("limits") or {}
        self.max_diff_lines = int(limits.get("max_diff_lines", 200))
        self.epsilon = float(limits.get("epsilon", 0.02))

    def evaluate(self, sandbox: dict, diff_lines: int = None,
                 recall: float = None, recall_baseline: float = None) -> dict:
        reasons = []
        if sandbox.get("crashed"):
            reasons.append(f"sandbox_{sandbox.get('stage', 'crash')}: "
                           f"{sandbox.get('error', '')[:160]}")
        if sandbox.get("failed", 0) > 0:
            reasons.append(f"тесты упали: {sandbox['failed']}")
        if sandbox.get("passed", 0) == 0 and not sandbox.get("crashed"):
            reasons.append("нет пройденных тестов")
        if diff_lines is not None and diff_lines > self.max_diff_lines:
            reasons.append(f"дифф {diff_lines} > {self.max_diff_lines}")
        if recall is not None and recall_baseline is not None:
            if recall + self.epsilon < recall_baseline:
                reasons.append(f"recall {recall:.2%} < baseline {recall_baseline:.2%} - ε")

        metrics = {
            "tests_passed": sandbox.get("passed", 0),
            "tests_failed": sandbox.get("failed", 0),
            "diff_lines": diff_lines,
            "recall": recall,
            "recall_baseline": recall_baseline,
            "duration_s": sandbox.get("duration_s"),
        }
        return {
            "passes": not reasons,
            "reason": "ok" if not reasons else "; ".join(reasons),
            "metrics": metrics,
        }
