# infographic-generator/skill.py
# Генератор инфографики: карточки, диаграммы, графики на Pillow + matplotlib
# Для автоматического создания контента под заказ

import json, os, io, base64
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

# === КОНФИГУРАЦИЯ ===
_OUTPUT_DIR = Path(__file__).parent / "output"
_OUTPUT_DIR.mkdir(exist_ok=True)

# Цветовые схемы
COLORS = {
    "business": {
        "bg": (245, 247, 250), "primary": (30, 60, 120), "accent": (66, 133, 244),
        "text": (50, 50, 50), "light": (200, 210, 225), "white": (255, 255, 255)
    },
    "vivid": {
        "bg": (255, 250, 240), "primary": (220, 50, 80), "accent": (255, 160, 0),
        "text": (40, 40, 40), "light": (255, 220, 180), "white": (255, 255, 255)
    },
    "dark": {
        "bg": (30, 30, 40), "primary": (80, 200, 255), "accent": (255, 100, 150),
        "text": (220, 220, 230), "light": (60, 60, 80), "white": (40, 40, 55)
    },
    "pastel": {
        "bg": (248, 245, 255), "primary": (130, 160, 200), "accent": (200, 150, 180),
        "text": (80, 70, 90), "light": (220, 210, 235), "white": (255, 255, 255)
    }
}

PALETTES = {
    "business": [(66, 133, 244), (52, 168, 83), (251, 188, 4), (234, 67, 53), (142, 124, 195)],
    "vivid": [(255, 99, 132), (255, 159, 64), (255, 205, 86), (75, 192, 192), (153, 102, 255)],
    "dark": [(80, 200, 255), (255, 100, 150), (100, 255, 180), (255, 200, 80), (180, 130, 255)],
    "pastel": [(180, 200, 230), (210, 180, 200), (180, 220, 200), (230, 210, 180), (200, 190, 220)]
}

WIDTH, HEIGHT = 800, 600
HAS_PILLOW = False
HAS_MPL = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PILLOW = True
except ImportError:
    pass

try:
    import matplotlib
    matplotlib.use('Agg')  # без GUI
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    pass


def _get_font(size: int):
    """Пытается загрузить системный шрифт, иначе дефолтный."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        try:
            return ImageFont.truetype("DejaVuSans.ttf", size)
        except Exception:
            return ImageFont.load_default()


def _save_image(img: Image.Image, prefix: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = _OUTPUT_DIR / f"{prefix}_{ts}.png"
    img.save(str(filepath), "PNG", dpi=(300, 300))
    return str(filepath)


def _draw_text_box(draw, text, x, y, max_w, font, fill):
    """Рисует текст с переносом строк."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_w:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)

    for line in lines:
        draw.text((x, y), line, fill=fill, font=font)
        y += font.size + 4
    return y


# === ИНСТРУМЕНТЫ ===

@tools.tool
def ig_create_card(title: str, facts_json: str, template: str = "business", footer: str = "") -> str:
    """
    Создаёт информационную карточку (статичную инфографику).
    title — заголовок карточки.
    facts_json — JSON-строка с фактами: ["Факт 1: значение", "Факт 2: значение", ...].
    template — цветовая схема: business, vivid, dark, pastel.
    footer — текст внизу карточки (опционально).
    Возвращает путь к PNG.
    """
    if not HAS_PILLOW:
        return "[Ошибка] Pillow не установлен. Выполни: pip install pillow"

    try:
        facts = json.loads(facts_json)
        if isinstance(facts, dict):
            facts = [f"{k}: {v}" for k, v in facts.items()]
    except json.JSONDecodeError:
        return "[Ошибка] Невалидный JSON. Пример: '[\"Продажи: 1.2M\", \"Клиенты: 500+\"]'"

    c = COLORS.get(template, COLORS["business"])

    img = Image.new("RGB", (WIDTH, HEIGHT), c["bg"])
    draw = ImageDraw.Draw(img)

    # Верхняя полоса
    draw.rectangle([(0, 0), (WIDTH, 8)], fill=c["primary"])

    # Заголовок
    title_font = _get_font(36)
    draw.text((40, 30), title, fill=c["primary"], font=title_font)

    # Линия под заголовком
    y = 80
    draw.rectangle([(40, y), (WIDTH - 40, y + 2)], fill=c["accent"])

    # Факты
    fact_font = _get_font(24)
    y = 110
    for i, fact in enumerate(facts):
        # Номер
        num = str(i + 1)
        draw.ellipse([(40, y + 2), (70, y + 32)], fill=c["accent"])
        draw.text((55 - len(num) * 3, y + 5), num, fill=c["white"], font=_get_font(18))

        # Текст факта
        _draw_text_box(draw, fact, 90, y + 2, WIDTH - 130, fact_font, c["text"])
        y += 55

    # Футер
    if footer:
        y = max(y + 20, HEIGHT - 80)
        draw.rectangle([(0, HEIGHT - 50), (WIDTH, HEIGHT)], fill=c["primary"])
        footer_font = _get_font(18)
        draw.text((40, HEIGHT - 40), footer, fill=c["white"], font=footer_font)

    filepath = _save_image(img, "card")
    return f"🖼️ Карточка создана: {filepath}\nЗаголовок: {title}\nФактов: {len(facts)}\nСхема: {template}"


