const state = { projects: [], summary: null, current: null, view: 'overview', apiBaseUrl: '' };
const $ = (selector) => document.querySelector(selector);
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const day = ms => ms == null ? 'No date' : new Date(ms).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'});
const localDate = ms => { if (ms == null) return ''; const d = new Date(ms); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };

async function request(path, options) {
  const response = await fetch(path, { ...options, headers: {'Content-Type':'application/json', ...(options?.headers || {})} });
  let result;
  try { result = await response.json(); } catch { throw new Error('Unexpected response from local server'); }
  if (!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

let toastTimer;
function toast(message) {
  const node = $('#toast'); node.textContent = message; node.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => node.classList.remove('show'), 3500);
}

function card(project, row) {
  const attention = row?.overdue?.length || 0;
  const percent = project.items?.length ? Math.round(project.items.filter(x => x.done).length / project.items.length * 100) : 0;
  return `<button class="project-card" data-project="${escapeHtml(project.id)}">
    <div class="card-top"><h3>${escapeHtml(project.title)}</h3><span class="status ${escapeHtml(project.status)}">${escapeHtml(project.status)}</span></div>
    <p>${escapeHtml(project.description || 'No description')}</p>
    <div class="card-bottom"><span>${project.items?.length || 0} tasks · ${percent}% complete</span><span class="${attention || project.status === 'blocked' ? 'attention' : ''}">${attention ? `${attention} overdue` : project.status === 'blocked' ? 'Needs attention' : 'View tasks ↗'}</span></div>
  </button>`;
}

function render() {
  const rows = state.summary?.projects || [];
  const byId = new Map(rows.map(row => [row.id, row]));
  const overdue = rows.reduce((n, row) => n + row.overdue.length, 0);
  const blocked = rows.filter(row => row.stuck).length;
  const changed = rows.filter(row => row.changed_this_week).length;
  $('#metrics').innerHTML = [
    ['Projects', state.projects.length, 'Across the workspace', ''],
    ['Need attention', blocked, 'Blocked or overdue', 'alert'],
    ['Overdue tasks', overdue, 'Open tasks past due', 'alert'],
    ['Updated this week', changed, 'Based on latest timestamp', '']
  ].map(([label, n, note, cls]) => `<div class="metric ${cls}"><div class="label">${label}</div><strong>${n}</strong><small>${note}</small></div>`).join('');
  const ranked = [...state.projects].sort((a,b) => Number(byId.get(b.id)?.stuck || false) - Number(byId.get(a.id)?.stuck || false) || (byId.get(b.id)?.overdue.length || 0) - (byId.get(a.id)?.overdue.length || 0));
  $('#overview-projects').innerHTML = ranked.map(p => card(p, byId.get(p.id))).join('');
  renderAllProjects();
  $('#last-updated').textContent = `Refreshed ${new Date().toLocaleTimeString([], {hour:'numeric', minute:'2-digit'})}`;
}

function renderAllProjects() {
  const query = $('#search').value.toLowerCase().trim();
  const status = $('#status-filter').value;
  const byId = new Map((state.summary?.projects || []).map(row => [row.id, row]));
  const shown = state.projects.filter(p => {
    const matchesStatus = !status || (status === 'overdue' ? (byId.get(p.id)?.overdue.length || 0) > 0 : p.status === status);
    const matchesSearch = !query || `${p.title} ${p.description} ${(p.items || []).map(i => i.task).join(' ')}`.toLowerCase().includes(query);
    return matchesStatus && matchesSearch;
  });
  $('#all-projects').innerHTML = shown.length ? shown.map(p => card(p, byId.get(p.id))).join('') : '<p class="empty">No projects match that search.</p>';
}

async function refresh() {
  $('#refresh').disabled = true;
  try {
    const [projects, report] = await Promise.all([request('/api/projects'), request('/api/summary')]);
    state.projects = projects.projects; state.apiBaseUrl = projects.api_base_url; state.summary = report; render();
    if (state.current) openProject(state.current);
  } catch (error) { toast(error.message); }
  finally { $('#refresh').disabled = false; }
}

function showView(view) {
  state.view = view;
  document.querySelectorAll('.view').forEach(node => node.classList.toggle('hidden', node.id !== `${view}-view`));
  document.querySelectorAll('.nav').forEach(node => node.classList.toggle('active', node.dataset.view === view));
  $('#crumb').textContent = ({overview:'Overview',projects:'Projects',automations:'Automations',ai:'AI tools'})[view];
}

function closeProject() { state.current = null; $('#drawer').classList.add('hidden'); $('#drawer-backdrop').classList.add('hidden'); }

async function openProject(id) {
  try {
    const p = await request(`/api/projects/${encodeURIComponent(id)}`); state.current = id;
    const today = localDate(Date.now());
    const activeProject = !['wrapped', 'dropped'].includes(String(p.status || '').toLowerCase());
    const todos = (p.items || []).map(t => {
      const hasDueDate = Number.isFinite(t.by);
      const late = activeProject && !t.done && hasDueDate && localDate(t.by) < today;
      const stateLabel = t.done ? 'Done' : late ? 'Overdue' : 'Open';
      const stateClass = t.done ? 'complete' : late ? 'overdue' : 'open';
      const ownerLabel = t.who ? `Assigned to ${escapeHtml(t.who)}` : 'Unassigned';
      return `<article class="todo ${t.done ? 'done' : ''} ${late ? 'is-overdue' : ''}">
        <label class="todo-main"><input type="checkbox" data-todo="${escapeHtml(t.id)}" aria-label="${t.done ? 'Reopen' : 'Complete'} ${escapeHtml(t.task)}" ${t.done ? 'checked' : ''}><span class="todo-primary"><span class="task-name">${escapeHtml(t.task)}</span><span class="task-owner">${ownerLabel}</span></span></label>
        <div class="todo-details"><span class="todo-date">${hasDueDate ? `Due <time datetime="${localDate(t.by)}">${day(t.by)}</time>` : 'No due date'}</span><span class="todo-state ${stateClass}">${stateLabel}</span></div>
        <div class="todo-actions"><button type="button" class="copy-request" data-copy-automation-url="${escapeHtml(t.id)}">Copy automation URL</button><button type="button" class="copy-request" data-copy-curl="${escapeHtml(t.id)}">Copy curl test</button></div>
      </article>`;
    }).join('') || '<p class="empty">No tasks yet.</p>';
    $('#drawer-content').innerHTML = `<div class="eyebrow">PROJECT DETAILS</div><h2>${escapeHtml(p.title)}</h2><span class="status ${escapeHtml(p.status)}">${escapeHtml(p.status)}</span><p class="description">${escapeHtml(p.description || 'No description')}</p><div class="meta"><span>${(p.items || []).filter(t => t.done).length} of ${(p.items || []).length} done</span><span>Updated ${day(p.updated_at)}</span></div><div class="task-head"><h3>Tasks</h3></div><div id="todo-list">${todos}</div><form id="add-form" class="form"><h3>Add a task</h3><label>Task<input name="task" required placeholder="What needs doing?"></label><label>Assignee<input name="who" required placeholder="Person's name"></label><label>Due date<input name="due" type="date" required></label><button class="button" type="submit">Add task</button></form>`;
    $('#drawer').classList.remove('hidden'); $('#drawer-backdrop').classList.remove('hidden');
    $('#add-form').onsubmit = async event => {
      event.preventDefault(); const data = Object.fromEntries(new FormData(event.target));
      try { await request(`/api/projects/${encodeURIComponent(id)}/todos`, {method:'POST', body:JSON.stringify(data)}); toast('Task added'); await refresh(); }
      catch(error) { toast(error.message); }
    };
    $('#todo-list').onchange = async event => {
      if (!event.target.matches('[data-todo]')) return;
      const checkbox = event.target; checkbox.disabled = true;
      try { await request(`/api/projects/${encodeURIComponent(id)}/todos/${encodeURIComponent(checkbox.dataset.todo)}/mark`, {method:'POST', body:JSON.stringify({done:checkbox.checked})}); toast(checkbox.checked ? 'Task completed' : 'Task reopened'); await refresh(); }
      catch(error) { checkbox.checked = !checkbox.checked; checkbox.disabled = false; toast(error.message); }
    };
    $('#todo-list').onclick = async event => {
      const button = event.target.closest('[data-copy-automation-url], [data-copy-curl]');
      if (!button) return;
      const todoId = button.dataset.copyAutomationUrl || button.dataset.copyCurl;
      const url = `${state.apiBaseUrl}/api/v1/proj/${encodeURIComponent(id)}/items/${encodeURIComponent(todoId)}/mark`;
      const quotedUrl = `'${url.replaceAll("'", "'\\''")}'`;
      try {
        if (button.dataset.copyAutomationUrl) {
          await navigator.clipboard.writeText(url);
          toast('Automation URL copied');
        } else {
          await navigator.clipboard.writeText(`curl -i -X POST ${quotedUrl} -H 'Content-Type: application/json' -d '{"flag":"yes"}'`);
          toast('Runnable curl command copied');
        }
      } catch { toast('Clipboard unavailable in this browser'); }
    };
  } catch (error) { toast(error.message); }
}

document.querySelectorAll('.nav').forEach(node => node.addEventListener('click', () => showView(node.dataset.view)));
document.addEventListener('click', event => { const card = event.target.closest('[data-project]'); if (card) openProject(card.dataset.project); });
$('#search').addEventListener('input', renderAllProjects);
$('#status-filter').addEventListener('change', renderAllProjects);
$('#refresh').addEventListener('click', refresh);
$('#close-drawer').addEventListener('click', closeProject);
$('#drawer-backdrop').addEventListener('click', closeProject);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeProject(); });
$('#webhook-url').textContent = `${location.origin}/api/automation/complete`;
refresh();
