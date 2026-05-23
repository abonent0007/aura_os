# autogen/beta/memory.py
# Эмуляция MemoryStream

from typing import List, Dict, Any


class MemoryHistory:
    """Контейнер истории сообщений."""
    def __init__(self):
        self._messages: List[Dict[str, Any]] = []

    async def get_messages(self) -> List[Dict[str, Any]]:
        return self._messages

    async def set(self, messages: List[Any]):
        self._messages = []
        for m in messages:
            if hasattr(m, 'content'):
                self._messages.append({"role": "assistant", "content": str(m.content)})
            elif isinstance(m, dict):
                self._messages.append(m)
            else:
                self._messages.append({"role": "assistant", "content": str(m)})

    async def clear(self):
        self._messages = []

    async def add(self, message: Dict[str, Any]):
        self._messages.append(message)


class MemoryStream:
    """Поток памяти — хранит историю сообщений."""
    def __init__(self):
        self.history = MemoryHistory()
