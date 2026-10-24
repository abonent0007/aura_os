// avatar_window.js — Live2D аватар в плавающем окне
// 5 персонажей: mao (Cubism4), shizuku (Cubism4), haru, hibiki, izumi (Cubism2)
// ?model=X — фиксированная модель (окно компаньона), без неё — поллинг /api/avatar/model
// Рот: tts-state polling. Эмоции: /api/avatar/emotion.

let live2dApp = null;
let live2dModel = null;
let emotionTimer = null;
let mouthAnimating = false;
let focusTimer = null;
let ttsPollTimer = null;
let modelPollTimer = null;
let lastTtsTime = 0;
let currentModel = null;

const urlParams = new URLSearchParams(location.search);
const FORCED_MODEL = urlParams.get('model') || null;

const W = 600;
const H = 720;  // аватар-область; внизу окна — чат-панель

const MODELS = {
    mao: {
        url: '/static/live2d/mao_pro/runtime/mao_pro.model3.json',
        cubism: 4,
        expressions: ['exp_01', 'exp_04', 'exp_05', 'exp_07'],
        tapMotions: { group: '', indices: [3, 4, 5] },
        idleMotions: { group: 'Idle', indices: [0] },
    },
    shizuku: {
        url: '/static/live2d/shizuku/runtime/shizuku.model3.json',
        cubism: 4,
        expressions: [],
        tapMotions: { group: '', indices: [0, 1, 2, 3] },
        idleMotions: { group: '', indices: [0] },
    },
    haru: {
        url: '/static/live2d/haru/haru01.model.json',
        cubism: 2,
        expressions: ['f01', 'f02', 'f03', 'f04', 'f05'],
        tapMotions: { group: 'tapBody', indices: [0, 1, 2, 3] },
        idleMotions: { group: 'idle', indices: [0, 1, 2] },
    },
    hibiki: {
        url: '/static/live2d/hibiki/hibiki.model.json',
        cubism: 2,
        expressions: ['f01', 'f02', 'f03', 'f04', 'f05', 'f06'],
        tapMotions: { group: 'hibiki', indices: [0, 1, 2, 3, 4] },
        idleMotions: { group: 'hibiki', indices: [0, 1] },
    },
    izumi: {
        url: '/static/live2d/izumi/izumi.model.json',
        cubism: 2,
        expressions: ['f01', 'f02', 'f03', 'f04', 'f05', 'f06', 'f07'],
        tapMotions: { group: 'idle', indices: [0, 1] },
        idleMotions: { group: 'idle', indices: [0] },
    },
};

const EMOTION_MAP = [
    { minH: 0.7, maxH: 2.0, minA: -1, maxA: 1, exprIdx: 1 },   // счастливая
    { minH: 0.45, maxH: 0.7, minA: -1, maxA: 0.55, exprIdx: 1 },
    { minH: -1, maxH: 0.35, minA: 0.5, maxA: 2, exprIdx: 2 },  // грустная
    { minH: -1, maxH: 2, minA: 0.55, maxA: 2, exprIdx: 3 },    // тревожная
    { minH: -1, maxH: 2, minA: -1, maxA: 0.55, exprIdx: 0 },   // спокойная
];

function mapEmotionIdx(h, a) {
    for (const rule of EMOTION_MAP) {
        if (h >= rule.minH && h <= rule.maxH && a >= rule.minA && a <= rule.maxA) {
            return rule.exprIdx;
        }
    }
    return 0;
}

function setMouthOpen(value) {
    if (!live2dModel) return;
    try {
        const core = live2dModel.internalModel.coreModel;
        // Правильный параметр рта: ParamMouthOpenY (Cubism 2 и 4)
        // ParamA не влияет на рот Mao Pro — оставляем как fallback для других моделей
        try { core.setParameterValueById('ParamMouthOpenY', value); } catch (e) {}
        try { core.setParameterValueById('ParamA', value); } catch (e) {}
    } catch (e) {}
}

