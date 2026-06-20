# SMS Sender

Отправка SMS через API sms.ru. Ключ хранится централизованно в skills/custom/.env.

## Инструменты
- `send_sms` — отправить SMS (на номер Юрия или указанный)
- `sms_balance` — проверить баланс sms.ru
- `sms_set_key` — сохранить API-ключ (записывает в .env + data.json)
- `sms_set_default_phone` — установить номер по умолчанию

## Хранение ключа
Ключ sms_ru_api_key хранится в skills/custom/.env — едином хранилище всех ключей AURA OS.
При вызове sms_set_key ключ сохраняется и в .env, и в локальный data.json (для обратной совместимости).
При отправке SMS ключ читается сначала из .env, потом из data.json.

## Зависимости
- httpx
