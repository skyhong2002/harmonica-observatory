import { t, getLocale, locales, countryName } from './i18n.js';
import { esc, icon, link, number, textMatch, platformName, sourceType, pastEvent, image, safeUrl, date } from './utils.js';
import { postCard, eventCard } from './views.js';
import { storyEmptyMarkup } from './stories.js';

// Keep this storage namespace compatible with preferences from the previous UI.
export const COLUMN_KEY = 'atlas-columns';
const PAGE_SIZE = 24;
const MAX_COLUMNS = 6;
const words = {
  worldwide: ['Worldwide updates', '全球動態', '世界の最新情報', '세계 소식'],
  add: ['Add column', '新增河道', 'カラムを追加', '열 추가'],
  remove: ['Remove column', '移除河道', 'カラムを削除', '열 삭제'],
  previous: ['Previous column', '上一條河道', '前のカラム', '이전 열'],
  next: ['Next column', '下一條河道', '次のカラム', '다음 열'],
  preview: ['Story preview', '限動預覽', 'ストーリープレビュー', '스토리 미리보기'],
  video: ['Video story', '影片限動', '動画ストーリー', '동영상 스토리'],
  unavailablePreview: ['Preview unavailable', '預覽目前無法載入', 'プレビューを読み込めません', '미리보기를 불러올 수 없습니다'],
  noPreview: ['No preview provided', '來源未提供預覽', 'プレビューは提供されていません', '제공된 미리보기가 없습니다'],
  expires: ['Expires', '有效至', '公開期限', '만료'],
  expiryUnknown: ['Expiry time unavailable', '未提供到期時間', '公開期限は不明です', '만료 시간 정보 없음'],
  archived: ['Story archive', '限動封存', 'ストーリーアーカイブ', '스토리 보관함'],
  feed: ['Feed', '河道', 'フィード', '피드'],
  all: ['All updates', '全部動態', 'すべての投稿', '모든 소식'],
  filtered: ['Filtered', '已篩選', '絞り込み中', '필터 적용'],
};
const r = (key) => words[key]?.[locales.indexOf(getLocale())] || words[key]?.[0] || t(key);
const fields = ['q', 'country', 'platform', 'type', 'kind', 'followed'];
export function newColumn(mode = 'posts') {
  return { mode: mode === 'events' ? 'events' : 'posts', q: '', country: '', platform: '', type: '', kind: '', followed: mode === 'following' };
}
export function defaultColumns() { return [newColumn(), newColumn('following'), newColumn('events')]; }
export function normalizeColumns(value) {
  if (!Array.isArray(value)) return defaultColumns();
  const result = value.filter(c => c && typeof c === 'object' && ['posts', 'events', 'feed'].includes(c.mode || c.t)).slice(0, MAX_COLUMNS).map(c => {
    const col = newColumn(c.mode || c.t);
    for (const k of fields) if (typeof c[k] === 'string') col[k] = c[k].slice(0, 300);
    col.followed = c.followed === true;
    if (!['', 'stories', 'following'].includes(col.kind)) col.kind = '';
    return col;
  });
  return result.length ? result : defaultColumns();
}
export function loadColumns(storage = globalThis.localStorage) {
  try { return normalizeColumns(JSON.parse(storage?.getItem(COLUMN_KEY) || 'null')); } catch { return defaultColumns(); }
}
function saveColumns(cols) { try { globalThis.localStorage?.setItem(COLUMN_KEY, JSON.stringify(cols)); } catch {} }
export function activeStories(catalog, now = Date.now()) {
  return (catalog.stories || []).filter(p => p.sourceAvailable !== false && !['expired', 'unknown', 'archived'].includes(p.storyState) && (!p.expiresAt || Date.parse(p.expiresAt) > now));
}
export function filterColumn(catalog, col, following = new Set()) {
  const sources = new Map((catalog.sources || []).map(s => [s.id, s]));
  const eventMode = col.mode === 'events';
  const sourcesByPostUrl = new Map();
  if (eventMode) for (const post of catalog.posts || []) {
    if (!post.url || !post.sourceId) continue;
    if (!sourcesByPostUrl.has(post.url)) sourcesByPostUrl.set(post.url, new Set());
    sourcesByPostUrl.get(post.url).add(post.sourceId);
  }
  const rows = eventMode ? (catalog.events || []).filter(e => !pastEvent(e)) : catalog.posts || [];
  return rows.filter(row => {
    const ids = new Set(row.sourceId ? [row.sourceId] : []);
    if (eventMode) for (const url of [row.url, row.sourceUrl]) {
      for (const id of sourcesByPostUrl.get(url) || []) ids.add(id);
    }
    // Event location remains authoritative; source country fills only absent metadata.
    const matchesSource = [...ids].some(id => {
      const source = sources.get(id);
      return (!col.type || source?.type === col.type) &&
        (!(col.followed || col.kind === 'following') || following.has(id)) &&
        (!col.country || row.countryCode || source?.countryCode === col.country);
    });
    const needsSource = col.type || col.followed || col.kind === 'following' || (col.country && !row.countryCode);
    return (!col.country || !row.countryCode || row.countryCode === col.country) &&
      (!col.platform || row.platform === col.platform) &&
      (!needsSource || matchesSource) &&
      (col.kind !== 'stories' || row.isStory) && textMatch(row, col.q);
  });
}
export function storyStrip(catalog) {
  const stories = activeStories(catalog);
  return `<section class="story-strip${stories.length ? ' has-stories' : ''}" aria-label="${esc(t('stories'))}">${stories.length ? stories.map(p => {
    const source = (catalog.sources || []).find(s => s.id === p.sourceId);
    const name = p.sourceName || source?.name || t('source');
    const preview = image(p.image, 'story-preview', `${name} · ${r('preview')}`);
    const video = safeUrl(p.videoUrl);
    const media = video ? `<video class="story-preview story-video" controls playsinline preload="none" ${safeUrl(p.image) ? `poster="${esc(safeUrl(p.image))}"` : ''} aria-label="${esc(name + ' · ' + r('video'))}"><source src="${esc(video)}">${esc(r('video'))}</video>` : link(p.url, `${preview}<span class="story-preview-missing">${icon('layers')}<span>${esc(r(preview ? 'unavailablePreview' : 'noPreview'))}</span></span>`, 'story-media-link', `aria-label="${esc(name + ' · ' + t('original'))}"`);
    const expiry = p.expiresAt && Number.isFinite(Date.parse(p.expiresAt)) ? `<time datetime="${esc(p.expiresAt)}">${esc(r('expires'))} ${esc(date(p.expiresAt, { year: undefined, hour: '2-digit', minute: '2-digit' }))}</time>` : `<span>${esc(r('expiryUnknown'))}</span>`;
    return `<article class="story-item" data-story-id="${esc(p.id || p.url || '')}"><div class="story-media">${media}</div><div class="story-caption"><strong class="story-name" title="${esc(name)}">${esc(name)}</strong><div class="story-expiry">${expiry}</div>${link(p.url, esc(t('original')), 'story-original')}</div></article>`;
  }).join('') : storyEmptyMarkup(catalog)}</section>`;
}
function title(col) { return col.mode === 'events' ? t('upcoming') : col.followed || col.kind === 'following' ? t('following') : col.country ? countryName(col.country) : r('worldwide'); }
function options(rows, value) { return rows.map(([key, label]) => `<option value="${esc(key)}" ${key === value ? 'selected' : ''}>${esc(label)}</option>`).join(''); }
function filterMenu(col, catalog, mobile) {
  const select = (key, label, opts) => `<label>${label}<select data-river-field="${key}">${options(opts, col[key])}</select></label>`;
  return `<div class="col-picker-menu col-menu-filters"><label class="river-search-label">${t('search')}<input type="search" data-river-field="q" class="cf-q" value="${esc(col.q)}" placeholder="${esc(t('searchPlaceholder'))}" autocomplete="off"></label>${select('country', t('country'), [['', t('allCountries')], ...(catalog.countries || []).map(c => [c.code, countryName(c.code, c.name)])])}${col.mode !== 'events' ? select('platform', t('platform'), [['', t('allPlatforms')], ...[...new Set(catalog.posts.map(p => p.platform).filter(Boolean))].sort().map(p => [p, platformName(p)])]) + select('type', t('type'), [['', t('allTypes')], ...[...new Set(catalog.sources.map(s => s.type).filter(Boolean))].sort().map(v => [v, sourceType(v)])]) + select('kind', t('postKind'), [['', r('all')], ['stories', r('archived')]]) : ''}<label class="river-follow-filter"><input type="checkbox" data-river-field="followed" ${col.followed || col.kind === 'following' ? 'checked' : ''}>${t('following')}</label><button type="button" data-river-reset>${t('reset')}</button>${mobile ? '' : `<button type="button" class="col-remove" data-river-remove>${icon('close')}${r('remove')}</button>`}</div>`;
}
function results(col, catalog, following, shown = PAGE_SIZE) {
  const rows = filterColumn(catalog, col, following);
  return `${rows.slice(0, shown).map(row => col.mode === 'events' ? eventCard(row) : postCard(row, catalog.sources, following, catalog.events)).join('') || `<div class="river-empty"><p>${t('noResults')}</p><span>${t('noResultsBody')}</span></div>`}<div class="river-result-count" role="status">${t('showing', {shown: number(Math.min(shown, rows.length)), total: number(rows.length)})}</div>${rows.length > shown ? `<button type="button" class="button button-outline feed-more" data-river-more>${t('loadMore')}</button>` : ''}`;
}
function column(col, index, catalog, following, mobile = false) {
  const filtered = fields.some(k => col[k]);
  return `<section class="feed-col${mobile ? ' river-mobile' : ''}" data-river-column="${index}" aria-label="${esc(title(col))}" tabindex="0"><header class="feed-col-head"><details class="col-picker ${filtered ? 'fon' : ''}"><summary><span class="feed-col-dot ${col.mode === 'events' ? 'dot-events' : col.followed ? 'dot-following' : 'dot-all'}"></span><h2>${esc(title(col))}</h2><span class="caret">${filtered ? r('filtered') : t('filter')}${icon('chevron')}</span></summary>${filterMenu(col, catalog, mobile)}</details></header><div class="river-results">${results(col, catalog, following)}</div></section>`;
}
function addMenu() {
  return `<details class="deck-add"><summary aria-label="${r('add')}" title="${r('add')}">${icon('plus')}</summary><div class="addcol-menu"><span class="addcol-title">${r('add')}</span>${[['posts', t('posts')], ['following', t('following')], ['events', t('upcoming')]].map(([key, label]) => `<button type="button" data-river-add="${key}">${label}</button>`).join('')}</div></details>`;
}
const snapshots = new WeakMap();
const scrollSnapshots = new Map();
// URL facets seed the first column; each additional column retains its own facets.
export function riverView(catalog, state = {}, following = new Set(), options = {}) {
  const columns = loadColumns();
  const first = columns.find(c => c.mode === 'posts');
  if (first) for (const key of fields) first[key] = state[key] ?? (key === 'followed' ? false : '');
  const mobile = { ...newColumn(), ...Object.fromEntries(fields.map(k => [k, state[k] ?? (k === 'followed' ? false : '')])) };
  const snapshot = { columns, mobile };
  snapshots.set(catalog, snapshot);
  return `<section class="river" aria-label="${esc(r('feed'))}">${options.stories === false ? '' : storyStrip(catalog)}<div class="river-deck-wrap"><div class="feed-cols" style="--ncols:${columns.length}">${columns.map((col, i) => column(col, i, catalog, following)).join('')}${columns.length < MAX_COLUMNS ? addMenu() : ''}</div><button type="button" class="deck-nav deck-prev" data-river-nav="-1" aria-label="${r('previous')}">${icon('chevron')}</button><button type="button" class="deck-nav deck-next" data-river-nav="1" aria-label="${r('next')}">${icon('chevron')}</button></div>${column(mobile, 'mobile', catalog, following, true)}</section>`;
}

