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
  assert.ok(document.querySelector('[data-action="reset"]'));
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
