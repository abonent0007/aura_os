# skill_manager.py
"""
Менеджер скиллов AURA OS.
Загрузка, выгрузка, валидация, горячая замена скиллов.
"""

import os
import re
import sys
import json
import importlib
import importlib.util
import inspect
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field

from loguru import logger


# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
SKILLS_DIR = Path(__file__).parent / "skills"
BUILTIN_DIR = SKILLS_DIR / "builtin"
CUSTOM_DIR = SKILLS_DIR / "custom"
REGISTRY_FILE = SKILLS_DIR / "registry.json"


# ============================================================
# 2. МОДЕЛИ ДАННЫХ
# ============================================================
@dataclass
class SkillManifest:
    """Манифест скилла"""
    name: str
    version: str
    author: str = "AURA AI"
    description: str = ""
    category: str = "general"
    dependencies: List[str] = field(default_factory=list)
    python_version: str = ">=3.10"
    triggers: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    auto_created: bool = False
    stability: str = "testing"
    created_at: str = ""
    updated_at: str = ""


@dataclass
class SkillInfo:
    """Информация о загруженном скилле"""
    manifest: SkillManifest
    module: Any = None
    tools: List[Callable] = field(default_factory=list)
    path: Path = None
    enabled: bool = True
    errors: int = 0
    loaded_at: Optional[str] = None


# ============================================================
# 3. ВАЛИДАТОР СКИЛЛОВ
# ============================================================
class SkillValidator:
    """Валидация скиллов перед загрузкой"""
    
    REQUIRED_FILES = ["manifest.json", "SKILL.md", "skill.py"]
    
    @classmethod
    def validate_skill_dir(cls, path: Path) -> tuple[bool, str]:
        """Проверяет структуру папки скилла"""
        if not path.exists():
            return False, f"Папка не существует: {path}"
        
        for file in cls.REQUIRED_FILES:
            if not (path / file).exists():
                return False, f"Отсутствует файл: {file}"
        
        return True, "OK"
    
    @classmethod
    def validate_manifest(cls, manifest_path: Path) -> tuple[bool, str, Optional[dict]]:
        """Валидация manifest.json"""
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            required_fields = ["name", "version", "description"]
            for field in required_fields:
                if field not in data:
                    return False, f"Отсутствует поле: {field}", None
            
            if not data["name"].isidentifier() and not re.match(r'^[a-z][a-z0-9_\-]+$', data["name"]):
                return False, f"Некорректное имя: {data['name']}", None
            
            return True, "OK", data
            
        except json.JSONDecodeError as e:
            return False, f"Ошибка JSON: {e}", None
        except Exception as e:
            return False, f"Ошибка чтения: {e}", None
    
    @classmethod
    def validate_skill_code(cls, skill_path: Path) -> tuple[bool, str]:
        """Базовая проверка Python-кода скилла"""
        try:
            with open(skill_path, "r", encoding="utf-8") as f:
                code = f.read()
            
            compile(code, str(skill_path), "exec")
            return True, "OK"
        except SyntaxError as e:
            return False, f"Синтаксическая ошибка: {e}"
        except Exception as e:
            return False, f"Ошибка: {e}"


