// settings.js — Настройки AURA OS

let timezones = [];

async function initSettings() {
    await loadTimezones();
    await loadSettings();
}

async function loadTimezones() {
    try {
        const res = await fetch('/api/timezones');
        const data = await res.json();
        timezones = data.timezones || [];
    } catch (e) { console.error('Timezones:', e); }
}

async function loadSettings() {
    try {
        const res = await fetch('/api/config');
        const config = await res.json();
        const container = document.getElementById('settingsContainer');
        if (!container) return;

        container.innerHTML = '';

        // === РЕДАКТИРУЕМЫЕ НАСТРОЙКИ ===
        container.appendChild(buildBriefingSection(config));
        container.appendChild(buildTriggersSection('Триггеры памяти', 'memory.memory_search.triggers_past', config.memory?.memory_search?.triggers_past || [], 'Слова для поиска в истории: «напомни», «вспомни», «проект»...'));
        container.appendChild(buildTriggersSection('Триггеры интернет-поиска', 'web_search.triggers.search', config.web_search?.triggers?.search || [], 'Фразы: «найди в интернете», «сколько стоит»...'));
        container.appendChild(buildTriggersSection('Триггеры новостей', 'web_search.triggers.news', config.web_search?.triggers?.news || [], 'Фразы: «что нового», «свежие новости»...'));
        container.appendChild(buildTriggersSection('Триггеры погоды', 'web_search.triggers.weather', config.web_search?.triggers?.weather || [], 'Фразы: «погода», «брать зонт»...'));
        container.appendChild(buildTextSection('Город для погоды', 'web_search.weather.default_city', config.web_search?.weather?.default_city || 'Moscow', 'Город по умолчанию для прогноза'));
        container.appendChild(buildTimezoneSection('Часовой пояс', 'briefing.timezone', config.briefing?.timezone || 'Europe/Moscow'));

        // === ВСЕ ОСТАЛЬНЫЕ НАСТРОЙКИ (только чтение) ===
        container.appendChild(buildAllConfig(config));

    } catch (e) { console.error('Settings:', e); }
}

// ── Редактируемые секции ──

function buildBriefingSection(config) {
    const div = document.createElement('div');
    div.className = 'settings-group';
    div.innerHTML = '<h3>Ежедневный брифинг</h3>';
    const time = config.briefing?.time || '09:00';
    div.innerHTML += `
        <div class="setting-row">
            <div><div class="setting-label">Время брифинга</div>
            <div class="setting-description">Во сколько Аура присылает утренний брифинг</div></div>
            <div class="setting-value">
                <input type="time" id="cfg-briefing-time" value="${time}" style="width:120px">
                <button class="btn btn-sm btn-primary" onclick="applySetting('briefing','time',document.getElementById('cfg-briefing-time').value)">Применить</button>
            </div>
        </div>
    `;
    return div;
}

function buildTriggersSection(title, key, values, desc) {
    const div = document.createElement('div');
    div.className = 'settings-group';
    const text = Array.isArray(values) ? values.join(', ') : values;
    const id = 'cfg-' + key.replace(/\./g, '-');
    div.innerHTML = `
        <h3>${title}</h3>
        <div class="setting-description" style="margin-bottom:8px">${desc}</div>
        <div style="display:flex;gap:8px">
            <textarea id="${id}" style="flex:1;background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);padding:8px;font-size:13px;resize:vertical;min-height:50px;font-family:inherit">${escapeHtml(text)}</textarea>
            <button class="btn btn-sm btn-primary" style="align-self:flex-start" onclick="applyTriggers('${key}','${id}')">Применить</button>
        </div>
    `;
    return div;
}

function buildTextSection(title, key, value, desc) {
    const div = document.createElement('div');
    div.className = 'settings-group';
    const id = 'cfg-' + key.replace(/\./g, '-');
    div.innerHTML = `
        <h3>${title}</h3>
        <div class="setting-description" style="margin-bottom:8px">${desc}</div>
        <div style="display:flex;gap:8px">
            <input type="text" id="${id}" value="${escapeHtml(String(value))}" style="flex:1;max-width:400px;background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);padding:8px 12px;font-size:14px">
            <button class="btn btn-sm btn-primary" onclick="applySettingSimple('${key}','${id}')">Применить</button>
        </div>
    `;
    return div;
}

