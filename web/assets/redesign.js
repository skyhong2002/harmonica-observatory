// Temporary review hook while the new interface replaces the original one.
// Visitors get no switch; `?redesign=on|off` (kept in localStorage) lets the
// review screenshots show either version. Removed before the PR.
const KEY = 'observatory-redesign';

export function isRedesign() {
  // Test runs pin a side with OBSERVATORY_REDESIGN=on|off; browsers have no process.
  const forced = globalThis.process?.env?.OBSERVATORY_REDESIGN;
  if (forced === 'on' || forced === 'off') return forced === 'on';
  try { return globalThis.localStorage?.getItem(KEY) === 'on'; } catch { return false; }
}

export function applyRedesign() {
  const root = globalThis.document?.documentElement;
  const on = isRedesign();
  if (root) {
    if (on) root.dataset.redesign = 'on';
    else delete root.dataset.redesign;
  }
  return on;
}

export function setRedesign(on) {
  try {
    if (on) globalThis.localStorage?.setItem(KEY, 'on');
    else globalThis.localStorage?.removeItem(KEY);
  } catch { /* Storage may be blocked; the switch then lasts for this page. */ }
  return applyRedesign();
}

export function initializeRedesign(location = globalThis.location) {
  const wanted = location ? new URLSearchParams(location.search).get('redesign') : null;
  if (wanted === 'on' || wanted === 'off') setRedesign(wanted === 'on');
  return applyRedesign();
}
