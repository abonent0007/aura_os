# aura_voice.py
"""
Голосовой модуль AURA OS.
- Приём голосовых из Telegram
- Распознавание речи (Whisper API / Vosk локально)
- Синтез речи (OpenAI TTS / pyttsx3 / Edge TTS)
- Автоопределение формата ответа (голос/текст)
- Очистка временных файлов
"""

import os
import io
import tempfile
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Literal
from enum import Enum

from dotenv import load_dotenv

load_dotenv()


# ============================================================
# 1. ФОРМАТЫ ОТВЕТА
# ============================================================
class ResponseMode(Enum):
    """Как отвечать пользователю"""
    VOICE = "voice"       # Голосом (по умолчанию)
    TEXT = "text"         # Текстом
    AUTO = "auto"         # Автоопределение по запросу


class InputMode(Enum):
    """Как пользователь начал диалог"""
    VOICE = "voice"
    TEXT = "text"


# ============================================================
# 2. КЛЮЧЕВЫЕ СЛОВА ДЛЯ ОПРЕДЕЛЕНИЯ ФОРМАТА
# ============================================================
TEXT_REQUEST_TRIGGERS = [
    # Прямые просьбы написать текстом
    "напиши", "напечатай", "текстом", "письменно",
    "скинь текстом", "отправь текст", "сообщение",
    
    # Когда нужен текст для копирования
    "скопировать", "копируй", "перешли",
    
    # Код и техническое
    "код", "команду", "конфиг", "настройки",
    "json", "yaml", "python", "sql",
    
    # Документы
    "документ", "письмо", "пост", "статью",
    "отчет", "заметку", "список",
    
    # Длинные ответы
    "подробно", "развернуто", "детально",
]

VOICE_REQUEST_TRIGGERS = [
    "скажи", "расскажи", "озвучь", "проговори",
    "голосом", "вслух", "аудио",
]


# ============================================================
# 3. РАСПОЗНАВАНИЕ РЕЧИ (Speech-to-Text)
# ============================================================
class SpeechToText:
    """
    Распознавание речи.
    Поддерживает: Vosk (локально), Google Speech (бесплатно), Whisper API.
    """
    def __init__(self, engine: str = "vosk"):
        self.engine = engine
        
        if engine == "vosk":
            self._init_vosk()
        elif engine == "google":
            self._init_google()
    
    def _init_google(self):
        try:
            import speech_recognition as sr
            self.recognizer = sr.Recognizer()
            print("Google Speech Recognition ready")
        except ImportError:
            print("Install: pip install SpeechRecognition")
            self.recognizer = None
    
    def _init_vosk(self):
        """Инициализация локального Vosk"""
        try:
            import vosk
            import json
            
            model_path = os.getenv("VOSK_MODEL_PATH", "models/vosk-model-small-ru-0.22")
            
            if not Path(model_path).exists():
                print(f"⚠️ Vosk модель не найдена: {model_path}")
                print("  Скачай: https://alphacephei.com/vosk/models")
                self.vosk_model = None
                return
            
            self.vosk_model = vosk.Model(model_path)
            self.vosk_recognizer = vosk.KaldiRecognizer(self.vosk_model, 16000)
            print(f"✅ Vosk загружен: {model_path}")
            
        except ImportError:
            print("⚠️ Vosk не установлен: pip install vosk")
            self.vosk_model = None
    
    async def transcribe_file(self, file_path: str) -> str:
        """Распознавание аудиофайла → текст"""
        
        if self.engine == "whisper_api":
            return await self._transcribe_whisper_api(file_path)
        elif self.engine == "vosk":
            return await self._transcribe_vosk(file_path)
        elif self.engine == "google":
            return await self._transcribe_google(file_path)
        else:
            raise ValueError(f"Неизвестный движок распознавания: {self.engine}")

    async def _transcribe_google(self, file_path: str) -> str:
        """Распознавание через Google Speech Recognition (бесплатно, без модели)"""
        import speech_recognition as sr
        if not self.recognizer:
            raise RuntimeError("Google Speech Recognition не инициализирован")
        
        # Конвертируем в WAV через sounddevice или просто читаем
        try:
            with sr.AudioFile(file_path) as source:
                audio = self.recognizer.record(source)
            text = self.recognizer.recognize_google(audio, language="ru-RU")
            return text
        except sr.UnknownValueError:
            return ""
        except sr.RequestError as e:
            raise RuntimeError(f"Google Speech API error: {e}")
    
    async def transcribe_bytes(self, audio_bytes: bytes, format: str = "ogg") -> str:
        """Распознавание из байтов (например из Telegram). Конвертирует OGG → WAV для Vosk."""
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as f:
            f.write(audio_bytes)
            temp_path = f.name

        try:
            # Конвертация OGG/Opus → WAV для Vosk
            if format in ("ogg", "opus", "mp3") and self.engine == "vosk":
                temp_path = self._convert_to_wav(temp_path, format)

            text = await self.transcribe_file(temp_path)
            return text
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"Deleted temp file: {temp_path}")

    def _convert_to_wav(self, file_path: str, fmt: str) -> str:
        """Конвертирует аудио в WAV (16kHz, mono, 16-bit) для Vosk."""
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(file_path, format=fmt)
            audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
            wav_path = file_path.rsplit(".", 1)[0] + "_converted.wav"
            audio.export(wav_path, format="wav")
            os.remove(file_path)
            return wav_path
        except ImportError:
            raise RuntimeError("pydub не установлен. pip install pydub")
        except Exception as e:
            raise RuntimeError(f"Ошибка конвертации аудио {fmt}→WAV: {e}")
    
    async def _transcribe_whisper_api(self, file_path: str) -> str:
        """Распознавание через OpenAI Whisper API"""
        import openai
        
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в .env")
        
        client = openai.AsyncOpenAI(api_key=api_key)
        
        with open(file_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="ru",
                response_format="text"
            )
        
        return transcript.strip()
    
    async def _transcribe_vosk(self, file_path: str) -> str:
        """Распознавание через локальный Vosk"""
        import wave
        import json
        
        if not self.vosk_model:
            raise RuntimeError("Vosk модель не загружена")
        
        # Конвертируем в WAV если нужно (упрощенно — считаем что уже WAV)
        wf = wave.open(file_path, "rb")
        
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2 or wf.getframerate() != 16000:
            wf.close()
            raise ValueError("Аудио должно быть: 1 канал, 16-bit, 16000 Hz")
        
        recognizer = self.vosk_recognizer
        recognizer.Reset()
        
        results = []
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if recognizer.AcceptWaveform(data):
                result = json.loads(recognizer.Result())
                results.append(result.get("text", ""))
        
        # Финальный результат
        final = json.loads(recognizer.FinalResult())
        results.append(final.get("text", ""))
        
        wf.close()
        return " ".join(results).strip()


