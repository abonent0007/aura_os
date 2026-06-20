# freelance-manager/skill.py
# Менеджер фриланс-заказов: клиенты, задания, статусы, автопайплайн
# Связывает browser-automation + infographic-generator в бизнес-процесс

import json
from pathlib import Path
from datetime import datetime, date
from autogen.beta import tools

# === ХРАНИЛИЩЕ ===
_DATA_FILE = Path(__file__).parent / "data.json"

VALID_STATUSES = ["new", "in_progress", "review", "done", "cancelled"]


class _Store:
    def __init__(self):
        self._data = {"clients": [], "orders": [], "order_counter": 0}
        self._load()

    def _load(self):
        if _DATA_FILE.exists():
            try:
                loaded = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
                self._data.update(loaded)
            except Exception:
                pass

    def _save(self):
        _DATA_FILE.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def next_order_id(self):
        self._data["order_counter"] += 1
        self._save()
        return self._data["order_counter"]

    def add_client(self, name: str, contact: str, notes: str = ""):
        client = {
            "id": len(self._data["clients"]) + 1,
            "name": name,
            "contact": contact,
            "notes": notes,
            "added": datetime.now().isoformat(),
            "total_orders": 0
        }
        self._data["clients"].append(client)
        self._save()
        return client

    def add_order(self, client_name: str, description: str, deadline: str, price: float):
        client = self.find_client(client_name)
        if not client:
            client = self.add_client(client_name, "", "авто-создан из заказа")

        order = {
            "id": self.next_order_id(),
            "client": client["name"],
            "client_id": client["id"],
            "description": description,
            "deadline": deadline,
            "price": price,
            "status": "new",
            "created": datetime.now().isoformat(),
            "updated": datetime.now().isoformat(),
            "result_file": "",
            "notes": ""
        }
        self._data["orders"].append(order)

        # Обновить счётчик клиента
        client["total_orders"] += 1
        self._save()
        return order

    def find_client(self, name: str):
        name_lower = name.lower()
        for c in self._data["clients"]:
            if c["name"].lower() == name_lower:
                return c
        return None

    def find_order(self, order_id: int):
        for o in self._data["orders"]:
            if o["id"] == order_id:
                return o
        return None

    def get_orders(self, status: str = "", client_name: str = ""):
        result = self._data["orders"]
        if status:
            result = [o for o in result if o["status"] == status]
        if client_name:
            result = [o for o in result if o["client"].lower() == client_name.lower()]
        return sorted(result, key=lambda o: o["id"], reverse=True)

    def get_stats(self):
        orders = self._data["orders"]
        done = [o for o in orders if o["status"] == "done"]
        total_earned = sum(o["price"] for o in done)
        total_orders = len(orders)
        in_progress = len([o for o in orders if o["status"] in ("new", "in_progress", "review")])

        # За этот месяц
        now = date.today()
        month_orders = [o for o in done if o.get("updated", "").startswith(f"{now.year}-{now.month:02d}")]
        month_earned = sum(o["price"] for o in month_orders)

        return {
            "total_orders": total_orders,
            "active": in_progress,
            "done": len(done),
            "total_earned": total_earned,
            "month_earned": month_earned,
            "avg_price": total_earned / len(done) if done else 0,
            "clients": len(self._data["clients"])
        }


store = _Store()

# === ИНСТРУМЕНТЫ ===

@tools.tool
def freelance_new_order(client: str, description: str, deadline: str = "", price: float = 0) -> str:
    """
    Создать новый заказ.
    client — имя клиента.
    description — описание задачи (что нужно сделать).
    deadline — срок сдачи в формате 'YYYY-MM-DD' (опционально).
    price — цена в рублях (опционально, по умолчанию 0).
    Возвращает ID созданного заказа.
    """
    if not description.strip():
        return "[Ошибка] Укажи описание задачи"

    order = store.add_order(client, description, deadline, price)

    deadline_str = f"\nДедлайн: {deadline}" if deadline else ""
    price_str = f"\nЦена: {price} ₽" if price else ""

    return (
        f"📋 Заказ #{order['id']} создан!\n"
        f"Клиент: {client}\n"
        f"Задача: {description}"
        f"{deadline_str}"
        f"{price_str}\n"
        f"Статус: 🆕 new\n\n"
        f"Используй freelance_pipeline({order['id']}) для автоматического выполнения."
    )


@tools.tool
def freelance_list_orders(status: str = "", client: str = "") -> str:
    """
    Показать список заказов.
    status — фильтр по статусу: new, in_progress, review, done, cancelled (опционально).
    client — фильтр по имени клиента (опционально).
    """
    orders = store.get_orders(status=status, client_name=client)

    if not orders:
        return "📭 Заказов нет." + (f" (статус: {status})" if status else "")

    status_emoji = {
        "new": "🆕", "in_progress": "🔨", "review": "👀",
        "done": "✅", "cancelled": "❌"
    }

    lines = [f"📋 Заказы ({len(orders)}):"]
    lines.append("=" * 50)

    for o in orders[:20]:
        emoji = status_emoji.get(o["status"], "❓")
        d = o["deadline"] or "без срока"
        p = f"{o['price']} ₽" if o["price"] else "—"
        lines.append(
            f"  #{o['id']} {emoji} [{o['status']}] {o['description'][:50]}"
        )
        lines.append(f"     Клиент: {o['client']} | Дедлайн: {d} | Цена: {p}")

    if len(orders) > 20:
        lines.append(f"  ... и ещё {len(orders) - 20}")

    return "\n".join(lines)


