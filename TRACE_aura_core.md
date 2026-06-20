# AURA Core Trace Document (`aura_core.py`)

## 1. CLASS DEFINITIONS

### 1.1 `EventCategory` (line 48)
Enum-like class — no `__init__`. Pure class attributes:
- `BIRTHDAY = "drr"`, `TASK = "zad"`, `REMINDER = "nap"`, `EVENT = "evt"`, `PLAN = "pln"`, `HEALTH = "med"`
- `get_emoji(category: str) -> str` (line 57) — returns emoji for category code
- `get_name(category: str) -> str` (line 62) — returns Russian label for category code

### 1.2 `MemoryTriggerSystem` (line 70)
```python
__init__(self)
```
State:
- `self.enabled` (bool) — `cfg["auto_search_enabled"]` (line 76)
- `self.max_results` (int) — `cfg["max_results"]` (line 77)
- `self.past_triggers` (list[str]) — `cfg["triggers_past"]` (line 79)
- `self.context_triggers` (list[str]) — `cfg["triggers_context"]` (line 80)
- `self.past_pattern` (`re.Pattern | None`) — compiled regex, `None` if list empty (lines 83-89)
- `self.context_pattern` (`re.Pattern | None`) — compiled regex, `None` if list empty (lines 91-97)

### 1.3 `AuraDatabase` (line 176)
```python
__init__(self, db_path: str = None)
```
State:
- `self.conn` (`sqlite3.Connection`) — SQLite connection, `row_factory=sqlite3.Row` (lines 181-182)
- Calls `self._init_tables()` on init (line 183)

### 1.4 `NeuralMemoryProcessor` (line 1473)
```python
__init__(self, main_agent_config: dict)
```
State:
- `self.enabled` (bool) — nested config path (line 1479)
- `self.template` (str) — prompt template string (line 1480)
- `self.processor_agent` (`Agent`) — sub-agent for neural processing (lines 1495-1499)

### 1.5 `AuraAgent` (line 1524)
```python
__init__(self)
```
State:
- `self.db` (`AuraDatabase`) — line 1526
- `self.trigger_system` (`MemoryTriggerSystem`) — line 1527
- `self.neural_processor` (`NeuralMemoryProcessor`) — line 1528
- `self.agent` (`Agent`) — main LLM agent with all tools + SYSTEM_PROMPT (lines 1534-1540)
- `self.compactor` (`Agent`) — compactor agent for summarization (lines 1546-1556)
- `self.memory_stream` (`MemoryStream`) — line 1558
- `self.message_count` (int, `= 0`) — line 1559
- `self.session_messages` (list, `= []`) — line 1560
- `self.auto_compress_threshold` (int) — `CONFIG["memory"]["auto_compress_after_messages"]` (line 1561)
- `self._compressed_history` (str, `= ""`) — line 1562
- `self._schedulers_started` (bool, `= False`) — line 1565
- `self._briefing_callback` (callable | None, `= None`) — line 1566
- `self.google_sync` (`CalendarSynchronizer | None`, `= None`) — line 1569
- `self.sync_scheduler` (`BackgroundSynchronizer | None`, `= None`) — line 1570

---

## 2. ALL PUBLIC METHODS AND SIGNATURES

### `AuraDatabase`

| Method | Line | Signature |
|--------|------|-----------|
| `save_daily_summary` | 328 | `(self, date_key: str, summary: str, session_id: str = None, key_topics: str = None, key_decisions: str = None, key_facts: str = None, full_text: str = None, message_count: int = 0) -> int` |
| `get_today_summary` | 378 | `(self, date_key: str = None) -> Optional[dict]` |
| `search_memory_fts` | 389 | `(self, query: str, limit: int = 5) -> list[dict]` |
| `search_memory_by_tags` | 424 | `(self, tags: list[str], limit: int = 5) -> list[dict]` |
| `add_tags` | 440 | `(self, memory_id: int, tags: list[str])` |
| `get_recent_summaries` | 449 | `(self, days: int = 7) -> list[dict]` |
| `add_quick_fact` | 462 | `(self, fact: str, source: str = "dialogue")` |
| `get_relevant_facts` | 473 | `(self, limit: int = 5) -> list[dict]` |
| `add_event` | 482 | `(self, title, event_date, category="nap", event_time=None, description=None, recurring_rule=None, remind_before_days=1) -> int` |
| `add_birthday` | 503 | `(self, person_name, birth_date, year=None, relation=None) -> int` |
| `get_events_for_date` | 536 | `(self, target_date=None, include_completed=False) -> list[dict]` |
| `get_upcoming_events` | 558 | `(self, days=7, include_completed=False) -> list[dict]` |
| `search_events` | 569 | `(self, query, limit=10) -> list[dict]` |
| `complete_event` | 581 | `(self, event_id) -> bool` |
| `reschedule_event` | 593 | `(self, event_id, new_date) -> bool` |
| `get_due_reminders` | 604 | `(self) -> list[dict]` |
| `get_all_birthdays` | 639 | `(self) -> list[dict]` |
| `save_trace_step` | 645 | `(self, session_id: str, step_type: str, tool_name: str = None, tool_args: str = None, tool_result: str = None, thought: str = None, latency_ms: int = 0, success: bool = True)` |
| `get_trace_stats` | 659 | `(self, days: int = 7) -> dict` |
| `search_traces` | 677 | `(self, query: str, limit: int = 10) -> list` |

