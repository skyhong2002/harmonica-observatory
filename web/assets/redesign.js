// The redesigned Observatory interface is the only supported product UI.
export function isRedesign() {
  return true;
}

export function applyRedesign() {
  const root = globalThis.document?.documentElement;
  if (root) root.dataset.redesign = "on";
  return true;
}

export function initializeRedesign() {
  return applyRedesign();
}
