from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Order:
    source: str
    external_id: str
    title: str
    description: str = ""
    url: str = ""
    published_at: Optional[str] = None
    budget: Optional[float] = None

    @property
    def text(self) -> str:
        return f"{self.title} {self.description}".strip()

    @property
    def key(self) -> str:
        return f"{self.source}:{self.external_id}"
