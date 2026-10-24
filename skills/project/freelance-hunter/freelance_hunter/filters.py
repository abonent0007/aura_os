import re
from dataclasses import dataclass

from .models import Order

_WORD_START = r"(?<![A-Za-zА-Яа-яЁё0-9])"


def _word_match(text: str, keyword: str) -> bool:
    """Поиск ключевого слова с начала слова (учитывает русские словоформы).

    «1с» не сработает внутри «t1сный», но сработает в «доработать 1С».
    «аналитик» сработает в «аналитика», «аналитике», «аналитиков».
    """
    pattern = rf"{_WORD_START}{re.escape(keyword.lower())}"
    return re.search(pattern, text) is not None


@dataclass(frozen=True)
class FilterConfig:
    accept_keywords: tuple[str, ...] = ()
    reject_keywords: tuple[str, ...] = ()
    min_score: int = 1
    min_length: int = 30
    max_length: int = 1200


@dataclass(frozen=True)
class Verdict:
    accepted: bool
    score: int
    reasons: tuple[str, ...] = ()


def evaluate(order: Order, cfg: FilterConfig) -> Verdict:
    text = order.text.lower()
    for keyword in cfg.reject_keywords:
        if _word_match(text, keyword):
            return Verdict(False, 0, (f"reject:{keyword}",))
    score = 0
    reasons: list[str] = []
    for keyword in cfg.accept_keywords:
        if keyword.lower() in text:
            score += 1
            reasons.append(f"match:{keyword}")
    if len(text) < cfg.min_length:
        return Verdict(False, score, tuple(reasons + ["too_short"]))
    if len(text) > cfg.max_length:
        return Verdict(False, score, tuple(reasons + ["too_long"]))
    return Verdict(score >= cfg.min_score, score, tuple(reasons))
