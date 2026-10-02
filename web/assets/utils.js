import { t, getLocale, countryName } from "./i18n.js";
export const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
export function safeUrl(value) {
  const s = String(value || "").trim();
  if (!s || /[\u0000-\u001f\\]/.test(s)) return "";
  if (s.startsWith("/") && !s.startsWith("//")) return s;
  try {
    const u = new URL(s);
    return ["http:", "https:"].includes(u.protocol) &&
      !u.username &&
      !u.password
      ? u.href
      : "";
  } catch {
    return "";
  }
}
export function link(url, label, classes = "", extra = "") {
  const safe = safeUrl(url);
  if (!safe) return `<span class="${esc(classes)}">${label}</span>`;
  const external = /^https?:/.test(safe);
  return `<a class="${esc(classes)}" href="${esc(safe)}" ${external ? 'target="_blank" rel="noopener noreferrer"' : ""} ${extra}>${label}${external ? '<span class="external" aria-hidden="true">↗</span>' : ""}</a>`;
}
export const icon = (name) => {
  const paths = {
    facebook: '<path d="M14 21v-8h3l.5-4H14V7c0-1 .4-2 2-2h2V1.5A24 24 0 0 0 15 1c-3 0-5 2-5 5v3H7v4h3v8"/>',
    instagram: '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r=".7" fill="currentColor" stroke="none"/>',
    youtube: '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="m10 9 5 3-5 3Z" fill="currentColor" stroke="none"/>',
    threads: '<path d="M20 7c-1-4-4-5-8-5C6 2 3 6 3 12s3 10 9 10c5 0 9-3 9-7 0-4-4-6-8-6-3 0-5 1-5 3s2 3 4 3c3 0 4-2 4-5s-1-5-4-5c-2 0-3 1-4 2"/>',
    flag: '<path d="M5 22V3m0 0c5-4 9 4 14 0v11c-5 4-9-4-14 0"/>',
    search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    globe:
      '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18M5 6.5h14M5 17.5h14"/>',
    arrow: '<path d="M4 12h16m-6-6 6 6-6 6"/>',
    heart:
      '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/>',
    calendar:
      '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M16 3v4M8 3v4M3 11h18m-12 4h3m3 0h3m-9 3h3"/>',
    music:
      '<path d="M9 18V5l12-2v13M9 8l12-2"/><ellipse cx="6" cy="18" rx="3" ry="3"/><ellipse cx="18" cy="16" rx="3" ry="3"/>',
    rss: '<circle cx="5" cy="19" r="1"/><path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    chevron: '<path d="m8 4 8 8-8 8"/>',
    menu: '<path d="M4 6h16M4 12h16M4 18h16"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    pin: '<path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z"/><circle cx="12" cy="10" r="2.5"/>',
    plus: '<path d="M12 4v16M4 12h16"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7v1"/>',
    layers:
      '<path d="m12 3 10 6-10 6L2 9l10-6ZM2 13l10 6 10-6M2 17l10 6 10-6"/>',
  };
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.globe}</svg>`;
};
// Date-only calendar values are civil dates, never UTC instants to shift.
function civilDate(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return null;
  const parsed = new Date(value + "T00:00:00Z");
  return Number.isFinite(+parsed) && parsed.toISOString().slice(0, 10) === value
    ? value
    : null;
}
function localCivilDate(timestamp, timeZone) {
  const options = {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: timeZone || "UTC",
  };
  let parts;
  try {
    parts = new Intl.DateTimeFormat(
      "en-CA-u-ca-gregory-nu-latn",
      options,
    ).formatToParts(new Date(timestamp));
  } catch {
    parts = new Intl.DateTimeFormat("en-CA-u-ca-gregory-nu-latn", {
      ...options,
      timeZone: "UTC",
    }).formatToParts(new Date(timestamp));
  }
  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
}
export function date(value, options = {}) {
  if (!value) return t("dateUnknown");
  const civil = civilDate(value);
  if (typeof value === "string" && /^\d{4}-\d{2}-\d{2}$/.test(value) && !civil)
    return t("dateUnknown");
  const d = new Date(
    civil
      ? civil + "T00:00:00Z"
      : typeof value === "number" && value < 1e12
        ? value * 1000
        : value,
  );
  if (!Number.isFinite(+d)) return t("dateUnknown");
  const format = {
    year: "numeric",
    month: "short",
    day: "numeric",
    ...options,
    ...(civil ? { timeZone: "UTC" } : {}),
  };
  try {
    return new Intl.DateTimeFormat(getLocale(), format).format(d);
  } catch {
    return new Intl.DateTimeFormat(getLocale(), {
      ...format,
      timeZone: "UTC",
    }).format(d);
  }
}
function parsedDate(value) {
  if (value === null || value === undefined || value === '') return null;
  const civil = civilDate(value);
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value) && !civil) return null;
  const parsed = new Date(civil ? civil + 'T00:00:00Z' : typeof value === 'number' && value < 1e12 ? value * 1000 : value);
  return Number.isFinite(+parsed) ? parsed : null;
}
function displayZone(timeZone) {
  try { return new Intl.DateTimeFormat('en', {timeZone}).resolvedOptions().timeZone; }
  catch { return 'UTC'; }
}
function clockTime(value, timeZone) {
  return new Intl.DateTimeFormat(getLocale(), {hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:displayZone(timeZone)}).format(parsedDate(value));
}
function offsetAt(value, timeZone) {
  return new Intl.DateTimeFormat('en', {timeZone:displayZone(timeZone),timeZoneName:'shortOffset'}).formatToParts(parsedDate(value)).find(part=>part.type==='timeZoneName')?.value || '';
}
export function shortDate(value, {timeZone, now = Date.now(), includeYear} = {}) {
  const parsed = parsedDate(value);
  if (!parsed) return t('dateUnknown');
  const zone = displayZone(timeZone);
  const valueYear = (civilDate(value) || localCivilDate(+parsed,zone)).slice(0,4);
  const sameYear = valueYear === localCivilDate(+parsedDate(now),zone).slice(0,4);
  return date(value, {timeZone:zone,year:(includeYear ?? !sameYear) ? 'numeric' : undefined});
}
export function shortDateTime(value, options = {}) {
  if (!parsedDate(value)) return t('dateUnknown');
  const label = shortDate(value,options);
  return civilDate(value) ? label : `${label} · ${clockTime(value,options.timeZone)}`;
}
export function timestamp(value, {dateOnly = false, ...options} = {}) {
  const parsed = parsedDate(value);
  if (!parsed) return `<span>${esc(t('dateUnknown'))}</span>`;
  const label = (dateOnly ? shortDate : shortDateTime)(value,options);
  const full = date(value, {timeZone:displayZone(options.timeZone),...(civilDate(value) ? {} : {hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZoneName:'short'})});
  return `<time datetime="${esc(civilDate(value) || parsed.toISOString())}" title="${esc(full)}" aria-label="${esc(full)}">${esc(label)}</time>`;
}
export function shortEventDate(event, {now = Date.now()} = {}) {
  const options = {timeZone:event.timezone || 'UTC',now};
  const start = parsedDate(event.start), end = parsedDate(event.end);
  if (!start) return t('dateUnknown');
  if (event.allDay) {
    if (civilDate(event.start) && civilDate(event.end) && end > start) {
      const inclusive = new Date(+end - 86400000).toISOString().slice(0,10);
      if (inclusive > event.start) {
        const includeYear = inclusive.slice(0,4) !== event.start.slice(0,4) ? true : undefined;
        return `${shortDate(event.start,{...options,includeYear})} – ${shortDate(inclusive,{...options,includeYear})}`;
      }
    }
    return shortDate(event.start,options);
  }
  if (!end || event.endEstimated || end <= start) return shortDateTime(event.start,options);
  const startDay = localCivilDate(+start,options.timeZone), endDay = localCivilDate(+end,options.timeZone);
  const startOffset = offsetAt(start,options.timeZone), endOffset = offsetAt(end,options.timeZone);
  const changedOffset = startOffset !== endOffset;
  if (startDay === endDay) return `${shortDate(event.start,options)} · ${clockTime(start,options.timeZone)}${changedOffset ? ' '+startOffset : ''}–${clockTime(end,options.timeZone)}${changedOffset ? ' '+endOffset : ''}`;
  const includeYear = startDay.slice(0,4) !== endDay.slice(0,4) ? true : undefined;
  return `${shortDateTime(event.start,{...options,includeYear})}${changedOffset ? ' '+startOffset : ''} – ${shortDateTime(event.end,{...options,includeYear})}${changedOffset ? ' '+endOffset : ''}`;
}

export const number = (value) =>
  new Intl.NumberFormat(getLocale()).format(Number(value) || 0);
export const money = (value) =>
  value === null || value === undefined
    ? t("unavailable")
    : new Intl.NumberFormat(getLocale(), {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 2,
      }).format(Number(value));
export function badgeCountry(row) {
  return `<span class="country-label">${icon("globe")}${esc(countryName(row.countryCode, row.country))}</span>`;
}
export function image(url, classes = "", alt = "") {
  const src = safeUrl(url);
  return src
    ? `<img class="${esc(classes)}" src="${esc(src)}" alt="${esc(alt)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">`
    : "";
}
export function sourceHref(source) {
  return safeUrl(source.url) || `/source/${encodeURIComponent(source.id)}/`;
}
export const initials = (name) =>
  [...String(name || "♪").trim()].slice(0, 2).join("");
export function avatar(source) {
  return `<span class="avatar"><span aria-hidden="true">${esc(initials(source.name || source.sourceName))}</span>${image(source.avatar, "", "")}</span>`;
}
export function postDisplayText(post, value) {
  const text = String(value || '');
  const generated = post.isStory && post.platform === 'instagram' && /^Instagram story (@[A-Za-z0-9_.]+)$/.exec(text);
  return generated && getLocale() !== 'en' ? `Instagram ${t('story')} ${generated[1]}` : text;
}
export function empty() {
  return `<div class="empty-state">${icon("search")}<h2>${t("noResults")}</h2><p>${t("noResultsBody")}</p><button class="button button-outline" data-action="reset">${t("reset")}</button> ${link("/submit/", t("submit"), "text-link")}</div>`;
}
export const pastEvent = (event) => {
  const end = event.end || event.start;
  if (!end) return false;
  if (event.allDay) {
    const civilEnd = civilDate(end);
    if (civilEnd) {
      const today = localCivilDate(Date.now(), event.timezone);
      // Published calendars use exclusive DTEND; absent end means a single day.
      return event.end ? today >= civilEnd : today > civilEnd;
    }
    if (typeof end === "string" && /^\d{4}-\d{2}-\d{2}$/.test(end))
      return false;
  }
  const timestamp = Date.parse(end);
  return Number.isFinite(timestamp) && timestamp <= Date.now();
};
export function toast(message) {
  const node = document.querySelector("#toast");
  node.textContent = message;
  node.classList.add("visible");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => node.classList.remove("visible"), 4500);
}
export function textMatch(row, query) {
  if (!query) return true;
  const haystack = [
    row.name,
    row.nameEn,
    ...Object.values(row.names || {}),
    ...(row.aliases || []),
    row.title,
    ...Object.values(row.titles || {}),
    ...Object.values(row.locations || {}),
    row.text,
    row.summary,
    ...Object.values(row.summaries || {}),
    ...Object.values(row.descriptions || {}),
    ...Object.values(row.tagsLocalized || {}).flat(),
    row.searchText,
    row.sourceName,
    row.location,
    row.description,
    row.composer,
    row.arranger,
    row.instrument,
    row.region,
    ...(row.tags || []),
  ]
    .join(" ")
    .normalize("NFKC")
    .toLocaleLowerCase();
  return query
    .normalize("NFKC")
    .toLocaleLowerCase()
    .split(/\s+/)
    .filter(Boolean)
    .every((term) => haystack.includes(term));
}
export const platformName = (platform) =>
  ({
    facebook: "Facebook",
    instagram: "Instagram",
    instagram_stories: t("instagramStories"),
    threads: "Threads",
    x: "X",
    twitter: "X",
    youtube: "YouTube",
    rss: "RSS",
    rsshub: "RSSHub",
    website: t("website"),
    apify: "Apify",
    mixed: "Apify · RSS · YouTube",
    manual: t("manualSource"),
  })[String(platform).toLowerCase()] || String(platform || "");
const typeMap = {
  演奏家: "artist",
  演奏者: "artist",
  個人: "artist",
  個人演奏者: "artist",
  口琴演奏家: "artist",
  團體: "ensemble",
  學校社團: "club",
  活動與比賽: "event",
  樂器與器材: "equipment",
  場館與平台: "venue",
  樂團: "ensemble",
  口琴樂團: "ensemble",
  重奏團: "ensemble",
  社團: "club",
  學生社團: "club",
  協會: "organization",
  組織: "organization",
  機構: "organization",
  品牌: "brand",
  製造商: "brand",
  廠商: "brand",
  教師: "teacher",
  音樂節: "festival",
};
export function sourceType(type) {
  const key = typeMap[type] || type;
  const known = [
    "artist",
    "ensemble",
    "club",
    "organization",
    "brand",
    "teacher",
    "festival",
    "venue",
    "equipment",
    "event",
  ];
  return known.includes(key)
    ? t("sourceType_" + key)
    : type || t("sourceType_other");
}
