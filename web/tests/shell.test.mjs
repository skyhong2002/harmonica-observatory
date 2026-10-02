import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

test('shell preserves preferences, exposes four languages and follows appearance changes', async () => {
  const dom = new JSDOM('<html><head><meta name="theme-color"></head><body><main id="main"></main></body></html>', {url:'https://harmonica.observe.tw/?lang=en'});
  const {window} = dom;
  for (const key of ['window','document','location','navigator','localStorage']) Object.defineProperty(globalThis,key,{configurable:true,value:key==='window'?window:window[key]});
  let dark = false, listener;
  window.matchMedia = () => ({get matches(){return dark;},addEventListener(type, callback){listener=callback;}});
  localStorage.setItem('atlas-following','["source-1"]');
  localStorage.setItem('atlas-language','ja');
  localStorage.setItem('atlas-theme','dark');
  const {navigation,footer,initializeShell,handleShellClick} = await import('../assets/shell.js');
  const {setLocale, t} = await import('../assets/i18n.js');
  initializeShell();
  assert.equal(document.documentElement.dataset.theme,'dark');
  const routes = {'/':'discover','/post/':'posts','/events/':'events','/source/':'sources','/scores/':'scores','/contribute/':'contribute','/privacy/':'privacy'};
  document.body.innerHTML=navigation('/source/',routes)+'<main id="main"></main>';
  assert.deepEqual([...document.querySelectorAll('#language-select option')].map(n=>n.value),['en','zh-Hant','ja','ko']);
  assert.equal(document.querySelector('.site-nav [aria-current="page"]').getAttribute('href'),'/source/');
  assert.equal(document.querySelector('a[href="/calendar/"]'),null);
  assert.deepEqual([...document.querySelectorAll('.site-nav > a')].map(a=>a.getAttribute('href')),['/','/post/','/events/','/source/','/scores/']);
  assert.equal(document.querySelector('.brand').getAttribute('href'),'/');
  assert.equal(document.querySelector('.mobile-header-action'),null);
  assert.equal(document.querySelector('.legacy-site-header') !== null,true);
  assert.equal(document.querySelector('.nav-more a[href="/contribute/"]') !== null,true);
  assert.equal(document.querySelector('.nav-more a[href="/status/"]') !== null,true);
  assert.ok(document.querySelector('.nav-more summary svg'));
  assert.ok(document.querySelector('.nav-more summary').getAttribute('aria-label').includes(t('language')));
  const click = (selector) => handleShellClick({target:document.querySelector(selector)});
  assert.equal(document.querySelector('[data-shell-panel="appearance"]'),null);
  assert.equal(document.querySelectorAll('.nav-theme-field [data-theme-choice]').length,3);
  click('[data-theme-choice="light"]');
  assert.equal(localStorage.getItem('observatory-appearance'),'light');
  assert.equal(document.documentElement.dataset.theme,'light');
  click('[data-theme-choice="system"]');
  dark=true;listener();
  assert.equal(document.documentElement.dataset.theme,'dark');
  dark=false;listener();
  assert.equal(document.documentElement.dataset.theme,'light');
  assert.equal(localStorage.getItem('atlas-following'),'["source-1"]');
  assert.equal(localStorage.getItem('atlas-language'),'ja');
  for (const locale of ['en','zh-Hant','ja','ko']) {
    setLocale(locale);
    document.body.innerHTML=navigation('/',routes);
    const brand = {en:'Harmonica Observatory','zh-Hant':'口琴觀測站',ja:'ハーモニカ観測所',ko:'하모니카 관측소'}[locale];
    assert.equal(document.querySelector('.brand-name').textContent,brand);
    assert.equal(document.querySelector('.brand-english')?.textContent,locale === 'en' ? undefined : 'HARMONICA OBSERVATORY');
    assert.equal(document.querySelector('.brand').getAttribute('aria-label'),locale === 'en' ? brand : brand + ' · Harmonica Observatory');
    assert.equal(document.querySelector('.brand small'),null);
    assert.ok(footer().includes('© ' + new Date().getFullYear() + ' ' + brand));
    if (locale !== 'zh-Hant') assert.ok(!footer().includes('口琴觀測站'));
    assert.doesNotMatch(document.body.textContent,/Atlas|undefined/);
    assert.equal(document.querySelector('#language-select').value,locale);
  }
  const more = document.querySelector('.nav-more');
  more.open = true;
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(more.querySelector('summary').getAttribute('aria-expanded'),'true');
  document.querySelector('#language-select').focus();
  document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  assert.equal(more.open,false);
  assert.equal(document.activeElement,more.querySelector('summary'));
  more.open = true;
  document.querySelector('.brand').focus();
  assert.equal(more.open,false,'tabbing out closes the disclosure');
  more.open = true;
  document.querySelector('.brand').dispatchEvent(new window.MouseEvent('click',{bubbles:true}));
  assert.equal(more.open,false,'clicking outside closes the disclosure');
  dom.window.close();
});

test('search navigation waits for the river before focusing its visible mobile input', async () => {
  const dom = new JSDOM('<html><body><div id="app"><main id="main"></main></div></body></html>', {url:'https://harmonica.observe.tw/post/?lang=en&focus=search'});
  const {window} = dom;
  for (const key of ['window','document','location','navigator','localStorage']) Object.defineProperty(globalThis,key,{configurable:true,value:key==='window'?window:window[key]});
  window.matchMedia = (query) => ({matches:query.includes('max-width'),addEventListener(){}});
  const {initializeShell} = await import('../assets/shell.js?focus-test');
  initializeShell();
  document.querySelector('#main').innerHTML='<section class="river-mobile"><details class="col-picker"><summary>Filters</summary><input data-river-field="q"></details></section>';
  await new Promise(resolve=>setTimeout(resolve,0));
  assert.equal(document.activeElement.dataset.riverField,'q');
  assert.equal(document.querySelector('.col-picker').open,true);
  assert.equal(new URL(location.href).searchParams.get('focus'),null);
  assert.equal(new URL(location.href).searchParams.get('lang'),'en');
  dom.window.close();
});

test('Google login is visible outside More on every page and switches to account management', async()=>{
  const dom=new JSDOM('<body></body>',{url:'https://harmonica.observe.tw/?lang=zh-Hant'});
  const {navigation}=await import('../assets/shell.js');
  const {setLocale}=await import('../assets/i18n.js');
  for (const locale of ['en','zh-Hant','ja','ko']) {
    setLocale(locale);
    for (const path of ['/','/post/','/contribute/']) {
      dom.window.document.body.innerHTML=navigation(path,{}, {googleLoginEnabled:true,account:null});
      const button=dom.window.document.querySelector('[data-account-nav] [data-google-auth="login"]');
      assert.ok(button);
      assert.equal(button.closest('.nav-more'),null);
      assert.equal(button.closest('.site-header')!==null,true);
      assert.match(button.textContent,/Google/);
    }
    dom.window.document.body.innerHTML=navigation('/',{}, {googleLoginEnabled:true,account:{name:'Private name',email:'private@example.org'}});
    const link=dom.window.document.querySelector('[data-account-nav] a');
    assert.equal(link.getAttribute('href'),'/contribute/?lang='+locale+'#google-account');
    assert.doesNotMatch(link.outerHTML,/Private name|private@example/);
  }
  dom.window.close();
});
