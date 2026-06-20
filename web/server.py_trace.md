# `C:\aura_os\web\server.py` — Full Trace Document

| Lines | Section |
|-------|---------|
| 1–6 | Docstring / header comment |
| 7–14 | Standard library imports |
| 16–20 | FastAPI core imports |
| 21–22 | Third-party imports (Pydantic, uvicorn) |
| 24–26 | dotenv load |
| 28–30 | Section header: Конфигурация сервера |
| 31–34 | Path constants (`WEB_DIR`, `ROOT_DIR`, `STATIC_DIR`, `TEMPLATES_DIR`) |
| 37–38 | Load `config.json` → `APP_CONFIG` |
| 40–44 | Extract `WEB_CONFIG`, `HOST`, `PORT`, tailscale flags |
| 46–51 | `app = FastAPI(...)` instantiation |
| 53–60 | CORS middleware |
| 62–64 | Static file mount + Jinja2 templates |
| 67–69 | Section header: Глобальные состояния |
| 70–86 | `AppState` class + `state = AppState()` |
| 89–91 | Section header: Модели API |
| 92–109 | Pydantic request models |
| 112–114 | Section header: Вспомогательные функции |
| 115–126 | `get_tailscale_ip()` |
| 128–139 | `get_tailscale_status()` |
| 141–152 | `add_log()` |
| 154–160 | `broadcast()` async |
| 163–165 | Section header: WEB-страница |
| 166–183 | `GET /` — index page |
| 186–188 | Section header: API — ДАШБОРД |
| 189–230 | `GET /api/status` |
| 232–248 | `GET /api/dashboard/history` |
| 251–253 | Section header: API — ЛОГИ |
| 254–270 | `GET /api/logs` |
| 272–278 | `POST /api/logs/clear` |
| 281–283 | Section header: API — СКИЛЛЫ |
| 284–310 | `GET /api/skills` |
| 312–330 | `GET /api/skills/{skill_name}/code` |
| 333–336 | `SkillCodeUpdate` (inline Pydantic model) |
| 338–363 | `PUT /api/skills/{skill_name}/code` |
| 365–381 | `POST /api/skills/create` |
| 383–405 | `POST /api/skills/{skill_name}/toggle` |
| 407–429 | `DELETE /api/skills/{skill_name}` |
| 432–434 | Section header: API — НАСТРОЙКИ |
| 435–449 | `GET /api/config` |
| 451–473 | `PUT /api/config` |
| 476–478 | Section header: API — БЕКАПЫ И ОТКАТЫ |
| 479–485 | `GET /api/backups` |
| 487–500 | `POST /api/backups/create` |
| 502–515 | `POST /api/backups/rollback` |
| 518–520 | Section header: API — КАЛЕНДАРЬ |
| 521–547 | `GET /api/calendar` |
| 550–563 | `POST /api/calendar/sync` |
| 566–571 | `GET /api/diagnose` |
| 574–576 | Section header: API — ОБЩЕНИЕ С АГЕНТОМ |
| 577–590 | `POST /api/chat` |
| 593–604 | `POST /api/chat/expert` |
| 607–608 | `TTSRequest` (inline Pydantic model) |
| 611–653 | `POST /api/chat/tts` |
| 656–664 | `POST /api/avatar/stop` |
| 667–692 | `GET /api/timezones` |
| 695–697 | Section header: WEBSOCKET |
| 698–734 | `WS /ws` |
| 737–739 | Section header: ЗАПУСК СЕРВЕРА |
| 740–757 | `init_web_server()` |
| 759–779 | `start_web_server()` |
| 782–784 | `__main__` guard |

---

## 1. ALL IMPORTS

### Standard library (lines 7–14)
| Line | Import |
|------|--------|
| 7 | `import os` |
| 8 | `import sys` |
| 9 | `import json` |
| 10 | `import asyncio` |
| 11 | `import subprocess` |
| 12 | `from pathlib import Path` |
| 13 | `from datetime import datetime, timedelta` |
| 14 | `from typing import Optional, Dict, List, Any` |

### FastAPI core (lines 16–20)
| Line | Import |
|------|--------|
| 16 | `from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request` |
| 17 | `from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response` |
| 18 | `from fastapi.staticfiles import StaticFiles` |
| 19 | `from fastapi.templating import Jinja2Templates` |
| 20 | `from fastapi.middleware.cors import CORSMiddleware` |

