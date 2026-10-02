import { t, getLocale, locales } from './i18n.js';
import { esc, safeUrl, image, link, initials, timestamp } from './utils.js';

const words = {
  empty: ['No active stories have been retrieved yet', '尚未取得有效限動', '有効なストーリーはまだ取得できていません', '아직 유효한 스토리를 가져오지 못했습니다'],
  preview: ['Story preview', '限動預覽', 'ストーリープレビュー', '스토리 미리보기'],
  missing: ['Preview unavailable', '預覽目前無法載入', 'プレビューを読み込めません', '미리보기를 불러올 수 없습니다'],
  expires: ['Shown until', '展示至', '表示期限', '표시 기한'],
  observed: ['Last retrieved', '最近收錄', '最終取得', '최근 수집'],
  browse: ['Browse stories', '瀏覽限時動態', 'ストーリーを見る', '스토리 탐색'],
};
const word = key => words[key][locales.indexOf(getLocale())] || words[key][0];

// The catalog sets a 48-hour display deadline from the original publication time.
export function activeStories(catalog, now = Date.now()) {
  return (catalog.stories || []).filter(story => story.sourceAvailable !== false &&
    !['expired', 'unknown', 'archived'].includes(story.storyState) &&
    Number.isFinite(Date.parse(story.expiresAt)) && Date.parse(story.expiresAt) > now);
}

function storyCard(story, sources) {
  const source = sources.find(item => item.id === story.sourceId);
  const name = story.sourceName || source?.name || t('source');
  const label = `${name} · ${word('preview')}`;
  const video = safeUrl(story.videoUrl), poster = safeUrl(story.image);
  const picture = image(poster, 'ob-story-image', label);
  const media = video
    ? `<video class="ob-story-image" controls playsinline preload="none" ${poster ? `poster="${esc(poster)}"` : ''} aria-label="${esc(label)}"><source src="${esc(video)}"></video>`
    : link(story.url, picture, 'ob-story-media-link', `aria-label="${esc(name + ' · ' + t('original'))}"`);
  const published = Number.isFinite(Date.parse(story.publishedAt))
    ? timestamp(story.publishedAt) : '';
  // Prefer the catalog's cached avatar to an expiring social-CDN address.
  const avatar = image(source?.avatar || story.avatar, '', '');
  return `<article class="ob-story-card" data-story-id="${esc(story.id || story.url || '')}" data-story-expires="${esc(story.expiresAt)}"><div class="ob-story-thumb">${media}<span class="ob-story-fallback" role="status" ${poster || video ? 'hidden' : ''}>${esc(word('missing'))}</span><span class="ob-story-rule" aria-hidden="true"></span><div class="ob-story-header"><span class="ob-story-avatar"><span aria-hidden="true">${esc(initials(name))}</span>${avatar}</span><div class="ob-story-identity"><strong title="${esc(name)}">${esc(name)}</strong>${published}</div></div><div class="ob-story-footer"><span>${esc(word('expires'))} ${timestamp(story.expiresAt)}</span>${link(story.url, esc(t('original')), 'ob-story-original')}</div></div></article>`;
}

function observedContent(catalog) {
  const value = activeStories(catalog).map(story => story.observedAt).filter(value => Number.isFinite(Date.parse(value))).sort((a, b) => Date.parse(b) - Date.parse(a))[0];
  return value ? `${esc(word('observed'))} ${timestamp(value)}` : '';
}
export function storyObservedMarkup(catalog) {
  return `<span class="home-updated" data-story-observed>${observedContent(catalog)}</span>`;
}
export function storiesView(catalog) {
  const stories = activeStories(catalog);
  return `<section class="ob-stories" aria-label="${esc(t('stories'))}"><div class="ob-story-strip" tabindex="0" role="region" aria-label="${esc(word('browse'))}">${stories.length ? stories.map(story => storyCard(story, catalog.sources || [])).join('') : `<p class="ob-story-empty" role="status">${esc(word('empty'))}</p>`}</div></section>`;
}

