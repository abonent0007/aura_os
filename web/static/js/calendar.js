// calendar.js — Календарь AURA OS (month/week grid)

let calendarYear, calendarMonth, calendarEvents = [], calendarView = 'month';

async function loadCalendarView(days) {
    if (!days || isNaN(days)) days = 7;
    const now = new Date();
    calendarYear = now.getFullYear();
    calendarMonth = now.getMonth() + 1;
    await fetchEvents();
    renderCalendar();
}

// Alias for backward compat
function loadCalendar(days) { loadCalendarView(days); }

async function fetchEvents() {
    try {
        const res = await fetch('/api/calendar?days=90');
        const data = await res.json();
        calendarEvents = data.events || [];
    } catch (e) { console.error('Calendar:', e); }
}

function switchCalendarView(view) {
    calendarView = view;
    document.getElementById('btn-view-month').classList.toggle('btn-primary', view === 'month');
    document.getElementById('btn-view-week').classList.toggle('btn-primary', view === 'week');
    renderCalendar();
}

function calendarPrevMonth() {
    calendarMonth--;
    if (calendarMonth < 1) { calendarMonth = 12; calendarYear--; }
    renderCalendar();
}

function calendarNextMonth() {
    calendarMonth++;
    if (calendarMonth > 12) { calendarMonth = 1; calendarYear++; }
    renderCalendar();
}

function renderCalendar() {
    document.getElementById('calendarMonthLabel').textContent =
        new Date(calendarYear, calendarMonth - 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });

    if (calendarView === 'week') renderWeekView();
    else renderMonthView();
}

