// AURA OS Dashboard — Основное приложение

let ws = null;
const WS_URL = `ws://${window.location.host}/ws`;

// ============================================================
// ИНИЦИАЛИЗАЦИЯ
// ============================================================
document.addEventListener('DOMContentLoaded', () => {
    initNavigation();
    connectWebSocket();
    refreshDashboard();
});

// ============================================================
// НАВИГАЦИЯ
// ============================================================
function initNavigation() {
    document.querySelectorAll('.nav-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const page = item.dataset.page;
            navigateTo(page);
        });
    });
    
    // Загружаем страницу из хеша
    const hash = window.location.hash.slice(1) || 'dashboard';
    navigateTo(hash);
}

function navigateTo(page) {
    // Обновляем навигацию
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.toggle('active', item.dataset.page === page);
    });
    
    // Обновляем страницы
    document.querySelectorAll('.page').forEach(p => {
        p.classList.toggle('active', p.id === `page-${page}`);
    });
    
    window.location.hash = page;
    
    // Загружаем данные
    switch(page) {
        case 'dashboard': refreshDashboard(); break;
        case 'skills': loadSkills(); break;
        case 'logs': loadLogs(); break;
        case 'backups': loadBackups(); break;
        case 'settings': loadSettings(); break;
        case 'calendar': loadCalendarView(7); break;
    }
}

// ============================================================
// WEBSOCKET
// ============================================================
function connectWebSocket() {
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('WebSocket подключен');
        updateConnectionStatus(true);
    };
    
    ws.onmessage = (event) => {
        const { event: evt, data } = JSON.parse(event.data);
        handleWebSocketEvent(evt, data);
    };
    
    ws.onclose = () => {
        console.log('WebSocket отключен');
        updateConnectionStatus(false);
        setTimeout(connectWebSocket, 3000);
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket ошибка:', error);
    };
}

function handleWebSocketEvent(event, data) {
    switch(event) {
        case 'skill_created':
        case 'skill_deleted':
        case 'skill_toggled':
            loadSkills();
            break;
        case 'backup_created':
        case 'rollback_performed':
            loadBackups();
            break;
        case 'config_updated':
            loadSettings();
            break;
        case 'chat_response':
            appendChatMessage('assistant', data.text);
            break;
    }
}

function updateConnectionStatus(connected) {
    const dot = document.querySelector('.status-dot');
    const text = document.querySelector('.status-text');
    
    if (connected) {
        dot.classList.remove('disconnected');
        text.textContent = 'Подключено';
    } else {
        dot.classList.add('disconnected');
        text.textContent = 'Переподключение...';
    }
}

// ============================================================
// API-КЛИЕНТ
// ============================================================
async function apiGet(url) {
    const response = await fetch(`/api${url}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function apiPost(url, body = {}) {
    const response = await fetch(`/api${url}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function apiPut(url, body = {}) {
    const response = await fetch(`/api${url}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

async function apiDelete(url) {
    const response = await fetch(`/api${url}`, { method: 'DELETE' });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

// ============================================================
// ОБЩИЕ ФУНКЦИИ
// ============================================================
function formatDate(isoString) {
    const d = new Date(isoString);
    return d.toLocaleString('ru-RU');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}