# ============================================================
# 4. СИНТЕЗ РЕЧИ (Text-to-Speech)
# ============================================================
class TextToSpeech:
    """
    Синтез речи.
    Основной: Edge TTS (ru-RU-SvetlanaNeural — бесплатно, высокое качество).
    Запасные: pyttsx3 (локально), OpenAI TTS.
    """
    def __init__(self, engine: str = "edge_tts", voice: str = "ru-RU-SvetlanaNeural"):
        self.engine = engine
        self.voice = voice
        
        if engine == "pyttsx3":
            self._init_pyttsx3()
    
    def _init_pyttsx3(self):
        """Инициализация локального pyttsx3 с женским русским голосом"""
        try:
            import pyttsx3
            
            self.tts_engine = pyttsx3.init()
            
            # Ищем русский женский голос
            voices = self.tts_engine.getProperty('voices')
            russian_voice = None
            
            for v in voices:
                name_lower = v.name.lower()
                id_lower = v.id.lower()
                if any(lang in name_lower + id_lower for lang in ['russian', 'ru', 'russ']):
                    russian_voice = v.id
                    break
            
            if russian_voice:
                self.tts_engine.setProperty('voice', russian_voice)
                print(f"✅ pyttsx3 голос: {russian_voice}")
            else:
                print("⚠️ Русский голос не найден, использую системный")
            
            self.tts_engine.setProperty('rate', int(os.getenv("TTS_RATE", "160")))
            self.tts_engine.setProperty('volume', 0.9)
            
        except ImportError:
            print("⚠️ pyttsx3 не установлен: pip install pyttsx3")
            self.tts_engine = None

    @staticmethod
    def _normalize_for_tts(text: str) -> str:
        import re
        
        # ── СЛОВАРЬ ЧИСЕЛ ──
        units = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять']
        teens = ['десять', 'одиннадцать', 'двенадцать', 'тринадцать', 'четырнадцать',
                 'пятнадцать', 'шестнадцать', 'семнадцать', 'восемнадцать', 'девятнадцать']
        tens = ['', '', 'двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят',
                'семьдесят', 'восемьдесят', 'девяносто']
        hundreds = ['', 'сто', 'двести', 'триста', 'четыреста', 'пятьсот',
                    'шестьсот', 'семьсот', 'восемьсот', 'девятьсот']
        
        def num_to_words(n: int) -> str:
            if n < 0: return 'минус ' + num_to_words(-n)
            if n == 0: return 'ноль'
            result = []
            if n >= 1000:
                t = n // 1000
                if t == 1: result.append('одна тысяча')
                elif t == 2: result.append('две тысячи')
                elif t < 5: result.append(num_to_words(t) + ' тысячи')
                else: result.append(num_to_words(t) + ' тысяч')
                n %= 1000
            if n >= 100:
                result.append(hundreds[n // 100])
                n %= 100
            if n >= 20:
                result.append(tens[n // 10])
                n %= 10
                if n > 0: result.append(units[n])
            elif n >= 10:
                result.append(teens[n - 10])
            elif n > 0:
                result.append(units[n])
            return ' '.join(filter(None, result))
        
        def replace_num(m):
            num_str = m.group(0)
            try:
                return num_to_words(int(num_str.replace(' ', '')))
            except ValueError:
                return num_str
        
        # ── ШАГ 1: ДЕСЯТИЧНЫЕ ЧИСЛА (до целых!) ──
        def _decimal_repl(m):
            left = num_to_words(int(m.group(1)))
            right = num_to_words(int(m.group(2)))
            return f'{left} точка {right}'
        text = re.sub(r'(\d+)\.(\d+)', _decimal_repl, text)
        
        # ── ШАГ 2: ЦЕЛЫЕ ЦИФРЫ ──
        text = re.sub(r'(?<![#№.\w])\d{4,}(?!\w)', replace_num, text)
        text = re.sub(r'(?<![#№.\w])\d{2,3}(?!\w)', replace_num, text)
        text = re.sub(r'(?<![#№.\w])\d(?![\d\w])', replace_num, text)
        # Второй проход: цифры после "номер ", "пункт ", "шаг " итд
        text = re.sub(r'(?<=номер )\d{1,6}\b', replace_num, text)
        text = re.sub(r'(?<=пункт )\d{1,6}\b', replace_num, text)
        text = re.sub(r'(?<=шаг )\d{1,6}\b', replace_num, text)
        text = re.sub(r'(?<=версия )\d{1,6}\b', replace_num, text)
        text = re.sub(r'(?<=v)\d+(?=\b)', replace_num, text)
        
        # ── ШАГ 2: ЗНАЧКИ В СЛОВА ──
        text = text.replace('%', ' процентов')
        # Температура: 25°C, 25C → 25 градусов
        text = re.sub(r'(\d+)\s*°\s*C\b', r'\1 градусов Цельсия', text)
        text = re.sub(r'(\d+)\s*°\s*F\b', r'\1 градусов Фаренгейта', text)
        text = re.sub(r'(\d+)\s*°', r'\1 градусов', text)
        text = re.sub(r'(\d+)\s*C\b', r'\1 градусов', text)
        text = re.sub(r'(\d+)\s*F\b', r'\1 градусов Фаренгейта', text)
        text = text.replace('~', ' примерно ')
        text = text.replace('≈', ' приблизительно ')
        text = text.replace('№', 'номер ')
        text = text.replace('&', ' и ')
        text = text.replace('+', ' плюс ').replace('=', ' равно ')
        # Десятичные: 4.0 → четыре точка ноль
        def _decimal_repl(m):
            left = num_to_words(int(m.group(1))) if m.group(1).isdigit() else m.group(1)
            right = num_to_words(int(m.group(2))) if m.group(2).isdigit() else m.group(2)
            return f'{left} точка {right}'
        text = re.sub(r'(\d+)\.(\d+)', _decimal_repl, text)
        
        # ── УДАЛИТЬ НЕПРОИЗНОСИМОЕ ──
        text = re.sub(r'["\'«»„“]', '', text)       # кавычки
        text = re.sub(r'[*#@^]', '', text)            # звёздочки/хештеги
        text = re.sub(r'[«»]', '', text)              # ёлочки
        
        # ── ПАУЗЫ: точка и запятая остаются — Silero делает паузы на них ──
        # Добавляем паузу после точки если текст слипается
        text = re.sub(r'\.(?=[а-яёА-ЯЁ])', '. ', text)
        
        # ── ШАГ 4: ФИНАЛЬНЫЙ ПРОХОД — цифры, оставшиеся после замены значков ──
        text = re.sub(r'(?<![#№.\w])\d{4,}(?!\w)', replace_num, text)
        text = re.sub(r'(?<![#№.\w])\d{2,3}(?!\w)', replace_num, text)
        text = re.sub(r'(?<![#№.\w])\d(?![\d\w])', replace_num, text)
        
        # Убираем лишние пробелы
        text = re.sub(r'\s{2,}', ' ', text)
        
        return text

    @staticmethod
    def _clean_for_tts(text: str) -> str:
        """Удалить из текста markdown и эмодзи для чистого голосового произношения."""
        import re
        # Markdown bold/italic: **...** *...* __...__
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'\1', text)
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        text = re.sub(r'\*(.+?)\*', r'\1', text)
        text = re.sub(r'__(.+?)__', r'\1', text)
        text = re.sub(r'~~(.+?)~~', r'\1', text)
        # Inline code
        text = re.sub(r'`(.+?)`', r'\1', text)
        # Markdown links: [text](url) → text
        text = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', text)
        # Markdown headers: ## ... → ...
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        # Horizontal rules: --- *** ___ → skip
        text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
        # Emoji: strip all Unicode emoji and emoticons
        text = re.sub(r'[\U0001F300-\U0001F9FF\u2600-\u27BF\u2B50\u2700-\u27BF\uFE00-\uFE0F\u200D\u20D0-\u20FF\uD83C-\uDBFF\uDC00-\uDFFF]+', '', text)
        # ASCII emoticons that edge-tts reads as characters (e.g. "двоеточие скобка")
        text = re.sub(r'\s?[:;][\-]?[()DPpdOo]', '', text)
        # HTML tags
        text = re.sub(r'<[^>]+>', '', text)
        # Collapse multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)

        # Удаляем блоки кода в ``` (тройные кавычки) — всё что внутри считается кодом
        text = re.sub(r'```[\s\S]*?```', '', text)

        # Фильтруем строки: пропускаем только с отступом (код) или без русских букв
        lines = text.split('\n')
        russian_lines = []
        for line in lines:
            stripped = line.strip()
            # Пропускаем строки с отступом — это код
            if line[0:1] in (' ', '\t'):
                continue
            # Оставляем строки с русскими буквами
            if re.search(r'[а-яёА-ЯЁ]', stripped):
                russian_lines.append(stripped)
            # Или строки без латиницы но со знаками препинания
            elif stripped and not re.search(r'[a-zA-Z]', stripped) and re.search(r'[.!?]', stripped):
                russian_lines.append(stripped)
        text = '\n'.join(russian_lines)

        # Удаляем URL
        text = re.sub(r'https?://\S+', '', text)

        # Удаляем оставшиеся строки которые выглядят как код/команды
        text = re.sub(r'^[a-zA-Z0-9_\-\.\/\\\:\s]+\$?\s*$', '', text, flags=re.MULTILINE)

        # Удаляем одиночные латинские слова (артефакты)
        text = re.sub(r'\b[a-zA-Z]{2,}\b', '', text)

        # Убираем пустые строки в начале и конце, дубли пробелов
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' +', ' ', text)

        return text.strip()

    async def synthesize_to_file(self, text: str, output_path: str = None) -> str:
        """
        Синтез речи в аудиофайл.
        Возвращает путь к файлу (временному или указанному).
        """
        original_len = len(text)
        original_len = len(text)
        # Чистка ДО нормализации: удаляем код пока он не испорчен конвертацией
        text = self._clean_for_tts(text)
        text = self._normalize_for_tts(text)
        if len(text) < original_len:
            print(f"[TTS] _clean_for_tts: {original_len} → {len(text)} символов (удалено {original_len - len(text)})")
        if self.engine == "openai_tts":
            return await self._synthesize_openai(text, output_path)
        elif self.engine == "pyttsx3":
            return await self._synthesize_pyttsx3(text, output_path)
        elif self.engine == "edge_tts":
            return await self._synthesize_edge(text, output_path)
        elif self.engine == "kokoro":
            raise NotImplementedError("Kokoro TTS engine not yet implemented. Use 'silero' or 'piper' instead.")
        elif self.engine == "piper":
            return await self._synthesize_piper(text, output_path)
        elif self.engine == "silero":
            return await self._synthesize_silero(text, output_path)
        else:
            raise ValueError(f"Неизвестный движок синтеза: {self.engine}")
    
    async def synthesize_to_bytes(self, text: str) -> bytes:
        """Синтез речи в байты (для отправки в Telegram)"""
        temp_path = None
        try:
            temp_path = await self.synthesize_to_file(text)
            with open(temp_path, "rb") as f:
                audio_bytes = f.read()
            return audio_bytes
        finally:
            # Пауза 5 мин перед удалением — даём аудио доиграть
            if temp_path and os.path.exists(temp_path):
                def _delayed_cleanup():
                    import time
                    time.sleep(300)
                    try:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                            print(f"🗑️ Удален временный файл TTS: {temp_path}")
                    except Exception:
                        pass
                import threading
                threading.Thread(target=_delayed_cleanup, daemon=True).start()
    
    async def _synthesize_openai(self, text: str, output_path: str = None) -> str:
        """Синтез через OpenAI TTS API (женские голоса: nova, shimmer, alloy)"""
        import openai
        
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в .env")
        
        client = openai.AsyncOpenAI(api_key=api_key, timeout=120.0)
        
        response = await client.audio.speech.create(
            model="tts-1",           # tts-1 быстрее, tts-1-hd качественнее
            voice=self.voice,        # nova — женский, спокойный
            input=text,
            speed=1.0
        )
        
        if output_path is None:
            # Временный файл
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                output_path = f.name
        
        response.stream_to_file(output_path)
        return output_path
    
    async def _synthesize_pyttsx3(self, text: str, output_path: str = None) -> str:
        """Синтез через локальный pyttsx3 (Microsoft Irina, без лимитов, офлайн)"""
        if not self.tts_engine:
            raise RuntimeError("pyttsx3 не инициализирован")

        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                output_path = f.name
        else:
            output_path = str(output_path)

        # pyttsx3 сохраняет в WAV → конвертируем в MP3 через pydub
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as wf:
            wav_path = wf.name

        try:
            self.tts_engine.save_to_file(text, wav_path)
            self.tts_engine.runAndWait()

            from pydub import AudioSegment
            audio = AudioSegment.from_file(wav_path, format="wav")
            audio.export(output_path, format="mp3")
        finally:
            if os.path.exists(wav_path):
                os.remove(wav_path)

        return output_path
    
    async def _synthesize_edge(self, text: str, output_path: str = None) -> str:
        """Синтез через Microsoft Edge TTS (бесплатно, качественно).
        Разбивает длинный текст на чанки чтобы обойти лимит сервиса."""
        try:
            import edge_tts

            voice = self.voice if self.voice else "ru-RU-SvetlanaNeural"

            if output_path is None:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    output_path = f.name

            # Edge TTS limit: ~3000 chars per request. Split at sentence boundaries.
            MAX_CHUNK = 2500
            if len(text) <= MAX_CHUNK:
                communicate = edge_tts.Communicate(text, voice, connect_timeout=40, receive_timeout=480)
                await communicate.save(output_path)
                return output_path

            # Split into sentence chunks
            import re
            sentences = re.split(r'(?<=[.!?])\s+', text)
            chunks = []
            current = ""
            for s in sentences:
                if len(current) + len(s) + 1 > MAX_CHUNK and current:
                    chunks.append(current.strip())
                    current = s
                else:
                    current = (current + " " + s).strip()
            if current.strip():
                chunks.append(current.strip())

            # Synthesize each chunk and concatenate
            import io
            from pydub import AudioSegment

            combined = AudioSegment.empty()
            for i, chunk in enumerate(chunks):
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as cf:
                    chunk_path = cf.name
                try:
                    communicate = edge_tts.Communicate(chunk, voice, connect_timeout=40, receive_timeout=480)
                    await communicate.save(chunk_path)
                    segment = AudioSegment.from_file(chunk_path, format="mp3")
                    combined += segment
                finally:
                    if os.path.exists(chunk_path):
                        os.remove(chunk_path)

            combined.export(output_path, format="mp3")
            return output_path

        except ImportError:
            raise ImportError("Установи edge_tts: pip install edge-tts")

    async def _synthesize_piper(self, text: str, output_path: str = None) -> str:
        """Синтез через Piper TTS (локальный, быстрый, русский голос irina)."""
        try:
            from piper import PiperVoice
            import wave
        except ImportError:
            raise ImportError("Установи piper-tts: pip install piper-tts")

        model_path = os.getenv("PIPER_MODEL_PATH", "models/piper/ru_RU-irina-medium.onnx")
        config_path = model_path.replace(".onnx", ".json")

        if not hasattr(self, '_piper_voice'):
            self._piper_voice = PiperVoice.load(model_path, config_path=config_path)

        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                output_path = f.name

        # Piper пишет WAV через wave.Wave_write объект
        wav_path = output_path.replace(".mp3", ".wav")
        if wav_path == output_path:
            wav_path = output_path + ".wav"

        from piper import SynthesisConfig
        syn_config = SynthesisConfig(
            length_scale=0.952,  # ~5% faster
            volume=float(os.getenv("TTS_RATE", "160")) / 160 * 1.0  # scale volume
        )
        with wave.open(wav_path, "wb") as wf:
            self._piper_voice.synthesize_wav(text, wf, syn_config=syn_config)

        # WAV → MP3
        from pydub import AudioSegment
        audio = AudioSegment.from_file(wav_path, format="wav")
        audio.export(output_path, format="mp3")
        if os.path.exists(wav_path):
            os.remove(wav_path)

        return output_path

    async def _synthesize_silero(self, text: str, output_path: str = None) -> str:
        """Синтез через Silero TTS v5 (локальный, 100x realtime, baya/kseniya/xenia).
        Длинный текст разбивается на предложения ≤500 символов — иначе модель обрывает голос."""
        try:
            import torch
            import scipy.io.wavfile as wavfile
        except ImportError:
            raise ImportError("pip install torch scipy")

        speaker = self.voice if self.voice else "baya"

        if not hasattr(self, '_silero_model'):
            self._silero_model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language='ru',
                speaker='v4_ru',
                trust_repo=True
            )

        sample_rate = 48000
        MAX_SILERO_CHUNK = 150  # chars per chunk — ультра-консервативный предел

        def _synthesize_chunk(chunk_text: str):
            chunk_audio = self._silero_model.apply_tts(
                text=chunk_text,
                speaker=speaker,
                sample_rate=sample_rate,
                put_accent=True,
                put_yo=True
            )
            # Silero возвращает тензор на GPU — переводим на CPU
            if chunk_audio.device.type != 'cpu':
                chunk_audio = chunk_audio.cpu()
            return chunk_audio

        if len(text) <= MAX_SILERO_CHUNK:
            print(f"[Silero] 1 чанк, {len(text)} символов")
            audio = _synthesize_chunk(text)
        else:
            import re
            # Разбивка по границам предложений (точка/вопрос/воскл + пробел)
            sentences = re.split(r'(?<=[.!?])\s+', text)
            chunks = []
            current = ""
            for s in sentences:
                if len(current) + len(s) + 1 > MAX_SILERO_CHUNK and current:
                    chunks.append(current.strip())
                    current = s
                else:
                    current = (current + " " + s).strip() if current else s
            if current.strip():
                chunks.append(current.strip())

            print(f"[Silero] Всего {len(text)} символов → {len(chunks)} чанков")

            # Синтез каждого чанка + пауза 0.35с между ними
            audio_parts = []
            silence_samples = int(sample_rate * 0.35)
            for i, chunk in enumerate(chunks):
                print(f"[Silero]   Чанк {i+1}/{len(chunks)}: {len(chunk)} символов → ", end="", flush=True)
                try:
                    part = _synthesize_chunk(chunk)
                    if part is None or part.shape[0] == 0:
                        print(f"ПУСТОЙ (пропущен)")
                        continue
                    duration = part.shape[0] / sample_rate
                    print(f"{duration:.1f}с")
                    audio_parts.append(part)
                    if i < len(chunks) - 1:
                        audio_parts.append(torch.zeros(silence_samples, dtype=part.dtype))
                except Exception as e:
                    print(f"ОШИБКА: {e}")
                    continue

            if not audio_parts:
                raise RuntimeError("Silero: все чанки упали. Текст не может быть синтезирован.")
            audio = torch.cat(audio_parts, dim=0)
            total_duration = audio.shape[0] / sample_rate
            print(f"[Silero] Итого: {total_duration:.1f}с аудио")

        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                output_path = f.name

        wav_path = output_path.replace(".mp3", ".wav")
        if wav_path == output_path:
            wav_path = output_path + ".wav"
        audio_np = audio.numpy()
        wavfile.write(wav_path, sample_rate, audio_np)
        print(f"[Silero] WAV записан: {os.path.getsize(wav_path)/1024:.0f} КБ, {audio_np.shape[0]/sample_rate:.1f}с")

        from pydub import AudioSegment
        seg = AudioSegment.from_file(wav_path, format="wav")
        seg.export(output_path, format="mp3")
        print(f"[Silero] MP3 записан: {os.path.getsize(output_path)/1024:.0f} КБ")
        if os.path.exists(wav_path):
            os.remove(wav_path)

        return output_path


# ============================================================
# 5. ОПРЕДЕЛИТЕЛЬ ФОРМАТА ОТВЕТА
# ============================================================
class ResponseFormatDetector:
    """
    Определяет, как отвечать: голосом или текстом.
    
    Правила:
    1. Если пользователь явно просит "напиши" → текст
    2. Если пользователь явно просит "скажи" → голос
    3. Если начал голосом → продолжаем голосом
    4. Если начал текстом → продолжаем текстом
    5. По умолчанию → голос
    """
    
    def __init__(self):
        self.text_triggers = set(TEXT_REQUEST_TRIGGERS)
        self.voice_triggers = set(VOICE_REQUEST_TRIGGERS)
    
    def detect(self, user_text: str, current_mode: InputMode) -> ResponseMode:
        """
        Определяет формат ответа на основе текста запроса и текущего режима.
        """
        text_lower = user_text.lower()
        
        # 1. Явные просьбы текстом
        for trigger in self.text_triggers:
            if trigger in text_lower:
                print(f"📝 Триггер текста: '{trigger}'")
                return ResponseMode.TEXT
        
        # 2. Явные просьбы голосом
        for trigger in self.voice_triggers:
            if trigger in text_lower:
                print(f"🎤 Триггер голоса: '{trigger}'")
                return ResponseMode.VOICE
        
        # 3. Продолжаем в том же формате, что и ввод
        if current_mode == InputMode.VOICE:
            return ResponseMode.VOICE
        elif current_mode == InputMode.TEXT:
            return ResponseMode.TEXT
        
        # 4. По умолчанию — голос
        return ResponseMode.VOICE


# ============================================================
# 6. ОБРАБОТЧИК ГОЛОСОВЫХ СООБЩЕНИЙ TELEGRAM
# ============================================================
class VoiceMessageHandler:
    """
    Полный цикл обработки голосового сообщения из Telegram:
    Скачать → Распознать → Обработать → Синтезировать → Отправить → Очистить
    """
    
    def __init__(
        self,
        stt_engine: str = "whisper_api",
        tts_engine: str = "openai_tts",
        tts_voice: str = "nova"
    ):
        self.stt = SpeechToText(engine=stt_engine)
        self.tts = TextToSpeech(engine=tts_engine, voice=tts_voice)
        self.format_detector = ResponseFormatDetector()
    
    async def handle_voice_message(
        self,
        bot,           # Telegram bot instance
        message,       # Telegram message object
        aura_agent,    # AuraAgent instance
        user_id: str
    ):
        """
        Полный цикл обработки голосового сообщения.
        
        1. Скачиваем голосовое из Telegram
        2. Распознаем в текст
        3. Обрабатываем через AURA
        4. Определяем формат ответа
        5. Отправляем ответ (голосом или текстом)
        6. Очищаем временные файлы
        """
        chat_id = message.chat.id
        
        # --- Шаг 1: Скачиваем голосовое ---
        voice = message.voice
        file_info = await bot.get_file(voice.file_id)

        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
            temp_voice_path = f.name

        await file_info.download_to_drive(temp_voice_path)
        print(f"📥 Голосовое скачано: {temp_voice_path}")
        
        try:
            # --- Шаг 2: Распознаем в текст ---
            with open(temp_voice_path, "rb") as f:
                audio_bytes = f.read()
            
            recognized_text = await self.stt.transcribe_bytes(audio_bytes, format="ogg")
            print(f"🎤 Распознано: \"{recognized_text}\"")
            
            if not recognized_text or len(recognized_text.strip()) < 2:
                await message.reply_text("🤔 Не разобрала, повтори пожалуйста")
                return
            
            # --- Шаг 3: Отправляем "печатает..." ---
            await bot.send_chat_action(chat_id=chat_id, action="typing")
            
            # --- Шаг 4: Обрабатываем через AURA ---
            aura_response = await aura_agent.process(
                text=recognized_text,
                user_id=user_id
            )
            
            # --- Шаг 5: Определяем формат ответа ---
            response_mode = self.format_detector.detect(
                recognized_text,
                current_mode=InputMode.VOICE  # начали с голоса
            )
            
            # --- Шаг 6: Отправляем ответ ---
            if response_mode == ResponseMode.VOICE:
                # Синтезируем голос
                await bot.send_chat_action(chat_id=chat_id, action="record_voice")
                
                audio_bytes = await self.tts.synthesize_to_bytes(aura_response)
                
                # Отправляем голосовое
                voice_file = io.BytesIO(audio_bytes)
                voice_file.name = "voice.mp3"
                
                await message.reply_voice(
                    voice=voice_file,
                    caption=None  # Без подписи текстом
                )
                print(f"🔊 Отправлен голосовой ответ")
                
            else:
                # Отправляем текстом
                await message.reply_text(
                    text=aura_response,
                    parse_mode=None
                )
                print(f"📝 Отправлен текстовый ответ")
            
        finally:
            # --- Шаг 7: ОЧИСТКА временных файлов ---
            if os.path.exists(temp_voice_path):
                os.remove(temp_voice_path)
                print(f"🗑️ Удален временный файл: {temp_voice_path}")
    
    async def handle_text_message(
        self,
        bot,
        message,
        aura_agent,
        user_id: str
    ):
        """
        Обработка текстового сообщения с возможностью голосового ответа.
        """
        chat_id = message.chat.id
        user_text = message.text
        
        await bot.send_chat_action(chat_id=chat_id, action="typing")
        
        # Обрабатываем
        aura_response = await aura_agent.process(
            text=user_text,
            user_id=user_id
        )
        
        # Определяем формат
        response_mode = self.format_detector.detect(
            user_text,
            current_mode=InputMode.TEXT  # начали с текста
        )
        
        if response_mode == ResponseMode.VOICE:
            await bot.send_chat_action(chat_id=chat_id, action="record_voice")
            audio_bytes = await self.tts.synthesize_to_bytes(aura_response)
            
            voice_file = io.BytesIO(audio_bytes)
            voice_file.name = "voice.mp3"
            
            await message.reply_voice(voice=voice_file)
            print(f"🔊 Текстовый запрос → голосовой ответ")
        else:
            await message.reply_text(text=aura_response)
            print(f"📝 Текстовый запрос → текстовый ответ")


# ============================================================
# 7. КОНСОЛЬНЫЙ РЕЖИМ (для тестирования без Telegram)
# ============================================================
class ConsoleVoiceMode:
    """Тестовый режим в консоли с эмуляцией голоса"""
    
    def __init__(self, aura_agent):
        self.aura_agent = aura_agent
        self.format_detector = ResponseFormatDetector()
        self.current_mode = InputMode.TEXT
    
    async def run(self):
        print("🎙️ AURA Console Mode")
        print("  Команды: !voice, !text, !quit")
        print("  Голосовой ввод эмулируется текстом с префиксом '🎤'")
        
        while True:
            try:
                user_input = input("\n👤 Вы: ").strip()
                
                if not user_input:
                    continue
                
                # Команды
                if user_input.startswith("!voice"):
                    self.current_mode = InputMode.VOICE
                    print("🎤 Режим: голосовой ввод")
                    continue
                elif user_input.startswith("!text"):
                    self.current_mode = InputMode.TEXT
                    print("📝 Режим: текстовый ввод")
                    continue
                elif user_input.startswith("!quit"):
                    print("👋 Пока!")
                    break
                
                # Эмуляция голосового ввода
                if user_input.startswith("🎤"):
                    user_text = user_input[1:].strip()
                    self.current_mode = InputMode.VOICE
                else:
                    user_text = user_input
                    self.current_mode = InputMode.TEXT
                
                # Обработка
                response = await self.aura_agent.process(user_text)
                
                # Определяем формат
                mode = self.format_detector.detect(user_text, self.current_mode)
                
                if mode == ResponseMode.VOICE:
                    print(f"🔊 AURA (голос): {response}")
                else:
                    print(f"🎙️ AURA (текст): {response}")
                    
            except KeyboardInterrupt:
                print("\n👋 Пока!")
                break
            except Exception as e:
                print(f"⚠️ Ошибка: {e}")


# ============================================================
# 8. ТЕСТ
# ============================================================
async def test_voice_flow():
    """Тест полного цикла: текст → голосовой ответ"""
    
    voice_handler = VoiceMessageHandler(
        stt_engine="whisper_api",
        tts_engine="openai_tts",
        tts_voice="nova"  # Женский голос OpenAI
    )
    
    # Тест синтеза
    print("🎤 Тест синтеза речи...")
    test_text = "Привет! Я Аура, твой голосовой ассистент. Как я могу помочь?"
    
    audio_bytes = await voice_handler.tts.synthesize_to_bytes(test_text)
    print(f"✅ Синтезировано {len(audio_bytes)} байт аудио")
    
    # Тест определения формата
    detector = ResponseFormatDetector()
    
    test_queries = [
        ("Расскажи о погоде", InputMode.VOICE),
        ("Напиши отчет", InputMode.TEXT),
        ("Как дела?", InputMode.VOICE),
        ("Скажи код", InputMode.TEXT),
    ]
    
    print("\n📋 Тест определения формата:")
    for query, input_mode in test_queries:
        result = detector.detect(query, input_mode)
        print(f"  '{query}' ({input_mode.value}) → {result.value}")


if __name__ == "__main__":
    asyncio.run(test_voice_flow())