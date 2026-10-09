// Customize a screen: palette, clock knobs, block details, motion, show now.

import { state, findScreen, isBuiltin, familyOf, describeScreen, clone, screenForSave, blockOf, layoutOf,
  defaultOptions, act, saveSettings, subscribe } from './store.js';
import { createMatrix, livePreview } from './matrix.js';
import { h, header, toggleRow, stepper, messageLine, toast, confirmSheet, paint, busy, eyebrow } from './ui.js';
import { optionsForm } from './options.js';
import { saveScreen, showNow, focusControls } from './controls.js';

const TYPES = [
  { id: 'big', layout: 'bigsmall', name: 'Big', note: 'Two-row digits', size: 'lg' },
  { id: 'classic', layout: 'two', name: 'Classic', note: '5 × 7 pixels', size: 'md' },
  { id: 'tiny', layout: 'three', name: 'Tiny', note: 'Three lines', size: 'sm' },
];
const SECOND = [
  { id: 'date', block: 'date', name: 'Date' },
  { id: 'weekday', block: 'weekday', name: 'Weekday' },
  { id: 'temp', block: 'temp', name: 'Weather' },
  { id: 'daybar', block: 'progress', name: 'Day bar', options: { source: 'day' } },
  { id: 'none', block: null, name: 'Nothing' },
];
const MOTION_GLYPHS = { still: '■', breathe: '◐', slide: '→', sparkle: '✦' };

