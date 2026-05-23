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
    
    async def synthesize_to_file(self, text: str, output_path: str = None) -> str:
        """
        Синтез речи в аудиофайл.
        Возвращает путь к файлу (временному или указанному).
        """
        if self.engine == "openai_tts":
            return await self._synthesize_openai(text, output_path)
        elif self.engine == "pyttsx3":
            return await self._synthesize_pyttsx3(text, output_path)
        elif self.engine == "edge_tts":
            return await self._synthesize_edge(text, output_path)
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
            # УДАЛЯЕМ временный файл после прочтения
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)
                print(f"🗑️ Удален временный файл TTS: {temp_path}")
    
    async def _synthesize_openai(self, text: str, output_path: str = None) -> str:
        """Синтез через OpenAI TTS API (женские голоса: nova, shimmer, alloy)"""
        import openai
        
        api_key = os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise ValueError("OPENAI_API_KEY не найден в .env")
        
        client = openai.AsyncOpenAI(api_key=api_key)
        
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
        """Синтез через локальный pyttsx3"""
        if not self.tts_engine:
            raise RuntimeError("pyttsx3 не инициализирован")
        
        if output_path is None:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                output_path = f.name
        
        # pyttsx3 сохраняет в файл
        self.tts_engine.save_to_file(text, output_path)
        self.tts_engine.runAndWait()
        
        return output_path
    
    async def _synthesize_edge(self, text: str, output_path: str = None) -> str:
        """Синтез через Microsoft Edge TTS (бесплатно, качественно)"""
        try:
            import edge_tts
            
            voice = self.voice if self.voice else "ru-RU-SvetlanaNeural"
            
            if output_path is None:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    output_path = f.name
            
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
            
            return output_path
            
        except ImportError:
            raise ImportError("Установи edge_tts: pip install edge-tts")


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