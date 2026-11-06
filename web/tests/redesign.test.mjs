import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

test('the redesigned interface is always enabled and ignores the old switch URL', async () => {
  const dom = new JSDOM('', { url: 'https://example.org/?redesign=off' });
  Object.defineProperty(globalThis, 'document', { value: dom.window.document, configurable: true });
  try {
    const { isRedesign, initializeRedesign } = await import('../assets/redesign.js');
    assert.equal(isRedesign(), true);
    assert.equal(initializeRedesign(), true);
    assert.equal(document.documentElement.dataset.redesign, 'on');
  } finally {
    dom.window.close();
  }
});
