import { getLocale, locales } from './i18n.js';
import { esc, safeUrl, icon } from './utils.js';

const labels = {
  report: ['Report', '回報資料', '情報を報告', '정보 신고'],
  context: ['Reporting: {name}\n', '回報資料：{name}\n', '報告する情報：{name}\n', '신고할 정보: {name}\n'],
};
const translated = key => labels[key][Math.max(0, locales.indexOf(getLocale()))];
const cleanName = value => typeof value === 'string' ? value.replace(/[\u0000-\u001f\u007f]/g, ' ').trim().slice(0, 500) : '';
const countryCode = value => typeof value === 'string' && /^[a-z]{2}$/i.test(value.trim()) ? value.trim().toUpperCase() : '';
function publicUrl(value) {
  const safe = safeUrl(value);
  if (!safe || safe.length > 2000) return '';
  try {
    // Relative source-detail links are valid public reports, but URL form fields
    // and the submission API need an absolute HTTP(S) address.
    const result = safeUrl(new URL(safe, globalThis.location?.origin || 'https://harmonica.observe.tw').href);
    return result.length <= 2000 ? result : '';
  } catch { return ''; }
}
export function reportLink(row = {}, urlOverride, {iconOnly = false} = {}) {
  const url = publicUrl(urlOverride ?? (row.url || row.sourceUrl));
  if (!url) return '';
  const params = new URLSearchParams({lang:getLocale(),reportUrl:url});
  const name = cleanName(row.name || row.title || row.sourceName);
  const country = countryCode(row.countryCode);
  if (name) params.set('reportName', name);
  if (country) params.set('reportCountry', country);
  const label = translated('report');
  return `<a class="context-report-link text-link${iconOnly ? ' src-link-icon' : ''}" href="${esc('/submit/?' + params)}" title="${esc(label)}" aria-label="${esc(name ? label + ': ' + name : label)}">${iconOnly ? icon('flag') + `<span class="sr-only">${esc(label)}</span>` : esc(label)}</a>`;
}
export function submissionContext(search = globalThis.location?.search || '') {
  const params = search instanceof URLSearchParams ? search : new URLSearchParams(search);
  return {
    url: publicUrl(params.get('reportUrl') || params.get('url') || params.get('source')),
    name: cleanName(params.get('reportName') || params.get('name')),
    countryCode: countryCode(params.get('reportCountry') || params.get('countryCode')),
  };
}
export function contextNote(name) {
  const value = cleanName(name);
  return value ? translated('context').replace('{name}', value) : '';
}
