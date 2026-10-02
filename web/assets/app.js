import { bindDirectoryColumns } from "./directory-columns.js";
import { sourceDisplayName, sourceSummaryText } from "./source-names.js";
import { observatoryHome } from "./home.js";
import { bindStories } from "./stories.js";
import { bindGoogleCalendar } from "./google-calendar.js";
import { eventsView, bindEvents } from "./events.js";
import { scoresView, scoreSourcesView } from "./scores.js";
import { navigation, accountNavigation, footer, initializeShell, handleShellClick } from "./shell.js";
import { timelineView, bindTimeline } from "./timeline.js";
import { t, getLocale, setLocale } from "./i18n.js";
import {
  esc,
  link,
  icon,
  number,
  empty,
  pastEvent,
  textMatch,
  toast,
  safeUrl,
} from "./utils.js";
import {
  directoryHeader,
  sortSources,
  togglePostExpansion,
  filterBar,
  pageHeading,
  sourceCard,
  postCard,
  eventCard,
  scoreRow,
  collectionCard,
  sourceDetail,
  feedsView,
  aboutView,
  privacyView,
  statusView,
} from "./views.js";
import {
  refreshCommunity,
  syncCommunityUi,
  getCommunity,
  getSession,
  capacityPanel,
  contributeView,
  submitView,
  handleForm,
  withdraw,
  handleGoogleAuth,
} from "./community.js";
const app = document.querySelector("#app");
let catalog = null,
  loadFailed = false,
  limit = 24,
  renderVersion = 0,
  searchTimer,
  timelineCleanup,
  calendarCleanup,
  storiesCleanup,
  eventsCleanup,
  directoryCleanup;
