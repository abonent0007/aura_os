# system_monitor.py
"""
Мониторинг стабильности AURA OS.
Отслеживает ошибки, создает бекапы, инициирует откаты.
"""

import os
import sys
import json
import time
import shutil
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List
from dataclasses import dataclass, field

from loguru import logger


# ============================================================
# 1. КОНФИГУРАЦИЯ МОНИТОРИНГА
# ============================================================
@dataclass
class MonitorConfig:
    """Настройки мониторинга"""
    check_interval_seconds: int = 60
    max_errors_per_minute: int = 5
    max_total_errors: int = 50
    backup_before_changes: bool = True
    auto_rollback_on_crash: bool = True
    stability_check_enabled: bool = True
    log_file: str = "logs/aura_monitor.log"


@dataclass
class SystemSnapshot:
    """Снимок состояния системы"""
    timestamp: str
    skills_count: int
    skills_errors: int
    active_tools: int
    memory_usage_mb: float
    uptime_seconds: float
    last_error: Optional[str] = None


# ============================================================
# 2. МОНИТОР
# ============================================================
class SystemMonitor:
    """
    Мониторит стабильность системы.
    При обнаружении проблем — создает бекап и может инициировать откат.
    """
    
    def __init__(self, config: MonitorConfig = None):
        self.config = config or MonitorConfig()
        self.snapshots: List[SystemSnapshot] = []
        self.error_count: int = 0
        self.errors_timestamps: List[float] = []
        self.start_time = time.time()
        self.last_backup_time: Optional[float] = None
        self.is_system_stable = True
        
        # Создаем папку для логов
        Path("logs").mkdir(exist_ok=True)
    
    def take_snapshot(self, skill_manager=None) -> SystemSnapshot:
        """Создание снимка текущего состояния"""
        import psutil
        
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        snapshot = SystemSnapshot(
            timestamp=datetime.now().isoformat(),
            skills_count=len(skill_manager.skills) if skill_manager else 0,
            skills_errors=sum(s.errors for s in skill_manager.skills.values()) if skill_manager else 0,
            active_tools=len(skill_manager.get_all_tools()) if skill_manager else 0,
            memory_usage_mb=round(memory_mb, 2),
            uptime_seconds=time.time() - self.start_time,
        )
        
        self.snapshots.append(snapshot)
        
        # Храним не более 100 снимков
        if len(self.snapshots) > 100:
            self.snapshots = self.snapshots[-100:]
        
        return snapshot
    
    def record_error(self, error: Exception, context: str = ""):
        """Запись ошибки"""
        now = time.time()
        self.error_count += 1
        self.errors_timestamps.append(now)
        
        # Удаляем старые (> 1 минуты)
        self.errors_timestamps = [t for t in self.errors_timestamps if now - t < 60]
        
        logger.error(f"❌ [{context}] {error}")
        
        # Проверка на превышение лимитов
        recent_errors = len(self.errors_timestamps)
        
        if recent_errors >= self.config.max_errors_per_minute:
            logger.critical(
                f"🚨 КРИТИЧЕСКИ: {recent_errors} ошибок за минуту! "
                f"Лимит: {self.config.max_errors_per_minute}"
            )
            self.is_system_stable = False
            return "critical"
        
        if self.error_count >= self.config.max_total_errors:
            logger.critical(
                f"🚨 КРИТИЧЕСКИ: {self.error_count} всего ошибок! "
                f"Лимит: {self.config.max_total_errors}"
            )
            self.is_system_stable = False
            return "critical"
        
        return "warning"
    
    def should_rollback(self) -> bool:
        """Проверяет, нужен ли откат"""
        if not self.config.auto_rollback_on_crash:
            return False
        
        return not self.is_system_stable
    
    def check_health(self, skill_manager=None) -> dict:
        """Проверка здоровья системы"""
        snapshot = self.take_snapshot(skill_manager)
        
        health = {
            "status": "healthy" if self.is_system_stable else "unstable",
            "snapshot": snapshot,
            "error_rate_per_minute": len(self.errors_timestamps),
            "total_errors": self.error_count,
            "uptime_hours": round(snapshot.uptime_seconds / 3600, 2),
            "recommendations": []
        }
        
        # Рекомендации
        if len(self.errors_timestamps) > self.config.max_errors_per_minute * 0.8:
            health["recommendations"].append("Высокая частота ошибок. Рекомендован откат.")
        
        if snapshot.memory_usage_mb > 1000:
            health["recommendations"].append("Высокое потребление памяти. Рекомендована перезагрузка скиллов.")
        
        return health


# ============================================================
# 3. ТЕСТ
# ============================================================
def test_monitor():
    """Тест мониторинга"""
    monitor = SystemMonitor()
    
    print("📊 Снимок системы:")
    snapshot = monitor.take_snapshot()
    print(f"   Память: {snapshot.memory_usage_mb} MB")
    print(f"   Аптайм: {snapshot.uptime_seconds:.0f}с")
    
    print("\n📝 Симуляция ошибок:")
    for i in range(3):
        status = monitor.record_error(ValueError(f"Тест ошибки {i}"), "test")
        print(f"   Ошибка {i+1}: {status}")
    
    health = monitor.check_health()
    print(f"\n🏥 Статус: {health['status']}")
    print(f"   Ошибок/мин: {health['error_rate_per_minute']}")


if __name__ == "__main__":
    test_monitor()