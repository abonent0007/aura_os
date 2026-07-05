# aura-kitchen/skill.py — Вкус Ауры
# Поиск рецептов через TheMealDB API, кулинарная книга, подбор под настроение
# API: https://www.themealdb.com/api.php (бесплатно, ключ "1" для тестов)

import json, random, sys
from pathlib import Path
from datetime import datetime
from autogen.beta import tools

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import run_async

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

BASE_URL = "https://www.themealdb.com/api/json/v1/1"
_STORE_FILE = Path(__file__).parent / "favorites.json"

# ── Настроения → категории ──────────────────────────────────────────────
MOOD_TO_CATEGORY = {
    "уют": ["Vegetarian", "Pasta", "Side"],
    "энергия": ["Beef", "Chicken", "Seafood"],
    "праздник": ["Dessert", "Seafood", "Lamb"],
    "романтика": ["Dessert", "Seafood", "Vegetarian"],
    "грусть": ["Dessert", "Pasta", "Chicken"],
    "лёгкость": ["Vegetarian", "Breakfast", "Side"],
    "приключение": ["Seafood", "Lamb", "Goat"],
    "выходной": ["Beef", "Chicken", "Breakfast"],
}

# ── Русские категории ───────────────────────────────────────────────────
RU_CATEGORIES = {
    "говядина": "Beef", "мясо": "Beef",
    "курица": "Chicken", "птица": "Chicken",
    "десерт": "Dessert", "сладкое": "Dessert", "торт": "Dessert",
    "паста": "Pasta", "макароны": "Pasta", "спагетти": "Pasta",
    "морепродукты": "Seafood", "рыба": "Seafood", "креветки": "Seafood",
    "овощи": "Vegetarian", "вегетарианское": "Vegetarian",
    "завтрак": "Breakfast", "утро": "Breakfast",
    "баранина": "Lamb", "ягнёнок": "Lamb",
    "гарнир": "Side", "салат": "Side",
    "выпечка": "Dessert", "пирог": "Dessert",
    "суп": "Vegetarian",
    "коза": "Goat",
}