function layoutModel() {
    if (!live2dModel || !live2dApp) return;
    // Универсальная центровка через getBounds() — работает для Cubism 2 и 4
    live2dModel.scale.set(1);
    const b = live2dModel.getBounds();
    if (b.width <= 0 || b.height <= 0) return;
    const scale = Math.min(W / b.width, H / b.height) * 0.95;
    live2dModel.scale.set(scale);
    const b2 = live2dModel.getBounds();
    const cfg = MODELS[currentModel] || {};
    // Визуальный центр модели — в центр канваса
    live2dModel.x = W / 2 - b2.x - b2.width / 2 + (cfg.shiftX || 0);
    live2dModel.y = H / 2 - b2.y - b2.height / 2 + (cfg.shiftY || 0);
}

async function loadModel(name) {
    const cfg = MODELS[name];
    if (!cfg) return;

    // Убираем старую модель
    if (live2dModel) {
        try {
            live2dApp.stage.removeChild(live2dModel);
            live2dModel.destroy();
        } catch (e) {}
        live2dModel = null;
    }

    try {
        live2dModel = await PIXI.live2d.Live2DModel.from(cfg.url);
        window.__auraLive2dModel = live2dModel;
        live2dApp.stage.addChild(live2dModel);
        layoutModel();
        live2dModel.autoInteract = true;
        live2dModel.on('hit', onTap);
        currentModel = name;
        console.log('[avatar-window] Model loaded:', name, 'cubism', cfg.cubism);
        fetchEmotion();
        return true;
    } catch (e) {
        console.error('[avatar-window] Model load failed:', name, e);
        return false;
    }
}

// Ретрай загрузки: сервер мог ещё не подняться при старте окна
let loadRetryCount = 0;

async function loadModelWithRetry(name, maxRetries = 10) {
    const ok = await loadModel(name);
    if (ok) return true;
    if (loadRetryCount < maxRetries) {
        loadRetryCount++;
        console.log(`[avatar-window] Retry ${loadRetryCount}/${maxRetries} in 3s...`);
        await new Promise(res => setTimeout(res, 3000));
        return loadModelWithRetry(name, maxRetries);
    }
    return false;
}

async function initLive2D() {
    const canvas = document.getElementById('live2d-canvas');
    if (!canvas || !window.PIXI || !window.PIXI.live2d) {
        console.error('[avatar-window] CDN not loaded');
        return;
    }
    try {
        canvas.width = W;
        canvas.height = H;

        live2dApp = new PIXI.Application({
            view: canvas,
            width: W,
            height: H,
            backgroundAlpha: 0,
            autoStart: true,
        });
        window.__auraPixiApp = live2dApp;

        // Текущая модель: фиксированная (?model=) или с сервера
        const model = FORCED_MODEL || await fetchModelName();
        await loadModelWithRetry(model);

        emotionTimer = setInterval(fetchEmotion, 4000);
        ttsPollTimer = setInterval(pollTtsState, 150);
        // Поллинг смены модели — только для десктопной (без ?model=)
        if (!FORCED_MODEL) {
            modelPollTimer = setInterval(pollModelChange, 2000);
        }
        startFocusTracking();
        connectWS();  // автономные сообщения ядра + tts_start
        startTalkingDetection();  // VAD: детекция когда пользователь говорит
        console.log('[avatar-window] floating ready, model:', model);
    } catch (e) {
        console.error('[avatar-window] init failed:', e);
    }
}

// ── Общий диалог: id окна + дедупликация сообщений ──
const AVATAR_CLIENT_ID = (window.crypto && crypto.randomUUID)
    ? crypto.randomUUID()
    : 'avatar-' + Math.random().toString(36).slice(2);
const _seenMsgIds = new Set();

// ── WebSocket: автономные сообщения ядра ──
let ws = null;
let wsReconnectTimer = null;