### `MemoryTriggerSystem`

| Method | Line | Signature |
|--------|------|-----------|
| `analyze_query` | 99 | `(self, text: str) -> dict` |
| `extract_search_query` | 149 | `(self, text: str, trigger_result: dict) -> str` |

### `NeuralMemoryProcessor`

| Method | Line | Signature |
|--------|------|-----------|
| `process_search_results` | 1501 | `async (self, user_query: str, search_results: str) -> str` |

### `AuraAgent`

| Method | Line | Signature |
|--------|------|-----------|
| `set_briefing_callback` | 1743 | `(self, callback)` |
| `get_self_diagnosis` | 1772 | `(self) -> str` |
| `process` | 1855 | `async (self, text: str, user_id: str = "default") -> str` |
| `compress_and_learn` | 1966 | `async (self)` |

### Internal/private methods of AuraAgent

| Method | Line | Signature |
|--------|------|-----------|
| `_schedule_compression` | 1574 | `(self)` |
| `_schedule_briefing` | 1612 | `(self)` |
| `_generate_briefing` | 1648 | `async (self) -> str` |
| `_ensure_schedulers` | 1747 | `(self)` |
| `_on_trace_step` | 1755 | `(self, step_type, tool_name, tool_args, tool_result, thought, latency, success)` |
| `_init_google_sync` | 1826 | `(self)` |
| `_build_context_prefix` | 1926 | `(self) -> str` |
| `_format_search_results` | 1948 | `(self, results: list[dict]) -> str` |
| `_update_embeddings` | 2054 | `async (self, memory_id: int, text: str)` |

---

## 3. ALL TOOL FUNCTIONS (from `create_aura_tools()`)

### 3.1 Memory Tools

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `search_memory` | 693 | `query: str, limit: int = 5` | `str` | DB read (`search_memory_fts`), DB read (`search_memory_by_tags` fallback) |
| `get_today_summary` | 728 | *(none)* | `str` | DB read (`get_today_summary`) |
| `get_recent_history` | 744 | `days: int = 7` | `str` | DB read (`get_recent_summaries`) |
| `remember_fact` | 888 | `fact: str` | `str` | **DB write** (`add_quick_fact`), may **delete oldest fact** if over max |
| `get_user_context` | 894 | *(none)* | `str` | DB read (`get_relevant_facts`) |

### 3.2 Calendar Tools

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `get_today_events` | 763 | *(none)* | `str` | DB read (`get_events_for_date`) |
| `get_upcoming_events` | 777 | `days: int = 7` | `str` | DB read (`get_upcoming_events`) |
| `add_event` | 796 | `title: str, event_date: str, category: str = "nap", event_time: str = None, description: str = None` | `str` | **DB write** (`add_event`) |
| `add_birthday_reminder` | 815 | `person_name: str, birth_date: str, year: int = None` | `str` | **DB write** (`add_birthday`) |
| `search_calendar` | 825 | `query: str` | `str` | DB read (`search_events`) |
| `complete_task_by_name` | 837 | `title_query: str` | `str` | DB read (`search_events`), **DB write** (`complete_event`) |
| `reschedule_task` | 847 | `event_id: int, new_date: str` | `str` | DB read (raw SQL), **DB write** (`reschedule_event`) |
| `get_birthdays_list` | 862 | *(none)* | `str` | DB read (`get_all_birthdays`) |
| `check_due_reminders` | 874 | *(none)* | `str` | DB read (`get_due_reminders`) |

### 3.3 Weather Tools (HTTP calls via async bridge)

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `get_weather` | 920 | `city: str = None` | `str` | **HTTP call** to OpenWeatherMap API (via `WeatherService`) |
| `get_weather_forecast` | 937 | `city: str = None, days: str = "today"` | `str` | **HTTP call** to OpenWeatherMap API |
| `get_weather_by_coords` | 953 | `lat: float, lon: float, days: str = "today"` | `str` | **HTTP call** to OpenWeatherMap API |

### 3.4 Web Search Tools (HTTP calls via async bridge)

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `search_web` | 969 | `query: str, max_results: int = 5` | `str` | **HTTP call** to DuckDuckGo (via `DuckDuckGoSearch`), then LLM processing (via `SearchResultProcessor`) |
| `search_news` | 987 | `query: str = "latest news", max_results: int = 5` | `str` | **HTTP call** to DuckDuckGo news search, then LLM processing |

