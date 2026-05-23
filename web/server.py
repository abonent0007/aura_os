#!/usr/bin/env python3
"""
Веб-интерфейс AURA OS.
Доступен локально и через Tailscale.
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from dotenv import load_dotenv

load_dotenv()

# ============================================================
# 1. КОНФИГУРАЦИЯ СЕРВЕРА
# ============================================================
WEB_DIR = Path(__file__).parent
ROOT_DIR = WEB_DIR.parent
STATIC_DIR = WEB_DIR / "static"
TEMPLATES_DIR = WEB_DIR / "templates"

# Загружаем конфиг
with open(ROOT_DIR / "config.json", "r", encoding="utf-8") as f:
    APP_CONFIG = json.load(f)

WEB_CONFIG = APP_CONFIG.get("web_interface", {})
HOST = WEB_CONFIG.get("host", "0.0.0.0")
PORT = WEB_CONFIG.get("port", 8000)
TAILSCALE_ENABLED = WEB_CONFIG.get("tailscale", {}).get("enabled", True)
TAILSCALE_HOSTNAME = WEB_CONFIG.get("tailscale", {}).get("hostname", "aura-os")

# Инициализация FastAPI
app = FastAPI(
    title="AURA OS Dashboard",
    version="1.0.1",
    description="Веб-интерфейс управления персональным ассистентом"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Статика и шаблоны
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


# ============================================================
# 2. ГЛОБАЛЬНЫЕ СОСТОЯНИЯ
# ============================================================
class AppState:
    """Глобальное состояние приложения"""
    aura_agent = None
    skill_manager = None
    rollback_manager = None
    system_monitor = None
    skill_builder = None
    avatar = None  # Плагин AURA Avatar
    
    # WebSocket соединения
    active_connections: List[WebSocket] = []
    
    # Логи в памяти
    logs: List[Dict] = []
    max_logs = 500

state = AppState()


# ============================================================
# 3. МОДЕЛИ API
# ============================================================
class SkillCreateRequest(BaseModel):
    description: str

class SkillToggleRequest(BaseModel):
    skill_name: str
    enabled: bool

class ConfigUpdateRequest(BaseModel):
    section: str
    key: str
    value: Any

class MessageRequest(BaseModel):
    text: str
    user_id: str = "web_user"

class RollbackRequest(BaseModel):
    backup_id: Optional[str] = None


# ============================================================
# 4. ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ============================================================
def get_tailscale_ip() -> Optional[str]:
    """Получить Tailscale IP"""
    try:
        result = subprocess.run(
            ["tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except:
        pass
    return None

def get_tailscale_status() -> dict:
    """Статус Tailscale"""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except:
        pass
    return {"error": "Tailscale не установлен или не настроен"}

def add_log(level: str, message: str, source: str = "web"):
    """Добавить лог"""
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "message": message,
        "source": source,
    }
    state.logs.append(log_entry)
    
    if len(state.logs) > state.max_logs:
        state.logs = state.logs[-state.max_logs:]

async def broadcast(event: str, data: dict):
    """Отправка данных всем WebSocket клиентам"""
    for connection in state.active_connections:
        try:
            await connection.send_json({"event": event, "data": data})
        except:
            pass


# ============================================================
# 5. WEB-СТРАНИЦА
# ============================================================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница дашборда"""
    tailscale_ip = get_tailscale_ip()
    tailscale_status = get_tailscale_status() if TAILSCALE_ENABLED else None
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "app_name": "AURA OS",
            "version": "1.0.0",
            "port": PORT,
            "tailscale_ip": tailscale_ip,
            "tailscale_hostname": TAILSCALE_HOSTNAME,
            "tailscale_status": tailscale_status,
            "local_url": f"http://localhost:{PORT}",
            "tailscale_url": f"http://{TAILSCALE_HOSTNAME}:{PORT}" if tailscale_ip else None,
        }
    )


