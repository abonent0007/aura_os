// skills.js — Управление скиллами AURA OS

let editorSkillName = '';
let editorTab = 'skillpy';
let editorCode = {};

async function initSkills() {
    await loadSkills();
}

async function loadSkills() {
    try {
        const res = await fetch('/api/skills');
        const data = await res.json();
        const statsEl = document.getElementById('skillsStats');
        const gridEl = document.getElementById('skillsGrid');
        if (!gridEl) return;

        if (statsEl) {
            const s = data.stats || {};
            statsEl.innerHTML = `Total: ${s.total || 0} | Active: ${s.enabled || 0} | Stable: ${s.stable || 0} | Testing: ${s.testing || 0}`;
        }

        const skills = data.skills || {};
        if (!Object.keys(skills).length) {
            gridEl.innerHTML = '<p>No skills</p>';
            return;
        }

        gridEl.innerHTML = Object.entries(skills).map(([name, info]) => `
            <div class="skill-card ${info.enabled ? '' : 'skill-disabled'}">
                <div class="skill-header">
                    <span class="skill-name">${name}</span>
                    <span class="skill-badge badge-${info.stability || 'testing'}">${info.stability || '?'}</span>
                    ${!info.enabled ? '<span class="skill-badge" style="background:#555;color:#999">disabled</span>' : ''}
                </div>
                <div class="skill-description">${info.description || ''}</div>
                <div class="skill-triggers">
                    ${(info.triggers || []).map(t => `<span class="trigger-tag">${t}</span>`).join('')}
                </div>
                <div class="skill-meta" style="font-size:12px;color:var(--text-muted);margin-bottom:8px">
                    v${info.version} | ${info.tools_count || 0} tools | ${info.errors || 0} errors
                    ${info.auto_created ? ' | AI-generated' : ' | Builtin'}
                </div>
                <div class="skill-actions">
                    <button onclick="toggleSkill('${name}', ${!info.enabled})" class="btn btn-sm">
                        ${info.enabled ? 'Disable' : 'Enable'}
                    </button>
                    <button onclick="openCodeEditor('${name}')" class="btn btn-sm">Edit</button>
                    <button onclick="deleteSkill('${name}')" class="btn btn-sm" style="color:var(--error);border-color:var(--error)">Delete</button>
                </div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Skills error:', e);
    }
}

// ── Create ──

function showCreateSkillModal() {
    document.getElementById('createSkillModal').classList.add('active');
}

function hideCreateSkillModal() {
    document.getElementById('createSkillModal').classList.remove('active');
    document.getElementById('skillDescription').value = '';
    document.getElementById('skillCreationStatus').innerHTML = '';
}

async function createSkill() {
    const desc = document.getElementById('skillDescription')?.value?.trim();
    if (!desc) return;
    const statusEl = document.getElementById('skillCreationStatus');
    statusEl.innerHTML = 'Creating...';

    try {
        const res = await fetch('/api/skills/create', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ description: desc })
        });
        const result = await res.json();
        if (result.success) {
            statusEl.innerHTML = `Skill "${result.skill_name}" created!`;
            setTimeout(hideCreateSkillModal, 1500);
            await loadSkills();
        } else {
            statusEl.innerHTML = `Error: ${(result.errors || []).join('; ')}`;
        }
    } catch (e) {
        statusEl.innerHTML = 'Network error';
    }
}

// ── Code Editor ──

async function openCodeEditor(skillName) {
    editorSkillName = skillName;
    try {
        const res = await fetch(`/api/skills/${skillName}/code`);
        editorCode = await res.json();
        document.getElementById('codeEditorTitle').textContent = `Code: ${skillName}`;
        switchEditorTab('skillpy');
        document.getElementById('codeEditorModal').classList.add('active');
    } catch (e) {
        alert('Failed to load code');
    }
}

function switchEditorTab(tab) {
    editorTab = tab;
    document.getElementById('btn-edit-manifest').classList.toggle('btn-primary', tab === 'manifest');
    document.getElementById('btn-edit-skillmd').classList.toggle('btn-primary', tab === 'skillmd');
    document.getElementById('btn-edit-skillpy').classList.toggle('btn-primary', tab === 'skillpy');

    const key = tab === 'manifest' ? 'manifest.json' : tab === 'skillmd' ? 'SKILL.md' : 'skill.py';
    document.getElementById('codeEditorTextarea').value = editorCode[key] || '';
    document.getElementById('codeEditorStatus').innerHTML = '';
}

function closeCodeEditor() {
    document.getElementById('codeEditorModal').classList.remove('active');
    editorSkillName = '';
    editorCode = {};
}

async function saveSkillCode() {
    const statusEl = document.getElementById('codeEditorStatus');
    const content = document.getElementById('codeEditorTextarea').value;
    const fileKey = editorTab === 'manifest' ? 'manifest.json' : editorTab === 'skillmd' ? 'SKILL.md' : 'skill.py';

    statusEl.innerHTML = 'Saving...';
    try {
        const res = await fetch(`/api/skills/${editorSkillName}/code`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file: fileKey, content: content })
        });
        if (!res.ok) { const err = await res.json(); throw new Error(err.detail); }
        editorCode[fileKey] = content;
        statusEl.innerHTML = 'Saved!';
        setTimeout(() => { statusEl.innerHTML = ''; }, 2000);
    } catch (e) {
        statusEl.innerHTML = `Error: ${e.message}`;
    }
}

// ── Toggle ──

async function toggleSkill(name, enable) {
    try {
        await fetch(`/api/skills/${name}/toggle`, {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ skill_name: name, enabled: enable })
        });
        await loadSkills();
    } catch (e) {
        console.error('Toggle error:', e);
    }
}

// ── Delete ──

async function deleteSkill(name) {
    if (!confirm(`Delete skill "${name}"? This cannot be undone.`)) return;
    try {
        const res = await fetch(`/api/skills/${name}`, { method: 'DELETE' });
        if (!res.ok) {
            const err = await res.json();
            alert(err.detail || 'Cannot delete');
            return;
        }
        await loadSkills();
    } catch (e) {
        alert('Delete failed');
    }
}

document.addEventListener('DOMContentLoaded', initSkills);
