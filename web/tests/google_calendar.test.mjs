import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { setLocale } from '../assets/i18n.js';
import { isRedesign } from '../assets/redesign.js';
import { pageNotes } from '../assets/page-notes.js';
import { publicCalendars, googleCalendarUrl, googleCalendarView, googleCalendarNotes, bindGoogleCalendar } from '../assets/google-calendar.js';
// The new interface keeps only the calendar choices and the embed in place;
// timezone, Google Calendar and ICS links move to the page notes.
const calendarPage=catalog=>isRedesign()?googleCalendarView(catalog)+pageNotes(googleCalendarNotes(catalog)):googleCalendarView(catalog);
const calendars=[{id:'taiwan-public@group.calendar.google.com',key:'taiwan'},{id:'world-public@group.calendar.google.com',key:'overseas'},{id:'online-public@group.calendar.google.com',key:'online'}];
function setup() {
  const {window}=new JSDOM('<main></main>',{url:'https://harmonica.observe.tw/'});
  for (const key of ['window','document','location','localStorage']) Object.defineProperty(globalThis,key,{configurable:true,value:key==='window'?window:window[key]});
  return window;
}
test('Google agenda URL includes only configured public calendars, explicit locale and independent timezone',()=>{
  const window=setup();
  assert.deepEqual(publicCalendars({calendars:[...calendars,calendars[0],{key:'taiwan',id:'javascript:alert(1)'},{key:'unknown',id:'other@group.calendar.google.com'}]}),calendars);
  for (const [locale,hl] of [['en','en'],['zh-Hant','zh_TW'],['ja','ja'],['ko','ko']]) {
    const url=new URL(googleCalendarUrl(calendars,{locale,timeZone:'America/New_York'}));
    assert.equal(url.origin,'https://calendar.google.com');
    assert.equal(url.pathname,'/calendar/embed');
    assert.deepEqual(url.searchParams.getAll('src'),calendars.map(c=>c.id));
    assert.equal(url.searchParams.get('mode'),'AGENDA');
    assert.equal(url.searchParams.get('hl'),hl);
    assert.equal(url.searchParams.get('ctz'),'America/New_York');
  }
  assert.equal(googleCalendarUrl([]),'');
  window.close();
});
test('calendar selections update only the real iframe and persist across UI locale changes',()=>{
  const window=setup(),root=document.querySelector('main');
  setLocale('en');
  root.innerHTML=calendarPage({calendars})+'<section class="river"><input value="untouched"></section>';
  const river=root.querySelector('.river');
  const cleanup=bindGoogleCalendar(root);
  const frame=root.querySelector('[data-public-calendar-embed]');
  assert.equal(root.querySelectorAll('[data-calendar-source]:checked').length,3);
  assert.equal(root.querySelector('.calendar-grid'),null);
  const controls=[...root.querySelectorAll('[data-calendar-source]')];
  controls[0].checked=false;controls[0].dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.equal(new URL(frame.src).searchParams.getAll('src').length,2);
  assert.equal(root.querySelector('.river'),river);
  controls.slice(1).forEach(control=>{control.checked=false;control.dispatchEvent(new window.Event('change',{bubbles:true}));});
  assert.equal(frame.hidden,true);assert.equal(frame.hasAttribute('src'),false);
  assert.equal(root.querySelector('.google-calendar-empty').hidden,false);
  controls[2].checked=true;controls[2].dispatchEvent(new window.Event('change',{bubbles:true}));
  assert.deepEqual(new URL(frame.src).searchParams.getAll('src'),[calendars[2].id]);
  assert.equal(frame.hidden,false);
  cleanup();setLocale('ja');root.innerHTML=calendarPage({calendars});
  assert.equal(root.querySelectorAll('[data-calendar-source]:checked').length,1);
  assert.equal(new URL(root.querySelector('iframe').src).searchParams.get('hl'),'ja');
  assert.equal(root.querySelectorAll('a[href$=".ics"]').length,3);
  assert.equal(root.querySelector('a[href^="https://calendar.google.com/"]').target,'_blank');
  if(isRedesign()){
    assert.equal(root.querySelectorAll('[data-google-calendar] a[href$=".ics"]').length,0);
    assert.equal(root.querySelector('[data-google-calendar] .google-calendar-context'),null);
    assert.equal(root.querySelectorAll('.page-notes a[href$=".ics"]').length,3);
  }
  window.close();
});
test('missing public calendar configuration shows an honest fallback and keeps subscription links',()=>{
  const window=setup();setLocale('ko');document.querySelector('main').innerHTML=calendarPage({});
  assert.equal(document.querySelector('iframe').hasAttribute('src'),false);
  assert.equal(document.querySelector('iframe').hidden,true);
  assert.equal(document.querySelector('.google-calendar-empty').hidden,false);
  assert.equal(document.querySelectorAll('a[href$=".ics"]').length,3);
  assert.ok(!document.body.textContent.includes('undefined'));
  // New interface: the same centred empty card as other empty states, with a way on.
  if(isRedesign()){
    const card=document.querySelector('.google-calendar-empty');
    assert.ok(card.classList.contains('empty-state'));
    assert.ok(card.querySelector('h3')&&card.querySelector('p'));
    assert.ok(card.querySelector('a[href="/events/"]'));
  }
  window.close();
});

test('opening Google Calendar preserves selected sources and offers an explicit local timezone and fallback',()=>{
  const window=setup(),root=document.querySelector('main');setLocale('en');root.innerHTML=calendarPage({calendars});const cleanup=bindGoogleCalendar(root);
  const open=root.querySelector('[data-google-calendar-open]'),frame=root.querySelector('iframe');
  for(const control of root.querySelectorAll('[data-calendar-source]')){control.checked=control.dataset.calendarKey==='online';control.dispatchEvent(new window.Event('change',{bubbles:true}));}
  assert.equal(open.href,frame.src);assert.deepEqual(new URL(open.href).searchParams.getAll('src'),[calendars[2].id]);
  assert.match(root.querySelector('.google-calendar-context').textContent,/Times shown in/);assert.ok(root.querySelector('.google-calendar-context a[href="/events/"]'));
  const online=root.querySelector('[data-calendar-key="online"]');online.checked=false;online.dispatchEvent(new window.Event('change',{bubbles:true}));assert.equal(open.hidden,true);assert.equal(open.hasAttribute('href'),false);
  cleanup();window.close();
});