# ============================================================
# 6. API — ДАШБОРД
# ============================================================
@app.get("/api/status")
async def get_status():
    """Общий статус системы"""
    tailscale_ip = get_tailscale_ip()
    
    skill_stats = {}
    if state.skill_manager:
        skill_stats = state.skill_manager.get_stats()
    
    health = {}
    if state.system_monitor:
        health = state.system_monitor.check_health(state.skill_manager)
    
    # Количество событий в календаре
    calendar_count = 0
    if state.aura_agent:
        try:
            events = state.aura_agent.db.get_upcoming_events(days=7)
            calendar_count = len(events)
        except:
            pass
    
    return {
        "status": "running",
        "uptime": health.get("uptime_hours", 0),
        "version": "1.0.0",
        "network": {
            "local_url": f"http://localhost:{PORT}",
            "tailscale_url": f"http://{TAILSCALE_HOSTNAME}:{PORT}" if tailscale_ip else None,
            "tailscale_ip": tailscale_ip,
            "tailscale_enabled": TAILSCALE_ENABLED,
        },
        "skills": skill_stats,
        "calendar": {
            "upcoming_events": calendar_count,
        },
        "memory": {
            "conversations": len(state.aura_agent.db.get_recent_summaries(30)) if state.aura_agent else 0,
            "facts": len(state.aura_agent.db.get_relevant_facts(50)) if state.aura_agent else 0,
        },
        "health": health.get("status", "unknown"),
    }

@app.get("/api/dashboard/history")
async def get_dashboard_history():
    """История для графиков дашборда"""
    now = datetime.now()
    
    # Генерируем тестовые данные (в будущем — из мониторинга)
    history = []
    for i in range(24):
        hour = now - timedelta(hours=23 - i)
        history.append({
            "timestamp": hour.isoformat(),
            "messages": abs(10 - (i % 5)) + 2,  # Пример
            "errors": max(0, (i % 3) - 1),
            "memory_mb": 150 + (i % 20) * 5,
        })
    
    return {"history": history}


# ============================================================
# 7. API — ЛОГИ
# ============================================================
@app.get("/api/logs")
async def get_logs(limit: int = 100, level: str = None):
    """Получить логи"""
    logs = state.logs
    
    if level:
        logs = [l for l in logs if l["level"] == level]
    
    return {
        "logs": logs[-limit:],
        "total": len(logs),
        "levels": {
            "info": sum(1 for l in logs if l["level"] == "info"),
            "warning": sum(1 for l in logs if l["level"] == "warning"),
            "error": sum(1 for l in logs if l["level"] == "error"),
        }
    }

@app.post("/api/logs/clear")
async def clear_logs():
    """Очистить логи"""
    state.logs = []
    add_log("info", "Логи очищены", "web")
    await broadcast("logs_cleared", {})
    return {"status": "ok"}


# ============================================================
# 8. API — СКИЛЛЫ
# ============================================================
@app.get("/api/skills")
async def get_skills():
    """Список скиллов"""
    if not state.skill_manager:
        return {"skills": {}, "stats": {}}
    
    skills = {}
    for name, info in state.skill_manager.skills.items():
        skills[name] = {
            "name": name,
            "version": info.manifest.version,
            "description": info.manifest.description,
            "category": info.manifest.category,
            "enabled": info.enabled,
            "stability": info.manifest.stability,
            "triggers": info.manifest.triggers,
            "tools_count": len(info.tools),
            "errors": info.errors,
            "loaded_at": info.loaded_at,
            "auto_created": info.manifest.auto_created,
        }
    
    return {
        "skills": skills,
        "stats": state.skill_manager.get_stats(),
        "triggers": state.skill_manager.get_skill_triggers(),
    }

@app.get("/api/skills/{skill_name}/code")
async def get_skill_code(skill_name: str):
    """Получить код скилла"""
    if not state.skill_manager:
        raise HTTPException(404, "Менеджер скиллов не инициализирован")

    if skill_name not in state.skill_manager.skills:
        raise HTTPException(404, f"Скилл {skill_name} не найден")

    skill_info = state.skill_manager.skills[skill_name]

    code = {}
    if skill_info.path:
        for file in ["manifest.json", "SKILL.md", "skill.py"]:
            file_path = skill_info.path / file
            if file_path.exists():
                code[file] = file_path.read_text(encoding="utf-8")

    return code


