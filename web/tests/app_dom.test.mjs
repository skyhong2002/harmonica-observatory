/** Actual DOM/event integration; no browser, network, credentials or runtime writes. */
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(predicate, message) {
  for (let i = 0; i < 150; i++) {
    if (predicate()) return;
    await sleep(10);
  }
  assert.fail(message);
}

test("application DOM journey across languages, routing, filters and community forms", async (t) => {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => errors.push(error.message));
  const dom = new JSDOM(
    readFileSync(new URL("../index.html", import.meta.url), "utf8").replace(
      "</head>",
      '<link rel="canonical" href="http://localhost:8330/source/?lang=en"></head>',
    ),
    {
      url: "http://localhost:8330/source/?lang=en",
      pretendToBeVisual: true,
      virtualConsole,
    },
  );
  const { window } = dom;
  // jsdom does not implement layout scrolling or the native dialog top layer.
  // These adapters preserve real DOM nodes/events; application code stays intact.
  window.scrollTo = () => {};
  window.HTMLDialogElement.prototype.showModal = function () {
    this.setAttribute("open", "");
  };
  window.HTMLDialogElement.prototype.close = function (value = "") {
    this.returnValue = value;
    this.removeAttribute("open");
    this.dispatchEvent(new window.Event("close"));
  };
  for (const key of [
    "window",
    "document",
    "location",
    "history",
    "navigator",
    "localStorage",
    "FormData",
  ]) {
    Object.defineProperty(globalThis, key, {
      value: key === "window" ? window : window[key],
      configurable: true,
      writable: true,
    });
  }
  const intervals = [];
  const originalInterval = globalThis.setInterval;
  globalThis.setInterval = (...args) => {
    const timer = originalInterval(...args);
    timer.unref();
    intervals.push(timer);
    return timer;
  };
  t.after(() => {
    intervals.forEach(clearInterval);
    globalThis.setInterval = originalInterval;
    dom.window.close();
  });
  const sources = [
    {
      id: "tokyo",
      url: "/source/tokyo/",
      name: "東京口琴團",
      nameEn: "Tokyo Harmonica",
      countryCode: "JP",
      country: "日本",
      type: "ensemble",
      summary: "Original Japanese ensemble",
      tags: [],
      links: [],
    },
    {
      id: "seoul",
      url: "/source/seoul/",
      name: "서울 하모니카",
      nameEn: "Seoul Harmonica",
      countryCode: "KR",
      country: "韓國",
      type: "artist",
      summary: "Original Korean artist",
      tags: [],
      links: [],
    },
  ];
  const catalog = {
    schemaVersion: "harmonica-atlas/v1",
    sources,
    posts: [
      {
        id: "one",
        sourceId: "tokyo",
        sourceName: sources[0].name,
        text: "原文 <b>保持</b>",
        url: "https://example.org/post",
        platform: "instagram",
        countryCode: "JP",
        publishedAt: "2026-01-01T00:00:00Z",
      },
    ],
    stories: [],
    calendars: [{id:"test@group.calendar.google.com",key:"taiwan",status:"ok"}],
    events: [],
    scores: [],
    scoreSources: [],
    countries: [
      { code: "JP", count: 1 },
      { code: "KR", count: 1 },
    ],
    feeds: [],
    status: { overall: "unknown", services: [] },
  };
  const session = {
    csrfToken: "fixture-csrf-only",
    contributions: [],
    submissions: [],
  };
  const community = {
    activeAccounts: 0,
    budgetRemainingUsd: 0,
    crawlSchedule: {
      pool: { usableAccountCount: 1, remainingUsd: 3.25 },
      platforms: {
        facebook: { sourceCount: 2, estimatedDays: 1, state: "paced" },
      },
    },
  };
  let failure = null;
  let refreshGate = null;
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    const method = options.method || "GET";
    const path = new URL(url, window.location.href).pathname;
    calls.push({ method, path, options });
    const response = (payload, ok = true) => ({
      ok,
      json: async () => structuredClone(payload),
    });
    if (method === "GET") {
      if (refreshGate && path !== "/api/v1/catalog") await refreshGate;
      if (path === "/api/v1/catalog") return response(catalog);
      if (path === "/api/v1/session") return response(session);
      if (path === "/api/v1/community") return response(community);
    }
    assert.equal(
      options.headers["X-CSRF-Token"],
      session.csrfToken,
      "writes carry session CSRF",
    );
    if (failure) return response({ code: failure }, false);
    if (method === "POST" && path === "/api/v1/contributions") {
      const body = JSON.parse(options.body);
      assert.equal(body.consent, true);
      assert.equal(body.token, "fixture-not-a-real-provider-token");
      session.contributions = [
        {
          id: "apy_fixture",
          name: body.name,
          status: "active",
          budgetUsd: body.budgetUsd,
          spentUsd: 0,
          reservedUsd: 0,
          budgetRemainingUsd: body.budgetUsd,
        },
      ];
      return response({
        contribution: session.contributions[0],
        crawlImpact: {
          before: community.crawlSchedule,
          after: community.crawlSchedule,
        },
      });
    }
    if (method === "DELETE" && path === "/api/v1/contributions/apy_fixture") {
      session.contributions[0].status = "revoked";
      return response({
        ok: true,
        crawlImpact: {
          before: community.crawlSchedule,
          after: community.crawlSchedule,
        },
      });
    }
    if (method === "POST" && path === "/api/v1/submissions") {
      const body = JSON.parse(options.body);
      session.submissions = [
        { ...body, status: "reviewing", createdAt: "2026-01-01T00:00:00Z" },
      ];
      return response({ submission: session.submissions[0] });
    }
    throw new Error("Unexpected test request " + method + " " + path);
  };
  const $ = (selector) => window.document.querySelector(selector);
  const change = (selector, value) => {
    const node = $(selector);
    assert.ok(node, selector);
    if (node.type === "checkbox") node.checked = value;
    else node.value = value;
    node.dispatchEvent(new window.Event("change", { bubbles: true }));
  };
  const click = (selector) => {
    const node = $(selector);
    assert.ok(node, selector);
    node.dispatchEvent(
      new window.MouseEvent("click", {
        bubbles: true,
        cancelable: true,
        button: 0,
      }),
    );
  };
  const submit = (form) =>
    form.dispatchEvent(
      new window.Event("submit", { bubbles: true, cancelable: true }),
    );
  const fillContribution = () => {
    const form = $("#contribution-form");
    form.elements.name.value = "Fixture capacity";
    form.elements.token.value = "fixture-not-a-real-provider-token";
    form.elements.budgetUsd.value = "1.25";
    form.elements.consent.checked = true;
    return form;
  };
  await import("../assets/app.js");
  const { t: translate } = await import("../assets/i18n.js");
  await until(
    () => window.document.querySelectorAll(".source-card").length === 2,
    "directory must render after catalog load",
  );

  await t.test(
    "four language switches retain independent country filtering",
    () => {
      change("[data-filter=country]", "JP");
      for (const locale of ["zh-Hant", "ja", "ko", "en"]) {
        change("#language-select", locale);
        assert.equal(window.document.documentElement.lang, locale);
        assert.equal(
          new URLSearchParams(window.location.search).get("country"),
          "JP",
        );
        assert.equal(
          new URLSearchParams(window.location.search).get("lang"),
          locale,
        );
        assert.equal(
          window.document.querySelectorAll(".source-card").length,
          1,
        );
        assert.ok($(".source-card").textContent.includes("東京口琴團"));
      }
    },
  );
  await t.test("internal navigation retains locale and source metadata", () => {
    change("#language-select", "ko");
    click(".source-card h3 a");
    assert.equal(window.location.pathname, "/source/tokyo/");
    assert.equal(new URLSearchParams(window.location.search).get("lang"), "ko");
    assert.ok(window.document.title.includes("東京口琴團"));
    assert.ok($("link[rel=canonical]").href.includes("/source/tokyo/?lang=ko"));
    assert.ok($(".post-text").textContent.includes("原文 <b>保持</b>"));
    assert.equal(
      $(".post-text b"),
      null,
      "quoted markup remains original text",
    );
    click('.site-nav a[href="/source/"]');
    change("#language-select", "en");
    assert.equal($("link[rel=canonical]").href, "http://localhost:8330/source/");
  });
  await t.test(
    "IME input stays connected until committed and search then filters",
    async () => {
      const input = $("#catalog-search");
      input.value = "東京";
      input.dispatchEvent(
        new window.InputEvent("input", {
          bubbles: true,
          isComposing: true,
          data: "京",
        }),
      );
      await sleep(280);
      assert.equal(
        $("#catalog-search"),
        input,
        "composition must not replace focused node",
      );
      assert.equal(new URLSearchParams(window.location.search).get("q"), null);
      input.dispatchEvent(
        new window.InputEvent("input", { bubbles: true, isComposing: false }),
      );
      await until(
        () => new URLSearchParams(window.location.search).get("q") === "東京",
        "committed search should reach URL",
      );
      assert.equal(window.document.querySelectorAll(".source-card").length, 1);
      click("[data-action=reset]");
    },
  );
  await t.test("follow state persists and followed filter uses it", () => {
    click("[data-follow=tokyo]");
    assert.deepEqual(
      JSON.parse(window.localStorage.getItem("atlas-following")),
      ["tokyo"],
    );
    assert.equal($("[data-follow=tokyo]").getAttribute("aria-pressed"), "true");
    change("[data-filter=followed]", true);
    assert.equal(window.document.querySelectorAll(".source-card").length, 1);
    click("[data-follow=tokyo]");
    assert.equal(window.document.querySelectorAll(".source-card").length, 0);
    click("[data-action=reset]");
  });
  await t.test(
    "contribution capacity includes operator pool and API errors clear token",
    async () => {
      click('.site-nav a[href="/contribute/"]');
      await until(
        () =>
          $("#contribution-form") &&
          !$("#contribution-form button[type=submit]").disabled,
        "session should enable contribution form",
      );
      await sleep(25);
      assert.ok($(".capacity-panel").textContent.includes("$3.25"));
      failure = "invalid_token";
      submit(fillContribution());
      await until(
        () => $("#form-message").classList.contains("is-error"),
        "API error should render",
      );
      assert.equal($("#contribution-token").value, "");
      assert.equal($("#form-message").textContent, translate("invalidToken"));
      assert.equal($("#contribution-form button[type=submit]").disabled, false);
      failure = null;
    },
  );
  await t.test(
    "successful contribution resets sensitive input and shows immediate impact",
    async () => {
      submit(fillContribution());
      await until(
        () => $(".owned-contribution"),
        "owned contribution should render",
      );
      assert.equal($("#contribution-token").value, "");
      assert.ok(
        $(".owned-contribution").textContent.includes("Fixture capacity"),
      );
      assert.ok($(".impact-panel"));
      assert.ok(
        !window.document.body.innerHTML.includes(
          "fixture-not-a-real-provider-token",
        ),
      );
    },
  );
  await t.test(
    "withdrawal cancellation does not send DELETE; errors keep ownership",
    async () => {
      const count = () => calls.filter((c) => c.method === "DELETE").length;
      const before = count();
      click("[data-withdraw]");
      assert.ok($("#confirm-dialog").open);
      $("#confirm-dialog").close("cancel");
      await sleep(20);
      assert.equal(count(), before);
      failure = "rate_limited";
      click("[data-withdraw]");
      $("#confirm-dialog").close("confirm");
      await until(
        () => $("#withdraw-message").textContent === translate("rateLimited"),
        "withdrawal error should be localized",
      );
      assert.ok($("[data-withdraw]"));
      failure = null;
    },
  );
  await t.test(
    "confirmed withdrawal refreshes owner state and impact",
    async () => {
      click("[data-withdraw]");
      $("#confirm-dialog").close("confirm");
      await until(
        () => !$("[data-withdraw]"),
        "revoked contribution must no longer offer withdrawal",
      );
      assert.ok(
        $(".owned-contribution").textContent.includes(translate("withdrawn")),
      );
      assert.ok($(".impact-panel"));
    },
  );
  await t.test(
    "source submission uses current country and returns reviewing state",
    async () => {
      click('.footer-links a[href="/submit/"]');
      await until(
        () =>
          $("#submission-form") &&
          !$("#submission-form button[type=submit]").disabled,
        "submission form session",
      );
      await sleep(25);
      const form = $("#submission-form");
      form.elements.url.value = "https://example.org/public-source";
      form.elements.countryCode.value = "KR";
      form.elements.note.value = "Original public source <b>note</b>";
      submit(form);
      await until(
        () => $(".submission-row"),
        "submission should appear in owner list",
      );
      assert.equal(session.submissions[0].countryCode, "KR");
      assert.ok(
        $(".submission-row").textContent.includes(
          "Original public source <b>note</b>",
        ),
      );
      assert.equal($(".submission-row b"), null);
      assert.ok(
        $(".submission-row").textContent.includes(translate("reviewing")),
      );
    },
  );
  await t.test("history restoration restores URL language and filter", () => {
    window.history.pushState({}, "", "/source/?lang=ja&country=KR");
    window.dispatchEvent(new window.PopStateEvent("popstate"));
    assert.equal(window.document.documentElement.lang, "ja");
    assert.equal($("[data-filter=country]").value, "KR");
    assert.equal(window.document.querySelectorAll(".source-card").length, 1);
    assert.ok($(".source-card").textContent.includes("서울 하모니카"));
  });
  await t.test(
    "late community refresh preserves an in-progress contribution draft",
    async () => {
      let release;
      refreshGate = new Promise((resolve) => {
        release = resolve;
      });
      click('.site-nav a[href="/contribute/"]');
      const field = $("#contribution-name");
      field.focus();
      field.value = "Draft while refreshing";
      field.dispatchEvent(new window.InputEvent("input", { bubbles: true }));
      release();
      refreshGate = null;
      await sleep(40);
      assert.equal($("#contribution-name").value, "Draft while refreshing");
      assert.equal(
        window.document.activeElement,
        $("#contribution-name"),
        "refresh should preserve input focus",
      );
    },
  );
  await t.test(
    "late session refresh also preserves the source submission draft",
    async () => {
      let release;
      refreshGate = new Promise((resolve) => {
        release = resolve;
      });
      click('.footer-links a[href="/submit/"]');
      const note = $("#submission-note");
      note.focus();
      note.value = "Draft original source note";
      note.dispatchEvent(new window.InputEvent("input", { bubbles: true }));
      release();
      refreshGate = null;
      await sleep(40);
      assert.equal($("#submission-note").value, "Draft original source note");
      assert.equal(window.document.activeElement, $("#submission-note"));
    },
  );
  await t.test("pending directory search cannot replace a draft after navigation", async () => {
    click('.site-nav a[href="/source/"]');
    const search = $("#catalog-search");
    search.value = "pending query";
    search.dispatchEvent(new window.InputEvent("input", { bubbles: true }));
    click('.site-nav a[href="/contribute/"]');
    const draft = $("#contribution-name");
    draft.value = "Keep this draft after search";
    draft.focus();
    await sleep(300);
    assert.equal($("#contribution-name"), draft);
    assert.equal(draft.value, "Keep this draft after search");
    assert.equal(window.document.activeElement, draft);
    assert.equal(new URLSearchParams(window.location.search).get("q"), null);
  });
  await t.test("home composes stories, Google calendar and a unified timeline while posts opens the same full timeline", async () => {
    click('.brand');
    assert.deepEqual([...$(".observatory-home").children].filter(node => node.tagName === "SECTION").map(node => node.classList[0]), ["home-stories", "home-calendar", "home-posts"]);
    assert.equal(window.document.querySelectorAll(".ob-stories").length, 1);
    assert.ok($("[data-google-calendar-embed]"));
    assert.equal($(".calendar-grid"), null);
    assert.ok($(".home-posts .feed-river"));
    assert.equal(window.document.body.classList.contains("feed-locked"), false);
    const feed = $(".home-posts .observatory-timeline");
    click('[data-google-calendar-source]');
    assert.equal($("[data-google-calendar-embed]").hidden, true);
    click('[data-google-calendar-source]');
    assert.equal($("[data-google-calendar-embed]").hidden, false);
    assert.equal(new URL($("[data-google-calendar-embed]").src).hostname, "calendar.google.com");
    assert.equal($(".home-posts .observatory-timeline"), feed, "calendar changes preserve the timeline DOM and filtering");
    click('.site-nav a[href="/post/"]');
    assert.equal($("[data-google-calendar-embed]"), null);
    assert.ok($(".feed-river"));
    assert.equal(window.document.body.classList.contains("feed-locked"), false);
  });
  await t.test("language changes preserve unsent form drafts without storing tokens", async () => {
    click('.nav-resource-grid a[href="/contribute/"]');
    await sleep(50);
    $('#contribution-name').value = 'Draft contribution';
    $('#contribution-token').value = 'mock-only-not-a-real-provider-token';
    $('#contribution-budget').value = '2.50';
    $('[name="consent"]').checked = true;
    for (const locale of ['ja', 'ko', 'zh-Hant', 'en']) {
      change('#language-select', locale);
      assert.equal($('#contribution-name').value, 'Draft contribution');
      assert.equal($('#contribution-token').value, 'mock-only-not-a-real-provider-token');
      assert.equal($('#contribution-budget').value, '2.50');
      assert.equal($('[name="consent"]').checked, true);
      assert.ok(!JSON.stringify({...localStorage}).includes('mock-only-not-a-real-provider-token'));
      assert.ok(!location.href.includes('mock-only-not-a-real-provider-token'));
    }
    click('.nav-resource-grid a[href="/submit/"]');
    await sleep(50);
    $('#submission-url').value = 'https://example.org/source';
    $('#submission-note').value = 'Original 日本語 한국어';
    $('#submission-country').value = 'JP';
    change('#language-select', 'ko');
    assert.equal($('#submission-url').value, 'https://example.org/source');
    assert.equal($('#submission-note').value, 'Original 日本語 한국어');
    assert.equal($('#submission-country').value, 'JP');
  });
  await t.test("More keeps language focus through locale changes and background status refresh", async () => {
    click('.nav-info-links a[href="/status/"]');
    await sleep(60);
    $(".nav-more").open = true;
    $("#language-select").focus();
    change('#language-select', 'ko');
    assert.equal($(".nav-more").open, true);
    assert.equal(window.document.activeElement, $("#language-select"));
    const previousSelect = $("#language-select");
    window.document.dispatchEvent(new window.Event('visibilitychange'));
    await until(() => $("#language-select") !== previousSelect, 'status refresh renders new content');
    assert.equal($(".nav-more").open, true);
    assert.equal(window.document.activeElement, $("#language-select"));
    assert.equal($("#language-select").value, 'ko');
  });
  await t.test("contextual reporting survives locale changes and generic filters retain keyboard focus", async () => {
    click('.site-nav a[href="/source/"]');
    const country = $('[data-filter="country"]');
    country.focus();
    change('[data-filter="country"]', 'JP');
    assert.equal(window.document.activeElement, $('[data-filter="country"]'));
    click('.context-report-link');
    assert.equal($("#submission-url").value, "http://localhost:8330/source/tokyo/");
    change('#language-select', 'ja');
    assert.equal($("#submission-url").value, "http://localhost:8330/source/tokyo/");
    assert.equal(new URLSearchParams(window.location.search).get('reportCountry'), 'JP');
    assert.ok($("#submission-note").value.includes('東京口琴團'));
  });
  assert.deepEqual(errors, [], "DOM must not emit unhandled runtime errors");
  assert.ok(
    calls.every((c) => c.path.startsWith("/api/v1/")),
    "all IO stayed within mocked public contracts",
  );
});
