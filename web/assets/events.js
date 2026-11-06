import { isRedesign } from './redesign.js';
import { eventText, eventOriginalMarkup } from './event-localization.js';
import { t, getLocale, countryName } from './i18n.js';
import { esc, link, icon, timestamp, number, safeUrl, image, avatar, sourceHref, pastEvent, textMatch, empty, hasFilters, platformName } from './utils.js';
import { pageHeading, filterBar, eventDateLabel } from './views.js';
import { reportLink } from './reporting.js';
import { pageNotes } from './page-notes.js';
import { sourceDisplayName, sourceSummaryMarkup } from './source-names.js';
const labels = {
  'zh-Hant': { followSource: '追蹤來源', moreActions: '更多動作', reference: '相關原始貼文', snapshot: '相關網站原文', description: '活動整理資訊', endUnknown: '結束時間未公告', poster: '活動圖片', moreImages: '更多活動圖片', video: '相關影片', videoUnavailable: '影片暫時無法載入，查看原始影片', unavailable: '圖片暫時無法載入，請查看原始來源。', share: '分享', zoneNote: '活動時間以活動當地時區顯示；與你所在的時區不同時，時間旁會標示該時區。', subscribe: '訂閱活動' },
  en: { followSource: 'Follow source', moreActions: 'More actions', reference: 'Related original post', snapshot: 'Original website content', description: 'Event information', endUnknown: 'End time not announced', poster: 'Event image', moreImages: 'More event images', video: 'Related video', videoUnavailable: 'Video unavailable. View the original video.', unavailable: 'Image unavailable. Please view the original source.', share: 'Share', zoneNote: 'Event times are shown in each event’s local timezone; when it differs from yours, the timezone is named beside the time.', subscribe: 'Subscribe to events' },
  ja: { followSource: '情報源をフォロー', moreActions: 'その他の操作', reference: '関連する元の投稿', snapshot: '関連ウェブサイトの原文', description: 'イベント情報', endUnknown: '終了時刻は未発表', poster: 'イベント画像', moreImages: 'その他のイベント画像', video: '関連動画', videoUnavailable: '動画を読み込めません。元の動画を見る', unavailable: '画像を読み込めません。元の情報をご確認ください。', share: '共有', zoneNote: 'イベントの時刻は開催地のタイムゾーンで表示します。お使いのタイムゾーンと異なる場合は、時刻の横にタイムゾーンを表示します。', subscribe: 'イベントを購読' },
  ko: { followSource: '출처 팔로우', moreActions: '더 보기 작업', reference: '관련 원본 게시물', snapshot: '관련 웹사이트 원문', description: '행사 정보', endUnknown: '종료 시각 미발표', poster: '행사 이미지', moreImages: '행사 이미지 더 보기', video: '관련 동영상', videoUnavailable: '동영상을 불러올 수 없습니다. 원본 동영상 보기', unavailable: '이미지를 불러올 수 없습니다. 원본 출처를 확인하세요.', share: '공유', zoneNote: '행사 시간은 행사 현지 시간대로 표시합니다. 내 시간대와 다르면 시간 옆에 해당 시간대를 표시합니다.', subscribe: '행사 구독' },
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
function followButton(source, following) {
  const followed = following.has(source.id), name = sourceDisplayName(source);
  // New interface: the button says what is followed (the source, not the event).
  const label = followed ? t('following') : isRedesign() ? l('followSource') : t('follow');
  return `<button type="button" class="feed-action ${followed ? 'is-following' : ''}" data-follow="${esc(source.id)}" aria-pressed="${!!followed}" aria-label="${esc(t(followed ? 'unfollow' : 'follow') + ' ' + name)}">${icon(followed ? 'check' : 'heart')}<span>${label}</span></button>`;
}
// New interface: the excerpt is clamped to three lines, so only text that
// surely fits stays unclamped (bindEvents hides "read more" when it fits).
const fitsThreeLines = text => text.length <= 60 && text.split('\n').length <= 3;
function originalPost(post, catalog, following, showAuthor = true, withActions = true, withFollow = true, text = post.text || '') {
  const source = catalog.sources?.find(source => source.id === post.sourceId);
  const name = source ? sourceDisplayName(source) : post.sourceName || t('source');
  const expanded = isRedesign() ? fitsThreeLines(text) : text.length <= 240 && text.split('\n').length <= 5;
  const followed = source && following.has(source.id);
  return `<section class="event-reference feed-content" data-event-post="${esc(post.id)}">${post.contentKind === 'website_snapshot' ? `<p class="event-reference-label">${l('snapshot')}</p>` : ''}${showAuthor ? eventAuthor(post, catalog) : ''}${text ? `<p class="feed-text ${expanded ? 'is-expanded' : ''}">${esc(text)}</p>${expanded ? '' : `<button type="button" class="feed-expand" data-expand-post aria-expanded="false">${t('readMore')}</button>`}` : ''}${withActions ? `<div class="event-reference-actions">${source && withFollow ? followButton(source, following) : ''}${link(post.url, t('original'), 'text-link')}</div>` : ''}</section>`;
}
// New interface: a post that opens with the event's title (give or take
// emoji, punctuation and spacing) shows only what follows it, since the card
// heading already says it. Returns the text unchanged when it is no repeat.
const titleKey = value => String(value || '').normalize('NFKC').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, '');
// Spaces, dashes, closing marks and emoji left over after the title (a
// following hashtag or mention keeps its # or @).
const leadingSeparators = /^(?:(?![#@＃＠])[\s\p{Pd}\p{Po}\p{Pe}\p{Pf}\p{S}\p{M}\p{Cf}])+/u;
function withoutTitleRepeat(text, titles) {
  for (const title of titles) {
    const target = titleKey(title);
    if (target.length < 4) continue;
    let matched = 0, end = 0, lineBreak = false, cut = -1;
    for (const match of text.matchAll(/[\s\S]/gu)) {
      const char = match[0], key = titleKey(char);
      if (char === '\n') lineBreak = true;
      if (!key) continue;
      if (!target.startsWith(key, matched)) {
        // The first line(s) are most of the title (e.g. the title adds
        // "(morning)"): drop those whole lines.
        if (lineBreak && matched >= Math.max(4, target.length * .75)) cut = end;
        break;
      }
      matched += key.length; end = match.index + char.length; lineBreak = false;
      if (matched === target.length) { cut = end; break; }
    }
    if (cut < 0 && matched >= Math.max(4, target.length * .75) && !titleKey(text.slice(end))) cut = end;
    // In space-separated scripts the title must end at a word boundary
    // ("Spring Concert" is not repeated by "Spring concerts are …").
    const last = [...text.slice(0, cut)].pop() || '', next = [...text.slice(cut)][0] || '';
    if (cut > 0 && /[\p{L}\p{N}]/u.test(next) && !/[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}]/u.test(last + next)) cut = -1;
    if (cut >= 0) return text.slice(cut).replace(leadingSeparators, '');
  }
  return text;
}
// A calendar-style date block in the event's own timezone (civil dates stay put).
// The date block already shows the day, so single-day timed events list only
// the clock times; all-day and multi-day events keep the full label.
function eventTimeLabel(event) {
  const start = new Date(event.start), end = new Date(event.end);
  if (event.allDay || !Number.isFinite(+start) || !/T/.test(String(event.start))) return eventDateLabel(event);
  const timeZone = event.timezone || 'UTC';
  const fmt = (value, options) => { try { return new Intl.DateTimeFormat(getLocale(), { timeZone, ...options }).format(value); } catch { return ''; } };
  const day = value => fmt(value, { year: 'numeric', month: '2-digit', day: '2-digit' });
  const clock = value => fmt(value, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  if (Number.isFinite(+end) && !event.endEstimated && end > start) return day(start) === day(end) ? `${clock(start)}–${clock(end)}` : eventDateLabel(event);
  return clock(start);
}
// Clock-only label for single-day timed events (the date block shows the day);
// empty when the event needs its full date label.
export function eventClockLabel(event) {
  const label = eventTimeLabel(event);
  return label === eventDateLabel(event) ? '' : label;
}
// The event's timezone, only when it would read differently from the
// visitor's own clock; empty when both show the same local time.
function visitorTimeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; }
}
function differingZone(event) {
  const zone = event.timezone || 'UTC', viewer = visitorTimeZone();
  if (zone === viewer) return '';
  const when = new Date(event.start);
  const at = Number.isFinite(+when) ? when : new Date();
  const wall = timeZone => { try { return new Intl.DateTimeFormat('en-US', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(at); } catch { return ''; } };
  return wall(zone) && wall(zone) === wall(viewer) ? '' : zone;
}
export function dateBlock(event) {
  const start = String(event.start || '');
  const civil = /^\d{4}-\d{2}-\d{2}$/.test(start);
  const when = new Date(civil ? start + 'T00:00:00Z' : start);
  if (!Number.isFinite(+when)) return '';
  const timeZone = civil ? 'UTC' : event.timezone || 'UTC';
  const part = (options) => { try { return new Intl.DateTimeFormat(getLocale(), { timeZone, ...options }).format(when); } catch { return ''; } };
  const year = part({ year: 'numeric' }).replace(/\D+$/, '');
  const showYear = pastEvent(event) || year !== new Intl.DateTimeFormat('en', { timeZone, year: 'numeric' }).format(new Date());
  return `<div class="event-date-block" aria-hidden="true">${showYear ? `<span class="event-date-year">${esc(year)}</span>` : ''}<span class="event-date-month">${esc(part({ month: 'short' }))}</span><strong>${esc(part({ day: 'numeric' }).replace(/\D+$/, ''))}</strong><span class="event-date-weekday">${esc(part({ weekday: 'short' }))}</span></div>`;
}
// seenPosts (new interface, optional): ids of posts whose excerpt an earlier
// card in the same list already showed; eventsView passes one per render.
export function richEventCard(event, catalog, following = new Set(), seenPosts) {
  return isRedesign() ? redesignedRichEventCard(event, catalog, following, seenPosts) : legacyRichEventCard(event, catalog, following);
}
// Original version, shown while the "new interface" switch is off.
function legacyRichEventCard(event, catalog, following = new Set()) {
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
// "New interface" version. Each card names the original source, follow and
// the ⋯ menu once; the timezone appears only when it differs from the
// visitor's; the structured description only shows when no post excerpt is.
// One excerpt per card (the first post with text not already shown on an
// earlier card of the same list); other posts show their author line only.
// A poster, when there is one, is a thumbnail; without one there is no tile.
function redesignedRichEventCard(event, catalog, following = new Set(), seenPosts = new Set()) {
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
  const eventUrl = event.url || event.sourceUrl;
  const eventKey = referenceKey(eventUrl);
  const eventIsPost = !!eventKey && posts.some(post => referenceKey(post.url) === eventKey);
  // One post that is the event's own source: its follow and original link
  // move to the card's action row. Several posts keep their own actions.
  const single = posts.length === 1 && (eventIsPost || !safeUrl(eventUrl));
  const sourceOf = post => catalog.sources?.find(source => source.id === post.sourceId);
  const followed = new Set();
  const titles = [...new Set([eventText(event), event.title].filter(Boolean))];
  let excerptShown = false;
  const references = posts.map(post => {
    const id = post.sourceId || '';
    const first = !followed.has(id); followed.add(id);
    const key = post.id || referenceKey(post.url);
    const text = excerptShown || seenPosts.has(key) ? '' : withoutTitleRepeat(post.text || '', titles);
    if (text) { excerptShown = true; seenPosts.add(key); }
    return originalPost(post, catalog, following, true, !single, first, text);
  }).join('');
  // The structured description fills the text area when no post excerpt
  // does (no post, or its excerpt is already on an earlier card); a long one
  // is clamped like the post excerpts, with "read more".
  const description = event.description && !excerptShown ? `<div class="event-description-block feed-content"><div class="event-description-text feed-text">${eventDescriptionMarkup(event)}</div>${fitsThreeLines(String(event.description)) ? '' : `<button type="button" class="feed-expand" data-expand-post aria-expanded="false">${t('readMore')}</button>`}</div>` : '';
  const original = single ? link(eventUrl || posts[0].url, t('original'), 'text-link event-original-link') : eventIsPost ? '' : link(eventUrl, t('original'), 'text-link event-original-link');
  const zone = differingZone(event);
  const time = `${eventTimeLabel(event) === eventDateLabel(event) ? esc(eventDateLabel(event)) : `<span class="sr-only">${esc(eventDateLabel(event))}</span><span aria-hidden="true">${esc(eventTimeLabel(event))}</span>`}${event.allDay ? ` · ${t('allDay')}` : event.endEstimated ? ` · ${l('endUnknown')}` : ''}${zone ? ` <span class="rich-event-zone" title="${esc(t('localTime'))}">${esc(zone)}</span>` : ''}`;
  return `<article class="rich-event-card ${pastEvent(event) ? 'is-past' : ''}" data-event-id="${esc(event.id)}"><header class="rich-event-header">${dateBlock(event)}<div class="rich-event-heading"><div class="eyebrow">${esc(countryName(event.countryCode, event.country))}${pastEvent(event) ? `<span class="past-badge">${t('past')}</span>` : ''}</div><h2>${esc(eventText(event))}</h2>${eventOriginalMarkup(event)}<div class="rich-event-facts"><p class="rich-event-time">${icon('calendar')}<span>${time}</span></p><p class="rich-event-location">${icon('pin')}<span>${esc(eventText(event, 'location') || t('locationUnknown'))}</span></p></div></div></header>${mainImage && !video ? `<figure class="event-media" data-event-media>${link(eventUrl, image(mainImage, 'event-poster', `${l('poster')}: ${eventText(event)}`), 'event-media-link')}${candidates.length > 1 ? `<span hidden data-event-image-fallback="${esc(JSON.stringify(candidates.slice(1)))}"></span>` : ''}</figure>` : ''}${gallery.length ? `<details class="event-gallery"><summary>${l('moreImages')} (${number(gallery.length)})</summary><div class="event-gallery-strip" tabindex="0" aria-label="${esc(l('moreImages'))}">${gallery.map(url => link(url, image(url, 'event-gallery-image', l('poster')), 'event-gallery-link')).join('')}</div></details>` : ''}${video ? `<video class="event-video" controls preload="metadata" playsinline data-original-video="${esc(safeUrl(eventUrl || posts[0]?.url))}" ${mainImage ? `poster="${esc(mainImage)}"` : ''} aria-label="${esc(l('video') + ': ' + eventText(event))}" src="${esc(video)}"></video>` : ''}<div class="rich-event-copy">${references}${description}<footer class="rich-event-actions">${single && sourceOf(posts[0]) ? followButton(sourceOf(posts[0]), following) : ''}${original}<details class="more-actions"><summary aria-label="${esc(l('moreActions'))}" title="${esc(l('moreActions'))}"><span aria-hidden="true">⋯</span></summary><div class="more-actions-menu"><button type="button" class="feed-action" data-share="${esc(eventUrl || '')}" data-share-title="${esc(eventText(event))}">${icon('arrow')}<span>${l('share')}</span></button>${reportLink(event)}</div></details></footer></div></article>`;
}
function emptyEvents(catalog, state) {
  if (hasFilters(state)) return empty();
  const hasPast = (catalog.events || []).length > 0;
  return empty({ filtered: false, symbol: 'calendar', title: t(hasPast ? 'emptyEventsTitle' : 'emptyEventsNone'), body: t(hasPast ? 'emptyEventsBody' : 'emptyEventsNoneBody'),
    actions: hasPast ? link('/events/?period=past', esc(t('seePastEvents')), 'button button-outline') : link('/feeds/', esc(t('feeds')) + icon('rss'), 'button button-outline') });
}
// Page notes (new interface): the timezone rule and the event subscriptions.
function eventNotes(catalog) {
  const feeds = (Array.isArray(catalog.feeds) ? catalog.feeds : []).filter(feed => ['taiwanCalendar', 'worldCalendar', 'onlineCalendar', 'events'].includes(feed.id) && safeUrl(feed.url));
  const colon = ['zh-Hant', 'ja'].includes(getLocale()) ? '：' : ': ';
  return pageNotes([esc(l('zoneNote')), feeds.length ? `${esc(l('subscribe'))}${colon}<span class="page-notes-links">${feeds.map(feed => link(feed.url, `${esc(t('feed_' + feed.id))} ${esc(feed.format || '')}`, 'text-link')).join('')}</span>` : ''], 'events-notes');
}
// New interface: the period as tabs above the list (the filter bar's period
// select is hidden), so phones see it while the filters are folded away.
function periodTabs(state) {
  const current = ['past', 'allEvents'].includes(state.period) ? state.period : 'upcoming';
  const tab = period => {
    const params = new URLSearchParams({ lang: getLocale() });
    for (const key of ['q', 'country']) if (state[key]) params.set(key, state[key]);
    if (period !== 'upcoming') params.set('period', period);
    return `<a class="follow-tab" href="/events/?${esc(params.toString())}" ${period === current ? 'aria-current="page"' : ''}>${t(period)}</a>`;
  };
  return `<nav class="follow-tabs event-period-tabs" aria-label="${esc(t('eventPeriod'))}">${['upcoming', 'past', 'allEvents'].map(tab).join('')}</nav>`;
}
export function eventsView(catalog, state = {}, following = new Set(), limit = 24) {
  const rows = eventRows(catalog, state);
  // New interface: a post's excerpt appears on the first card that links it.
  const seenPosts = new Set();
  // New interface: a count only when a search or filter narrows the list
  // (the period is a tab, not a filter).
  const count = !isRedesign() || hasFilters({ ...state, period: 'upcoming' }) ? `<div class="results-bar"><p role="status">${t('results', { count: number(rows.length) })}</p></div>` : '';
  return `${pageHeading('events', 'eventsBody')}${isRedesign() ? periodTabs(state) : ''}${filterBar(state, catalog, 'events', following)}${count}<div class="rich-events-grid">${rows.length ? rows.slice(0, limit).map(event => richEventCard(event, catalog, following, seenPosts)).join('') : emptyEvents(catalog, state)}</div>${rows.length > limit ? `<div class="pagination"><p>${t('showing', { shown: number(limit), total: number(rows.length) })}</p><button type="button" class="button button-outline" data-action="more">${t('loadMore')}${icon('plus')}</button></div>` : ''}${isRedesign() ? eventNotes(catalog) : ''}`;
}
export function bindEvents(root) {
  const grid = root.querySelector('.rich-events-grid');
  const cards = [...(grid?.querySelectorAll('.rich-event-card') || [])];
  let frame = 0;
  const layout = () => {
    frame = 0;
    // The new interface lists events in date order; the original keeps its
    // two-column masonry on wide screens.
    const masonry = !isRedesign() && window.innerWidth > 760;
    grid?.classList.toggle('events-masonry', masonry);
    for (const card of cards) {
      card.style.gridRowEnd = masonry ? `span ${Math.ceil((card.getBoundingClientRect().height + 20) / 8)}` : '';
    }
    // New interface: "read more" only when the three-line clamp hides text.
    if (isRedesign()) for (const button of grid?.querySelectorAll('.rich-event-card [data-expand-post][aria-expanded="false"]') || []) {
      const text = button.closest('.feed-content')?.querySelector('.feed-text');
      const clamped = text?.querySelector('.source-summary') || text;
      if (clamped?.clientHeight) button.hidden = clamped.scrollHeight <= clamped.clientHeight + 1;
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
      const card = img.closest('.rich-event-card');
      const original = card?.querySelector('.rich-event-actions .event-original-link') || card?.querySelector('.rich-event-actions a');
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
      // The new interface hides the whole tile (redesign-home-events.css).
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
