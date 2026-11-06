import { isRedesign } from './redesign.js';
import { getLocale } from './i18n.js';
import { link, esc, icon, number, pastEvent } from './utils.js';
import { storiesView, storyObservedMarkup } from './stories.js';
import { timelineView } from './timeline.js';
import { googleCalendarView, googleCalendarNotes } from './google-calendar.js';
import { pageNotes } from './page-notes.js';
import { dateBlock, eventClockLabel } from './events.js';
import { eventText } from './event-localization.js';
import { shortEventDate } from './utils.js';
const labels = {
  en: { upcomingTitle: 'Coming up', fullCalendar: 'Full calendar', tagline: 'Public harmonica news from around the world, in one place', intro: 'Posts, stories, events and sheet music from players, ensembles and clubs, each linked to its original source.', sources: 'sources', countries: 'countries & regions', upcoming: 'upcoming events', scores: 'score records', home: 'Home', stories: 'Stories from the past 24 hours', calendar: 'Harmonica event calendar', feed: 'Latest public posts', full: 'Open the full feed', events: 'Browse event list', subscriptions: 'Calendar subscriptions' },
  'zh-Hant': { upcomingTitle: '接下來的活動', fullCalendar: '完整行事曆', tagline: '全球口琴公開資訊，一站看完', intro: '彙整演奏者、樂團與社團的貼文、限動、活動和樂譜，每則都連回原始來源。', sources: '個來源', countries: '個國家與地區', upcoming: '場即將舉行', scores: '筆樂譜紀錄', home: '首頁', stories: '近 24 小時限動', calendar: '公開口琴活動行事曆', feed: '最新公開貼文', full: '開啟完整動態河道', events: '瀏覽活動清單', subscriptions: '訂閱行事曆' },
  ja: { upcomingTitle: '今後のイベント', fullCalendar: 'カレンダー全体', tagline: '世界のハーモニカ公開情報をひとつの場所で', intro: '演奏家・楽団・クラブの投稿、ストーリー、イベント、楽譜をまとめ、すべて元の情報源にリンクします。', sources: '情報源', countries: '国・地域', upcoming: '件の予定イベント', scores: '件の楽譜記録', home: 'ホーム', stories: '過去24時間のストーリー', calendar: 'ハーモニカイベントカレンダー', feed: '最新の公開投稿', full: '投稿フィードを開く', events: 'イベント一覧', subscriptions: 'カレンダーを購読' },
  ko: { upcomingTitle: '다가오는 행사', fullCalendar: '전체 달력', tagline: '전 세계 하모니카 공개 소식을 한곳에서', intro: '연주자·앙상블·동아리의 게시물, 스토리, 행사, 악보를 모으고 모두 원본 출처로 연결해요.', sources: '개 출처', countries: '개 국가·지역', upcoming: '개 예정 행사', scores: '개 악보 기록', home: '홈', stories: '최근 24시간 스토리', calendar: '하모니카 행사 달력', feed: '최신 공개 게시물', full: '전체 소식 피드 보기', events: '행사 목록 보기', subscriptions: '달력 구독' },
};
function upcomingList(catalog, w) {
  const rows = (catalog.events || []).filter(event => !pastEvent(event)).sort((a, b) => Date.parse(a.start) - Date.parse(b.start)).slice(0, 4);
  if (!rows.length) return '';
  return `<ol class="home-upcoming" aria-label="${esc(w.upcomingTitle)}">${rows.map(event => {
    // Lead with the time so sessions on the same day (morning / afternoon) differ at a glance.
    const clock = eventClockLabel(event);
    const when = clock ? `<span class="sr-only">${esc(shortEventDate(event))}</span><span aria-hidden="true">${esc(clock)}</span>` : esc(shortEventDate(event));
    return `<li>${link(event.url || event.sourceUrl, `${dateBlock(event)}<span class="home-upcoming-copy"><span class="home-upcoming-time">${when}</span><strong>${esc(eventText(event))}</strong><span class="home-upcoming-place">${icon('pin')}${esc(eventText(event, 'location') || '')}</span></span>`, 'home-upcoming-link')}</li>`;
  }).join('')}</ol>`;
}
export function observatoryHome(catalog, state, following, limit = 24) {
  return isRedesign() ? redesignedObservatoryHome(catalog, state, following, limit) : legacyObservatoryHome(catalog, state, following, limit);
}
// Original version, shown while the "new interface" switch is off.
function legacyObservatoryHome(catalog, state, following, limit = 24) {
  const w = labels[getLocale()] || labels.en;
  const params = new URLSearchParams({lang:getLocale()});
  for (const key of ['q','country','platform','type','kind','followed']) if (state[key]) params.set(key,state[key]===true?'1':state[key]);
  const updated = storyObservedMarkup(catalog);
  return `<div class="observatory-home"><h1 class="sr-only">${esc(w.home)}</h1>
    <section class="home-stories home-band" aria-labelledby="home-stories-title"><div class="home-section-inner"><header class="home-section-heading"><h2 id="home-stories-title">${esc(w.stories)}</h2>${updated}</header>${storiesView(catalog)}</div></section>
    <section class="home-calendar home-band" aria-labelledby="home-calendar-title"><div class="home-section-inner"><header class="home-section-heading"><h2 id="home-calendar-title">${esc(w.calendar)}</h2><div>${link('/events/',esc(w.events),'text-link')}${link('/feeds/',esc(w.subscriptions),'text-link')}</div></header>${googleCalendarView(catalog)}</div></section>
    <section class="home-posts home-band" aria-labelledby="home-posts-title"><div class="home-section-inner"><header class="home-section-heading"><h2 id="home-posts-title">${esc(w.feed)}</h2>${link('/post/?'+params,esc(w.full)+icon('arrow'),'text-link')}</header>${timelineView(catalog,state,following,limit)}</div></section>
  </div>`;
}
// "New interface" version. The intro has no quick entries (the top
// navigation covers them); snapshot time, timezone and calendar
// subscriptions sit in the page notes at the end.
function redesignedObservatoryHome(catalog, state, following, limit = 24) {
  const w = labels[getLocale()] || labels.en;
  const params = new URLSearchParams({lang:getLocale()});
  for (const key of ['q','country','platform','type','kind','followed']) if (state[key]) params.set(key,state[key]===true?'1':state[key]);
  const lang = '?lang=' + encodeURIComponent(getLocale());
  const countries = new Set((catalog.sources || []).map(source => source.countryCode).filter(code => code && !['WORLD', 'ONLINE', 'UNKNOWN'].includes(code))).size;
  const upcoming = (catalog.events || []).filter(event => !pastEvent(event)).length;
  const stats = [[catalog.sources?.length || 0, w.sources], [countries, w.countries], [upcoming, w.upcoming], [catalog.scores?.length || 0, w.scores]];
  const coming = upcomingList(catalog, w);
  // The observed-time span stays even when empty so bindStories can fill it.
  const notes = pageNotes([storyObservedMarkup(catalog), ...googleCalendarNotes(catalog)], 'home-notes');
  return `<div class="observatory-home">
    <section class="home-intro home-band" aria-labelledby="home-intro-title"><div class="home-section-inner home-intro-grid">
      <div class="home-intro-copy"><h1 id="home-intro-title">${esc(w.tagline)}</h1><p>${esc(w.intro)}</p>
        ${stats.some(([value]) => value) ? `<dl class="home-stats">${stats.map(([value, label]) => `<div><dt>${esc(label)}</dt><dd>${number(value)}</dd></div>`).join('')}</dl>` : ''}</div>
    </div></section>
    <section class="home-stories home-band" aria-labelledby="home-stories-title"><div class="home-section-inner home-now-grid">
      <div class="home-now-stories"><header class="home-section-heading"><h2 id="home-stories-title">${esc(w.stories)}</h2></header>${storiesView(catalog)}</div>
      ${coming ? `<aside class="home-now-events" aria-labelledby="home-upcoming-title"><header class="home-section-heading"><h2 id="home-upcoming-title">${esc(w.upcomingTitle)}</h2>${link('/events/' + lang, esc(w.events) + icon('arrow'), 'text-link')}</header>${coming}</aside>` : ''}
    </div></section>
    <section class="home-calendar home-band" aria-labelledby="home-calendar-title"><div class="home-section-inner"><header class="home-section-heading"><h2 id="home-calendar-title">${esc(w.calendar)}</h2></header>${googleCalendarView(catalog)}</div></section>
    <section class="home-posts home-band" aria-labelledby="home-posts-title"><div class="home-section-inner"><header class="home-section-heading"><h2 id="home-posts-title">${esc(w.feed)}</h2>${link('/post/?'+params,esc(w.full)+icon('arrow'),'text-link')}</header>${timelineView(catalog,state,following,limit)}</div></section>
    <div class="home-notes"><div class="home-section-inner">${notes}</div></div>
  </div>`;
}