### Third-party (lines 21–22)
| Line | Import |
|------|--------|
| 21 | `from pydantic import BaseModel` |
| 22 | `import uvicorn` |

### Env loader (lines 24–26)
| Line | Import |
|------|--------|
| 24 | `from dotenv import load_dotenv` |
| 26 | `load_dotenv()` — called at module level |

### Lazy / dynamic imports (not at module top-level)

| Location | Import | Line |
|----------|--------|------|
| `delete_skill()` | `import shutil` | 424 |
| `get_calendar()` | `from datetime import date, timedelta` | 535 |
| `chat_expert()` | `from plugins.aura_orchestrator.aura_orchestrator import orchestrate` | 597 |
| `chat_tts()` | `from aura_voice import TextToSpeech` | 619 |
| `chat_tts()` | `from pydub import AudioSegment` | 629 |
| `chat_tts()` | `import io` | 630 |
| `chat_tts()` | `import threading` | 639 |
| `init_web_server()` | `from plugins.aura_avatar.aura_avatar import AuraAvatar` | 750 |

---

## 2. ALL REQUEST/RESPONSE MODELS (Pydantic)

### Module-level models (lines 92–109)

#### `SkillCreateRequest` (line 92)
```python
class SkillCreateRequest(BaseModel):
    description: str
```
Used by: `POST /api/skills/create`

#### `SkillToggleRequest` (line 95)
```python
class SkillToggleRequest(BaseModel):
    skill_name: str
    enabled: bool
```
Used by: `POST /api/skills/{skill_name}/toggle`

#### `ConfigUpdateRequest` (line 99)
```python
class ConfigUpdateRequest(BaseModel):
    section: str
    key: str
    value: Any
```
Used by: `PUT /api/config`

#### `MessageRequest` (line 104)
```python
class MessageRequest(BaseModel):
    text: str
    user_id: str = "web_user"
```
Used by: `POST /api/chat`, `POST /api/chat/expert`

#### `RollbackRequest` (line 108)
```python
class RollbackRequest(BaseModel):
    backup_id: Optional[str] = None
```
Used by: `POST /api/backups/rollback`

### Inline / body models (not at module level)

#### `SkillCodeUpdate` (line 333)
```python
class SkillCodeUpdate(BaseModel):
    file: str   # "manifest.json", "SKILL.md", "skill.py"
    content: str
```
Used by: `PUT /api/skills/{skill_name}/code`

#### `TTSRequest` (line 607)
```python
class TTSRequest(BaseModel):
    text: str
```
Used by: `POST /api/chat/tts`

---

## 3. ALL MIDDLEWARE

### CORS Middleware (lines 53–60)
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```
- **Origin**: `*` (fully open)
- **Credentials**: `True`
- **Methods**: `*`
- **Headers**: `*`

There are **no other middleware** added.

---

## 4. STATIC FILE SERVING

### Line 63
```python
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
```
- Mounted at path `/static`
- Serves from directory `WEB_DIR / "static"` (i.e. `C:\aura_os\web\static\`)
- Name: `"static"`

---

## 5. TEMPLATE RENDERING

### Line 64
```python
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
```
- Template directory: `WEB_DIR / "templates"` (i.e. `C:\aura_os\web\templates\`)

Only used in the index endpoint:

### `GET /` (lines 166–183)
```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "app_name": "AURA OS",
            "version": "1.0.3",
            "port": PORT,
            "tailscale_ip": tailscale_ip,
            "tailscale_hostname": TAILSCALE_HOSTNAME,
            "local_url": f"http://localhost:{PORT}",
            "tailscale_url": f"http://{TAILSCALE_HOSTNAME}:{PORT}" if tailscale_ip else None,
        }
    )
```
- Template: `index.html`
- Context variables: `app_name`, `version`, `port`, `tailscale_ip`, `tailscale_hostname`, `local_url`, `tailscale_url`

---

## 6. CONFIGURATION DEPENDENCIES

### Path constants (lines 31–34)
| Constant | Value |
|----------|-------|
| `WEB_DIR` | `Path(__file__).parent` — `C:\aura_os\web\` |
| `ROOT_DIR` | `WEB_DIR.parent` — `C:\aura_os\` |
| `STATIC_DIR` | `WEB_DIR / "static"` — `C:\aura_os\web\static\` |
| `TEMPLATES_DIR` | `WEB_DIR / "templates"` — `C:\aura_os\web\templates\` |

### `config.json` (lines 37–44)
```python
with open(ROOT_DIR / "config.json", "r", encoding="utf-8") as f:
    APP_CONFIG = json.load(f)