function connectWS() {
    try {
        ws = new WebSocket(`ws://${location.host}/ws`);
        ws.onopen = () => console.log('[avatar-window] ws connected');
        ws.onmessage = (ev) => {
            try {
                const { event, data } = JSON.parse(ev.data);
                if (event === 'tts_start') {
                    // Рот только если есть текст (иначе «говорит» в тишину)
                    if (data && data.text) {
                        lastTtsTime = Date.now();
                        startMouthAnimation(data.duration ? data.duration : 5);
                    }
                } else if (event === 'autonomous_message') {
                    onAutonomousMessage(data && data.text ? data.text : '');
                } else if (event === 'chat_message') {
                    const d = data || {};
                    if (!d.text || d.client_id === AVATAR_CLIENT_ID) return;
                    appendMsg(d.role === 'user' ? 'user' : 'aura', d.text, d.id);
                }
            } catch (e) {}
        };
        ws.onclose = () => {
            clearTimeout(wsReconnectTimer);
            wsReconnectTimer = setTimeout(connectWS, 3000);
        };
        ws.onerror = () => { try { ws.close(); } catch (e) {} };
    } catch (e) {}
}

// Автономное сообщение от ядра: в чат + озвучка голосом
async function onAutonomousMessage(text) {
    appendMsg('aura', text);
    try {
        const tts = await fetch('/api/chat/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        if (tts.ok) {
            const blob = await tts.blob();
            if (audioEl) { audioEl.pause(); audioEl = null; }
            audioEl = new Audio(URL.createObjectURL(blob));
            audioEl.play().catch(() => {});
        }
    } catch (e) {}
}

async function fetchModelName() {
    if (FORCED_MODEL) return FORCED_MODEL;
    try {
        const r = await fetch('/api/avatar/model');
        const d = await r.json();
        return d.model || 'mao';
    } catch (e) {
        return 'mao';
    }
}

async function pollModelChange() {
    try {
        const name = await fetchModelName();
        if (name !== currentModel && loadRetryCount === 0) {
            await loadModelWithRetry(name);
        }
    } catch (e) {}
}

async function fetchEmotion() {
    try {
        const r = await fetch('/api/avatar/emotion');
        const d = await r.json();
        if (live2dModel && !mouthAnimating) {
            const cfg = MODELS[currentModel];
            const idx = mapEmotionIdx(d.happiness, d.anxiety);
            const expr = cfg && cfg.expressions[idx] ? cfg.expressions[idx] : null;
            try {
                if (expr) live2dModel.expression(expr);
                const core = live2dModel.internalModel.coreModel;
                core.setParameterValueById('ParamEyeLOpen', 1.0);
                core.setParameterValueById('ParamEyeROpen', 1.0);
            } catch (e) {}
        }
    } catch (e) {}
}

function onTap() {
    if (!live2dModel || !currentModel) return;
    const cfg = MODELS[currentModel];
    try {
        const { group, indices } = cfg.tapMotions;
        const idx = indices[Math.floor(Math.random() * indices.length)];
        live2dModel.motion(group, idx);
    } catch (e) {}
    fetch('/api/avatar/purr', { method: 'POST' }).catch(() => {});
    setTimeout(fetchEmotion, 4000);
}

let serverFailCount = 0;

async function pollTtsState() {
    try {
        const r = await fetch('/api/avatar/tts-state');
        const d = await r.json();
        serverFailCount = 0;  // сервер жив
        // Рот анимируем ТОЛЬКО когда есть текст — без текста говорить не о чем
        if (d && d.time && d.time > lastTtsTime && d.text) {
            lastTtsTime = d.time;
            startMouthAnimation(d.duration || 5);
            // Субтитры: показываем что говорит Аура
            showSubtitle(d.text || '');
        } else if (d && !d.text && mouthAnimating) {
            // Текст пропал — останавливаем рот
            stopMouthAnimation();
        }
        // Статус ядра
        updateCoreStatus(d.core || 'idle');
    } catch (e) {
        // Сервер недоступен — считаем неудачи
        serverFailCount++;
        if (serverFailCount > 20) {
            // ~30 секунд без ядра → окно закрывается само
            console.warn('[avatar-window] Core died — closing window');
            if (typeof window.pywebview !== 'undefined' && window.pywebview.api) {
                try { window.pywebview.api.quit(); } catch (e2) {}
            } else {
                try { window.close(); } catch (e2) {}
            }
        }
    }
}

