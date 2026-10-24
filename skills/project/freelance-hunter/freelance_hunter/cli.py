import argparse
import functools
import json

from .collector import FeedCollector
from .config import AppConfig, load_config
from .estimator import Estimator
from .filters import FilterConfig
from .notifier import NullNotifier, TelegramNotifier
from .pipeline import Pipeline
from .storage import Storage


def http_fetch(url: str, timeout: float = 20.0) -> str:
    import httpx

    response = httpx.get(
        url,
        timeout=httpx.Timeout(timeout, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "freelance-hunter/0.1"},
    )
    response.raise_for_status()
    return response.text


class OpenAICompatibleClient:
    def __init__(self, base_url: str, api_key: str, model: str, timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def complete(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
            },
            timeout=httpx.Timeout(self.timeout, connect=5.0),
        )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]


def telegram_transport(url: str, payload: dict, timeout: float = 10.0) -> dict:
    import httpx

    response = httpx.post(url, json=payload, timeout=httpx.Timeout(timeout, connect=5.0))
    response.raise_for_status()
    return response.json()


def build_pipeline(cfg: AppConfig) -> Pipeline:
    fetcher = functools.partial(http_fetch, timeout=cfg.fetch_timeout)
    base_filter = FilterConfig(
        accept_keywords=cfg.accept_keywords,
        reject_keywords=cfg.reject_keywords,
        min_score=cfg.min_score,
        min_length=cfg.min_length,
        max_length=cfg.max_length,
    )
    collectors = []
    for source in cfg.sources:
        source_filter = base_filter
        if source.min_score is not None and source.min_score != cfg.min_score:
            # У источника свой порог (доски вакансий строже фриланс-бирж)
            source_filter = FilterConfig(
                accept_keywords=base_filter.accept_keywords,
                reject_keywords=base_filter.reject_keywords,
                min_score=source.min_score,
                min_length=base_filter.min_length,
                max_length=base_filter.max_length,
            )
        collectors.append(
            FeedCollector(name=source.name, url=source.url, fetcher=fetcher,
                          filter_config=source_filter)
        )
    estimator = Estimator(
        client=OpenAICompatibleClient(
            cfg.llm_base_url, cfg.llm_api_key, cfg.llm_model, timeout=cfg.llm_timeout
        ),
        fallback_price=cfg.fallback_price,
        fallback_days=cfg.fallback_days,
    )
    # Telegram без VPN недоступен: без токена/чата — тихая заглушка,
    # заказы всё равно сохраняются, их показывает Аура.
    if cfg.telegram_token and cfg.telegram_chat_id:
        notifier = TelegramNotifier(
            cfg.telegram_token,
            cfg.telegram_chat_id,
            functools.partial(telegram_transport, timeout=cfg.telegram_timeout),
        )
    else:
        notifier = NullNotifier()
    storage = Storage(cfg.db_path)
    return Pipeline(collectors, base_filter, estimator, storage, notifier,
                    max_workers=cfg.max_workers)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="freelance_hunter",
        description="Собирает лёгкие фриланс-заказы, оценивает их и готовит черновики откликов",
    )
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    cfg = load_config(args.config)
    pipeline = build_pipeline(cfg)
    try:
        stats = pipeline.run_once()
    finally:
        pipeline.storage.close()
    print(json.dumps(stats.as_dict(), ensure_ascii=False))
    return 0