WEB_CONFIG = APP_CONFIG.get("web_interface", {})
HOST = WEB_CONFIG.get("host", "0.0.0.0")
PORT = WEB_CONFIG.get("port", 8000)
TAILSCALE_ENABLED = WEB_CONFIG.get("tailscale", {}).get("enabled", True)
TAILSCALE_HOSTNAME = WEB_CONFIG.get("tailscale", {}).get("hostname", "aura-os")
```

| Variable | Config path | Default |
|----------|-------------|---------|
| `HOST` | `web_interface.host` | `"0.0.0.0"` |
| `PORT` | `web_interface.port` | `8000` |
| `TAILSCALE_ENABLED` | `web_interface.tailscale.enabled` | `True` |
| `TAILSCALE_HOSTNAME` | `web_interface.tailscale.hostname` | `"aura-os"` |

### Environment variables (via `dotenv`)

| Variable | Used at | Default | Context |
|----------|---------|---------|---------|
| `TTS_ENGINE` | line 621 | `"edge_tts"` | TTS engine selection |
| `TTS_VOICE` | line 622 | `"ru-RU-SvetlanaNeural"` | TTS voice |

### `AppState` (lines 70–86) — runtime dependency injection
```python
class AppState:
    aura_agent = None             # AuraAgent instance
    skill_manager = None          # SkillManager instance
    rollback_manager = None       # RollbackManager instance
    system_monitor = None         # SystemMonitor instance
    skill_builder = None          # SkillBuilder instance
    avatar = None                 # AuraAvatar plugin
    active_connections: List[WebSocket] = []
    logs: List[Dict] = []
    max_logs = 500
```
All set by `init_web_server()` (lines 740–757).

---

## 7. ALL FASTAPI ENDPOINTS

### Web Page

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 1 | `GET` | `/` | `index` (line 166) | `HTMLResponse` | `Request` (injected by FastAPI) |

### Dashboard / Status

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 2 | `GET` | `/api/status` | `get_status` (line 189) | `JSONResponse` (dict) | none |
| 3 | `GET` | `/api/dashboard/history` | `get_dashboard_history` (line 232) | `JSONResponse` (dict) | none |

### Logs

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 4 | `GET` | `/api/logs` | `get_logs` (line 254) | `JSONResponse` (dict) | `limit: int = 100`, `level: str = None` (query params) |
| 5 | `POST` | `/api/logs/clear` | `clear_logs` (line 272) | `JSONResponse` (dict) | none |

### Skills

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 6 | `GET` | `/api/skills` | `get_skills` (line 284) | `JSONResponse` (dict) | none |
| 7 | `GET` | `/api/skills/{skill_name}/code` | `get_skill_code` (line 312) | `JSONResponse` (dict) | `skill_name: str` (path param) |
| 8 | `PUT` | `/api/skills/{skill_name}/code` | `save_skill_code` (line 338) | `JSONResponse` (dict) | `skill_name: str` (path), `SkillCodeUpdate` (body) |
| 9 | `POST` | `/api/skills/create` | `create_skill` (line 365) | `JSONResponse` (dict) | `SkillCreateRequest` (body) |
| 10 | `POST` | `/api/skills/{skill_name}/toggle` | `toggle_skill` (line 383) | `JSONResponse` (dict) | `skill_name: str` (path), `SkillToggleRequest` (body) |
| 11 | `DELETE` | `/api/skills/{skill_name}` | `delete_skill` (line 407) | `JSONResponse` (dict) | `skill_name: str` (path param) |

### Config

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 12 | `GET` | `/api/config` | `get_config` (line 435) | `JSONResponse` (dict) | none |
| 13 | `PUT` | `/api/config` | `update_config` (line 451) | `JSONResponse` (dict) | `ConfigUpdateRequest` (body) |

### Backups

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 14 | `GET` | `/api/backups` | `get_backups` (line 479) | `JSONResponse` (dict) | none |
| 15 | `POST` | `/api/backups/create` | `create_backup` (line 487) | `JSONResponse` (dict) | none |
| 16 | `POST` | `/api/backups/rollback` | `rollback` (line 502) | `JSONResponse` (dict) | `RollbackRequest` (body) |

### Calendar

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 17 | `GET` | `/api/calendar` | `get_calendar` (line 521) | `JSONResponse` (dict) | `days: str = "7"` (query param, parsed to int, clamped 1–365) |
| 18 | `POST` | `/api/calendar/sync` | `sync_calendar` (line 550) | `JSONResponse` (dict) | none |

### Diagnostics

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 19 | `GET` | `/api/diagnose` | `diagnose` (line 566) | `JSONResponse` (dict) | none |

### Chat

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 20 | `POST` | `/api/chat` | `chat` (line 577) | `JSONResponse` (dict) | `MessageRequest` (body) |
| 21 | `POST` | `/api/chat/expert` | `chat_expert` (line 593) | `JSONResponse` (dict) | `MessageRequest` (body) |

### TTS

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 22 | `POST` | `/api/chat/tts` | `chat_tts` (line 611) | `Response` (audio/mpeg) | `TTSRequest` (body) |

### Avatar

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 23 | `POST` | `/api/avatar/stop` | `avatar_stop` (line 656) | `JSONResponse` (dict) | none |

### Timezones

| # | Method | Path | Handler | Response | Params |
|---|--------|------|---------|----------|--------|
| 24 | `GET` | `/api/timezones` | `get_timezones` (line 667) | `JSONResponse` (dict) | none |

### WebSocket

| # | Method | Path | Handler | Protocol |
|---|--------|------|---------|----------|
| 25 | `WS` | `/ws` | `websocket_endpoint` (line 698) | WebSocket |

**Total: 24 HTTP endpoints + 1 WebSocket endpoint**

---

## 8. CHAT FLOW — Detailed Trace

### 8.1 `POST /api/chat` (lines 577–590)

```
1. Client sends POST /api/chat with JSON body:
   { "text": "user message", "user_id": "web_user" }

