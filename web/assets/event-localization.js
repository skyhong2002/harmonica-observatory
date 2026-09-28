import { getLocale } from './i18n.js';
import { esc } from './utils.js';

export function eventText(event, field = 'title', locale = getLocale()) {
  const values = event?.[field === 'title' ? 'titles' : 'locations'];
  const translated = values?.[locale];
  return typeof translated === 'string' && translated.trim() ? translated.trim() : String(event?.[field] || '');
}

const labels = {
  en: 'Reference translation · original wording',
  'zh-Hant': '參考翻譯・原始名稱與地點',
  ja: '参考訳・元の名称と会場',
  ko: '참고 번역 · 원래 이름과 장소',
};

export function eventOriginalMarkup(event, locale = getLocale()) {
  const originals = ['title', 'location'].filter(field => event?.[field] && eventText(event, field, locale) !== event[field]);
  if (!originals.length) return '';
  return `<details class="event-original"><summary>${esc(labels[locale] || labels.en)}</summary>${originals.map(field => `<p>${esc(event[field])}</p>`).join('')}</details>`;
}
