// Renders inputs for a block's `options` schema from the catalog.

import { state, blockOf, allArt } from './store.js';
import { h, toggleRow, chips, stepper, nextId, paint } from './ui.js';
import { api } from './api.js';
import { nearbyPicker } from './nearby.js';
import { fontControls } from './fonts.js';
import { teamPicker, followedTeams } from './nhl-teams.js';
import { flightIdentity, airlineFor } from './airlines.js';

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

function clockSelection(options) {
  const legacy = { minute_track: 'minutes', seconds_track: 'seconds' }[options.design];
  return { design: legacy ? 'tracker' : options.design || 'platform',
    track_unit: options.track_unit ?? legacy ?? 'minutes' };
}

/** Options that only make sense for some values of a sibling option. */
export function optionVisible(blockId, name, options) {
  if (blockId === 'clock_design') {
    const { design, track_unit: unit } = clockSelection(options);
    if (name === 'track_unit') return design === 'tracker';
    if (['font', 'font_family', 'font_size'].includes(name)) return design === 'tracker';
    if (name === 'h24') return !['month_map', 'date_poster', 'word_glow'].includes(design);
    if (name === 'show_date') return ['platform', 'station', 'time_stack', 'orbit', 'tracker', 'clockwork', 'minute_runner'].includes(design);
    if (name === 'show_seconds') return ['station', 'orbit', 'minute_runner'].includes(design);
    if (name === 'seconds_display') return (design === 'tracker' && unit === 'minutes') || ['platform', 'time_stack', 'clockwork', 'perpetual_card', 'week_strip'].includes(design);
    if (name === 'animate') return ['platform', 'station', 'orbit', 'tracker', 'clockwork', 'minute_runner'].includes(design);
  }
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
      if (spec.hidden) continue;
      if (blockId === 'nhl' && name === 'team') continue; // superseded by the multi-team picker
      if (name === 'font_family' || name === 'font_size') continue;
      if (skip.has(name) || !optionVisible(blockId, name, options)) continue;
      if (name === 'font' && meta.options.font_family) {
        wrap.append(fontControls(options, onChange));
        if (blockId === 'clock_design') wrap.append(h('p', { class: 'foot-note' },
          'Font and size change the time only; the ruler stays readable.'));
        continue;
      }
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
  const value = blockId === 'clock_design' && ['design', 'track_unit'].includes(name)
    ? clockSelection(options)[name] : options[name] ?? spec.default;
  const label = optionLabel(name, spec);
  const type = spec.type;

  if (type === 'teams') {
    return h('div', { class: 'field' }, teamPicker({ value: followedTeams(options),
      detail: 'Live games play first. Multiple games rotate every 10 seconds; a shared matchup appears once.',
      onChange: (teams) => set(teams) }),
    h('p', { class: 'card-note' }, 'Live games first. Multiple games rotate every 10 seconds.'));
  }

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
    const reflow = name === 'source' || name === 'display' || name === 'design' || name === 'track_unit';
    // Long lists (world clock cities) read better as a dropdown with full names.
    if (choices.length > 12 || spec.control === 'select') {
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
  if (name === 'callsign') input.setAttribute('placeholder', 'WS2231 or WJA2231');
  input.addEventListener('input', () => {
    if (upper) {
      const pos = input.selectionStart;
      input.value = input.value.toUpperCase();
      if (name === 'callsign') input.value = input.value.replace(/[\s-]+/g, '');
      try { input.setSelectionRange(pos, pos); } catch { /* ignore */ }
    }
    set(input.value);
  });
  if (name === 'callsign') {
    const identity = h('div');
    const identify = callsign => {
      identity.replaceChildren();
      if (airlineFor({callsign})) identity.append(flightIdentity({callsign}));
    };
    identify(input.value);
    const helpId = nextId('flight-help');
    const result = h('p', { class: 'foot-note', role: 'status', 'aria-live': 'polite' });
    const button = h('button', { type: 'button', class: 'btn btn-small btn-secondary' }, 'Check flight');
    input.setAttribute('aria-describedby', helpId);
    const picker = nearbyPicker({ distanceUnit: state.settings?.distance_unit,
      selected: () => input.value,
      onChoose: (callsign) => {
        input.value = callsign;
        identify(callsign);
        result.textContent = `Selected ${callsign}. Save, then tap Show now to put it on the display.`;
        set(callsign);
      } });
    input.addEventListener('input', () => { result.textContent = ''; });
    input.addEventListener('input', () => identify(input.value));
    input.addEventListener('input', picker.syncSelection);
    button.addEventListener('click', async () => {
      const callsign = input.value.replace(/[\s-]+/g, '').toUpperCase();
      if (!/^[A-Z0-9]{2,10}$/.test(callsign) || !/[A-Z]/.test(callsign)) {
        result.textContent = 'Enter a flight number with its airline code, such as WS2231.';
        return;
      }
      button.disabled = true;
      result.textContent = `Looking for ${callsign}…`;
      try {
        for (let attempt = 0; attempt < 40; attempt += 1) {
          if (!input.isConnected || input.value !== callsign) return;
          const checked = await api.checkFlight(callsign);
          if (!input.isConnected || input.value !== callsign) return;
          const resolved = checked.resolved || callsign;
          identify(resolved);
          if (checked.state === 'found') {
            result.textContent = `Live position found${resolved !== callsign ? ` as ${resolved}` : ''}. Save, then tap Show now to put it on the display.`;
            set(input.value);
            return;
          }
          if (checked.state === 'not_seen') {
            result.textContent = `No live position in our feed for ${resolved}. For a regional or codeshare flight, try the operating callsign shown by your tracker. A scheduled flight may not be transmitting yet.`;
            set(input.value);
            return;
          }
          if (checked.state === 'error') {
            result.textContent = 'The flight feed could not be reached. Try again shortly.';
            set(input.value);
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 1000));
        }
        result.textContent = 'Still checking. Make sure the Pi display service is running, then try again.';
      } catch (error) {
        result.textContent = error.message;
      } finally {
        button.disabled = false;
      }
    });
    return h('div', { class: 'field' }, picker.el, h('label', { class: 'field-label', for: id }, label), input, identity,
      h('p', { class: 'foot-note', id: helpId }, 'Flight numbers (WS2231) and transmitted callsigns (WJA2231) are accepted. Regional flights can use a different operator code. Check the live feed before saving.'),
      button, result);
  }
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
