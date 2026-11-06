/** Pure-module integration checks: node --test web/tests/catalog_contract.test.mjs */
import test from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { resolve, dirname } from "node:path";

globalThis.document = { documentElement: { lang: "en" } };
Object.defineProperty(globalThis, "localStorage", {
  value: { getItem: () => null, setItem: () => {} },
  configurable: true,
});
const i18n = await import("../assets/i18n.js");
const views = await import("../assets/views.js");
const { observatoryHome } = await import("../assets/home.js");
const utils = await import("../assets/utils.js");
const community = await import("../assets/community.js");
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
// Build the actual public contract, reading existing local snapshots only.
const catalog = JSON.parse(
  execFileSync(
    "python3",
    [
      "-c",
      'import json,sys;sys.path.insert(0,"scripts");import global_catalog;print(json.dumps(global_catalog.build_catalog()))',
    ],
    {
      cwd: root,
      encoding: "utf8",
      timeout: 10000,
      maxBuffer: 32 * 1024 * 1024,
    },
  ),
);
const state = {
  q: "",
  country: "",
  platform: "",
  type: "",
  kind: "",
  period: "upcoming",
  followed: false,
  year: "",
};
const source = {
  id: "fixture-source",
  url: "/source/fixture-source/",
  name: "原文 <b>source</b> & friends",
  nameEn: "Original source",
  summary: "原始簡介 <b>bold</b>",
  countryCode: "JP",
  type: "artist",
  tags: ["口琴"],
  links: [
    { url: "https://example.org/official", label: "Official & original" },
  ],
};
const post = {
  id: "fixture-post",
  sourceId: source.id,
  sourceName: source.name,
  sourceUrl: source.url,
  text: "原文 <b>text</b> & friends",
  title: "Original <b>title</b>",
  url: "https://example.org/post",
  countryCode: "JP",
  platform: "instagram",
  publishedAt: "2026-01-02T00:00:00Z",
  isStory: false,
};
const event = {
  id: "fixture-event",
  title: "Concert <b>title</b>",
  countryCode: "US",
  start: "2026-01-02",
  end: "2026-01-03",
  allDay: true,
  timezone: "America/Los_Angeles",
  location: "Hall & friends",
  url: "https://example.org/event",
};
const plain = (html) => html.replace(/<[^>]*>/g, "");

