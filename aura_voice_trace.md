# `aura_voice.py` — Detailed Trace Document

**File:** `C:\aura_os\aura_voice.py` (871 lines)
**Purpose:** Voice module for AURA OS — Telegram voice reception, speech recognition (STT), speech synthesis (TTS), response format auto-detection, and temp-file cleanup.

---

## 1. ALL Class Definitions with `__init__` Parameters

### 1.1 `ResponseMode(Enum)` — line 28
```python
class ResponseMode(Enum):
```
| Member  | Value      | Description                          |
|---------|------------|--------------------------------------|
| `VOICE` | `"voice"`  | Answer by voice (default)            |
| `TEXT`  | `"text"`   | Answer by text                       |
| `AUTO`  | `"auto"`   | Auto-determine from request content  |

### 1.2 `InputMode(Enum)` — line 35
```python
class InputMode(Enum):
```
| Member  | Value      |
|---------|------------|
| `VOICE` | `"voice"`  |
| `TEXT`  | `"text"`   |

### 1.3 `SpeechToText` — line 73
```python
def __init__(self, engine: str = "vosk"):
```
| Parameter | Type   | Default  | Description                     |
|-----------|--------|----------|---------------------------------|
| `engine`  | `str`  | `"vosk"` | STT backend: `"vosk"`, `"google"`, `"whisper_api"` |

Side effects in `__init__`:
- `engine="vosk"` → calls `_init_vosk()` (line 82)
- `engine="google"` → calls `_init_google()` (line 84)
- `engine="whisper_api"` → **no init** (API key checked at call time, line 180)

### 1.4 `TextToSpeech` — line 237
```python
def __init__(self, engine: str = "edge_tts", voice: str = "ru-RU-SvetlanaNeural"):
```
| Parameter | Type   | Default                     | Description              |
|-----------|--------|-----------------------------|--------------------------|
| `engine`  | `str`  | `"edge_tts"`                | TTS backend              |
| `voice`   | `str`  | `"ru-RU-SvetlanaNeural"`    | Voice/model identifier   |

Valid `engine` values: `"openai_tts"`, `"pyttsx3"`, `"edge_tts"`, `"kokoro"` (stub), `"piper"`, `"silero"`.

Side effect: if `engine="pyttsx3"`, calls `_init_pyttsx3()` (line 248).

### 1.5 `ResponseFormatDetector` — line 582
```python
def __init__(self):
```
No parameters. Builds `self.text_triggers` and `self.voice_triggers` sets from the module-level lists `TEXT_REQUEST_TRIGGERS` (line 44) and `VOICE_REQUEST_TRIGGERS` (line 64).

### 1.6 `VoiceMessageHandler` — line 629
```python
def __init__(
    self,
    stt_engine: str = "whisper_api",
    tts_engine: str = "openai_tts",
    tts_voice: str = "nova"
):
```
| Parameter      | Type   | Default          | Description                    |
|----------------|--------|------------------|--------------------------------|
| `stt_engine`   | `str`  | `"whisper_api"`  | Passed to `SpeechToText()`     |
| `tts_engine`   | `str`  | `"openai_tts"`   | Passed to `TextToSpeech()`     |
| `tts_voice`    | `str`  | `"nova"`         | Passed to `TextToSpeech()`     |

Creates three sub-objects:
- `self.stt = SpeechToText(engine=stt_engine)` (line 641)
- `self.tts = TextToSpeech(engine=tts_engine, voice=tts_voice)` (line 642)
- `self.format_detector = ResponseFormatDetector()` (line 643)

### 1.7 `ConsoleVoiceMode` — line 776
```python
def __init__(self, aura_agent):
```
| Parameter     | Type          | Description                          |
|---------------|---------------|--------------------------------------|
| `aura_agent`  | `AuraAgent`   | External agent for text processing   |

Also creates `self.format_detector = ResponseFormatDetector()` and `self.current_mode = InputMode.TEXT` (lines 781–782).

---

## 2. ALL Public Methods with Signatures

### `SpeechToText` (line 73)
| Method                                          | Line | Async | Returns | Description                                      |
|-------------------------------------------------|------|-------|---------|--------------------------------------------------|
| `transcribe_file(file_path: str) -> str`         | 117  | Yes   | `str`   | Routes to engine-specific transcription           |
| `transcribe_bytes(audio_bytes: bytes, format: str = "ogg") -> str` | 146 | Yes | `str` | Writes bytes to temp file, converts if needed, transcribes, cleans up |