class SkillCodeUpdate(BaseModel):
    file: str  # "manifest.json", "SKILL.md", "skill.py"
    content: str


@app.put("/api/skills/{skill_name}/code")
async def save_skill_code(skill_name: str, request: SkillCodeUpdate):
    """Сохранить изменённый код скилла"""
    if not state.skill_manager:
        raise HTTPException(404, "Менеджер скиллов не инициализирован")

    if skill_name not in state.skill_manager.skills:
        raise HTTPException(404, f"Скилл {skill_name} не найден")

    if request.file not in ("manifest.json", "SKILL.md", "skill.py"):
        raise HTTPException(400, "file must be: manifest.json, SKILL.md, skill.py")

    skill_info = state.skill_manager.skills[skill_name]
    if not skill_info.path:
        raise HTTPException(400, "Скилл не имеет пути (builtin?)")

    file_path = skill_info.path / request.file
    try:
        file_path.write_text(request.content, encoding="utf-8")
        # Перезагружаем скилл после сохранения
        if skill_info.enabled:
            state.skill_manager.reload_skill(skill_name)
        add_log("info", f"Код скилла {skill_name}/{request.file} обновлён", "web")
        return {"status": "ok", "file": request.file}
    except Exception as e:
        raise HTTPException(500, f"Ошибка сохранения: {e}")

@app.post("/api/skills/create")
async def create_skill(request: SkillCreateRequest):
    """Создать новый скилл"""
    if not state.skill_builder:
        raise HTTPException(400, "Генератор скиллов не инициализирован")

    add_log("info", f"Создание скилла: {request.description}", "web")

    result = await state.skill_builder.build_skill(request.description)

    if result["success"]:
        add_log("info", f"Скилл создан: {result['skill_name']}", "skill_builder")
        # Переподхватываем новые скиллы
        state.skill_manager.load_all_skills()
        await broadcast("skill_created", {"name": result["skill_name"]})

    return result

@app.post("/api/skills/{skill_name}/toggle")
async def toggle_skill(skill_name: str, request: SkillToggleRequest):
    """Включить/выключить скилл"""
    if not state.skill_manager:
        raise HTTPException(400, "Менеджер скиллов не инициализирован")

    if request.enabled:
        # Ищем папку скилла и загружаем заново
        for base in [Path(__file__).parent.parent / "skills" / "builtin",
                      Path(__file__).parent.parent / "skills" / "custom"]:
            skill_dir = base / skill_name
            if skill_dir.exists() and (skill_dir / "manifest.json").exists():
                state.skill_manager.load_skill_from_dir(skill_dir)
                add_log("info", f"Скилл включен: {skill_name}", "web")
                break
        else:
            raise HTTPException(404, f"Скилл {skill_name} не найден")
    else:
        state.skill_manager.unload_skill(skill_name)
        add_log("info", f"Скилл выключен: {skill_name}", "web")
    
    await broadcast("skill_toggled", {"name": skill_name, "enabled": request.enabled})
    return {"status": "ok"}

@app.delete("/api/skills/{skill_name}")
async def delete_skill(skill_name: str):
    """Удалить скилл"""
    if not state.skill_manager:
        raise HTTPException(400, "Менеджер скиллов не инициализирован")
    
    # Выгружаем
    state.skill_manager.unload_skill(skill_name)
    
    # Запрет удаления встроенных скиллов
    import re
    if skill_name in [d.name for d in (Path(__file__).parent.parent / "skills" / "builtin").iterdir() if d.is_dir()]:
        raise HTTPException(403, "Нельзя удалить встроенный скилл")
    
    # Удаляем папку
    skill_path = Path(__file__).parent.parent / "skills" / "custom" / skill_name
    if skill_path.exists():
        import shutil
        shutil.rmtree(skill_path)
    
    add_log("info", f"Скилл удален: {skill_name}", "web")
    await broadcast("skill_deleted", {"name": skill_name})
    return {"status": "ok"}