@tools.tool
def ig_create_barchart(title: str, data_json: str, template: str = "business", xlabel: str = "", ylabel: str = "") -> str:
    """
    Создаёт столбчатую диаграмму (bar chart).
    title — заголовок.
    data_json — JSON-строка: {"Категория 1": 100, "Категория 2": 200, ...}.
    template — цветовая схема.
    Возвращает путь к PNG.
    """
    if not HAS_MPL:
        return "[Ошибка] matplotlib не установлен. Выполни: pip install matplotlib"

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return "[Ошибка] Невалидный JSON. Пример: '{\"Янв\": 100, \"Фев\": 200}'"

    palette = PALETTES.get(template, PALETTES["business"])
    colors_hex = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.bar(data.keys(), data.values(), color=colors_hex[:len(data)], edgecolor="white", linewidth=1.5)

    ax.set_title(title, fontsize=18, fontweight="bold", pad=15)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=12)

    # Значения над столбцами
    for bar, val in zip(bars, data.values()):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(data.values()) * 0.02,
                str(val), ha="center", fontsize=12, fontweight="bold")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="x", rotation=30)
    plt.tight_layout()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = _OUTPUT_DIR / f"barchart_{ts}.png"
    fig.savefig(str(filepath), dpi=150, bbox_inches="tight")
    plt.close(fig)

    return f"📊 Столбчатая диаграмма: {filepath}\nЗаголовок: {title}\nКатегорий: {len(data)}"


