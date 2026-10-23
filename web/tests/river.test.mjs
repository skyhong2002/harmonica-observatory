import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { newColumn, normalizeColumns, loadColumns, activeStories, filterColumn, riverView, bindRiver, COLUMN_KEY } from '../assets/river.js';
import { setLocale } from '../assets/i18n.js';

const catalog = {
  sources: [{id:'jp',name:'日本の口琴',countryCode:'JP',type:'artist'}, {id:'tw',name:'口琴',countryCode:'TW',type:'ensemble'}],
  posts: Array.from({length:32},(_,i)=>({id:`p${i}`,sourceId:i%2?'jp':'tw',sourceName:i%2?'日本の口琴':'口琴',text:`Original ${i}`,countryCode:i%2?'JP':'TW',platform:i%2?'instagram':'youtube',url:`https://example.com/${i}`,publishedAt:'2026-01-01',isStory:i===1,storyState:i===1?'expired':undefined})),
  events:[{id:'event',title:'Future concert',countryCode:'JP',start:'2099-01-01',end:'2099-01-02',allDay:true,timezone:'Asia/Tokyo'}],
  countries:[{code:'JP'},{code:'TW'}],
  stories:[{id:'active',sourceId:'jp',sourceName:'日本の口琴',storyState:'active',expiresAt:'2099-01-01',url:'https://example.com/story'},{id:'old',storyState:'expired',expiresAt:'2000-01-01'}],
};
function dom() {
  const {window} = new JSDOM('<main></main>',{url:'https://example.com/?lang=en',pretendToBeVisual:true});
  for(const name of ['window','document','location','localStorage']) Object.defineProperty(globalThis,name,{value:name==='window'?window:window[name],configurable:true});
  return window;
}
const wait = () => new Promise(resolve=>setTimeout(resolve,230));

test('column filtering keeps country, language, platform, category, follows and archive independent',()=>{
  assert.equal(filterColumn(catalog,{...newColumn(),country:'JP',platform:'instagram',type:'artist'}).length,16);
  assert.equal(filterColumn(catalog,{...newColumn(),country:'JP',type:'ensemble'}).length,0);
  assert.equal(filterColumn(catalog,{...newColumn(),followed:true},new Set(['tw'])).length,16);
  assert.equal(filterColumn(catalog,{...newColumn(),kind:'stories'})[0].storyState,'expired');
  assert.deepEqual(activeStories(catalog).map(p=>p.id),['active']);
  assert.equal(filterColumn(catalog,newColumn('events')).length,1);
  assert.equal(filterColumn(catalog,{...newColumn(),q:'Original 31'}).length,1);
});

test('storage validates hostile or damaged data without losing existing language/follow settings',()=>{
  const window=dom();
  window.localStorage.setItem('atlas-language','ja');
  window.localStorage.setItem('atlas-following','["jp"]');
  window.localStorage.setItem(COLUMN_KEY,'{bad');
  assert.equal(loadColumns().length,3);
  assert.equal(normalizeColumns([null,{mode:'posts',country:'JP',followed:'false',kind:'invalid'}])[0].followed,false);
  assert.equal(normalizeColumns(Array.from({length:30},()=>newColumn())).length,6);
  assert.equal(window.localStorage.getItem('atlas-language'),'ja');
  assert.equal(window.localStorage.getItem('atlas-following'),'["jp"]');
  window.close();
});

test('real DOM deck supports independent facets, IME, more, add/remove and URL callbacks',async()=>{
  const window=dom(),root=window.document.querySelector('main'),patches=[];
  setLocale('en');
  root.innerHTML=riverView(catalog,{},new Set(['jp']));
  const cleanup=bindRiver(root,{catalog,following:new Set(['jp']),onStateChange:p=>patches.push(p)});
  let cols=root.querySelectorAll('.feed-cols .feed-col');
  assert.equal(cols.length,3);
  assert.equal(root.querySelectorAll('.river-mobile').length,1);
  assert.equal(cols[0].querySelectorAll('.post-card').length,24);
  cols[0].querySelector('[data-river-more]').click();
  assert.equal(cols[0].querySelectorAll('.post-card').length,32);
  const second=cols[1].querySelector('[data-river-field="country"]');
  second.value='TW';second.dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(cols[1].querySelectorAll('.post-card').length,0);
  assert.equal(cols[0].querySelectorAll('.post-card').length,32);
  assert.equal(patches.length,0,'independent second column does not replace URL facets');
  const input=cols[0].querySelector('[data-river-field="q"]');
  input.focus();input.dispatchEvent(new window.CompositionEvent('compositionstart',{bubbles:true}));
  input.value='Original 31';input.dispatchEvent(new window.InputEvent('input',{bubbles:true,isComposing:true}));
  await wait();assert.equal(cols[0].querySelectorAll('.post-card').length,32);
  input.dispatchEvent(new window.CompositionEvent('compositionend',{bubbles:true}));
  await wait();assert.equal(cols[0].querySelectorAll('.post-card').length,1);
  assert.equal(document.activeElement,input);
  assert.equal(patches.at(-1).q,'Original 31');
  assert.equal(root.querySelector('.river-mobile [data-river-field="q"]').value,'Original 31');
  root.querySelector('[data-river-add="posts"]').click();
  assert.equal(root.querySelectorAll('.feed-cols .feed-col').length,4);
  root.querySelector('.feed-cols .feed-col:last-of-type [data-river-remove]').click();
  assert.equal(root.querySelectorAll('.feed-cols .feed-col').length,3);
  assert.equal(JSON.parse(localStorage.getItem(COLUMN_KEY))[1].country,'TW');
  cleanup();window.close();
});

