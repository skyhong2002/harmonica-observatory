import { isRedesign } from './redesign.js';
import { getLocale, locales } from './i18n.js';
import { esc, link } from './utils.js';

const words = {
  title: ['Public harmonica events · Google Calendar', '公開口琴活動 · Google Calendar', '公開ハーモニカイベント · Google Calendar', '공개 하모니카 행사 · Google Calendar'],
  filter: ['Calendars', '活動日曆', 'カレンダー', '행사 달력'],
  taiwan: ['Taiwan', '臺灣實體', '台湾の会場', '대만 현장 행사'],
  overseas: ['Outside Taiwan', '海外實體', '台湾以外の会場', '대만 외 현장 행사'],
  online: ['Online', '線上活動', 'オンライン', '온라인 행사'],
  timezone: ['Times shown in', '顯示時區', '表示タイムゾーン', '표시 시간대'],
  subscribe: ['Calendar subscriptions', '訂閱行事曆', 'カレンダーを購読', '달력 구독'],
  fallback: ['Calendar not loading? Browse the event list', '日曆無法載入？瀏覽活動清單', 'カレンダーが表示されない場合はイベント一覧へ', '달력이 표시되지 않으면 행사 목록 보기'],
  empty: ['Select a calendar to display events.', '請選取要顯示的活動日曆。', '表示するカレンダーを選択してください。', '표시할 행사 달력을 선택하세요.'],
  unavailable: ['The Google Calendar embed is unavailable. Event lists and ICS subscriptions remain available.', '目前無法提供 Google Calendar 嵌入內容，仍可瀏覽活動清單或訂閱 ICS。', 'Google Calendar の埋め込みを利用できません。イベント一覧と ICS 購読をご利用ください。', 'Google Calendar를 삽입할 수 없습니다. 행사 목록과 ICS 구독은 계속 이용할 수 있습니다.'],
};
const label = key => words[key][Math.max(0, locales.indexOf(getLocale()))];
const colon = () => ['zh-Hant', 'ja'].includes(getLocale()) ? '：' : ': ';
const calendarColors = {taiwan:'#0B8043',overseas:'#3F51B5',online:'#D81B60'};
const feedPaths = {taiwan:'/feeds/public-calendar.ics',overseas:'/feeds/overseas-calendar.ics',online:'/feeds/online-calendar.ics'};
const preferenceKey = 'observatory-calendar-sources';
export function publicCalendars(catalog = {}) {
  const seen = new Set();
  return (Array.isArray(catalog.calendars) ? catalog.calendars : []).filter(calendar => {
    if (!calendar || !Object.hasOwn(calendarColors,calendar.key) || typeof calendar.id !== 'string' || !/^[a-zA-Z0-9._+-]+@group\.calendar\.google\.com$/.test(calendar.id) || seen.has(calendar.id)) return false;
    seen.add(calendar.id);
    return true;
  });
}
export function calendarTimeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; }
  catch { return 'UTC'; }
}
// Google's agenda (list) view at every width: the native "Coming up" list
// already shows the next events, so the embed stays a short list too.
export function googleCalendarUrl(calendars, {locale=getLocale(),timeZone=calendarTimeZone(),mode='AGENDA'} = {}) {
  if (!calendars.length) return '';
  const url = new URL('https://calendar.google.com/calendar/embed');
  for (const calendar of calendars) {
    url.searchParams.append('src',calendar.id);
    url.searchParams.append('color',calendarColors[calendar.key]);
  }
  const params = {ctz:timeZone,hl:locale==='zh-Hant'?'zh_TW':locale,mode,showTitle:'0',showNav:'1',showDate:'1',showPrint:'0',showTabs:'0',showCalendars:'0',showTz:'1'};
  for (const [key,value] of Object.entries(params)) url.searchParams.set(key,value);
  return url.href;
}
function savedKeys(calendars) {
  try {
    const stored = JSON.parse(localStorage.getItem(preferenceKey));
    if (Array.isArray(stored)) return new Set(stored.filter(key=>Object.hasOwn(calendarColors,key)));
  } catch {}
  return new Set(calendars.map(calendar=>calendar.key));
}
const openLink = url => `<a data-google-calendar-open class="text-link" ${url ? `href="${esc(url)}"` : 'hidden'} target="_blank" rel="noopener noreferrer">Google Calendar<span class="external" aria-hidden="true">↗</span></a>`;
const filters = (calendars, selected) => calendars.map(calendar=>`<label><input type="checkbox" data-google-calendar-source data-calendar-source data-calendar-id="${esc(calendar.id)}" data-calendar-key="${esc(calendar.key)}" ${selected.has(calendar.key)?'checked':''}><span class="google-calendar-dot calendar-dot-${calendar.key}" aria-hidden="true"></span>${esc(label(calendar.key))}</label>`).join('');
const frame = (calendars, url) => `<div class="google-calendar-frame"><iframe title="${esc(label('title'))}" ${url ? `src="${esc(url)}"` : 'hidden'} data-google-calendar-embed data-public-calendar-embed loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe><p class="google-calendar-empty" ${url?'hidden':''} role="status">${esc(label(calendars.length?'empty':'unavailable'))}</p></div>`;
// Page-notes rows for the calendar (new interface): the display timezone with
// the event-list fallback, then Google Calendar and the three ICS feeds.
export function googleCalendarNotes(catalog) {
  const calendars = publicCalendars(catalog);
  const selected = savedKeys(calendars);
  const url = googleCalendarUrl(calendars.filter(calendar=>selected.has(calendar.key)));
  return [
    `<span class="google-calendar-context">${esc(label('timezone'))} <strong>${esc(calendarTimeZone())}</strong> · ${link('/events/',esc(label('fallback')),'text-link')}</span>`,
    `${esc(label('subscribe'))}${colon()}<span class="page-notes-links">${openLink(url)}${Object.entries(feedPaths).map(([key,path])=>link(path,esc(label(key))+' ICS','text-link')).join('')}</span>`,
  ];
}
export function googleCalendarView(catalog) {
  const calendars = publicCalendars(catalog);
  const selected = savedKeys(calendars);
  const shown = calendars.filter(calendar=>selected.has(calendar.key));
  const url = googleCalendarUrl(shown);
  const calendarLink = openLink(url);
  // New interface: only the calendar choices and the embed here; timezone,
  // Google Calendar and ICS links go to the page notes (googleCalendarNotes).
  if (isRedesign()) return `<div class="google-calendar" data-google-calendar><div class="google-calendar-toolbar"><div class="google-calendar-filters" role="group" aria-label="${esc(label('filter'))}">${filters(calendars, selected)}</div></div>${frame(calendars, url)}</div>`;
  return `<div class="google-calendar" data-google-calendar><div class="google-calendar-toolbar"><div class="google-calendar-filters" role="group" aria-label="${esc(label('filter'))}">${calendars.map(calendar=>`<label><input type="checkbox" data-google-calendar-source data-calendar-source data-calendar-id="${esc(calendar.id)}" data-calendar-key="${esc(calendar.key)}" ${selected.has(calendar.key)?'checked':''}><span class="google-calendar-dot calendar-dot-${calendar.key}" aria-hidden="true"></span>${esc(label(calendar.key))}</label>`).join('')}</div><div class="google-calendar-links">${calendarLink}${Object.entries(feedPaths).map(([key,path])=>link(path,esc(label(key))+' ICS','text-link')).join('')}</div></div><p class="google-calendar-context">${esc(label('timezone'))} <strong>${esc(calendarTimeZone())}</strong> · ${link('/events/',esc(label('fallback')),'text-link')}</p><div class="google-calendar-frame"><iframe title="${esc(label('title'))}" ${url ? `src="${esc(url)}"` : 'hidden'} data-google-calendar-embed data-public-calendar-embed loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe><p class="google-calendar-empty" ${url?'hidden':''} role="status">${esc(label(calendars.length?'empty':'unavailable'))}</p></div></div>`;
}
export function bindGoogleCalendar(root) {
  const host = root.querySelector('[data-google-calendar]');
  if (!host) return () => {};
  const change = event => {
    if (!event.target.matches('[data-google-calendar-source]')) return;
    const selected = [...host.querySelectorAll('[data-google-calendar-source]:checked')].map(input=>({id:input.dataset.calendarId,key:input.dataset.calendarKey}));
    try { localStorage.setItem(preferenceKey,JSON.stringify(selected.map(calendar=>calendar.key))); } catch {}
    const frame = host.querySelector('[data-google-calendar-embed]');
    const url = googleCalendarUrl(selected);
    // The open link sits in the page notes in the new interface.
    const open = host.querySelector('[data-google-calendar-open]') || root.querySelector('[data-google-calendar-open]');
    if (open) {
      open.hidden = !url;
      if (url) open.href = url;
      else open.removeAttribute('href');
    }
    frame.hidden = !url;
    if (url) frame.src = url;
    else frame.removeAttribute('src');
    host.querySelector('.google-calendar-empty').hidden = !!url;
  };
  host.addEventListener('change',change);
  return () => host.removeEventListener('change',change);
}