# ============================================================
# 9. API — НАСТРОЙКИ
# ============================================================
@app.get("/api/config")
async def get_config():
    """Получить конфигурацию (без секретов)"""
    config_copy = json.loads(json.dumps(APP_CONFIG))
    
    # Маскируем чувствительные данные
    for section in config_copy:
        if isinstance(config_copy[section], dict):
            for key in list(config_copy[section].keys()):
                if any(s in key.lower() for s in ["key", "token", "secret", "password"]):
                    val = config_copy[section][key]
                    if isinstance(val, str) and len(val) > 8:
                        config_copy[section][key] = val[:4] + "****" + val[-4:]
    
    return config_copy

@app.put("/api/config")
async def update_config(request: ConfigUpdateRequest):
    """Обновить настройку (поддерживает вложенные ключи через точку: voice.input.engine)"""
    if state.rollback_manager:
        state.rollback_manager.create_backup(reason=f"config_update_{request.section}_{request.key}")

    # Поддержка вложенных ключей: "input.engine" → APP_CONFIG["voice"]["input"]["engine"]
    keys = request.key.split(".")
    if request.section in APP_CONFIG:
        target = APP_CONFIG[request.section]
        for k in keys[:-1]:
            if k in target and isinstance(target[k], dict):
                target = target[k]
            else:
                raise HTTPException(400, f"Ключ {k} не найден в {request.section}")
        target[keys[-1]] = request.value

    with open(ROOT_DIR / "config.json", "w", encoding="utf-8") as f:
        json.dump(APP_CONFIG, f, indent=2, ensure_ascii=False)

    add_log("info", f"Конфиг обновлен: {request.section}.{request.key}", "web")
    await broadcast("config_updated", {"section": request.section, "key": request.key})
    return {"status": "ok"}


# ============================================================
# 10. API — БЕКАПЫ И ОТКАТЫ
# ============================================================
@app.get("/api/backups")
async def get_backups():
    """Список бекапов"""
    if not state.rollback_manager:
        return {"backups": []}
    
    return {"backups": state.rollback_manager.list_backups()}

@app.post("/api/backups/create")
async def create_backup():
    """Создать бекап вручную"""
    if not state.rollback_manager:
        raise HTTPException(400, "Менеджер откатов не инициализирован")
    
    backup = state.rollback_manager.create_backup(reason="manual", is_automatic=False)
    
    if backup:
        add_log("info", f"Бекап создан: {backup.id}", "web")
        await broadcast("backup_created", {"id": backup.id})
        return {"status": "ok", "backup_id": backup.id}
    
    raise HTTPException(500, "Ошибка создания бекапа")

@app.post("/api/backups/rollback")
async def rollback(request: RollbackRequest):
    """Откат к бекапу"""
    if not state.rollback_manager:
        raise HTTPException(400, "Менеджер откатов не инициализирован")
    
    success = state.rollback_manager.rollback(request.backup_id)
    
    if success:
        add_log("warning", "Выполнен откат системы", "web")
        await broadcast("rollback_performed", {"backup_id": request.backup_id})
        return {"status": "ok"}
    
    raise HTTPException(500, "Ошибка отката")


# ============================================================
# 11. API — КАЛЕНДАРЬ
# ============================================================
@app.get("/api/calendar")
async def get_calendar(days: str = "7"):
    """События календаря"""
    try:
        days_int = int(days)
    except (ValueError, TypeError):
        days_int = 7
    if days_int < 1 or days_int > 365:
        days_int = 7

    if not state.aura_agent:
        return {"events": []}

    # Все события: прошедший год + будущие
    from datetime import date, timedelta
    events = []
    d = date.today() - timedelta(days=365)
    end = date.today() + timedelta(days=days_int)
    while d <= end:
        day_events = state.aura_agent.db.get_events_for_date(d.isoformat(), include_completed=True)
        events.extend(day_events)
        d += timedelta(days=1)

    return {
        "events": events,
        "total": len(events),
    }


