import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { activeStories, storiesView, bindStories, storyObservedMarkup } from '../assets/stories.js';
import { setLocale } from '../assets/i18n.js';

const localeDocument = new JSDOM('', { url: 'https://example.org/' });
Object.defineProperty(globalThis, 'document', { value: localeDocument.window.document, configurable: true });
Object.defineProperty(globalThis, 'localStorage', { value: localeDocument.window.localStorage, configurable: true });

const story = { id: 'live', sourceId: 'source', sourceName: '原始 <b>名稱</b>', image: '/assets/story.webp', url: 'https://example.org/story', avatar: 'https://example.org/expired-avatar.jpg', expiresAt: '2099-01-01T00:00:00Z', publishedAt: '2026-09-23T00:00:00Z', storyState: 'active' };
const catalog = { sources: [{ id: 'source', avatar: '/assets/cached-avatar.webp' }], stories: [story] };

test('stories use only currently verifiable active records and preserve safe original media in four locales', () => {
  const data = { ...catalog, stories: [story,
    { ...story, id: 'expired', expiresAt: '2000-01-01' },
    { ...story, id: 'unknown', expiresAt: '' },
    { ...story, id: 'archived', storyState: 'archived' },
    { ...story, id: 'removed', sourceAvailable: false },
  ] };
  assert.deepEqual(activeStories(data).map(s => s.id), ['live']);
  for (const [locale, expiry] of [['en', 'Shown until'], ['zh-Hant', '展示至'], ['ja', '表示期限'], ['ko', '표시 기한']]) {
    setLocale(locale);
    const dom = new JSDOM(storiesView(data));
    const root = dom.window.document;
    assert.equal(root.querySelectorAll('.ob-story-card').length, 1);
    assert.equal(root.querySelector('.ob-story-image').getAttribute('src'), story.image);
    assert.equal(root.querySelector('.ob-story-avatar img').getAttribute('src'), '/assets/cached-avatar.webp');
    assert.equal(root.querySelector('.ob-story-original').getAttribute('href'), story.url);
    assert.equal(root.querySelector('.ob-story-identity strong').textContent, story.sourceName);
    assert.equal(root.querySelectorAll('b').length, 0);
    assert.ok(root.querySelector('.ob-story-footer').textContent.includes(expiry));
    assert.equal(root.querySelector('[role="progressbar"]'), null, 'decorative legacy rule makes no fake progress claim');
    dom.window.close();
  }
});

test('unsafe media and unknown sources remain honest; video playback requires user action', () => {
  setLocale('en');
  const dom = new JSDOM(storiesView({ stories: [
    { ...story, sourceId: '', sourceName: '', image: 'javascript:alert(1)', url: 'javascript:alert(1)' },
    { ...story, id: 'video', videoUrl: 'https://example.org/video.mp4' },
  ] }));
  const root = dom.window.document;
  assert.equal(root.querySelector('.ob-story-card').querySelector('a'), null);
  assert.equal(root.querySelector('.ob-story-card').querySelector('.ob-story-image'), null);
  assert.ok(root.querySelector('.ob-story-fallback').textContent.includes('unavailable'));
  const video = root.querySelector('video');
  assert.ok(video.hasAttribute('controls')); assert.ok(!video.hasAttribute('autoplay'));
  assert.equal(video.getAttribute('poster'), story.image);
  dom.window.close();
});

test('empty state describes retrieval status without claiming sources published nothing', () => {
  for (const [locale, message] of [['en', 'No active stories have been retrieved yet'], ['zh-Hant', '尚未取得有效限動'], ['ja', '有効なストーリーはまだ取得できていません'], ['ko', '아직 유효한 스토리를 가져오지 못했습니다']]) {
    setLocale(locale);
    assert.ok(storiesView({ stories: [] }).includes(message));
  }
});

test('expiry removes only expired cards, keeps live playback nodes, and preserves archive data', async () => {
  setLocale('en');
  const expires = { ...story, id: 'ending', expiresAt: new Date(Date.now() + 60).toISOString() };
  const data = { ...catalog, stories: [expires, story], posts: [expires] };
  const dom = new JSDOM(`<main>${storiesView(data)}</main>`, { pretendToBeVisual: true });
  const root = dom.window.document.querySelector('main');
  const kept = root.querySelector('[data-story-id="live"]');
  const cleanup = bindStories(root, { catalog: data });
  const strip = root.querySelector('.ob-story-strip');
  strip.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true }));
  assert.ok(strip.scrollLeft > 0);
  await new Promise(resolve => setTimeout(resolve, 120));
  assert.equal(root.querySelector('[data-story-id="ending"]'), null);
  assert.equal(root.querySelector('[data-story-id="live"]'), kept);
  assert.equal(data.posts.length, 1); assert.equal(data.stories.length, 2);
  cleanup(); dom.window.close();
});