### `TextToSpeech` (line 237)
| Method                                                      | Line | Async | Returns | Description                                              |
|-------------------------------------------------------------|------|-------|---------|----------------------------------------------------------|
| `_clean_for_tts(text: str) -> str` (static)                 | 281  | No    | `str`   | Strips markdown/emoji/code for clean speech (see §6)     |
| `synthesize_to_file(text: str, output_path: str = None) -> str` | 340 | Yes | `str`   | Routes to engine-specific synthesis, returns file path   |
| `synthesize_to_bytes(text: str) -> bytes`                   | 361  | Yes   | `bytes` | Calls `synthesize_to_file`, reads bytes, schedules delayed cleanup |

### `ResponseFormatDetector` (line 582)
| Method                                                          | Line | Async | Returns         | Description                                   |
|-----------------------------------------------------------------|------|-------|-----------------|-----------------------------------------------|
| `detect(user_text: str, current_mode: InputMode) -> ResponseMode` | 598  | No    | `ResponseMode`  | Determines response format (see §11 logic)    |

### `VoiceMessageHandler` (line 629)
| Method                                                                                       | Line | Async | Returns | Description                                                      |
|----------------------------------------------------------------------------------------------|------|-------|---------|------------------------------------------------------------------|
| `handle_voice_message(bot, message, aura_agent, user_id: str)`                                | 645  | Yes   | `None`  | Full pipeline: download→STT→process→format→synthesize→send→clean  |
| `handle_text_message(bot, message, aura_agent, user_id: str)`                                 | 732  | Yes   | `None`  | Text message with optional voice reply                            |

### `ConsoleVoiceMode` (line 776)
| Method      | Line | Async | Returns | Description                                    |
|-------------|------|-------|---------|------------------------------------------------|
| `run()`     | 784  | Yes   | `None`  | Interactive console loop with `!voice`/`!text`/`!quit` commands |

### Module-level
| Function               | Line | Async | Description                                       |
|------------------------|------|-------|---------------------------------------------------|
| `test_voice_flow()`    | 838  | Yes   | Tests synthesis + format detection with hardcoded cases |

---

## 3. ALL TTS Engines and Their Synthesis Methods

### 3.1 Engine: `"openai_tts"` — `_synthesize_openai` (line 384)
```
async def _synthesize_openai(self, text: str, output_path: str = None) -> str
```
- **API:** OpenAI Audio API (`tts-1` model)
- **Voices:** `nova`, `shimmer`, `alloy` (female; set via `self.voice`)
- **Format:** MP3 (streamed directly from API)
- **Speed:** hardcoded `1.0` (line 398)
- **Requires:** `OPENAI_API_KEY` env var (checked line 389)
- **Dependency:** `openai` (imported inline, line 386)
- **Temp file:** `NamedTemporaryFile(suffix=".mp3", delete=False)` (line 403) when `output_path` is None
- **Output:** Writes via `response.stream_to_file(output_path)` (line 406)

### 3.2 Engine: `"pyttsx3"` — `_synthesize_pyttsx3` (line 409)
```
async def _synthesize_pyttsx3(self, text: str, output_path: str = None) -> str
```
- **Backend:** Local offline `pyttsx3` (SAPI5 on Windows)
- **Voice:** Auto-detected Russian female voice (lines 258–272), falls back to system default
- **Rate:** Configurable via `TTS_RATE` env var (default `"160"`, line 274)
- **Volume:** Hardcoded `0.9` (line 275)
- **Init:** `_init_pyttsx3()` (line 250) called from `__init__`
- **Pipeline:** pyttsx3 saves WAV → `pydub` converts to MP3 (lines 421–434)
- **Two temp files:** intermediate `.wav` + final `.mp3`; WAV deleted immediately in `finally` (line 432–433)
- **Dependencies:** `pyttsx3`, `pydub`; ImportError caught at init (line 277) and sets `self.tts_engine = None`
- **Error:** Raises `RuntimeError` if `self.tts_engine` is None (line 412)

### 3.3 Engine: `"edge_tts"` — `_synthesize_edge` (line 437)
```
async def _synthesize_edge(self, text: str, output_path: str = None) -> str
```
- **Service:** Microsoft Edge TTS (free, online)
- **Voice:** Default `"ru-RU-SvetlanaNeural"` (line 443); configurable via `self.voice`
- **Format:** MP3
- **Chunking:** Splits text at sentence boundaries when > 2500 chars (line 450–468)
  - Regex split: `re.split(r'(?<=[.!?])\s+', text)` (line 458)
  - Each chunk synthesized separately, concatenated with `pydub.AudioSegment` (line 474–487)
- **Timeouts:** `connect_timeout=40`, `receive_timeout=480` (line 452)
- **Temp chunks:** Each chunk uses `NamedTemporaryFile`, deleted in `finally` after concatenation (line 484–485)
- **Dependency:** `edge_tts` (import in try-block, line 441; raises `ImportError` on failure, line 490–491)
- **Concatenation:** Uses `pydub` for MP3 merging (line 472, 481–482, 487)