test('horizontal wheel and touch navigation preserve vertical column scrolling; rebind restores positions',()=>{
  const window=dom(),root=document.querySelector('main');
  root.innerHTML=riverView(catalog,{});
  let cleanup=bindRiver(root,{catalog});
  let deck=root.querySelector('.feed-cols');
  Object.defineProperties(deck,{scrollWidth:{value:1600},clientWidth:{value:1000}});
  const vertical=new window.WheelEvent('wheel',{deltaY:80,bubbles:true,cancelable:true});
  deck.dispatchEvent(vertical);assert.equal(vertical.defaultPrevented,false);assert.equal(deck.scrollLeft,0);
  const horizontal=new window.WheelEvent('wheel',{deltaY:80,shiftKey:true,bubbles:true,cancelable:true});
  deck.dispatchEvent(horizontal);assert.equal(horizontal.defaultPrevented,true);assert.equal(deck.scrollLeft,80);
  const touchEvent=(type,x,y)=>{ const e=new window.Event(type,{bubbles:true,cancelable:true});Object.defineProperty(e,'touches',{value:[{clientX:x,clientY:y}]});return e; };
  deck.dispatchEvent(touchEvent('touchstart',200,100));
  const swipe=touchEvent('touchmove',100,105);deck.dispatchEvent(swipe);
  assert.equal(swipe.defaultPrevented,true);assert.equal(deck.scrollLeft,180);
  root.querySelector('.feed-col').scrollTop=350;
  cleanup();root.innerHTML=riverView(catalog,{});cleanup=bindRiver(root,{catalog});
  assert.equal(root.querySelector('.feed-cols').scrollLeft,180);
  assert.equal(root.querySelector('.feed-col').scrollTop,350);
  cleanup();window.close();
});

test('four locales translate column controls and empty active stories honestly',()=>{
  const window=dom();
  for(const [locale,label] of [['en','Add column'],['zh-Hant','新增河道'],['ja','カラムを追加'],['ko','열 추가']]){
    setLocale(locale);const html=riverView({...catalog,stories:[]},{});
    assert.ok(html.includes(label));assert.ok(!html.includes('story-ring'));
    assert.ok(!html.includes('Harmonica Atlas'));assert.ok(!html.includes('undefined'));
  }
  window.close();
});

test('event facets resolve explicit source IDs and exact linked-post URLs without guessing names',()=>{
  const future=(id,extra={})=>({id,title:'日本の口琴',start:'2099-01-01',end:'2099-01-02',allDay:true,timezone:'Asia/Tokyo',...extra});
  const data={...catalog,events:[
    future('post-url',{url:catalog.posts[1].url}),
    future('source-url',{sourceUrl:catalog.posts[0].url}),
    future('explicit-id',{sourceId:'jp'}),
    future('venue-country',{url:catalog.posts[1].url,countryCode:'TW'}),
    future('same-name-only',{url:'https://unrelated.example/event'}),
    future('two-linked-sources',{url:catalog.posts[1].url,sourceUrl:catalog.posts[0].url}),
  ]};
  const ids=(facets={},following=new Set(['jp']))=>filterColumn(data,{...newColumn('events'),...facets},following).map(e=>e.id);
  assert.deepEqual(ids({followed:true}),['post-url','explicit-id','venue-country','two-linked-sources']);
  assert.deepEqual(ids({kind:'following',type:'artist',country:'JP'}),['post-url','explicit-id','two-linked-sources']);
  assert.deepEqual(ids({followed:true,type:'ensemble',country:'TW'},new Set(['tw'])),['source-url','two-linked-sources']);
  assert.deepEqual(ids({followed:true,type:'ensemble'},new Set(['jp'])),[], 'type and following must match the same explicit source');
  assert.deepEqual(ids({followed:true,country:'TW'}),['venue-country'], 'event country is the venue country when provided');
  assert.equal(ids().length,6, 'unresolved sources remain visible when no source facets are selected');
  assert.ok(!ids({followed:true}).includes('same-name-only'),'matching source display names cannot establish ownership');
});