export function render(root, { id, go }) {
  const source = findScreen(id);
  if (!source) {
    root.append(header({ back: '#/', backLabel: '‹ Gallery', title: 'Customize' }),
      h('div', { class: 'empty-state' }, h('p', null, 'That screen no longer exists.'), h('a', { class: 'btn btn-primary', href: '#/' }, 'Back to the gallery')));
    return null;
  }

  const builtin = isBuiltin(source.id);
  const original = clone(source);
  const work = clone(source);
  if (builtin) { work.id = ''; work.based_on = source.id; }
  work.style = { palette: work.style?.palette ?? null, motion: work.style?.motion || 'still' };
  work.slots = (work.slots || []).map((s) => ({ block: s.block, color: s.color ?? null, options: { ...(s.options || {}) } }));
  let savedJSON = JSON.stringify(screenForSave(work));
  let savedId = builtin ? source.id : source.id;
  const family = familyOf(source);
  let lastType = typeFromLayout(work.layout) || 'big';
  let thirdSlot = work.layout === 'three' ? clone(work.slots[2]) : null;

  let nightToggle = null;
  let detailsBody = null;
  const dirty = () => JSON.stringify(screenForSave(work)) !== savedJSON;
  const msg = messageLine();
  const matrix = createMatrix({ pitch: 10, glow: true, label: `${work.name} preview` });
  const live = livePreview(matrix, { onError: (e) => msg.error(e) });
  const bezel = h('div', { class: 'bezel' }, matrix.el);
  const palName = h('span', { class: 'mono-note' });
  const refresh = () => {
    live.update(work);
    const pal = state.catalog.paletteById.get(work.style.palette);
    palName.textContent = pal ? pal.name : 'Custom colors';
    const glow = pal ? (Array.isArray(pal.primary) ? pal.primary[1] || pal.primary[0] : pal.primary) : firstColor(work);
    bezel.style.setProperty('--glow', hexAlpha(glow, 0.28));
  };

  const doneLink = h('a', { class: 'subbar-link subbar-strong', href: '#/' }, 'Done');
  root.append(header({ back: '#/', backLabel: '‹ Gallery', title: 'Customize', action: doneLink }));

  // Name + preview
  const nameInput = h('input', { class: 'title-input', 'aria-label': 'Screen name', value: work.name || '', maxlength: '32', autocomplete: 'off' });
  nameInput.addEventListener('input', () => { work.name = nameInput.value; refresh(); });
  root.append(h('section', { class: 'pad' }, bezel,
    h('div', { class: 'title-row' },
      h('div', { class: 'title-col' }, nameInput, h('div', { class: 'subtle' }, `${describeScreen(source)}${source.source ? ' · ' + source.source : ''}`)),
      palName)));

  // Palette
  const palettes = state.catalog.palettes;
  const palGroup = h('div', { class: 'palette-grid', role: 'group', 'aria-label': 'Palette' });
  const palChoices = [];
  if (builtin || work.based_on) palChoices.push({ id: '__original', name: 'Original' });
  palChoices.push(...palettes.map((p) => ({ id: p.id, name: p.name, color: p.primary })));
  const palButtons = palChoices.map((p) => {
    const dot = h('span', { class: 'pal-dot' });
    if (p.color) paint(dot, p.color);
    else { dot.classList.add('pal-original'); paintOriginal(dot); }
    const btn = h('button', { type: 'button', class: 'pal', 'aria-pressed': 'false', 'aria-label': `${p.name} palette` }, dot, h('span', { class: 'pal-name' }, p.name));
    btn.addEventListener('click', () => { pickPalette(p.id); syncPalette(); });
    btn.dataset.id = p.id;
    return btn;
  });
  function paintOriginal(dot) {
    const base = original.based_on ? findScreen(original.based_on) : original;
    const colors = (base?.slots || []).map((s) => s.color).filter(Boolean);
    const pal = state.catalog.paletteById.get(base?.style?.palette);
    paint(dot, pal ? pal.primary : colors.length > 1 ? [colors[0], colors[1]] : colors[0] || '#F4F2EE');
  }
  function pickPalette(pid) {
    if (pid === '__original') {
      const base = (builtin ? original : findScreen(original.based_on)) || original;
      work.style.palette = base.style?.palette ?? null;
      work.slots.forEach((slot, i) => {
        const match = base.slots?.[i] && base.slots[i].block === slot.block ? base.slots[i] : base.slots?.find((s) => s.block === slot.block);
        slot.color = match ? match.color ?? null : null;
      });
    } else {
      work.style.palette = pid;
      for (const slot of work.slots) slot.color = null;
    }
    refresh();
  }
  function syncPalette() {
    const current = work.style.palette;
    const isOriginal = (builtin || work.based_on) && isOriginalStyle();
    for (const b of palButtons) {
      const on = b.dataset.id === '__original' ? isOriginal : (!isOriginal && b.dataset.id === current && work.slots.every((s) => s.color === null));
      b.setAttribute('aria-pressed', String(on));
    }
  }
  function isOriginalStyle() {
    const base = (builtin ? original : findScreen(original.based_on)) || original;
    if ((base.style?.palette ?? null) !== work.style.palette) return false;
    return work.slots.every((s, i) => (base.slots?.[i]?.color ?? null) === s.color);
  }
  palGroup.append(...palButtons);
  root.append(h('section', { class: 'block', 'aria-labelledby': 'pal-h' }, eyebrow('Palette', 'pal-h'), palGroup));
  syncPalette();

  // Clock knobs
  if (family === 'clock' && work.slots[0]?.block === 'time') {
    root.append(clockSections());
  }

  // Details: options of every slot (except those handled by the clock knobs).
  const details = detailsSection();
  if (details) root.append(details);

  // Timer / habit
  const focusWrap = h('div');
  const renderFocus = () => {
    const target = { ...work, id: savedId };
    const c = focusControls(target);
    focusWrap.replaceChildren();
    if (c) focusWrap.append(h('section', { class: 'block', 'aria-labelledby': 'focus-h' }, eyebrow(c.getAttribute('aria-label') === 'Habit' ? 'Habit' : 'Timer', 'focus-h'), h('div', { class: 'card' }, c)));
  };
  renderFocus();
  root.append(focusWrap);

  // Motion
  const motionGroup = h('div', { class: 'grid-4', role: 'group', 'aria-label': 'Motion' },
    state.catalog.motions.map((m) => {
      const btn = h('button', { type: 'button', class: 'tile-btn', 'aria-pressed': String(work.style.motion === m.id) },
        h('span', { class: 'tile-glyph', 'aria-hidden': 'true' }, MOTION_GLYPHS[m.id] || '•'), h('span', null, m.name));
      btn.addEventListener('click', () => {
        work.style.motion = m.id;
        for (const b of motionGroup.children) b.setAttribute('aria-pressed', String(b === btn));
        refresh();
      });
      return btn;
    }));
  root.append(h('section', { class: 'block', 'aria-labelledby': 'mo-h' }, eyebrow('Motion', 'mo-h'), motionGroup));

  // Shows for
  let seconds = lineupSeconds(source.id) || 20;
  const initialSeconds = seconds;
  root.append(h('section', { class: 'block card row' },
    h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, 'Shows for'), h('div', { class: 'row-detail' }, 'Each time it comes up in the lineup')),
    stepper({ label: 'seconds', value: seconds, min: 5, max: 300, step: 5, format: (v) => `${v} s`, onChange: (v) => { seconds = v; } })));

  // Actions
  const showBtn = h('button', { type: 'button', class: 'btn btn-primary' }, 'Show now');
  const addBtn = h('button', { type: 'button', class: 'btn btn-secondary' }, 'Add to lineup');
  root.append(h('div', { class: 'btn-row pad-x' }, showBtn, addBtn),
    h('p', { class: 'foot-note' }, 'Changes preview here first. Nothing reaches the matrix until you tap Show now.'),
    h('div', { class: 'pad-x' }, msg));

  if (!builtin) {
    const del = h('button', { type: 'button', class: 'btn btn-danger-quiet' }, 'Delete screen');
    del.addEventListener('click', async () => {
      if (!(await confirmSheet({ title: `Delete “${work.name}”?`, text: 'It is removed from the gallery and the lineup. This can’t be undone.' }))) return;
      try { await act('delete_screen', { screen_id: savedId }); toast('Screen deleted.'); go('#/'); } catch (error) { msg.error(error); }
    });
    root.append(h('div', { class: 'btn-row pad-x' },
      h('a', { class: 'btn btn-secondary', href: `#/build/${encodeURIComponent(source.id)}` }, 'Edit blocks'), del));
  }

  async function persist() {
    if (!String(work.name || '').trim()) throw new Error('Give the screen a name.');
    if (dirty()) {
      const newId = await saveScreen({ ...work, id: work.id || '' });
      if (!newId) throw new Error('The screen was saved but could not be found.');
      work.id = newId;
      savedId = newId;
      savedJSON = JSON.stringify(screenForSave(work));
      history.replaceState(null, '', `#/customize/${encodeURIComponent(newId)}`);
    }
    if (seconds !== initialSeconds) await updateLineupSeconds(savedId, seconds);
    return savedId;
  }

  showBtn.addEventListener('click', async () => {
    busy(showBtn, true, 'Sending…');
    msg.show('');
    try {
      const sid = await persist();
      await showNow(sid);
      msg.show(`${work.name} is on the matrix now.`);
      toast(`${work.name} is on the matrix.`);
    } catch (error) { msg.error(error); }
    finally { busy(showBtn, false); }
  });
  addBtn.addEventListener('click', async () => {
    busy(addBtn, true, 'Saving…');
    try {
      const sid = await persist();
      go(`#/lineup?add=${encodeURIComponent(sid)}&seconds=${seconds}`);
    } catch (error) { msg.error(error); busy(addBtn, false); }
  });

  refresh();
  live.now(work);

  const unsubscribe = subscribe((what) => {
    if (what === 'library') renderFocus();
    if (what === 'settings' && nightToggle) nightToggle.setAttribute('aria-pressed', String(!!state.settings?.night_palette));
  });

  // ---- clock helpers -------------------------------------------------------

  function clockSections() {
    const frag = h('div');
    const typeGroup = h('div', { class: 'grid-3', role: 'group', 'aria-label': 'Type' });
    const secondGroup = h('div', { class: 'chips', role: 'group', 'aria-label': 'Second line' });
    const redraw = () => {
      const type = work.layout === 'full' ? lastType : typeFromLayout(work.layout);
      for (const b of typeGroup.children) b.setAttribute('aria-pressed', String(b.dataset.id === type));
      const sec = secondFromSlots();
      for (const b of secondGroup.children) b.setAttribute('aria-pressed', String(b.dataset.id === sec));
    };
    for (const t of TYPES) {
      if (!layoutOf(t.layout)) continue;
      const btn = h('button', { type: 'button', class: 'type-btn', dataset: { id: t.id } },
        h('span', { class: `type-sample type-${t.size}`, 'aria-hidden': 'true' }, '10:24'),
        h('span', { class: 'type-name' }, t.name), h('span', { class: 'type-note' }, t.note));
      btn.addEventListener('click', () => { setType(t.id); redraw(); refresh(); });
      typeGroup.append(btn);
    }
    for (const s of SECOND) {
      if (s.block && !blockOf(s.block)) continue;
      const btn = h('button', { type: 'button', class: 'chip', dataset: { id: s.id } }, s.name);
      btn.addEventListener('click', () => { setSecond(s); renderDetails(); redraw(); refresh(); });
      secondGroup.append(btn);
    }
    redraw();

    const time = work.slots[0];
    const timeMeta = blockOf('time');
    const rows = h('div', { class: 'card card-rows' }, h('h2', { class: 'eyebrow card-eyebrow', id: 'clock-h' }, 'Clock'));
    if (!timeMeta || 'h24' in (timeMeta.options || {})) {
      rows.append(toggleRow({ title: '24-hour time', pressed: (time.options.h24 ?? timeMeta?.options?.h24?.default ?? true) !== false,
        onChange: (v) => { time.options.h24 = v; refresh(); } }));
    }
    if (!timeMeta || 'colon_blink' in (timeMeta.options || {})) {
      rows.append(toggleRow({ title: 'Blinking colon', pressed: !!(time.options.colon_blink ?? timeMeta?.options?.colon_blink?.default),
        onChange: (v) => { time.options.colon_blink = v; refresh(); } }));
    }
    const s = state.settings || {};
    const nightRow = toggleRow({
      title: 'Night look',
      detail: `Switch to Night red from ${s.night_start || '22:00'} to ${s.night_end || '07:00'} (all screens)`,
      pressed: !!s.night_palette,
      onChange: async (v) => {
        try { await saveSettings({ night_palette: v }); toast(v ? 'Night look on.' : 'Night look off.'); }
        catch (error) { nightToggle.setAttribute('aria-pressed', String(!v)); msg.error(error); }
      },
    });
    nightToggle = nightRow.querySelector('.switch');
    rows.append(nightRow);

    frag.append(
      h('section', { class: 'block', 'aria-labelledby': 'type-h' }, eyebrow('Type', 'type-h'), typeGroup),
      h('section', { class: 'block', 'aria-labelledby': 'l2-h' }, eyebrow('Second line', 'l2-h'), secondGroup),
      h('section', { class: 'block', 'aria-labelledby': 'clock-h' }, rows));
    return frag;
  }

  function secondFromSlots() {
    if (work.slots.length < 2) return 'none';
    const b = work.slots[1];
    if (b.block === 'progress') return 'daybar';
    if (b.block === 'none') return 'none';
    const hit = SECOND.find((s) => s.block === b.block);
    return hit ? hit.id : null;
  }

  function setType(typeId) {
    lastType = typeId;
    if (secondFromSlots() === 'none' && work.layout === 'full') return; // stays one big line
    applyLayout(TYPES.find((t) => t.id === typeId).layout);
  }

  function setSecond(choice) {
    if (!choice.block) {
      if (work.layout === 'three') thirdSlot = clone(work.slots[2]);
      if (layoutOf('full')) { work.layout = 'full'; work.slots = [work.slots[0]]; }
      else work.slots = work.slots.map((s, i) => (i === 0 ? s : { block: 'none', color: null, options: {} }));
      return;
    }
    const prev = work.slots[1];
    const slot = { block: choice.block, color: prev ? prev.color : null, options: { ...defaultOptions(choice.block), ...(choice.options || {}) } };
    if (work.layout === 'full') applyLayout(TYPES.find((t) => t.id === lastType).layout);
    work.slots[1] = slot;
  }

  function applyLayout(layoutId) {
    const layout = layoutOf(layoutId);
    if (!layout) return;
    if (work.layout === 'three') thirdSlot = clone(work.slots[2]);
    const second = work.slots[1] && work.slots[1].block !== 'none' ? work.slots[1] : { block: 'date', color: null, options: defaultOptions('date') };
    const slots = [work.slots[0], second];
    if (layout.slots.length >= 3) slots.push(thirdSlot || { block: blockOf('sun_time') ? 'sun_time' : 'weekday', color: null, options: defaultOptions(blockOf('sun_time') ? 'sun_time' : 'weekday') });
    work.layout = layoutId;
    work.slots = slots.slice(0, layout.slots.length);
    while (work.slots.length < layout.slots.length) work.slots.push({ block: 'none', color: null, options: {} });
    renderDetails();
  }

  // ---- details -------------------------------------------------------------

  function detailsSection() {
    detailsBody = h('div', { class: 'details' });
    const sec = h('section', { class: 'block', 'aria-labelledby': 'det-h' }, eyebrow('Details', 'det-h'), detailsBody);
    renderDetails();
    sec.hidden = !detailsBody.childElementCount;
    detailsSection.el = sec;
    return sec;
  }
  function renderDetails() {
    if (!detailsBody) return;
    detailsBody.replaceChildren();
    const layout = layoutOf(work.layout);
    work.slots.forEach((slot, i) => {
      const meta = blockOf(slot.block);
      if (!meta || !Object.keys(meta.options || {}).length) return;
      const skip = family === 'clock' && i === 0 && slot.block === 'time' ? ['h24', 'colon_blink'] : [];
      if (family === 'clock' && i === 1 && slot.block === 'progress') skip.push('source');
      const names = Object.keys(meta.options).filter((n) => !skip.includes(n));
      if (!names.length) return;
      const where = layout?.slots[i]?.where || `Slot ${i + 1}`;
      detailsBody.append(h('div', { class: 'detail-group' },
        h('h3', { class: 'detail-title' }, `${meta.name}`, h('span', { class: 'subtle' }, ` · ${where}`)),
        optionsForm(slot.block, slot.options, () => refresh(), { skip })));
    });
    if (detailsSection.el) detailsSection.el.hidden = !detailsBody.childElementCount;
  }

  return () => { unsubscribe(); live.cancel(); };
}