### 3.4 Engine: `"piper"` — `_synthesize_piper` (line 493)
```
async def _synthesize_piper(self, text: str, output_path: str = None) -> str
```
- **Backend:** Piper TTS (local, fast offline)
- **Model:** `PIPER_MODEL_PATH` env var (default `"models/piper/ru_RU-irina-medium.onnx"`, line 501)
- **Config:** Auto-derived from model path by replacing `.onnx` → `.json` (line 502)
- **Lazy loading:** Model loaded once into `self._piper_voice` via `PiperVoice.load()` (line 505)
- **Format:** Piper writes WAV via `wave.open()` → `pydub` converts to MP3 (lines 521–529)
- **Settings:** `SynthesisConfig(length_scale=0.952)` for ~5% faster; volume scaled from `TTS_RATE` env var (lines 517–520)
- **Interim WAV:** Written alongside output, deleted after MP3 conversion (line 528–529)
- **WAV path logic:** `output_path.replace(".mp3", ".wav")` — fallback appends `.wav` if path doesn't contain `.mp3` (lines 512–514)
- **Dependencies:** `piper` (PiperVoice, SynthesisConfig), `wave`, `pydub`

### 3.5 Engine: `"silero"` — `_synthesize_silero` (line 533)
```
async def _synthesize_silero(self, text: str, output_path: str = None) -> str
```
- **Backend:** Silero TTS v5 (local, PyTorch, ~100x realtime)
- **Model:** Loaded via `torch.hub.load('snakers4/silero-models', 'silero_tts', language='ru', speaker='v4_ru')` (lines 544–550)
- **Lazy loading:** Stored in `self._silero_model` (line 543–544)
- **Speaker:** `"baya"` default; also `"kseniya"`, `"xenia"` (line 541)
- **Sample rate:** 48000 Hz (line 552)
- **Features:** `put_accent=True`, `put_yo=True` (lines 557–558)
- **Format:** WAV via `scipy.io.wavfile.write()` → `pydub` converts to MP3 (lines 568–574)
- **Interim WAV:** Deleted after conversion (line 573–574)
- **Dependencies:** `torch`, `scipy`, `pydub`

### 3.6 Engine: `"kokoro"` — `_synthesize_kokoro` — **NOT IMPLEMENTED**
- Referenced at line 352–353 in `synthesize_to_file()` dispatch
- No `_synthesize_kokoro` method exists in the file
- Calling this engine will raise `AttributeError` at runtime

---

## 4. Engine Priority / Fallback Chain

**There is NO automatic fallback chain.** The engine is selected once at instantiation and is fixed for the lifetime of the object.

- `TextToSpeech.__init__` default: `engine="edge_tts"` (line 243)
  - Comment at line 240 says: *"Основной: Edge TTS ... Запасные: pyttsx3, OpenAI TTS"* — but this is documentation only, not implemented.
- `VoiceMessageHandler.__init__` default: `tts_engine="openai_tts"` (line 638)
- `SpeechToText.__init__` default: `engine="vosk"` (line 78)
- The `synthesize_to_file()` method (line 340) is a simple if/elif dispatch — no try/except fallback logic.
- To implement fallback, caller must catch exceptions and re-instantiate `TextToSpeech` with a different engine.

---

## 5. File I/O Operations — Temp Files, WAV Conversion, Cleanup

### 5.1 Temp file creation patterns

| Location                    | Line | Pattern                                          | Suffix  | Context                        |
|-----------------------------|------|--------------------------------------------------|---------|--------------------------------|
| `transcribe_bytes`          | 148  | `NamedTemporaryFile(suffix=f".{format}", delete=False)` | `.ogg` etc. | STT input buffer       |
| `_synthesize_openai`        | 403  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | OpenAI TTS output              |
| `_synthesize_pyttsx3`       | 415  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | pyttsx3 final output           |
| `_synthesize_pyttsx3`       | 421  | `NamedTemporaryFile(suffix=".wav", delete=False)` | `.wav`  | pyttsx3 intermediate WAV       |
| `_synthesize_edge`          | 446  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | Edge TTS output                |
| `_synthesize_edge` (chunk)  | 476  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | Edge chunk temp                |
| `_synthesize_piper`         | 508  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | Piper final output             |
| `_synthesize_silero`        | 562  | `NamedTemporaryFile(suffix=".mp3", delete=False)` | `.mp3`  | Silero final output            |
| `handle_voice_message`      | 668  | `NamedTemporaryFile(suffix=".ogg", delete=False)` | `.ogg`  | Telegram voice download        |

All temp files use `delete=False` (manual cleanup).

### 5.2 WAV conversion paths

