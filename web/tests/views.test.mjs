import { isRedesign as redesignOn } from '../assets/redesign.js';
import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
const dom = new JSDOM('<html><body></body></html>', { url: 'http://localhost/' });
globalThis.document = dom.window.document;
globalThis.localStorage = dom.window.localStorage;
const { setLocale, t } = await import('../assets/i18n.js');
const { sourceCard, sortSources, postCard, togglePostExpansion, statusView } = await import('../assets/views.js');
const sources = [{ id:'a',name:'Alpha',countryCode:'JP',url:'/source/alpha/',updatedAt:'2026-01-01',avatar:'/assets/avatar.webp' },{id:'b',name:'Beta',countryCode:'KR',url:'/source/beta/',updatedAt:'2026-02-01'}];
const catalog = {posts:[{sourceId:'b'},{sourceId:'b'},{sourceId:'a'}]};
test('status distinguishes a fresh snapshot from zero collection coverage and budget deferral in four locales', () => {
  for (const locale of ['en', 'zh-Hant', 'ja', 'ko']) {
    setLocale(locale);
    document.body.innerHTML = statusView({ generatedAt: '2026-10-18T00:00:00Z', status: {
      overall: 'paused', updatedAt: '2026-10-18T00:00:00Z', services: [{ id: 'facebook', count: 73,
        status: 'paused', reasonCode: 'budget_deferred', errors: 0,
        coverage: { checkedSources24h: 0, totalSources: 73, lastSuccessAt: '' } }],
    } });
    assert.equal(document.querySelector('.status-hero h2').textContent, t('paused'));
    assert.equal(document.querySelector('.status-orb.ok'), null);
    assert.ok(document.querySelector('tbody').textContent.includes(t('budgetDeferred')));
    assert.ok(document.querySelector('thead').textContent.includes(t('checkedCoverage')));
    assert.match(document.querySelector('tbody').textContent, /0 \/ 73/);
    assert.ok(document.body.textContent.includes(t('snapshotNote')));
  }
});
test('unconfirmed coverage is unknown rather than zero successful checks in four locales', () => {
  for (const locale of ['en', 'zh-Hant', 'ja', 'ko']) {
    setLocale(locale);
    document.body.innerHTML = statusView({ status: { services: [{ id: 'facebook', count: 2,
      status: 'degraded', coverage: { checkedSources24h: null, totalSources: 2, lastSuccessAt: '' },
    }] } });
    const coverage = document.querySelector('tbody tr').children[3];
    assert.ok(coverage.textContent.includes(t('coverageUnknown')));
    assert.doesNotMatch(coverage.textContent, /[02] \/ 2/);
    assert.equal(coverage.querySelector('time'), null);
  }
});
test('directory sorting uses real post counts and remains independent of locale and following',()=>{
 setLocale('en');
 assert.deepEqual(sortSources(sources,'posts',true,catalog).map(s=>s.id),['b','a']);
 assert.deepEqual(sortSources(sources,'updated',false,catalog).map(s=>s.id),['a','b']);
 const html=sourceCard(sources[1],new Set(['b']),catalog);
 document.body.innerHTML=html;
 assert.equal(document.querySelector('.src-count').textContent,'2');
 assert.equal(document.querySelector('[data-follow]').getAttribute('aria-pressed'),'true');
 assert.equal(document.querySelector('h3 a').getAttribute('href'),'/source/beta/');
});
test('long original expands and collapses without truncating, duplicating, or interpreting markup',()=>{
 const original='原文 <script>alert(1)</script> & 保持\n'.repeat(20);
 for(const locale of ['en','zh-Hant','ja','ko']){
  setLocale(locale);
  document.body.innerHTML=postCard({sourceId:'a',text:original,url:'https://example.org/post',publishedAt:'2026-01-01',platform:'instagram'},sources);
  const button=document.querySelector('[data-expand-post]'), text=document.querySelector('.feed-text');
  assert.equal(text.textContent,original);
  assert.equal(document.querySelector('script'),null);
  assert.equal(document.querySelectorAll('.feed-text').length,1);
  togglePostExpansion(button);
  assert.equal(button.getAttribute('aria-expanded'),'true');
  assert.ok(text.classList.contains('is-expanded'));
  togglePostExpansion(button);
  assert.equal(button.getAttribute('aria-expanded'),'false');
  assert.ok(!text.classList.contains('is-expanded'));
  assert.equal(text.textContent,original);
 }
});
test('posts use source avatar fallback and link only explicit matching events',()=>{
 setLocale('en');
 const post={sourceId:'a',text:'Original',url:'https://example.org/post',publishedAt:'2026-01-01',platform:'instagram'};
 const events=[{id:'match',title:'Actual linked event',url:post.url,start:'2026-01-01',allDay:true,timezone:'America/Los_Angeles'},{id:'other',title:'Unrelated event',url:'https://example.org/elsewhere',start:'2026-01-01'}];
 document.body.innerHTML=postCard(post,sources,new Set(['a']),events);
 assert.equal(document.querySelector('.feed-avatar-wrap img').getAttribute('src'),sources[0].avatar);
 assert.equal(document.querySelectorAll('.feed-ev').length,1);
 assert.match(document.querySelector('.feed-ev').textContent,/Actual linked event/);
 assert.equal(document.querySelector('[data-share]').dataset.share,post.url);
 assert.equal(document.querySelector('[data-follow]').getAttribute('aria-pressed'),'true');
});