@app.post("/api/calendar/sync")
async def sync_calendar():
    """Ручная синхронизация с Google Calendar"""
    if not state.aura_agent:
        raise HTTPException(400, "Агент не инициализирован")
    if not state.aura_agent.google_sync:
        raise HTTPException(400, "Google Calendar не подключен. Проверь: 1) credentials.json в корне проекта 2) Google Calendar API включен в config.json")

    try:
        stats = await state.aura_agent.google_sync.full_sync()
        add_log("info", f"Синхронизация Google Calendar: {stats}", "calendar")
        return {"status": "ok", "stats": stats}
    except Exception as e:
        raise HTTPException(500, f"Ошибка синхронизации: {e}")


@app.get("/api/diagnose")
async def diagnose():
    """Самодиагностика ядра AURA OS"""
    if not state.aura_agent:
        raise HTTPException(400, "Агент не инициализирован")
    return {"report": state.aura_agent.get_self_diagnosis()}


# ============================================================
# 12. API — ОБЩЕНИЕ С АГЕНТОМ
# ============================================================
@app.post("/api/chat")
async def chat(request: MessageRequest):
    """Отправить сообщение агенту"""
    if not state.aura_agent:
        raise HTTPException(400, "Агент не инициализирован")

    add_log("info", f"Сообщение: {request.text[:100]}", "chat")

    response = await state.aura_agent.process(request.text, request.user_id)

    return {
        "text": response,
        "user_id": request.user_id,
    }


@app.post("/api/chat/expert")
async def chat_expert(request: MessageRequest):
    """Экспертный режим: мультиагентный оркестратор DeepSeek."""
    try:
        from plugins.aura_orchestrator.aura_orchestrator import orchestrate
        add_log("info", f"Expert: {request.text[:100]}", "expert")
        result = await orchestrate(request.text)
        return {"text": result, "user_id": request.user_id, "mode": "expert"}
    except ImportError:
        raise HTTPException(500, "Orchestrator plugin not available. Install sentence-transformers.")
    except Exception as e:
        raise HTTPException(500, f"Orchestrator error: {e}")


class TTSRequest(BaseModel):
    text: str


@app.post("/api/chat/tts")
async def chat_tts(request: TTSRequest):
    """Генерирует TTS аудио (MP3). Очищает текст от эмодзи и маркдауна."""
    try:
        import re
        text = request.text
        # Очистка для голоса
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'`(.+?)`', r'\1', text)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Оставляем только буквы, цифры, пробелы, пунктуацию и переносы строк
        text = re.sub(r'[^a-zA-Zа-яА-ЯёЁ0-9\s\.\,\!\?\;\:\-\(\)\n]', '', text, flags=re.UNICODE)
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            text = "Нет текста для озвучивания."

        from aura_voice import TextToSpeech
        tts = TextToSpeech(
            engine=os.getenv("TTS_ENGINE", "edge_tts"),
            voice=os.getenv("TTS_VOICE", "ru-RU-SvetlanaNeural")
        )
        audio_bytes = await tts.synthesize_to_bytes(text)

        # Точная длительность аудио через pydub
        audio_duration = len(audio_bytes) / 16000  # fallback
        try:
            from pydub import AudioSegment
            import io
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            audio_duration = len(seg) / 1000.0  # миллисекунды → секунды
        except Exception:
            pass

        # Аватар: запускаем анимацию синхронно со звуком
        if state.avatar:
            try:
                import threading
                threading.Thread(
                    target=lambda: state.avatar.speak(request.text, audio_duration),
                    daemon=True
                ).start()
            except Exception:
                pass

        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline; filename=aura_response.mp3"}
        )
    except Exception as e:
        raise HTTPException(500, f"TTS error: {e}")


@app.post("/api/avatar/stop")
async def avatar_stop():
    """Остановить анимацию аватара."""
    if state.avatar:
        try:
            state.avatar.stop()
        except Exception:
            pass
    return {"status": "ok"}