| Method                     | Line | Source Format | Target     | Tool      |
|----------------------------|------|---------------|------------|-----------|
| `_convert_to_wav`          | 164  | OGG/Opus/MP3  | 16kHz mono 16-bit WAV | `pydub.AudioSegment` |
| `_synthesize_pyttsx3`      | 425  | pyttsx3 WAV   | MP3        | `pydub`   |
| `_synthesize_piper`        | 521  | Piper WAV     | MP3        | `pydub`   |
| `_synthesize_silero`       | 568  | Silero WAV    | MP3        | `pydub`   |
| `_synthesize_edge` (chunks)| 481  | chunk MP3     | MP3 (merged) | `pydub` |

`_convert_to_wav` (line 164–177):
- Uses `pydub.AudioSegment.from_file()`
- Resamples to 16000 Hz, mono, 16-bit (`set_sample_width(2)`)
- Output: `{original}_converted.wav`
- Deletes original file after conversion (line 172)

### 5.3 Cleanup strategies

| Strategy              | Location                          | Description                                      |
|-----------------------|-----------------------------------|--------------------------------------------------|
| **Immediate**         | `transcribe_bytes` finally (161)  | Deletes temp STT input after transcription       |
| **Immediate**         | `_synthesize_pyttsx3` finally (432) | Deletes intermediate WAV after MP3 conversion  |
| **Immediate**         | `_synthesize_piper` (528)         | Deletes intermediate WAV after MP3 conversion    |
| **Immediate**         | `_synthesize_silero` (573)        | Deletes intermediate WAV after MP3 conversion    |
| **Immediate**         | `_synthesize_edge` chunk finally (484) | Deletes each chunk temp after merge       |
| **Immediate**         | `handle_voice_message` finally (728) | Deletes downloaded `.ogg` after full pipeline |
| **Delayed (3 min)**   | `synthesize_to_bytes` (371–382)   | Daemon thread waits 180s then deletes TTS output |
| **Delayed (3 min)**   | `_convert_to_wav` (172)           | Deletes original format file after WAV conversion |

---

## 6. `_clean_for_tts` / `_clean_audio_text` Filtering Logic

**Method:** `TextToSpeech._clean_for_tts(text: str) -> str` — line 281–338 (static method)

Called automatically inside `synthesize_to_file()` at line 345 before any engine is invoked.

### Processing steps (in order):

| Step | Line(s)  | Operation                                          | Regex / Logic                                      |
|------|----------|----------------------------------------------------|----------------------------------------------------|
| 1    | 286      | Strip triple bold `***...***`                       | `r'\*\*\*(.+?)\*\*\*'` → `\1`                     |
| 2    | 287      | Strip double bold `**...**`                         | `r'\*\*(.+?)\*\*'` → `\1`                         |
| 3    | 288      | Strip single italic `*...*`                         | `r'\*(.+?)\*'` → `\1`                             |
| 4    | 289      | Strip double underscore `__...__`                   | `r'__(.+?)__'` → `\1`                             |
| 5    | 290      | Strip strikethrough `~~...~~`                       | `r'~~(.+?)~~'` → `\1`                             |
| 6    | 292      | Strip inline code `` `...` ``                         | `r'`(.+?)`'` → `\1`                              |
| 7    | 294      | Convert `[text](url)` → `text`                     | `r'\[(.+?)\]\(.+?\)'` → `\1`                     |
| 8    | 296      | Strip `#`…`######` headers                         | `r'^#{1,6}\s+'` → `''` (MULTILINE)               |
| 9    | 298      | Strip horizontal rules `---`, `***`, `___`         | `r'^[-*_]{3,}\s*$'` → `''` (MULTILINE)           |
| 10   | 300      | Strip Unicode emoji (ranges: U+1F300–U+1F9FF, U+2600–U+27BF, U+2B50, U+2700–U+27BF, variation selectors, ZWJ, combos, surrogates) | Single complex regex |
| 11   | 302      | Strip ASCII emoticons `:)`, `;-)`, `:D`, `:P`, etc. | `r'\s?[:;][\-]?[()DPpd/\dOo]'` → `''`           |
| 12   | 304      | Strip HTML tags                                     | `r'<[^>]+>'` → `''`                              |
| 13   | 306      | Collapse 3+ newlines to 2                           | `r'\n{3,}'` → `'\n\n'`                           |
| 14   | 309      | Remove code blocks `` ```...``` ``                    | `r'```[\s\S]*?```'` → `''`                       |
| 15   | 312–323 | **Remove non-Russian lines:** Keep only lines containing Cyrillic (`[а-яёА-ЯЁ]`) OR lines without Latin chars that contain punctuation `[.!?]` | Per-line filter |
| 16   | 326      | Remove URLs                                         | `r'https?://\S+'` → `''`                         |
| 17   | 329      | Remove lines matching code/command patterns         | `r'^[a-zA-Z0-9_\-\.\/\\\:\s]+\$?\s*$'` → `''`  |
| 18   | 332      | Remove standalone Latin words (2+ chars)            | `r'\b[a-zA-Z]{2,}\b'` → `''`                    |
| 19   | 335      | Collapse 3+ newlines to 2 (again)                   | `r'\n{3,}'` → `'\n\n'`                           |
| 20   | 336      | Collapse multiple spaces to one                     | `r' +'` → `' '`                                 |
| 21   | 338      | `.strip()` final result                             | Remove leading/trailing whitespace                |

