// Renders inputs for a block's `options` schema from the catalog.

import { state, blockOf, allArt } from './store.js';
import { h, toggleRow, chips, stepper, nextId, paint } from './ui.js';

const FALLBACK_COLORS = [
  { c: '#F4F2EE', name: 'White' }, { c: '#FFB23F', name: 'Amber' }, { c: '#FF5A36', name: 'Tomato' },
  { c: '#FF7AB6', name: 'Pink' }, { c: '#B98CFF', name: 'Violet' }, { c: '#7CB8FF', name: 'Sky' },
  { c: '#5AD1A0', name: 'Mint' }, { c: '#8C8A84', name: 'Grey' },
];

const LABELS = {
  h24: '24-hour time', colon_blink: 'Blinking colon', work_min: 'Focus minutes', break_min: 'Break minutes',
  callsign: 'Flight or callsign', feed_id: 'Feed', art_id: 'Pixel art', habit_id: 'Habit name', station: 'Airport (ICAO code)',
  which: 'Show', field: 'Show', source: 'Source', event: 'Event', label: 'Label', date: 'Date', text: 'Your text',
  name: 'Icon', style: 'Style', color: 'Color', accent: 'Secondary color', icon_color: 'Icon color',
  face: 'Dial color', city: 'City',
};
const CHOICES = {
  now: 'Now', high: 'High', low: 'Low', hilo: 'High · low', next: 'Next', sunrise: 'Sunrise', sunset: 'Sunset',
  nearby: 'Nearby', follow: 'Follow one', callsign: 'Callsign', route: 'Route', detail: 'Details',
  day: 'Day', year: 'Year', timer: 'Timer', flight: 'Flight', temp_hourly: 'Hourly temp', feed: 'A feed',
  value: 'Value', time: 'Time', title: 'Title', station: 'Station', category: 'Flight rules', wind: 'Wind',
  distance: 'Distance', direction: 'Direction', cpu: 'CPU temp', net: 'Network', short: 'Short', long: 'Long',
};
export const swatchColors = () => state.catalog?.colors || FALLBACK_COLORS;
const human = (s) => String(s).replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
export const optionLabel = (name, spec) => spec?.label || LABELS[name] || human(name);
const choiceLabel = (v) => CHOICES[v] || human(v);

/** Options that only make sense for some values of a sibling option. */
function visible(name, options) {
  if (name === 'callsign') return options.source === 'follow';
  if (name === 'feed_id' && 'source' in options) return options.source === 'feed';
  return true;
}

/**
 * @param {string} blockId
 * @param {object} options  current values (edited in place)
 * @param {(options: object) => void} onChange
 * @param {object} [cfg] {skip: [names], idPrefix}
 */
export function optionsForm(blockId, options, onChange, cfg = {}) {
  const meta = blockOf(blockId);
  const wrap = h('div', { class: 'options' });
  if (!meta) return wrap;
  const skip = new Set(cfg.skip || []);
  const draw = () => {
    wrap.replaceChildren();
    for (const [name, spec] of Object.entries(meta.options || {})) {
      if (skip.has(name) || !visible(name, options)) continue;
      const field = optionField(blockId, name, spec || {}, options, (value, rerender) => {
        options[name] = value;
        onChange(options);
        if (rerender) draw();
      });
      if (field) wrap.append(field);
    }
  };
  draw();
  return wrap;
}