test('preview failure is announced only after a media error including video source failures',()=>{
 setLocale('en');const data={...catalog,stories:[{...story,videoUrl:'https://example.org/video.mp4'}]};const dom=new JSDOM(`<main>${storiesView(data)}</main>`);const root=dom.window.document.querySelector('main');const status=root.querySelector('.ob-story-fallback');assert.equal(status.hidden,true);const cleanup=bindStories(root,{catalog:data});assert.equal(status.hidden,true);root.querySelector('video source').dispatchEvent(new dom.window.Event('error'));assert.equal(status.hidden,false);assert.equal(status.getAttribute('role'),'status');assert.ok(root.querySelector('.ob-story-original'));cleanup();dom.window.close();
});

function refreshingStoryDom(data = catalog) {
  const dom = new JSDOM(`<main><input id="draft" value="unsent"><iframe id="calendar"></iframe><div id="river">unchanged</div>${storiesView(data)}</main>`, { url: 'https://example.org/', pretendToBeVisual: true });
  return { dom, root: dom.window.document.querySelector('main'), doc: dom.window.document };
}
const settle = () => new Promise(resolve => setTimeout(resolve, 0));

test('automatic refresh patches only stories while preserving live media, focus, scroll, calendar and river nodes', async () => {
  setLocale('en'); const data = { ...catalog, stories: [{ ...story, videoUrl: 'https://example.org/video.mp4' }] };
  const { dom, root, doc } = refreshingStoryDom(data), pending = [];
  const oldCard = root.querySelector('.ob-story-card'), video = root.querySelector('video'); video.currentTime = 12;
  const calendar = root.querySelector('#calendar'), river = root.querySelector('#river'), draft = root.querySelector('#draft');
  const strip = root.querySelector('.ob-story-strip'); strip.scrollLeft = 87;
  const cleanup = bindStories(root, { catalog: data, refreshCatalog: ({signal}) => new Promise(resolve => pending.push({resolve, signal})) });
  draft.focus(); doc.dispatchEvent(new dom.window.Event('visibilitychange')); doc.dispatchEvent(new dom.window.Event('visibilitychange')); assert.equal(pending.length, 1); assert.equal(root.querySelector('[data-refresh-stories]'), null);
  pending[0].resolve({ ...data, stories: [{ ...story, id: 'new' }, ...data.stories] }); await settle();
  assert.equal(root.querySelectorAll('.ob-story-card').length, 2); assert.equal(root.querySelector('[data-story-id="live"]'), oldCard); assert.equal(root.querySelector('video'), video); assert.equal(video.currentTime, 12);
  assert.equal(root.querySelector('#calendar'), calendar); assert.equal(root.querySelector('#river'), river); assert.equal(doc.activeElement, draft); assert.equal(strip.scrollLeft, 87); assert.equal(data.stories.length, 2);
  cleanup(); dom.window.close();
});

test('automatic refresh failures and invalid responses keep existing stories in four locales', async () => {
  for (const locale of ['en', 'zh-Hant', 'ja', 'ko']) {
    setLocale(locale); const data = { ...catalog, stories: [story] }, { dom, root } = refreshingStoryDom(data);
    const card = root.querySelector('.ob-story-card'); let count = 0;
    const cleanup = bindStories(root, { catalog: data, refreshCatalog: async () => { if (++count === 1) throw new Error('offline'); return {}; } });
    for (let i = 0; i < 2; i++) { root.ownerDocument.dispatchEvent(new dom.window.Event('visibilitychange')); await settle(); assert.equal(root.querySelector('.ob-story-card'), card); assert.equal(data.stories.length, 1); assert.equal(root.querySelector('[data-refresh-stories]'), null); }
    cleanup(); dom.window.close();
  }
});

test('60-second polling skips hidden pages; visibility resumes and preserves focused unsent text', async () => {
  setLocale('en'); const data = { ...catalog, stories: [] }, { dom, root, doc } = refreshingStoryDom(data);
  let visibility = 'visible'; Object.defineProperty(doc, 'visibilityState', { get: () => visibility });
  let intervalCallback, delay, intervalCleared = false, calls = 0;
  const originalSet = globalThis.setInterval, originalClear = globalThis.clearInterval;
  globalThis.setInterval = (callback, milliseconds) => { intervalCallback = callback; delay = milliseconds; return 42; };
  globalThis.clearInterval = handle => { if (handle === 42) intervalCleared = true; else originalClear(handle); };
  try {
    const cleanup = bindStories(root, { catalog: data, refreshCatalog: async () => { calls++; return { ...catalog, stories: [story] }; } });
    assert.equal(delay, 60000); assert.equal(calls, 0);
    const draft = root.querySelector('#draft'); draft.focus(); draft.value = 'still writing';
    visibility = 'hidden'; await intervalCallback(); assert.equal(calls, 0);
    visibility = 'visible'; doc.dispatchEvent(new dom.window.Event('visibilitychange')); await settle(); assert.equal(calls, 1); assert.equal(root.querySelectorAll('.ob-story-card').length, 1); assert.equal(doc.activeElement, draft); assert.equal(draft.value, 'still writing');
    await intervalCallback(); assert.equal(calls, 2);
    cleanup(); assert.equal(intervalCleared, true); doc.dispatchEvent(new dom.window.Event('visibilitychange')); await intervalCallback(); assert.equal(calls, 2);
  } finally { globalThis.setInterval = originalSet; globalThis.clearInterval = originalClear; dom.window.close(); }
});