2. FastAPI validates body → MessageRequest(text=str, user_id="web_user")

3. Guard: if state.aura_agent is None → HTTPException(400, "Агент не инициализирован")

4. add_log("info", f"Сообщение: {text[:100]}", "chat")
   └─ Appends to state.logs, truncates if >500

5. response = await state.aura_agent.process(request.text, request.user_id)
   └─ Delegates entire processing to AuraAgent.process(text, user_id)
      (imported from main module, injected via init_web_server())

6. Returns:
   {
     "text": <response_string>,
     "user_id": <user_id>
   }
```

### 8.2 WebSocket Chat (lines 720–730)

```
1. Client sends WebSocket JSON:
   { "type": "chat", "text": "...", "user_id": "web_user" }

2. Guard: if state.aura_agent → calls same process()

3. state.aura_agent.process(text, user_id) → response

4. Server sends:
   { "event": "chat_response", "data": { "text": "<response>" } }
```

### 8.3 Agent Integration Points

`state.aura_agent` is used in these endpoints:

| Endpoint | Access | Line | Purpose |
|----------|--------|------|---------|
| `/api/status` | `.db.get_upcoming_events(days=7)` | 206 | Calendar event count |
| `/api/status` | `.db.get_recent_summaries(30)` | 226 | Conversation count |
| `/api/status` | `.db.get_relevant_facts(50)` | 227 | Facts count |
| `/api/calendar` | `.db.get_events_for_date(...)` | 540 | Calendar event fetching |
| `/api/chat` | `.process(text, user_id)` | 585 | Core chat processing |
| `WS /ws` | `.process(text, user_id)` | 723 | WebSocket chat |
| `/api/calendar/sync` | `.google_sync` | 555 | Google Calendar sync |
| `/api/calendar/sync` | `.google_sync.full_sync()` | 559 | Full sync execution |
| `/api/diagnose` | `.get_self_diagnosis()` | 571 | Self-diagnosis report |

---

## 9. EXPERT MODE ENDPOINT — `/api/chat/expert`

### Path: `POST /api/chat/expert` (lines 593–604)

```python
@app.post("/api/chat/expert")
async def chat_expert(request: MessageRequest):
    try:
        from plugins.aura_orchestrator.aura_orchestrator import orchestrate
        add_log("info", f"Expert: {request.text[:100]}", "expert")
        result = await orchestrate(request.text)
        return {"text": result, "user_id": request.user_id, "mode": "expert"}
    except ImportError:
        raise HTTPException(500, "Orchestrator plugin not available. Install sentence-transformers.")
    except Exception as e:
        raise HTTPException(500, f"Orchestrator error: {e}")