function buildTimezoneSection(title, key, currentValue) {
    const div = document.createElement('div');
    div.className = 'settings-group';
    const id = 'cfg-' + key.replace(/\./g, '-');
    let options = timezones.map(tz =>
        `<option value="${tz.value}" ${tz.value === currentValue ? 'selected' : ''}>${tz.label}</option>`
    ).join('');
    div.innerHTML = `
        <h3>${title}</h3>
        <div class="setting-description" style="margin-bottom:8px">Для брифинга и расписания</div>
        <div style="display:flex;gap:8px">
            <select id="${id}" style="background:var(--bg-secondary);border:1px solid var(--border);border-radius:var(--radius-sm);color:var(--text-primary);padding:8px 12px;font-size:14px;min-width:280px">${options}</select>
            <button class="btn btn-sm btn-primary" onclick="applySettingSimple('${key}','${id}')">Применить</button>
        </div>
    `;
    return div;
}

// ── Все настройки (только чтение) ──

function buildAllConfig(config) {
    const div = document.createElement('div');
    div.innerHTML = '<hr style="border-color:var(--border);margin:24px 0"><h2 style="margin-bottom:16px">Все настройки</h2>';

    for (const [section, values] of Object.entries(config)) {
        if (section.startsWith('_') || typeof values !== 'object' || !values) continue;
        const group = document.createElement('div');
        group.className = 'settings-group';
        group.innerHTML = `<h3>${section}</h3>`;
        for (const [key, value] of Object.entries(values)) {
            if (key.startsWith('_')) continue;
            group.appendChild(buildConfigRow(section, key, value));
        }
        div.appendChild(group);
    }
    return div;
}

function buildConfigRow(section, key, value) {
    const row = document.createElement('div');
    row.className = 'setting-row';

    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
        row.innerHTML = `<div><div class="setting-label">${key}</div></div>
            <div class="setting-value" style="color:var(--text-muted);font-size:12px">${JSON.stringify(value).substring(0, 80)}</div>`;
    } else if (Array.isArray(value)) {
        row.innerHTML = `<div><div class="setting-label">${key}</div></div>
            <div class="setting-value" style="color:var(--text-muted);font-size:12px">[${value.length} элементов] ${value.slice(0,3).join(', ')}...</div>`;
    } else if (typeof value === 'boolean') {
        const subkeys = section + '.' + key;
        const id = 'cfg-ro-' + subkeys.replace(/\./g, '-');
        row.innerHTML = `<div><div class="setting-label">${key}</div></div>
            <div class="setting-value">
                <input type="checkbox" id="${id}" ${value ? 'checked' : ''} onchange="applySetting('${section}','${key}',this.checked)">
            </div>`;
    } else if (typeof value === 'number') {
        row.innerHTML = `<div><div class="setting-label">${key}</div></div>
            <div class="setting-value" style="color:var(--text-muted);font-size:13px">${value}</div>`;
    } else {
        row.innerHTML = `<div><div class="setting-label">${key}</div></div>
            <div class="setting-value" style="color:var(--text-muted);font-size:13px">${escapeHtml(String(value ?? 'null'))}</div>`;
    }
    return row;
}

// ── API ──

async function applySetting(section, key, value) {
    try {
        await fetch('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ section, key, value }) });
        flashMessage('Сохранено');
    } catch (e) { flashMessage('Ошибка'); }
}

async function applySettingSimple(fullKey, elementId) {
    const value = document.getElementById(elementId)?.value;
    if (value === undefined) return;
    const parts = fullKey.split('.');
    await applySetting(parts[0], parts.slice(1).join('.'), value);
}

async function applyTriggers(fullKey, elementId) {
    const raw = document.getElementById(elementId)?.value || '';
    const values = raw.split(',').map(s => s.trim()).filter(Boolean);
    const parts = fullKey.split('.');
    try {
        await fetch('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ section: parts[0], key: parts.slice(1).join('.'), value: values }) });
        flashMessage('Сохранено');
    } catch (e) { flashMessage('Ошибка'); }
}

function flashMessage(text) {
    const el = document.createElement('div');
    el.style.cssText = 'position:fixed;bottom:20px;right:20px;background:var(--accent);color:white;padding:10px 20px;border-radius:8px;z-index:999;transition:opacity 0.3s';
    el.textContent = text;
    document.body.appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 2000);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

document.addEventListener('DOMContentLoaded', initSettings);