test("all four locales have every translation and matching interpolation fields", () => {
  assert.deepEqual(
    new Set(i18n.locales),
    new Set(["en", "zh-Hant", "ja", "ko"]),
  );
  const keys = Object.keys(i18n.messages.en).sort();
  assert.ok(keys.length >= 200);
  const placeholders = (s) =>
    [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
  for (const locale of i18n.locales) {
    assert.deepEqual(Object.keys(i18n.messages[locale]).sort(), keys);
    for (const key of keys) {
      const translated = i18n.messages[locale][key];
      assert.equal(typeof translated, "string", `${locale}.${key}`);
      assert.ok(translated.trim(), `${locale}.${key} must not be blank`);
      assert.deepEqual(
        placeholders(translated),
        placeholders(i18n.messages.en[key]),
        `${locale}.${key}`,
      );
    }
  }
});

test("real catalog renders all public view families in each locale", () => {
  assert.equal(catalog.schemaVersion, "harmonica-atlas/v1");
  for (const locale of i18n.locales) {
    i18n.setLocale(locale);
    const html = [
      observatoryHome(catalog, state, new Set()),
      views.feedsView(catalog),
      views.statusView(catalog, null),
      community.contributeView(),
      community.submitView(catalog),
      views.aboutView(),
      views.privacyView(),
      views.sourceDetail(catalog.sources[0], catalog, new Set()),
      ...catalog.events.map(views.eventCard),
      ...catalog.scores.slice(0, 10).map(views.scoreRow),
    ].join("\n");
    assert.ok(html.length > 1000);
    assert.doesNotMatch(html, /\b(?:undefined|NaN)\b/);
    assert.doesNotMatch(html, /\{(?:count|date|days|shown|total)\}/);
    assert.equal(document.documentElement.lang, locale);
    for (const feed of catalog.feeds) {
      assert.ok(
        i18n.messages[locale]["feed_" + feed.id],
        `${locale} feed ${feed.id}`,
      );
      assert.ok(views.feedsView(catalog).includes(`href="${feed.url}"`));
    }
  }
});

test("original source and post text survive language changes as escaped text", () => {
  for (const locale of i18n.locales) {
    i18n.setLocale(locale);
    const html = views.sourceDetail(
      source,
      { sources: [source], posts: [post] },
      new Set(),
    );
    assert.ok(html.includes("原文 &lt;b&gt;source&lt;/b&gt; &amp; friends"));
    assert.ok(html.includes("原文 &lt;b&gt;text&lt;/b&gt; &amp; friends"));
    assert.ok(html.includes('href="/source/fixture-source/"'));
    assert.ok(html.includes('href="https://example.org/post"'));
    assert.ok(html.includes('href="https://example.org/official"'));
    assert.doesNotMatch(html, /<b>(?:source|text|title)<\/b>/);
  }
});

test("archived stories remain readable but clearly distinct from active stories", () => {
  for (const locale of i18n.locales) {
    i18n.setLocale(locale);
    for (const storyState of ["expired", "unknown"]) {
      const html = views.postCard(
        { ...post, isStory: true, storyState, sourceAvailable: false },
        [source],
      );
      assert.ok(html.includes(i18n.t("storyExpired")));
      assert.ok(html.includes("https://example.org/post"));
    }
    assert.ok(
      views
        .postCard({ ...post, isStory: true, sourceAvailable: false }, [source])
        .includes(i18n.t("storyExpired")),
    );
    assert.ok(
      !views
        .postCard(
          {
            ...post,
            isStory: true,
            storyState: "active",
            sourceAvailable: true,
            expiresAt: "2099-01-01T00:00:00Z",
          },
          [source],
        )
        .includes(i18n.t("storyExpired")),
    );
  }
  for (const story of catalog.stories) {
    assert.equal(story.storyState, "active");
    assert.ok(Date.parse(story.expiresAt) > Date.parse(catalog.evaluatedAt));
  }
});

test("all-day event civil date never shifts backward in American time zones", () => {
  i18n.setLocale("en");
  const html = views.eventCard(event);
  assert.match(html, /<strong>02<\/strong>/);
  assert.match(plain(html), /Jan 2(?:, 2026)?/);
  assert.ok(html.includes(i18n.t("allDay")));
});

test("timed events display organizer time zone independently of browser zone", () => {
  i18n.setLocale("en");
  const html = views.eventCard({
    ...event,
    start: "2026-01-03T00:30:00Z",
    end: "2026-01-03T01:30:00Z",
    allDay: false,
  });
  assert.match(html, /<strong>02<\/strong>/);
  assert.match(plain(html), /Jan 2(?:, 2026)?.*16:30–17:30/);
  assert.ok(html.includes("America/Los_Angeles"));
  assert.ok(!html.includes(i18n.t("allDay")));
});

test("all-day exclusive end uses event-local date without an extra grace day", () => {
  const original = Date.now;
  try {
    Date.now = () => Date.parse("2026-01-03T07:59:00Z"); // Jan 2 23:59 in LA
    assert.equal(utils.pastEvent(event), false);
    Date.now = () => Date.parse("2026-01-03T08:01:00Z"); // Jan 3 00:01 in LA
    assert.equal(utils.pastEvent(event), true);
  } finally {
    Date.now = original;
  }
});

test("contribution view uses aggregate accounting and never renders session secrets", async () => {
  i18n.setLocale("en");
  const original = globalThis.fetch;
  const schedule = {
    platforms: {
      facebook: { sourceCount: 10, estimatedDays: 2.5, state: "paced" },
      instagram: { sourceCount: 10, estimatedDays: null, state: "unknown" },
    },
  };
  globalThis.fetch = async (url) => ({
    ok: true,
    json: async () =>
      url.endsWith("/session")
        ? {
            csrfToken: "session-secret-marker",
            contributions: [
              {
                id: "mine",
                name: "My <b>capacity</b>",
                status: "active",
                budgetUsd: 1,
                spentUsd: 0.1,
                reservedUsd: 0.2,
                budgetRemainingUsd: 0.7,
              },
            ],
            submissions: [],
          }
        : {
            activeAccounts: 1,
            budgetRemainingUsd: 0.7,
            crawlSchedule: schedule,
          },
  });
  try {
    await community.refreshCommunity();
    const html = community.contributeView();
    assert.ok(html.includes("My &lt;b&gt;capacity&lt;/b&gt;"));
    assert.ok(html.includes('type="password"'));
    assert.ok(html.includes('data-withdraw="mine"'));
    assert.ok(html.includes("$0.70"));
    assert.ok(html.includes(i18n.t("estimateDays", { days: "2.5" })));
    assert.ok(html.includes(i18n.t("estimateUnknown")));
    assert.ok(!html.includes("session-secret-marker"));
    assert.ok(!/<button[^>]*type="submit"[^>]*disabled/.test(html));
  } finally {
    globalThis.fetch = original;
  }
});

test("unavailable status and unverified collection frequency never claim healthy", () => {
  i18n.setLocale("en");
  const html = views.statusView(
    { ...catalog, status: { overall: "unknown", services: [] } },
    null,
  );
  assert.ok(html.includes(`<h2>${i18n.t("unavailable")}</h2>`));
  assert.ok(!html.includes(`<h2>${i18n.t("healthy")}</h2>`));
  const schedule = community.scheduleView({
    platforms: {
      facebook: {
        sourceCount: 10,
        estimatedDays: null,
        state: "insufficient_daily_budget",
      },
    },
  });
  assert.ok(schedule.includes(i18n.t("noCapacity")));
});

test("civil-date boundaries remain correct during daylight-saving changes", () => {
  const original = Date.now;
  try {
    const spring = { ...event, start: "2026-03-08", end: "2026-03-09" };
    Date.now = () => Date.parse("2026-03-09T06:59:00Z");
    assert.equal(utils.pastEvent(spring), false);
    Date.now = () => Date.parse("2026-03-09T07:00:00Z");
    assert.equal(utils.pastEvent(spring), true);
    const autumn = { ...event, start: "2026-11-01", end: "2026-11-02" };
    Date.now = () => Date.parse("2026-11-02T07:59:00Z");
    assert.equal(utils.pastEvent(autumn), false);
    Date.now = () => Date.parse("2026-11-02T08:00:00Z");
    assert.equal(utils.pastEvent(autumn), true);
  } finally {
    Date.now = original;
  }
});

test("source navigation uses stable local catalog URLs", () => {
  for (const row of catalog.sources) {
    const href = utils.sourceHref(row);
    assert.ok(href.startsWith("/source/"), `source route ${row.id}`);
    assert.equal(utils.safeUrl(href), href);
  }
});

test("date formatter preserves civil dates and rejects invalid calendar dates", () => {
  i18n.setLocale("en");
  assert.equal(
    utils.date("2026-01-02", { timeZone: "America/Los_Angeles" }),
    "Jan 2, 2026",
  );
  assert.equal(
    utils.date("2026-01-02", { timeZone: "Pacific/Kiritimati" }),
    "Jan 2, 2026",
  );
  assert.equal(utils.date("2026-02-30"), i18n.t("dateUnknown"));
});

test("all-day events without an end include the entire start day in their own zone", () => {
  const original = Date.now;
  try {
    const single = { ...event, end: null, timezone: "Asia/Tokyo" };
    Date.now = () => Date.parse("2026-01-02T14:59:00Z");
    assert.equal(utils.pastEvent(single), false);
    Date.now = () => Date.parse("2026-01-02T15:00:00Z");
    assert.equal(utils.pastEvent(single), true);
    assert.equal(utils.pastEvent({ ...single, start: "2026-02-30" }), false);
  } finally {
    Date.now = original;
  }
});