```

### Flow
```
1. Client sends: { "text": "complex task", "user_id": "web_user" }

2. Lazy imports: plugins.aura_orchestrator.aura_orchestrator → orchestrate

3. add_log("info", text[:100], "expert")

4. result = await orchestrate(request.text)
   └─ Multi-agent orchestrator (DeepSeek-based) processes the request

5. Response: { "text": result, "user_id": "web_user", "mode": "expert" }
```

### Error cases
| Exception | HTTP Status | Message |
|-----------|-------------|---------|
| `ImportError` | 500 | "Orchestrator plugin not available. Install sentence-transformers." |
| Any other `Exception` | 500 | "Orchestrator error: {e}" |

### Key difference from `/api/chat`
- `/api/chat` → `state.aura_agent.process()` (single agent, standard path)
- `/api/chat/expert` → `orchestrate()` (multi-agent orchestration via DeepSeek)

---

## 10. TTS ENDPOINT — `/api/chat/tts`

### Path: `POST /api/chat/tts` (lines 611–653)

```python
class TTSRequest(BaseModel):
    text: str

@app.post("/api/chat/tts")
async def chat_tts(request: TTSRequest):
```

### Flow
```
1. Client sends: { "text": "text to speak" }

2. Fallback: if text is empty/whitespace → "Нет текста для озвучивания."

3. Lazy import: from aura_voice import TextToSpeech

4. Initialize TTS:
   - engine: os.getenv("TTS_ENGINE", "edge_tts")
   - voice:  os.getenv("TTS_VOICE", "ru-RU-SvetlanaNeural")
   - tts = TextToSpeech(engine=..., voice=...)

5. Synthesize:
   - audio_bytes = await tts.synthesize_to_bytes(text)

6. Duration calculation:
   a. Fallback: len(audio_bytes) / 16000  (16kHz assumption)
   b. Preferred: via pydub AudioSegment.from_file(BytesIO(audio_bytes), format="mp3")
      → audio_duration = len(seg) / 1000.0  (milliseconds → seconds)
      (wrapped in try/except, silently falls back on failure)

7. Avatar animation (if state.avatar is not None):
   - Launches a daemon thread calling state.avatar.speak(text, audio_duration)
   - Wrapped in try/except for both thread creation and execution

8. Returns:
   - Content: audio_bytes (raw MP3)
   - Media type: "audio/mpeg"
   - Header: Content-Disposition: inline; filename=aura_response.mp3
```

### Response type
- **Not** JSON — raw `Response` with `media_type="audio/mpeg"`
- Returns binary MP3 audio

### Error handling
```python
except Exception as e:
    raise HTTPException(500, f"TTS error: {e}")
```
General catch-all. Failures in pydub duration calculation and avatar thread are silently swallowed.

---

## 11. AVATAR ENDPOINT

### `POST /api/avatar/stop` (lines 656–664)

```python
@app.post("/api/avatar/stop")
async def avatar_stop():
    if state.avatar:
        try:
            state.avatar.stop()
        except Exception:
            pass
    return {"status": "ok"}
```

### Flow
```
1. Check if state.avatar exists
2. Call state.avatar.stop() (stops avatar animation)
3. Always returns {"status": "ok"}
```

### Avatar initialization (lines 749–755)
```python
try:
    from plugins.aura_avatar.aura_avatar import AuraAvatar
    state.avatar = AuraAvatar()
except Exception as e:
    print(f"[avatar] Avatar init skipped: {e}")
    state.avatar = None
```

### Avatar interactions
| Where | What | Line |
|-------|------|------|
| `init_web_server()` | Creates `AuraAvatar()` instance | 751 |
| `chat_tts()` | Calls `state.avatar.speak(text, duration)` in daemon thread | 641 |
| `avatar_stop()` | Calls `state.avatar.stop()` | 661 |

---

## 12. CALENDAR ENDPOINTS — Full Detail

### `GET /api/calendar` (lines 521–547)

```
Query param: days: str = "7"
  └─ Parsed to int, clamped to [1, 365], default 7

Guard: if state.aura_agent is None → return {"events": []}

