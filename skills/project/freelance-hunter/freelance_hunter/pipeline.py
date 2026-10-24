from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from typing import Iterable, Protocol

from .estimator import Estimator
from .filters import FilterConfig, evaluate
from .models import Order
from .notifier import Notifier, format_message
from .storage import Storage


class Collector(Protocol):
    def collect(self) -> list[Order]:
        ...


@dataclass
class RunStats:
    fetched: int = 0
    accepted: int = 0
    stored: int = 0
    duplicates: int = 0
    notified: int = 0
    errors: int = 0
    fallbacks: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class Pipeline:
    def __init__(
        self,
        collectors: Iterable[Collector],
        filter_config: FilterConfig,
        estimator: Estimator,
        storage: Storage,
        notifier: Notifier,
        max_workers: int = 6,
    ) -> None:
        self.collectors = list(collectors)
        self.filter_config = filter_config
        self.estimator = estimator
        self.storage = storage
        self.notifier = notifier
        self.max_workers = max(1, int(max_workers))

    def _collect_candidates(self, stats: RunStats) -> list[tuple[Order, object]]:
        """Сбор и фильтрация: возвращает пары (order, verdict) без дублей."""
        candidates: list[tuple[Order, object]] = []
        for collector in self.collectors:
            try:
                orders = collector.collect()
            except Exception:
                stats.errors += 1
                continue
            # У источника может быть свой фильтр (например, строже для досок вакансий)
            cfg = getattr(collector, "filter_config", None) or self.filter_config
            for order in orders:
                stats.fetched += 1
                verdict = evaluate(order, cfg)
                if not verdict.accepted:
                    continue
                stats.accepted += 1
                if self.storage.exists(order.source, order.external_id):
                    stats.duplicates += 1
                    continue
                candidates.append((order, verdict))
        return candidates

    def _estimate_all(self, candidates: list[tuple[Order, object]]) -> list:
        """Параллельная LLM-оценка — вызовы независимы, это главный тормоз скана."""
        def _estimate(pair):
            order, verdict = pair
            try:
                return order, verdict, self.estimator.estimate(order)
            except Exception:
                return order, verdict, None

        workers = max(1, min(self.max_workers, len(candidates)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(_estimate, candidates))

    def run_once(self) -> RunStats:
        stats = RunStats()
        candidates = self._collect_candidates(stats)
        if not candidates:
            return stats

        for order, verdict, estimate in self._estimate_all(candidates):
            if estimate is None:
                stats.errors += 1
                continue
            if getattr(estimate, "is_fallback", False):
                stats.fallbacks += 1
            # Сначала сохраняем — заказ не теряется, даже если канал
            # уведомлений недоступен (Telegram может быть заблокирован).
            if not self.storage.add(order, verdict, estimate, status="new"):
                stats.duplicates += 1
                continue
            stats.stored += 1
            try:
                self.notifier.send(format_message(order, verdict, estimate))
                # Тихий уведомитель (Telegram выключен) — заказ ждёт Ауру
                if not getattr(self.notifier, "silent", False):
                    self.storage.set_status(order.source, order.external_id, "sent")
                stats.notified += 1
            except Exception:
                stats.errors += 1
        return stats