test('country facets count the current content and other filters without coupling language to country', async()=>{
 const {countryFacets,filterBar}=await import('../assets/views.js');
 const data={countries:[{code:'JP',count:21},{code:'KR',count:23}],events:[{countryCode:'JP',title:'Future concert',start:'2099-01-01',end:'2099-01-02',allDay:true},{countryCode:'KR',title:'Past',start:'2000-01-01',end:'2000-01-02',allDay:true}],sources:[{id:'a',countryCode:'JP',type:'club'},{id:'b',countryCode:'KR',type:'club'}],posts:[{countryCode:'JP',sourceId:'a'},{countryCode:'JP',sourceId:'a',isStory:true},{countryCode:'KR',sourceId:'b'}]};
 for(const locale of ['en','ja','ko','zh-Hant']){
  setLocale(locale);
  assert.equal(countryFacets({period:'upcoming'},data,'events').find(c=>c.code==='JP').count,1);
  assert.equal(countryFacets({period:'upcoming'},data,'events').find(c=>c.code==='KR').count,0);
  assert.equal(countryFacets({q:'missing',country:'JP'},data,'events').find(c=>c.code==='JP').count,0);
  assert.equal(countryFacets({followed:true},data,'sources',new Set(['b'])).find(c=>c.code==='JP').count,0);
  assert.equal(countryFacets({},data,'posts').find(c=>c.code==='JP').count,1);
  assert.equal(countryFacets({kind:'stories'},data,'posts').find(c=>c.code==='JP').count,1);
  document.body.innerHTML=filterBar({period:'past',q:''},data,'events');
  // The new interface shows the event period as tabs, so it alone is no filter to clear.
  assert.equal(!!document.querySelector('[data-action="reset"]'),!redesignOn());
 }
});

test('directory and profile generic website actions are localized while source names and custom link labels remain original',async()=>{
 const {sourceDetail}=await import('../assets/views.js');
 const source={...sources[0],name:'原始名稱',links:[{url:'https://example.org',label:'網站'},{url:'https://example.org/custom',label:'原始標題'}]};
 for(const [locale,label,country] of [['ja','ウェブサイト','日本'],['ko','웹사이트','일본'],['en','Website','Japan'],['zh-Hant','網站','日本']]){
  setLocale(locale);
  document.body.innerHTML=sourceCard(source,new Set(),catalog);
  assert.match(document.querySelector('.src-links').textContent,new RegExp(label));
  assert.equal(document.querySelector('.src-country-mobile').textContent,country);
  document.body.innerHTML=sourceDetail(source,{posts:[],sources:[source]},new Set());
  assert.match(document.querySelector('.profile-links').textContent,new RegExp(label));
  assert.match(document.querySelector('.profile-links').textContent,/原始標題/);
  assert.equal(document.querySelector('h1').textContent,'原始名稱');
 }
});

