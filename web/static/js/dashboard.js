// dashboard.js — Дашборд AURA OS

async function initDashboard() {
    await loadStatus();
    drawCharts();
    document.getElementById('btn-refresh-dashboard')?.addEventListener('click', refreshDashboard);
}

async function refreshDashboard() {
    await loadStatus();
    drawCharts();
}

async function loadStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('stat-skills').textContent = data.skills?.total || 0;
        document.getElementById('stat-events').textContent = data.calendar?.upcoming_events || 0;
        document.getElementById('stat-messages').textContent = data.memory?.conversations || 0;
        document.getElementById('stat-uptime').textContent = `${data.uptime || 0}h`;
    } catch (e) {
        console.error('Dashboard status error:', e);
    }
}

async function drawCharts() {
    try {
        const res = await fetch('/api/dashboard/history');
        const data = await res.json();
        if (!data.history || !data.history.length) return;
        drawChart('activityChart', data.history, 'messages', '#6c5ce7', 'Messages');
        drawChart('memoryChart', data.history, 'memory_mb', '#00c853', 'Memory (MB)');
    } catch (e) {
        console.error('Chart error:', e);
    }
}

function drawChart(canvasId, history, field, color, label) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    // Get stable container width from the card (not canvas parent which shifts)
    const card = canvas.closest('.card');
    const cardWidth = card ? card.offsetWidth : 400;
    const w = Math.max(300, cardWidth - 40);
    const h = 200;

    canvas.width = w;
    canvas.height = h;
    canvas.style.width = w + 'px';
    canvas.style.height = h + 'px';
    canvas.style.maxWidth = '100%';

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);

    const pad = 30;
    const cw = w - pad * 2;
    const ch = h - pad * 2;
    const maxVal = Math.max(...history.map(p => p[field] || 0), 1);

    // Grid
    ctx.strokeStyle = '#2d3140';
    ctx.lineWidth = 0.5;
    const gridLines = 5;
    for (let i = 0; i <= gridLines; i++) {
        const y = pad + (ch / gridLines) * i;
        ctx.beginPath();
        ctx.moveTo(pad, y);
        ctx.lineTo(pad + cw, y);
        ctx.stroke();

        // Y-axis labels
        const val = Math.round(maxVal - (maxVal / gridLines) * i);
        ctx.fillStyle = '#6c6f78';
        ctx.font = '10px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(String(val), pad - 5, y + 3);
    }

    // X-axis labels (hours)
    ctx.textAlign = 'center';
    for (let i = 0; i < history.length; i += 4) {
        const x = pad + (i / (history.length - 1)) * cw;
        const h = new Date(history[i].timestamp).getHours();
        ctx.fillText(h + ':00', x, h - 8);
    }

    // Line
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.beginPath();
    history.forEach((point, i) => {
        const x = pad + (i / (history.length - 1)) * cw;
        const y = pad + ch - ((point[field] || 0) / maxVal) * ch;
        i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.stroke();

    // Fill under line
    ctx.globalAlpha = 0.1;
    ctx.fillStyle = color;
    ctx.lineTo(pad + cw, pad + ch);
    ctx.lineTo(pad, pad + ch);
    ctx.closePath();
    ctx.fill();
    ctx.globalAlpha = 1;

    // Dots
    history.forEach((point, i) => {
        const x = pad + (i / (history.length - 1)) * cw;
        const y = pad + ch - ((point[field] || 0) / maxVal) * ch;
        ctx.fillStyle = color;
        ctx.beginPath();
        ctx.arc(x, y, 3, 0, Math.PI * 2);
        ctx.fill();
    });

    // Label
    ctx.fillStyle = '#b0b3b8';
    ctx.font = '11px sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(label, pad, pad - 5);
}

document.addEventListener('DOMContentLoaded', initDashboard);
