import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Union

from .estimator import Estimate
from .filters import Verdict
from .models import Order

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    score INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    price REAL,
    days INTEGER,
    proposal TEXT,
    created_at TEXT NOT NULL,
    PRIMARY KEY (source, external_id)
)
"""


class Storage:
    def __init__(self, path: Union[str, Path]) -> None:
        self.path = str(path)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def add(
        self,
        order: Order,
        verdict: Verdict,
        estimate: Optional[Estimate] = None,
        status: str = "new",
    ) -> bool:
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO orders
            (source, external_id, title, url, description, score, status, price, days, proposal, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order.source,
                order.external_id,
                order.title,
                order.url,
                order.description,
                verdict.score,
                status,
                estimate.price if estimate else None,
                estimate.days if estimate else None,
                estimate.proposal if estimate else None,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        self.conn.commit()
        return cursor.rowcount > 0

    def exists(self, source: str, external_id: str) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM orders WHERE source = ? AND external_id = ?",
            (source, external_id),
        ).fetchone()
        return row is not None

    def get_by_status(self, status: str) -> list[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at", (status,)))

    def set_status(self, source: str, external_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE orders SET status = ? WHERE source = ? AND external_id = ?",
            (status, source, external_id),
        )
        self.conn.commit()

    def count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0])