---

## 7. Delayed Cleanup Timing and Threading

**Location:** `TextToSpeech.synthesize_to_bytes()` — lines 369–382

```python
if temp_path and os.path.exists(temp_path):
    def _delayed_cleanup():
        import time
        time.sleep(180)                    # 3 minutes
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(...)
        except Exception:
            pass
    import threading
    threading.Thread(target=_delayed_cleanup, daemon=True).start()
```

| Property        | Value                                  |
|-----------------|----------------------------------------|
| Delay           | 180 seconds (3 minutes)               |
| Mechanism       | `threading.Thread(daemon=True)`        |
| Reason          | "даём аудио доиграть" (let audio finish playing in Telegram before deleting) |
| Error handling  | All exceptions silently swallowed (`except Exception: pass`) |
| Scope           | Only for `synthesize_to_bytes()`; `synthesize_to_file()` does **no** delayed cleanup |
| Daemon thread   | Yes — will not block process exit      |

The daemon thread captures `temp_path` via closure. There is no cancellation mechanism; if the user requests many TTS outputs rapidly, multiple daemon threads will accumulate (each sleeping 3 minutes).

---

## 8. Speech Recognition (STT) Methods

### 8.1 `_transcribe_google` — line 129
```
async def _transcribe_google(self, file_path: str) -> str
```
- **Library:** `speech_recognition` (aliased `sr`)
- **Model:** Google Speech Recognition (free tier, no API key)
- **Language:** `"ru-RU"` hardcoded (line 139)
- **Requires:** `speech_recognition` imported inline (line 131)
- **Init:** `_init_google()` (line 86) creates `sr.Recognizer()` and stores in `self.recognizer`
- **Audio source:** `sr.AudioFile(file_path)` (line 137)
- **Error handling:**
  - `sr.UnknownValueError` → returns empty string `""` (line 141–142)
  - `sr.RequestError` → raises `RuntimeError` (line 143–144)
  - `self.recognizer` is None → raises `RuntimeError` (line 132–133)

### 8.2 `_transcribe_whisper_api` — line 179
```
async def _transcribe_whisper_api(self, file_path: str) -> str
```
- **API:** OpenAI Whisper API (`whisper-1` model)
- **Language:** `"ru"` (line 193)
- **Response format:** `"text"` (line 194)
- **Auth:** `OPENAI_API_KEY` env var → raises `ValueError` if missing (line 184–185)
- **Client:** `openai.AsyncOpenAI(api_key=api_key)` created per call (line 187)
- **Returns:** `.strip()` of transcript (line 197)
- **File:** opened in binary read mode `"rb"` (line 189)
- **No error handling** for network/API errors beyond what the OpenAI SDK raises

### 8.3 `_transcribe_vosk` — line 199
```
async def _transcribe_vosk(self, file_path: str) -> str
```
- **Backend:** Vosk (local offline)
- **Init:** `_init_vosk()` (line 95) loads model from `VOSK_MODEL_PATH` env var (default `"models/vosk-model-small-ru-0.22"`)
- **Sample rate:** 16000 Hz (hardcoded)
- **Validation (lines 210–212):** Raises `ValueError` if WAV is not 1-channel, 16-bit, 16000 Hz
- **Recognition loop (lines 218–224):** Reads 4000-frame chunks, calls `AcceptWaveform()`, collects `Result()` → `"text"` field
- **Final result (lines 227–228):** Calls `FinalResult()` for trailing audio
- **Output:** All text fragments joined with space, stripped (line 231)
- **Model not loaded:** Raises `RuntimeError` (line 204–205)
- **Requires:** `vosk`, `wave`, `json`

### 8.4 `transcribe_bytes` — line 146 (dispatch + conversion)
```
async def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str
```
- Writes bytes to `NamedTemporaryFile(suffix=f".{format}")` (line 148)
- If format is `"ogg"`, `"opus"`, or `"mp3"` AND engine is `"vosk"` → calls `_convert_to_wav()` (line 154–155)
- Then calls `transcribe_file()` (line 157)
- Temp file deleted in `finally` (line 161–162)

