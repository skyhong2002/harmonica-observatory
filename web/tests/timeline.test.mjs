import test from 'node:test';
import assert from 'node:assert/strict';
import {JSDOM} from 'jsdom';
import {timelinePosts,timelineCard,timelineView,bindTimeline} from '../assets/timeline.js';
import {togglePostExpansion} from '../assets/views.js';
import {setLocale} from '../assets/i18n.js';
import {isRedesign} from '../assets/redesign.js';
const catalog={sources:[{id:'jp',name:'日本の口琴',countryCode:'JP'},{id:'tw',name:'臺灣口琴社',countryCode:'TW'}],countries:[{code:'JP'},{code:'TW'}],events:[],posts:Array.from({length:61},(_,i)=>({id:'p'+i,sourceId:i%2?'jp':'tw',sourceName:i%2?'日本の口琴':'臺灣口琴社',countryCode:i%2?'JP':'TW',text:'Original '+i+'\n'+('完整原文 '.repeat(60)),platform:i%2?'instagram':'facebook',publishedAt:new Date(Date.UTC(2026,8,23,0,-i)).toISOString(),url:'https://example.com/post/'+i,image:i%3?'':'/assets/test.webp',isStory:i===60,storyState:i===60?'expired':undefined}))};
function setup(width=1440){const{window}=new JSDOM('<main></main>',{url:'https://example.com/?lang=en',pretendToBeVisual:true});for(const key of ['window','document','location','localStorage'])Object.defineProperty(globalThis,key,{value:key==='window'?window:window[key],configurable:true});window.innerWidth=width;window.scrollBy=()=>{};window.HTMLElement.prototype.getBoundingClientRect=function(){const height=this.classList.contains('feed-river-column')?[...this.children].reduce((sum,n)=>sum+100+(Number(n.dataset.timelineIndex)%3)*20,0):100;return{height,width:300,top:0,bottom:height};};return window;}

test('one chronological timeline excludes stories by default and filters country, platform and follows independently',()=>{
 assert.equal(timelinePosts(catalog,{}).length,60);
 assert.deepEqual(timelinePosts(catalog,{kind:'stories'}).map(p=>p.id),['p60']);
 assert.equal(timelinePosts(catalog,{country:'JP',platform:'instagram'}).length,30);
 assert.equal(timelinePosts(catalog,{country:'JP',platform:'facebook'}).length,0);
 assert.equal(timelinePosts(catalog,{kind:'following'},new Set(['tw'])).length,30);
 const reversed={...catalog,posts:[...catalog.posts].reverse()};assert.equal(timelinePosts(reversed,{})[0].id,'p0');
});

test('original image-first cards preserve escaped full original, source, follow/share/report and archive status',()=>{
 const window=setup();setLocale('en');const html=timelineCard({...catalog.posts[0],text:'<script>alert(1)</script>'+catalog.posts[0].text},catalog.sources,new Set(['tw']));
 document.querySelector('main').innerHTML=html;const card=document.querySelector('.home-feed-card');
 assert.ok(card.querySelector('.home-feed-thumb'));assert.ok(card.querySelector('.feed-text').textContent.includes('<script>alert(1)</script>'));assert.equal(card.querySelectorAll('script').length,0);
 assert.ok([...card.querySelector('.home-feed-body').children].indexOf(card.querySelector('.home-feed-thumb'))<[...card.querySelector('.home-feed-body').children].indexOf(card.querySelector('.feed-text')));
 assert.equal(card.querySelector('[data-follow]').getAttribute('aria-pressed'),'true');assert.ok(card.querySelector('[data-share]'));assert.ok(card.querySelector('a[href^="/submit/"]'));assert.match(timelineCard(catalog.posts[60],catalog.sources),/story-expired/);
 window.close();
});

