// "New interface" beta switch. Off by default; the choice lives in this
// browser only. While on, <html data-redesign="on"> scopes redesign.css and
// the modules render the redesigned markup. `?redesign=on|off` sets it too,
// so a preview link can open either version.
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
