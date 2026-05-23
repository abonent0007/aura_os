// backups.js — Управление бекапами AURA OS

async function initBackups() {
    await loadBackups();
}

async function loadBackups() {
    try {
        const res = await fetch('/api/backups');
        const data = await res.json();
        const container = document.getElementById('backupList');
        if (!container) return;

        if (!data.backups?.length) {
            container.innerHTML = '<p>Нет бекапов</p>';
            return;
        }

        container.innerHTML = data.backups.map(b => `
            <div class="skill-card">
                <div class="skill-header">
                    <span class="skill-name">${b.id}</span>
                    <span>${b.is_automatic ? '🤖 Авто' : '👤 Вручную'}</span>
                </div>
                <div class="skill-description">
                    📅 ${b.timestamp}<br>
                    Причина: ${b.reason || '—'}<br>
                    Файлов: ${b.files_count || 0}
                </div>
                <div class="skill-actions">
                    <button onclick="rollbackTo('${b.id}')" class="btn btn-sm">Откатить</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Backups error:', e);
    }
}

async function createBackup() {
    try {
        const res = await fetch('/api/backups/create', { method: 'POST' });
        const data = await res.json();
        if (data.status === 'ok') await loadBackups();
    } catch (e) {
        alert('Ошибка создания бекапа');
    }
}

async function rollbackTo(backupId) {
    if (!confirm(`Откатить к ${backupId}?`)) return;
    try {
        const res = await fetch('/api/backups/rollback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ backup_id: backupId })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            alert('Откат выполнен. Перезагрузка...');
            location.reload();
        }
    } catch (e) {
        alert('Ошибка отката');
    }
}

document.addEventListener('DOMContentLoaded', initBackups);
