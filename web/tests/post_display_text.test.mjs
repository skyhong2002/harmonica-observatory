import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { setLocale } from '../assets/i18n.js';
import { postDisplayText } from '../assets/utils.js';

test('only exact generated Instagram story labels translate; authored content stays original', () => {
  const {window} = new JSDOM('', {url: 'https://example.com'});
  Object.assign(globalThis, {window, document:window.document, location:window.location, localStorage:window.localStorage});
  const story = {isStory:true,platform:'instagram'};
  const expected = {en:'Instagram story @artist.name', 'zh-Hant':'Instagram 限時動態 @artist.name', ja:'Instagram ストーリー @artist.name', ko:'Instagram 스토리 @artist.name'};
  for (const [locale,label] of Object.entries(expected)) {
    setLocale(locale);
    assert.equal(postDisplayText(story,'Instagram story @artist.name'),label);
    assert.equal(postDisplayText(story,'Instagram story @artist.name: my concert'), 'Instagram story @artist.name: my concert');
    assert.equal(postDisplayText({...story,isStory:false},'Instagram story @artist.name'),'Instagram story @artist.name');
    assert.equal(postDisplayText(story,'原始貼文\nOriginal post'),'原始貼文\nOriginal post');
  }
  window.close();
});

test('a truncated preview line is dropped when the full Threads reply below it repeats it after an "@handle ↩️:" prefix', () => {
  const preview = '@jangli_harmonica: 但實際製作的過程並沒有想像中那麼簡單。 從地形、建築、角色設定到各種互動機制，幾乎每個環節都得反覆嘗試，有時候好不容易修好一個問題，...';
  const full = '@jangli_harmonica ↩️: 但實際製作的過程並沒有想像中那麼簡單。\n從地形、建築、角色設定到各種互動機制，幾乎每個環節都得反覆嘗試，有時候好不容易修好一個問題，卻又冒出更多新的問題。';
  const post = {platform:'threads'};
  const shown = postDisplayText(post, `${preview}\n${full}`);
  assert.equal(shown, full);
  assert.equal(shown.split('@jangli_harmonica').length - 1, 1);
  assert.equal(shown.split('但實際製作的過程').length - 1, 1);
  // Plain previews still collapse, and unrelated first lines stay.
  assert.equal(postDisplayText(post, '今天的音樂會非常精彩，謝謝大家來參加，...\n今天的音樂會非常精彩，謝謝大家來參加，下次見！'), '今天的音樂會非常精彩，謝謝大家來參加，下次見！');
  assert.equal(postDisplayText(post, '@someone: 完全不同的開頭文字在這裡出現…\n@someone ↩️: 另一段內容與前一行無關。'), '@someone: 完全不同的開頭文字在這裡出現…\n@someone ↩️: 另一段內容與前一行無關。');
});

test('Threads previews collapse when the first line repeats in full or quotes a repost inline', () => {
  const post = {platform:'threads'};
  assert.equal(postDisplayText(post, '@jangli_harmonica: 原來等待的過程是有貪食蛇可以玩的嗎？！\n@jangli_harmonica : 原來等待的過程是有貪食蛇可以玩的嗎？！'), '@jangli_harmonica : 原來等待的過程是有貪食蛇可以玩的嗎？！');
  const repost = '@jangli_harmonica 🔁: 挖苦挖苦好期待！我的老婆是魔法少女❤️❤️ 去年的華文徵稿選了三部作品～\n終於要陸續出版了(汗)。\n----\n「──要保守祕密喔。」';
  assert.equal(postDisplayText(post, '@jangli_harmonica: 挖苦挖苦好期待！我的老婆是魔法少女❤️❤️ 🔁 @lsyeh_chika.publishing: "去年的華文徵稿選了三部作品～ 終於要陸續出版了(汗)。 ---- ...\n' + repost), repost);
  // A complete first line without a handle marker is authored text, not a preview.
  assert.equal(postDisplayText(post, '今天的音樂會非常精彩謝謝大家\n今天的音樂會非常精彩謝謝大家，下次見'), '今天的音樂會非常精彩謝謝大家\n今天的音樂會非常精彩謝謝大家，下次見');
});