function typeFromLayout(layout) {
  const t = TYPES.find((x) => x.layout === layout);
  return t ? t.id : null;
}

function firstColor(screen) {
  const c = screen.slots.find((s) => s.color)?.color;
  return c || '#FFB23F';
}

function hexAlpha(color, alpha) {
  const c = Array.isArray(color) ? color[0] : color;
  if (!/^#[0-9a-fA-F]{6}$/.test(c || '')) return `rgba(255,178,63,${alpha})`;
  const n = parseInt(c.slice(1), 16);
  return `rgba(${n >> 16},${(n >> 8) & 255},${n & 255},${alpha})`;
}

function lineupSeconds(screenId) {
  const lu = state.library?.lineup;
  if (!lu) return null;
  const all = [...lu.always, ...lu.moments.flatMap((m) => m.screens)];
  const hit = all.find((it) => it.screen_id === screenId);
  return hit ? hit.seconds : null;
}

async function updateLineupSeconds(screenId, seconds) {
  const lu = clone(state.library.lineup);
  let changed = false;
  for (const list of [lu.always, ...lu.moments.map((m) => m.screens)]) {
    for (const it of list) if (it.screen_id === screenId && it.seconds !== seconds) { it.seconds = seconds; changed = true; }
  }
  if (changed) await act('save_lineup', { lineup: lu });
}
