import test from 'node:test';
import assert from 'node:assert/strict';
import { eventText, eventOriginalMarkup } from '../assets/event-localization.js';

const event = { title: '音樂會', location: '音樂廳', titles: { en: 'Concert' }, locations: { en: 'Concert hall' } };
test('English display uses reviewed titles and locations; other locales retain originals', () => {
  assert.equal(eventText(event, 'title', 'en'), 'Concert');
  assert.equal(eventText(event, 'location', 'en'), 'Concert hall');
  assert.equal(eventText(event, 'title', 'ja'), '音樂會');
  assert.equal(eventText({...event, titles:{en:' '}}, 'title', 'en'), '音樂會');
});
test('original wording and reference translation label remain available without duplicates', () => {
  const html = eventOriginalMarkup(event, 'en');
  assert.match(html, /Reference translation/);
  assert.match(html, /音樂會/);
  assert.match(html, /音樂廳/);
  assert.equal(eventOriginalMarkup(event, 'ja'), '');
  assert.equal(eventOriginalMarkup({...event, title:'Concert', location:'Concert hall'}, 'en'), '');
});
test('original source text is escaped rather than inserted as markup', () => {
  const html = eventOriginalMarkup({...event, title:'<img src=x onerror=alert(1)>'}, 'en');
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
});

// Search should find a localized card even when the original is in another script.
import { textMatch } from '../assets/utils.js';
test('event search matches translated titles and venues as well as original text', () => {
  assert.equal(textMatch(event, 'Concert hall'), true);
  assert.equal(textMatch(event, '音樂會'), true);
  assert.equal(textMatch(event, 'unrelated'), false);
});
