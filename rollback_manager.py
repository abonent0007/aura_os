# rollback_manager.py
"""
Система откатов AURA OS.
Автоматические бекапы и восстановление при сбоях.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass

from loguru import logger


# ============================================================
# 1. КОНФИГУРАЦИЯ
# ============================================================
BACKUPS_DIR = Path(__file__).parent / "skills" / "backups"
MAX_BACKUPS = 10

FILES_TO_BACKUP = [
    "config.json",
    "aura_core.py",
    "skill_manager.py",
    "skills/registry.json",
    ".env",
]


@dataclass
class BackupInfo:
    """Информация о бекапе"""
    id: str
    timestamp: str
    reason: str
    files: List[str]
    is_automatic: bool = True


# ============================================================
# 2. МЕНЕДЖЕР ОТКАТОВ
# ============================================================
class RollbackManager:
    """
    Управление бекапами и откатами.
    """
    
    def __init__(self):
        self.backups: List[BackupInfo] = []
        self._ensure_backup_dir()
        self._load_backup_index()
    
    def _ensure_backup_dir(self):
        """Создание папки бекапов"""
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    
    def _load_backup_index(self):
        """Загрузка индекса бекапов"""
        index_file = BACKUPS_DIR / "index.json"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.backups = [BackupInfo(**b) for b in data.get("backups", [])]
    
    def _save_backup_index(self):
        """Сохранение индекса"""
        index_file = BACKUPS_DIR / "index.json"
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump({
                "backups": [
                    {
                        "id": b.id,
                        "timestamp": b.timestamp,
                        "reason": b.reason,
                        "files": b.files,
                        "is_automatic": b.is_automatic,
                    }
                    for b in self.backups
                ],
                "updated_at": datetime.now().isoformat()
            }, f, indent=2, ensure_ascii=False)
    
    def create_backup(self, reason: str = "manual", is_automatic: bool = True) -> Optional[BackupInfo]:
        """
        Создание бекапа критических файлов.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        backup_id = f"backup_{timestamp}"
        backup_dir = BACKUPS_DIR / backup_id
        
        try:
            backup_dir.mkdir(parents=True, exist_ok=True)
            backed_files = []
            
            for file_path in FILES_TO_BACKUP:
                full_path = Path(__file__).parent / file_path
                
                if full_path.exists():
                    # Сохраняем структуру папок
                    dest = backup_dir / file_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    
                    shutil.copy2(full_path, dest)
                    backed_files.append(file_path)
                    logger.debug(f"📄 Бекап: {file_path}")
            
            backup_info = BackupInfo(
                id=backup_id,
                timestamp=timestamp,
                reason=reason,
                files=backed_files,
                is_automatic=is_automatic,
            )
            
            self.backups.append(backup_info)
            self._save_backup_index()
            
            # Удаляем старые бекапы
            self._cleanup_old_backups()
            
            logger.info(f"✅ Бекап создан: {backup_id} ({len(backed_files)} файлов)")
            return backup_info
            
        except Exception as e:
            logger.error(f"❌ Ошибка бекапа: {e}")
            return None
    
    def rollback(self, backup_id: str = None) -> bool:
        """
        Откат к бекапу.
        Если backup_id не указан — откат к последнему.
        """
        if not self.backups:
            logger.error("❌ Нет бекапов для отката")
            return False
        
        # Выбираем бекап
        if backup_id:
            backup = next((b for b in self.backups if b.id == backup_id), None)
        else:
            backup = self.backups[-1]  # Последний
        
        if not backup:
            logger.error(f"❌ Бекап не найден: {backup_id}")
            return False
        
        backup_dir = BACKUPS_DIR / backup.id
        
        if not backup_dir.exists():
            logger.error(f"❌ Папка бекапа не существует: {backup_dir}")
            return False
        
        try:
            # Создаем бекап текущего состояния перед откатом
            self.create_backup(reason="pre_rollback", is_automatic=True)
            
            # Восстанавливаем файлы
            restored = 0
            for file_path in backup.files:
                src = backup_dir / file_path
                dest = Path(__file__).parent / file_path
                
                if src.exists():
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
                    restored += 1
                    logger.info(f"🔄 Восстановлен: {file_path}")
            
            logger.info(f"✅ Откат выполнен: {restored} файлов из бекапа {backup.id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка отката: {e}")
            return False
    
    def _cleanup_old_backups(self):
        """Удаление старых бекапов (оставляем MAX_BACKUPS)"""
        while len(self.backups) > MAX_BACKUPS:
            oldest = self.backups.pop(0)
            backup_dir = BACKUPS_DIR / oldest.id
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
                logger.debug(f"🗑️ Удален старый бекап: {oldest.id}")
        
        self._save_backup_index()
    
    def list_backups(self) -> List[dict]:
        """Список доступных бекапов"""
        return [
            {
                "id": b.id,
                "timestamp": b.timestamp,
                "reason": b.reason,
                "files_count": len(b.files),
                "is_automatic": b.is_automatic,
            }
            for b in self.backups
        ]
    
    def get_latest_backup(self) -> Optional[BackupInfo]:
        """Последний бекап"""
        return self.backups[-1] if self.backups else None


# ============================================================
# 3. ТЕСТ
# ============================================================
def test_rollback():
    """Тест системы откатов"""
    print("=" * 60)
    print("🔄 Тест Rollback Manager")
    print("=" * 60)
    
    rm = RollbackManager()
    
    # Создаем бекап
    print("\n📦 Создание бекапа...")
    backup = rm.create_backup(reason="test")
    if backup:
        print(f"   ID: {backup.id}")
        print(f"   Файлов: {len(backup.files)}")
    
    # Список бекапов
    print("\n📋 Список бекапов:")
    for b in rm.list_backups():
        print(f"   • {b['timestamp']} — {b['reason']} ({b['files_count']} файлов)")


if __name__ == "__main__":
    test_rollback()