test('leaving the page aborts in-flight reads and ignores stale responses without changing the shared catalog', async () => {
  setLocale('en'); const data = { ...catalog, stories: [story] }, { dom, root } = refreshingStoryDom(data); let request;
  const cleanup = bindStories(root, { catalog: data, refreshOnMount: true, refreshCatalog: ({signal}) => new Promise(resolve => request = {signal, resolve}) });
  assert.ok(request); cleanup(); assert.equal(request.signal.aborted, true);
  root.innerHTML = '<textarea>unsubmitted report</textarea>'; const field = root.querySelector('textarea'); field.focus();
  request.resolve({ ...catalog, stories: [] }); await settle();
  assert.equal(data.stories.length, 1); assert.equal(root.querySelector('textarea'), field); assert.equal(root.ownerDocument.activeElement, field); dom.window.close();
});

test('rapid hidden-visible transitions abort old reads and queue exactly one fresh read without overlap', async () => {
  setLocale('en'); const data = { ...catalog, stories: [story] }, { dom, root, doc } = refreshingStoryDom(data); let visibility = 'visible'; Object.defineProperty(doc, 'visibilityState', { get: () => visibility });
  const pending = []; const cleanup = bindStories(root, { catalog: data, refreshOnMount: true, refreshCatalog: ({signal}) => new Promise(resolve => pending.push({signal, resolve})) });
  visibility = 'hidden'; doc.dispatchEvent(new dom.window.Event('visibilitychange')); assert.equal(pending[0].signal.aborted, true);
  visibility = 'visible'; doc.dispatchEvent(new dom.window.Event('visibilitychange')); doc.dispatchEvent(new dom.window.Event('visibilitychange')); assert.equal(pending.length, 1);
  pending[0].resolve({ stories: [] }); await settle(); assert.equal(pending.length, 2); assert.equal(data.stories.length, 1);
  pending[1].resolve({ ...catalog, stories: [story, { ...story, id: 'fresh' }] }); await settle(); assert.equal(data.stories.length, 2); cleanup(); dom.window.close();
});

test('refreshing out a focused removed story moves focus to the strip while valid stories remain', async () => {
  setLocale('en'); const data = { ...catalog, stories: [story] }, { dom, root, doc } = refreshingStoryDom(data);
  const cleanup = bindStories(root, { catalog: data, refreshCatalog: async () => ({ ...catalog, stories: [] }) });
  root.querySelector('.ob-story-original').focus(); root.ownerDocument.dispatchEvent(new dom.window.Event('visibilitychange')); await settle();
  assert.equal(root.querySelectorAll('.ob-story-card').length, 0); assert.ok(root.querySelector('.ob-story-empty')); assert.equal(doc.activeElement, root.querySelector('.ob-story-strip')); cleanup(); dom.window.close();
});

test('hung automatic requests time out and permit retry; their late responses cannot replace newer stories', async () => {
  setLocale('en'); const data = { ...catalog, stories: [story] }, { dom, root } = refreshingStoryDom(data); const pending = [];
  const cleanup = bindStories(root, { catalog: data, refreshTimeout: 25, refreshCatalog: ({signal}) => new Promise(resolve => pending.push({signal, resolve})) });
  root.ownerDocument.dispatchEvent(new dom.window.Event('visibilitychange')); await new Promise(resolve => setTimeout(resolve, 40));
  assert.equal(pending[0].signal.aborted, true); assert.equal(root.querySelector('[data-refresh-stories]'), null);
  root.ownerDocument.dispatchEvent(new dom.window.Event('visibilitychange')); assert.equal(pending.length, 2); pending[1].resolve({ ...catalog, stories: [story, { ...story, id: 'newer' }] }); await settle();
  pending[0].resolve({ ...catalog, stories: [] }); await settle(); assert.equal(data.stories.length, 2); cleanup(); dom.window.close();
});

test('retrieval timestamp uses active story observation evidence and clears when the final story expires', async () => {
  setLocale('en'); const data = { ...catalog, generatedAt: '2099-01-01', stories: [{ ...story, observedAt: '2026-09-22T08:00:00Z', expiresAt: new Date(Date.now() + 55).toISOString() }, { ...story, id: 'past', expiresAt: '2000-01-01', observedAt: '2099-01-01' }] };
  const dom = new JSDOM(`<main>${storyObservedMarkup(data)}${storiesView(data)}</main>`, { pretendToBeVisual: true }); const root = dom.window.document.querySelector('main');
  assert.match(root.querySelector('[data-story-observed]').textContent, /Last retrieved/); assert.equal(root.querySelector('[data-story-observed] time').getAttribute('datetime'), '2026-09-22T08:00:00.000Z');
  const cleanup = bindStories(root, { catalog: data }); await new Promise(resolve => setTimeout(resolve, 85)); assert.equal(root.querySelector('[data-story-observed]').textContent, ''); assert.ok(root.querySelector('.ob-story-empty')); cleanup(); dom.window.close();
});
