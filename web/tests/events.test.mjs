import { isRedesign } from '../assets/redesign.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { referenceKey, relatedEventPosts, eventRows, richEventCard, eventsView, bindEvents } from '../assets/events.js';
import { togglePostExpansion } from '../assets/views.js';
import { setLocale } from '../assets/i18n.js';
import { textMatch } from '../assets/utils.js';
const source = { id: 'source1', name: '原始名稱 / Original name', countryCode: 'JP', url: '/source/original/', avatar: '/avatar.webp' };
const post = { id: 'post1', url: 'https://www.instagram.com/p/abc/?igsh=tracking', sourceId: 'source1', sourceName: source.name, text: '原始發文 <script>bad()</script>\n' + 'Original post content '.repeat(50), image: '/cached.webp', platform: 'instagram', publishedAt: '2026-09-01T12:00:00Z' };
const event = { id: 'event1', title: 'Original concert', url: 'https://instagram.com/reel/abc/', sourceUrl: post.url, start: '2099-09-23', end: '2099-09-25', allDay: true, timezone: 'America/Los_Angeles', countryCode: 'JP', location: 'Original Hall', image: '/poster.webp', description: 'Structured description' };
const catalog = { sources: [source], events: [event], posts: [post], countries: [{ code: 'JP' }, { code: 'TW' }] };
function setup() { const window = new JSDOM('<main></main>', { url: 'https://example.com', pretendToBeVisual: true }).window; globalThis.window = window; globalThis.document = window.document; globalThis.localStorage = window.localStorage; globalThis.location = window.location; setLocale('en'); return window; }

test('event explanations follow locale while original posts and descriptions remain accessible', () => {
  const window = setup();
  const translated = {...event, description: '原始活動說明 <b>文字</b>', descriptionLanguage: 'zh-Hant',
    descriptions: {'zh-Hant': '原始活動說明 <b>文字</b>', en: 'English explanation <b>text</b>', ja: '日本語の説明', ko: '한국어 설명'}};
  for (const locale of ['zh-Hant','en','ja','ko']) {
    setLocale(locale);
    document.querySelector('main').innerHTML = richEventCard(translated, catalog);
    assert.equal(document.querySelector('.feed-text').textContent, post.text);
    // The new interface shows the structured description only when no
    // original post is linked (the post already says it), and never folded.
    if (isRedesign()) {
      assert.equal(document.querySelector('.source-summary'), null);
      assert.equal(document.querySelector('details.event-description'), null);
      document.querySelector('main').innerHTML = richEventCard(translated, { ...catalog, posts: [] });
      assert.equal(document.querySelector('.event-description-text').closest('details'), null);
    }
    assert.equal(document.querySelector('.source-summary').textContent, translated.descriptions[locale]);
    assert.equal(document.querySelector('.event-description b'), null);
    assert.equal(document.querySelector('.event-description-text b'), null);
    const original = document.querySelector('.source-summary-original');
    if (locale === 'zh-Hant') assert.equal(original, null);
    else { assert.equal(original.open, false); assert.equal(original.querySelector('p').textContent, translated.description); }
  }
  assert.equal(textMatch(translated, 'English explanation'), true);
  assert.equal(textMatch(translated, '한국어'), true);
  window.close();
});

test('event references match canonical post IDs and explicit links, never merely the same author', () => {
  assert.equal(referenceKey('https://x.com/name/status/123?s=20'), referenceKey('https://twitter.com/other/status/123'));
  assert.equal(referenceKey('https://youtu.be/xyz'), referenceKey('https://www.youtube.com/watch?v=xyz&feature=share'));
  assert.equal(referenceKey('https://m.facebook.com/story.php?story_fbid=123&id=45'), referenceKey('https://www.facebook.com/author/posts/123'));
  assert.equal(referenceKey('javascript:alert(1)'), '');
  const wrong = { ...post, id: 'other', url: 'https://instagram.com/p/not-related/' };
  const explicit = { ...wrong, id: 'explicit', eventIds: [event.id] };
  assert.deepEqual(relatedEventPosts(event, [post, post, wrong, explicit]).map(p => p.id), ['post1', 'explicit']);
  assert.deepEqual(relatedEventPosts({ ...event, url: '', sourceUrl: '' }, [post, wrong]), []);
});