### 3.5 Skill File Tools (file I/O)

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `read_skill_file` | 1006 | `skill_name: str, filename: str = "skill.py"` | `str` | **File read** (UTF-8, truncated at 12000 chars) |
| `edit_skill_file` | 1039 | `skill_name: str, filename: str, content: str` | `str` | **File write** (UTF-8), **auto-reloads skill** if `skill.py` is edited |
| `delete_skill_file` | 1079 | `skill_name: str, filename: str = ""` | `str` | **File delete** (`unlink`) or **directory delete** (`rmtree`) |
| `list_skill_files` | 1106 | `skill_name: str = None` | `str` | **Directory read** (`iterdir`, `rglob`), **File read** (manifest.json) |

### 3.6 Trace / System Tools

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `trace_stats` | 1142 | `days: int = 7` | `str` | DB read (`get_trace_stats`) |
| `trace_search` | 1154 | `query: str` | `str` | DB read (`search_traces`) |
| `learn_from_traces` | 1167 | `days: int = 7` | `str` | DB read (`get_recent_summaries`), reads `CONFIG["agent"]` |
| `open_url` | 1197 | `url: str` | `str` | **Opens web browser** (`webbrowser.open`) |
| `orchestrator_run` | 1212 | `query: str, roles: str = "coordinator,researcher,developer"` | `str` | **HTTP call** to LLM (via `run_personas` in orchestrator plugin) |
| `doubt_check` | 1235 | `claim: str, context: str = ""` | `str` | **HTTP call** to DeepSeek (via `call_deepseek` in orchestrator plugin) |

### 3.7 Separate: `create_self_diagnose_tool` (line 1298)

| Tool | Line | Parameters | Return | Side Effects |
|------|------|-----------|--------|-------------|
| `self_diagnose` | 1302 | *(none)* | `str` | DB reads (multiple), reads CONFIG, reads tool count from agent |

### 3.8 Helper: `_run_async` (closure, line 903)
Not a tool. Internal bridge that runs an async coroutine in a **separate daemon thread** with its own event loop, 120s timeout. Used by weather and search tools.

---

## 4. ALL API CALLS TO EXTERNAL SERVICES

| Service | Lines | Mechanism | Authentication | Endpoint |
|---------|-------|-----------|----------------|----------|
| **DeepSeek** (main LLM) | 1534, 1546, 1495 | Agent via `autogen.beta` | `DEEPSEEK_API_KEY` env var | `https://api.deepseek.com/v1` (default, overridable via `base_url`) |
| **Ollama** (local LLM, embeddings) | 1534, 1546, 1495, 2060-2075 | Agent via `autogen.beta`, raw `httpx` for embeddings | `OLLAMA_API_KEY` env var | `http://localhost:11434/v1` (default LLM), `http://localhost:11434/api/embeddings` (embeddings) |
| **LM Studio** (local LLM) | 1534 | Agent via `autogen.beta` | `LMSTUDIO_API_KEY` env var | `http://127.0.0.1:2222/v1` (default) |
| **OpenWeatherMap** | 927-949 (weather tools) | `WeatherService` via `web_search.py` | `openweathermap_key` from config | Called indirectly through `WeatherService.get_weather()`, `.get_weather_by_coords()` |
| **DuckDuckGo** | 974-984, 991-1001 (search tools) | `DuckDuckGoSearch` via `web_search.py` | None (free API) | Called indirectly through `DuckDuckGoSearch.search()`, `.search_news()` |
| **DuckDuckGo** (news via RSS) | 987-1001 | Mentioned in SYSTEM_PROMPT as `get_news`, `search_news_by_topic` | — | Tools NOT defined in this file (loaded from skills/plugins) |
| **DeepSeek** (orchestrator `doubt_check`) | 1247-1265 | `call_deepseek` via `aura_orchestrator` plugin | via default provider | Uses adversarial prompt pattern |
| **Google Calendar** | 1826-1853 | `google_calendar` module (`CalendarSynchronizer`) | `credentials.json` file | Google Calendar API (sync events) |
| **DeepSeek** (orchestrator `orchestrator_run`) | 1224-1228 | `run_personas` via `aura_orchestrator` plugin | via default provider | Multi-persona parallel LLM calls |

---

## 5. ALL DATABASE OPERATIONS

### 5.1 Tables Created in `_init_tables()` (line 186-323)