### 8.5 `transcribe_file` — line 117 (router)
```
async def transcribe_file(self, file_path: str) -> str
```
| engine value        | dispatches to               | line |
|---------------------|-----------------------------|------|
| `"whisper_api"`     | `_transcribe_whisper_api`   | 121  |
| `"vosk"`            | `_transcribe_vosk`          | 123  |
| `"google"`          | `_transcribe_google`        | 125  |
| anything else       | raises `ValueError`         | 127  |

---

## 9. ALL Error Handling

### 9.1 Import errors (soft-fail, prints warning)
| Location                 | Line | Library                | Behavior                                      |
|--------------------------|------|------------------------|-----------------------------------------------|
| `_init_google`           | 91   | `speech_recognition`   | Prints install hint, sets `recognizer = None` |
| `_init_vosk`             | 113  | `vosk`                 | Prints install hint, sets `vosk_model = None` |
| `_init_pyttsx3`          | 277  | `pyttsx3`              | Prints install hint, sets `tts_engine = None` |

### 9.2 Import errors (hard-fail, raises)
| Location                 | Line | Library      | Raises                         |
|--------------------------|------|--------------|--------------------------------|
| `_synthesize_edge`       | 490  | `edge_tts`   | `ImportError` with message     |
| `_synthesize_piper`      | 498  | `piper`/`wave` | `ImportError` with message  |
| `_synthesize_silero`     | 538  | `torch`/`scipy` | `ImportError` with message |

### 9.3 `ValueError`
| Location                 | Line | Condition                                       |
|--------------------------|------|-------------------------------------------------|
| `transcribe_file`        | 127  | Unknown STT engine                               |
| `_transcribe_whisper_api`| 184  | `OPENAI_API_KEY` not set                          |
| `_transcribe_vosk`       | 212  | WAV format mismatch (not 1ch/16bit/16kHz)        |
| `synthesize_to_file`     | 359  | Unknown TTS engine                               |
| `_synthesize_openai`     | 390  | `OPENAI_API_KEY` not set                          |

### 9.4 `RuntimeError`
| Location                 | Line | Condition                                           |
|--------------------------|------|-----------------------------------------------------|
| `_transcribe_google`     | 133  | `self.recognizer` is None                           |
| `_transcribe_google`     | 144  | `sr.RequestError` from Google API                   |
| `_convert_to_wav`        | 175  | `pydub` not installed                               |
| `_convert_to_wav`        | 177  | Audio conversion failure (wraps any `Exception`)     |
| `_transcribe_vosk`       | 205  | `self.vosk_model` is None                           |
| `_synthesize_pyttsx3`    | 412  | `self.tts_engine` is None                           |

### 9.5 Silently handled exceptions
| Location                      | Line | What is suppressed                    |
|-------------------------------|------|---------------------------------------|
| `synthesize_to_bytes` cleanup | 379  | `except Exception: pass` — deletion failure ignored |
| `ConsoleVoiceMode.run`        | 831  | `except Exception as e` — prints `⚠️ Ошибка: {e}` and continues loop |

### 9.6 `UnknownValueError` (non-exceptional)
| Location              | Line | Behavior                        |
|-----------------------|------|---------------------------------|
| `_transcribe_google`  | 141  | Returns empty string `""`      |

### 9.7 Early return (non-exceptional)
| Location                  | Line | Condition                                      |
|---------------------------|------|------------------------------------------------|
| `handle_voice_message`    | 682  | Recognized text too short or empty — sends "не разобрала" reply and returns |
| `_init_vosk`              | 103  | Model path doesn't exist — prints warning, sets `vosk_model = None`, returns |

### 9.8 Missing method (would be `AttributeError` at runtime)
| Location              | Line | Issue                                      |
|-----------------------|------|--------------------------------------------|
| `_synthesize_kokoro`  | 352  | Referenced in dispatch but not implemented |

---

## 10. Voice Message Handling (`VoiceMessageHandler`)

**Class:** `VoiceMessageHandler` — line 629

### 10.1 `handle_voice_message` — line 645
```
async def handle_voice_message(self, bot, message, aura_agent, user_id: str)
```
Pipeline (7 steps):

| Step | Lines      | Action                                                |
|------|------------|-------------------------------------------------------|
| 1    | 665–672    | Download voice: `bot.get_file(voice.file_id)` → `file_info.download_to_drive(temp_voice_path)` with `.ogg` temp file |
| 2    | 676–679    | Read bytes from `.ogg`, call `self.stt.transcribe_bytes(audio_bytes, format="ogg")` |
| 3    | 682–684    | Validate: if recognized text is empty or < 2 chars → reply `"🤔 Не разобрала, повтори пожалуйста"` and return |
| 4    | 687       | Send `"typing"` chat action |
| 5    | 690–693    | Process via `aura_agent.process(text=recognized_text, user_id=user_id)` |
| 6    | 696–723    | Determine response format (`ResponseFormatDetector.detect` with `InputMode.VOICE`), then either synthesize voice OR send text |
| 7    | 726–730    | **`finally` block:** Delete downloaded `.ogg` temp file |