test('multi-day event cards display inclusive civil date ranges across time zones without changing single-day events',async()=>{
 const {eventDateLabel}=await import('../assets/views.js');
 setLocale('en');
 for(const timezone of ['Asia/Tokyo','Asia/Seoul','America/Los_Angeles','America/New_York']){
  assert.equal(eventDateLabel({start:'2026-03-07',end:'2026-03-10',allDay:true,timezone},{now:Date.parse('2026-09-23T00:00:00Z')}),'Mar 7 – Mar 9');
  assert.equal(eventDateLabel({start:'2026-03-07',end:'2026-03-08',allDay:true,timezone},{now:Date.parse('2026-09-23T00:00:00Z')}),'Mar 7');
  assert.equal(eventDateLabel({start:'2026-03-07',end:'invalid',allDay:true,timezone},{now:Date.parse('2026-09-23T00:00:00Z')}),'Mar 7');
 }
});

test('website source snapshots distinguish observation from publication and are excluded from default post facets',async()=>{
 const {countryFacets}=await import('../assets/views.js');
 const snapshot={sourceId:'a',text:'Original website',contentKind:'website_snapshot',platform:'website',publishedAt:null,observedAt:'2026-09-23T10:00:00Z',url:'https://example.org',countryCode:'JP'};
 for(const [locale,label] of [['en','Website snapshot'],['ja','ウェブページの保存記録'],['ko','웹페이지 스냅샷'],['zh-Hant','網站頁面快照']]){
  setLocale(locale);
  document.body.innerHTML=postCard(snapshot,sources);
  assert.match(document.querySelector('.notice').textContent,new RegExp(label));
  assert.match(document.querySelector('.feed-time').textContent,/23/);
  assert.equal(countryFacets({}, {posts:[snapshot],countries:[{code:'JP'}]},'posts')[0].count,0);
  assert.equal(countryFacets({platform:'website'}, {posts:[snapshot],countries:[{code:'JP'}]},'posts')[0].count,1);
 }
});

test('event cards show announced end times and label estimated calendar placeholders without presenting them as facts',async()=>{
 const {eventCard}=await import('../assets/views.js');
 const event={start:'2026-09-25T20:30:00+08:00',end:'2026-09-25T21:30:00+08:00',timezone:'Asia/Taipei',title:'Original concert'};
 for(const [locale,label] of [['en','End time not announced'],['ja','終了時刻は未発表'],['ko','종료 시각 미발표'],['zh-Hant','結束時間未公告']]){
  setLocale(locale);
  document.body.innerHTML=eventCard({...event,endEstimated:false});
  assert.match(document.querySelector('.event-time').textContent,/–/);
  document.body.innerHTML=eventCard({...event,endEstimated:true});
  assert.match(document.querySelector('.event-time').textContent,new RegExp(label));
  assert.doesNotMatch(document.querySelector('.event-time').textContent,/–/);
 }
});