export function bindRiver(root, { catalog, following = new Set(), onStateChange = () => {} } = {}) {
  const river = root.querySelector('.river');
  if (!river || !catalog) return () => {};
  const { columns, mobile } = snapshots.get(catalog) || { columns: loadColumns(), mobile: newColumn() };
  const deck = river.querySelector('.feed-cols');
  const shown = new Map();
  const scrollKey = globalThis.location?.pathname || '/';
  const priorScroll = scrollSnapshots.get(scrollKey);
  if (priorScroll) {
    deck.scrollLeft = priorScroll.left;
    for (const node of river.querySelectorAll('[data-river-column]')) {
      const saved = priorScroll.columns[node.dataset.riverColumn];
      if (saved && saved.filters === JSON.stringify(node.dataset.riverColumn === 'mobile' ? mobile : columns[Number(node.dataset.riverColumn)])) {
        if (saved.shown > PAGE_SIZE) {
          shown.set(node, saved.shown);
          node.querySelector('.river-results').innerHTML = results(node.dataset.riverColumn === 'mobile' ? mobile : columns[Number(node.dataset.riverColumn)], catalog, following, saved.shown);
        }
        node.scrollTop = saved.top;
      }
    }
  }
  const timers = new Map();
  const composing = new WeakSet();
  const firstIndex = () => columns.findIndex(c => c.mode === 'posts');
  const nodeColumn = el => el.closest('[data-river-column]');
  const model = node => node.dataset.riverColumn === 'mobile' ? mobile : columns[Number(node.dataset.riverColumn)];
  const statePatch = col => Object.fromEntries(fields.map(k => [k, col[k]]));
  function updateCount() {
    deck.style.setProperty('--ncols', columns.length);
    deck.querySelectorAll('[data-river-remove]').forEach(b => { b.disabled = columns.length <= 1; });
    const maximum = deck.scrollWidth - deck.clientWidth;
    for (const b of river.querySelectorAll('[data-river-nav]')) {
      b.hidden = maximum <= 2;
      b.disabled = b.dataset.riverNav === '-1' ? deck.scrollLeft <= 2 : deck.scrollLeft >= maximum - 2;
    }
  }
  function refresh(node, col, reset = true) {
    if (reset) shown.delete(node);
    node.querySelector('.river-results').innerHTML = results(col, catalog, following, shown.get(node) || PAGE_SIZE);
    node.querySelector('h2').textContent = title(col);
    node.setAttribute('aria-label', title(col));
    const filtered = fields.some(k => col[k]);
    node.querySelector('.col-picker').classList.toggle('fon', filtered);
    node.querySelector('.caret').innerHTML = (filtered ? r('filtered') : t('filter')) + icon('chevron');
  }
  function syncControls(node, col) {
    node.querySelectorAll('[data-river-field]').forEach(field => {
      const key = field.dataset.riverField;
      if (field.type === 'checkbox') field.checked = key === 'followed' ? !!(col.followed || col.kind === 'following') : !!col[key];
      else field.value = col[key];
    });
  }
  function change(input) {
    const node = nodeColumn(input);
    if (!node) return;
    const col = model(node);
    const key = input.dataset.riverField;
    col[key] = input.type === 'checkbox' ? input.checked : input.value;
    if (key === 'followed' && col.kind === 'following') col.kind = '';
    refresh(node, col);
    // First desktop feed and the mobile combined feed share URL facets, not locale.
    if (node.dataset.riverColumn === 'mobile' || Number(node.dataset.riverColumn) === firstIndex()) {
      const other = node.dataset.riverColumn === 'mobile' ? columns[firstIndex()] : mobile;
      if (other) Object.assign(other, statePatch(col));
      const otherNode = river.querySelector(`[data-river-column="${node.dataset.riverColumn === 'mobile' ? firstIndex() : 'mobile'}"]`);
      if (otherNode) {
        refresh(otherNode, other);
        syncControls(otherNode, other);
      }
      onStateChange(statePatch(col));
    }
    saveColumns(columns);
  }
  function onInput(e) {
    if (!e.target.matches('[data-river-field="q"]') || composing.has(e.target) || e.isComposing) return;
    clearTimeout(timers.get(e.target));
    timers.set(e.target, setTimeout(() => { timers.delete(e.target); change(e.target); }, 180));
  }
  function onCompositionStart(e) { composing.add(e.target); clearTimeout(timers.get(e.target)); }
  function onCompositionEnd(e) { composing.delete(e.target); onInput(e); }
  function onChange(e) { if (e.target.matches('[data-river-field]:not([data-river-field="q"])')) change(e.target); }
  function onClick(e) {
    const button = e.target.closest('button');
    if (!button) return;
    const node = nodeColumn(button);
    if (button.hasAttribute('data-river-more')) {
      shown.set(node, (shown.get(node) || PAGE_SIZE) + PAGE_SIZE);
      refresh(node, model(node), false);
    }
    if (button.hasAttribute('data-river-reset')) {
      const col = model(node);
      Object.assign(col, newColumn(col.mode));
      node.querySelectorAll('[data-river-field]').forEach(field => { if (field.type === 'checkbox') field.checked = false; else field.value = ''; });
      change(node.querySelector('[data-river-field="q"]'));
    }
    if (button.hasAttribute('data-river-remove') && columns.length > 1) {
      columns.splice(Number(node.dataset.riverColumn), 1);
      node.remove();
      deck.querySelectorAll('[data-river-column]').forEach((n, i) => { n.dataset.riverColumn = i; });
      if (!deck.querySelector('.deck-add')) deck.insertAdjacentHTML('beforeend', addMenu());
      saveColumns(columns); updateCount();
      const first = columns[firstIndex()];
      if (first) {
        Object.assign(mobile, statePatch(first));
        onStateChange(statePatch(first));
        const mobileNode = river.querySelector('.river-mobile');
        refresh(mobileNode, mobile);
        syncControls(mobileNode, mobile);
      }
      deck.querySelector('.col-picker summary')?.focus();
    }
    if (button.dataset.riverAdd && columns.length < MAX_COLUMNS) {
      const col = newColumn(button.dataset.riverAdd);
      columns.push(col);
      const add = deck.querySelector('.deck-add');
      add.insertAdjacentHTML('beforebegin', column(col, columns.length - 1, catalog, following));
      add.open = false;
      if (columns.length >= MAX_COLUMNS) add.remove();
      saveColumns(columns); updateCount();
      const added = deck.querySelector(`[data-river-column="${columns.length - 1}"]`);
      added.querySelector('summary').focus({ preventScroll: true });
      deck.scrollLeft = added.offsetLeft - deck.offsetLeft;
    }
    if (button.dataset.riverNav) {
      const step = (deck.querySelector('.feed-col')?.getBoundingClientRect().width || 420) + 12;
      if (deck.scrollBy) deck.scrollBy({ left: Number(button.dataset.riverNav) * step, behavior: 'smooth' });
      else deck.scrollLeft += Number(button.dataset.riverNav) * step;
    }
  }
  let gx = 0, gy = 0, lastWheel = 0, axis = null, touch = null;
  function wheel(e) {
    if (e.ctrlKey) return;
    if (Date.now() - lastWheel > 180) { gx = 0; gy = 0; axis = null; }
    lastWheel = Date.now();
    gx += Math.abs(e.deltaX); gy += Math.abs(e.deltaY);
    if (e.shiftKey && !e.deltaX) axis = 'x';
    else if (!axis && (gx > 6 || gy > 6)) axis = gx > gy ? 'x' : 'y';
    if (axis !== 'x') return;
    const dx = (e.deltaX || (e.shiftKey ? e.deltaY : 0)) * (e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? deck.clientWidth : 1);
    if (deck.scrollWidth > deck.clientWidth) { e.preventDefault(); deck.scrollLeft += dx; }
  }
  function touchStart(e) { if (e.touches.length === 1) touch = { x: e.touches[0].clientX, y: e.touches[0].clientY, left: deck.scrollLeft, axis: null }; }
  function touchMove(e) {
    if (!touch || e.touches.length !== 1) return;
    const dx = e.touches[0].clientX - touch.x, dy = e.touches[0].clientY - touch.y;
    if (!touch.axis && Math.max(Math.abs(dx), Math.abs(dy)) > 8) touch.axis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y';
    if (touch.axis === 'x' && deck.scrollWidth > deck.clientWidth) { if (e.cancelable) e.preventDefault(); deck.scrollLeft = touch.left - dx; }
  }
  function touchEnd() { touch = null; }
  function escape(e) { if (e.key === 'Escape') river.querySelectorAll('details[open]').forEach(d => { d.open = false; d.querySelector('summary')?.focus(); }); }
  const listeners = [[river,'input',onInput], [river,'change',onChange], [river,'click',onClick], [river,'compositionstart',onCompositionStart], [river,'compositionend',onCompositionEnd], [river,'keydown',escape], [deck,'scroll',updateCount], [deck,'wheel',wheel,{passive:false}], [deck,'touchstart',touchStart,{passive:true}], [deck,'touchmove',touchMove,{passive:false}], [deck,'touchend',touchEnd,{passive:true}], [deck,'touchcancel',touchEnd,{passive:true}], [window,'resize',updateCount]];
  for (const [node, type, handler, options] of listeners) node.addEventListener(type,handler,options);
  updateCount();
  // Remove tiles at their real expiry even when a page is left open. Never
  // rebuild live video previews on a polling interval or include archived posts.
  let storyExpiryTimer;
  function scheduleStoryExpiry() {
    clearTimeout(storyExpiryTimer);
    const expiries = activeStories(catalog).map(p => Date.parse(p.expiresAt)).filter(Number.isFinite);
    if (!expiries.length) return;
    const delay = Math.min(Math.max(Math.min(...expiries) - Date.now() + 25, 25), 2147483647);
    storyExpiryTimer = setTimeout(() => {
      for (const strip of root.querySelectorAll('.story-strip')) {
        const left = strip.scrollLeft;
        const replacement = document.createElement('div');
        replacement.innerHTML = storyStrip(catalog);
        const updated = replacement.firstElementChild;
        strip.replaceWith(updated);
        updated.scrollLeft = left;
      }
      scheduleStoryExpiry();
      updateCount();
    }, delay);
  }
  scheduleStoryExpiry();
  return () => {
    clearTimeout(storyExpiryTimer);
    scrollSnapshots.set(scrollKey, { left: deck.scrollLeft, columns: Object.fromEntries([...river.querySelectorAll('[data-river-column]')].map(node => [node.dataset.riverColumn, { top: node.scrollTop, shown: shown.get(node) || PAGE_SIZE, filters: JSON.stringify(model(node)) }])) });
    for (const timer of timers.values()) clearTimeout(timer); for (const [node,type,handler,options] of listeners) node.removeEventListener(type,handler,options); };
}