**Voice reply path (lines 702–716):**
- Send `"record_voice"` chat action
- `self.tts.synthesize_to_bytes(aura_response)` → `io.BytesIO(audio_bytes)` with `name="voice.mp3"`
- `message.reply_voice(voice=voice_file, caption=None)`

**Text reply path (lines 719–723):**
- `message.reply_text(text=aura_response, parse_mode=None)`

### 10.2 `handle_text_message` — line 732
```
async def handle_text_message(self, bot, message, aura_agent, user_id: str)
```
Pipeline:

| Step | Lines      | Action                                                |
|------|------------|-------------------------------------------------------|
| 1    | 742–744    | Extract `message.text`, send `"typing"` chat action |
| 2    | 748–751    | Process via `aura_agent.process(text=user_text, user_id=user_id)` |
| 3    | 754–757    | Detect format with `InputMode.TEXT` |
| 4    | 759–770    | Either synthesize voice + `reply_voice` OR `reply_text` |

---

## 11. `ResponseMode` Enum Values

Defined at line 28–32:
```python
class ResponseMode(Enum):
    VOICE = "voice"
    TEXT = "text"
    AUTO = "auto"
```

**Note:** `AUTO` is defined but **never used** anywhere in the codebase. The `ResponseFormatDetector.detect()` only ever returns `VOICE` or `TEXT`. The `InputMode` enum at line 35 has no `AUTO` member.

### Detection logic (`ResponseFormatDetector.detect`) — line 598:

| Priority | Condition                                              | Result           |
|----------|--------------------------------------------------------|------------------|
| 1 (highest) | User text contains any `TEXT_REQUEST_TRIGGERS` keyword | `ResponseMode.TEXT` |
| 2        | User text contains any `VOICE_REQUEST_TRIGGERS` keyword | `ResponseMode.VOICE` |
| 3        | `current_mode == InputMode.VOICE`                       | `ResponseMode.VOICE` |
| 4        | `current_mode == InputMode.TEXT`                        | `ResponseMode.TEXT` |
| 5 (default) | None of the above                                      | `ResponseMode.VOICE` |

### Trigger keyword lists:

**`TEXT_REQUEST_TRIGGERS`** (line 44–62): `"напиши"`, `"напечатай"`, `"текстом"`, `"письменно"`, `"скинь текстом"`, `"отправь текст"`, `"сообщение"`, `"скопировать"`, `"копируй"`, `"перешли"`, `"код"`, `"команду"`, `"конфиг"`, `"настройки"`, `"json"`, `"yaml"`, `"python"`, `"sql"`, `"документ"`, `"письмо"`, `"пост"`, `"статью"`, `"отчет"`, `"заметку"`, `"список"`, `"подробно"`, `"развернуто"`, `"детально"`

**`VOICE_REQUEST_TRIGGERS`** (line 64–67): `"скажи"`, `"расскажи"`, `"озвучь"`, `"проговори"`, `"голосом"`, `"вслух"`, `"аудио"`

---

## 12. ALL Configuration Dependencies

### 12.1 Environment variables (via `python-dotenv` / `os.getenv`)

| Variable            | Default                                   | Used at line(s) | Purpose                                           |
|---------------------|-------------------------------------------|-----------------|---------------------------------------------------|
| `VOSK_MODEL_PATH`   | `"models/vosk-model-small-ru-0.22"`       | 101             | Path to Vosk speech recognition model             |
| `OPENAI_API_KEY`    | `""` (empty, raises error if missing)     | 183, 388        | API key for Whisper STT and OpenAI TTS            |
| `TTS_RATE`          | `"160"`                                   | 274, 519        | pyttsx3 speech rate; Piper volume scaling factor  |
| `PIPER_MODEL_PATH`  | `"models/piper/ru_RU-irina-medium.onnx"`  | 501             | Path to Piper TTS ONNX model file                 |

### 12.2 `dotenv` loading
- `load_dotenv()` called at module level, line 22 — runs once at import time

### 12.3 External model files (expected on disk, checked at runtime)

| Model                      | Default Path                                   | Checked at line |
|----------------------------|------------------------------------------------|-----------------|
| Vosk model                 | `models/vosk-model-small-ru-0.22`              | 103 (`Path.exists()`) |
| Piper ONNX model           | `models/piper/ru_RU-irina-medium.onnx`         | 504–505 (lazy load; no pre-check) |
| Piper config JSON          | `{model_path}.json` (auto-derived)             | 502 (lazy load) |
| Silero model               | `snakers4/silero-models` (torch.hub, downloaded automatically) | 544 |

