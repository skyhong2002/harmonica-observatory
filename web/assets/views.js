import { eventText, eventOriginalMarkup } from './event-localization.js';
import { sourceDisplayName, sourceNamesMarkup, sourceTypesMarkup, sourceAlternativesMarkup, sourceSummaryMarkup, sourceTags } from "./source-names.js";
import { reportLink } from "./reporting.js";
import { t, getLocale, countryName } from "./i18n.js";
import {
  esc,
  postDisplayText,
  link,
  icon,
  date,
  shortDate,
  shortEventDate,
  timestamp,
  number,
  money,
  badgeCountry,
  image,
  sourceHref,
  avatar,
  empty,
  pastEvent,
  platformName,
  sourceType,
  textMatch,
} from "./utils.js";
const viewLabels = {
  en: { share: "Share", collapse: "Show less", name: "Name", updated: "Updated", links: "Links", endUnknown: "End time not announced", snapshot: "Website snapshot", observed: "Observed", website: "Website", sort: "Sort" },
  "zh-Hant": { share: "分享", collapse: "收合", name: "名稱", updated: "更新", links: "來源連結", endUnknown: "結束時間未公告", snapshot: "網站頁面快照", observed: "觀測時間", website: "網站", sort: "排序" },
  ja: { share: "共有", collapse: "閉じる", name: "名前", updated: "更新", links: "リンク", endUnknown: "終了時刻は未発表", snapshot: "ウェブページの保存記録", observed: "確認日時", website: "ウェブサイト", sort: "並べ替え" },
  ko: { share: "공유", collapse: "접기", name: "이름", updated: "업데이트", links: "링크", endUnknown: "종료 시각 미발표", snapshot: "웹페이지 스냅샷", observed: "확인 시각", website: "웹사이트", sort: "정렬" },
};
const vl = (key) => (viewLabels[getLocale()] || viewLabels.en)[key];
const sourceLinkLabel = (label) => /^(網站|website|web site)$/i.test(String(label || "").trim()) ? vl("website") : label || t("original");
function sourceIconLink(item) {
  let host = '';
  try { host = new URL(item.url).hostname.toLowerCase(); } catch { /* Generic website icon. */ }
  const domains = {facebook:['facebook.com','fb.com','fb.me'], instagram:['instagram.com'], youtube:['youtube.com','youtu.be'], threads:['threads.net','threads.com']};
  const platform = Object.keys(domains).find(key => domains[key].some(domain => host === domain || host.endsWith('.' + domain)));
  const label = sourceLinkLabel(item.label || (platform ? platformName(platform) : 'Website'));
  return link(item.url, icon(platform || 'globe') + `<span class="sr-only">${esc(label)}</span>`, 'src-link src-link-icon', `title="${esc(label)}" aria-label="${esc(label)}"`);
}
const sourcePostCount = (s, catalog) => catalog?.posts?.filter(p => p.sourceId === s.id).length;
export function directoryHeader(sort = "name", descending = false) {
  const heading = (key, label) => `<button type="button" class="src-sort ${sort === key ? "active" : ""}" data-source-sort="${key}" aria-label="${esc(vl("sort") + ": " + label)}">${esc(label)}<span aria-hidden="true">${sort === key ? descending ? "↓" : "↑" : "↕"}</span></button>`;
  return `<div class="src-head"><span>${heading("name", vl("name"))}</span><span>${heading("country", t("country"))}</span><span>${heading("type", t("type"))}</span><span class="src-th-links">${vl("links")}</span><span>${heading("posts", t("posts"))}</span><span>${heading("updated", vl("updated"))}</span><span class="src-th-follow">${t("follow")}</span></div>`;
}
export function sortSources(rows, sort = "name", descending = false, catalog = {}) {
  const collator = new Intl.Collator(getLocale(), { numeric: true, sensitivity: "base" });
  const counts = new Map();
  for (const post of catalog.posts || []) counts.set(post.sourceId, (counts.get(post.sourceId) || 0) + 1);
  const value = s => sort === "posts" ? counts.get(s.id) || 0 : sort === "updated" ? Date.parse(s.updatedAt) || 0 : sort === "country" ? countryName(s.countryCode, s.country) : sort === "type" ? sourceType(s.type) : sourceDisplayName(s);
  return [...rows].sort((a, b) => {
    const av = value(a), bv = value(b);
    return (typeof av === "number" ? av - bv : collator.compare(av || "", bv || "")) * (descending ? -1 : 1) || collator.compare(a.name || "", b.name || "");
  });
}
export function sourceCard(s, following = new Set(), catalog) {
  const followed = following.has(s.id), count = sourcePostCount(s, catalog);
  return `<article class="source-card src-row"><div class="src-c-name"><h3>${link(sourceHref(s), avatar(s) + `<span class="src-name">${sourceNamesMarkup(s)}</span><span class="src-country-mobile" title="${esc(countryName(s.countryCode, s.country))}">${esc(countryName(s.countryCode, s.country))}</span>`, "source-avatar-link", `title="${esc(s.name)}"`)}</h3></div><span class="src-country">${esc(countryName(s.countryCode, s.country))}</span><div class="src-c-chips">${sourceTypesMarkup(s)}</div><div class="src-links">${(s.links || []).map(sourceIconLink).join("")}${reportLink(s, sourceHref(s), {iconOnly:true})}</div><span class="src-count" title="${esc(t("posts"))}">${count === undefined ? "—" : number(count)}</span><span class="src-upd">${s.updatedAt ? timestamp(s.updatedAt, { dateOnly: true }) : "—"}</span><button class="follow-button src-c-follow ${followed ? "is-following" : ""}" data-follow="${esc(s.id)}" aria-pressed="${followed}" aria-label="${esc(t(followed ? "unfollow" : "follow") + " " + s.name)}">${icon(followed ? "check" : "heart")}<span>${t(followed ? "following" : "follow")}</span></button></article>`;
}
export function togglePostExpansion(button) {
  const expanded = button.getAttribute("aria-expanded") !== "true";
  button.setAttribute("aria-expanded", String(expanded));
  button.closest(".feed-content")?.querySelector(".feed-text")?.classList.toggle("is-expanded", expanded);
  button.textContent = expanded ? vl("collapse") : t("readMore");
}
export function postCard(p, sources, following = new Set(), events = []) {
  const s = sources.find(s => s.id === p.sourceId);
  const label = s ? sourceDisplayName(s) : p.sourceName || t("source");
  const text = postDisplayText(p, p.text);
  const snapshot = p.contentKind === "website_snapshot";
  const timeLabel = snapshot ? `${esc(vl("observed"))}: ${timestamp(p.observedAt)}` : timestamp(p.publishedAt);
  const expandable = text.length > 180 || text.split("\n").length > 6;
  const followed = s && following.has(s.id);
  const linkedEvents = events.filter(e => (p.eventIds || []).includes(e.id) || (p.url && (e.url === p.url || e.sourceUrl === p.url)));
  const country = countryName(p.countryCode || s?.countryCode, p.country || s?.country);
  return `<article class="post-card feed-post"><div class="feed-avatar-wrap">${link(s ? sourceHref(s) : p.sourceUrl, avatar({ ...s, ...p, avatar: p.avatar || s?.avatar, name: label }), "feed-avatar-link")}</div><div class="feed-content"><div class="feed-head"><strong class="feed-name">${link(s ? sourceHref(s) : p.sourceUrl, esc(label), "", `title="${esc(label)}"`)}</strong><span class="feed-time">${timeLabel}</span></div><div class="feed-meta"><span class="feed-topic">${esc(country)}</span><span aria-hidden="true">·</span>${link(p.url, esc(platformName(p.platform)), "feed-plat")}${p.isStory ? `<span class="tag story-tag">${t("story")}</span>` : ""}</div>${snapshot ? `<p class="notice">${esc(vl("snapshot"))}</p>` : ""}${p.title && p.title !== p.text && !(p.text || "").startsWith(p.title) ? `<h3 class="feed-title">${esc(postDisplayText(p, p.title))}</h3>` : ""}<p class="post-text feed-text ${expandable ? "" : "is-expanded"}">${esc(text)}</p>${expandable ? `<button type="button" class="feed-expand" data-expand-post aria-expanded="false">${t("readMore")}</button>` : ""}${image(p.image, "post-image feed-img", "")}${p.isStory && (p.sourceAvailable === false || p.storyState === "expired" || p.storyState === "unknown" || (p.expiresAt && Date.parse(p.expiresAt) < Date.now())) ? `<p class="muted story-expired">${t("storyExpired")}</p>` : ""}${linkedEvents.length ? `<div class="feed-evs">${linkedEvents.map(e => link(e.url || e.sourceUrl, `<span class="feed-ev-date">${esc(shortDate(e.start, { timeZone: e.timezone || "UTC" }))}</span><span class="feed-ev-title">${esc(eventText(e))}</span>`, "feed-ev")).join("")}</div>` : ""}<div class="feed-actions">${s ? `<button type="button" class="feed-action ${followed ? "is-following" : ""}" data-follow="${esc(s.id)}" aria-pressed="${!!followed}" aria-label="${esc(t(followed ? "unfollow" : "follow") + " " + label)}">${icon(followed ? "check" : "heart")}<span>${t(followed ? "following" : "follow")}</span></button>` : ""}<button type="button" class="feed-action" data-share="${esc(p.url || "")}" data-share-title="${esc(label)}">${icon("arrow")}<span>${vl("share")}</span></button>${link(p.url, t("original"), "feed-action feed-original")}${reportLink({ ...p, name: p.title || label, countryCode: p.countryCode || s?.countryCode })}</div></div></article>`;
}
export function eventDateLabel(e, options = {}) {
  return shortEventDate(e, options);
}

