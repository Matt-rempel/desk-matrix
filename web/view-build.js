// Build your own: layout, slots, blocks, block options and colors.

import { state, findScreen, isBuiltin, clone, layoutOf, blockOf, defaultOptions, act, customs } from './store.js';
import { createMatrix, livePreview } from './matrix.js';
import { h, header, messageLine, toast, confirmSheet, busy, eyebrow, chips, paint } from './ui.js';
import { optionsForm, colorPicker } from './options.js';
import { saveScreen, showNow } from './controls.js';

const LETTERS = 'ABCDEFGH';
const DEFAULTS = {
  icon2: [['weather_icon', '#FFB23F'], ['time', '#F4F2EE'], ['temp', '#7CB8FF']],
  two: [['time', '#F4F2EE'], ['date', '#FFB23F']],
  bigsmall: [['time', '#F4F2EE'], ['date', '#8C8A84']],
  three: [['time', '#F4F2EE'], ['temp', '#7CB8FF'], ['sun_time', '#FFB23F']],
  split: [['icon', '#FF7AB6'], ['countdown', '#F4F2EE']],
  full: [['text', '#FFB23F']],
};

export function render(root, { id, go }) {
  const existing = id ? findScreen(id) : null;
  const editing = existing && !isBuiltin(existing.id);
  let work;
  if (existing) {
    work = clone(existing);
    if (!editing) { work.id = ''; work.based_on = existing.id; }
  } else {
    const layout = layoutOf('icon2') ? 'icon2' : state.catalog.layouts[0]?.id;
    work = { id: '', name: newName(), layout, slots: [], style: { palette: null, motion: 'still' }, based_on: null };
    work.slots = defaultSlots(layout);
  }
  work.style = { palette: work.style?.palette ?? null, motion: work.style?.motion || 'still' };
  work.slots = work.slots.map((s) => ({ block: s.block, color: s.color ?? null, options: { ...(s.options || {}) } }));
  let sel = 0;

  const msg = messageLine();
  const saveLink = h('button', { type: 'button', class: 'subbar-link subbar-strong' }, 'Save');
  root.append(header({ back: editing ? `#/customize/${encodeURIComponent(work.id)}` : '#/', backLabel: 'Cancel', title: editing ? 'Edit screen' : 'New screen', action: saveLink }));

  // Preview with slot outline
  const matrix = createMatrix({ pitch: 10, glow: true, label: 'Screen preview' });
  const live = livePreview(matrix, { onError: (e) => msg.error(e) });
  const outline = h('div', { class: 'slot-outline', 'aria-hidden': 'true' });
  const host = h('div', { class: 'overlay-host' }, matrix.el, outline);
  const nameInput = h('input', { id: 'sname', class: 'input', value: work.name, maxlength: '32', autocomplete: 'off', required: true });
  nameInput.addEventListener('input', () => { work.name = nameInput.value; });
  root.append(h('section', { class: 'pad' }, h('div', { class: 'bezel' }, host),
    h('div', { class: 'inline-field' }, h('label', { for: 'sname', class: 'eyebrow' }, 'Name'), nameInput)));

  // 1 · Layout
  const layoutGrid = h('div', { class: 'grid-3', role: 'group', 'aria-label': 'Layout' });
  root.append(h('section', { class: 'block', 'aria-labelledby': 'lay-h' }, eyebrow('1 · Layout', 'lay-h'), layoutGrid));
  // 2 · Slots
  const slotList = h('div', { class: 'slot-list', role: 'group', 'aria-label': 'Slots' });
  root.append(h('section', { class: 'block', 'aria-labelledby': 'slot-h' }, eyebrow('2 · Slots', 'slot-h'), slotList));
  // 3 · Block
  const blockHead = eyebrow('3 · Block', 'blk-h');
  const blockGrid = h('div', { class: 'grid-3 block-grid', role: 'group', 'aria-labelledby': 'blk-h' });
  const tooBig = h('details', { class: 'too-big' });
  const optionsHost = h('div', { class: 'options-host' });
  root.append(h('section', { class: 'block', 'aria-labelledby': 'blk-h' },
    h('div', { class: 'head-row' }, blockHead, h('span', { class: 'subtle' }, 'Text resizes to fit')), blockGrid, tooBig, optionsHost));
  // 4 · Color
  const colorHead = eyebrow('4 · Color', 'col-h');
  const colorHost = h('div');
  root.append(h('section', { class: 'block', 'aria-labelledby': 'col-h' }, colorHead, colorHost));
  // 5 · Look
  const lookHost = h('div');
  root.append(h('section', { class: 'block', 'aria-labelledby': 'look-h' }, eyebrow('5 · Palette & motion', 'look-h'), lookHost));

  const saveShow = h('button', { type: 'button', class: 'btn btn-primary' }, 'Save & show now');
  root.append(h('div', { class: 'btn-row pad-x' }, saveShow, h('a', { class: 'btn btn-secondary btn-auto', href: '#/draw' }, 'Draw an icon')),
    h('div', { class: 'pad-x' }, msg));
  if (editing) {
    const del = h('button', { type: 'button', class: 'btn btn-danger-quiet' }, 'Delete screen');
    del.addEventListener('click', async () => {
      if (!(await confirmSheet({ title: `Delete “${work.name}”?`, text: 'It is removed from the gallery and the lineup. This can’t be undone.' }))) return;
      try { await act('delete_screen', { screen_id: work.id }); toast('Screen deleted.'); go('#/'); } catch (error) { msg.error(error); }
    });
    root.append(h('div', { class: 'btn-row pad-x' }, del));
  }

  function rects() { return layoutOf(work.layout)?.slots || []; }
  function fits(meta, r) { return meta.min_w <= r.w && meta.min_h <= r.h; }

  function renderLayouts() {
    layoutGrid.replaceChildren(...state.catalog.layouts.map((l) => {
      const on = l.id === work.layout;
      const mini = h('span', { class: 'mini-layout', 'aria-hidden': 'true' }, l.slots.map((r, i) => h('i', {
        class: on ? (i === sel ? 'sel' : 'on') : '',
        css: { left: `${(r.x / 32) * 100}%`, top: `${(r.y / 16) * 100}%`, width: `${(r.w / 32) * 100}%`, height: `${(r.h / 16) * 100}%` },
      })));
      const btn = h('button', { type: 'button', class: 'layout-btn', 'aria-pressed': String(on) }, mini, h('span', null, l.name));
      btn.addEventListener('click', () => { switchLayout(l.id); });
      return btn;
    }));
  }

  function switchLayout(layoutId) {
    const layout = layoutOf(layoutId);
    const old = work.slots;
    work.layout = layoutId;
    work.slots = layout.slots.map((r, i) => old[i] ? old[i] : { block: 'none', color: null, options: {} });
    sel = Math.min(sel, work.slots.length - 1);
    renderAll();
  }

  function renderSlots() {
    const rs = rects();
    slotList.replaceChildren(...work.slots.map((slot, i) => {
      const meta = blockOf(slot.block);
      const r = rs[i] || { w: 0, h: 0, where: '' };
      const ok = !meta || fits(meta, r);
      const dot = h('i', { class: 'slot-color' });
      paint(dot, slot.color || paletteColor(i));
      const btn = h('button', { type: 'button', class: 'slot-btn', 'aria-pressed': String(i === sel) },
        h('span', { class: 'slot-letter', 'aria-hidden': 'true' }, LETTERS[i]),
        h('span', { class: 'slot-text' },
          h('span', { class: 'slot-name' }, `${meta ? meta.name : slot.block}`, h('span', { class: 'sr-only' }, ` in slot ${LETTERS[i]}`)),
          h('span', { class: 'slot-where' }, `${r.where} · ${r.w}×${r.h}${ok ? '' : ' · too small for this block'}`)),
        dot);
      if (!ok) btn.classList.add('is-warn');
      btn.addEventListener('click', () => { sel = i; renderAll(); });
      return btn;
    }));
  }

  function paletteColor(i) {
    const pal = state.catalog.paletteById.get(work.style.palette);
    if (!pal) return '#F4F2EE';
    return i === 0 ? pal.primary : pal.secondary;
  }

  function renderBlocks() {
    const r = rects()[sel];
    const slot = work.slots[sel];
    blockHead.textContent = `3 · Block for slot ${LETTERS[sel]}`;
    const all = state.catalog.blocks;
    const good = all.filter((b) => fits(b, r));
    const bad = all.filter((b) => !fits(b, r));
    const makeBtn = (b, ok) => {
      const btn = h('button', { type: 'button', class: 'block-btn', 'aria-pressed': String(b.id === slot.block), disabled: !ok },
        h('span', { class: 'block-glyph', 'aria-hidden': 'true' }, b.glyph),
        h('span', { class: 'block-name' }, b.name),
        ok ? null : h('span', { class: 'block-need' }, `Needs ${b.min_w}×${b.min_h}`));
      if (ok) btn.addEventListener('click', () => {
        if (slot.block !== b.id) {
          slot.block = b.id;
          slot.options = defaultOptions(b.id);
        }
        renderAll();
      });
      return btn;
    };
    // Empty goes last.
    good.sort((a, b) => (a.id === 'none') - (b.id === 'none'));
    blockGrid.replaceChildren(...good.map((b) => makeBtn(b, true)));
    tooBig.replaceChildren();
    tooBig.hidden = !bad.length;
    if (bad.length) {
      tooBig.append(h('summary', null, `${bad.length} blocks need a bigger slot`),
        h('div', { class: 'grid-3 block-grid' }, bad.map((b) => makeBtn(b, false))));
    }
    optionsHost.replaceChildren();
    const meta = blockOf(slot.block);
    if (meta && Object.keys(meta.options || {}).length) {
      optionsHost.append(h('h3', { class: 'detail-title' }, `${meta.name} options`), optionsForm(slot.block, slot.options, () => update()));
    }
  }

  function renderColor() {
    const slot = work.slots[sel];
    colorHead.textContent = `4 · Color for slot ${LETTERS[sel]}`;
    colorHost.replaceChildren(colorPicker({
      value: slot.color, label: `Color for slot ${LETTERS[sel]}`, allowAuto: true, autoColor: paletteColor(sel),
      onChange: (c) => { slot.color = c; renderSlots(); update(); },
    }), h('p', { class: 'card-note' }, 'A uses the palette color.'));
  }

  function renderLook() {
    lookHost.replaceChildren(
      h('div', { class: 'field-label look-label' }, 'Palette'),
      chips({
        label: 'Palette', value: work.style.palette || '',
        choices: [{ id: '', label: 'None' }, ...state.catalog.palettes.map((p) => ({ id: p.id, label: p.name }))],
        onChange: (v) => { work.style.palette = v || null; renderSlots(); renderColor(); update(); },
      }),
      h('div', { class: 'field-label look-label' }, 'Motion'),
      chips({
        label: 'Motion', value: work.style.motion,
        choices: state.catalog.motions.map((m) => ({ id: m.id, label: m.name })),
        onChange: (v) => { work.style.motion = v; update(); },
      }));
  }

  function placeOutline() {
    const r = rects()[sel];
    if (!r) { outline.hidden = true; return; }
    outline.hidden = false;
    outline.style.left = `calc(${(r.x / 32) * 100}% - 3px)`;
    outline.style.top = `calc(${(r.y / 16) * 100}% - 3px)`;
    outline.style.width = `calc(${(r.w / 32) * 100}% + 6px)`;
    outline.style.height = `calc(${(r.h / 16) * 100}% + 6px)`;
  }

  function update() { live.update(work); }

  function renderAll() {
    renderLayouts();
    renderSlots();
    renderBlocks();
    renderColor();
    placeOutline();
    update();
  }

  async function save(andShow, button) {
    work.name = nameInput.value.trim();
    if (!work.name) { msg.show('Give the screen a name.', 'error'); nameInput.focus(); return; }
    busy(button, true, 'Saving…');
    msg.show('');
    try {
      const sid = await saveScreen(work);
      if (!sid) throw new Error('Saved, but the new screen could not be found.');
      work.id = sid;
      if (andShow) { await showNow(sid); toast(`${work.name} is on the matrix.`); }
      else toast(`${work.name} saved.`);
      go(andShow ? '#/' : `#/customize/${encodeURIComponent(sid)}`);
    } catch (error) {
      msg.error(error);
      busy(button, false);
    }
  }
  saveLink.addEventListener('click', () => save(false, saveLink));
  saveShow.addEventListener('click', () => save(true, saveShow));

  renderLook();
  renderAll();
  live.now(work);
  return () => live.cancel();
}

function defaultSlots(layoutId) {
  const layout = layoutOf(layoutId);
  const defs = DEFAULTS[layoutId] || [];
  return (layout?.slots || []).map((r, i) => {
    const [block, color] = defs[i] || ['none', null];
    const meta = blockOf(block);
    const ok = meta && meta.min_w <= r.w && meta.min_h <= r.h;
    const id = ok ? block : (blockOf('text') ? 'text' : 'none');
    return { block: id, color: ok ? color : null, options: defaultOptions(id) };
  });
}

function newName() {
  const taken = new Set(customs().map((s) => s.name));
  let n = 1;
  let name = 'My screen';
  while (taken.has(name)) { n += 1; name = `My screen ${n}`; }
  return name;
}
