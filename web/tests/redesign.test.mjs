import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

// The switch logic itself: run with no pinned side so localStorage decides.
test('the new-interface switch is off by default, persists in this browser and accepts ?redesign=', async () => {
  const pinned = process.env.OBSERVATORY_REDESIGN;
  delete process.env.OBSERVATORY_REDESIGN;
  const dom = new JSDOM('', { url: 'https://example.org/' });
  Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true });
  Object.defineProperty(globalThis, 'localStorage', { value: dom.window.localStorage, configurable: true });
  try {
    const { isRedesign, setRedesign, initializeRedesign } = await import('../assets/redesign.js');
    assert.equal(isRedesign(), false);
    assert.equal(initializeRedesign(new URL('https://example.org/')), false);
    assert.equal(document.documentElement.dataset.redesign, undefined);
    setRedesign(true);
    assert.equal(localStorage.getItem('observatory-redesign'), 'on');
    assert.equal(document.documentElement.dataset.redesign, 'on');
    initializeRedesign(new URL('https://example.org/?redesign=off'));
    assert.equal(isRedesign(), false);
    assert.equal(localStorage.getItem('observatory-redesign'), null);
    assert.equal(document.documentElement.dataset.redesign, undefined);
    initializeRedesign(new URL('https://example.org/?redesign=on'));
    assert.equal(isRedesign(), true);
  } finally {
    if (pinned !== undefined) process.env.OBSERVATORY_REDESIGN = pinned;
    dom.window.close();
  }
});
