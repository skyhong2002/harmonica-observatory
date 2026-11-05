import { getLocale, locales } from './i18n.js';
import { esc } from './utils.js';

// One place at the foot of a page for subscriptions, timezones, snapshot
// times and how numbers are counted, so the content above stays uncluttered.
const titles = ['About this page’s data', '本頁的資料來源與計算方式', 'このページのデータと集計方法', '이 페이지의 데이터와 계산 방법'];

export function pageNotesTitle() {
  return titles[Math.max(0, locales.indexOf(getLocale()))];
}

// items: HTML strings (callers escape their own text). Empty items are skipped.
export function pageNotes(items = [], id = 'page-notes') {
  const rows = items.filter(Boolean);
  if (!rows.length) return '';
  return `<section class="page-notes" aria-labelledby="${esc(id)}-title"><h2 id="${esc(id)}-title">${esc(pageNotesTitle())}</h2><ul>${rows.map((row) => `<li>${row}</li>`).join('')}</ul></section>`;
}
