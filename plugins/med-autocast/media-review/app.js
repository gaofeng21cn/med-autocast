import { App, applyDocumentTheme, applyHostFonts, applyHostStyleVariables } from '@modelcontextprotocol/ext-apps';

const app = new App({ name: 'med-autocast-media-review', version: '0.1.1' }, { tools: { listChanged: false } }, { strict: true });
const root = document.getElementById('app');
const initialFocus = Object.fromEntries(new URLSearchParams(location.search));
const state = { payload: null, input: initialFocus, selectedId: '', selectedShotId: '', note: '', busy: false, error: '' };

function record(value) { return value && typeof value === 'object' && !Array.isArray(value) ? value : {}; }
function escape(value) { return String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])); }
function formatTime(seconds) {
  const total = Math.max(0, Number(seconds) || 0);
  return `${Math.floor(total / 60)}:${String(Math.floor(total % 60)).padStart(2, '0')}`;
}
function localize(value, fallback = '') {
  const labels = record(value);
  return labels['zh-CN'] || labels.zh || labels.en || labels['en-US'] || fallback;
}
function workspaceFocus() { return state.input.workspace_path ? { workspace_path: state.input.workspace_path } : {}; }
function selectedItem() {
  const data = record(state.payload?.data?.data);
  const items = Array.isArray(data.items) ? data.items.filter(item => item && typeof item === 'object') : [];
  return items.find(item => `${item.series_id}/${item.episode_id}` === state.selectedId) || items[0] || null;
}
function selectedShot(item) {
  const shots = Array.isArray(item?.shots) ? item.shots : [];
  return shots.find(shot => shot.id === state.selectedShotId) || item?.selected_shot || shots[0] || null;
}
function artifactHref(item, shot) {
  const ref = item?.media?.artifact_ref;
  if (!ref) return '';
  const params = new URLSearchParams({ ref });
  if (shot?.start !== undefined) params.set('start', String(shot.start));
  if (shot?.end !== undefined) params.set('end', String(shot.end));
  return `opl-workspace://artifact?${params.toString()}`;
}
function applyHostContext(context) {
  if (context?.theme) applyDocumentTheme(context.theme);
  if (context?.styles?.variables) applyHostStyleVariables(context.styles.variables);
  if (context?.styles?.css?.fonts) applyHostFonts(context.styles.css.fonts);
  if (context?.locale) document.documentElement.lang = context.locale;
  if (context?.displayMode) document.documentElement.dataset.displayMode = context.displayMode;
}
function message(text, error = false) {
  state.error = error ? text : '';
  const node = document.querySelector('[role="status"]');
  if (node) node.textContent = text;
}
async function call(name, args) {
  const result = await app.callServerTool({ name, arguments: args });
  if (result.isError) throw new Error(record(result.structuredContent?.error).message || result.content?.find(part => part.type === 'text')?.text || '操作未完成');
  return result.structuredContent || {};
}
function render() {
  const envelope = record(state.payload);
  const result = record(envelope.data);
  const data = record(result.data);
  const items = Array.isArray(data.items) ? data.items.filter(item => item && typeof item === 'object') : [];
  const item = selectedItem();
  const shot = selectedShot(item);
  if (result.state === 'unavailable' && !state.error) state.error = result.reason || '制作工作区读取失败';
  if (state.error) {
    root.innerHTML = `<header class="topbar"><div class="family-heading"><h1>媒体审看</h1><span class="family-label">OPL Apps · Med Auto Cast</span></div></header><div class="error-state" role="alert"><div><strong>${state.error.includes('登记制作工作区') ? '尚未连接制作工作区' : '媒体审看读取失败'}</strong><p>${escape(state.error)}</p><button class="button" type="button" data-refresh>重新读取</button></div></div>`;
    root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh());
    return;
  }
  if (result.state !== 'ready' || !items.length || !item) {
    root.innerHTML = `<header class="topbar"><div class="family-heading"><h1>媒体审看</h1><span class="family-label">OPL Apps · Med Auto Cast</span></div></header><div class="empty-state" role="status"><div><strong>还没有可审看的登记单集</strong><p>先在 Med Auto Cast 工作区登记系列与单集，再从这里读取当前候选。</p><button class="button" type="button" data-refresh>重新读取</button></div></div>`;
    root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh());
    return;
  }
  const notes = Array.isArray(item.review_notes) ? item.review_notes : [];
  const shots = Array.isArray(item.shots) ? item.shots : [];
  const currentRevision = item.revision || '';
  const currentArtifactHref = artifactHref(item, shot);
  const shotButtons = shots.map(entry => `<button class="shot-button" type="button" data-shot="${escape(entry.id)}" aria-pressed="${entry.id === shot?.id ? 'true' : 'false'}" style="--weight:${Math.max(.5, Number(entry.end) - Number(entry.start) || 1)}"><strong>${escape(entry.title || entry.id)}</strong><small>${escape(formatTime(entry.start))}–${escape(formatTime(entry.end))}</small></button>`).join('');
  root.innerHTML = `<header class="topbar">
    <div class="topbar-copy"><div class="family-heading"><h1>媒体审看</h1><span class="family-label">OPL Apps · Med Auto Cast</span></div><div class="topbar-meta">${state.input.workspace_path ? `<span title="${escape(state.input.workspace_path)}">工作区：${escape(state.input.workspace_path.split(/[\\/]/).filter(Boolean).at(-1))}</span>` : ''}<span>${escape(item.title || `${item.series_id} · ${item.episode_id}`)}</span><span class="badge">${escape(item.status || 'ready')}</span><span class="badge ${item.media ? '' : 'warning'}">${item.media ? '当前候选' : '尚无成片'}</span></div></div>
    <div class="topbar-actions"><button class="button quiet" type="button" data-fullscreen>展开</button><button class="button" type="button" data-refresh>刷新</button></div>
  </header>
  <div class="workspace">
    <aside class="rail" aria-label="媒体选择">
      <section class="rail-section"><h2>制作单</h2><label class="field">系列<select data-series>${[...new Set(items.map(entry => entry.series_id))].map(series => `<option value="${escape(series)}" ${series === item.series_id ? 'selected' : ''}>${escape(series)}</option>`).join('')}</select></label></section>
      <section class="rail-section"><h2>已登记单集 <span class="badge">${items.length}</span></h2><div class="episode-list">${items.map(entry => `<button class="episode-button" type="button" data-episode="${escape(`${entry.series_id}/${entry.episode_id}`)}" aria-current="${entry === item ? 'true' : 'false'}"><strong>${escape(entry.episode_id)}</strong><small>${escape(entry.summary || entry.title || '')}</small></button>`).join('')}</div></section>
    </aside>
    <section class="stage" aria-label="媒体和镜头">
      <div class="stage-header"><div><h2>${escape(item.title || '当前候选')}</h2><p>${escape(item.summary || '选择镜头查看时码和当前候选。')}</p></div>${artifactHref(item, shot) ? `<a class="artifact-link" href="${escape(artifactHref(item, shot))}">打开候选</a>` : ''}</div>
      <div class="media-frame" role="img" aria-label="${escape(shot ? `当前镜头 ${shot.title || shot.id}` : '等待媒体候选')}"><div class="media-placeholder"><strong>${shot ? escape(shot.title || shot.id) : '等待媒体候选'}</strong><p>${shot ? `当前镜头 ${escape(formatTime(shot.start))}–${escape(formatTime(shot.end))}。宿主通过工作区 artifact bridge 打开精确区间。` : '当前工作区尚未登记可打开的候选视频。'}</p>${currentArtifactHref ? `<a class="artifact-link" href="${escape(currentArtifactHref)}">打开当前片段</a>` : ''}</div></div>
      <section class="shot-strip"><div class="shot-strip-header"><h2>镜头时间线</h2><small>${shots.length} 个镜头</small></div><div class="timeline" role="list" aria-label="镜头时间线">${shotButtons || '<span class="empty-state">尚无有效镜头时码。</span>'}</div></section>
      <dl class="detail-grid"><div class="detail-card"><dt>当前版本</dt><dd>${escape(currentRevision || '未生成')}</dd></div><div class="detail-card"><dt>交付审查</dt><dd>${item.delivery_review ? '已有 owner 审查记录' : '尚无交付审查记录'}</dd></div><div class="detail-card"><dt>质量裁决</dt><dd>${item.domain_quality_approved === true ? '由 owner 明确提供' : '本 UI 不代替质量批准'}</dd></div></dl>
    </section>
    <aside class="review-rail" aria-label="审看意见"><header><h2>审看意见</h2><span class="badge">${notes.length}</span></header><div class="note-list" aria-live="polite">${notes.length ? notes.map(note => `<article class="note" data-stale="${note.matches_current_revision === false ? 'true' : 'false'}"><p>${escape(note.note || '')}</p><small>${note.matches_current_revision === false ? '旧版本意见 · ' : ''}${escape(note.request_id || '')}</small></article>`).join('') : '<div class="empty-state">当前版本还没有审看意见。</div>'}</div><form class="note-form"><label class="field" for="note">记录本次审看意见<span class="sr-only">意见文本</span></label><textarea id="note" aria-describedby="note-help" maxlength="20000" placeholder="写下镜头、节奏、构图或听审待办…">${escape(state.note)}</textarea><button class="button primary" type="submit" ${state.busy ? 'disabled' : ''}>${state.busy ? '保存中…' : '记录意见'}</button><small id="note-help">意见绑定当前版本 ${escape(currentRevision)}，不会直接改变质量状态。</small></form></aside>
  </div>`;
  root.querySelector('[data-refresh]')?.addEventListener('click', () => void refresh());
  root.querySelector('[data-fullscreen]')?.addEventListener('click', () => void app.requestDisplayMode({ mode: app.getHostContext()?.displayMode === 'fullscreen' ? 'inline' : 'fullscreen' }).catch(() => {}));
  root.querySelectorAll('[data-episode]').forEach(button => button.addEventListener('click', () => { state.selectedId = button.dataset.episode; state.selectedShotId = ''; const next = selectedItem(); state.input = { ...workspaceFocus(), series_id: next.series_id, episode_id: next.episode_id }; render(); }));
  root.querySelector('[data-series]')?.addEventListener('change', event => { state.input = { ...workspaceFocus(), series_id: event.target.value }; void refresh(); });
  root.querySelectorAll('[data-shot]').forEach(button => button.addEventListener('click', () => { state.selectedShotId = button.dataset.shot; render(); }));
  root.querySelector('#note')?.addEventListener('input', event => { state.note = event.target.value; });
  root.querySelector('.note-form')?.addEventListener('submit', event => { event.preventDefault(); void recordNote(item, shot); });
  app.updateModelContext({ content: [{ type: 'text', text: `正在审看 ${item.title || item.id}${shot ? `，镜头 ${shot.id}` : ''}` }], structuredContent: { navigation: { ...workspaceFocus(), series_id: item.series_id, episode_id: item.episode_id, ...(shot ? { shot_id: shot.id } : {}) }, series_id: item.series_id, episode_id: item.episode_id, revision: item.revision, shot: shot || null } }).catch(() => {});
}
async function refresh() {
  state.error = '';
  message('正在读取当前候选…');
  try {
    const result = await call('open_media_review', state.input);
    const payload = record(result);
    state.payload = payload;
    state.input = record(payload.focus);
    if (state.input.shot_id) state.selectedShotId = state.input.shot_id;
    const item = selectedItem();
    if (item) { state.selectedId = `${item.series_id}/${item.episode_id}`; state.input = { ...workspaceFocus(), series_id: item.series_id, episode_id: item.episode_id }; }
    render();
  } catch (error) { state.error = error?.message || '读取失败'; render(); }
}
async function recordNote(item, shot) {
  const note = state.note.trim();
  if (!note || state.busy) return;
  state.busy = true; render();
  try {
    await call('media_review_note', { ...workspaceFocus(), series_id: item.series_id, episode_id: item.episode_id, shot_id: shot?.id, revision: item.revision, request_id: crypto.randomUUID(), note });
    state.note = '';
    await refresh();
  } catch (error) { state.busy = false; state.error = error?.message || '意见未记录'; render(); }
  finally { state.busy = false; }
}
app.ontoolresult = params => {
  if (params?.isError) { state.error = record(params.structuredContent?.error).message || '读取失败'; render(); return; }
  const payload = record(params?.structuredContent);
  if (payload.data || payload.focus || payload.presentation) { state.payload = payload; state.input = record(payload.focus); if (state.input.series_id && state.input.episode_id) state.selectedId = `${state.input.series_id}/${state.input.episode_id}`; state.selectedShotId = state.input.shot_id || ''; const item = selectedItem(); if (item) state.selectedId = `${item.series_id}/${item.episode_id}`; render(); }
};
app.onhostcontextchanged = applyHostContext;
await app.connect();
applyHostContext(app.getHostContext?.() || {});
// Initial content is supplied by the host's read-only launcher result.
