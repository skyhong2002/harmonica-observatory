// Photograph every state in states.mjs at both sizes.
//   NODE_PATH=/path/with/playwright FONTCONFIG_FILE=... node capture.mjs site http://127.0.0.1:8401 OUT_DIR [id-filter]
//   node capture.mjs references OUT_DIR
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { SIZES, STATES, REFERENCES, SIGNED_IN_SESSION, NOW } from './states.mjs';

const [mode, ...rest] = process.argv.slice(2);
const browser = await chromium.launch();

async function settle(page, maxHeight) {
  // Walk the page so lazy images and iframes load, then return to the top.
  const height = Math.min(await page.evaluate(() => document.documentElement.scrollHeight), maxHeight * 2);
  for (let y = 0; y < height; y += 500) {
    await page.evaluate((top) => window.scrollTo(0, top), y);
    await page.waitForTimeout(120);
  }
  // Lazy iframes (the Google Calendar embed) need to sit in view to render.
  for (const frame of await page.locator('iframe:visible').all()) {
    await frame.scrollIntoViewIfNeeded({ timeout: 2000 }).catch(() => {});
    await page.waitForTimeout(3500);
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState('networkidle', { timeout: 8000 }).catch(() => {});
  await page.evaluate(() => Promise.all([...document.images].filter((img) => !img.complete).map((img) => new Promise((done) => { img.onload = img.onerror = done; setTimeout(done, 4000); }))));
  await page.waitForTimeout(600);
}

async function shoot(page, file, size, { anchor, viewportOnly } = {}) {
  let top = 0;
  if (anchor) {
    top = await page.evaluate((selector) => {
      const node = document.querySelector(selector);
      return node ? Math.round(Math.max(0, node.getBoundingClientRect().top + window.scrollY - 24)) : 0;
    }, anchor);
  }
  if (viewportOnly) {
    await page.evaluate((y) => window.scrollTo(0, y), top);
    await page.waitForTimeout(300);
    return page.screenshot({ path: file });
  }
  const full = await page.evaluate(() => document.documentElement.scrollHeight);
  const height = Math.max(size.height, Math.min(full - top, size.maxHeight));
  if (size.isMobile) {
    // Mobile full-page captures drop iframe paint (the Google Calendar embed
    // came out blank), so grow the viewport to the shot height instead.
    await page.setViewportSize({ width: size.width, height: Math.round(Math.min(height, full - top)) || size.height });
    await page.waitForTimeout(2500);
    await page.evaluate((y) => window.scrollTo(0, y), top);
    await page.waitForTimeout(400);
    return page.screenshot({ path: file });
  }
  return page.screenshot({ path: file, fullPage: true, clip: { x: 0, y: top, width: size.width, height: Math.min(height, full - top) } });
}

if (mode === 'site') {
  const [base, out, filter] = rest;
  mkdirSync(out, { recursive: true });
  const catalog = await (await fetch(base + '/api/v1/catalog')).json();
  const empty = { ...catalog, sources: [], posts: [], stories: [], events: [], scores: [], scoreSources: [], calendars: [] };
  for (const [sizeName, size] of Object.entries(SIZES).filter(([name]) => !process.env.ONLY_SIZE || name === process.env.ONLY_SIZE)) {
    for (const state of STATES.filter((s) => !filter || s.id.includes(filter))) {
      const context = await browser.newContext({
        viewport: { width: size.width, height: size.height }, deviceScaleFactor: size.deviceScaleFactor,
        isMobile: !!size.isMobile, hasTouch: !!size.hasTouch, colorScheme: state.theme === 'dark' ? 'dark' : 'light',
        locale: state.lang === 'zh-Hant' ? 'zh-TW' : state.lang, timezoneId: 'Asia/Taipei', reducedMotion: 'reduce',
      });
      const page = await context.newPage();
      await page.clock.setFixedTime(new Date(NOW));
      await page.route('**/api/v1/catalog', async (route) => {
        if (state.catalog === 'loading') return; // never answers
        if (state.catalog === 'error') return route.fulfill({ status: 500, contentType: 'application/json', body: '{"error":"Server error."}' });
        if (state.catalog === 'empty') return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(empty) });
        return route.continue();
      });
      if (state.session === 'in') await page.route('**/api/v1/session', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(SIGNED_IN_SESSION) }));
      const url = base + state.path + (state.path.includes('?') ? '&' : '?') + 'lang=' + state.lang;
      await page.goto(url, { waitUntil: state.catalog === 'loading' ? 'domcontentloaded' : 'networkidle', timeout: 45000 }).catch(() => {});
      if (state.catalog === 'loading') await page.waitForTimeout(1500);
      else {
        await page.waitForTimeout(500);
        for (const selector of state.click || []) {
          await page.locator(selector).first().click({ timeout: 5000 }).catch((error) => console.warn(state.id, 'click failed', selector, error.message.split('\n')[0]));
          await page.waitForTimeout(400);
        }
        await settle(page, size.maxHeight);
      }
      const file = `${out}/${state.id}_${sizeName}.png`;
      await shoot(page, file, size, state);
      console.log(file);
      await context.close();
    }
  }
} else if (mode === 'references') {
  const [out] = rest;
  mkdirSync(out, { recursive: true });
  for (const [sizeName, size] of Object.entries(SIZES).filter(([name]) => !process.env.ONLY_SIZE || name === process.env.ONLY_SIZE)) {
    for (const ref of REFERENCES.filter((r) => !process.argv[4] || r.id.includes(process.argv[4]))) {
      const context = await browser.newContext({
        viewport: { width: size.width, height: size.height }, deviceScaleFactor: size.deviceScaleFactor,
        isMobile: !!size.isMobile, hasTouch: !!size.hasTouch, locale: 'en-US', timezoneId: 'Asia/Taipei',
        userAgent: size.isMobile
          ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'
          : 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
      });
      const page = await context.newPage();
      await page.goto(ref.url, { waitUntil: 'domcontentloaded', timeout: 45000 }).catch(() => {});
      await page.waitForTimeout(8000);
      for (const name of ['Reject All', 'Reject all', 'Accept All', 'Accept all', 'Accept', 'Got it']) {
        const button = page.getByRole('button', { name, exact: true });
        if (await button.count().catch(() => 0)) { await button.first().click({ timeout: 2000 }).catch(() => {}); break; }
      }
      await settle(page, size.maxHeight);
      const file = `${out}/${ref.id}_${sizeName}.png`;
      await shoot(page, file, size, {});
      console.log(file);
      await context.close();
    }
  }
}
await browser.close();
