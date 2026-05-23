// chat.js — Chat with Aura: markdown, code, audio + Expert mode

let audioPlayer = null;
let chatMode = 'aura';
let recognition = null;
let isListening = false;

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
        if (chatMode === 'aura' && data.text && data.text.length < 2000) {
            const lastMsg = document.getElementById('chatMessages').lastElementChild;
            const btn = lastMsg?.querySelector('.audio-player button');
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

    const rendered = role === 'assistant' ? renderMarkdown(text) : escapeHtml(text);

    const msgId = 'msg-' + Date.now();
    div.innerHTML = `
        <div class="message-avatar">${role === 'user' ? '?' : '👩'}</div>
        <div class="message-body">
            <div class="message-content">${rendered}</div>
            ${role === 'assistant' ? `
            <div class="audio-player">
                <button class="btn btn-sm" onclick="playAudio(this, document.getElementById('${msgId}').dataset.text)">Прослушать</button>
            </div>` : ''}
        </div>
    `;
    if (role === 'assistant') {
        div.dataset.text = text;
        div.id = msgId;
    }

    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
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

    // Unordered lists
    text = text.replace(/^[*-] (.+)$/gm, '<li>$1</li>');
    text = text.replace(/((?:<li>.*<\/li>\n?)+)/g, '<ul>$1</ul>');

    // Ordered lists
    text = text.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');

    // Links
    text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

    // Paragraphs — split on double newlines
    const paragraphs = text.split('\n\n');
    return paragraphs.map(p => {
        const trimmed = p.trim();
        if (!trimmed) return '';
        if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<div class="code-block"')) {
            return trimmed;
        }
        return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }).join('');
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
            body: JSON.stringify({ text: cleanText.substring(0, 1000) })
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

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