test('removing the first post column synchronizes mobile facets, results and URL callbacks',()=>{
  const window=dom(),root=document.querySelector('main'),patches=[];
  localStorage.setItem(COLUMN_KEY,JSON.stringify([
    newColumn(),
    {...newColumn(),q:'Original',country:'TW',platform:'youtube',type:'ensemble',kind:'following'},
    newColumn('events'),
  ]));
  root.innerHTML=riverView(catalog,{country:'JP'},new Set(['jp']));
  const cleanup=bindRiver(root,{catalog,following:new Set(['jp']),onStateChange:patch=>patches.push(patch)});
  assert.equal(root.querySelector('.river-mobile [data-river-field="country"]').value,'JP');
  root.querySelector('.feed-cols [data-river-remove]').click();
  const mobile=root.querySelector('.river-mobile');
  for(const [key,value] of Object.entries({q:'Original',country:'TW',platform:'youtube',type:'ensemble'})) {
    assert.equal(mobile.querySelector(`[data-river-field="${key}"]`).value,value);
    assert.equal(patches.at(-1)[key],value);
  }
  const followed=mobile.querySelector('[data-river-field="followed"]');
  assert.equal(followed.checked,true, 'legacy following kind remains reflected in checkbox');
  assert.equal(mobile.querySelectorAll('.post-card').length,0);
  followed.checked=false;followed.dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(mobile.querySelectorAll('.post-card').length,16);
  assert.equal(patches.at(-1).kind,'');
  assert.equal(root.querySelector('.feed-cols [data-river-field="followed"]').checked,false);
  cleanup();window.close();
});

test('embedded river can omit its story strip while the standalone exported strip keeps active-only semantics',async()=>{
  const window=dom();
  const {storyStrip}=await import('../assets/river.js');
  assert.ok(storyStrip(catalog).includes('https://example.com/story'));
  assert.ok(!storyStrip(catalog).includes('2000-01-01'));
  const root=document.querySelector('main');
  root.innerHTML=riverView(catalog,{},new Set(),{stories:false});
  assert.equal(root.querySelectorAll('.story-strip').length,0);
  assert.equal(root.querySelectorAll('.river').length,1);
  const cleanup=bindRiver(root,{catalog});
  root.querySelector('[data-river-add="events"]').click();
  assert.equal(root.querySelectorAll('.feed-cols .feed-col').length,4);
  cleanup();window.close();
});

test('active stories expose actual image/video previews, source labels, expiry and original links in all four locales',async()=>{
  const window=dom();
  const {storyStrip}=await import('../assets/river.js');
  const base={sourceId:'jp',sourceName:'原始 <b>來源</b>',storyState:'active',expiresAt:'2099-01-01T00:00:00Z',sourceAvailable:true,url:'https://example.com/actual-story'};
  const data={...catalog,stories:[
    {...base,id:'image',image:'https://example.com/actual-preview.jpg'},
    {...base,id:'video',videoUrl:'https://example.com/actual-video.mp4',image:'https://example.com/actual-poster.jpg'},
    {...base,id:'missing',image:'javascript:alert(1)',videoUrl:'javascript:alert(2)'},
    {...base,id:'expired',storyState:'expired',image:'https://example.com/expired.jpg'},
    {...base,id:'unavailable',sourceAvailable:false,image:'https://example.com/unavailable.jpg'},
    {...base,id:'invalid-expiry',expiresAt:'not-a-date'},
  ]};
  for(const locale of ['en','zh-Hant','ja','ko']){
    setLocale(locale);document.querySelector('main').innerHTML=storyStrip(data);
    const root=document.querySelector('main');
    assert.equal(root.querySelectorAll('.story-item').length,3);
    assert.equal(root.querySelector('[data-story-id="image"] img').getAttribute('src'),'https://example.com/actual-preview.jpg');
    const video=root.querySelector('video');
    assert.equal(video.getAttribute('poster'),'https://example.com/actual-poster.jpg');
    assert.equal(video.querySelector('source').getAttribute('src'),'https://example.com/actual-video.mp4');
    assert.equal(video.hasAttribute('controls'),true);assert.equal(video.hasAttribute('autoplay'),false);
    assert.equal(root.querySelectorAll('.story-expiry time').length,3);
    assert.equal(root.querySelectorAll('.story-original[href="https://example.com/actual-story"]').length,3);
    assert.ok(root.querySelector('.story-name').textContent.includes('<b>來源</b>'));
    assert.equal(root.querySelector('b'),null);
    assert.equal(root.querySelector('[data-story-id="missing"] img'),null);
    assert.ok(root.querySelector('[data-story-id="missing"] .story-preview-missing'));
    assert.equal(root.querySelector('[data-story-id="expired"]'),null);
  }
  window.close();
});

test('active story tile disappears at actual expiry while its archive remains in post data',async()=>{
  const window=dom(),root=document.querySelector('main');
  const {storyStrip}=await import('../assets/river.js');
  setLocale('en');
  const data={...catalog,stories:[{...catalog.stories[0],expiresAt:new Date(Date.now()+150).toISOString()}]};
  root.innerHTML=`<div class="home-stories">${storyStrip(data)}</div>${riverView(data,{},new Set(),{stories:false})}`;
  const cleanup=bindRiver(root,{catalog:data});
  assert.equal(root.querySelectorAll('.story-item').length,1);
  await new Promise(resolve=>setTimeout(resolve,230));
  assert.equal(root.querySelectorAll('.story-item').length,0);
  assert.ok(root.querySelector('.story-empty').textContent.includes('No active stories'));
  assert.equal(data.posts.find(p=>p.isStory).storyState,'expired');
  cleanup();window.close();
});
