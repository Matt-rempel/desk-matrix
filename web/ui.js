// Small DOM toolkit. Everything is built with createElement; dynamic styles go
// through the CSSOM (el.style / custom properties), never style="" attributes.

export function h(tag, props = null, ...children) {
  const el = document.createElement(tag);
  if (props) {
    for (const [name, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (name === 'class') el.className = value;
      else if (name === 'text') el.textContent = value;
      else if (name === 'on') {
        for (const [type, fn] of Object.entries(value)) el.addEventListener(type, fn);
      } else if (name === 'css') {
        for (const [prop, v] of Object.entries(value)) {
          if (prop.startsWith('--')) el.style.setProperty(prop, v);
          else el.style[prop] = v;
        }
      } else if (name === 'dataset') Object.assign(el.dataset, value);
      else if (name === 'value' || name === 'checked' || name === 'disabled' || name === 'hidden'
        || name === 'selected' || name === 'htmlFor' || name === 'tabIndex') el[name] = value;
      else if (name === 'style') throw new Error('Use css: {...} instead of style attributes');
      else el.setAttribute(name, value === true ? '' : String(value));
    }
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children) {
    if (child === null || child === undefined || child === false) continue;
    if (Array.isArray(child)) append(el, child);
    else if (child instanceof Node) el.append(child);
    else el.append(document.createTextNode(String(child)));
  }
}

let uid = 0;
export function nextId(prefix = 'id') { uid += 1; return `${prefix}-${uid}`; }

/** iOS-style switch. Uses a real button with aria-pressed. */
export function toggle({ label, pressed = false, onChange, describedBy, disabled = false }) {
  const btn = h('button', {
    type: 'button', class: 'switch', 'aria-pressed': String(!!pressed), 'aria-label': label,
    'aria-describedby': describedBy, disabled,
  }, h('i', { 'aria-hidden': 'true' }));
  btn.addEventListener('click', () => {
    const next = btn.getAttribute('aria-pressed') !== 'true';
    btn.setAttribute('aria-pressed', String(next));
    if (onChange) onChange(next);
  });
  return btn;
}

/** A labelled row with a switch on the right. */
export function toggleRow({ title, detail, pressed, onChange, disabled }) {
  const detailId = detail ? nextId('detail') : null;
  return h('div', { class: 'row' },
    h('div', { class: 'row-text' },
      h('div', { class: 'row-title' }, title),
      detail ? h('div', { class: 'row-detail', id: detailId }, detail) : null),
    toggle({ label: title, pressed, onChange, describedBy: detailId, disabled }));
}

/** Pressable chip group; `choices` = [{id, label}] */
export function chips({ choices, value, onChange, label, className = 'chips', chipClass = 'chip', render }) {
  const group = h('div', { class: className, role: 'group', 'aria-label': label });
  const buttons = choices.map((choice) => {
    const btn = h('button', {
      type: 'button', class: chipClass, 'aria-pressed': String(choice.id === value),
      'aria-label': choice.ariaLabel, disabled: choice.disabled,
    }, render ? render(choice) : choice.label);
    btn.addEventListener('click', () => {
      for (const b of buttons) b.setAttribute('aria-pressed', String(b === btn));
      onChange(choice.id);
    });
    return btn;
  });
  group.append(...buttons);
  return group;
}

/** − value + stepper. */
export function stepper({ label, value, min = 0, max = 999, step = 1, format = (v) => String(v), onChange }) {
  let current = Number(value) || 0;
  const out = h('output', { class: 'stepper-value', 'aria-live': 'polite' }, format(current));
  const less = h('button', { type: 'button', class: 'stepper-btn', 'aria-label': `Less ${label}` }, '−');
  const more = h('button', { type: 'button', class: 'stepper-btn', 'aria-label': `More ${label}` }, '+');
  const sync = () => {
    out.textContent = format(current);
    less.disabled = current <= min;
    more.disabled = current >= max;
  };
  const change = (delta) => {
    const next = Math.min(max, Math.max(min, current + delta));
    if (next === current) return;
    current = next;
    sync();
    onChange(current);
  };
  less.addEventListener('click', () => change(-step));
  more.addEventListener('click', () => change(step));
  sync();
  const el = h('div', { class: 'stepper', role: 'group', 'aria-label': label }, less, out, more);
  el.setValue = (v) => { current = v; sync(); };
  return el;
}

/** Section heading in the mono eyebrow style. */
export function eyebrow(text, id, tag = 'h2') {
  return h(tag, { class: 'eyebrow', id }, text);
}

/** Inline message area (role=status or alert). */
export function messageLine(className = 'msg') {
  const el = h('p', { class: className, role: 'status', 'aria-live': 'polite' });
  el.show = (text, kind = 'ok') => {
    el.textContent = text || '';
    el.classList.toggle('is-error', kind === 'error');
    el.classList.toggle('is-ok', kind === 'ok' && !!text);
  };
  el.error = (error) => el.show(error && error.message ? error.message : String(error || 'Something went wrong'), 'error');
  return el;
}

let toastTimer = 0;
export function toast(text, kind = 'ok') {
  const el = document.getElementById('toast');
  if (!el) return;
  el.textContent = text;
  el.classList.toggle('is-error', kind === 'error');
  el.classList.add('is-visible');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('is-visible'), kind === 'error' ? 5000 : 2600);
}