test('"Clear filters" appears only for a real filter; in the new interface Following is a tab, not a filter', async () => {
 const { filterBar } = await import('../assets/views.js');
 const { isRedesign } = await import('../assets/redesign.js');
 const data = { countries: [{ code: 'JP' }], sources: [{ id: 'a', countryCode: 'JP', type: 'club' }], posts: [{ countryCode: 'JP', sourceId: 'a', platform: 'instagram' }], events: [] };
 setLocale('en');
 for (const [kind, state] of [['sources', { followed: true }], ['posts', { kind: 'following' }]]) {
  document.body.innerHTML = filterBar(state, data, kind, new Set());
  assert.equal(!!document.querySelector('[data-action="reset"]'), !isRedesign());
  document.body.innerHTML = filterBar({ ...state, country: 'JP' }, data, kind, new Set());
  assert.ok(document.querySelector('[data-action="reset"]'));
 }
});
test('new interface: status explains its snapshot once in the page notes, and the source page follows with a heart', async () => {
 const { sourceDetail } = await import('../assets/views.js');
 const { isRedesign } = await import('../assets/redesign.js');
 setLocale('en');
 document.body.innerHTML = statusView({ status: { services: [] } });
 assert.equal(document.body.textContent.split(t('snapshotNote')).length - 1, 1);
 assert.equal(!!document.querySelector('.page-notes'), isRedesign());
 document.body.innerHTML = sourceDetail(sources[0], { posts: [], sources }, new Set());
 assert.equal(!!document.querySelector('.source-profile [data-follow] path[d^="M20.8"]'), isRedesign());
 const { aboutView } = await import('../assets/views.js');
 for (const locale of ['en', 'zh-Hant', 'ja', 'ko']) {
  setLocale(locale);
  document.body.innerHTML = aboutView();
  assert.equal(!!document.querySelector('.page-heading a[href="https://github.com/skyhong2002/chumei"]'), isRedesign(), 'project origin is linked once on About');
  assert.equal(document.querySelector('.page-heading p').textContent.replace(/↗/g, ''), t('aboutBody'));
 }
});