test('original shortest-column layout uses 3 desktop columns and 1 mobile with no duplicate posts; expansion remains functional',async()=>{
 const window=setup(),root=document.querySelector('main');root.innerHTML=timelineView(catalog,{},new Set());
 const click=e=>{const b=e.target.closest('[data-expand-post]');if(b)togglePostExpansion(b);};root.addEventListener('click',click);
 const cleanup=bindTimeline(root);let cols=root.querySelectorAll('.feed-river-column');assert.equal(cols.length,3);assert.ok([...cols].every(n=>n.children.length>0));assert.equal(root.querySelectorAll('.home-feed-card').length,24);
 const button=root.querySelector('[data-expand-post]');button.click();await Promise.resolve();assert.equal(button.getAttribute('aria-expanded'),'true');assert.ok(button.closest('.home-feed-card').querySelector('.feed-text').classList.contains('is-expanded'));
 window.innerWidth=390;window.dispatchEvent(new window.Event('resize'));await new Promise(r=>setTimeout(r,130));cols=root.querySelectorAll('.feed-river-column');assert.equal(cols.length,1);assert.equal(root.querySelectorAll('.home-feed-card').length,24);assert.deepEqual([...cols[0].children].map(n=>Number(n.dataset.timelineIndex)),Array.from({length:24},(_,i)=>i));cleanup();root.removeEventListener('click',click);window.close();
});

test('unavailable images remove only the broken media frame and retain original text/source actions',async()=>{
 const window=setup(),root=document.querySelector('main');root.innerHTML=timelineView(catalog,{},new Set(),3);const cleanup=bindTimeline(root);
 const image=root.querySelector('.home-feed-thumb img'),card=image.closest('.home-feed-card');image.dispatchEvent(new window.Event('error'));await new Promise(r=>setTimeout(r,100));
 assert.equal(card.querySelector('.home-feed-thumb'),null);assert.ok(card.querySelector('.home-feed-body-no-image'));assert.ok(card.querySelector('.feed-text').textContent.includes('完整原文'));assert.ok(card.querySelector('.feed-open-link'));cleanup();window.close();
});

test('autoload starts only after manual load-more and always keeps a manual fallback',()=>{
 const window=setup(),root=document.querySelector('main'),observers=[];window.IntersectionObserver=class{constructor(cb){this.cb=cb;observers.push(this);}observe(node){this.node=node;}disconnect(){this.disconnected=true;}};
 root.innerHTML=timelineView(catalog,{},new Set(),24);let cleanup=bindTimeline(root);assert.equal(observers.length,0);root.querySelector('[data-action="more"]').click();cleanup();
 root.innerHTML=timelineView(catalog,{},new Set(),48);cleanup=bindTimeline(root);assert.equal(observers.length,1);let clicks=0;root.querySelector('[data-action="more"]').addEventListener('click',()=>clicks++);observers[0].cb([{isIntersecting:true}]);assert.equal(clicks,1);assert.equal(observers[0].disconnected,true);cleanup();root.innerHTML=timelineView(catalog,{},new Set(),100);const status=root.querySelector('.feed-load-more-status');status.focus();assert.equal(document.activeElement,status);assert.equal(root.querySelector('[data-action="more"]'),null);window.close();
});

test('timeline controls and actions translate in four languages while original text stays unchanged',()=>{
 const window=setup();for(const locale of ['en','zh-Hant','ja','ko']){setLocale(locale);const html=timelineView(catalog,{country:'JP'},new Set());assert.ok(html.includes('日本の口琴'));assert.ok(html.includes('id="catalog-search"'));assert.ok(html.includes('data-filter="platform"'));assert.ok(html.includes('data-filter="kind"'));assert.ok(!html.includes('undefined'));assert.ok(!html.includes('data-river-column'));}window.close();
});

test('first-time following empty state gives a useful directory action in all locales',()=>{
 const window=setup();for(const locale of ['en','zh-Hant','ja','ko']){setLocale(locale);document.querySelector('main').innerHTML=timelineView(catalog,{kind:'following'},new Set());const empty=document.querySelector('.empty-state');assert.ok(empty.querySelector('a[href="/source/"]'));assert.equal(empty.querySelector('a[href="/submit/"]'),null);assert.ok(!empty.textContent.includes('undefined'));}window.close();
});

