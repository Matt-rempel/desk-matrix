// Focus rings belong to keyboard navigation, not taps or automatic dialog focus.
export function usingKeyboard() {
  return document.documentElement.dataset.inputMode === 'keyboard';
}

export function installInputMode() {
  const root = document.documentElement;
  root.dataset.inputMode = 'pointer';
  document.addEventListener('pointerdown', () => { root.dataset.inputMode = 'pointer'; },
    { capture: true, passive: true });
  const navigation = new Set(['Tab', 'Escape', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
    'Home', 'End', 'PageUp', 'PageDown']);
  document.addEventListener('keydown', event => {
    if (!event.altKey && !event.ctrlKey && !event.metaKey && navigation.has(event.key)) {
      root.dataset.inputMode = 'keyboard';
    }
  }, true);
}

export function focusForKeyboard(element) {
  if (usingKeyboard() && element && !element.disabled) element.focus({ preventScroll: true });
}
