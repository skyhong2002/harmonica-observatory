import { eventText, eventOriginalMarkup } from './event-localization.js';
import { t, getLocale, countryName } from './i18n.js';
import { esc, link, icon, timestamp, number, safeUrl, image, avatar, sourceHref, pastEvent, textMatch, empty, platformName } from './utils.js';
import { pageHeading, filterBar, eventDateLabel } from './views.js';
import { reportLink } from './reporting.js';
import { sourceDisplayName, sourceSummaryMarkup } from './source-names.js';
const labels = {
  'zh-Hant': { reference: '相關原始貼文', snapshot: '相關網站原文', description: '活動整理資訊', endUnknown: '結束時間未公告', poster: '活動圖片', moreImages: '更多活動圖片', video: '相關影片', videoUnavailable: '影片暫時無法載入，查看原始影片', unavailable: '圖片暫時無法載入，請查看原始來源。', share: '分享' },
  en: { reference: 'Related original post', snapshot: 'Original website content', description: 'Event information', endUnknown: 'End time not announced', poster: 'Event image', moreImages: 'More event images', video: 'Related video', videoUnavailable: 'Video unavailable. View the original video.', unavailable: 'Image unavailable. Please view the original source.', share: 'Share' },
  ja: { reference: '関連する元の投稿', snapshot: '関連ウェブサイトの原文', description: 'イベント情報', endUnknown: '終了時刻は未発表', poster: 'イベント画像', moreImages: 'その他のイベント画像', video: '関連動画', videoUnavailable: '動画を読み込めません。元の動画を見る', unavailable: '画像を読み込めません。元の情報をご確認ください。', share: '共有' },
  ko: { reference: '관련 원본 게시물', snapshot: '관련 웹사이트 원문', description: '행사 정보', endUnknown: '종료 시각 미발표', poster: '행사 이미지', moreImages: '행사 이미지 더 보기', video: '관련 동영상', videoUnavailable: '동영상을 불러올 수 없습니다. 원본 동영상 보기', unavailable: '이미지를 불러올 수 없습니다. 원본 출처를 확인하세요.', share: '공유' },
};
const l = key => (labels[getLocale()] || labels.en)[key];