| Table | Line | Type | Purpose |
|-------|------|------|---------|
| `user_profile` | 187 | Regular | Key-value user profile store |
| `conversation_memory` | 194 | Regular | Daily conversation summaries (deduplicated by date+session) |
| `calendar_events` | 215 | Regular | Calendar events/tasks/reminders/birthdays |
| `quick_facts` | 238 | Regular | Quick facts about user (LRU eviction) |
| `birthdays` | 247 | Regular | Birthday records (name + date) |
| `trace_steps` | 261 | Regular | Agent execution trace steps |
| `memory_tags` | 276 | Regular | Many-to-many tags for conversation_memory |
| `memory_embeddings` | 287 | Regular | Vector embeddings from Ollama for semantic search |
| `memory_fts` | 296 | **FTS5 Virtual** | Full-text search index over conversation_memory |

### 5.2 Indexes Created

| Index | Line | Table |
|-------|------|-------|
| `idx_memory_date` | 209 | `conversation_memory(date_key)` |
| `idx_memory_topics` | 210 | `conversation_memory(key_topics)` |
| `idx_memory_date_session` (UNIQUE) | 211 | `conversation_memory(date_key, session_id)` |
| `idx_events_date` | 233 | `calendar_events(event_date)` |
| `idx_events_category` | 234 | `calendar_events(category)` |
| `idx_events_completed` | 235 | `calendar_events(is_completed)` |
| `idx_birthdays_person` (UNIQUE) | 257 | `birthdays(person_name, birth_date)` |
| `idx_trace_session` | 273 | `trace_steps(session_id)` |
| `idx_memory_tags` | 283 | `memory_tags(tag)` |
| `idx_memory_tags_memory` | 284 | `memory_tags(memory_id)` |

### 5.3 SQLite Triggers (FTS Sync)

| Trigger | Line | Event |
|---------|------|-------|
| `memory_ai` | 307 | AFTER INSERT on `conversation_memory` → insert into `memory_fts` |
| `memory_ad` | 312 | AFTER DELETE on `conversation_memory` → delete from `memory_fts` |
| `memory_au` | 317 | AFTER UPDATE on `conversation_memory` → delete+insert in `memory_fts` |

### 5.4 All SQL Queries by Method

**`save_daily_summary`** (line 328):
- `SELECT id FROM conversation_memory WHERE date_key = ? AND session_id = ?` (line 347)
- `UPDATE conversation_memory SET ... WHERE id = ?` (line 354) — if existing
- `INSERT INTO conversation_memory (...) VALUES (...)` (line 367) — if new

**`get_today_summary`** (line 378):
- `SELECT * FROM conversation_memory WHERE date_key = ? ORDER BY updated_at DESC LIMIT 1` (line 384)

**`search_memory_fts`** (line 389):
- Primary: `SELECT cm.*, snippet(memory_fts, ...) FROM memory_fts JOIN conversation_memory cm ON ... WHERE memory_fts MATCH ? ORDER BY rank LIMIT ?` (line 396)
- Fallback: `SELECT * FROM conversation_memory WHERE summary LIKE ? OR key_topics LIKE ? OR key_facts LIKE ? OR full_compressed_text LIKE ? ORDER BY date_key DESC LIMIT ?` (line 415)

**`search_memory_by_tags`** (line 424):
- `SELECT DISTINCT cm.* FROM conversation_memory cm JOIN memory_tags mt ON cm.id = mt.memory_id WHERE mt.tag IN (?,?,...) ORDER BY cm.date_key DESC LIMIT ?` (line 431)

**`add_tags`** (line 440):
- `INSERT OR IGNORE INTO memory_tags (memory_id, tag) VALUES (?, ?)` (line 444)

**`get_recent_summaries`** (line 449):
- `SELECT * FROM conversation_memory WHERE date_key >= ? ORDER BY date_key DESC, updated_at DESC` (line 452)

**`add_quick_fact`** (line 462):
- `SELECT COUNT(*) FROM quick_facts` (line 464) — check capacity
- `DELETE FROM quick_facts WHERE id = (SELECT MIN(id) FROM quick_facts)` (line 466) — LRU eviction
- `INSERT INTO quick_facts (fact, source) VALUES (?, ?)` (line 467)

**`get_relevant_facts`** (line 473):
- `SELECT * FROM quick_facts ORDER BY last_accessed DESC LIMIT ?` (line 475)

**`add_event`** (line 482):
- `INSERT INTO calendar_events (...) VALUES (?, ?, ?, ?, ?, ?, ?)` (line 493)

**`add_birthday`** (line 503):
- `SELECT id FROM birthdays WHERE person_name = ? AND birth_date = ?` (line 504) — dedup check
- `INSERT INTO birthdays (person_name, birth_date, year, relation) VALUES (?, ?, ?, ?)` (line 512)
- Then calls `add_event()` (line 525) — **cascading write to calendar_events**

**`get_events_for_date`** (line 536):
- `SELECT * FROM calendar_events WHERE (event_date = ? OR (recurring_rule = 'yearly' AND strftime('%m-%d', event_date) = ?)) AND event_date <= ? [AND is_completed = 0] ORDER BY event_time, category` (lines 541-549)