# ============================================================
# 4. ЗАГРУЗЧИК СКИЛЛОВ
# ============================================================
class SkillLoader:
    """Динамическая загрузка скиллов"""
    
    @staticmethod
    def load_skill(skill_path: Path, skill_name: str) -> Optional[Any]:
        """
        Загружает Python-модуль скилла.
        Возвращает модуль или None при ошибке.
        """
        try:
            # Добавляем путь в sys.path
            skill_dir = str(skill_path.parent)
            if skill_dir not in sys.path:
                sys.path.insert(0, skill_dir)
            
            # Загружаем модуль
            spec = importlib.util.spec_from_file_location(
                skill_name.replace("-", "_"),
                str(skill_path / "skill.py")
            )
            
            if spec is None or spec.loader is None:
                return None
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            return module
            
        except Exception as e:
            logger.error(f"Ошибка загрузки скилла {skill_name}: {e}")
            return None
    
    @staticmethod
    def extract_tools(module: Any) -> List[Callable]:
        """Извлекает инструменты из модуля скилла"""
        tools = []
        
        for name, obj in inspect.getmembers(module):
            # Ищем функции с атрибутом @tool или начинающиеся с tool_
            if inspect.isfunction(obj):
                if hasattr(obj, '_is_tool') or name.startswith('tool_'):
                    tools.append(obj)
        
        return tools
    
    @staticmethod
    def reload_skill(skill_info: SkillInfo) -> Optional[SkillInfo]:
        """Горячая перезагрузка скилла"""
        if skill_info.module:
            importlib.reload(skill_info.module)
            skill_info.tools = SkillLoader.extract_tools(skill_info.module)
            skill_info.loaded_at = datetime.now().isoformat()
        return skill_info