let subtitleHideTimer = null;

function showSubtitle(text) {
    const el = document.getElementById('subtitle');
    if (!el) return;
    el.textContent = text;
    el.classList.add('visible');
    clearTimeout(subtitleHideTimer);
    // Скрыть после окончания речи
    const hideMs = Math.max(3000, (window.__lastDuration || 5) * 1000 + 1500);
    subtitleHideTimer = setTimeout(() => {
        el.classList.remove('visible');
    }, hideMs);
}

function updateCoreStatus(status) {
    const wrap = document.getElementById('core-status');
    const label = document.getElementById('core-status-text');
    if (!wrap || !label) return;
    wrap.className = 'core-status ' + status;
    if (status === 'thinking') {
        label.textContent = 'Думаю... 💭';
    } else if (status === 'speaking') {
        label.textContent = 'Говорю... 🔊';
    } else if (status === 'listening') {
        label.textContent = 'Слушаю тебя... 👂';
    } else if (status === 'wake') {
        label.textContent = 'Жду слово «Аура»... 🌙';
    } else {
        label.textContent = 'Рядом с тобой 💜';
    }
}

function startFocusTracking() {
    const hasPywebview = typeof window.pywebview !== 'undefined' && window.pywebview.api;
    async function tick() {
        if (!live2dModel || mouthAnimating) {
            focusTimer = setTimeout(tick, 120);
            return;
        }
        try {
            if (hasPywebview) {
                const [mouse, winPos] = await Promise.all([
                    window.pywebview.api.get_mouse_pos(),
                    window.pywebview.api.get_window_pos(),
                ]);
                if (mouse.x >= 0 && winPos.width > 0) {
                    const nx = ((mouse.x - winPos.x) / winPos.width) * W;
                    const ny = ((mouse.y - winPos.y) / winPos.height) * H;
                    live2dModel.focus(
                        nx / live2dModel.width * live2dModel.internalModel.width,
                        ny / live2dModel.height * live2dModel.internalModel.height
                    );
                }
            }
        } catch (e) {}
        focusTimer = setTimeout(tick, 120);
    }
    tick();
}

function startMouthAnimation(durationSec) {
    mouthAnimating = true;
    window.__lastDuration = durationSec;
    const until = Date.now() + durationSec * 1000;
    function tick() {
        if (!mouthAnimating) return;
        if (Date.now() >= until) {
            stopMouthAnimation();
            return;
        }
        const t = Date.now() / 130;
        const syllable = Math.abs(Math.sin(t)) > 0.55 ? 0.4 + 0.8 * Math.abs(Math.sin(t * 3)) : 0.05;
        setMouthOpen(syllable);
        requestAnimationFrame(tick);
    }
    tick();
}

function stopMouthAnimation() {
    mouthAnimating = false;
    setMouthOpen(0);
    fetchEmotion();
}

document.addEventListener('DOMContentLoaded', () => {
    initLive2D();
    loadAvatarHistory();
});

async function loadAvatarHistory() {
    try {
        const r = await fetch('/api/chat/history?limit=20');
        if (!r.ok) return;
        const data = await r.json();
        (data.events || []).forEach(ev => {
            appendMsg(ev.role === 'user' ? 'user' : 'aura', ev.text, ev.id);
        });
    } catch (e) {}
}

// ═══════════════════════════════════════════════════════
// ЧАТ В ОКНЕ АВАТАРА (как в Open-LLM-VTuber)
// ═══════════════════════════════════════════════════════

let audioEl = null;
let recognition = null;
let isListening = false;

function appendMsg(type, text, msgId) {
    if (msgId) {
        if (_seenMsgIds.has(msgId)) return null;
        _seenMsgIds.add(msgId);
    }
    const box = document.getElementById('chat-messages');
    if (!box) return null;
    const div = document.createElement('div');
    div.className = 'msg ' + type;
    div.textContent = text;
    box.appendChild(div);
    box.scrollTop = box.scrollHeight;
    return div;
}