export function bindStories(root, { catalog, refreshCatalog, onRefresh, refreshOnMount = false, refreshInterval = 60000, refreshTimeout = 15000 } = {}) {
  const strips = [...root.querySelectorAll('.ob-story-strip')];
  if (!catalog || !strips.length) return () => {};
  const owner = root.ownerDocument;
  let timer, refreshTimer, requestTimer, request, busy = false, disposed = false, refreshAgain = false;
  function expire() {
    clearTimeout(timer);
    let next = Infinity;
    for (const strip of strips) {
      for (const card of strip.querySelectorAll('[data-story-expires]')) {
        const expiry = Date.parse(card.dataset.storyExpires);
        if (expiry <= Date.now()) { const focused = card.contains(owner.activeElement); card.remove(); if (focused) strip.focus({ preventScroll: true }); }
        else next = Math.min(next, expiry);
      }
      if (!strip.querySelector('.ob-story-card') && !strip.querySelector('.ob-story-empty')) {
        strip.innerHTML = `<p class="ob-story-empty" role="status">${esc(word('empty'))}</p>`;
      }
    }
    root.querySelectorAll('[data-story-observed]').forEach(node => { node.innerHTML = observedContent(catalog); });
    if (Number.isFinite(next)) timer = setTimeout(expire, Math.min(2147483647, Math.max(1, next - Date.now() + 10)));
  }
  function patch(nextCatalog) {
    const live = activeStories(nextCatalog);
    const wanted = new Set(live.map(story => String(story.id || story.url || '')));
    for (const strip of strips) {
      const left = strip.scrollLeft;
      const existing = new Map([...strip.querySelectorAll('.ob-story-card')].map(card => [card.dataset.storyId, card]));
      for (const [id, card] of existing) {
        if (!wanted.has(id)) {
          const focused = card.contains(owner.activeElement);
          card.remove(); existing.delete(id);
          if (focused) strip.focus({ preventScroll: true });
        }
      }
      if (live.length) strip.querySelector('.ob-story-empty')?.remove();
      for (let i = 0; i < live.length; i++) {
        const story = live[i], id = String(story.id || story.url || '');
        const kept = existing.get(id);
        if (kept) {
          if (kept.dataset.storyExpires !== story.expiresAt) {
            kept.dataset.storyExpires = story.expiresAt;
            const expiry = kept.querySelector('.ob-story-footer > span');
            if (expiry) expiry.innerHTML = `${esc(word('expires'))} ${timestamp(story.expiresAt)}`;
          }
          continue;
        }
        const template = owner.createElement('template');
        template.innerHTML = storyCard(story, nextCatalog.sources || catalog.sources || []);
        const card = template.content.firstElementChild;
        const nextKept = live.slice(i + 1).map(item => existing.get(String(item.id || item.url || ''))).find(Boolean);
        strip.insertBefore(card, nextKept || null); existing.set(id, card);
      }
      strip.scrollLeft = left;
    }
    root.querySelectorAll('[data-story-observed]').forEach(node => { node.innerHTML = observedContent(nextCatalog); });
    expire();
  }
  async function refresh() {
    if (!refreshCatalog || disposed || busy || owner.visibilityState === 'hidden') return;
    busy = true; request = new AbortController();
    try {
      const next = await Promise.race([
        refreshCatalog({ signal: request.signal }),
        new Promise((_, reject) => {
          requestTimer = setTimeout(() => { request.abort(); reject(new Error('timeout')); }, refreshTimeout);
        }),
      ]);
      if (disposed || request.signal.aborted) return;
      if (!next || !Array.isArray(next.stories)) throw new Error('invalid_stories');
      catalog.stories = next.stories;
      onRefresh?.(next);
      patch(next);
    } catch (error) {
      // Keep existing previews until a later automatic retry succeeds.
    } finally {
      clearTimeout(requestTimer);
      busy = false;
      if (refreshAgain && !disposed && owner.visibilityState !== 'hidden') { refreshAgain = false; refresh(); }
    }
  }
  function visibility() {
    if (owner.visibilityState === 'hidden') request?.abort();
    else if (busy && request?.signal.aborted) refreshAgain = true;
    else refresh();
  }
  function keydown(event) {
    if (!event.target.matches('.ob-story-strip') || !['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    const strip = event.target;
    event.preventDefault();
    strip.scrollLeft += (event.key === 'ArrowRight' ? 1 : -1) * ((strip.querySelector('.ob-story-card')?.getBoundingClientRect().width || 180) + 12);
  }
  function mediaError(event) {
    if (event.target.matches('.ob-story-image, .ob-story-image source')) {
      const thumb = event.target.closest('.ob-story-thumb');
      thumb?.classList.add('ob-story-media-failed');
      const fallback = thumb?.querySelector('.ob-story-fallback');
      if (fallback) fallback.hidden = false;
    }
    if (event.target.matches('.ob-story-avatar img')) event.target.hidden = true;
  }
  root.addEventListener('keydown', keydown);
  if (refreshCatalog) {
    owner.addEventListener('visibilitychange', visibility);
    refreshTimer = setInterval(refresh, refreshInterval);
    if (refreshOnMount) refresh();
  }
  root.addEventListener('error', mediaError, true);
  for (const picture of root.querySelectorAll('img.ob-story-image, .ob-story-avatar img')) {
    if (picture.complete && !picture.naturalWidth) mediaError({target:picture});
  }
  expire();
  return () => {
    disposed = true; request?.abort(); clearTimeout(timer); clearTimeout(requestTimer); clearInterval(refreshTimer);
    root.removeEventListener('keydown', keydown); root.removeEventListener('error', mediaError, true);
    owner.removeEventListener('visibilitychange', visibility);
  };
}