# ============================================================
# 5. МЕНЕДЖЕР СКИЛЛОВ
# ============================================================
class SkillManager:
    """
    Главный менеджер скиллов.
    Управляет жизненным циклом: установка, загрузка, выгрузка, удаление.
    """
    
    def __init__(self):
        self.skills: Dict[str, SkillInfo] = {}
        self.registry: dict = self._load_registry()
        
        # Создаем директории
        BUILTIN_DIR.mkdir(parents=True, exist_ok=True)
        CUSTOM_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_registry(self) -> dict:
        """Загрузка реестра"""
        if REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"version": "1.0.1", "skills": {}, "creation_history": []}
    
    def _save_registry(self):
        """Сохранение реестра"""
        self.registry["updated_at"] = datetime.now().isoformat()
        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.registry, f, indent=2, ensure_ascii=False)
    
    def discover_skills(self) -> List[Path]:
        """Поиск всех скиллов в папках"""
        skill_dirs = []
        
        for base_dir in [BUILTIN_DIR, CUSTOM_DIR]:
            if base_dir.exists():
                for item in base_dir.iterdir():
                    if item.is_dir() and (item / "manifest.json").exists():
                        skill_dirs.append(item)
        
        return skill_dirs
    
    def load_all_skills(self) -> Dict[str, SkillInfo]:
        """Загрузка ВСЕХ обнаруженных скиллов (включая отключенные)."""
        skill_dirs = self.discover_skills()
        
        for skill_dir in skill_dirs:
            try:
                # Всегда загружаем, но отмечаем enabled из реестра
                reg_entry = self.registry.get("skills", {}).get(skill_dir.name, {})
                if skill_dir.name not in self.skills:
                    info = self.load_skill_from_dir(skill_dir)
                    if info and reg_entry.get("enabled") is False:
                        info.enabled = False
            except Exception as e:
                logger.error(f"Ошибка загрузки скилла {skill_dir.name}: {e}")
        
        return self.skills
    
    def load_skill_from_dir(self, skill_dir: Path) -> Optional[SkillInfo]:
        """Загрузка одного скилла из папки"""
        # Валидация
        valid, msg = SkillValidator.validate_skill_dir(skill_dir)
        if not valid:
            logger.warning(f"Скилл {skill_dir.name}: {msg}")
            return None
        
        # Загружаем манифест
        valid, msg, manifest_data = SkillValidator.validate_manifest(
            skill_dir / "manifest.json"
        )
        if not valid:
            logger.warning(f"Манифест {skill_dir.name}: {msg}")
            return None
        
        # Создаем SkillManifest
        manifest = SkillManifest(**manifest_data)
        
        # Загружаем модуль
        module = SkillLoader.load_skill(skill_dir, manifest.name)
        if module is None:
            self._record_error(manifest.name)
            return None
        
        # Извлекаем инструменты
        tools = SkillLoader.extract_tools(module)
        
        # Создаем SkillInfo
        skill_info = SkillInfo(
            manifest=manifest,
            module=module,
            tools=tools,
            path=skill_dir,
            enabled=True,
            loaded_at=datetime.now().isoformat()
        )
        
        # Регистрируем
        self.skills[manifest.name] = skill_info
        
        # Обновляем реестр
        self.registry["skills"][manifest.name] = {
            "path": str(skill_dir.relative_to(SKILLS_DIR)),
            "enabled": True,
            "stability": manifest.stability,
            "loaded_at": skill_info.loaded_at,
            "errors": skill_info.errors,
            "version": manifest.version,
        }
        self._save_registry()
        
        logger.info(f"✅ Скилл загружен: {manifest.name} v{manifest.version} ({len(tools)} tools)")
        
        return skill_info
    
    def unload_skill(self, skill_name: str) -> bool:
        """Выгрузка скилла"""
        if skill_name not in self.skills:
            return False
        
        skill_info = self.skills.pop(skill_name)
        
        # Удаляем из sys.modules
        if skill_info.module:
            module_name = skill_info.module.__name__
            if module_name in sys.modules:
                del sys.modules[module_name]
        
        # Обновляем реестр
        if skill_name in self.registry["skills"]:
            self.registry["skills"][skill_name]["enabled"] = False
            self._save_registry()
        
        logger.info(f"🗑️ Скилл выгружен: {skill_name}")
        return True
    
    def reload_skill(self, skill_name: str) -> bool:
        """Горячая перезагрузка скилла"""
        if skill_name not in self.skills:
            return False
        
        skill_info = self.skills[skill_name]
        updated = SkillLoader.reload_skill(skill_info)
        
        if updated:
            self.skills[skill_name] = updated
            logger.info(f"🔄 Скилл перезагружен: {skill_name}")
            return True
        
        return False
    
    def get_all_tools(self) -> List[Callable]:
        """Получить все инструменты из всех скиллов"""
        all_tools = []
        for skill_info in self.skills.values():
            if skill_info.enabled:
                all_tools.extend(skill_info.tools)
        return all_tools
    
    def get_skill_triggers(self) -> Dict[str, str]:
        """Получить маппинг триггер → имя скилла"""
        triggers = {}
        for skill_info in self.skills.values():
            if skill_info.enabled:
                for trigger in skill_info.manifest.triggers:
                    triggers[trigger.lower()] = skill_info.manifest.name
        return triggers
    
    def _record_error(self, skill_name: str):
        """Запись ошибки скилла"""
        if skill_name in self.skills:
            self.skills[skill_name].errors += 1
        
        if skill_name in self.registry["skills"]:
            self.registry["skills"][skill_name]["errors"] += 1
            self._save_registry()
    
    def get_stats(self) -> dict:
        """Статистика скиллов"""
        return {
            "total": len(self.skills),
            "enabled": sum(1 for s in self.skills.values() if s.enabled),
            "stable": sum(1 for s in self.skills.values() if s.manifest.stability == "stable"),
            "testing": sum(1 for s in self.skills.values() if s.manifest.stability == "testing"),
            "errors": sum(s.errors for s in self.skills.values()),
            "total_tools": sum(len(s.tools) for s in self.skills.values()),
        }


# ============================================================
# 6. ТЕСТ
# ============================================================
def test_skill_manager():
    """Тест менеджера скиллов"""
    print("=" * 60)
    print("🧩 Тест Skill Manager")
    print("=" * 60)
    
    manager = SkillManager()
    
    # Поиск скиллов
    skill_dirs = manager.discover_skills()
    print(f"\n📁 Найдено скиллов: {len(skill_dirs)}")
    for d in skill_dirs:
        print(f"   • {d.name}")
    
    # Загрузка
    print("\n🔄 Загрузка скиллов...")
    manager.load_all_skills()
    
    # Статистика
    stats = manager.get_stats()
    print(f"\n📊 Статистика:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    
    # Триггеры
    triggers = manager.get_skill_triggers()
    print(f"\n🔔 Триггеры ({len(triggers)}):")
    for trigger, skill in list(triggers.items())[:10]:
        print(f"   '{trigger}' → {skill}")


if __name__ == "__main__":
    test_skill_manager()