Processing:
  1. Compute date range: today - 365 days → today + days
  2. For each date in range:
     - events = state.aura_agent.db.get_events_for_date(date.isoformat(), include_completed=True)
     - Extend results list
  3. Return:
     {
       "events": [...all events...],
       "total": len(events)
     }
```

### `POST /api/calendar/sync` (lines 550–563)

```
Guards:
  1. state.aura_agent is None → 400 "Агент не инициализирован"
  2. state.aura_agent.google_sync is None → 400 "Google Calendar не подключен..."

Processing:
  1. stats = await state.aura_agent.google_sync.full_sync()
  2. add_log("info", ..., "calendar")
  3. Return {"status": "ok", "stats": stats}

Errors:
  - 400: agent not init or google_sync None
  - 500: any sync exception, message includes str(e)
```

---

## 13. ALL ERROR HANDLING

### Pattern: `HTTPException`

All endpoints use `raise HTTPException(status_code, detail)`. No custom exception handlers registered.

| Endpoint | Status | Condition | Line |
|----------|--------|-----------|------|
| `/api/skills/{name}/code` GET | 404 | `skill_manager` None | 316 |
| `/api/skills/{name}/code` GET | 404 | skill not found | 319 |
| `/api/skills/{name}/code` PUT | 404 | `skill_manager` None | 342 |
| `/api/skills/{name}/code` PUT | 404 | skill not found | 345 |
| `/api/skills/{name}/code` PUT | 400 | invalid file name | 348 |
| `/api/skills/{name}/code` PUT | 400 | skill has no path | 352 |
| `/api/skills/{name}/code` PUT | 500 | file write error | 363 |
| `/api/skills/create` POST | 400 | `skill_builder` None | 369 |
| `/api/skills/{name}/toggle` POST | 400 | `skill_manager` None | 387 |
| `/api/skills/{name}/toggle` POST | 404 | skill dir not found | 399 |
| `/api/skills/{name}` DELETE | 400 | `skill_manager` None | 411 |
| `/api/skills/{name}` DELETE | 403 | builtin skill (forbidden) | 416 |
| `/api/config` PUT | 400 | nested key not found | 465 |
| `/api/backups/create` POST | 400 | `rollback_manager` None | 491 |
| `/api/backups/create` POST | 500 | backup creation failed | 500 |
| `/api/backups/rollback` POST | 400 | `rollback_manager` None | 506 |
| `/api/backups/rollback` POST | 500 | rollback failed | 515 |
| `/api/calendar/sync` POST | 400 | agent not init | 554 |
| `/api/calendar/sync` POST | 400 | google_sync None | 556 |
| `/api/calendar/sync` POST | 500 | sync exception | 563 |
| `/api/diagnose` GET | 400 | agent not init | 570 |
| `/api/chat` POST | 400 | agent not init | 581 |
| `/api/chat/expert` POST | 500 | ImportError (orchestrator) | 602 |
| `/api/chat/expert` POST | 500 | any orchestrator error | 604 |
| `/api/chat/tts` POST | 500 | any TTS error | 653 |

### Pattern: Graceful degradation (returns empty/default)

| Endpoint | Condition | Fallback | Line |
|----------|-----------|----------|------|
| `/api/status` | `skill_manager` None | `skill_stats = {}` | 195 |
| `/api/status` | `system_monitor` None | `health = {}` | 199 |
| `/api/status` | db access error | `calendar_count = 0` | 207–209 |
| `/api/status` | agent None → memory | `0` connections/facts | 226–227 |
| `/api/skills` | `skill_manager` None | `{"skills": {}, "stats": {}}` | 288 |
| `/api/backups` | `rollback_manager` None | `{"backups": []}` | 483 |
| `/api/calendar` | agent None | `{"events": []}` | 532 |

### Pattern: Silent try/except

| Location | What | Line |
|----------|------|------|
| `get_tailscale_ip()` | `subprocess.run` failure | 124–125 |
| `get_tailscale_status()` | `subprocess.run` failure | 137–138 |
| `broadcast()` | individual connection send failure | 159–160 |
| `chat_tts()` | pydub duration calculation failure | 633–634 |
| `chat_tts()` | avatar thread start/run failure | 644–645 |
| `avatar_stop()` | `state.avatar.stop()` failure | 662–663 |
| `init_web_server()` | `AuraAvatar` import/init failure | 753–755 |

---

## 14. HELPER FUNCTIONS

### `get_tailscale_ip()` (lines 115–126)
```python
def get_tailscale_ip() -> Optional[str]:
    result = subprocess.run(["tailscale", "ip", "-4"], ...)
    if result.returncode == 0:
        return result.stdout.strip()
    return None
