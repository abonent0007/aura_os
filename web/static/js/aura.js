/* ═══════════════════ CONFIG ═══════════════════ */
    const API_BASE = '';

    /* ═══════════════════ NAVIGATION ═══════════════════ */
    function navigateTo(name){
      document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
      const t=document.querySelector(`.page[data-page="${name}"]`); if(t)t.classList.add('active');
      document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
      const ni=document.querySelector(`.nav-item[data-page="${name}"]`); if(ni)ni.classList.add('active');
      document.getElementById('sidebar').classList.remove('open');
      if(name==='calendar')loadCalendar(); if(name==='skills')loadSkills();
      if(name==='logs')loadLogs(); if(name==='backups')loadBackups();
      if(name==='settings')loadSettings();
    }
    document.querySelectorAll('.nav-item').forEach(item=>{item.addEventListener('click',e=>{e.preventDefault();navigateTo(item.dataset.page)})});

    /* ═══════════════════ BOOT SEQUENCE ═══════════════════ */
    function runBoot(){
      const bar=document.getElementById('boot-progress'),log=document.getElementById('boot-log');
      if(!bar||!log)return;
      bar.style.width='0%';
      const steps=[{pct:22,t:'<span class="ok">[  OK  ]</span> Загрузка языковой модели (RU)',d:200},{pct:40,t:'<span class="ok">[  OK  ]</span> Инициализация контекстной памяти',d:350},{pct:58,t:'<span class="ok">[  OK  ]</span> Эмоциональный движок v3.1',d:250},{pct:76,t:'<span class="ok">[  OK  ]</span> Подсистема эмпатии',d:200},{pct:90,t:'<span class="info">[  ..  ]</span> Загрузка персональных воспоминаний...',d:400},{pct:100,t:'<span class="ok">[  OK  ]</span> Все системы активны. Аура готова. 💖',d:150}];
      let total=0; steps.forEach(s=>{total+=s.d;setTimeout(()=>{bar.style.width=s.pct+'%';log.innerHTML+=`<div>${s.t}</div>`},total)});
      setTimeout(()=>navigateTo('chat'),total+500);
    }

    /* ═══════════════════ CHAT — REAL API ═══════════════════ */
    let chatPaused=false, chatMode='aura', autoTTS=true, msgCount=0, recognition=null, isListening=false, audioEl=null;

    function toggleAutoTTS(){autoTTS=!autoTTS;const b=document.getElementById('btn-tts-auto');if(b){b.style.background=autoTTS?'var(--accent)':'';b.style.borderColor=autoTTS?'transparent':'';b.style.color=autoTTS?'#fff':'';b.textContent=autoTTS?'🔊 Авто':'🔊 Ручной'}}
    function toggleChatPause(){chatPaused=!chatPaused;const b=document.getElementById('btn-pause');if(b){b.textContent=chatPaused?'▶':'⏸';b.title=chatPaused?'Прокрутка на паузе':'Пауза прокрутки'}}
    function setChatMode(m){chatMode=m;const ba=document.getElementById('btn-mode-aura'),be=document.getElementById('btn-mode-expert');ba.style.background=m==='aura'?'var(--accent)':'';ba.style.borderColor=m==='aura'?'transparent':'';be.style.background=m==='expert'?'var(--accent)':'';be.style.borderColor=m==='expert'?'transparent':''}
    let activeWs = null;

    async function sendMessage(){
      const inp=document.getElementById('chat-input'),text=inp.value.trim();if(!text)return;
      appendMsg('user',text);inp.value='';
      const body=document.getElementById('chat-body');
      const tId='typing-'+Date.now();
      const tDiv=document.createElement('div');tDiv.className='msg aura';tDiv.id=tId;
      tDiv.innerHTML=`<div class="msg-avatar">💖</div><div><div class="msg-bubble"><div class="typing-indicator"><span></span><span></span><span></span></div></div></div>`;
      body.appendChild(tDiv);body.scrollTop=body.scrollHeight;
      try{
        const ep=chatMode==='expert'?'/api/chat/expert':'/api/chat';
        const r=await fetch(ep,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
        const data=await r.json();
        document.getElementById(tId)?.remove();
        const msgText=data.text||data.report||'Ответ не получен';
        const el=appendMsg('aura',msgText);
        if(autoTTS&&el){const btn=el.querySelector('.btn-tts');if(btn)setTimeout(()=>ttsSpeak(btn),300)}
      }catch(e){document.getElementById(tId)?.remove();appendMsg('aura','❌ Ошибка: '+e.message)}
    }
    function sendQuick(t){document.getElementById('chat-input').value=t;sendMessage()}

    function appendMsg(type,text){
      const body=document.getElementById('chat-body'),isAura=type==='aura';
      const avatar=isAura?'💖':'😊';
      const time=new Date().toLocaleTimeString('ru-RU',{hour:'2-digit',minute:'2-digit'});
      const msgId='msg-'+Date.now();
      const div=document.createElement('div');div.className=`msg ${type}`;div.id=msgId;div.dataset.text=text;
      div.innerHTML=`<div class="msg-avatar">${avatar}</div><div><div class="msg-bubble">${renderMarkdown(escapeHtml(text))}</div><div class="msg-footer"><span class="msg-time">Сегодня, ${time}</span><button class="btn-tts" onclick="ttsSpeak(this)" title="Озвучить">🔊</button><button class="btn-copy" onclick="copyMsg(this)" title="Копировать">📋</button></div></div>`;
      body.appendChild(div);if(!chatPaused)body.scrollTop=body.scrollHeight;
      msgCount++;const bad=document.getElementById('badge-chat');if(bad){bad.textContent=msgCount;bad.style.display=''}
      return div;
    }

    function copyMsg(btn){const el=btn.closest('.msg');if(!el)return;const t=el.dataset.text||'';navigator.clipboard.writeText(t).then(()=>{btn.textContent='✓';setTimeout(()=>btn.textContent='📋',1500)}).catch(()=>{})}

    async function ttsSpeak(btn){
      const el=btn.closest('.msg');if(!el)return;const text=el.dataset.text||'';
      if(audioEl&&!audioEl.paused){audioEl.pause();audioEl=null;btn.textContent='🔊';return}
      btn.textContent='...';
      try{
        const r=await fetch('/api/chat/tts',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:text.substring(0,6000)})});
        if(!r.ok)throw new Error('TTS failed');
        const blob=await r.blob();const url=URL.createObjectURL(blob);
        audioEl=new Audio(url);audioEl.onended=()=>{btn.textContent='🔊';audioEl=null};audioEl.onerror=()=>{btn.textContent='🔊';audioEl=null};
        await audioEl.play();btn.textContent='⏸';
      }catch(e){btn.textContent='🔊';console.error('TTS:',e)}
    }

    function toggleVoiceInput(){
      if(!('webkitSpeechRecognition' in window)&&!('SpeechRecognition' in window)){alert('Голосовой ввод не поддерживается. Используйте Chrome.');return}
      if(isListening){stopVoice();return}
      const SR=window.SpeechRecognition||window.webkitSpeechRecognition;recognition=new SR();recognition.lang='ru-RU';recognition.interimResults=true;recognition.continuous=false;
      recognition.onresult=(ev)=>{let t='';for(let i=0;i<ev.results.length;i++)t+=ev.results[i][0].transcript;document.getElementById('chat-input').value=t;if(ev.results[0].isFinal){stopVoice();setTimeout(()=>sendMessage(),300)}};
      recognition.onerror=()=>stopVoice();recognition.onend=()=>stopVoice();
      recognition.start();isListening=true;document.getElementById('btn-mic').textContent='🔴';document.getElementById('btn-mic').style.background='#ff5252';
    }
    function stopVoice(){if(recognition){recognition.stop();recognition=null}isListening=false;document.getElementById('btn-mic').textContent='🎤';document.getElementById('btn-mic').style.background=''}

    /* ── Markdown Renderer ── */
    function escapeHtml(t){const d=document.createElement('div');d.textContent=t;return d.innerHTML}
    function renderMarkdown(t){
      let tables=[];t=t.replace(/(\|.+\|\n\|[-| :]+\|\n(?:\|.+\|\n?)+)/g,(m)=>{tables.push(m);return`%%TBL${tables.length-1}%%`});
      t=t.replace(/```(\w*)\n([\s\S]*?)```/g,(_,lang,code)=>`<div class="code-block"><div class="code-header"><span>${lang||'code'}</span><button class="btn btn-sm" onclick="navigator.clipboard.writeText(\`${code.trim().replace(/`/g,'\\`').replace(/\\/g,'\\\\')}\`);this.textContent='✓';setTimeout(()=>this.textContent='Копировать',1500)">Копировать</button></div><pre><code>${escapeHtml(code.trim())}</code></pre></div>`);
      t=t.replace(/`([^`]+)`/g,'<code class="inline-code">$1</code>');
      t=t.replace(/\*\*(.+?)\*\*/g,'<strong>$1</strong>');t=t.replace(/\*(.+?)\*/g,'<em>$1</em>');
      t=t.replace(/^### (.+)$/gm,'<h4>$1</h4>');t=t.replace(/^## (.+)$/gm,'<h3>$1</h3>');t=t.replace(/^# (.+)$/gm,'<h2>$1</h2>');
      t=t.replace(/^[-*_]{3,}\s*$/gm,'<hr>');
      t=t.replace(/^[*-] (.+)$/gm,'<li>$1</li>');t=t.replace(/((?:<li>.*<\/li>\n?)+)/g,'<ul>$1</ul>');
      t=t.replace(/^\d+\. (.+)$/gm,'<li>$1</li>');
      t=t.replace(/\[([^\]]+)\]\(([^)]+)\)/g,'<a href="$2" target="_blank">$1</a>');
      t=t.replace(/%%TBL(\d+)%%/g,(_,i)=>renderTable(tables[parseInt(i)]));
      const ps=t.split('\n\n');return ps.map(p=>{const tr=p.trim();if(!tr)return'';if(tr.startsWith('<h')||tr.startsWith('<ul')||tr.startsWith('<ol')||tr.startsWith('<div class="code-block"')||tr.startsWith('<table'))return tr;return`<p>${tr.replace(/\n/g,'<br>')}</p>`}).join('');
    }
    function renderTable(md){
      if(!md)return'';const rows=md.trim().split('\n'),dataRows=rows.filter(r=>!r.match(/^\|[-| :]+\|$/));
      if(dataRows.length<1)return md;let h='<table class="md-table"><thead><tr>';
      dataRows[0].split('|').filter(c=>c.trim()).forEach(c=>{h+=`<th>${c.trim()}</th>`});h+='</tr></thead><tbody>';
      for(let i=1;i<dataRows.length;i++){h+='<tr>';dataRows[i].split('|').filter(c=>c.trim()).forEach(c=>{h+=`<td>${c.trim()}</td>`});h+='</tr>'}
      return h+'</tbody></table>';
    }

    /* ═══════════════════ CALENDAR — REAL API ═══════════════════ */
    let calYear,calMonth,calView='month',calendarEvents=[];
    function initCal(){const now=new Date();calYear=now.getFullYear();calMonth=now.getMonth()+1}
    async function loadCalendar(){initCal();try{const r=await fetch('/api/calendar?days=90');const d=await r.json();calendarEvents=(d.events||[]).map(e=>({date:e.event_date,title:e.title,category:e.category,desc:e.description||'',time:e.event_time||''}));const bad=document.getElementById('badge-calendar');if(bad){const now=new Date();const thisMonth=calendarEvents.filter(e=>e.date&&e.date.startsWith(now.toISOString().slice(0,7))).length;bad.textContent=thisMonth;bad.style.display=thisMonth?'':(bad.style.display||'')};renderCalendar()}catch(e){toast('Ошибка загрузки календаря')}}
    async function syncCalendar(){try{const r=await fetch('/api/calendar/sync',{method:'POST'});const d=await r.json();toast('✅ Синхронизировано: '+JSON.stringify(d));loadCalendar()}catch(e){toast('❌ Ошибка синхронизации')}}
    function switchCalView(v){calView=v;document.getElementById('btn-view-month').classList.toggle('btn-primary',v==='month');document.getElementById('btn-view-week').classList.toggle('btn-primary',v==='week');renderCalendar()}
    function calendarPrevMonth(){calMonth--;if(calMonth<1){calMonth=12;calYear--}renderCalendar()}
    function calendarNextMonth(){calMonth++;if(calMonth>12){calMonth=1;calYear++}renderCalendar()}
    function renderCalendar(){if(calendarEvents.length===0)return loadCalendar();document.getElementById('cal-month-label').textContent=new Date(calYear,calMonth-1).toLocaleDateString('ru-RU',{month:'long',year:'numeric'});document.getElementById('cal-day-detail').style.display='none';calView==='week'?renderWeekView():renderMonthView()}
    function renderMonthView(){const grid=document.getElementById('cal-grid'),firstDay=new Date(calYear,calMonth-1,1),lastDay=new Date(calYear,calMonth,0);const startDow=(firstDay.getDay()+6)%7,totalDays=lastDay.getDate(),dn=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];const byDate={};calendarEvents.forEach(ev=>{if(!byDate[ev.date])byDate[ev.date]=[];byDate[ev.date].push(ev)});let h='<div class="cal-row">';dn.forEach(d=>h+=`<div class="cal-header-cell">${d}</div>`);h+='</div>';let day=1;for(let w=0;w<6;w++){h+='<div class="cal-row">';for(let dow=0;dow<7;dow++){if((w===0&&dow<startDow)||day>totalDays){h+='<div class="cal-cell empty"></div>';continue}const ds=`${calYear}-${String(calMonth).padStart(2,'0')}-${String(day).padStart(2,'0')}`;const evts=byDate[ds]||[],today=new Date().toISOString().slice(0,10),isToday=ds===today;let dots='';['drr','zad','nap','evt','pln','med'].forEach(cat=>{if(evts.some(e=>e.category===cat))dots+=`<span class="cal-dot dot-${cat}"></span>`});h+=`<div class="cal-cell${isToday?' today':''}" onclick="showDayDetail('${ds}')"><span class="cal-day-num">${day}</span><div class="cal-dots">${dots}</div></div>`;day++}h+='</div>';if(day>totalDays)break}grid.innerHTML=h}
    function renderWeekView(){const grid=document.getElementById('cal-grid'),today=new Date(),dow=(today.getDay()+6)%7,monday=new Date(today);monday.setDate(today.getDate()-dow);const byDate={};calendarEvents.forEach(ev=>{if(!byDate[ev.date])byDate[ev.date]=[];byDate[ev.date].push(ev)});const dn=['Пн','Вт','Ср','Чт','Пт','Сб','Вс'];let h='';for(let i=0;i<7;i++){const d=new Date(monday);d.setDate(monday.getDate()+i);const ds=d.toISOString().slice(0,10),isToday=ds===today.toISOString().slice(0,10),evts=byDate[ds]||[];h+=`<div class="cal-week-row${isToday?' today':''}" onclick="showDayDetail('${ds}')"><div class="cal-week-date"><span class="cal-week-dayname">${dn[i]}</span><span class="cal-week-daynum">${d.getDate()} ${d.toLocaleDateString('ru-RU',{month:'short'})}</span></div><div class="cal-week-events">`;if(evts.length===0)h+='<div class="cal-no-events">Нет событий</div>';else evts.forEach(ev=>{const em={drr:'🎂',zad:'📋',nap:'🔔',evt:'📅',pln:'📌',med:'🏥'};h+=`<div class="cal-week-event"><span>${em[ev.category]||'📌'}</span><span>${ev.title}</span>${ev.time?`<span class="cal-event-time">${ev.time.slice(0,5)}</span>`:''}</div>`});h+='</div></div>'}grid.innerHTML=h}
    function showDayDetail(ds){const evts=calendarEvents.filter(e=>e.date===ds),dd=document.getElementById('cal-day-detail');const d=new Date(ds+'T00:00:00'),title=d.toLocaleDateString('ru-RU',{weekday:'long',day:'numeric',month:'long'});let h=`<h3>${title}</h3>`;if(evts.length===0)h+='<p style="color:var(--text-muted)">Нет событий</p>';else{const em={drr:'🎂',zad:'📋',nap:'🔔',evt:'📅',pln:'📌',med:'🏥'},cn={drr:'День рождения',zad:'Задача',nap:'Напоминание',evt:'Событие',pln:'План',med:'Здоровье'};evts.forEach(ev=>{h+=`<div class="cal-day-event ${ev.category}"><span class="cal-event-emoji">${em[ev.category]||'📌'}</span><div class="cal-event-info"><strong>${ev.title}</strong><div class="cat">${cn[ev.category]||'Событие'}${ev.time?' в '+ev.time.slice(0,5):''}</div>${ev.desc?`<p class="desc">${ev.desc}</p>`:''}</div></div>`})}dd.innerHTML=h;dd.style.display='block';dd.scrollIntoView({behavior:'smooth'})}

    /* ═══════════════════ SKILLS — REAL API ═══════════════════ */
    function loadSkills(){document.getElementById('skills-stats').textContent='Загрузка...';
      fetch('/api/skills').then(r=>r.json()).then(data=>{const skills=data.skills||{};const stats=data.stats||{};
        let list=Object.values(skills);const bad=document.getElementById('badge-skills');if(bad){bad.textContent=list.length;bad.style.display=''};
        document.getElementById('skills-stats').textContent=`Всего: ${list.length} | Активно: ${stats.enabled||0} | Стаб: ${stats.stable||0}`;
        document.getElementById('skills-grid').innerHTML=list.map(s=>`
          <div class="skill-card${s.enabled?'':' disabled'}">
            <div class="skill-hdr"><span class="skill-name">${s.name}</span><span class="skill-badge badge-${s.stability||'testing'}">${s.stability||'?'}</span></div>
            <div class="skill-desc">${s.description||''}</div>
            <div class="skill-tags">${(s.triggers||[]).slice(0,5).map(t=>`<span class="skill-tag">${t}</span>`).join('')}</div>
            <div class="skill-meta">v${s.version||'?'} | ${s.tools_count||0} tools | ${s.errors||0} errors</div>
          </div>`).join('');
      }).catch(()=>document.getElementById('skills-stats').textContent='Ошибка');
    }
    function showCreateSkillModal(){document.getElementById('createSkillModal').classList.add('active')}
    function hideCreateSkillModal(){document.getElementById('createSkillModal').classList.remove('active')}
    async function createSkill(){const desc=document.getElementById('skill-desc-input').value.trim();if(!desc)return;const st=document.getElementById('skill-creation-status');st.innerHTML='⏳...';try{const r=await fetch('/api/skills/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({description:desc})});await r.json();st.innerHTML='✅ Создано';loadSkills();setTimeout(hideCreateSkillModal,2000)}catch(e){st.innerHTML='❌ Ошибка'}}

    /* ═══════════════════ LOGS — REAL ═══════════════════ */
    let logsData=[];
    async function loadLogs(){try{const r=await fetch('/api/logs?limit=200');const data=await r.json();logsData=data.logs||data||[];if(!Array.isArray(logsData))logsData=[];renderLogs()}catch(e){console.error(e)}}
    function renderLogs(){const container=document.getElementById('log-container');if(!container)return;container.innerHTML=logsData.map(l=>`<div class="log-entry"><span class="log-time">${l.time||''}</span><span class="log-level ${l.level||'info'}">[${(l.level||'INFO').toUpperCase()}]</span><span class="log-msg">${l.message||l.msg||''}</span></div>`).join('')||'<div class="log-entry"><span class="log-msg">Нет записей</span></div>'}
    async function clearLogs(){try{await fetch('/api/logs/clear',{method:'POST'});logsData=[];renderLogs();toast('Логи очищены')}catch(e){toast('Ошибка')}}

    /* ═══════════════════ BACKUPS — REAL ═══════════════════ */
    async function loadBackups(){try{const r=await fetch('/api/backups');const data=await r.json();let list=data.backups||data||[];if(!Array.isArray(list))list=[];document.getElementById('backup-list').innerHTML=list.map(b=>`<div class="backup-card"><div class="row"><div><strong>${b.id||b.name||'?'}</strong></div></div><div class="info">📅 ${b.time||b.created||'?'}</div></div>`).join('')||'<div class="backup-card"><div class="info">Нет бекапов</div></div>'}catch(e){document.getElementById('backup-list').innerHTML='<div class="backup-card"><div class="info">Ошибка</div></div>'}
    async function createBackup(){try{await fetch('/api/backups/create',{method:'POST'});toast('✅ Бекап создан');loadBackups()}catch(e){toast('❌ Ошибка')}}

    /* ═══════════════════ SETTINGS ═══════════════════ */
    let timezonesList=[];
    async function loadSettings(){try{const r=await fetch('/api/timezones');const d=await r.json();timezonesList=d.timezones||[]}catch(e){}try{await loadSettingsUI()}catch(e){document.getElementById('settings-container').innerHTML='<div class="setting-row">Ошибка загрузки</div>'}}
    
    async function loadSettingsUI(){
      const r=await fetch('/api/config');const config=await r.json();const c=document.getElementById('settings-container');c.innerHTML='';
      c.appendChild(cfgBriefing(config));
      c.appendChild(cfgTriggers('Триггеры памяти','memory.memory_search.triggers_past',config.memory?.memory_search?.triggers_past||[]));
      c.appendChild(cfgTriggers('Триггеры поиска','web_search.triggers.search',config.web_search?.triggers?.search||[]));
      c.appendChild(cfgTriggers('Триггеры новостей','web_search.triggers.news',config.web_search?.triggers?.news||[]));
      c.appendChild(cfgTriggers('Триггеры погоды','web_search.triggers.weather',config.web_search?.triggers?.weather||[]));
      c.appendChild(cfgText('Город для погоды','web_search.weather.default_city',config.web_search?.weather?.default_city||'Moscow'));
      c.appendChild(cfgTz(config));
      c.appendChild(cfgAll(config));
      toast('Настройки загружены');
    }
    function cfgBriefing(cfg){const d=document.createElement('div');d.className='settings-group';d.innerHTML=`<h3>Ежедневный брифинг</h3><div class="setting-row"><div><div class="setting-label">Время</div><div class="setting-desc">Когда Аура присылает утренний брифинг</div></div><div style="display:flex;gap:8px;align-items:center"><input type="time" id="cfg-briefing-time" value="${cfg.briefing?.time||'09:00'}"><button class="btn btn-sm btn-primary" onclick="cfgSave('briefing','time','cfg-briefing-time')">✓</button></div></div>`;return d}
    function cfgTriggers(title,key,values){const d=document.createElement('div');d.className='settings-group';const text=Array.isArray(values)?values.join(', '):(values||'');const id='s-'+key.replace(/\./g,'-');d.innerHTML=`<h3>${title}</h3><div style="display:flex;gap:8px"><textarea id="${id}" style="flex:1;background:var(--bg-input);border:1px solid var(--border-default);border-radius:4px;color:var(--text-primary);padding:8px;font-size:.78rem;resize:vertical;min-height:50px">${escapeHtml(text)}</textarea><button class="btn btn-sm btn-primary" style="align-self:flex-start" onclick="cfgTriggersSave('${key}','${id}')">✓</button></div>`;return d}
    function cfgText(title,key,value){const d=document.createElement('div');d.className='settings-group';const id='s-'+key.replace(/\./g,'-');d.innerHTML=`<h3>${title}</h3><div style="display:flex;gap:8px"><input type="text" id="${id}" value="${escapeHtml(String(value||''))}" style="flex:1;max-width:400px;background:var(--bg-input);border:1px solid var(--border-default);border-radius:4px;color:var(--text-primary);padding:8px;font-size:.82rem"><button class="btn btn-sm btn-primary" onclick="cfgTextSave('${key}','${id}')">✓</button></div>`;return d}
    function cfgTz(cfg){const d=document.createElement('div');d.className='settings-group';const opts=timezonesList.map(tz=>`<option value="${tz.value}" ${tz.value===(cfg.briefing?.timezone||'Europe/Moscow')?'selected':''}>${tz.label}</option>`).join('');d.innerHTML=`<h3>Часовой пояс</h3><div style="display:flex;gap:8px"><select id="cfg-tz" style="min-width:280px;background:var(--bg-input);border:1px solid var(--border-default);border-radius:4px;color:var(--text-primary);padding:8px;font-size:.82rem">${opts}</select><button class="btn btn-sm btn-primary" onclick="cfgTextSave('briefing.timezone','cfg-tz')">✓</button></div>`;return d}
    function cfgAll(cfg){const d=document.createElement('div');d.innerHTML='<hr style="border-color:var(--border-default);margin:24px 0"><h2 style="margin-bottom:16px;font-size:1.1rem">Все настройки (только чтение)</h2>';let first=true;for(const[section,vals]of Object.entries(cfg)){if(section.startsWith('_')||typeof vals!=='object'||!vals)continue;const g=document.createElement('div');g.className='settings-group';g.innerHTML=`<h3>${section}</h3>`;function walk(obj,pre){for(const[k,v]of Object.entries(obj)){if(typeof v==='object'&&v!==null&&!Array.isArray(v)){walk(v,pre?pre+'.'+k:k)}else{const row=document.createElement('div');row.className='setting-row';row.innerHTML=`<span class="setting-label" style="font-size:.75rem">${pre?pre+'.'+k:k}</span> <span class="setting-desc">${Array.isArray(v)?v.join(', '):String(v??'').substring(0,80)}</span>`;g.appendChild(row)}}}walk(vals,'');d.appendChild(g)}return d}
    async function cfgSave(section,key,elId){const el=document.getElementById(elId);if(!el)return;try{await fetch('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({section,key,value:el.value})});toast('✅ Сохранено')}catch(e){toast('❌ Ошибка')}}
    function cfgTextSave(keystr,elId){const el=document.getElementById(elId);if(!el)return;const p=keystr.split('.');cfgSave(p[0],p.slice(1).join('.'),elId)}
    function cfgTriggersSave(keystr,elId){const el=document.getElementById(elId);if(!el)return;const p=keystr.split('.');const v=el.value.split(',').map(s=>s.trim()).filter(Boolean);try{fetch('/api/config',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({section:p[0],key:p.slice(1).join('.'),value:v})});toast('✅ Сохранено')}catch(e){toast('❌ Ошибка')}}

    /* ═══════════════════ UTILS ═══════════════════ */
    function toggleTheme(){const themes=['','slate','forest','amethyst','rose'];const cur=document.documentElement.getAttribute('data-theme')||'';const idx=themes.indexOf(cur);const next=themes[(idx+1)%themes.length];const labels={'':'Тёплая','slate':'Синяя','forest':'Зелёная','amethyst':'Фиолетовая','rose':'Розовая'};if(next){document.documentElement.setAttribute('data-theme',next)}else{document.documentElement.removeAttribute('data-theme')};[document.getElementById('btn-theme'),document.getElementById('btn-theme-settings')].forEach(b=>{if(b)b.textContent='🎨 '+labels[next]});toast('🎨 '+labels[next])}
    function toast(msg){let el=document.querySelector('.toast');if(!el){el=document.createElement('div');el.className='toast';document.body.appendChild(el)}el.textContent=msg;el.style.opacity='1';clearTimeout(el._t);el._t=setTimeout(()=>{el.style.opacity='0'},2000)}

    /* ═══════════════════ PARTICLES ═══════════════════ */
    (function(){const c=document.getElementById('particles-canvas'),ctx=c.getContext('2d');let ps=[];function rz(){c.width=innerWidth;c.height=innerHeight}rz();addEventListener('resize',rz);
      for(let i=0;i<42;i++)ps.push({x:Math.random()*c.width,y:Math.random()*c.height,sz:Math.random()*2+0.4,sx:(Math.random()-0.5)*0.25,sy:(Math.random()-0.5)*0.25-0.08,op:Math.random()*0.55+0.08,pl:Math.random()*Math.PI*2});
      function dr(){ctx.clearRect(0,0,c.width,c.height);const a=getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()||'#e879a0';
        ps.forEach(p=>{p.x+=p.sx;p.y+=p.sy;p.pl+=0.02;if(p.x<0)p.x=c.width;if(p.x>c.width)p.x=0;if(p.y<0)p.y=c.height;if(p.y>c.height)p.y=0;
          ctx.beginPath();ctx.arc(p.x,p.y,p.sz,0,Math.PI*2);ctx.fillStyle=a;ctx.globalAlpha=p.op*(0.6+0.4*Math.sin(p.pl));ctx.fill();
          for(let j=0;j<ps.length;j++){const dx=p.x-ps[j].x,dy=p.y-ps[j].y,dist=Math.sqrt(dx*dx+dy*dy);if(dist<110){ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(ps[j].x,ps[j].y);ctx.strokeStyle=a;ctx.globalAlpha=0.035*(1-dist/110);ctx.lineWidth=0.5;ctx.stroke()}}
        });ctx.globalAlpha=1;requestAnimationFrame(dr);
      }dr();
    })();

    /* ═══════════════════ INIT ═══════════════════ */
    document.addEventListener('DOMContentLoaded',()=>{
      runBoot();
      const el=document.getElementById('welcome-msg');if(el)el.textContent='Привет! Я Аура. Чем могу помочь?';
      setTimeout(()=>{const btn=document.querySelector('#welcome-msg')?.closest('.msg')?.querySelector('.btn-tts');if(btn)ttsSpeak(btn)},1500);
      fetch('/api/skills').then(r=>r.json()).then(data=>{const bad=document.getElementById('badge-skills');if(bad){const n=Object.keys(data.skills||{}).length;bad.textContent=n;bad.style.display=''}}).catch(()=>{});
      fetch('/api/calendar?days=90').then(r=>r.json()).then(d=>{const bad=document.getElementById('badge-calendar');if(bad){const now=new Date();const n=(d.events||[]).filter(e=>e.event_date&&e.event_date.startsWith(now.toISOString().slice(0,7))).length;bad.textContent=n;if(n)bad.style.display=''}}).catch(()=>{});
    });
  }