test('historical posts show their year; linked events distinguish timezone and all-day civil dates',()=>{
 const window=setup();setLocale('en');const p={...catalog.posts[0],publishedAt:'2018-09-23T01:00:00Z',eventIds:['timed','civil']};document.querySelector('main').innerHTML=timelineCard(p,catalog.sources,new Set(),[{id:'timed',start:'2026-09-24T02:30:00Z',timezone:'America/Los_Angeles',url:'https://example.com/event',title:'LA concert'},{id:'civil',start:'2026-09-24',allDay:true,timezone:'America/Los_Angeles',url:'https://example.com/all-day',title:'All day'}]);
 assert.match(document.querySelector('.feed-latest-meta').textContent,/2018/);const linked=[...document.querySelectorAll('.timeline-event')];assert.match(linked[0].textContent,/Sep 23(?:, 2026)?.*19:30.*America\/Los_Angeles/);assert.match(linked[1].textContent,/Sep 24(?:, 2026)?.*All.day/);window.close();
});

test('website snapshots stay available explicitly without masquerading as newly published posts',()=>{
 const window=setup();setLocale('en');const snapshot={...catalog.posts[0],id:'snapshot',platform:'website',publishedAt:null,observedAt:'2026-09-23T12:00:00Z',contentKind:'website_snapshot'};const data={...catalog,posts:[snapshot,...catalog.posts]};assert.equal(timelinePosts(data,{}).some(p=>p.id==='snapshot'),false);assert.deepEqual(timelinePosts(data,{platform:'website'}).map(p=>p.id),['snapshot']);document.querySelector('main').innerHTML=timelineCard(snapshot,data.sources);assert.match(document.querySelector('.feed-latest-meta').textContent,/Observed, not published/);assert.match(document.querySelector('.feed-latest-meta time').title,/2026/);assert.match(document.querySelector(isRedesign() ? '.feed-latest-meta' : '.timeline-meta').textContent,/Website snapshot/);assert.ok(document.querySelector('.feed-text').textContent.includes(snapshot.text));window.close();
});


test('feed summary is concise and linked authors use one interface-language name',()=>{
 const window=setup();setLocale('en');const data={...catalog,sources:catalog.sources.map(source=>({...source,names:{en:'English author',original:source.name}}))};
 document.querySelector('main').innerHTML=timelineView(data,{});
 // The new interface shows the total once, beside "load more"; a result count only while filtered.
 if(isRedesign()){assert.equal(document.querySelector('.feed-river-summary'),null);assert.match(document.querySelector('.feed-load-more-status').textContent,/Showing 24 of 60/);document.querySelector('main').innerHTML=timelineView(data,{country:'JP'});}
 assert.equal(document.querySelector('.feed-river-summary').children.length,1);
 if(isRedesign()){document.querySelector('main').innerHTML=timelineView(data,{kind:'following'},new Set(['jp']));assert.equal(document.querySelector('.feed-river-summary'),null,'the Following tab is not a filter');document.querySelector('main').innerHTML=timelineView(data,{});}
 assert.equal(document.querySelector('.source-name-link').textContent,'English author');
 assert.ok(document.querySelector('.feed-text').textContent.includes('完整原文'));
 window.close();
});

test('new interface card footer: follow source, the shared original-source label, then share and report in "⋯"',()=>{
 if(!isRedesign())return;
 const window=setup();
 for(const [locale,follow,original] of [['zh-Hant','追蹤來源','原始來源'],['en','Follow source','Original source'],['ja','情報源をフォロー','原文を見る'],['ko','출처 팔로우','원문 보기']]){
  setLocale(locale);document.querySelector('main').innerHTML=timelineCard(catalog.posts[0],catalog.sources,new Set());
  const footer=document.querySelector('.home-feed-footer');
  assert.equal(footer.querySelector('[data-follow]').textContent.trim(),follow);
  assert.equal(footer.querySelector('.feed-open-link').textContent.replace('↗','').trim(),original);
  assert.equal(footer.querySelectorAll('.timeline-actions').length,1);
  assert.ok(footer.querySelector('.more-actions .more-actions-menu [data-share]'));
  assert.ok(footer.querySelector('.more-actions .more-actions-menu a[href^="/submit/"]'));
 }
 // A Threads title that only differs from the text by its "@handle ↩️:" prefix is not shown twice.
 setLocale('en');
 const post={...catalog.posts[0],image:'',title:'@handle: The same opening sentence of this reply…',text:'@handle ↩️: The same opening sentence of this reply, and then the rest.'};
 document.querySelector('main').innerHTML=timelineCard(post,catalog.sources,new Set());
 assert.equal(document.querySelector('.home-feed-title'),null);
 window.close();
});