### 12.4 Python package dependencies (imported inline)

| Package              | Used by                                      | Import style       |
|----------------------|----------------------------------------------|--------------------|
| `speech_recognition` | Google STT                                   | Inline inside method (lines 88, 131) |
| `vosk`               | Vosk STT                                     | Inline in `_init_vosk` (line 98) |
| `openai`             | Whisper STT + OpenAI TTS                     | Inline (lines 181, 386) |
| `pyttsx3`            | pyttsx3 TTS                                  | Inline in `_init_pyttsx3` (line 253) |
| `edge_tts`           | Edge TTS                                     | Inline in `_synthesize_edge` (line 441) |
| `piper`              | Piper TTS                                    | Inline in `_synthesize_piper` (line 496) |
| `pydub`              | Audio format conversion (WAV↔MP3, merging)   | Inline in multiple methods (lines 167, 428, 472, 525, 570) |
| `torch`              | Silero TTS                                   | Inline in `_synthesize_silero` (line 536) |
| `scipy`              | Silero TTS (WAV writing)                     | Inline in `_synthesize_silero` (line 537) |
| `wave`               | Vosk STT + Piper TTS (WAV I/O)              | Top of file (line 201) for Vosk; inline (line 497) for Piper |
| `json`               | Vosk STT (parsing results)                   | Inline in `_init_vosk` (line 99) |
| `io`                 | Voice message reply (BytesIO)                | Top of file (line 12) |
| `tempfile`           | Temp files throughout                        | Top of file (line 13) |
| `asyncio`            | Module-level `asyncio.run()`                 | Top of file (line 14) |
| `pathlib.Path`       | Model path existence check                   | Top of file (line 15) |
| `dotenv`             | Environment loading                          | Top of file (line 20) |

### 12.5 Hardcoded configuration constants

| Constant                    | Value                     | Line | Usage                                    |
|-----------------------------|---------------------------|------|------------------------------------------|
| Vosk sample rate            | `16000`                   | 110  | KaldiRecognizer + WAV validation         |
| Vosk read chunk size        | `4000` frames             | 219  | `wf.readframes(4000)`                    |
| pyttsx3 volume              | `0.9`                     | 275  | `setProperty('volume', 0.9)`             |
| OpenAI TTS model            | `"tts-1"`                 | 394  | `client.audio.speech.create(model=...)`  |
| OpenAI TTS speed            | `1.0`                     | 398  | `speed=1.0`                              |
| OpenAI Whisper model        | `"whisper-1"`             | 191  | `client.audio.transcriptions.create()`   |
| Whisper language            | `"ru"`                    | 193  | `language="ru"`                          |
| Google STT language         | `"ru-RU"`                 | 139  | `recognize_google(audio, language=...)`   |
| Edge TTS chunk limit        | `2500` chars              | 450  | `MAX_CHUNK = 2500`                       |
| Edge TTS connect timeout    | `40` seconds              | 452  | `connect_timeout=40`                     |
| Edge TTS receive timeout    | `480` seconds             | 452  | `receive_timeout=480`                    |
| Edge TTS default voice      | `"ru-RU-SvetlanaNeural"`  | 443  | Fallback if `self.voice` is falsy        |
| Piper length scale          | `0.952` (~5% faster)      | 518  | `SynthesisConfig(length_scale=0.952)`    |
| Silero sample rate          | `48000`                   | 552  | `sample_rate=48000`                      |
| Silero model name           | `"silero_tts"`            | 546  | `torch.hub.load(model=...)`              |
| Silero language             | `"ru"`                    | 547  | `torch.hub.load(language=...)`           |
| Silero speaker version      | `"v4_ru"`                 | 548  | `torch.hub.load(speaker=...)`            |
| Silero default speaker      | `"baya"`                  | 541  | `self.voice if self.voice else "baya"`   |
| Cleanup delay               | `180` seconds             | 374  | `time.sleep(180)`                        |
| Min recognized text length  | `2` characters            | 682  | Skip reply if shorter                    |
| Voice reply filename        | `"voice.mp3"`             | 710, 764 | `voice_file.name = "voice.mp3"`      |
| Default STT engine          | `"vosk"`                  | 78   | `SpeechToText.__init__`                  |
| Default TTS engine          | `"edge_tts"`              | 243  | `TextToSpeech.__init__`                  |
| Default TTS voice           | `"ru-RU-SvetlanaNeural"`  | 243  | `TextToSpeech.__init__`                  |
| VH default STT engine       | `"whisper_api"`           | 637  | `VoiceMessageHandler.__init__`           |
| VH default TTS engine       | `"openai_tts"`            | 638  | `VoiceMessageHandler.__init__`           |
| VH default TTS voice        | `"nova"`                  | 639  | `VoiceMessageHandler.__init__`           |