function renderMonthView() {
    const grid = document.getElementById('calendarGrid');
    const detail = document.getElementById('calendarDayDetail');
    detail.style.display = 'none';

    const firstDay = new Date(calendarYear, calendarMonth - 1, 1);
    const lastDay = new Date(calendarYear, calendarMonth, 0);
    const startDow = (firstDay.getDay() + 6) % 7; // Monday=0
    const totalDays = lastDay.getDate();

    // Header row
    const dayNames = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    let html = '<div class="cal-row cal-header">';
    dayNames.forEach(d => html += `<div class="cal-cell cal-header-cell">${d}</div>`);
    html += '</div>';

    // Group events by date
    const byDate = {};
    calendarEvents.forEach(ev => {
        const d = ev.event_date;
        if (!byDate[d]) byDate[d] = [];
        byDate[d].push(ev);
    });

    // Calendar cells
    let day = 1;
    for (let week = 0; week < 6; week++) {
        html += '<div class="cal-row">';
        for (let dow = 0; dow < 7; dow++) {
            if ((week === 0 && dow < startDow) || day > totalDays) {
                html += '<div class="cal-cell cal-empty"></div>';
            } else {
                const dateStr = `${calendarYear}-${String(calendarMonth).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
                const events = byDate[dateStr] || [];
                const today = new Date().toISOString().slice(0, 10);
                const isToday = dateStr === today;

                let dots = '';
                if (events.length > 0) {
                    const hasBday = events.some(e => e.category === 'drr');
                    const hasTask = events.some(e => e.category === 'zad');
                    const hasRem = events.some(e => e.category === 'nap');
                    const hasEvt = events.some(e => e.category === 'evt');
                    const hasPln = events.some(e => e.category === 'pln');
                    const hasMed = events.some(e => e.category === 'med');
                    if (hasBday) dots += '<span class="cal-dot dot-birthday"></span>';
                    if (hasTask) dots += '<span class="cal-dot dot-task"></span>';
                    if (hasRem) dots += '<span class="cal-dot dot-reminder"></span>';
                    if (hasEvt) dots += '<span class="cal-dot dot-event"></span>';
                    if (hasPln) dots += '<span class="cal-dot dot-plan"></span>';
                    if (hasMed) dots += '<span class="cal-dot dot-health"></span>';
                }

                html += `<div class="cal-cell ${isToday ? 'cal-today' : ''}" onclick="showDayDetail('${dateStr}')">
                    <span class="cal-day-num">${day}</span>
                    <div class="cal-dots">${dots}</div>
                </div>`;
                day++;
            }
        }
        html += '</div>';
        if (day > totalDays) break;
    }

    grid.innerHTML = html;
}

function renderWeekView() {
    const grid = document.getElementById('calendarGrid');
    const detail = document.getElementById('calendarDayDetail');
    detail.style.display = 'none';

    const today = new Date();
    const dow = (today.getDay() + 6) % 7;
    const monday = new Date(today);
    monday.setDate(today.getDate() - dow);

    // Group by date
    const byDate = {};
    calendarEvents.forEach(ev => { const d = ev.event_date; if (!byDate[d]) byDate[d] = []; byDate[d].push(ev); });

    const dayNames = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
    let html = '';

    for (let i = 0; i < 7; i++) {
        const d = new Date(monday);
        d.setDate(monday.getDate() + i);
        const dateStr = d.toISOString().slice(0, 10);
        const isToday = dateStr === today.toISOString().slice(0, 10);
        const events = byDate[dateStr] || [];

        html += `<div class="cal-week-row ${isToday ? 'cal-today' : ''}" onclick="showDayDetail('${dateStr}')">
            <div class="cal-week-date">
                <span class="cal-week-dayname">${dayNames[i]}</span>
                <span class="cal-week-daynum">${d.getDate()} ${d.toLocaleDateString('ru-RU',{month:'short'})}</span>
            </div>
            <div class="cal-week-events">`;

        if (events.length === 0) {
            html += '<span class="cal-no-events">Нет событий</span>';
        } else {
            events.forEach(ev => {
                const emojis = {drr:'🎂', zad:'📋', nap:'🔔', evt:'📅', pln:'📌', med:'🏥'};
                const emoji = emojis[ev.category] || '📌';
                html += `<div class="cal-week-event ${ev.category}">
                    <span>${emoji}</span>
                    <span>${ev.title || ''}</span>
                    ${ev.event_time ? `<span class="cal-event-time">${ev.event_time.slice(0,5)}</span>` : ''}
                </div>`;
            });
        }

        html += `</div></div>`;
    }

    grid.innerHTML = html;
}

function showDayDetail(dateStr) {
    const events = calendarEvents.filter(e => e.event_date === dateStr);
    const detail = document.getElementById('calendarDayDetail');
    const title = document.getElementById('calendarDayTitle');
    const eventsDiv = document.getElementById('calendarDayEvents');

    const d = new Date(dateStr + 'T00:00:00');
    title.textContent = d.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });

    if (events.length === 0) {
        eventsDiv.innerHTML = '<p>Нет событий на этот день</p>';
    } else {
        eventsDiv.innerHTML = events.map(ev => {
            const emojis = {drr:'🎂', zad:'📋', nap:'🔔', evt:'📅', pln:'📌', med:'🏥'};
            const emoji = emojis[ev.category] || '📌';
            const names = {drr:'День рождения', zad:'Задача', nap:'Напоминание', evt:'Событие', pln:'План', med:'Здоровье'};
            const catName = names[ev.category] || 'Событие';
            return `<div class="cal-day-event ${ev.category} ${ev.is_completed ? 'completed' : ''}">
                <span class="cal-event-emoji">${emoji}</span>
                <div class="cal-event-info">
                    <strong>${ev.title || 'Без названия'}</strong>
                    <span class="cal-event-cat">${catName}${ev.event_time ? ' в ' + ev.event_time.slice(0,5) : ''}</span>
                    ${ev.description ? `<p class="cal-event-desc">${ev.description}</p>` : ''}
                </div>
            </div>`;
        }).join('');
    }

    detail.style.display = 'block';
    detail.scrollIntoView({ behavior: 'smooth' });
}

async function syncCalendar() {
    try {
        const res = await fetch('/api/calendar/sync', { method: 'POST' });
        await res.json();
        await fetchEvents();
        renderCalendar();
    } catch (e) { console.error('Sync:', e); }
}

document.addEventListener('DOMContentLoaded', () => loadCalendarView(7));