let previousRenderedPath = null;
let following = new Set();
try {
  following = new Set(
    JSON.parse(localStorage.getItem("atlas-following") || "[]").filter(
      (v) => typeof v === "string",
    ),
  );
} catch {}
const routes = {
  "/": "discover",
  "/events/": "events",
  "/post/": "posts",
  "/source/": "sources",
  "/scores/": "scores",
  "/scores/sources/": "scoreSources",
  "/feeds/": "feeds",
  "/status/": "status",
  "/contribute/": "contribute",
  "/submit/": "submit",
  "/about/": "about",
  "/privacy/": "privacy",
};
function path() {
  return location.pathname.endsWith("/")
    ? location.pathname
    : location.pathname + "/";
}
function readState() {
  const p = new URLSearchParams(location.search);
  return {
    reportUrl: p.get("reportUrl") || p.get("url") || p.get("source") || "",
    reportName: p.get("reportName") || p.get("name") || "",
    reportCountry: p.get("reportCountry") || p.get("countryCode") || "",
    q: p.get("q") || "",
    country: p.get("country") || "",
    platform: p.get("platform") || "",
    type: p.get("type") || "",
    kind: p.get("kind") || "",
    period: ["upcoming", "past", "allEvents"].includes(p.get("period"))
      ? p.get("period")
      : "upcoming",
    followed: p.get("followed") === "1",
    year: p.get("year") || "",
    instrument: p.get("instrument") || "",
    division: p.get("division") || "",
    publisher: p.get("publisher") || "",
    scoreSort: p.get("scoreSort") || "year_desc",
    scoreKind: ["books", "announcements", "contacts"].includes(p.get("scoreKind")) ? p.get("scoreKind") : "",
    sort: p.get("sort") || "name",
    descending: p.get("descending") === "1",
  };
}
let state = readState();
function updateUrl() {
  const params = new URLSearchParams();
  params.set("lang", getLocale());
  for (const [k, v] of Object.entries(state))
    if (v && !(k === "period" && v === "upcoming") && !(k === "sort" && v === "name") && !(k === "scoreSort" && v === "year_desc"))
      params.set(k, v === true ? "1" : v);
  history.replaceState({}, "", location.pathname + "?" + params);
}
function filtered() {
  const base = (rows) =>
    rows.filter(
      (row) =>
        (!state.country || row.countryCode === state.country) &&
        textMatch(row, state.q),
    );
  return {
    sources: base(catalog.sources).filter(
      (s) =>
        (!state.type || s.type === state.type) &&
        (!state.followed || following.has(s.id)),
    ),
    posts: base(catalog.posts).filter(
      (p) =>
        (!state.platform || p.platform === state.platform) &&
        (!state.kind ||
          (state.kind === "stories" && p.isStory) ||
          (state.kind === "following" && following.has(p.sourceId))),
    ),
    events: base(catalog.events),
    scores: base(catalog.scores).filter(
      (s) => !state.year || s.year === state.year,
    ),
    scoreSources: base(catalog.scoreSources),
  };
}
function listView(kind, data) {
  const bodyKey = {
    sources: "directoryBody",
    posts: "latestBody",
    events: "eventsBody",
    scores: "scoresBody",
    scoreSources: "scoreSourcesBody",
  }[kind];
  const visible =
    kind === "events"
      ? data.filter(
          (e) =>
            state.period === "allEvents" ||
            (state.period === "past" && pastEvent(e)) ||
            (state.period === "upcoming" && !pastEvent(e)),
        )
      : data;
  const sorted =
    kind === "sources" ? sortSources(visible, state.sort, state.descending, catalog) :
    kind === "events" && state.period === "past"
      ? [...visible].reverse()
      : visible;
  const card = {
    sources: (s) => sourceCard(s, following, catalog),
    posts: (p) => postCard(p, catalog.sources, following, catalog.events),
    events: eventCard,
    scores: scoreRow,
    scoreSources: collectionCard,
  }[kind];
  const cls = {
    sources: "source-grid",
    posts: "post-grid",
    events: "event-list",
    scores: "score-list",
    scoreSources: "collection-grid",
  }[kind];
  const extra =
    kind === "scores"
      ? link(
          "/scores/sources/",
          t("musicNote") + icon("arrow"),
          "button button-outline",
        )
      : kind === "sources"
        ? link("/submit/", t("submit") + icon("plus"), "button button-outline")
        : "";
  return `${pageHeading(kind, bodyKey, extra)}${filterBar(state, catalog, kind, following)}<div class="results-bar"><p role="status">${t("results", { count: number(sorted.length) })}</p>${kind === "sources" && state.followed ? `<span>${t("followHint")}</span>` : ""}</div>${kind === "sources" ? directoryHeader(state.sort, state.descending) : ""}<div class="${cls}">${sorted.length ? sorted.slice(0, limit).map(card).join("") : empty()}</div>${sorted.length > limit ? `<div class="pagination"><p>${t("showing", { shown: number(limit), total: number(sorted.length) })}</p><button class="button button-outline" data-action="more">${t("loadMore")}${icon("plus")}</button></div>` : ""}`;
}
function sourceForPath() {
  let slug;
  try { slug = decodeURIComponent(path().split("/").filter(Boolean).at(-1)); } catch { return null; }
  if (!path().startsWith("/source/") && !path().startsWith("/post/source/")) return null;
  return catalog?.sources.find(source => source.id === slug || source.publicId === slug || source.url === path() || source.url?.split("/").filter(Boolean).at(-1) === slug);
}
function body() {
  if (!catalog)
    return `<div class="initial-loading" ${loadFailed ? "" : 'aria-busy="true"'}>${icon(loadFailed ? "info" : "globe")}<h1>${t(loadFailed ? "loadError" : "loading")}</h1>${loadFailed ? `<p>${t("loadErrorBody")}</p><button class="button button-primary" data-action="retry">${t("retry")}</button>` : '<div class="loading-dots"><i></i><i></i><i></i></div>'}</div>`;
  const key = routes[path()];
  const data = filtered();
  if (key === "discover") return observatoryHome(catalog, state, following, limit);
  if (key === "posts") return pageHeading("posts", null) + timelineView(catalog, state, following, limit);
  if (key === "scores") return scoresView(catalog, state, limit);
  if (key === "scoreSources") return scoreSourcesView(catalog, state, limit);
  if (key === "events") return eventsView(catalog, state, following, limit);
  if (key === "sources")
    return listView(key, data[key]);
  if (key === "feeds") return feedsView(catalog);
  if (key === "about") return aboutView();
  if (key === "privacy") return privacyView();
  if (key === "status") return statusView(catalog, getCommunity());
  if (key === "contribute") return contributeView();
  if (key === "submit") return submitView(catalog);
  if (path().startsWith("/source/") || path().startsWith("/post/source/")) {
    const source = sourceForPath();
    return sourceDetail(source, catalog, following, limit);
  }
  return `${pageHeading("notFound", "countryNote")}${link("/", t("home"), "button button-primary")}`;
}
function render({ focus = false } = {}) {
  const refreshStoriesOnMount = path() === "/" && previousRenderedPath !== null && previousRenderedPath !== "/";
  previousRenderedPath = path();
  const previousMenu = app.querySelector('.nav-more[open]');
  const menuControls = 'summary, a, button, select';
  const menuFocus = !focus && previousMenu?.contains(document.activeElement)
    ? [...previousMenu.querySelectorAll(menuControls)].indexOf(document.activeElement) : -1;
  const menuScroll = previousMenu?.querySelector('.nav-more-menu')?.scrollTop || 0;
  clearTimeout(searchTimer);
  timelineCleanup?.();
  calendarCleanup?.();
  storiesCleanup?.();
  eventsCleanup?.();
  directoryCleanup?.();
  renderVersion++;
  setLocale(getLocale());
  const current = routes[path()] || "sources";
  const detail = sourceForPath();
  document.title = `${detail ? sourceDisplayName(detail) : t(current)} · ${t("brand")}`;
  updateMetadata();
  const isTimeline = ["/", "/post/"].includes(path());
  document.body.classList.remove("feed-locked");
  app.innerHTML =
    navigation(path(), routes, getSession()) +
    `<main id="main" class="main-container${path() === "/post/" ? " timeline-main" : path() === "/" ? " home-main" : ""}" tabindex="-1">${body()}</main>` +
    footer();
  directoryCleanup = bindDirectoryColumns(app);
  if (isTimeline && catalog) timelineCleanup = bindTimeline(app);
  if (path() === "/events/" && catalog) eventsCleanup = bindEvents(app);
  if (path() === "/" && catalog) {
    calendarCleanup = bindGoogleCalendar(app);
    storiesCleanup = bindStories(app, {
      catalog,
      refreshOnMount: refreshStoriesOnMount,
      refreshCatalog: async ({ signal }) => {
        const response = await fetch("/api/v1/catalog", { signal, cache: "no-store", headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("catalog");
        return response.json();
      },
      onRefresh: next => { catalog.stories = next.stories; },
    });
  }
  if (menuFocus >= 0) {
    const menu = app.querySelector('.nav-more');
    menu.open = true;
    menu.querySelectorAll(menuControls)[menuFocus]?.focus({ preventScroll: true });
    menu.querySelector('.nav-more-menu').scrollTop = menuScroll;
  }
  if (focus) document.querySelector("#main")?.focus({ preventScroll: true });
}

function updateMetadata() {
  const source = sourceForPath();
  const descriptionText = source && sourceSummaryText(source) || t("aboutBody");
  const canonical = document.querySelector('link[rel="canonical"]');
  const base = canonical ? new URL(canonical.href).origin : location.origin;
  const href = base + path() + "?lang=" + getLocale();
  if (canonical) canonical.href = href;
  document
    .querySelectorAll("link[hreflang]")
    .forEach((node) => (node.href = base + path() + "?lang=" + node.hreflang));
  for (const [property, value] of [
    ["og:title", document.title],
    ["og:site_name", t("brand")],
    ["og:url", href],
    ["og:description", descriptionText],
  ]) {
    const node = document.querySelector(`meta[property="${property}"]`);
    if (node) node.content = value;
  }
  const description = document.querySelector('meta[name="description"]');
  if (description) description.content = descriptionText;
}
let refreshingCommunity = false;
function syncAccountNavigation() {
  const control = document.querySelector('[data-account-nav]');
  if (control && !control.querySelector('[aria-busy="true"]')) control.outerHTML = accountNavigation(getSession());
}
async function refreshVisibleCommunity() {
  if (
    refreshingCommunity ||
    document.visibilityState === "hidden" ||
    !["/contribute/", "/status/"].includes(path())
  )
    return;
  refreshingCommunity = true;
  const currentPath = path();
  try {
    await refreshCommunity();
    syncAccountNavigation();
    if (currentPath !== path()) return;
    if (currentPath === "/contribute/") {
      const panel = document.querySelector(".capacity-panel");
      if (panel) panel.outerHTML = capacityPanel();
    } else render();
  } finally {
    refreshingCommunity = false;
  }
}
setInterval(refreshVisibleCommunity, 60000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refreshVisibleCommunity();
});

function navigate(url) {
  const next = new URL(url, location.href);
  if (!next.searchParams.has("lang"))
    next.searchParams.set("lang", getLocale());
  history.pushState({}, "", next.pathname + next.search + next.hash);
  state = readState();
  limit = 24;
  render({ focus: true });
  window.scrollTo({ top: 0, behavior: "instant" });
  if (["/contribute/", "/submit/", "/status/"].includes(path())) {
    const version = renderVersion;
    refreshCommunity().then(() => {
      syncAccountNavigation();
      if (version === renderVersion) {
        if (path() === "/status/") render();
        else syncCommunityUi();
      }
    });
  }
}
async function load() {
  loadFailed = false;
  render();
  try {
    const response = await fetch("/api/v1/catalog", {
      headers: { Accept: "application/json" },
    });
    if (!response.ok) throw new Error("catalog");
    catalog = await response.json();
    for (const key of [
      "sources",
      "posts",
      "events",
      "scores",
      "scoreSources",
      "countries",
      "feeds",
    ])
      if (!Array.isArray(catalog[key])) catalog[key] = [];
    render();
    const version = renderVersion;
    await refreshCommunity();
    syncAccountNavigation();
    if (
      version === renderVersion &&
      ["/status/", "/contribute/", "/submit/"].includes(path())
    ) {
      if (path() === "/status/") render();
      else syncCommunityUi();
    }
  } catch {
    if (!catalog) {
      loadFailed = true;
      render();
    }
  }
}
initializeShell();
if (path() === '/') {
  const authError = new URLSearchParams(location.search).get('auth_error');
  if (authError) toast(t(authError === 'cancelled' ? 'loginCancelled' : 'loginFailed'));
}
app.addEventListener("click", (event) => {
  const googleAuth = event.target.closest('[data-google-auth]');
  if (googleAuth) { handleGoogleAuth(googleAuth, render); return; }
  if (handleShellClick(event)) return;
  const expand = event.target.closest("[data-expand-post]");
  if (expand) { togglePostExpansion(expand); return; }
  const sort = event.target.closest("[data-source-sort]");
  if (sort) {
    state.descending = state.sort === sort.dataset.sourceSort ? !state.descending : false;
    state.sort = sort.dataset.sourceSort;
    updateUrl(); render(); return;
  }
  const share = event.target.closest("[data-share]");
  if (share) {
    const url = safeUrl(share.dataset.share);
    if (url) {
      const value = new URL(url, location.origin).href;
      if (navigator.share) navigator.share({ title: share.dataset.shareTitle || t("brand"), url: value }).catch(error => { if (error.name !== "AbortError") toast(t("copyFailed")); });
      else if (navigator.clipboard?.writeText) navigator.clipboard.writeText(value).then(() => toast(t("copied"))).catch(() => toast(t("copyFailed")));
      else toast(t("copyFailed"));
    }
    return;
  }
  const a = event.target.closest("a");
  if (a && a.getAttribute("href")?.startsWith("#")) return;
  if (
    a &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.shiftKey &&
    !event.altKey &&
    event.button === 0 &&
    !a.hasAttribute("download") &&
    a.target !== "_blank"
  ) {
    const url = new URL(a.href, location.href);
    if (
      url.origin === location.origin &&
      (routes[url.pathname] ||
        /^\/(?:post\/)?source\/[^/]+\/$/.test(url.pathname))
    ) {
      event.preventDefault();
      navigate(url);
    }
  }
  const follow = event.target.closest("[data-follow]");
  if (follow) {
    const id = follow.dataset.follow;
    const postId = follow.closest("[data-timeline-post]")?.dataset.timelinePost;
    const eventId = follow.closest("[data-event-id]")?.dataset.eventId;
    const eventPost = follow.closest("[data-event-post]")?.dataset.eventPost;
    const wasFocused = document.activeElement === follow;
    if (following.has(id)) following.delete(id);
    else following.add(id);
    try {
      localStorage.setItem("atlas-following", JSON.stringify([...following]));
    } catch {}
    const scroll = window.scrollY;
    render();
    window.scrollTo(0, scroll);
    if (wasFocused) [...app.querySelectorAll("[data-follow]")].find(node =>
      node.dataset.follow === id && node.closest("[data-timeline-post]")?.dataset.timelinePost === postId
      && node.closest("[data-event-id]")?.dataset.eventId === eventId
      && node.closest("[data-event-post]")?.dataset.eventPost === eventPost
    )?.focus({ preventScroll: true });
    return;
  }
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "retry") load();
  if (action === "more") {
    const wasFocused = document.activeElement === event.target.closest('[data-action="more"]');
    limit += 24;
    const scroll = window.scrollY;
    render();
    window.scrollTo(0, scroll);
    if (wasFocused) (app.querySelector('[data-action="more"]') || app.querySelector('.feed-load-more-status'))?.focus({preventScroll:true});
  }
  if (action === "reset") {
    state = {
      q: "",
      country: "",
      platform: "",
      type: "",
      kind: "",
      period: "upcoming",
      followed: false,
      year: "",
    };
    limit = 24;
    updateUrl();
    render();
  }
  const copy = event.target.closest("[data-copy]");
  if (copy) {
    const href = safeUrl(copy.dataset.copy);
    if (href) {
      if (navigator.clipboard?.writeText)
        navigator.clipboard
          .writeText(new URL(href, location.origin).href)
          .then(() => toast(t("copied")))
          .catch(() => toast(t("copyFailed")));
      else toast(t("copyFailed"));
    }
  }
  const remove = event.target.closest("[data-withdraw]");
  if (remove) withdraw(remove.dataset.withdraw, render);
});
app.addEventListener("change", (event) => {
  const node = event.target;
  if (node.id === "language-select") {
    if (app.querySelector('#contribution-form[data-submitting], #submission-form[data-submitting]')) { node.value = getLocale(); return; }
    const menuOpen = document.querySelector(".nav-more")?.open;
    const wasFocused = document.activeElement === node;
    // Hold unsent values only for this synchronous render, never in browser storage.
    const form = app.querySelector('#contribution-form, #submission-form');
    const draft = form ? [...form.querySelectorAll('input[name], textarea[name], select[name]')].map(field => ({
      name: field.name, value: field.value, checked: field.checked,
    })) : [];
    const formId = form?.id;
    setLocale(node.value);
    updateUrl();
    render();
    const replacement = formId && document.getElementById(formId);
    if (replacement) for (const field of replacement.querySelectorAll('input[name], textarea[name], select[name]')) {
      const saved = draft.find(value => value.name === field.name);
      if (saved) { field.value = saved.value; if (field.type === 'checkbox') field.checked = saved.checked; }
    }
    if (menuOpen) document.querySelector(".nav-more").open = true;
    if (wasFocused) document.querySelector("#language-select")?.focus({ preventScroll: true });
    return;
  }
  if (node.dataset.filter) {
    const filterName = node.dataset.filter;
    const wasFocused = document.activeElement === node;
    state[node.dataset.filter] =
      node.type === "checkbox" ? node.checked : node.value;
    limit = 24;
    updateUrl();
    render();
    if (wasFocused) [...app.querySelectorAll("[data-filter]")].find(control => control.dataset.filter === filterName)?.focus({ preventScroll: true });
  }
});
app.addEventListener("input", (event) => {
  if (event.target.id !== "catalog-search" || event.isComposing) return;
  clearTimeout(searchTimer);
  const selection = event.target.selectionStart;
  state.q = event.target.value;
  searchTimer = setTimeout(() => {
    limit = 24;
    updateUrl();
    render();
    const search = document.querySelector("#catalog-search");
    if (search) {
      search.focus({ preventScroll: true });
      if (selection !== null) search.setSelectionRange(selection, selection);
    }
  }, 220);
});
app.addEventListener("submit", (event) => {
  if (["contribution-form", "submission-form"].includes(event.target.id)) {
    event.preventDefault();
    handleForm(event.target, render);
  }
});
app.addEventListener(
  "error",
  (event) => {
    if (event.target.tagName === "IMG") {
      event.target.hidden = true;
      event.target.classList.add("failed-image");
    }
  },
  true,
);
window.addEventListener("popstate", () => {
  state = readState();
  limit = 24;
  const lang = new URLSearchParams(location.search).get("lang");
  if (lang) setLocale(lang);
  render();
});

load();