@tools.tool
def freelance_update_order(order_id: int, status: str, notes: str = "") -> str:
    """
    Обновить статус заказа.
    order_id — номер заказа.
    status — новый статус: new, in_progress, review, done, cancelled.
    notes — заметка (опционально).
    """
    if status not in VALID_STATUSES:
        return f"[Ошибка] Неверный статус. Допустимые: {', '.join(VALID_STATUSES)}"

    order = store.find_order(order_id)
    if not order:
        return f"[Ошибка] Заказ #{order_id} не найден"

    old_status = order["status"]
    order["status"] = status
    order["updated"] = datetime.now().isoformat()
    if notes:
        order["notes"] += f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M')}] {notes}"

    store._save()

    status_emoji = {"new": "🆕", "in_progress": "🔨", "review": "👀", "done": "✅", "cancelled": "❌"}
    emoji = status_emoji.get(status, "")

    return (
        f"📝 Заказ #{order_id}: {old_status} → {emoji} {status}\n"
        f"Описание: {order['description'][:100]}\n"
        f"Клиент: {order['client']}"
    )


@tools.tool
def freelance_client_add(name: str, contact: str = "", notes: str = "") -> str:
    """
    Добавить нового клиента.
    name — имя клиента.
    contact — контакт (Telegram, email, телефон).
    notes — заметки о клиенте.
    """
    existing = store.find_client(name)
    if existing:
        return f"👤 Клиент '{name}' уже существует (ID: {existing['id']}, заказов: {existing['total_orders']})"

    client = store.add_client(name, contact, notes)
    return (
        f"👤 Клиент добавлен!\n"
        f"Имя: {client['name']}\n"
        f"Контакт: {contact or 'не указан'}\n"
        f"ID: {client['id']}"
    )


@tools.tool
def freelance_client_list() -> str:
    """Показать всех клиентов."""
    clients = store._data["clients"]

    if not clients:
        return "👤 Клиентов пока нет. Используй freelance_client_add чтобы добавить."

    lines = [f"👥 Клиенты ({len(clients)}):"]
    lines.append("=" * 40)

    for c in sorted(clients, key=lambda x: x["total_orders"], reverse=True):
        contact = c["contact"] or "нет контакта"
        lines.append(f"  {c['name']} | Заказов: {c['total_orders']} | {contact}")

    return "\n".join(lines)


@tools.tool
def freelance_pipeline(order_id: int) -> str:
    """
    Запустить автоматический пайплайн выполнения заказа.
    Шаги:
      1. Переводит заказ в статус 'in_progress'
      2. Показывает инструкцию: какие инструменты использовать (browser + infographic)
      3. Ждёт подтверждения о готовности инфографики
    Используй этот инструмент когда нужно выполнить заказ от начала до конца.
    """
    order = store.find_order(order_id)
    if not order:
        return f"[Ошибка] Заказ #{order_id} не найден"

    if order["status"] not in ("new", "in_progress"):
        return f"[Ошибка] Заказ #{order_id} уже в статусе '{order['status']}'. Ожидаются: new, in_progress"

    # Переводим в работу
    if order["status"] == "new":
        order["status"] = "in_progress"
        order["updated"] = datetime.now().isoformat()
        store._save()

    return (
        f"🚀 ПАЙПЛАЙН ЗАПУЩЕН — Заказ #{order_id}\n"
        f"========================================\n"
        f"Задача: {order['description']}\n"
        f"Клиент: {order['client']}\n"
        f"Статус: 🔨 in_progress\n\n"
        f"📋 ПЛАН ВЫПОЛНЕНИЯ:\n"
        f"1️⃣  Собери данные через browser_automation:\n"
        f"    — browser_get_text(url) для текста\n"
        f"    — browser_extract_data(url, rules) для структуры\n"
        f"    — browser_screenshot(url) для скриншотов\n\n"
        f"2️⃣  Создай инфографику через infographic-generator:\n"
        f"    — ig_create_card(title, facts, template)\n"
        f"    — ig_create_barchart / linechart / piechart\n\n"
        f"3️⃣  Когда инфографика готова:\n"
        f"    freelance_update_order({order_id}, 'review')\n\n"
        f"4️⃣  После оплаты:\n"
        f"    freelance_update_order({order_id}, 'done')\n\n"
        f"💡 Я могу выполнить шаги 1 и 2 прямо сейчас — просто скажи что делать!"
    )


@tools.tool
def freelance_stats() -> str:
    """
    Статистика фриланс-менеджера:
    всего заказов, выполнено, заработок всего и за месяц, средний чек.
    """
    s = store.get_stats()

    return (
        f"💰 ФРИЛАНС-СТАТИСТИКА\n"
        f"====================\n"
        f"📋 Всего заказов: {s['total_orders']}\n"
        f"🔨 В работе: {s['active']}\n"
        f"✅ Выполнено: {s['done']}\n"
        f"👥 Клиентов: {s['clients']}\n\n"
        f"💵 Заработано всего: {s['total_earned']:,.0f} ₽\n"
        f"📅 За этот месяц: {s['month_earned']:,.0f} ₽\n"
        f"📊 Средний чек: {s['avg_price']:,.0f} ₽"
    )