// Match only explicit event IDs or the identity of the actual source post.
// Profile names, author IDs, and generic page links are not event relationships.
export function referenceKey(value) {
  const safe = safeUrl(value);
  if (!safe) return '';
  try {
    const u = new URL(safe, 'https://harmonica.observe.tw');
    const host = u.hostname.toLowerCase().replace(/^(www|m|mobile)\./, '');
    const path = u.pathname.replace(/\/+$/, '');
    if (host === 'instagram.com') {
      const match = path.match(/^\/(?:p|reel|reels|tv)\/([^/]+)/);
      if (match) return `instagram:${match[1]}`;
      const story = path.match(/^\/stories\/[^/]+\/(\d+)$/);
      return story ? `instagram-story:${story[1]}` : '';
    }
    if (['twitter.com', 'x.com'].includes(host)) {
      const match = path.match(/^\/[^/]+\/status\/(\d+)/);
      return match ? `x:${match[1]}` : '';
    }
    if (host === 'youtube.com' || host === 'youtu.be') {
      const id = host === 'youtu.be' ? path.slice(1) : u.searchParams.get('v') || path.match(/^\/(?:shorts|embed)\/([^/]+)/)?.[1];
      return id && /^[a-zA-Z0-9_-]+$/.test(id) ? `youtube:${id}` : '';
    }
    if (host === 'facebook.com') {
      const id = path.match(/\/(?:posts|videos|reel)\/([^/]+)/)?.[1]
        || path.match(/\/photos\/(?:[^/]+\/)*(\d+)$/)?.[1]
        || u.searchParams.get('story_fbid')
        || (/^\/photo(?:\.php)?$/.test(path) ? u.searchParams.get('fbid') : '')
        || (/^\/(?:watch|video\.php)$/.test(path) ? u.searchParams.get('v') : '');
      return id && /^[a-zA-Z0-9_-]+$/.test(id) ? `facebook:${id}` : '';
    }
    if (['threads.net', 'threads.com'].includes(host)) {
      const match = path.match(/^\/@[^/]+\/post\/([^/]+)$/);
      return match ? `threads:${match[1]}` : '';
    }
    u.hash = '';
    for (const key of [...u.searchParams.keys()]) if (/^(utm_|fbclid$|igsh$|igshid$|ref$)/i.test(key)) u.searchParams.delete(key);
    u.searchParams.sort();
    return host + path + (u.searchParams.size ? '?' + u.searchParams : '');
  } catch { return ''; }
}
export function relatedEventPosts(event, posts = []) {
  const references = new Set([event.url, event.sourceUrl].map(referenceKey).filter(Boolean));
  const seen = new Set();
  return posts.filter(post => {
    const matched = post.eventIds?.includes(event.id) || references.has(referenceKey(post.url));
    const identity = post.id || referenceKey(post.url);
    if (!matched || seen.has(identity)) return false;
    seen.add(identity); return true;
  });
}
export function eventRows(catalog, state = {}) {
  return (catalog.events || []).filter(event => (!state.country || event.countryCode === state.country) && textMatch(event, state.q) && (state.period === 'allEvents' || (state.period === 'past' ? pastEvent(event) : !pastEvent(event))))
    .sort((a, b) => (Date.parse(a.start) - Date.parse(b.start)) * (state.period === 'past' ? -1 : 1));
}
function eventAuthor(post, catalog) {
  const source = catalog.sources?.find(source => source.id === post.sourceId);
  const name = source ? sourceDisplayName(source) : post.sourceName || t('source');
  return `<div class="event-author">${link(source ? sourceHref(source) : post.sourceUrl,
    avatar({ ...source, name, avatar: source?.avatar || post.avatar }) +
    `<span class="event-author-identity"><strong>${esc(name)}</strong><span class="event-author-meta"><span>${esc(platformName(post.platform))}</span>${post.publishedAt ? `<span aria-hidden="true">·</span>${timestamp(post.publishedAt, { dateOnly: true })}` : ''}</span></span>`,
    'event-author-link')}</div>`;
}
export function eventDescriptionMarkup(event) {
  return sourceSummaryMarkup({summary: event.description, summaries: event.descriptions, summaryLanguage: event.descriptionLanguage});
}
function originalPost(post, catalog, following, showAuthor = true) {
  const source = catalog.sources?.find(source => source.id === post.sourceId);
  const name = source ? sourceDisplayName(source) : post.sourceName || t('source');
  const expanded = (post.text || '').length <= 240 && (post.text || '').split('\n').length <= 5;
  const followed = source && following.has(source.id);
  return `<section class="event-reference feed-content" data-event-post="${esc(post.id)}">${post.contentKind === 'website_snapshot' ? `<p class="event-reference-label">${l('snapshot')}</p>` : ''}${showAuthor ? eventAuthor(post, catalog) : ''}${post.text ? `<p class="feed-text ${expanded ? 'is-expanded' : ''}">${esc(post.text)}</p>${expanded ? '' : `<button type="button" class="feed-expand" data-expand-post aria-expanded="false">${t('readMore')}</button>`}` : ''}<div class="event-reference-actions">${source ? `<button type="button" class="feed-action ${followed ? 'is-following' : ''}" data-follow="${esc(source.id)}" aria-pressed="${!!followed}" aria-label="${esc(t(followed ? 'unfollow' : 'follow') + ' ' + name)}">${icon(followed ? 'check' : 'heart')}<span>${t(followed ? 'following' : 'follow')}</span></button>` : ''}${link(post.url, t('original'), 'text-link')}</div></section>`;
}
export function richEventCard(event, catalog, following = new Set()) {
  const posts = relatedEventPosts(event, catalog.posts);
  const postImages = posts.flatMap(post => [post.image, ...(Array.isArray(post.images) ? post.images : [])]).map(safeUrl).filter(Boolean);
  const eventImages = [event.image, ...(Array.isArray(event.images) ? event.images : [])].map(safeUrl).filter(Boolean);
  const candidates = [...new Set([...postImages.filter(url => url.startsWith('/')), ...eventImages.filter(url => url.startsWith('/')), ...eventImages, ...postImages])];
  const video = safeUrl(event.videoUrl || posts.find(post => post.videoUrl)?.videoUrl);
  const mainImage = candidates[0];
  // A cached cover corresponds to the first source image in that record's
  // ordered media list. Retain other remote images, even when not cached yet.
  const cachedOriginals = new Set([event, ...posts].flatMap(row => {
    const cover = safeUrl(row.image);
    const first = safeUrl(Array.isArray(row.images) ? row.images[0] : '');
    return cover.startsWith('/') && first && !first.startsWith('/') ? [first] : [];
  }));
  const gallery = candidates.filter(url => url !== mainImage && !cachedOriginals.has(url));
  return `<article class="rich-event-card ${pastEvent(event) ? 'is-past' : ''}" data-event-id="${esc(event.id)}"><header class="rich-event-header">${posts[0] ? eventAuthor(posts[0], catalog) : ''}<div class="eyebrow">${esc(countryName(event.countryCode, event.country))}${pastEvent(event) ? ` · ${t('past')}` : ''}</div><h2>${esc(eventText(event))}</h2>${eventOriginalMarkup(event)}<p class="rich-event-time">${icon('calendar')}<span>${esc(eventDateLabel(event))}${event.allDay ? ` · ${t('allDay')}` : event.endEstimated ? ` · ${l('endUnknown')}` : ''}</span></p><p class="rich-event-location">${icon('pin')}<span>${esc(eventText(event, 'location') || t('locationUnknown'))}</span></p><p class="rich-event-zone">${esc(event.timezone || 'UTC')} · ${t('localTime')}</p></header>${mainImage && !video ? `<figure class="event-media" data-event-media>${link(event.url || event.sourceUrl, image(mainImage, 'event-poster', `${l('poster')}: ${eventText(event)}`), 'event-media-link')}${candidates.length > 1 ? `<span hidden data-event-image-fallback="${esc(JSON.stringify(candidates.slice(1)))}"></span>` : ''}</figure>` : ''}${gallery.length ? `<details class="event-gallery"><summary>${l('moreImages')} (${number(gallery.length)})</summary><div class="event-gallery-strip" tabindex="0" aria-label="${esc(l('moreImages'))}">${gallery.map(url => link(url, image(url, 'event-gallery-image', l('poster')), 'event-gallery-link')).join('')}</div></details>` : ''}${video ? `<video class="event-video" controls preload="metadata" playsinline data-original-video="${esc(safeUrl(event.url || event.sourceUrl || posts[0]?.url))}" ${mainImage ? `poster="${esc(mainImage)}"` : ''} aria-label="${esc(l('video') + ': ' + eventText(event))}" src="${esc(video)}"></video>` : ''}<div class="rich-event-copy">${posts.map((post, index) => originalPost(post, catalog, following, index > 0)).join('')}${event.description ? posts.length ? `<details class="event-description"><summary>${l('description')}</summary>${eventDescriptionMarkup(event)}</details>` : `<div class="event-description-text">${eventDescriptionMarkup(event)}</div>` : ''}<footer class="rich-event-actions">${posts.some(post => safeUrl(post.url) === safeUrl(event.url || event.sourceUrl)) ? '' : link(event.url || event.sourceUrl, t('original'), 'text-link')}<button type="button" class="feed-action" data-share="${esc(event.url || event.sourceUrl || '')}" data-share-title="${esc(eventText(event))}">${icon('arrow')}<span>${l('share')}</span></button>${reportLink(event)}</footer></div></article>`;
}
export function eventsView(catalog, state = {}, following = new Set(), limit = 24) {
  const rows = eventRows(catalog, state);
  return `${pageHeading('events', 'eventsBody')}${filterBar(state, catalog, 'events', following)}<div class="results-bar"><p role="status">${t('results', { count: number(rows.length) })}</p></div><div class="rich-events-grid">${rows.length ? rows.slice(0, limit).map(event => richEventCard(event, catalog, following)).join('') : empty()}</div>${rows.length > limit ? `<div class="pagination"><p>${t('showing', { shown: number(limit), total: number(rows.length) })}</p><button type="button" class="button button-outline" data-action="more">${t('loadMore')}${icon('plus')}</button></div>` : ''}`;
}
export function bindEvents(root) {
  const grid = root.querySelector('.rich-events-grid');
  const cards = [...(grid?.querySelectorAll('.rich-event-card') || [])];
  let frame = 0;
  const layout = () => {
    frame = 0;
    const masonry = window.innerWidth > 760;
    grid?.classList.toggle('events-masonry', masonry);
    for (const card of cards) {
      card.style.gridRowEnd = masonry ? `span ${Math.ceil((card.getBoundingClientRect().height + 20) / 8)}` : '';
    }
  };
  const queueLayout = () => { if (!frame) frame = window.requestAnimationFrame(layout); };
  const observer = window.ResizeObserver ? new window.ResizeObserver(queueLayout) : null;
  cards.forEach(card => observer?.observe(card));
  window.addEventListener('resize', queueLayout);
  root.addEventListener('load', queueLayout, true);
  root.addEventListener('click', queueLayout);
  layout();
  function failed(event) {
    const img = event.target;
    const video = img.matches?.('.event-video') ? img : img.closest?.('.event-video');
    if (video) {
      const original = safeUrl(video.dataset.originalVideo);
      const poster = safeUrl(video.getAttribute('poster'));
      const fallback = document.createElement('figure');
      fallback.className = 'event-media event-video-unavailable';
      fallback.dataset.eventMedia = '';
      fallback.innerHTML = link(original, (poster ? image(poster, 'event-poster', l('poster')) : '') + `<span class="event-video-fallback-label">${esc(l('videoUnavailable'))}</span>`, 'event-media-link');
      video.replaceWith(fallback);
      queueLayout();
      return;
    }
    if (img.matches?.('.event-gallery-image')) {
      const galleryLink = img.closest('.event-gallery-link');
      const original = img.closest('.rich-event-card')?.querySelector('.rich-event-actions a');
      if (galleryLink) {
        if (original?.href) galleryLink.href = original.href;
        galleryLink.textContent = l('unavailable');
        galleryLink.classList.add('event-gallery-unavailable');
      }
      return;
    }
    if (!img.matches?.('.event-poster')) return;
    const media = img.closest('[data-event-media]');
    const fallback = media?.querySelector('[data-event-image-fallback]');
    let remaining = [];
    try { remaining = JSON.parse(fallback?.dataset.eventImageFallback || '[]'); } catch {}
    if (remaining.length) {
      img.hidden = false; img.classList.remove('failed-image');
      img.src = remaining.shift(); fallback.dataset.eventImageFallback = JSON.stringify(remaining);
    } else if (media) {
      media.classList.add('event-media-unavailable');
      img.remove();
      media.querySelector('.event-media-link')?.append(document.createTextNode(l('unavailable')));
    }
  }
  root.addEventListener('error', failed, true);
  root.querySelectorAll('.event-video').forEach(video => { if (video.error) failed({ target: video }); });
  root.querySelectorAll('.event-poster').forEach(img => { if (img.complete && !img.naturalWidth) failed({ target: img }); });
  return () => {
    root.removeEventListener('error', failed, true);
    root.removeEventListener('load', queueLayout, true);
    root.removeEventListener('click', queueLayout);
    window.removeEventListener('resize', queueLayout);
    observer?.disconnect();
    if (frame) window.cancelAnimationFrame(frame);
  };
}