test('rich cards visibly preserve original post text and usable image, source, follow, share and report controls', () => {
  const window = setup(); document.querySelector('main').innerHTML = richEventCard(event, catalog, new Set([source.id]));
  assert.equal(document.querySelector('.event-poster').getAttribute('src'), '/cached.webp');
  assert.match(document.querySelector('.feed-text').textContent, /<script>bad\(\)<\/script>/);
  assert.equal(document.querySelector('script'), null);
  assert.equal(document.querySelector('.event-reference').closest('details'), null);
  assert.equal(document.querySelector('[data-follow]').getAttribute('aria-pressed'), 'true');
  assert.ok(document.querySelector('[data-share]')); assert.ok(document.querySelector('a[href^="/submit/"]'));
  const button = document.querySelector('[data-expand-post]'); togglePostExpansion(button); assert.equal(button.getAttribute('aria-expanded'), 'true'); assert.ok(document.querySelector('.feed-text.is-expanded'));
  assert.match(document.querySelector('.rich-event-time').textContent, /Sep 23, 2099.*Sep 24, 2099/); assert.doesNotMatch(document.querySelector('.rich-event-time').textContent, /Sep 25/);
  window.close();
});

test('time zones, unknown ends, and archived events remain truthful', () => {
  const window = setup(); const timed = { ...event, allDay: false, start: '2026-09-23T01:00:00Z', end: '2026-09-23T03:00:00Z', endEstimated: true };
  document.querySelector('main').innerHTML = richEventCard(timed, catalog); const text = document.querySelector('.rich-event-time').textContent;
  assert.match(text, /Sep 22(?:, 2026)?.*18:00.*End time not announced/); assert.doesNotMatch(text, /20:00/);
  const rows = [{ ...event, id: 'old', start: '2000-01-01', end: '2000-01-02' }, event, { ...event, id: 'next', countryCode: 'TW', start: '2099-09-26', end: '2099-09-27' }];
  assert.deepEqual(eventRows({ events: rows }, {}).map(e => e.id), ['event1', 'next']);
  assert.deepEqual(eventRows({ events: rows }, { period: 'past' }).map(e => e.id), ['old']);
  assert.deepEqual(eventRows({ events: rows }, { country: 'TW', q: 'concert' }).map(e => e.id), ['next']);
  assert.equal(eventRows({ events: rows }, { period: 'allEvents' }).length, 3); window.close();
});

test('failed cached image tries the event poster before showing a functional source fallback', () => {
  const window = setup(); const root = document.querySelector('main'); root.innerHTML = richEventCard(event, catalog); const cleanup = bindEvents(root); const img = root.querySelector('.event-poster');
  img.hidden = true; img.classList.add('failed-image'); img.dispatchEvent(new window.Event('error')); assert.equal(img.getAttribute('src'), '/poster.webp'); assert.equal(img.hidden, false);
  img.dispatchEvent(new window.Event('error')); assert.equal(root.querySelector('.event-poster'), null); assert.match(root.querySelector('.event-media-unavailable').textContent, /Image unavailable/);
  assert.ok(root.querySelector('.event-media-link[href]')); assert.ok(root.querySelector('.feed-text')); cleanup(); window.close();
});

test('four languages retain original content and pagination; absent and unsafe media produce no fake frames', () => {
  const window = setup();
  for (const locale of ['zh-Hant', 'en', 'ja', 'ko']) {
    setLocale(locale); document.querySelector('main').innerHTML = eventsView({ ...catalog, events: [event, { ...event, id: 'another' }] }, {}, new Set(), 1);
    assert.equal(document.querySelectorAll('.rich-event-card').length, 1); assert.ok(document.querySelector('[data-action="more"]'));
    assert.ok(document.querySelector('[data-filter="country"]')); assert.ok(document.querySelector('[data-filter="period"]')); assert.ok(document.querySelector('#catalog-search'));
    assert.match(document.querySelector('.feed-text').textContent, /原始發文/); assert.ok(!document.querySelector('main').textContent.includes('undefined'));
  }
  document.querySelector('main').innerHTML = richEventCard({ ...event, image: 'javascript:bad()', videoUrl: 'javascript:bad()' }, { ...catalog, posts: [] });
  assert.equal(document.querySelector('.event-media'), null); assert.equal(document.querySelector('video'), null); assert.match(document.querySelector('.event-description-text').textContent, /Structured description/);
  window.close();
});

test('playable original video uses its poster once and never autoplays', () => {
  const window = setup(); document.querySelector('main').innerHTML = richEventCard({ ...event, videoUrl: '/original.mp4' }, catalog);
  assert.equal(document.querySelector('video').getAttribute('poster'), '/cached.webp');
  assert.equal(document.querySelector('video').getAttribute('preload'), 'metadata');
  assert.equal(document.querySelector('video').hasAttribute('controls'), true);
  assert.equal(document.querySelector('video').hasAttribute('autoplay'), false);
  assert.equal(document.querySelector('.event-poster'), null); window.close();
});