test('new interface post cards: original source link, share and report in "⋯", one quiet archived-story hint; legacy keeps its row and notice', async()=>{
 const { isRedesign } = await import('../assets/redesign.js');
 const { sourceDetail, directoryHeader } = await import('../assets/views.js');
 const story={sourceId:'a',text:'Story text',url:'https://example.org/story',publishedAt:'2026-01-01',platform:'instagram',isStory:true,storyState:'expired',sourceAvailable:false,image:'https://example.org/s.jpg'};
 for(const [locale,original,follow] of [['zh-Hant','原始來源','追蹤來源'],['en','Original source','Follow source'],['ja','原文を見る','情報源をフォロー'],['ko','원문 보기','출처 팔로우']]){
  setLocale(locale);
  document.body.innerHTML=postCard(story,sources);
  const actions=document.querySelector('.feed-actions');
  assert.equal(actions.querySelector('.feed-original').getAttribute('href'),story.url);
  assert.match(actions.querySelector('.feed-original').textContent,new RegExp(original));
  assert.ok(actions.querySelector('[data-share]'));
  assert.ok(actions.querySelector('a[href^="/submit/"]'));
  if(isRedesign()){
   assert.equal(document.querySelector('.story-expired'),null);
   assert.equal(document.querySelector('.story-tag').getAttribute('title'),t('storyExpired'));
   assert.ok(actions.querySelector('.more-actions > .more-actions-menu [data-share]'));
   assert.ok(actions.querySelector('.more-actions > .more-actions-menu a[href^="/submit/"]'));
   assert.equal(actions.querySelector('[data-follow]').textContent.trim(),follow);
   // Source page: the page's own follow button is the only visible one (redesign.css hides the card's).
   document.body.innerHTML=sourceDetail(sources[0],{sources,posts:[story],events:[]},new Set());
   assert.equal(document.querySelectorAll('.source-updates-grid .more-actions').length,1);
  } else {
   assert.equal(document.querySelector('.story-expired').textContent,t('storyExpired'));
   assert.equal(document.querySelector('.more-actions'),null);
  }
 }
 // Directory sort: phones get one labelled menu in the new interface; the header buttons stay.
 setLocale('zh-Hant');
 document.body.innerHTML=directoryHeader('posts',true);
 assert.equal(document.querySelectorAll('.src-head [data-source-sort]').length,5);
 if(isRedesign()){
  const select=document.querySelector('.src-sort-bar select[data-source-sort-select]');
  assert.deepEqual([...select.options].map(o=>o.value),['name','country','type','posts','updated']);
  assert.equal(select.value,'posts');
  assert.match(document.querySelector('.src-sort-bar label').textContent,/排序/);
  assert.equal(document.querySelector('.src-sort-direction').dataset.sourceSort,'posts');
  assert.match(document.querySelector('.src-sort-direction').textContent,/遞減/);
 } else assert.equal(document.querySelector('.src-sort-bar'),null);
});
test('new interface: directory overflow links are labelled, feed titles open the feed, and form fields say required or optional', async () => {
 const { isRedesign } = await import('../assets/redesign.js');
 const { feedsView } = await import('../assets/views.js');
 const { submitView, contributeView } = await import('../assets/community.js');
 const links = n => Array.from({ length: n }, (_, i) => ({ url: `https://example.org/${i}`, label: 'Website' }));
 setLocale('en');
 document.body.innerHTML = sourceCard({ ...sources[0], links: links(5) }, new Set(), catalog) + sourceCard({ ...sources[1], links: links(6) }, new Set(), catalog);
 const more = [...document.querySelectorAll('.src-links-more')].map(node => node.textContent);
 assert.deepEqual(more, isRedesign() ? ['+2 links', '+3 links'] : []);
 setLocale('zh-Hant');
 document.body.innerHTML = sourceCard({ ...sources[0], links: links(4) }, new Set(), catalog);
 assert.equal(document.querySelector('.src-links-more'), null);
 const feeds = { feeds: [{ id: 'updates', title: 'updates', url: '/feeds/updates.xml', format: 'RSS' }] };
 document.body.innerHTML = feedsView(feeds);
 const card = document.querySelector('.feed-card');
 assert.equal(card.querySelectorAll('.copy-button').length, 1);
 if (isRedesign()) {
  assert.equal(card.querySelector('h2 a').getAttribute('href'), '/feeds/updates.xml');
  assert.equal(card.querySelector('.feed-actions .text-link'), null);
 } else assert.equal(card.querySelector('.feed-actions .text-link').getAttribute('href'), '/feeds/updates.xml');
 document.body.innerHTML = submitView({ countries: [] }) + contributeView();
 for (const label of document.querySelectorAll('form label[for]')) {
  const field = document.getElementById(label.htmlFor), tag = label.querySelector('.field-tag');
  if (!isRedesign()) { assert.equal(tag, null); continue; }
  assert.equal(tag.textContent, t(field.required ? 'fieldRequired' : 'fieldOptional'), label.htmlFor);
  assert.equal(tag.getAttribute('aria-hidden'), 'true');
 }
 assert.equal(document.querySelector('#submission-url').placeholder, isRedesign() ? 'https://www.instagram.com/…' : 'https://');
});

test('source page summary: the new interface adds a hidden "read more" that reveals the clamped summary', async () => {
  const { isRedesign } = await import('../assets/redesign.js');
  const { sourceDetail, toggleSummaryExpansion } = await import('../assets/views.js');
  setLocale('en');
  const source = { id:'s', name:'Summary Source', countryCode:'JP', summary:'A long biography. '.repeat(20), tags:['a','b','c','d','e'] };
  document.body.innerHTML = sourceDetail(source, { posts:[], sources:[source] }, new Set());
  const button = document.querySelector('[data-expand-summary]');
  if (!isRedesign()) { assert.equal(button, null); return; }
  assert.ok(button.hidden, 'shown only when the clamp cuts the text');
  assert.equal(document.querySelectorAll('.profile-tags .tag').length, 5, 'tags past three are hidden by CSS on phones, not dropped');
  toggleSummaryExpansion(button);
  assert.equal(button.getAttribute('aria-expanded'), 'true');
  assert.ok(document.querySelector('.source-biography').classList.contains('is-expanded'));
  assert.equal(button.textContent, 'Show less');
});