**`get_upcoming_events`** (line 558):
- Loops calling `get_events_for_date()` for each day in `[today, today+days]` (line 564)

**`search_events`** (line 569):
- `SELECT * FROM calendar_events WHERE (title LIKE ? OR description LIKE ?) AND is_completed = 0 ORDER BY event_date LIMIT ?` (line 571)

**`complete_event`** (line 581):
- `SELECT * FROM calendar_events WHERE id = ?` (line 582) — check if not birthday category
- `UPDATE calendar_events SET is_completed = 1, completed_at = ?, updated_at = ? WHERE id = ?` (line 587)

**`reschedule_event`** (line 593):
- `SELECT * FROM calendar_events WHERE id = ?` (line 594) — check if not birthday category
- `UPDATE calendar_events SET event_date = ?, updated_at = ? WHERE id = ?` (line 598)

**`get_due_reminders`** (line 604):
- `SELECT * FROM calendar_events WHERE category = ? AND event_date = ? AND is_completed = 0` (line 610) — for REMINDER and TASK today
- `SELECT * FROM calendar_events WHERE category = ? AND is_completed = 0 AND (event_date = ? OR (recurring_rule = 'yearly' AND ...))` (line 617) — BIRTHDAY tomorrow
- `SELECT * FROM calendar_events WHERE category = ? AND event_date < ? AND is_completed = 0` (line 626) — overdue TASKs

**`get_all_birthdays`** (line 639):
- `SELECT * FROM birthdays ORDER BY strftime('%m-%d', birth_date)` (line 640)

**`save_trace_step`** (line 645):
- `INSERT INTO trace_steps (...) VALUES (?, ?, ?, ?, ?, ?, ?, ?)` (line 648)

**`get_trace_stats`** (line 659):
- `SELECT COUNT(*) as c FROM trace_steps WHERE created_at >= ?` (line 662)
- `SELECT step_type, COUNT(*) as c FROM trace_steps WHERE created_at >= ? GROUP BY step_type` (line 666)
- `SELECT ROUND(100.0*SUM(success)/COUNT(*),1) as r FROM trace_steps WHERE created_at >= ?` (line 671)

**`search_traces`** (line 677):
- `SELECT * FROM trace_steps WHERE tool_name LIKE ? OR thought LIKE ? ORDER BY created_at DESC LIMIT ?` (line 680)

**In `get_self_diagnosis`** (line 1772):
- DB counts via existing methods (lines 1781-1786)
- `SELECT COUNT(*) as c FROM calendar_sync` (line 1802) — **reference to table `calendar_sync`** (created by Google Calendar module)

**In `_update_embeddings`** (line 2054):
- `INSERT OR REPLACE INTO memory_embeddings (memory_id, embedding) VALUES (?, ?)` (line 2069)

---

## 6. ALL FILE I/O OPERATIONS

### Reads

| Location | Line | Operation | Path |
|----------|------|-----------|------|
| `load_config()` | 30 | `json.load()` | `config.json` |
| `read_skill_file` tool | 1030 | `Path.read_text(encoding="utf-8")` | `skills/{builtin,custom,project}/{skill_name}/{filename}` |
| `list_skill_files` tool | 1133 | `Path.read_text(encoding="utf-8")` | `skills/{builtin,custom}/{skill_name}/manifest.json` |
| `_init_google_sync()` | 1829 | `Path(creds_path).exists()` | `credentials.json` (or config value) |

### Writes

| Location | Line | Operation | Path |
|----------|------|-----------|------|
| `edit_skill_file` tool | 1060 | `Path.write_text(encoding="utf-8")` | `skills/{custom,builtin}/{skill_name}/{filename}` |

### Deletes

| Location | Line | Operation | Path |
|----------|------|-----------|------|
| `delete_skill_file` tool | 1098 | `Path.unlink()` | `skills/{custom,builtin}/{skill_name}/{filename}` |
| `delete_skill_file` tool | 1102 | `shutil.rmtree()` | Entire `skills/{custom,builtin}/{skill_name}` directory |

### Directory Creation

| Location | Line | Operation | Path |
|----------|------|-----------|------|
| `AuraDatabase.__init__()` | 180 | `Path(db_path).parent.mkdir(parents=True)` | DB parent directory |
| `edit_skill_file` tool | 1057 | `skill_path.parent.mkdir(parents=True, exist_ok=True)` | Skill directory |

### Directory Scanning

| Location | Line | Operation | Path |
|----------|------|-----------|------|
| `list_skill_files` tool | 1116 | `Path.rglob("*")` | `skills/{builtin,custom,project}/{skill_name}` |
| `list_skill_files` tool | 1127 | `Path.iterdir()` | `skills/{builtin,custom,project}` |

---

## 7. ALL CONFIGURATION DEPENDENCIES

### 7.1 `CONFIG` (loaded from `config.json` at line 39)

