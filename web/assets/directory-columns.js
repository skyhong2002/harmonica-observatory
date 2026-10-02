import { getLocale } from './i18n.js';

const STORAGE_KEY = 'harmonica-directory-columns-v1';
const MIN_WIDTHS = [180, 65, 60, 80, 50, 65, 44];
const words = {
  'zh-Hant': {resize:'調整欄寬', hint:'拖曳或使用左右方向鍵；雙擊重設欄寬', reset:'重設欄寬'},
  en: {resize:'Resize column', hint:'Drag or use left/right arrow keys; double-click to reset widths', reset:'Reset column widths'},
  ja: {resize:'列幅を調整', hint:'ドラッグまたは左右キーで調整、ダブルクリックでリセット', reset:'列幅をリセット'},
  ko: {resize:'열 너비 조절', hint:'드래그 또는 좌우 방향키로 조절, 더블 클릭으로 초기화', reset:'열 너비 초기화'},
};

export function resizePair(widths, index, delta) {
  const next = [...widths];
  const movement = Math.max(MIN_WIDTHS[index] - widths[index], Math.min(delta, widths[index + 1] - MIN_WIDTHS[index + 1]));
  next[index] += movement;
  next[index + 1] -= movement;
  return next;
}

function readWidths(storage) {
  try {
    const value = JSON.parse(storage.getItem(STORAGE_KEY));
    return Array.isArray(value) && value.length === 7 && value.every(n => Number.isFinite(n) && n >= 20 && n <= 10000) ? value : null;
  } catch { return null; }
}

// One shared grid definition keeps the header and every rendered row aligned.
// Relative tracks adapt to viewport changes; the mobile card layout ignores them.
export function bindDirectoryColumns(root) {
  const head = root.querySelector('.src-head');
  if (!head) return () => {};
  const view = root.ownerDocument.defaultView;
  const labels = words[getLocale()] || words.en;
  let storage;
  try { storage = view.localStorage; } catch { /* Storage may be blocked. */ }
  let widths = readWidths(storage), drag = null;
  const apply = value => {
    widths = value;
    if (value) root.style.setProperty('--directory-columns', value.map((w, i) => `minmax(${MIN_WIDTHS[i]}px, ${w}fr)`).join(' '));
    else root.style.removeProperty('--directory-columns');
  };
  apply(widths);
  const measured = () => view.getComputedStyle(head).gridTemplateColumns.split(/\s+/).map(parseFloat);
  const desktop = () => view.innerWidth >= 900;
  const save = () => {
    try { if (widths) storage.setItem(STORAGE_KEY, JSON.stringify(widths)); else storage.removeItem(STORAGE_KEY); } catch { /* Keep the current session usable. */ }
  };
  const handles = [...head.children].slice(0, 6).map((cell, index) => {
    const handle = root.ownerDocument.createElement('span');
    handle.className = 'src-column-resize';
    handle.dataset.columnResize = index;
    handle.tabIndex = 0;
    handle.setAttribute('role', 'separator');
    handle.setAttribute('aria-orientation', 'vertical');
    handle.setAttribute('aria-label', `${labels.resize}: ${cell.textContent.replace(/[↑↓↕]/g, '').trim()}`);
    handle.title = labels.hint;
    cell.append(handle);
    return handle;
  });
  const updateValues = () => {
    if (!desktop()) return;
    const current = measured();
    if (current.length !== 7 || current.some(n => !Number.isFinite(n))) return;
    handles.forEach((h, i) => {
      h.setAttribute('aria-valuemin', MIN_WIDTHS[i]);
      h.setAttribute('aria-valuemax', Math.round(current[i] + current[i + 1] - MIN_WIDTHS[i + 1]));
      h.setAttribute('aria-valuenow', Math.round(current[i]));
    });
  };
  const reset = root.ownerDocument.createElement('button');
  reset.type = 'button'; reset.className = 'src-columns-reset'; reset.textContent = labels.reset;
  (root.querySelector('.results-bar') || head.parentElement).append(reset);
  const resetWidths = () => { apply(null); save(); updateValues(); };
  reset.addEventListener('click', resetWidths);
  const target = event => event.target.closest('[data-column-resize]');
  const click = event => { if (target(event)) { event.preventDefault(); event.stopPropagation(); } };
  const down = event => {
    const handle = target(event);
    if (!handle || !desktop() || event.button !== 0 || drag) return;
    const current = measured();
    if (current.length !== 7 || current.some(n => !Number.isFinite(n))) return;
    event.preventDefault();
    drag = {handle, pointerId:event.pointerId, index:Number(handle.dataset.columnResize), x:event.clientX, initial:current, previous:widths};
    try { handle.setPointerCapture(event.pointerId); } catch { /* Synthetic events have no active pointer. */ }
    head.classList.add('is-resizing');
  };
  const move = event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    apply(resizePair(drag.initial, drag.index, event.clientX - drag.x));
    updateValues();
  };
  const finish = event => {
    if (!drag || event.pointerId !== drag.pointerId) return;
    const previous = drag;
    drag = null;
    if (event.type !== 'pointerup') apply(previous.previous);
    else save();
    try { previous.handle.releasePointerCapture(event.pointerId); } catch { /* Already released. */ }
    head.classList.remove('is-resizing'); updateValues();
  };
  const keydown = event => {
    const handle = target(event);
    if (!handle || !desktop() || !['ArrowLeft','ArrowRight'].includes(event.key)) return;
    event.preventDefault(); event.stopPropagation();
    apply(resizePair(measured(), Number(handle.dataset.columnResize), (event.key === 'ArrowLeft' ? -1 : 1) * (event.shiftKey ? 24 : 8)));
    save(); updateValues();
  };
  const doubleClick = event => { if (target(event)) { event.preventDefault(); resetWidths(); } };
  head.addEventListener('click', click);
  head.addEventListener('dblclick', doubleClick);
  head.addEventListener('pointerdown', down);
  head.addEventListener('keydown', keydown);
  view.addEventListener('pointermove', move);
  view.addEventListener('pointerup', finish);
  view.addEventListener('pointercancel', finish);
  head.addEventListener('lostpointercapture', finish);
  view.addEventListener('resize', updateValues);
  updateValues();
  return () => {
    head.removeEventListener('click', click);
    head.removeEventListener('dblclick', doubleClick);
    head.removeEventListener('pointerdown', down);
    head.removeEventListener('keydown', keydown);
    head.removeEventListener('lostpointercapture', finish);
    view.removeEventListener('pointermove', move);
    view.removeEventListener('pointerup', finish);
    view.removeEventListener('pointercancel', finish);
    view.removeEventListener('resize', updateValues);
    head.classList.remove('is-resizing');
    handles.forEach(h => h.remove()); reset.remove();
    root.style.removeProperty('--directory-columns');
  };
}