@app.get("/api/timezones")
async def get_timezones():
    """Список популярных часовых поясов."""
    zones = [
        {"value": "Europe/Moscow", "label": "Москва (MSK, UTC+3)"},
        {"value": "Europe/Kaliningrad", "label": "Калининград (UTC+2)"},
        {"value": "Europe/Samara", "label": "Самара (UTC+4)"},
        {"value": "Asia/Yekaterinburg", "label": "Екатеринбург (UTC+5)"},
        {"value": "Asia/Omsk", "label": "Омск (UTC+6)"},
        {"value": "Asia/Krasnoyarsk", "label": "Красноярск (UTC+7)"},
        {"value": "Asia/Irkutsk", "label": "Иркутск (UTC+8)"},
        {"value": "Asia/Yakutsk", "label": "Якутск (UTC+9)"},
        {"value": "Asia/Vladivostok", "label": "Владивосток (UTC+10)"},
        {"value": "Asia/Magadan", "label": "Магадан (UTC+11)"},
        {"value": "Asia/Kamchatka", "label": "Камчатка (UTC+12)"},
        {"value": "Europe/London", "label": "Лондон (UTC+0)"},
        {"value": "Europe/Berlin", "label": "Берлин (UTC+1)"},
        {"value": "Europe/Paris", "label": "Париж (UTC+1)"},
        {"value": "America/New_York", "label": "Нью-Йорк (UTC-5)"},
        {"value": "America/Chicago", "label": "Чикаго (UTC-6)"},
        {"value": "America/Los_Angeles", "label": "Лос-Анджелес (UTC-8)"},
        {"value": "Asia/Dubai", "label": "Дубай (UTC+4)"},
        {"value": "Asia/Tokyo", "label": "Токио (UTC+9)"},
        {"value": "Asia/Shanghai", "label": "Шанхай (UTC+8)"},
    ]
    return {"timezones": zones}


# ============================================================
# 13. WEBSOCKET — РЕАЛЬНОЕ ВРЕМЯ
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket для real-time обновлений"""
    await websocket.accept()
    state.active_connections.append(websocket)
    
    add_log("info", "WebSocket подключен", "websocket")
    
    try:
        # Отправляем начальное состояние
        await websocket.send_json({
            "event": "connected",
            "data": {"message": "WebSocket подключен"}
        })
        
        while True:
            # Принимаем сообщения от клиента
            data = await websocket.receive_json()
            
            if data.get("type") == "ping":
                await websocket.send_json({"event": "pong", "data": {}})
            
            elif data.get("type") == "chat":
                # Чат через WebSocket
                if state.aura_agent:
                    response = await state.aura_agent.process(
                        data.get("text", ""),
                        data.get("user_id", "web_user")
                    )
                    await websocket.send_json({
                        "event": "chat_response",
                        "data": {"text": response}
                    })
    
    except WebSocketDisconnect:
        state.active_connections.remove(websocket)
        add_log("info", "WebSocket отключен", "websocket")


# ============================================================
# 14. ЗАПУСК СЕРВЕРА
# ============================================================
def init_web_server(aura_agent, skill_manager, rollback_manager, system_monitor, skill_builder):
    """Инициализация веб-сервера с зависимостями"""
    state.aura_agent = aura_agent
    state.skill_manager = skill_manager
    state.rollback_manager = rollback_manager
    state.system_monitor = system_monitor
    state.skill_builder = skill_builder

    # Инициализация аватара
    try:
        from plugins.aura_avatar.aura_avatar import AuraAvatar
        state.avatar = AuraAvatar()
        print("[avatar] AURA Avatar initialized")
    except Exception as e:
        print(f"[avatar] Avatar init skipped: {e}")
        state.avatar = None

    add_log("info", "Веб-сервер инициализирован", "system")

def start_web_server(host: str = None, port: int = None):
    """Запуск веб-сервера"""
    h = host or HOST
    p = port or PORT
    
    print(f"\n🌐 Веб-интерфейс AURA OS:")
    print(f"   Локально:  http://localhost:{p}")
    
    tailscale_ip = get_tailscale_ip()
    if tailscale_ip and TAILSCALE_ENABLED:
        print(f"   Tailscale: http://{TAILSCALE_HOSTNAME}:{p}")
        print(f"   Tailscale: http://{tailscale_ip}:{p}")
    
    print()
    
    uvicorn.run(
        app,
        host=h,
        port=p,
        log_level="info"
    )


if __name__ == "__main__":
    print("AURA OS Web Server")
    print("Запускайте через main.py: python main.py --web")