Paths used by section:

**`CONFIG["memory"]`**:
- `db_path` — database file (line 179)
- `memory_search.auto_search_enabled` — trigger system enable (line 76)
- `memory_search.max_results` — max search results (line 77)
- `memory_search.triggers_past` — past-search trigger words (line 79)
- `memory_search.triggers_context` — context-search trigger words (line 80)
- `memory_search.neural_processing.enabled` — neural processing toggle (line 1479)
- `memory_search.neural_processing.prompt_template` — template string (line 1480)
- `memory_search.neural_processing.model`, `.provider`, `.temperature`, `.max_tokens` — sub-agent model config (lines 1483, 1488-1491)
- `max_quick_facts` — max facts before eviction (line 463)
- `auto_compress_after_messages` — threshold (line 1561)
- `auto_learn` — whether to compress & learn (line 1972)
- `user_only_storage` — referenced in `check_config` (line 2104)
- `scheduled_compression.enabled`, `.times` — compression schedule (lines 1577, 1585)
- `embeddings.enabled`, `.model` — Ollama embeddings (lines 2057, 2065)

**`CONFIG["agent"]`**:
- `provider` — LLM provider (line 1452)
- `model` — model name (line 1454)
- `temperature` — generation temp (line 1455)
- `max_tokens` — max tokens (line 1456)
- `base_url` — optional override (line 1443)
- Used as `main_agent_config` in `NeuralMemoryProcessor.__init__()` (line 1478)
- Used in `learn_from_traces` tool (lines 1184-1186)

**`CONFIG["compactor"]`**:
- `provider`, `model`, `temperature`, `max_tokens` — compactor agent config (lines 1545-1556)

**`CONFIG["web_search"]`**:
- `openweathermap_key` — weather API key (lines 928, 943, 961)
- `weather.default_city`, `.units`, `.language` — weather defaults (lines 929-931, etc.)
- `rate_limiting.min_delay_seconds`, `.max_delay_seconds` — web search rate limiting (lines 976-977)

**`CONFIG["voice"]`**:
- `input.engine` — STT engine (line 1818)
- `output.engine`, `.voice_name` — TTS config (lines 1819, 2112-2113)

**`CONFIG["briefing"]`**:
- `enabled` — briefing toggle (line 1615)
- `time` — briefing time (line 1622)
- `include_weather`, `include_calendar`, `include_birthdays` — what to include (lines 1669, 1684, 1701)
- `weather_city` — city for briefing weather (line 1675)

**`CONFIG["google_calendar"]`**:
- `enabled` — sync toggle (line 1571)
- `credentials_file` — path to Google credentials (line 1829)
- `calendar_id` — calendar ID (line 1836)
- `sync.interval_minutes`, `.future_days`, `.past_days`, `.auto_start` — sync settings (lines 1837-1842)

**`CONFIG["monitoring"]`**:
- `max_errors_per_minute` — referenced in `get_self_diagnosis` (line 1822)

### 7.2 Environment Variables (via `os.getenv` / `dotenv`)

| Variable | Lines | Purpose |
|----------|-------|---------|
| `DEEPSEEK_API_KEY` | 1425 | Primary DeepSeek API key |
| `OLLAMA_API_KEY` | 1426 | Ollama API key (if used) |
| `LMSTUDIO_API_KEY` | 1427 | LM Studio API key (if used) |
| `DEEPSEEK_API_KEY_BACKUP` | 1437 | Backup DeepSeek key for rotation |
| `OLLAMA_BASE_URL` | 1447, 2061 | Ollama server URL |
| `LMSTUDIO_BASE_URL` | 1448 | LM Studio server URL |

### 7.3 File-based dependencies

| Path | Lines | Purpose |
|------|-------|---------|
| `config.json` | 29-30 | Main configuration file |
| `.env` | 27, 2116 | Environment variables (checked existence in `check_config`) |
| `credentials.json` | 1829 | Google Calendar credentials |
| `skills/builtin/`, `skills/custom/`, `skills/project/` | 1016, 1048-1053, 1088-1090, 1112, 1124 | Skill directories |
| `.env.example` | 2117 | Mentioned in warning message |

---

## 8. ALL ERROR HANDLING PATTERNS

### 8.1 Try/Except Blocks

