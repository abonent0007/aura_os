# content-sanitizer/skill.py
# Очищает чувствительные данные из текста (телефоны, email, адреса, ключи и т.д.)

import re
from autogen.beta import tools

# Правила очистки: (название, регулярка, замена)
RULES = [
    ("телефон РФ", r"(?<!\d)(?:\+?7[-\s]?)?8?[-\s]?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{2}[-\s]?\d{2}(?!\d)", "[ТЕЛЕФОН УДАЛЁН]"),
    ("телефон международный", r"(?<!\d)\+\d{1,3}[-\s]?\d{6,14}(?!\d)", "[ТЕЛЕФОН УДАЛЁН]"),
    ("email", r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", "[EMAIL УДАЛЁН]"),
    ("паспорт РФ", r"(?<!\d)\d{4}[-\s]?\d{6}(?!\d)", "[ПАСПОРТ УДАЛЁН]"),
    ("СНИЛС", r"(?<!\d)\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}(?!\d)", "[СНИЛС УДАЛЁН]"),
    ("банковская карта", r"(?<!\d)[3-6]\d{3}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{1,4}(?!\d)", "[КАРТА УДАЛЕНА]"),
    ("API ключ", r"(?i)(?:api[_-]?key|token|secret|password)\s*[:=]\s*[\"']?[a-zA-Z0-9_\-\.]{16,}[\"']?", "[КЛЮЧ УДАЛЁН]"),
    ("приватный ключ", r"-----BEGIN\s+(?:RSA\s+)?(?:PRIVATE\s+KEY|CERTIFICATE)-----[\s\S]*?-----END\s+(?:RSA\s+)?(?:PRIVATE\s+KEY|CERTIFICATE)-----", "[КЛЮЧ УДАЛЁН]"),
    ("IP адрес", r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?::\d{1,5})?\b", "[IP УДАЛЁН]"),
    ("GPS координаты", r"(?i)(?:широта|долгота|lat|lng|longitude|latitude)\s*[:：]?\s*-?\d{1,3}\.\d{3,}", "[КООРДИНАТЫ УДАЛЕНЫ]"),
    ("адрес", r"(?:ул\.|улица|пр\.|проспект|пер\.|переулок|бул\.|бульвар|пл\.|площадь|наб\.|набережная|ш\.|шоссе)\s+[\w\s\d\-/,]+(?:\s*д\.?\s*\d+)?", "[АДРЕС УДАЛЁН]"),
    ("госномер РФ", r"[АВЕКМНОРСТУХавекмнорстух]\d{3}[АВЕКМНОРСТУХавекмнорстух]{2}\d{2,3}", "[НОМЕР УДАЛЁН]"),
    ("UUID", r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "[UUID УДАЛЁН]"),
    ("URL БД", r"(?i)(?:mysql|postgres(?:ql)?|mongodb(?:\+srv)?|redis)://[^\s)\"']+", "[БД_URL УДАЛЁН]"),
    ("SSH команда", r"(?i)ssh\s+(?:-[a-zA-Z]\s+)*\S+@\S+", "[SSH УДАЛЁН]"),
]


def _clean(text: str) -> tuple:
    """Очищает текст. Возвращает (очищенный_текст, отчёт)."""
    report = []
    for name, pattern, replacement in RULES:
        matches = list(re.finditer(pattern, text))
        if matches:
            report.append({"тип": name, "найдено": len(matches)})
            text = re.sub(pattern, replacement, text)
    return text, report


@tools.tool
def clean_text(text: str) -> str:
    """
    Очищает текст от чувствительных данных: телефоны, email, адреса, паспорта, ключи API.
    Возвращает очищенный текст и отчёт о найденных совпадениях.
    """
    try:
        cleaned, report = _clean(text)
        if not report:
            return "Чувствительных данных не обнаружено. Текст безопасен."

        lines = ["Очистка завершена. Найдены чувствительные данные:\n"]
        for r in report:
            lines.append(f"  - {r['тип']}: {r['найдено']} совпадений")
        lines.append(f"\nОчищенный текст:\n{cleaned[:1000]}")
        if len(cleaned) > 1000:
            lines.append("...[текст обрезан]")

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка очистки: {e}"


@tools.tool
def scan_text(text: str) -> str:
    """
    Проверяет текст на наличие чувствительных данных БЕЗ изменения текста.
    Возвращает отчёт о найденных типах данных.
    """
    try:
        findings = []
        for name, pattern, _ in RULES:
            matches = list(re.finditer(pattern, text))
            if matches:
                findings.append({"тип": name, "найдено": len(matches)})

        if not findings:
            return "Чувствительных данных не обнаружено."

        lines = ["Обнаружены чувствительные данные:\n"]
        for f in findings:
            lines.append(f"  - {f['тип']}: {f['найдено']} совпадений")

        return "\n".join(lines)

    except Exception as e:
        return f"Ошибка проверки: {e}"