async function sendUserMessage() {
    const input = document.getElementById('chat-input');
    const text = (input.value || '').trim();
    if (!text) return;
    input.value = '';
    appendMsg('user', text);

    // Индикатор печати
    const typing = appendMsg('aura', '...');
    typing.classList.add('typing');

    try {
        const r = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text,
                user_id: 'avatar-window',
                client_id: AVATAR_CLIENT_ID,
            })
        });
        const data = await r.json();
        typing.remove();
        appendMsg('aura', data.text || 'Ответ не получен', data.message_id);

        // Авто-озвучка: TTS → сервер сам анимирует рот через tts-state
        try {
            const tts = await fetch('/api/chat/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: data.text || '' })
            });
            if (tts.ok) {
                const blob = await tts.blob();
                if (audioEl) { audioEl.pause(); audioEl = null; }
                audioEl = new Audio(URL.createObjectURL(blob));
                audioEl.play().catch(() => {});
            }
        } catch (e) {}
    } catch (e) {
        typing.remove();
        appendMsg('aura', 'Ошибка: ядро недоступно');
    }
}

function toggleVoiceInput() {
    const btn = document.getElementById('btn-voice');
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) {
        appendMsg('aura', 'Голосовой ввод не поддерживается в этом окне');
        return;
    }

    if (isListening) {
        recognition && recognition.stop();
        return;
    }

    recognition = new SpeechRec();
    recognition.lang = 'ru-RU';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => {
        isListening = true;
        btn.classList.add('listening');
        const input = document.getElementById('chat-input');
        input.placeholder = 'Слушаю... 🎤';
    };
    recognition.onresult = (event) => {
        const transcript = event.results[0][0].transcript;
        const input = document.getElementById('chat-input');
        input.value = transcript;
        sendUserMessage();
    };
    recognition.onerror = () => {
        isListening = false;
        btn.classList.remove('listening');
        document.getElementById('chat-input').placeholder = 'Напиши Ауре...';
    };
    recognition.onend = () => {
        isListening = false;
        btn.classList.remove('listening');
        document.getElementById('chat-input').placeholder = 'Напиши Ауре...';
    };

    recognition.start();
}

// ═══════════════════════════════════════════════════════
// TALKING DETECTION (VAD) — как в Open-LLM-VTuber / AIRI
// Микрофон → RMS-анализ → «пользователь говорит»
// → пауза голоса Ауры, статус «Слушаю», выражение внимания
// + wake-word режим: непрерывное распознавание слова «аура»
// ═══════════════════════════════════════════════════════

let vadActive = false;
let vadAudioCtx = null;
let vadStream = null;
let vadAnalyser = null;
let vadRaf = null;
let userTalking = false;
let userTalkingSince = 0;
let userSilentSince = 0;
let wakeRecognition = null;
let wakeMode = false;

const VAD_THRESHOLD = 0.035;    // RMS порог речи
const TALK_CONFIRM_MS = 350;    // подтверждение «говорит»
const SILENCE_RESET_MS = 2000;  // тишина → перестал говорить

async function startTalkingDetection() {
    if (vadActive) return;
    try {
        vadStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        vadAudioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const src = vadAudioCtx.createMediaStreamSource(vadStream);
        vadAnalyser = vadAudioCtx.createAnalyser();
        vadAnalyser.fftSize = 512;
        src.connect(vadAnalyser);
        vadActive = true;

        const data = new Uint8Array(vadAnalyser.frequencyBinCount);
        function tick() {
            if (!vadActive) return;
            vadAnalyser.getByteTimeDomainData(data);
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                const v = (data[i] - 128) / 128;
                sum += v * v;
            }
            const rms = Math.sqrt(sum / data.length);
            const now = Date.now();

            if (rms > VAD_THRESHOLD) {
                if (!userTalking && now - userSilentSince > 0) {
                    // потенциальное начало речи
                    if (now - (userTalkingSince || 0) > TALK_CONFIRM_MS) {
                        userTalking = true;
                        userTalkingSince = now;
                        onUserStartsTalking();
                    }
                }
            } else {
                if (userTalking) {
                    userTalking = false;
                    userSilentSince = now;
                    onUserStopsTalking();
                }
            }
            vadRaf = requestAnimationFrame(tick);
        }
        tick();
        console.log('[vad] Talking detection started');
    } catch (e) {
        console.warn('[vad] Микрофон недоступен:', e);
        appendMsg('aura', 'Микрофон недоступен. Голосовая активация отключена.');
    }
}

