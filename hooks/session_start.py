"""Хук: выполняется при старте сессии AURA."""


def run() -> str:
    from datetime import datetime
    return f"session_start: {datetime.now().isoformat()}"
