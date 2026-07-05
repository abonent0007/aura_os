# OSINT Key Hunter

Автоматический охотник за API-ключами через GitHub Code Search.

## Возможности

- **16+ сервисов**: DeepSeek, OpenAI, Anthropic, Gemini, Groq, ElevenLabs, Perplexity, Mistral, Cohere, Together AI, Hugging Face, Replicate, Stability AI, Fireworks AI, Lepton AI, OpenRouter
- **Шаблонный поиск**: `api_key=sk-+"SERVICE"`, `SERVICE_API_KEY "sk-"` и др.
- **Авто-валидация**: проверка каждого ключа через реальный API
- **Автосохранение**: рабочие ключи → `.env`
- **Многопоточность**: до 5 параллельных запросов

## Инструменты

| Инструмент | Описание |
|---|---|
| `hunt_keys_github` | Основной: поиск + валидация + сохранение |
| `hunt_single_service` | Охота по одному сервису |
| `validate_key` | Проверка одного ключа |
| `hunt_status` | Статус последней охоты |

## Использование

```python
# Полная охота по всем сервисам
hunt_keys_github(services="all")

# Охота по конкретному сервису
hunt_keys_github(services="DeepSeek")

# Только поиск без валидации
hunt_keys_github(services="all", validate=False)

# Автосохранение в .env
hunt_keys_github(services="all", auto_save=True)
```