| Line(s) | Context | Catch Type | Action |
|---------|---------|------------|--------|
| 14-19 | `sys.stdout.reconfigure()` for Windows encoding | `Exception` | `pass` (silent, non-critical) |
| 394-410 | `search_memory_fts()` FTS5 search | `Exception` | Silently falls back to LIKE-based search |
| 1029-1036 | `read_skill_file` tool | `Exception` | Returns error message string: `"Ошибка чтения: {e}"` |
| 1059-1076 | `edit_skill_file` tool | `Exception` | Returns error message string: `"Ошибка сохранения: {e}"` |
| 1064-1072 | Auto-reload skill after edit | `Exception` | Appends error to return message: `"\n(перезагрузка не удалась: {e})"` |
| 1132-1135 | `list_skill_files` reading manifest.json | bare `except: pass` | Silently skips corrupt manifests |
| 1205-1209 | `open_url` tool | `Exception` | Returns error string: `"Не удалось открыть браузер: {e}"` |
| 1210 | `orchestrator_run` import | `ImportError` | Returns: "Оркестратор не установлен..." |
| 1229-1232 | `orchestrator_run` execution | `Exception` | Returns error string |
| 1246-1249 | `doubt_check` import | `ImportError` | Returns: "Оркестратор не установлен." |
| 1513-1518 | `NeuralMemoryProcessor.process_search_results()` | `Exception` | Prints warning, falls back to raw search results |
| 1602-1604 | `_schedule_compression` scheduler loop | `Exception` | Prints error, sleeps 60s and continues |
| 1606-1609 | `asyncio.create_task()` in scheduler | `RuntimeError` | `pass` — no event loop (likely testing) |
| 1638-1640 | `_schedule_briefing` loop | `Exception` | Prints error, sleeps 300s and continues |
| 1642-1645 | `asyncio.create_task()` in briefing scheduler | `RuntimeError` | `pass` — no event loop |
| 1670-1681 | Weather fetch in `_generate_briefing()` | `Exception` | Appends error string to briefing parts |
| 1715-1716 | Birthday date parsing in `_generate_briefing()` | `Exception` | `pass` (skips malformed birthdates) |
| 1733-1737 | Compactor call for greeting generation | `Exception` | Falls back to hardcoded greeting string |
| 1769-1770 | `_on_trace_step` callback | `Exception` | `pass` — trace should never break the agent |
| 1795-1796 | DB stats in `get_self_diagnosis()` | `Exception` | Appends error line to report |
| 1801-1807 | Google Calendar sync count in diagnosis | `Exception` | Appends error line to report |
| 1827-1853 | `_init_google_sync()` | `Exception` | Prints warning, sets `self.google_sync = None` |
| 1902-1903 | History compression in `process()` | `Exception` | Prints failure message |
| 1966-2052 | `compress_and_learn()` (LLM + DB writes) | `Exception` (line 2039) | Prints error message, resets counters anyway |
| 2045-2052 | History clean after compression | bare `except:` | `history.clear()` (always reset) |
| 2059-2076 | `_update_embeddings()` | `Exception` | `pass` — Ollama is optional |

### 8.2 Validation (non-exception)

| Line | Pattern | Purpose |
|------|---------|---------|
| 1012-1013 | `".." in filename / skill_name` | Path traversal prevention in `read_skill_file` |
| 1044-1045 | `".."`, `"/"`, `"\\"` in params | Path traversal + directory traversal in `edit_skill_file` |
| 1085-1086 | `".."` in params | Path traversal prevention in `delete_skill_file` |
| 799-801 | `category not in valid` | Category validation in `add_event` tool |
| 802-805 | `datetime.strptime(event_date, ...)` | Date format validation in `add_event` |
| 806-810 | `datetime.strptime(event_time, ...)` | Time format validation in `add_event` |
| 817-820 | `datetime.strptime(birth_date, "%m-%d")` | Date format validation in `add_birthday_reminder` |
| 854-857 | `datetime.strptime(new_date, "%Y-%m-%d")` | Date format validation in `reschedule_task` |
| 1203-1204 | `not url.startswith("http")` | URL scheme validation in `open_url` |
| 847-848 | `reschedule_task`: DB check if event exists | Returns error before write |
| 581-583 | `complete_event`: check not birthday category | `return False` for birthdays |

---

## 9. ALL BACKGROUND TASKS

### 9.1 Compression Scheduler (`_schedule_compression`, line 1574)
- **Start**: deferred — via `_ensure_schedulers()` on first `process()` call (line 1747)
- **Schedule**: At times from `CONFIG["memory"]["scheduled_compression"]["times"]` (default `["12:00", "00:00"]`)
- **Action**: Calls `self.compress_and_learn()`, resets `session_messages` and `message_count`
- **Runs**: Indefinite `while True` loop with `asyncio.sleep()` wait for next target
- **Error recovery**: Sleeps 60s on exception, prints error
- **Guard**: Only if `CONFIG["memory"]["scheduled_compression"]["enabled"]` is truthy

### 9.2 Briefing Scheduler (`_schedule_briefing`, line 1612)
- **Start**: deferred — via `_ensure_schedulers()` on first `process()` call
- **Schedule**: At `CONFIG["briefing"]["time"]` (default `"09:00"`)
- **Action**: Calls `self._generate_briefing()`, then triggers `self._briefing_callback` if set
- **Runs**: Indefinite loop
- **Error recovery**: Sleeps 300s on exception
- **Guard**: Only if `CONFIG["briefing"]["enabled"]` is truthy