@tools.tool
def ig_create_linechart(title: str, data_json: str, template: str = "business", xlabel: str = "", ylabel: str = "") -> str:
    """
    Создаёт линейный график (тренды, динамика).
    title — заголовок.
    data_json — JSON-строка вида:
      {"точки X": [1, 2, 3, ...], "Серия 1": [10, 20, 15, ...], "Серия 2": [5, 15, 25, ...]}.
      Первый ключ всегда — ось X, остальные — серии данных.
    template — цветовая схема.
    Возвращает путь к PNG.
    """
    if not HAS_MPL:
        return "[Ошибка] matplotlib не установлен. Выполни: pip install matplotlib"

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return "[Ошибка] Невалидный JSON. Пример: '{\"Месяцы\": [1,2,3], \"Продажи\": [100,200,150]}'"

    keys = list(data.keys())
    if len(keys) < 2:
        return "[Ошибка] Нужно минимум 2 ключа: ось X и одна серия данных"

    x = data[keys[0]]
    palette = PALETTES.get(template, PALETTES["business"])

    fig, ax = plt.subplots(figsize=(10, 6))

    for i, key in enumerate(keys[1:], 0):
        color = f"#{palette[i % len(palette)][0]:02x}{palette[i % len(palette)][1]:02x}{palette[i % len(palette)][2]:02x}"
        ax.plot(x, data[key], marker="o", linewidth=2.5, label=key, color=color, markersize=6)

    ax.set_title(title, fontsize=18, fontweight="bold", pad=15)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=12)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=12)

    ax.legend(loc="best", frameon=True, fancybox=True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = _OUTPUT_DIR / f"linechart_{ts}.png"
    fig.savefig(str(filepath), dpi=150, bbox_inches="tight")
    plt.close(fig)

    return f"📈 Линейный график: {filepath}\nЗаголовок: {title}\nСерий данных: {len(keys) - 1}"


@tools.tool
def ig_create_piechart(title: str, data_json: str, template: str = "business") -> str:
    """
    Создаёт круговую диаграмму (доли, проценты).
    title — заголовок.
    data_json — JSON-строка: {"Сегмент 1": 30, "Сегмент 2": 45, "Сегмент 3": 25}.
    template — цветовая схема.
    Возвращает путь к PNG.
    """
    if not HAS_MPL:
        return "[Ошибка] matplotlib не установлен. Выполни: pip install matplotlib"

    try:
        data = json.loads(data_json)
    except json.JSONDecodeError:
        return "[Ошибка] Невалидный JSON. Пример: '{\"Прибыль\": 60, \"Расходы\": 40}'"

    palette = PALETTES.get(template, PALETTES["business"])
    colors_hex = [f"#{r:02x}{g:02x}{b:02x}" for r, g, b in palette]

    fig, ax = plt.subplots(figsize=(8, 8))
    wedges, texts, autotexts = ax.pie(
        data.values(),
        labels=data.keys(),
        autopct="%1.1f%%",
        colors=colors_hex[:len(data)],
        startangle=90,
        wedgeprops={"edgecolor": "white", "linewidth": 2}
    )

    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")

    ax.set_title(title, fontsize=18, fontweight="bold", pad=20)
    plt.tight_layout()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filepath = _OUTPUT_DIR / f"piechart_{ts}.png"
    fig.savefig(str(filepath), dpi=150, bbox_inches="tight")
    plt.close(fig)

    return f"🥧 Круговая диаграмма: {filepath}\nЗаголовок: {title}\nСегментов: {len(data)}"


@tools.tool
def ig_list_templates() -> str:
    """Показывает доступные шаблоны и цветовые схемы для инфографики."""
    return (
        "🎨 Доступные шаблоны инфографики:\n\n"
        "ЦВЕТОВЫЕ СХЕМЫ:\n"
        "  🏢 business — сине-серые тона (презентации, отчёты)\n"
        "  🔥 vivid   — яркие цвета (соцсети, маркетинг)\n"
        "  🌙 dark    — тёмная тема (технические обзоры)\n"
        "  🌸 pastel  — пастельные тона (лайфстайл, блоги)\n\n"
        "ТИПЫ ВИЗУАЛИЗАЦИЙ:\n"
        "  🖼️ card       — информационная карточка с фактами\n"
        "  📊 barchart   — столбчатая диаграмма (сравнение)\n"
        "  📈 linechart  — линейный график (тренды)\n"
        "  🥧 piechart   — круговая диаграмма (доли)\n\n"
        "ФОРМАТЫ: PNG (300 DPI), PDF через конвертацию\n"
        "ВЫХОД: skills/infographic-generator/output/"
    )


@tools.tool
def ig_status() -> str:
    """Статистика генератора инфографики: количество созданных файлов, зависимости."""
    files = list(_OUTPUT_DIR.glob("*.png")) + list(_OUTPUT_DIR.glob("*.pdf"))
    total_size = sum(f.stat().st_size for f in files) if files else 0

    lines = ["🎨 Статус генератора инфографики:", ""]
    lines.append(f"  {'✅' if HAS_PILLOW else '❌'} Pillow: {'установлен' if HAS_PILLOW else 'pip install pillow'}")
    lines.append(f"  {'✅' if HAS_MPL else '❌'} matplotlib: {'установлен' if HAS_MPL else 'pip install matplotlib'}")
    lines.append(f"  📁 Создано файлов: {len(files)} ({total_size // 1024} КБ)")

    if files:
        latest = max(files, key=lambda p: p.stat().st_mtime)
        lines.append(f"     Последний: {latest.name}")

    return "\n".join(lines)