function optionField(blockId, name, spec, options, set) {
  const value = options[name] ?? spec.default;
  const label = optionLabel(name, spec);
  const type = spec.type;

  if (type === 'bool') {
    return h('div', { class: 'card card-rows' }, toggleRow({ title: label, pressed: !!value, onChange: (v) => set(v) }));
  }
  if (type === 'int') {
    const min = Number.isFinite(spec.min) ? spec.min : 0;
    const max = Number.isFinite(spec.max) ? spec.max : 999;
    return h('div', { class: 'card row' },
      h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, label)),
      stepper({ label, value: Number(value) || min, min, max, onChange: (v) => set(v) }));
  }
  if (type === 'enum' || (blockId === 'icon' && name === 'name')) {
    let choices = spec.choices || [];
    if (!choices.length && name === 'name') choices = state.catalog?.icons || [];
    const reflow = name === 'source';
    // Long lists (world clock cities) read better as a dropdown with full names.
    if (choices.length > 12) {
      const id = nextId('opt');
      const select = h('select', { id, class: 'input' },
        choices.map((c) => h('option', { value: c, selected: c === value || null }, spec.labels?.[c] || choiceLabel(c))));
      select.addEventListener('change', () => set(select.value, reflow));
      return h('div', { class: 'field' }, h('label', { class: 'field-label', for: id }, label), select);
    }
    return h('div', { class: 'field' },
      h('div', { class: 'field-label', id: nextId('lbl') }, label),
      chips({ label, value, choices: choices.map((c) => ({ id: c, label: spec.labels?.[c] || choiceLabel(c) })), onChange: (v) => set(v, reflow) }));
  }
  if (type === 'date') {
    const id = nextId('opt');
    const input = h('input', { id, type: 'date', class: 'input', value: value || '' });
    input.addEventListener('change', () => set(input.value));
    return h('div', { class: 'field' }, h('label', { class: 'field-label', for: id }, label), input);
  }
  if (type === 'color') {
    // Color options default to null ("use the block's own color").
    return h('div', { class: 'field' }, h('div', { class: 'field-label' }, label),
      colorPicker({ value, label, allowAuto: true, autoLabel: 'Default color', onChange: (v) => set(v) }));
  }
  if (type === 'art') return artPicker(label, value, set);
  if (type === 'feed') return feedPicker(label, value, set);

  // str (default)
  const id = nextId('opt');
  const upper = ['text', 'label', 'callsign', 'station'].includes(name);
  const input = h('input', {
    id, type: 'text', class: upper ? 'input input-mono' : 'input', value: value ?? '', maxlength: spec.max_len || 64,
    autocomplete: 'off', spellcheck: 'false', autocapitalize: upper ? 'characters' : 'off',
  });
  input.addEventListener('input', () => {
    if (upper) {
      const pos = input.selectionStart;
      input.value = input.value.toUpperCase();
      try { input.setSelectionRange(pos, pos); } catch { /* ignore */ }
    }
    set(input.value);
  });
  return h('div', { class: 'field' }, h('label', { class: 'field-label', for: id }, label), input);
}

/** Round color swatches; optional "Palette" (null) choice and a custom color input. */
export function colorPicker({ value, label = 'Color', onChange, allowAuto = false, autoColor = null, autoLabel = 'Palette color' }) {
  const group = h('div', { class: 'swatches', role: 'group', 'aria-label': label });
  const items = [];
  if (allowAuto) items.push({ c: null, name: autoLabel });
  items.push(...swatchColors());
  const custom = h('input', { type: 'color', class: 'swatch-input', 'aria-label': 'Custom color', value: /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : '#FFB23F' });
  const buttons = items.map((item) => {
    const btn = h('button', { type: 'button', class: item.c ? 'swatch' : 'swatch swatch-auto', 'aria-label': item.name, 'aria-pressed': String(sameColor(item.c, value)) });
    if (item.c) paint(btn, item.c);
    else {
      if (autoColor) paint(btn, autoColor);
      btn.append(h('span', { 'aria-hidden': 'true' }, 'A'));
    }
    btn.addEventListener('click', () => {
      for (const b of buttons) b.setAttribute('aria-pressed', String(b === btn));
      custom.classList.remove('is-on');
      onChange(item.c);
    });
    return btn;
  });
  const isCustom = value && !Array.isArray(value) && !items.some((i) => sameColor(i.c, value));
  custom.classList.toggle('is-on', !!isCustom);
  custom.addEventListener('input', () => {
    for (const b of buttons) b.setAttribute('aria-pressed', 'false');
    custom.classList.add('is-on');
    onChange(custom.value.toUpperCase());
  });
  group.append(...buttons, h('label', { class: 'swatch-custom', title: 'Custom color' }, custom, h('span', { class: 'sr-only' }, 'Custom color')));
  return group;
}

function sameColor(a, b) {
  if (!a || !b) return !a && !b;
  return JSON.stringify(a).toLowerCase() === JSON.stringify(b).toLowerCase();
}

function artPicker(label, value, set) {
  const art = allArt();
  const field = h('div', { class: 'field' }, h('div', { class: 'field-label' }, label));
  if (!art.length) {
    field.append(h('p', { class: 'card-note' }, 'No pixel art yet. ', h('a', { href: '#/draw' }, 'Draw some in the pixel studio'), '.'));
    return field;
  }
  field.append(chips({
    label, value, choices: art.map((a) => ({ id: a.id, label: `${a.name} · ${a.w}×${a.h}${String(a.id).startsWith('builtin-') ? ' · built in' : ''}` })), onChange: (v) => set(v),
  }), h('p', { class: 'card-note' }, h('a', { href: '#/draw' }, 'Draw new art')));
  return field;
}

function feedPicker(label, value, set) {
  const feeds = state.library?.feeds || [];
  const field = h('div', { class: 'field' }, h('div', { class: 'field-label' }, label));
  if (!feeds.length) {
    field.append(h('p', { class: 'card-note' }, 'No feeds yet. ', h('a', { href: '#/device' }, 'Add a JSON feed under Device › Data sources'), '.'));
    return field;
  }
  field.append(chips({ label, value, choices: feeds.map((f) => ({ id: f.id, label: f.name || f.id })), onChange: (v) => set(v) }));
  return field;
}