export function eventCard(e) {
  const d = e.start ? new Date(e.start) : null;
  let month = "—",
    day = "—";
  if (d && Number.isFinite(+d)) {
    try {
      month = new Intl.DateTimeFormat(getLocale(), {
        month: "short",
        timeZone:
          e.allDay && /^\d{4}-\d{2}-\d{2}$/.test(e.start)
            ? "UTC"
            : e.timezone || "UTC",
      }).format(d);
      day = new Intl.DateTimeFormat(getLocale(), {
        day: "2-digit",
        timeZone:
          e.allDay && /^\d{4}-\d{2}-\d{2}$/.test(e.start)
            ? "UTC"
            : e.timezone || "UTC",
      }).format(d);
    } catch {}
  }
  return `<article class="event-card ${pastEvent(e) ? "is-past" : ""}"><div class="event-date" aria-hidden="true"><span>${esc(month)}</span><strong>${esc(day)}</strong></div><div class="event-content"><div class="eyebrow">${esc(countryName(e.countryCode, e.country))}${pastEvent(e) ? ` · ${t("past")}` : ""}</div><h3>${esc(eventText(e))}</h3>${eventOriginalMarkup(e)}<p class="event-time">${icon("calendar")}${esc(eventDateLabel(e))}${e.allDay ? ` · ${t("allDay")}` : e.endEstimated ? ` · ${esc(vl("endUnknown"))}` : ""}</p><p class="event-location">${icon("pin")}${esc(eventText(e, "location") || t("locationUnknown"))}</p><div class="card-bottom"><span class="small muted">${esc(e.timezone || "UTC")} · ${t("localTime")}</span><span class="profile-links">${link(e.url || e.sourceUrl, t("original"), "text-link")}${reportLink(e)}</span></div>${e.description ? `<details class="event-details"><summary>${t("eventDetails")}</summary>${sourceSummaryMarkup({summary: e.description, summaries: e.descriptions, summaryLanguage: e.descriptionLanguage})}</details>` : ""}</div></article>`;
}
export function scoreRow(s) {
  return `<article class="score-row"><div class="score-icon">${icon("music")}</div><div class="score-main"><div class="eyebrow">${esc(s.year || s.instrument || t("scores"))}</div><h3>${link(s.url || s.sourceUrl, esc(s.title))}</h3><p>${s.composer ? `${t("composer")}: ${esc(s.composer)}` : ""}${s.arranger ? `${s.composer ? " · " : ""}${t("arranger")}: ${esc(s.arranger)}` : ""}</p><p class="small muted">${esc([s.instrument, s.division, s.sourceName].filter(Boolean).join(" · "))}</p>${s.notes ? `<details><summary>${t("details")}</summary><p>${esc(s.notes)}</p></details>` : ""}</div>${link(s.url || s.sourceUrl, icon("arrow"), "round-link", `aria-label="${esc(t("original") + " " + s.title)}"`)}</article>`;
}
export function collectionCard(s) {
  return `<article class="collection-card"><div class="collection-art">${icon("music")}<span aria-hidden="true">♫</span></div><div class="collection-copy"><div class="eyebrow">${esc(countryName(s.countryCode))}</div><h3>${esc(s.name || s.title)}</h3><p>${esc(s.summary || "")}</p><div class="card-bottom"><span class="muted small">${s.count !== undefined ? number(s.count) + " " + t("scoresCount") : ""}</span>${link(s.url, t("original"), "text-link")}</div></div></article>`;
}
export function pageHeading(key, body, extra = "") {
  return `<header class="page-heading"><div><h1>${t(key)}</h1>${body ? `<p>${t(body)}</p>` : ""}</div>${extra}</header>`;
}
export function countryFacets(state, catalog, kind, following = new Set()) {
  const sources = new Map((catalog.sources || []).map(source => [source.id, source]));
  const rows = (catalog[kind] || []).filter(row => {
    if (!textMatch(row, state.q)) return false;
    if (kind === "sources") return (!state.type || row.type === state.type) && (!state.followed || following.has(row.id));
    if (kind === "posts") return (state.platform === "website" || row.contentKind !== "website_snapshot") && (!state.platform || row.platform === state.platform) && (state.kind === "stories" ? row.isStory : !row.isStory) && (!(state.followed || state.kind === "following") || following.has(row.sourceId)) && (!state.type || sources.get(row.sourceId)?.type === state.type);
    if (kind === "events") return state.period === "allEvents" || (state.period === "past" ? pastEvent(row) : !pastEvent(row));
    return true;
  });
  const options = new Map((catalog.countries || []).map(c => [c.code, { ...c, count: 0 }]));
  for (const row of rows) {
    const code = row.countryCode || "UNKNOWN";
    if (!options.has(code)) options.set(code, { code, name: row.country, count: 0 });
    options.get(code).count += 1;
  }
  if (state.country && !options.has(state.country)) options.set(state.country, { code: state.country, count: 0 });
  const collator = new Intl.Collator(getLocale());
  return [...options.values()].sort((a, b) => collator.compare(countryName(a.code, a.name), countryName(b.code, b.name)));
}
export function filterBar(state, catalog, kind, following = new Set()) {
  const countries = countryFacets(state, catalog, kind, following);
  let extra = "";
  if (kind === "posts")
    extra = `<label>${t("platform")}<select data-filter="platform"><option value="">${t("allPlatforms")}</option>${[
      ...new Set(catalog.posts.map((p) => p.platform).filter(Boolean)),
    ]
      .sort()
      .map(
        (p) =>
          `<option value="${esc(p)}" ${state.platform === p ? "selected" : ""}>${esc(platformName(p))}</option>`,
      )
      .join(
        "",
      )}</select></label><label>${t("postKind")}<select data-filter="kind"><option value="">${t("allPosts")}</option><option value="stories" ${state.kind === "stories" ? "selected" : ""}>${t("stories")}</option><option value="following" ${state.kind === "following" ? "selected" : ""}>${t("following")}</option></select></label>`;
  if (kind === "events")
    extra = `<label>${t("eventPeriod")}<select data-filter="period">${["upcoming", "past", "allEvents"].map((v) => `<option value="${v}" ${state.period === v ? "selected" : ""}>${t(v)}</option>`).join("")}</select></label>`;
  if (kind === "sources")
    extra = `<label>${t("type")}<select data-filter="type"><option value="">${t("allTypes")}</option>${[
      ...new Set(catalog.sources.map((s) => s.type).filter(Boolean)),
    ]
      .sort()
      .map(
        (v) =>
          `<option value="${esc(v)}" ${state.type === v ? "selected" : ""}>${esc(sourceType(v))}</option>`,
      )
      .join(
        "",
      )}</select></label><label class="checkbox-filter"><input type="checkbox" data-filter="followed" ${state.followed ? "checked" : ""}> ${t("following")}</label>`;
  if (kind === "scores")
    extra = `<label>${t("year")}<select data-filter="year"><option value="">${t("allYears")}</option>${[
      ...new Set(catalog.scores.map((s) => s.year).filter(Boolean)),
    ]
      .sort()
      .reverse()
      .map(
        (v) =>
          `<option value="${esc(v)}" ${state.year === v ? "selected" : ""}>${esc(v)}</option>`,
      )
      .join("")}</select></label>`;
  return `<section class="filter-bar" aria-label="${t("filter")}"><label class="search-label"><span>${t("search")}</span><div class="search-wrap">${icon("search")}<input type="search" id="catalog-search" placeholder="${t("searchPlaceholder")}" value="${esc(state.q)}" autocomplete="off"></div></label><label>${t("country")}<select data-filter="country"><option value="">${t("allCountries")}</option>${countries.map((c) => `<option value="${esc(c.code)}" ${state.country === c.code ? "selected" : ""}>${esc(countryName(c.code, c.name))} (${number(c.count)})</option>`).join("")}</select></label>${extra}${state.q || state.country || state.platform || state.kind || state.type || state.followed || state.year || (state.period && state.period !== "upcoming") ? `<button class="clear-filter" data-action="reset">${t("reset")}</button>` : ""}</section>`;
}
export function homeView(catalog, state, following, filtered) {
  return `${filterBar(state, catalog, "posts")}<div class="post-grid">${filtered.posts.length ? filtered.posts.slice(0, 24).map(p => postCard(p, catalog.sources, following, catalog.events)).join("") : empty()}</div>`;
}
export function communityBanner() {
  return `<aside class="community-banner"><div><h2>${t("contribute")}</h2><p>${t("communityBody")}</p></div><div class="community-actions">${link("/contribute/", t("contribute") + icon("arrow"), "button button-outline")}${link("/submit/", t("submit"), "text-link")}</div></aside>`;
}
export function sourceDetail(source, catalog, following, limit = 24) {
  if (!source)
    return `${pageHeading("sourceMissing", "directoryBody")}${link("/source/", t("backDirectory"), "button button-primary")}`;
  const posts = catalog.posts.filter((p) => p.sourceId === source.id);
  return `<div class="org-page"><div class="back-link">${link("/source/", "← " + t("backDirectory"), "text-link")}</div><section class="source-profile"><div class="profile-avatar">${avatar(source)}</div><div><p class="eyebrow">${esc(countryName(source.countryCode, source.country))}</p><h1>${esc(sourceDisplayName(source))}</h1>${sourceNamesMarkup(source, {includePrimary:false})}<div class="profile-types">${sourceTypesMarkup(source)}</div>${sourceAlternativesMarkup(source)}${sourceSummaryMarkup(source)}<div class="profile-tags">${sourceTags(source).map((tag) => `<span class="tag">${esc(tag)}</span>`).join("")}</div><div class="profile-links">${(Array.isArray(source.links) ? source.links : []).map((l) => link(l.url, esc(sourceLinkLabel(l.label)), "button button-outline")).join("")}${reportLink(source, sourceHref(source))}</div></div><button class="button button-outline" data-follow="${esc(source.id)}" aria-pressed="${following.has(source.id)}">${icon(following.has(source.id) ? "check" : "plus")}${t(following.has(source.id) ? "following" : "follow")}</button></section><div class="section-heading"><div><h2>${t("sourceUpdates")}</h2><p>${t("results", { count: number(posts.length) })}</p></div></div><div class="post-grid source-updates-grid">${
    posts.length
      ? posts
          .slice(0, limit)
          .map((p) => postCard(p, catalog.sources, following, catalog.events || []))
          .join("")
      : empty()
  }</div>${posts.length > limit ? `<div class="pagination"><p>${t("showing", { shown: number(limit), total: number(posts.length) })}</p><button class="button button-outline" data-action="more">${t("loadMore")}${icon("plus")}</button></div>` : ""}</div>`;
}
export function feedsView(catalog) {
  return `${pageHeading("feeds", "feedBody")}<div class="feed-grid">${catalog.feeds.map((f) => `<article class="feed-card"><span class="feed-icon">${icon(String(f.format).toLowerCase().includes("ics") ? "calendar" : "rss")}</span><span class="tag">${esc(f.format || "RSS")}</span><h2>${t("feed_" + (f.id || f.title))}</h2><div class="feed-actions">${link(f.url, t("openFeed"), "text-link")}<button class="copy-button" data-copy="${esc(f.url)}">${t("copy")}</button></div></article>`).join("")}</div>`;
}
export function aboutView() {
  return `${pageHeading("aboutTitle", "aboutBody")}<div class="about-layout"><section class="faq-section"><h2>${t("faq")}</h2>${["Lang", "Cost", "Data", "Withdraw", "Coverage"].map((id) => `<details class="faq"><summary>${t("faq" + id + "Q")}${icon("plus")}</summary><p>${t("faq" + id + "A")}</p></details>`).join("")}</section></div>${communityBanner()}`;
}
export function privacyView() {
  return `${pageHeading("privacy", "privacyBody")}<div class="prose">${["Browser", "Server", "External"].map((id) => `<section><h2>${t("privacy" + id + "Title")}</h2><p>${t("privacy" + id)}</p></section>`).join("")}<p>${link("/contribute/", t("myContributions"), "text-link")} · ${link("/submit/", t("submit"), "text-link")}</p></div>`;
}
export function statusView(catalog, community) {
  const status = catalog.status || {};
  return `${pageHeading("status", "statusBody")}<section class="status-hero"><span class="status-orb ${["ok", "healthy", "operational"].includes(status.overall) ? "ok" : ""}"></span><div><h2>${t(["ok", "healthy", "operational"].includes(status.overall) ? "healthy" : status.overall === "unknown" ? "unavailable" : "degraded")}</h2><p>${t("updated", { date: timestamp(status.updatedAt || catalog.generatedAt) })}</p></div></section><div class="status-metrics"><div><span>${t("provider")}</span><strong>${esc(platformName(status.provider) || t("unavailable"))}</strong></div><div><span>${t("snapshot")}</span><strong>${timestamp(catalog.generatedAt, { dateOnly: true })}</strong></div><div><span>${t("activeAccounts")}</span><strong>${community ? number(community.crawlSchedule?.pool?.usableAccountCount ?? community.activeAccounts) : "—"}</strong></div></div><p class="notice">${icon("info")}${t("snapshotNote")}</p><div class="table-scroll"><table><thead><tr><th>${t("service")}</th><th>${t("status")}</th><th>${t("observed")}</th><th>${t("errors")}</th></tr></thead><tbody>${(status.services || []).map((s) => `<tr><td>${esc(platformName(s.name || s.id))}</td><td><span class="status-pill ${["ok", "healthy"].includes(s.status) ? "is-ok" : ""}">${t(["ok", "healthy"].includes(s.status) ? "healthy" : s.status === "disabled" ? "disabled" : s.status === "paused" ? "paused" : s.status === "unknown" ? "unavailable" : "degraded")}</span></td><td>${number(s.count)}</td><td>${number(s.errors)}</td></tr>`).join("")}</tbody></table></div>${communityBanner()}`;
}
