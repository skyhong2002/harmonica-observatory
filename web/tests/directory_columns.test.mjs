import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';
import { bindDirectoryColumns, resizePair } from '../assets/directory-columns.js';
const key = 'harmonica-directory-columns-v1';
const initial = [400, 90, 100, 140, 65, 84, 94];
function setup(saved) {
  const dom = new JSDOM('<div id="app"><div class="results-bar"></div><div class="src-head">'+['Name','Country','Type','Links','Updates','Updated','Follow'].map(t=>`<span><button data-source-sort>${t}</button></span>`).join('')+'</div></div>', {url:'https://example.org/'});
  const {window} = dom, root = window.document.querySelector('#app');
  // jsdom has no layout; supply the browser's measured tracks at the layout boundary.
  window.getComputedStyle = () => ({gridTemplateColumns:(root.style.getPropertyValue('--directory-columns').match(/[\d.]+(?=fr)/g)?.map(Number) || initial).map(n=>n+'px').join(' ')});
  if (saved !== undefined) window.localStorage.setItem(key, saved);
  let cleanup = bindDirectoryColumns(root);
  const handles = () => [...root.querySelectorAll('[data-column-resize]')];
  const pointer = (target, type, x) => {const e = new window.Event(type,{bubbles:true,cancelable:true});Object.assign(e,{clientX:x,pointerId:1,button:0});target.dispatchEvent(e);};
  return {window,root,handles,pointer,cleanup:()=>cleanup(),remount:()=>{cleanup();cleanup=bindDirectoryColumns(root);}};
}
test('adjacent widths keep their total and stop at readable minimums',()=>{
  assert.deepEqual(resizePair(initial,2,-30),[400,90,70,170,65,84,94]);
  assert.deepEqual(resizePair(initial,2,-999),[400,90,60,180,65,84,94]);
  assert.deepEqual(resizePair(initial,2,999),[400,90,160,80,65,84,94]);
});
test('drag changes the shared grid, preserves sort clicks and persists on release',()=>{
  const s=setup(); let clicks=0;s.root.addEventListener('click',()=>clicks++);
  const handle=s.handles()[2];
  s.pointer(handle,'pointerdown',300);s.pointer(s.window,'pointermove',270);s.pointer(s.window,'pointerup',270);
  assert.deepEqual(JSON.parse(s.window.localStorage.getItem(key)),resizePair(initial,2,-30));
  assert.match(s.root.style.getPropertyValue('--directory-columns'),/70fr/);
  assert.equal(handle.getAttribute('aria-valuenow'),'70');
  handle.click();assert.equal(clicks,0);
  s.root.querySelector('[data-source-sort]').click();assert.equal(clicks,1);
  s.remount();assert.equal(s.handles().length,6);assert.match(s.root.style.getPropertyValue('--directory-columns'),/70fr/);s.cleanup();
});
test('keyboard resizing is saved, reset removes saved widths',()=>{
  const s=setup();s.handles()[2].dispatchEvent(new s.window.KeyboardEvent('keydown',{key:'ArrowLeft',bubbles:true}));
  assert.equal(JSON.parse(s.window.localStorage.getItem(key))[2],92);
  s.root.querySelector('.src-columns-reset').click();
  assert.equal(s.window.localStorage.getItem(key),null);assert.equal(s.root.style.getPropertyValue('--directory-columns'),'');s.cleanup();
});
test('cancelled drag restores prior widths and cleanup removes listeners',()=>{
  const s=setup();s.pointer(s.handles()[2],'pointerdown',300);s.pointer(s.window,'pointermove',270);s.pointer(s.window,'pointercancel',270);
  assert.equal(s.root.style.getPropertyValue('--directory-columns'),'');assert.equal(s.window.localStorage.getItem(key),null);
  s.pointer(s.handles()[2],'pointerdown',300);s.cleanup();s.pointer(s.window,'pointermove',250);
  assert.equal(s.root.style.getPropertyValue('--directory-columns'),'');assert.equal(s.handles().length,0);
});
test('corrupt preferences and blocked storage never break the directory',()=>{
  for(const saved of ['{','[]','[1,2,3,4,5,6,"bad"]','[1,2,3,4,5,6,7]']){
    const s=setup(saved);assert.equal(s.root.style.getPropertyValue('--directory-columns'),'');s.cleanup();
  }
  const s=setup();s.cleanup();Object.defineProperty(s.window,'localStorage',{get(){throw Error('blocked');}});
  assert.doesNotThrow(()=>{const cleanup=bindDirectoryColumns(s.root);s.root.querySelector('.src-columns-reset').click();cleanup();});
});
test('mobile ignores drag and retains desktop preferences',()=>{
  const s=setup(JSON.stringify(initial));Object.defineProperty(s.window,'innerWidth',{value:390});
  s.pointer(s.handles()[2],'pointerdown',300);s.pointer(s.window,'pointermove',270);s.pointer(s.window,'pointerup',270);
  assert.deepEqual(JSON.parse(s.window.localStorage.getItem(key)),initial);s.cleanup();
});