test('events use masonry on wide screens in the original interface and one dated list in the new one', async () => {
  const window = setup(); const root = document.querySelector('main'); root.innerHTML = eventsView(catalog, {});
  const card = root.querySelector('.rich-event-card'); let height = 400; card.getBoundingClientRect = () => ({ height });
  const callbacks = []; window.ResizeObserver = class { constructor(callback) { callbacks.push(callback); } observe() {} disconnect() {} };
  const cleanup = bindEvents(root); assert.equal(card.style.gridRowEnd, isRedesign() ? '' : 'span 53');
  height = 800; callbacks[0](); await new Promise(resolve => setTimeout(resolve, 30)); assert.equal(card.style.gridRowEnd, isRedesign() ? '' : 'span 103');
  window.innerWidth = 390; window.dispatchEvent(new window.Event('resize')); await new Promise(resolve => setTimeout(resolve, 30));
  assert.equal(card.style.gridRowEnd, ''); assert.equal(root.querySelector('.events-masonry'), null); cleanup(); window.close();
});

test('cached reference media wins over expiring remote posters and extra cached images remain available', () => {
  const window = setup(); document.querySelector('main').innerHTML = richEventCard({ ...event, image: 'https://cdn.example.com/expired.jpg', images: ['https://cdn.example.com/expired.jpg'] }, { ...catalog, posts: [{ ...post, images: ['https://cdn.example.com/expired.jpg', '/cached.webp', '/second.webp'] }] });
  assert.equal(document.querySelector('.event-poster').getAttribute('src'), '/cached.webp');
  assert.deepEqual([...document.querySelectorAll('.event-gallery-image')].map(i => i.getAttribute('src')), ['/second.webp']);
  assert.equal(document.querySelector('.event-gallery-strip').getAttribute('tabindex'), '0'); window.close();
});

test('social profile URLs never link events to unrelated profile posts, while photo and Threads identities survive URL variants', () => {
  for (const url of ['https://instagram.com/name/', 'https://facebook.com/name/', 'https://x.com/name', 'https://twitter.com/name', 'https://youtube.com/@name', 'https://youtube.com/channel/abc', 'https://threads.net/@name']) {
    assert.equal(referenceKey(url), '');
    assert.deepEqual(relatedEventPosts({ ...event, url, sourceUrl: url }, [{ ...post, url }]), []);
  }
  assert.equal(referenceKey('https://facebook.com/photo.php?fbid=123&id=456'), referenceKey('https://www.facebook.com/name/photos/a.456/123/'));
  assert.equal(referenceKey('https://threads.net/@name/post/ABC'), referenceKey('https://www.threads.com/@name/post/ABC?x=1'));
});

test('remote gallery images after the cached cover are retained and fail with an original-source action', () => {
  const window = setup(); const root = document.querySelector('main');
  root.innerHTML = richEventCard({ ...event, image: '/cached.webp', images: ['https://cdn.example.com/cover.jpg', 'https://cdn.example.com/second.jpg'] }, { ...catalog, posts: [{ ...post, images: ['https://cdn.example.com/cover.jpg'] }] });
  const gallery = root.querySelectorAll('.event-gallery-image'); assert.equal(gallery.length, 1); assert.equal(gallery[0].getAttribute('src'), 'https://cdn.example.com/second.jpg');
  const cleanup = bindEvents(root); gallery[0].dispatchEvent(new window.Event('error')); assert.match(root.querySelector('.event-gallery-unavailable').textContent, /Image unavailable/); assert.equal(root.querySelector('.event-gallery-unavailable').getAttribute('href'), event.url);
  cleanup(); window.close();
});

test('failed videos remove dead controls and retain their poster with a four-language original-video action', () => {
  const window = setup(); const root = document.querySelector('main');
  for (const locale of ['zh-Hant', 'en', 'ja', 'ko']) {
    setLocale(locale); root.innerHTML = richEventCard({ ...event, videoUrl: 'https://cdn.example.com/expired.mp4' }, catalog);
    const cleanup = bindEvents(root); root.querySelector('video').dispatchEvent(new window.Event('error'));
    assert.equal(root.querySelector('video'), null);
    assert.equal(root.querySelector('.event-video-unavailable a').getAttribute('href'), event.url);
    assert.equal(root.querySelector('.event-video-unavailable img').getAttribute('src'), '/cached.webp');
    assert.ok(root.querySelector('.event-video-fallback-label').textContent.length > 10);
    assert.ok(!root.querySelector('.event-video-unavailable').innerHTML.includes('expired.mp4'));
    cleanup();
  }
  window.close();
});