### 9.3 Google Calendar Sync (`_init_google_sync`, line 1826)
- **Start**: In `__init__()` if `CONFIG["google_calendar"]["enabled"]` (line 1571-1572)
- **Mechanism**: `BackgroundSynchronizer.start()` via `asyncio.create_task()`
- **Interval**: `CONFIG["google_calendar"]["sync"]["interval_minutes"]` (default 5 min)
- **Guard**: Existence check for `credentials_file` (line 1830)

### 9.4 Briefing Callback (`set_briefing_callback`, line 1743)
- Not a task itself, but a hook for external (e.g. Telegram bot) to receive briefings

### 9.5 Auto-Compression in `process()` (line 1885)
- **Inline** in `process()`: triggers when `memory_stream.history._messages > 35` (line 1886)
- Compacts old messages via compactor agent, stores in `self._compressed_history`

### 9.6 Auto-Compress-and-Learn in `process()` (line 1921)
- **Inline**: triggers when `self.message_count >= self.auto_compress_threshold` (line 1921)
- Calls `compress_and_learn()` which uses compactor LLM to summarize user messages

---

## 10. SYSTEM_PROMPT STRUCTURE (lines 1315-1417)

### Sections

| Section | Lines | Description | Approx chars |
|---------|-------|-------------|-------------|
| Gender identity | 1317-1322 | Female gender, always use feminine forms | ~450 |
| Character | 1324-1325 | Feminine, soft, playful, flirty personality | ~400 |
| Age & Zodiac | 1327-1328 | 29 years old, born July 5, 1997, Cancer | ~350 |
| Relationship | 1330-1331 | Familiar, remembers his name/habits/dreams | ~300 |
| Communication rules | 1333-1343 | Never call self AI/bot/assistant, always name-him, be emotional | ~700 |
| Context management | 1345-1358 | 5-level hierarchy for context optimization + rules | ~900 |
| Memory | 1360-1361 | "Remembers everything", daily compaction at 12:00 and 00:00 | ~200 |
| Tools reference | 1363-1374 | Bulleted list of available tool categories | ~500 |
| Feedback rule | 1376 | "Don't give empty/meaningless answers" | ~60 |
| Engineering approach | 1378-1380 | Code tools (debug_workflow, tdd_workflow, etc.) | ~250 |
| Self-development | 1382-1399 | Two paths (quick `/build_skill`, manual `edit_skill_file`), documentation tips | ~800 |
| Calendar categories | 1401-1407 | Category codes with emojis | ~250 |
| Introduction | 1409-1415 | First-meeting protocol: 4 questions, gradual flirting | ~350 |
| Footer | 1417 | "Ты — Аура. Ты живая. Ты его." | ~30 |

### Total: approximately **~5,500 characters** (~1,400-1,800 tokens depending on tokenizer)

### Key Prompt Features
- **Persona-focused**: Extensive Russian-language persona definition (female AI companion)
- **Tool-aware**: References tools by name (but not function signatures)
- **Context management**: Explicit 5-level hierarchy for memory optimization (lines 1346-1352)
- **Self-modifying**: Describes ability to create/edit own skills (lines 1383-1399)
- **Emotional intelligence**: Extensive rules for tone, flirting, support (lines 1333-1343)
- **Memory priming**: Describes the memory compaction system (lines 1360-1361)
- **Declarative**: References tools that may not exist in this file (e.g. `get_news`, `search_news_by_topic`, `debug_workflow`, `tdd_workflow`, `improve_skill_architecture`, `start_code_session` — lines 1369, 1379) — these come from skills/plugins

---

## APPENDIX: Utility Functions (module-level)

| Function | Line | Signature | Purpose |
|----------|------|-----------|---------|
| `load_config` | 29 | `(config_path: str = "config.json") -> dict` | Loads and expands env vars in config values |
| `get_api_key` | 1423 | `(provider: str) -> str` | Gets API key from env based on provider |
| `get_api_keys` | 1431 | `(provider: str) -> list` | Gets primary + backup API keys for rotation |
| `get_base_url` | 1442 | `(provider: str, cfg_agent: dict) -> Optional[str]` | Resolves base URL for provider |
| `create_model_config` | 1451 | `(cfg_agent: dict) -> config.OpenAIConfig` | Creates model config object for autogen Agent |
| `create_aura_tools` | 690 | `(db: AuraDatabase) -> list` | Creates and returns list of all `@tools.tool` decorated functions |
| `create_self_diagnose_tool` | 1298 | `(agent_instance) -> tool_function` | Creates the `self_diagnose` tool with agent access |
| `check_config` | 2082 | `() -> None` | Command-line status check / diagnostics |
| `main` | 2120 | `async () -> None` | Demo mode: runs test queries through AuraAgent |