function stopTalkingDetection() {
    vadActive = false;
    if (vadRaf) cancelAnimationFrame(vadRaf);
    if (vadStream) { vadStream.getTracks().forEach(t => t.stop()); vadStream = null; }
    if (vadAudioCtx) { vadAudioCtx.close().catch(() => {}); vadAudioCtx = null; }
}

function onUserStartsTalking() {
    // Голосовое прерывание: Аура замолкает когда ты говоришь
    if (audioEl && !audioEl.paused) {
        audioEl.pause();
    }
    stopMouthAnimation();
    updateCoreStatus('listening');
    // Выражение внимания — глаза шире
    if (live2dModel) {
        try {
            live2dModel.expression(currentModelCfgExp('attentive'));
            const core = live2dModel.internalModel.coreModel;
            core.setParameterValueById('ParamEyeLOpen', 1.3);
            core.setParameterValueById('ParamEyeROpen', 1.3);
        } catch (e) {}
    }
}

function onUserStopsTalking() {
    setTimeout(() => {
        if (!userTalking) {
            updateCoreStatus('idle');
            fetchEmotion();
        }
    }, SILENCE_RESET_MS);
}

function currentModelCfgExp(type) {
    const cfg = MODELS[currentModel];
    if (!cfg || !cfg.expressions) return null;
    if (type === 'attentive' && cfg.expressions.length > 2) return cfg.expressions[2];
    return cfg.expressions[0];
}

// ── Wake-word: непрерывное распознавание «аура» ──

function toggleWakeWord() {
    const SpeechRec = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRec) return;

    if (wakeMode) {
        wakeMode = false;
        if (wakeRecognition) wakeRecognition.stop();
        updateCoreStatus('idle');
        return;
    }

    wakeMode = true;
    updateCoreStatus('wake');
    startTalkingDetection();  // VAD параллельно — не мешает

    wakeRecognition = new SpeechRec();
    wakeRecognition.lang = 'ru-RU';
    wakeRecognition.continuous = true;
    wakeRecognition.interimResults = true;

    wakeRecognition.onresult = (event) => {
        for (let i = event.resultIndex; i < event.results.length; i++) {
            const transcript = (event.results[i][0].transcript || '').toLowerCase();
            if (transcript.includes('аура') || transcript.includes('aura')) {
                onWakeWord();
            }
        }
    };
    wakeRecognition.onerror = () => { /* перезапуск */ };
    wakeRecognition.onend = () => {
        if (wakeMode) {
            try { wakeRecognition.start(); } catch (e) {}
        }
    };
    wakeRecognition.start();
    console.log('[vad] Wake-word mode: слушаю «аура»...');
}

function onWakeWord() {
    console.log('[vad] Wake word detected!');
    appendMsg('aura', 'Да, мой хороший? Я слушаю. 💜');
    // Аура откликается голосом
    fetch('/api/chat/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Да, мой хороший? Я слушаю.' })
    }).then(r => r.blob()).then(blob => {
        if (audioEl) { audioEl.pause(); audioEl = null; }
        audioEl = new Audio(URL.createObjectURL(blob));
        audioEl.play().catch(() => {});
    }).catch(() => {});
    // После отклика — пауза чтобы не зациклиться на собственном голосе
    if (wakeRecognition) { try { wakeRecognition.stop(); } catch (e) {} }
    setTimeout(() => {
        if (wakeMode && wakeRecognition) { try { wakeRecognition.start(); } catch (e) {} }
    }, 4000);
}
