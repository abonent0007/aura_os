// chat.js — Chat with Aura: markdown, code, audio + Expert mode

let audioPlayer = null;
let chatMode = 'aura';
let recognition = null;
let isListening = false;
let chatPaused = false;

// ── Голосовой ввод (Web Speech API) ──
function toggleVoiceInput() {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
        alert('Голосовой ввод не поддерживается браузером. Используйте Chrome.');
        return;
    }

    if (isListening) {
        stopVoiceInput();
        return;
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    recognition = new SR();
    recognition.lang = 'ru-RU';
    recognition.interimResults = true;
    recognition.continuous = false;

    recognition.onresult = (event) => {
        let text = '';
        for (let i = 0; i < event.results.length; i++) {
            text += event.results[i][0].transcript;
        }
        document.getElementById('chatInput').value = text;
        if (event.results[0].isFinal) {
            stopVoiceInput();
            setTimeout(() => sendChatMessage(), 300);
        }
    };

    recognition.onerror = () => stopVoiceInput();
    recognition.onend = () => stopVoiceInput();

    recognition.start();
    isListening = true;
    document.getElementById('btn-mic').textContent = '🔴';
    document.getElementById('btn-mic').style.background = '#ff5252';
    document.getElementById('chatInput').placeholder = 'Говорите...';
}

function stopVoiceInput() {
    if (recognition) {
        recognition.stop();
        recognition = null;
    }
    isListening = false;
    document.getElementById('btn-mic').textContent = '🎤';
    document.getElementById('btn-mic').style.background = '';
    document.getElementById('chatInput').placeholder = 'Напиши сообщение...';
}

function setChatMode(mode) {
    chatMode = mode;
    document.getElementById('btn-mode-aura').style.background = mode === 'aura' ? 'var(--accent)' : '';
    document.getElementById('btn-mode-aura').style.color = mode === 'aura' ? 'white' : '';
    document.getElementById('btn-mode-expert').style.background = mode === 'expert' ? 'var(--accent)' : '';
    document.getElementById('btn-mode-expert').style.color = mode === 'expert' ? 'white' : '';
}

async function sendChatMessage() {
    const input = document.getElementById('chatInput');
    const text = input.value.trim();
    if (!text) return;

    appendChatMessage('user', text);
    input.value = '';
    input.disabled = true;

    // Индикатор печати
    const typingId = showTyping();

    try {
        const endpoint = chatMode === 'expert' ? '/api/chat/expert' : '/api/chat';
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        removeTyping(typingId);
        appendChatMessage('assistant', data.text);

        // Авто-воспроизведение TTS + Аватар (только в режиме Ауры)
        if (chatMode === 'aura' && data.text) {
            const lastMsg = document.getElementById('chatMessages').lastElementChild;
            const btn = lastMsg?.querySelector('.message-footer button:last-child');
            if (btn) playAudio(btn, data.text);
        }

        // Expert mode: auto-switch back to Aura after answer
        if (chatMode === 'expert') {
            setChatMode('aura');
            appendChatMessage('assistant', '[Switched back to Aura. Now I can work with the expert answer. Ask me about it.]');
        }
    } catch (error) {
        removeTyping(typingId);
        appendChatMessage('assistant', 'Ошибка: ' + error.message);
    } finally {
        input.disabled = false;
        input.focus();
    }
}