/** Bottom sheet built on <dialog> (focus trap + Esc for free). */
export function sheet({ title, body, onClose }) {
  const titleId = nextId('sheet-title');
  const close = h('button', { type: 'button', class: 'link-btn' }, 'Close');
  const dialog = h('dialog', { class: 'sheet', 'aria-labelledby': titleId },
    h('div', { class: 'sheet-head' }, h('h2', { id: titleId, class: 'sheet-title' }, title), close),
    h('div', { class: 'sheet-body' }, body));
  const shut = () => { if (dialog.open) dialog.close(); };
  close.addEventListener('click', shut);
  dialog.addEventListener('click', (event) => { if (event.target === dialog) shut(); });
  dialog.addEventListener('close', () => { dialog.remove(); if (onClose) onClose(); });
  document.body.append(dialog);
  dialog.showModal();
  return { dialog, close: shut };
}

/** Confirm via a sheet; resolves true/false. */
export function confirmSheet({ title, text, confirmLabel = 'Delete', danger = true }) {
  return new Promise((resolve) => {
    let answer = false;
    const yes = h('button', { type: 'button', class: danger ? 'btn btn-danger' : 'btn btn-primary' }, confirmLabel);
    const no = h('button', { type: 'button', class: 'btn btn-secondary' }, 'Cancel');
    const s = sheet({
      title,
      body: [h('p', { class: 'sheet-text' }, text), h('div', { class: 'btn-row' }, no, yes)],
      onClose: () => resolve(answer),
    });
    yes.addEventListener('click', () => { answer = true; s.close(); });
    no.addEventListener('click', () => s.close());
    no.focus();
  });
}

/** Swatch background for a color or a two-color gradient. */
export function paint(el, color) {
  if (Array.isArray(color)) {
    el.style.background = `linear-gradient(135deg, ${color[0]}, ${color[1] || color[0]})`;
  } else if (color) {
    el.style.background = color;
  }
  return el;
}

export function busy(button, on, text) {
  if (on) {
    button.dataset.label = button.textContent;
    button.disabled = true;
    if (text) button.textContent = text;
  } else {
    button.disabled = false;
    if (button.dataset.label) button.textContent = button.dataset.label;
  }
}

export function header({ back, backLabel, title, action }) {
  return h('header', { class: 'subbar' },
    h('a', { class: 'subbar-link', href: back }, backLabel),
    h('h1', { class: 'subbar-title' }, title),
    action || h('span', { class: 'subbar-spacer', 'aria-hidden': 'true' }));
}

/**
 * Two-column layout for wide screens: everything up to and including `last`
 * (after the sticky sub-bar) goes in the side column, the rest in the main one.
 * Both wrappers use `display: contents` on phones, so order and sticky
 * positioning are unchanged there.
 */
export function splitLayout(root, last, kind) {
  root.classList.add('split', `split-${kind}`);
  const side = h('div', { class: 'split-side' });
  const main = h('div', { class: 'split-main' });
  let target = side;
  for (const child of [...root.children]) {
    if (child.classList.contains('subbar')) continue;
    target.append(child);
    if (child === last) target = main;
  }
  root.append(side, main);
}