test('event cards omit repeated declarations without hiding snapshot status, timezone or original links',()=>{
 const window=setup();document.querySelector('main').innerHTML=eventsView(catalog,{});
 // The new interface states the count only when a search or filter narrows the list.
 if(isRedesign()){assert.equal(document.querySelector('.results-bar'),null);document.querySelector('main').innerHTML=eventsView(catalog,{q:'concert'});}
 assert.equal(document.querySelector('.results-bar').children.length,1);
 if(isRedesign()) document.querySelector('main').innerHTML=eventsView(catalog,{});
 assert.equal(document.querySelector('.event-reference-label'),null);
 // The new interface keeps one action row per single-post event.
 assert.ok(document.querySelector(isRedesign() ? '.rich-event-actions a[href]' : '.event-reference-actions a[href]'));
 assert.match(document.querySelector('.rich-event-zone').textContent,/America\/Los_Angeles/);
 if(isRedesign()){
  // One original link, one follow and one ⋯ menu per card; the zone sits beside the time.
  assert.equal(document.querySelectorAll('.rich-event-card a.event-original-link').length,1);
  assert.equal(document.querySelectorAll('.rich-event-card .event-reference-actions').length,0);
  assert.equal(document.querySelectorAll('.rich-event-card [data-follow]').length,1);
  // The follow button names what is followed: the source.
  assert.equal(document.querySelector('.rich-event-card [data-follow] span').textContent,'Follow source');
  assert.equal(document.querySelectorAll('.rich-event-card .more-actions').length,1);
  assert.ok(document.querySelector('.rich-event-time .rich-event-zone'));
  // The general rule and the event subscriptions live in the page notes.
  assert.ok(document.querySelector('.page-notes'));
  const zone=Intl.DateTimeFormat().resolvedOptions().timeZone;
  document.querySelector('main').innerHTML=richEventCard({...event,timezone:zone},catalog);
  assert.equal(document.querySelector('.rich-event-zone'),null);
  document.querySelector('main').innerHTML=eventsView({...catalog,feeds:[{id:'taiwanCalendar',url:'/feeds/public-calendar.ics',format:'ICS'},{id:'events',url:'/feeds/events.xml',format:'RSS'},{id:'posts',url:'/feeds/posts.xml',format:'RSS'}]},{});
  assert.deepEqual([...document.querySelectorAll('.page-notes a')].map(a=>a.getAttribute('href')),['/feeds/public-calendar.ics','/feeds/events.xml']);
 }
 document.querySelector('main').innerHTML=richEventCard({...event,url:post.url,sourceUrl:post.url},{...catalog,posts:[{...post,contentKind:'website_snapshot',publishedAt:null}]});
 assert.match(document.querySelector('.event-reference-label').textContent,/website/i);
 assert.equal(document.querySelectorAll('.rich-event-actions a[href="'+post.url+'"]').length,isRedesign() ? 1 : 0);
 window.close();
});

test('new interface: a post excerpt shows once per list and cards without a poster have no thumbnail tile', () => {
  const window = setup();
  const second = { ...event, id: 'event2', start: '2099-09-30', end: '2099-10-01', description: 'Second session description' };
  document.querySelector('main').innerHTML = eventsView({ ...catalog, events: [event, second] }, {});
  const cards = [...document.querySelectorAll('.rich-event-card')];
  assert.equal(cards.length, 2);
  assert.ok(cards[0].querySelector('.feed-text').textContent.includes('原始發文'));
  // Both cards keep the author line and the original link.
  for (const card of cards) { assert.ok(card.querySelector('.event-author')); assert.ok(card.querySelector('a.event-original-link, .event-reference-actions a')); }
  if (isRedesign()) {
    assert.equal(cards[1].querySelector('.event-reference .feed-text'), null);
    assert.match(cards[1].querySelector('.event-description-text').textContent, /Second session description/);
    document.querySelector('main').innerHTML = richEventCard({ ...event, image: '' }, { ...catalog, posts: [] });
    assert.equal(document.querySelector('.event-media'), null);
    assert.equal(document.querySelector('.event-thumb-placeholder'), null);
  } else assert.equal(cards[1].querySelectorAll('.feed-text').length, 1);
  window.close();
});

test('new interface: the event period is a row of tabs that keep the search and country', () => {
  const window = setup();
  document.querySelector('main').innerHTML = eventsView(catalog, { q: 'concert', country: 'JP', period: 'past' });
  const tabs = [...document.querySelectorAll('.event-period-tabs .follow-tab')];
  if (isRedesign()) {
    assert.equal(tabs.length, 3);
    assert.deepEqual(tabs.map(tab => new URL(tab.href, 'https://example.com').searchParams.get('period')), [null, 'past', 'allEvents']);
    for (const tab of tabs) { const params = new URL(tab.href, 'https://example.com').searchParams; assert.equal(params.get('q'), 'concert'); assert.equal(params.get('country'), 'JP'); assert.equal(params.get('lang'), 'en'); }
    assert.equal(document.querySelector('.event-period-tabs [aria-current="page"]'), tabs[1]);
    // The period alone is not a filter: no result count.
    document.querySelector('main').innerHTML = eventsView(catalog, { period: 'past' });
    assert.equal(document.querySelector('.results-bar'), null);
  } else assert.equal(tabs.length, 0);
  window.close();
});