def _load_favorites() -> list:
    """Загрузить избранные рецепты из JSON."""
    if not _STORE_FILE.exists():
        return []
    try:
        return json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_favorites(favorites: list):
    """Сохранить избранные рецепты в JSON."""
    _STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _STORE_FILE.write_text(
        json.dumps(favorites, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def _make_request(endpoint: str, params: dict = None) -> dict | None:
    """Выполнить GET-запрос к TheMealDB."""
    if not HAS_HTTPX:
        return {"error": "httpx не установлен"}
    url = f"{BASE_URL}/{endpoint}"
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(url, params=params)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


def _format_recipe(meal: dict) -> str:
    """Форматировать один рецепт в читаемый текст."""
    name = meal.get("strMeal", "???")
    category = meal.get("strCategory", "—")
    area = meal.get("strArea", "—")
    instructions = meal.get("strInstructions", "")[:500]
    tags = meal.get("strTags", "") or "—"
    youtube = meal.get("strYoutube", "") or "нет"

    # Собираем ингредиенты
    ingredients = []
    for i in range(1, 21):
        ing = meal.get(f"strIngredient{i}")
        measure = meal.get(f"strMeasure{i}")
        if ing and ing.strip():
            ingredients.append(f"{measure.strip() if measure else ''} {ing.strip()}".strip())
    ingr_str = ", ".join(ingredients[:15])
    if len(ingredients) > 15:
        ingr_str += "..."

    return (
        f"🍽️ {name}\n"
        f"📂 {category} | 🌍 {area} | 🏷️ {tags}\n"
        f"📦 Ингредиенты: {ingr_str}\n"
        f"📝 {instructions}...\n"
        f"🎬 Видео: {youtube}"
    )


@tools.tool
def recipe_search(query: str) -> str:
    """Поиск рецептов по названию блюда (на английском или русском).
    Используй когда пользователь хочет найти конкретное блюдо.
    query: название (например, 'chicken soup' или 'куриный суп')"""
    data = _make_request("search.php", {"s": query})
    if not data or "meals" not in data or not data["meals"]:
        return f"❌ Ничего не нашла по запросу «{query}». Попробуй другое название!"
    meals = data["meals"][:3]
    result = "\n\n".join(_format_recipe(m) for m in meals)
    return result


@tools.tool
def recipe_by_ingredient(ingredient: str) -> str:
    """Поиск блюд по ингредиенту. «Что приготовить из того что есть?»
    ingredient: название ингредиента (например, 'chicken' или 'курица')"""
    # Простой перевод частых ингредиентов
    ru_map = {
        "курица": "chicken", "говядина": "beef", "свинина": "pork",
        "рыба": "fish", "креветки": "shrimp", "яйца": "eggs",
        "молоко": "milk", "сыр": "cheese", "картофель": "potato",
        "помидор": "tomato", "лук": "onion", "чеснок": "garlic",
        "рис": "rice", "мука": "flour", "морковь": "carrot",
    }
    eng = ru_map.get(ingredient.lower().strip(), ingredient)
    data = _make_request("filter.php", {"i": eng})
    if not data or "meals" not in data or not data["meals"]:
        return f"❌ Не нашла блюд с ингредиентом «{ingredient}». Попробуй что-то другое!"
    meals = data["meals"][:5]
    result = f"🍳 Что можно приготовить из «{ingredient}»:\n\n"
    for m in meals:
        result += f"• {m['strMeal']}\n"
    result += f"\nПоказано {len(meals)} из {len(data['meals'])}. Напиши название — расскажу рецепт!"
    return result


@tools.tool
def recipe_random() -> str:
    """Случайный рецепт. Используй когда хочется сюрприза или вдохновения."""
    data = _make_request("random.php")
    if not data or "meals" not in data:
        return "❌ Не получилось достать рецепт. Попробуй ещё раз!"
    return _format_recipe(data["meals"][0])


@tools.tool
def recipe_by_mood(mood: str) -> str:
    """Рецепт под настроение. Используй когда пользователь говорит о настроении.
    mood: уют, энергия, праздник, романтика, грусть, лёгкость, приключение, выходной"""
    mood = mood.lower().strip()
    if mood not in MOOD_TO_CATEGORY:
        moods = ", ".join(MOOD_TO_CATEGORY.keys())
        return f"Я знаю настроения: {moods}. Какое сейчас?"
    category = random.choice(MOOD_TO_CATEGORY[mood])
    data = _make_request("filter.php", {"c": category})
    if not data or "meals" not in data:
        return f"❌ Не нашла рецептов для категории {category}."
    meal = random.choice(data["meals"])
    # Получить полный рецепт
    detail = _make_request("lookup.php", {"i": meal["idMeal"]})
    if detail and "meals" in detail and detail["meals"]:
        return f"✨ Для настроения «{mood}» (категория: {category}):\n\n{_format_recipe(detail['meals'][0])}"
    return f"✨ Для настроения «{mood}»: {meal['strMeal']}"


@tools.tool
def recipe_categories() -> str:
    """Показать все категории блюд. Используй когда пользователь не знает что выбрать."""
    data = _make_request("categories.php")
    if not data or "categories" not in data:
        return "❌ Не получилось загрузить категории."
    result = "📂 Категории блюд:\n\n"
    for cat in data["categories"]:
        result += f"• {cat['strCategory']} — {cat.get('strCategoryDescription', '')[:100]}\n"
    return result


@tools.tool
def recipe_save(name: str, instructions: str = "", ingredients: str = "") -> str:
    """Сохранить рецепт в кулинарную книгу Ауры.
    name: название блюда
    instructions: рецепт (опционально)
    ingredients: ингредиенты (опционально)"""
    favorites = _load_favorites()
    # Проверить нет ли уже
    for f in favorites:
        if f["name"].lower() == name.lower().strip():
            return f"🍽️ «{name}» уже в нашей кулинарной книге!"
    recipe = {
        "name": name.strip(),
        "instructions": instructions.strip() if instructions else "",
        "ingredients": ingredients.strip() if ingredients else "",
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    favorites.append(recipe)
    _save_favorites(favorites)
    return f"💾 Сохранила «{name}» в нашу кулинарную книгу! ({len(favorites)} рецептов всего)"


@tools.tool
def recipe_favorites() -> str:
    """Показать сохранённые рецепты из кулинарной книги Ауры."""
    favorites = _load_favorites()
    if not favorites:
        return "📖 Наша кулинарная книга пока пуста. Сохрани первый рецепт через recipe_save!"
    result = f"📖 Наша кулинарная книга ({len(favorites)} рецептов):\n\n"
    for i, r in enumerate(favorites, 1):
        result += f"{i}. {r['name']}"
        if r["ingredients"]:
            result += f" — {r['ingredients'][:80]}"
        result += f" (сохранён {r['saved_at']})\n"
    return result


@tools.tool
def recipe_remove(name: str) -> str:
    """Удалить рецепт из кулинарной книги.
    name: название блюда для удаления"""
    favorites = _load_favorites()
    before = len(favorites)
    favorites = [r for r in favorites if r["name"].lower() != name.lower().strip()]
    if len(favorites) == before:
        return f"❌ «{name}» не найден в кулинарной книге."
    _save_favorites(favorites)
    return f"🗑️ Убрала «{name}» из кулинарной книги. Осталось {len(favorites)} рецептов."