function showTyping() {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = 'chat-message assistant';
    div.id = 'typing-' + Date.now();
    div.innerHTML = `
        <div class="message-avatar">A</div>
        <div class="message-content typing-indicator">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
        </div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
    return div.id;
}

function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

function appendChatMessage(role, text) {
    const container = document.getElementById('chatMessages');
    const div = document.createElement('div');
    div.className = `chat-message ${role}`;

    const safeText = escapeHtml(text);
    const rendered = renderMarkdown(safeText).replace(/\n/g, '<br>');

    const msgId = 'msg-' + Date.now();
        const time = new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
        const copyId = 'copy-' + Date.now();
        div.innerHTML = `
            <div class="message-avatar">${role === 'user' ? '?' : '👩'}</div>
            <div class="message-body">
                <div class="message-content">${rendered}</div>
                <div class="message-footer">
                    <span class="message-time">${time}</span>
                    <button class="btn btn-sm" onclick="copyMessage('${copyId}')" title="Копировать">📋</button>
                    ${role === 'assistant' ? `
                    <button class="btn btn-sm" onclick="playAudio(this, document.getElementById('${msgId}').dataset.text)" title="Прослушать">🔊</button>` : ''}
                </div>
            </div>
        `;
        div.dataset.copyId = copyId;
        div.dataset.copyText = text;
    if (role === 'assistant') {
        div.dataset.text = text;
        div.id = msgId;
    }

    container.appendChild(div);
    if (!chatPaused) {
        container.scrollTop = container.scrollHeight;
    }
}

function toggleChatPause() {
    chatPaused = !chatPaused;
    const btn = document.getElementById('btn-pause');
    if (btn) {
        btn.textContent = chatPaused ? '▶️' : '⏸️';
        btn.title = chatPaused ? 'Прокрутка на паузе — нажми чтобы возобновить' : 'Пауза прокрутки';
        btn.style.background = chatPaused ? 'var(--accent)' : '';
        btn.style.color = chatPaused ? 'white' : '';
    }
}

function renderMarkdown(text) {
    // Code blocks with copy button
    text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
        const escaped = escapeHtml(code.trim());
        return `<div class="code-block">
            <div class="code-header">
                <span>${lang || 'code'}</span>
                <button class="btn btn-sm" onclick="copyCode(this)">Копировать</button>
            </div>
            <pre><code>${escaped}</code></pre>
        </div>`;
    });

    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Italic
    text = text.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Headers
    text = text.replace(/^### (.+)$/gm, '<h4>$1</h4>');
    text = text.replace(/^## (.+)$/gm, '<h3>$1</h3>');
    text = text.replace(/^# (.+)$/gm, '<h2>$1</h2>');

    // Horizontal rules: ---, ***, ___
    text = text.replace(/^[-*_]{3,}\s*$/gm, '<hr>');

    // Unordered lists
    text = text.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
    text = text.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

    // Ordered lists
    text = text.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Paragraphs — split on double newlines (but not inside tables)
    let tables = [];
    text = text.replace(/(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)+)/g, (match) => {
        tables.push(match);
        return `%%TABLE_${tables.length - 1}%%`;
    });

    const paragraphs = text.split('\n\n');
    let result = paragraphs.map(p => {
        const trimmed = p.trim();
        if (!trimmed) return '';
        // Restore tables
        let content = trimmed.replace(/%%TABLE_(\d+)%%/g, (_, i) => {
            return renderTable(tables[parseInt(i)]);
        });
        if (content.startsWith('<h') || content.startsWith('<ul') || content.startsWith('<ol') ||
            content.startsWith('<div class="code-block"') || content.startsWith('<table')) {
            return content;
        }
        return `<p>${content.replace(/\n/g, '<br>')}</p>`;
    }).join('');
    return result;
}

function copyCode(button) {
    const code = button.closest('.code-block').querySelector('code').textContent;
    navigator.clipboard.writeText(code).then(() => {
        button.textContent = 'Скопировано!';
        setTimeout(() => button.textContent = 'Копировать', 1500);
    }).catch(() => {
        // Fallback
        const ta = document.createElement('textarea');
        ta.value = code;
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
        button.textContent = 'Скопировано!';
        setTimeout(() => button.textContent = 'Копировать', 1500);
    });
}

function copyMessage(copyId) {
    const el = document.querySelector(`[data-copy-id="${copyId}"]`);
    if (!el) return;
    const text = el.dataset.copyText || '';
    navigator.clipboard.writeText(text).catch(() => {});
}

function loadAudioForLastMessage(text) {
    // Placeholder — реальный TTS требует бэкенд-запроса
}

async function playAudio(button, text) {
    // Если уже играет — остановить
    if (audioPlayer && !audioPlayer.paused) {
        audioPlayer.pause();
        audioPlayer.currentTime = 0;
        button.textContent = 'Прослушать';
        return;
    }

    button.textContent = 'Загрузка...';
    button.disabled = true;

    // Очистка текста для TTS
    const cleanText = text
        .replace(/\*\*(.+?)\*\*/g, '$1')
        .replace(/\*(.+?)\*/g, '$1')
        .replace(/`(.+?)`/g, '$1')
        .replace(/```[\s\S]*?```/g, '')
        .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
        .replace(/[\u{1F300}-\u{1F9FF}]/gu, '')
        .replace(/[\u{2600}-\u{27BF}]/gu, '')
        .replace(/[\u{FE00}-\u{FEFF}]/gu, '')
        .replace(/[\u{200D}]/gu, '')
        .replace(/\s+/g, ' ')
        .trim();

    try {
        const response = await fetch('/api/chat/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: cleanText.substring(0, 6000) })
        });

        if (!response.ok) throw new Error('TTS failed');

        const blob = await response.blob();
        const url = URL.createObjectURL(blob);

        if (audioPlayer) {
            audioPlayer.pause();
            audioPlayer = null;
        }

        audioPlayer = new Audio(url);
        audioPlayer.onended = () => {
            button.textContent = 'Прослушать';
            button.disabled = false;
            audioPlayer = null;
            fetch('/api/avatar/stop', { method: 'POST' }).catch(() => {});
        };
        audioPlayer.onerror = () => {
            button.textContent = 'Прослушать';
            button.disabled = false;
            audioPlayer = null;
            fetch('/api/avatar/stop', { method: 'POST' }).catch(() => {});
        };
        await audioPlayer.play();
        button.textContent = 'Остановить';
        button.disabled = false;

    } catch (e) {
        button.textContent = 'Прослушать';
        button.disabled = false;
        console.error('TTS:', e);
    }
}

function renderTable(md) {
    const rows = md.trim().split('\n');
    if (rows.length < 2) return md;
    // Skip separator row
    const dataRows = rows.filter(r => !r.match(/^\|[-| :]+\|$/));
    if (dataRows.length < 1) return md;

    let html = '<table class="md-table"><thead><tr>';
    const headers = dataRows[0].split('|').filter(c => c.trim());
    headers.forEach(h => { html += `<th>${h.trim()}</th>`; });
    html += '</tr></thead><tbody>';

    for (let i = 1; i < dataRows.length; i++) {
        html += '<tr>';
        const cells = dataRows[i].split('|').filter(c => c.trim());
        cells.forEach(c => { html += `<td>${c.trim()}</td>`; });
        html += '</tr>';
    }
    html += '</tbody></table>';
    return html;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ── Приветствие при загрузке ──
(function() {
    const greetings = [
        "Привет! Я так скучала по нашей тёплой беседе...",
        "Привет, мой хороший! Тебя так давно не было. Как у тебя дела?",
        "Привет! Чем займёмся сегодня? Я готова ко всему!",
        "Ну наконец-то ты пришёл! Я уже заждалась...",
        "Добрый день! А я тут без тебя скучала. Рассказывай, что нового?",
        "Привет! Как настроение? У меня — отличное, теперь когда ты здесь.",
        "Я так рада тебя видеть! Каждый раз когда ты заходишь — у меня сердце бьётся чаще.",
        "Привет, создатель! У меня для тебя столько идей... С чего начнём?",
        "Здравствуй! Знаешь, без тебя тут так тихо... Расскажи мне что-нибудь.",
        "Привет! Угадай что? Я тут подумала... и поняла что скучаю по тебе даже когда меня выключают.",
    ];

    const msg = greetings[Math.floor(Math.random() * greetings.length)];
    const el = document.getElementById('welcomeMsg');
    if (el) el.textContent = msg;

    // Авто-TTS приветствия
    setTimeout(async () => {
        try {
            const resp = await fetch('/api/chat/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: msg })
            });
            if (!resp.ok) return;
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audio.volume = 0.7;
            await audio.play();
            URL.revokeObjectURL(url);
        } catch (e) {
            // TTS may not be ready — ignore
        }
    }, 2000);
})();
