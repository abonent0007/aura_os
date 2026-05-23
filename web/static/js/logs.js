// logs.js — Просмотр логов AURA OS

async function initLogs() {
    await loadLogs();
    document.getElementById('logLevelFilter')?.addEventListener('change', loadLogs);
}

async function loadLogs() {
    const levelFilter = document.getElementById('logLevelFilter')?.value || '';
    const url = levelFilter ? `/api/logs?level=${levelFilter}&limit=200` : '/api/logs?limit=200';

    try {
        const res = await fetch(url);
        const data = await res.json();
        const container = document.getElementById('logContainer');
        if (!container) return;

        if (!data.logs?.length) {
            container.innerHTML = '<p>Нет записей</p>';
            return;
        }

        container.innerHTML = data.logs.map(log => {
            const levelClass = log.level || 'info';
            const time = new Date(log.timestamp).toLocaleTimeString();
            return `<div class="log-entry">
                <span class="log-time">${time}</span>
                <span class="log-level ${levelClass}">[${log.level?.toUpperCase() || 'INFO'}]</span>
                <span class="log-message">${escapeHtml(log.message || '')}</span>
            </div>`;
        }).join('');
        container.scrollTop = container.scrollHeight;
    } catch (e) {
        console.error('Logs error:', e);
    }
}

async function clearLogs() {
    if (!confirm('Очистить все логи?')) return;
    try {
        await fetch('/api/logs/clear', { method: 'POST' });
        await loadLogs();
    } catch (e) {
        console.error('Clear logs error:', e);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', initLogs);
