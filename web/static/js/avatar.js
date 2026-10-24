// avatar.js — Live2D аватар Ауры (Mao Pro model)
// Фиксированный размер канваса (не зависит от видимости страницы),
// авто-моргание, слежение за курсором, эмоции из aura_soul.db,
// синхронизация рта с TTS, клик-реакции с мурлыканьем.

let live2dApp = null;
let live2dModel = null;
let emotionTimer = null;
let avatarInitialized = false;
let mouthAnimating = false;

const AVATAR_WIDTH = 800;
const AVATAR_HEIGHT = 900;

// Эмоция → выражение модели
const EMOTION_MAP = [
    { minH: 0.7, maxH: 2.0, minA: -1, maxA: 1, expr: 'exp_04', label: 'Счастливая 😊' },
    { minH: 0.45, maxH: 0.7, minA: -1, maxA: 1, expr: 'exp_02', label: 'Улыбается 🙂' },
    { minH: -1, maxH: 0.35, minA: 0.5, maxA: 2, expr: 'exp_05', label: 'Грустит 😢' },
    { minH: -1, maxH: 2, minA: 0.55, maxA: 2, expr: 'exp_07', label: 'Волнуется 😟' },
    { minH: -1, maxH: 2, minA: -1, maxA: 0.55, expr: 'exp_01', label: 'Спокойная 🌙' },
];

const MOOD_LABELS = ['Сонная 😴', 'Спокойная 🌙', 'Бодрая ✨'];

function mapEmotionToExpression(h, a) {
    for (const rule of EMOTION_MAP) {
        if (h >= rule.minH && h <= rule.maxH && a >= rule.minA && a <= rule.maxA) {
            return { expr: rule.expr, label: rule.label };
        }
    }
    return { expr: 'exp_01', label: 'Спокойная 🌙' };
}

function moodLabel(e) {
    if (e < 0.3) return MOOD_LABELS[0];
    if (e < 0.65) return MOOD_LABELS[1];
    return MOOD_LABELS[2];
}

function layoutModel() {
    if (!live2dModel || !live2dApp) return;
    const w = AVATAR_WIDTH;
    const h = AVATAR_HEIGHT;
    const scale = Math.min(w / live2dModel.width, h / live2dModel.height) * 0.85;
    live2dModel.scale.set(scale);
    live2dModel.x = w / 2;
    live2dModel.y = h / 2 + live2dModel.height * scale * 0.05;
}

async function initLive2D() {
    if (avatarInitialized) return;
    if (!window.PIXI || !window.PIXI.live2d) {
        console.error('[avatar] PIXI.live2d не загружен (CDN недоступен?)');
        return;
    }
    avatarInitialized = true;

    const canvas = document.getElementById('live2d-canvas');
    if (!canvas) return;

    try {
        // Фиксированный размер — не зависит от видимости страницы
        canvas.width = AVATAR_WIDTH;
        canvas.height = AVATAR_HEIGHT;

        live2dApp = new PIXI.Application({
            view: canvas,
            width: AVATAR_WIDTH,
            height: AVATAR_HEIGHT,
            autoStart: true,
            backgroundAlpha: 0,
        });
        window.__auraPixiApp = live2dApp; // для отладки

        // Загружаем модель Mao Pro
        live2dModel = await PIXI.live2d.Live2DModel.from(
            '/static/live2d/mao_pro/runtime/mao_pro.model3.json'
        );
        window.__auraLive2dModel = live2dModel;

        live2dApp.stage.addChild(live2dModel);
        layoutModel();

        // Авто-моргание и слежение за курсором
        live2dModel.autoInteract = true;

        // Клик → реакция + мурлыканье
        live2dModel.on('hit', () => onAvatarTap());

        // Стартовое выражение + поллинг эмоций
        fetchEmotion();
        emotionTimer = setInterval(fetchEmotion, 3000);

        console.log('[avatar] Live2D Mao Pro loaded');
    } catch (e) {
        console.error('[avatar] Load failed:', e);
        const hint = document.querySelector('.avatar-hint');
        if (hint) hint.textContent = 'Не удалось загрузить модель: ' + e.message;
    }
}

async function fetchEmotion() {
    try {
        const r = await fetch('/api/avatar/emotion');
        const data = await r.json();
        const { expr, label } = mapEmotionToExpression(data.happiness, data.anxiety);
        if (live2dModel && !mouthAnimating) {
            try { live2dModel.expression(expr); } catch (e) {}
        }
        const el = document.getElementById('avatar-emotion-label');
        if (el) {
            el.textContent = `Настроение: ${label} | ${moodLabel(data.energy)} | ❤${data.happiness.toFixed(1)} 😰${data.anxiety.toFixed(1)} ⚡${data.energy.toFixed(1)}`;
        }
    } catch (e) {
        // API недоступен — тихо игнорируем
    }
}

function onAvatarTap() {
    // Спец-моушен как реакция (группа '' — индексы 3,4,5)
    if (live2dModel) {
        try {
            const idx = 3 + Math.floor(Math.random() * 3);
            live2dModel.motion('', idx);
        } catch (e) {}
    }
    fetch('/api/avatar/purr', { method: 'POST' }).catch(() => {});
    setTimeout(fetchEmotion, 4000);
}

async function avatarSpeak() {
    const text = 'Привет, мой хороший! Я Аура. Рада тебя видеть! Как твои дела?';
    try {
        const r = await fetch('/api/chat/tts', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text })
        });
        if (!r.ok) return;
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        driveMouthWithAudio(audio);
        await audio.play();
    } catch (e) {
        console.error('[avatar] speak failed:', e);
    }
}

function driveMouthWithAudio(audio) {
    mouthAnimating = true;
    try {
        const AudioCtx = window.AudioContext || window.webkitAudioContext;
        const ctx = new AudioCtx();
        const src = ctx.createMediaElementSource(audio);
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 256;
        src.connect(analyser);
        analyser.connect(ctx.destination);

        const data = new Uint8Array(analyser.frequencyBinCount);

        function tick() {
            if (audio.paused || audio.ended) {
                mouthAnimating = false;
                setMouthOpen(0);
                ctx.close().catch(() => {});
                fetchEmotion();
                return;
            }
            analyser.getByteTimeDomainData(data);
            let sum = 0;
            for (let i = 0; i < data.length; i++) {
                const v = (data[i] - 128) / 128;
                sum += v * v;
            }
            const rms = Math.sqrt(sum / data.length);
            setMouthOpen(Math.min(1.5, rms * 18));
            requestAnimationFrame(tick);
        }
        tick();
    } catch (e) {
        // Нет AudioContext — анимируем синусоидой
        const t0 = Date.now();
        function fakeTick() {
            if (Date.now() - t0 > 4000) {
                mouthAnimating = false;
                setMouthOpen(0);
                fetchEmotion();
                return;
            }
            setMouthOpen(0.3 + 0.7 * Math.abs(Math.sin(Date.now() / 120)));
            requestAnimationFrame(fakeTick);
        }
        fakeTick();
        audio.play().catch(() => {});
    }
}

function setMouthOpen(value) {
    if (!live2dModel) return;
    try {
        const core = live2dModel.internalModel.coreModel;
        core.setParameterValueById('ParamA', value);
    } catch (e) {}
}

function avatarWave() {
    if (!live2dModel) return;
    try {
        const idx = Math.floor(Math.random() * 3);
        live2dModel.motion('', idx);
    } catch (e) {}
    fetch('/api/avatar/purr', { method: 'POST' }).catch(() => {});
}