```
Queries tailscale for the node's IPv4 address. Returns `None` on any failure.

### `get_tailscale_status()` (lines 128–139)
```python
def get_tailscale_status() -> dict:
    result = subprocess.run(["tailscale", "status", "--json"], ...)
    if result.returncode == 0:
        return json.loads(result.stdout)
    return {"error": "Tailscale не установлен или не настроен"}
```
Returns parsed JSON status or error dict. **Note: this function is defined but never called in this file.**

### `add_log()` (lines 141–152)
```python
def add_log(level: str, message: str, source: str = "web"):
    log_entry = {"timestamp": datetime.now().isoformat(), "level": level, "message": message, "source": source}
    state.logs.append(log_entry)
    if len(state.logs) > state.max_logs:
        state.logs = state.logs[-state.max_logs:]
```
Appends to in-memory log buffer. Truncates to 500 entries, keeping latest.

### `broadcast()` (lines 154–160)
```python
async def broadcast(event: str, data: dict):
    for connection in state.active_connections:
        try:
            await connection.send_json({"event": event, "data": data})
        except:
            pass
```
Sends JSON event to all active WebSocket connections. Silently skips failed connections.

### `init_web_server()` (lines 740–757)
```python
def init_web_server(aura_agent, skill_manager, rollback_manager, system_monitor, skill_builder):
    state.aura_agent = aura_agent
    state.skill_manager = skill_manager
    state.rollback_manager = rollback_manager
    state.system_monitor = system_monitor
    state.skill_builder = skill_builder
    # + avatar init
```
Dependency injection entry point. Called from main.py before `start_web_server()`.

### `start_web_server()` (lines 759–779)
```python
def start_web_server(host=None, port=None):
    h = host or HOST
    p = port or PORT
    # prints URLs
    uvicorn.run(app, host=h, port=p, log_level="info")
```
Launches uvicorn with the configured host/port.

---

## 15. WEBSOCKET — `/ws` (lines 698–734)

### Protocol
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.active_connections.append(websocket)
    # ...
```

### Message handling loop
| Client → Server `type` | Server → Client `event` | Data |
|------------------------|------------------------|------|
| `"ping"` | `"pong"` | `{}` |
| `"chat"` | `"chat_response"` | `{"text": "<agent response>"}` |

### Lifecycle
```
1. accept() → append to active_connections → log "WebSocket подключен"
2. Send initial: { "event": "connected", "data": {"message": "WebSocket подключен"} }
3. Loop: receive_json() → handle by type
4. WebSocketDisconnect → remove from active_connections → log "WebSocket отключен"
```

### WebSocket is NOT used for streaming
- Standard `/api/chat` and `/api/chat/expert` are HTTP POST (request/response).
- WebSocket only used for real-time push notifications (broadcast) and optional WS-based chat (same `aura_agent.process()` call).
- No streaming token-by-token — responses are fully assembled before sending.

---

## 16. DATA FLOW SUMMARY

```
main.py
  │
  ├─ init_web_server(agent, skill_mgr, rollback, monitor, builder)
  │   └─ Sets state.* dependencies + initializes AuraAvatar
  │
  ├─ start_web_server()
  │   └─ uvicorn.run(app)
  │
  └─ At runtime:
      Client HTTP requests ──► FastAPI routes ──► state.aura_agent / state.skill_manager / etc.
                                                    │
                                    ┌───────────────┴───────────────┐
                                    ▼                               ▼
                            Synchronous returns              WebSocket broadcast
                            (JSON/dict/Response)             (state.active_connections)
```

---

## 17. UNUSED IMPORTS

These FastAPI response classes are imported but never used in this file:
- `JSONResponse` (line 17) — endpoints return plain dicts, FastAPI auto-converts
- `FileResponse` (line 17) — never referenced

`JSONResponse` from `fastapi.responses` is imported on line 17 but no endpoint returns it explicitly; FastAPI auto-serializes dict returns to JSON via `jsonable_encoder` internally.

---

*Generated from `C:\aura_os\web\server.py` (784 lines, Python 3, FastAPI).*
