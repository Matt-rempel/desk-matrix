// Pixel studio: draw 7×7 icons, 16×16 sprites or full-panel art, with frames.

import { state, act, layoutOf, blockOf } from './store.js';
import { createMatrix, livePreview } from './matrix.js';
import { h, header, messageLine, toast, confirmSheet, busy, stepper, paint, nextId } from './ui.js';
import { saveScreen } from './controls.js';

const SIZES = [
  { id: '7', name: '7 × 7 icon', w: 7, h: 7, note: 'Icons sit beside text in any layout.' },
  { id: '16', name: '16 × 16 sprite', w: 16, h: 16, note: 'Sprites fill half the panel; text goes beside.' },
  { id: '32', name: 'Full 32 × 16', w: 32, h: 16, note: 'Full-panel art for messages and ambient screens.' },
];
const INKS = [
  { c: '#FF3D5A', name: 'Red' }, { c: '#FF7AB6', name: 'Pink' }, { c: '#FFB23F', name: 'Amber' },
  { c: '#FFE066', name: 'Yellow' }, { c: '#5AD1A0', name: 'Mint' }, { c: '#7CB8FF', name: 'Sky' },
  { c: '#B98CFF', name: 'Violet' }, { c: '#F4F2EE', name: 'White' }, { c: '#8C8A84', name: 'Grey' },
];
const MAX_FRAMES = 8;
const MAX_COLORS = 16;
const EMPTY = '#1A1A1D';

export function decodeArt(art) {
  const pal = art.palette || [];
  return (art.frames && art.frames.length ? art.frames : ['.'.repeat(art.w * art.h)]).map((f) => {
    const cells = new Array(art.w * art.h).fill(null);
    for (let i = 0; i < cells.length; i++) {
      const ch = f[i];
      if (!ch || ch === '.') continue;
      const idx = parseInt(ch, 16);
      cells[i] = Number.isFinite(idx) && pal[idx] ? pal[idx].toUpperCase() : null;
    }
    return cells;
  });
}

export function encodeArt(frames) {
  const palette = [];
  const out = frames.map((cells) => cells.map((c) => {
    if (!c) return '.';
    let idx = palette.indexOf(c);
    if (idx < 0) { palette.push(c); idx = palette.length - 1; }
    return idx < 16 ? idx.toString(16) : '?';
  }).join(''));
  if (palette.length > MAX_COLORS) throw new Error(`Use at most ${MAX_COLORS} colors in one drawing (this one has ${palette.length}).`);
  return { palette, frames: out };
}

export function render(root, { id, go }) {
  const existing = id ? (state.library?.art || []).find((a) => a.id === id) : null;
  const art = existing
    ? { id: existing.id, name: existing.name, w: existing.w, h: existing.h, fps: existing.fps || 4, frames: decodeArt(existing) }
    : { id: '', name: 'My drawing', w: 16, h: 16, fps: 4, frames: [new Array(256).fill(null)] };
  let frameIdx = 0;
  let tool = 'pen';
  let mirror = false;
  let ink = INKS[0].c;
  let savedJSON = JSON.stringify([art.name, art.w, art.h, art.fps, art.frames]);
  const undo = [];
  const dirty = () => JSON.stringify([art.name, art.w, art.h, art.fps, art.frames]) !== savedJSON;
  const sizeOf = () => SIZES.find((s) => s.w === art.w && s.h === art.h) || SIZES[1];

  const msg = messageLine();
  const saveLink = h('button', { type: 'button', class: 'subbar-link subbar-strong' }, 'Save');
  root.append(header({ back: '#/', backLabel: '‹ Back', title: 'Pixel studio', action: saveLink }));

  // Preview
  const matrix = createMatrix({ pitch: 4, glow: true, label: 'How the art looks on the matrix' });
  const live = livePreview(matrix, { onError: () => {} });
  const useNote = h('div', { class: 'use-note' });
  const previewState = h('div', { class: 'mono-note' });
  root.append(h('section', { class: 'pad draw-top' },
    h('div', { class: 'bezel bezel-sm' }, matrix.el),
    h('div', null, h('div', { class: 'eyebrow' }, 'On the matrix'), useNote, previewState)));

  // Name
  const nameId = nextId('art-name');
  const nameInput = h('input', { id: nameId, class: 'input', value: art.name, maxlength: '32', autocomplete: 'off' });
  nameInput.addEventListener('input', () => { art.name = nameInput.value; });
  root.append(h('div', { class: 'inline-field pad-x' }, h('label', { for: nameId, class: 'eyebrow' }, 'Name'), nameInput));

  // Sizes
  const sizeGroup = h('div', { class: 'seg', role: 'group', 'aria-label': 'Canvas size' });
  root.append(h('div', { class: 'pad-x block-tight' }, sizeGroup));

  // Canvas
  const grid = h('canvas', { class: 'pixel-grid', tabindex: '0', role: 'application', 'aria-roledescription': 'pixel canvas',
    'aria-label': 'Drawing canvas. Arrow keys move, Space paints.', 'aria-describedby': 'grid-pos' });
  const gridPos = h('p', { id: 'grid-pos', class: 'sr-only', 'aria-live': 'polite' });
  const gridWrap = h('div', { class: 'grid-wrap' }, grid);
  root.append(h('section', { class: 'pad', 'aria-label': 'Drawing canvas' }, gridWrap, gridPos));

  // Tools
  const toolRow = h('div', { class: 'tool-row' });
  const inkRow = h('div', { class: 'swatches ink-row', role: 'group', 'aria-label': 'Ink color' });
  root.append(h('section', { class: 'block', 'aria-labelledby': 'tools-h' }, h('h2', { id: 'tools-h', class: 'sr-only' }, 'Tools'), toolRow, inkRow));

  // Frames
  const frameRow = h('div', { class: 'frame-row', role: 'group', 'aria-label': 'Frames' });
  const fpsNote = h('span', { class: 'mono-note' });
  root.append(h('section', { class: 'block card', 'aria-labelledby': 'fr-h' },
    h('div', { class: 'head-row' }, h('h2', { id: 'fr-h', class: 'card-title' }, 'Frames'), fpsNote),
    h('p', { class: 'card-note' }, 'Add frames to animate it: a blinking pet, a flickering flame.'),
    frameRow,
    h('div', { class: 'row row-flat' }, h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, 'Speed')),
      stepper({ label: 'frames per second', value: art.fps, min: 1, max: 12, format: (v) => `${v} fps`, onChange: (v) => { art.fps = v; renderFrames(); preview(); } }))));

  // Actions
  const saveBtn = h('button', { type: 'button', class: 'btn btn-primary' }, 'Save art');
  const screenBtn = h('button', { type: 'button', class: 'btn btn-secondary' }, 'Make a screen');
  root.append(h('div', { class: 'btn-row pad-x' }, saveBtn, screenBtn), h('div', { class: 'pad-x' }, msg));
  if (existing) {
    const del = h('button', { type: 'button', class: 'btn btn-danger-quiet' }, 'Delete art');
    del.addEventListener('click', async () => {
      if (!(await confirmSheet({ title: `Delete “${art.name}”?`, text: 'Screens that use it will show an empty slot.' }))) return;
      try { await act('delete_art', { art_id: art.id }); toast('Art deleted.'); go('#/'); } catch (error) { msg.error(error); }
    });
    root.append(h('div', { class: 'btn-row pad-x' }, del));
  }

  // ---- rendering ---------------------------------------------------------------

  let cursor = { x: 0, y: 0 };
  let cell = 10;
  const gap = () => (art.w <= 7 ? 3 : art.w <= 16 ? 2 : 1);

  function layoutGrid() {
    const avail = Math.min(gridWrap.clientWidth || 350, 420) - 16;
    const g = gap();
    cell = Math.max(6, Math.floor((avail - g * (art.w - 1)) / art.w));
    if (art.w === 7) cell = Math.min(cell, 38);
    const cssW = art.w * cell + (art.w - 1) * g;
    const cssH = art.h * cell + (art.h - 1) * g;
    const dpr = Math.min(3, window.devicePixelRatio || 1);
    grid.width = Math.round(cssW * dpr);
    grid.height = Math.round(cssH * dpr);
    grid.style.width = `${cssW}px`;
    grid.style.height = `${cssH}px`;
    drawGrid();
  }

  function drawGrid() {
    const ctx = grid.getContext('2d');
    const dpr = grid.width / parseFloat(grid.style.width || grid.width);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, grid.width, grid.height);
    const g = gap();
    const r = art.w <= 7 ? 6 : art.w <= 16 ? 3 : 2;
    const cells = art.frames[frameIdx];
    const ghost = frameIdx > 0 ? art.frames[frameIdx - 1] : null;
    for (let y = 0; y < art.h; y++) {
      for (let x = 0; x < art.w; x++) {
        const c = cells[y * art.w + x];
        ctx.fillStyle = c || EMPTY;
        ctx.globalAlpha = 1;
        if (!c && ghost && ghost[y * art.w + x]) { ctx.fillStyle = ghost[y * art.w + x]; ctx.globalAlpha = 0.18; }
        rounded(ctx, x * (cell + g), y * (cell + g), cell, cell, r);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
    if (document.activeElement === grid) {
      ctx.strokeStyle = '#FFB23F';
      ctx.lineWidth = 2;
      rounded(ctx, cursor.x * (cell + g) + 1, cursor.y * (cell + g) + 1, cell - 2, cell - 2, r);
      ctx.stroke();
    }
  }

  function rounded(ctx, x, y, w, hh, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + hh, r);
    ctx.arcTo(x + w, y + hh, x, y + hh, r);
    ctx.arcTo(x, y + hh, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  function renderSizes() {
    const cur = sizeOf();
    sizeGroup.replaceChildren(...SIZES.map((s) => {
      const btn = h('button', { type: 'button', class: 'seg-btn', 'aria-pressed': String(s.id === cur.id) }, s.name);
      btn.addEventListener('click', () => resize(s));
      return btn;
    }));
    useNote.textContent = cur.note;
  }

  function resize(s) {
    if (s.w === art.w && s.h === art.h) return;
    pushUndo();
    art.frames = art.frames.map((cells) => {
      const next = new Array(s.w * s.h).fill(null);
      for (let y = 0; y < Math.min(s.h, art.h); y++) {
        for (let x = 0; x < Math.min(s.w, art.w); x++) next[y * s.w + x] = cells[y * art.w + x];
      }
      return next;
    });
    art.w = s.w;
    art.h = s.h;
    cursor = { x: 0, y: 0 };
    renderSizes();
    layoutGrid();
    renderFrames();
    preview();
  }

  function renderTools() {
    const tools = [['pen', 'Pencil'], ['erase', 'Erase'], ['fill', 'Fill']];
    toolRow.replaceChildren(
      ...tools.map(([tid, label]) => {
        const btn = h('button', { type: 'button', class: 'tool-btn', 'aria-pressed': String(tool === tid) }, label);
        btn.addEventListener('click', () => { tool = tid; renderTools(); });
        return btn;
      }),
      (() => {
        const btn = h('button', { type: 'button', class: 'tool-btn', 'aria-pressed': String(mirror) }, 'Mirror');
        btn.addEventListener('click', () => { mirror = !mirror; renderTools(); });
        return btn;
      })(),
      (() => {
        const btn = h('button', { type: 'button', class: 'tool-btn', disabled: !undo.length }, 'Undo');
        btn.addEventListener('click', () => {
          const snap = undo.pop();
          if (!snap) return;
          Object.assign(art, JSON.parse(snap));
          frameIdx = Math.min(frameIdx, art.frames.length - 1);
          renderSizes(); layoutGrid(); renderFrames(); renderTools(); preview();
        });
        return btn;
      })(),
      (() => {
        const btn = h('button', { type: 'button', class: 'tool-btn' }, 'Clear');
        btn.addEventListener('click', () => {
          pushUndo();
          art.frames[frameIdx] = new Array(art.w * art.h).fill(null);
          drawGrid(); renderFrames(); preview();
        });
        return btn;
      })());
    const custom = h('input', { type: 'color', class: 'swatch-input', 'aria-label': 'Custom ink', value: INKS.some((i) => i.c === ink) ? '#FFFFFF' : ink });
    custom.classList.toggle('is-on', !INKS.some((i) => i.c === ink));
    custom.addEventListener('input', () => { ink = custom.value.toUpperCase(); if (tool === 'erase') tool = 'pen'; renderTools(); });
    inkRow.replaceChildren(...INKS.map((i) => {
      const btn = h('button', { type: 'button', class: 'swatch swatch-sm', 'aria-label': i.name, 'aria-pressed': String(i.c === ink) });
      paint(btn, i.c);
      btn.addEventListener('click', () => { ink = i.c; if (tool === 'erase') tool = 'pen'; renderTools(); });
      return btn;
    }), h('label', { class: 'swatch-custom swatch-sm', title: 'Custom ink' }, custom));
  }

  function renderFrames() {
    fpsNote.textContent = art.frames.length > 1 ? `${art.fps} fps · loop` : 'Still';
    frameRow.replaceChildren(
      ...art.frames.map((_, i) => {
        const btn = h('button', { type: 'button', class: 'frame-btn', 'aria-pressed': String(i === frameIdx), 'aria-label': `Frame ${i + 1}` }, String(i + 1));
        btn.addEventListener('click', () => { frameIdx = i; renderFrames(); drawGrid(); preview(); });
        return btn;
      }),
      h('button', {
        type: 'button', class: 'frame-btn frame-add', 'aria-label': 'Add frame (copies this one)', disabled: art.frames.length >= MAX_FRAMES,
        on: { click: () => { pushUndo(); art.frames.splice(frameIdx + 1, 0, art.frames[frameIdx].slice()); frameIdx += 1; renderFrames(); drawGrid(); preview(); } },
      }, '+'),
      art.frames.length > 1 ? h('button', {
        type: 'button', class: 'frame-btn frame-del', 'aria-label': `Delete frame ${frameIdx + 1}`,
        on: { click: () => { pushUndo(); art.frames.splice(frameIdx, 1); frameIdx = Math.max(0, frameIdx - 1); renderFrames(); drawGrid(); preview(); } },
      }, '×') : null);
  }

  function pushUndo() {
    undo.push(JSON.stringify({ w: art.w, h: art.h, frames: art.frames }));
    if (undo.length > 40) undo.shift();
    renderToolsSoon();
  }
  let toolsQueued = false;
  function renderToolsSoon() {
    if (toolsQueued) return;
    toolsQueued = true;
    requestAnimationFrame(() => { toolsQueued = false; renderTools(); });
  }

  // ---- painting ----------------------------------------------------------------

  function apply(x, y) {
    const cells = art.frames[frameIdx];
    if (tool === 'fill') {
      const from = cells[y * art.w + x] || null;
      if (from === ink) return;
      const stack = [[x, y]];
      while (stack.length) {
        const [px, py] = stack.pop();
        if (px < 0 || py < 0 || px >= art.w || py >= art.h) continue;
        const k = py * art.w + px;
        if ((cells[k] || null) !== from) continue;
        cells[k] = ink;
        stack.push([px + 1, py], [px - 1, py], [px, py + 1], [px, py - 1]);
      }
      return;
    }
    const targets = [[x, y]];
    if (mirror) targets.push([art.w - 1 - x, y]);
    for (const [tx, ty] of targets) cells[ty * art.w + tx] = tool === 'erase' ? null : ink;
  }

  function cellAt(event) {
    const rect = grid.getBoundingClientRect();
    const g = gap();
    const x = Math.floor((event.clientX - rect.left) / (cell + g));
    const y = Math.floor((event.clientY - rect.top) / (cell + g));
    if (x < 0 || y < 0 || x >= art.w || y >= art.h) return null;
    return { x, y };
  }

  let drawing = false;
  let last = null;
  grid.addEventListener('pointerdown', (event) => {
    const p = cellAt(event);
    if (!p) return;
    event.preventDefault();
    grid.setPointerCapture(event.pointerId);
    pushUndo();
    drawing = tool !== 'fill';
    last = `${p.x},${p.y}`;
    cursor = p;
    apply(p.x, p.y);
    drawGrid();
    preview();
  });
  grid.addEventListener('pointermove', (event) => {
    if (!drawing) return;
    const p = cellAt(event);
    if (!p || `${p.x},${p.y}` === last) return;
    last = `${p.x},${p.y}`;
    apply(p.x, p.y);
    drawGrid();
    preview();
  });
  const stop = () => { drawing = false; last = null; };
  grid.addEventListener('pointerup', stop);
  grid.addEventListener('pointercancel', stop);
  grid.addEventListener('focus', drawGrid);
  grid.addEventListener('blur', drawGrid);
  grid.addEventListener('keydown', (event) => {
    const moves = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (moves[event.key]) {
      event.preventDefault();
      cursor = { x: Math.min(art.w - 1, Math.max(0, cursor.x + moves[event.key][0])), y: Math.min(art.h - 1, Math.max(0, cursor.y + moves[event.key][1])) };
      const c = art.frames[frameIdx][cursor.y * art.w + cursor.x];
      gridPos.textContent = `Pixel ${cursor.x + 1}, ${cursor.y + 1}, ${c ? 'filled' : 'empty'}`;
      drawGrid();
    } else if (event.key === ' ' || event.key === 'Enter') {
      event.preventDefault();
      pushUndo();
      apply(cursor.x, cursor.y);
      const c = art.frames[frameIdx][cursor.y * art.w + cursor.x];
      gridPos.textContent = `Pixel ${cursor.x + 1}, ${cursor.y + 1}, ${c ? 'filled' : 'empty'}`;
      drawGrid();
      preview();
    }
  });

  // ---- preview -----------------------------------------------------------------

  let animTimer = 0;
  function artScreen(artId) {
    const small = art.w <= 7 && layoutOf('icon2');
    const slots = small
      ? [{ block: 'art', color: null, options: { art_id: artId } },
        { block: blockOf('time') ? 'time' : 'none', color: '#F4F2EE', options: {} },
        { block: blockOf('temp') ? 'temp' : 'none', color: '#8C8A84', options: {} }]
      : [{ block: 'art', color: null, options: { art_id: artId } }];
    return { id: '', name: art.name, layout: small ? 'icon2' : 'full', slots, style: { palette: null, motion: 'still' }, based_on: null };
  }

  /** Server preview when saved; an exact local composite of the pixels while editing. */
  function preview() {
    clearInterval(animTimer);
    if (art.id && !dirty()) {
      previewState.textContent = 'Rendered by the Pi';
      live.update(artScreen(art.id));
      return;
    }
    live.cancel();
    previewState.textContent = 'Unsaved · save to see it with text';
    const paintLocal = (i) => matrix.setFrame(localFrame(art.frames[i]));
    if (art.frames.length > 1) {
      let i = frameIdx;
      paintLocal(i);
      animTimer = setInterval(() => {
        if (!matrix.el.isConnected) { clearInterval(animTimer); return; }
        i = (i + 1) % art.frames.length;
        paintLocal(i);
      }, 1000 / art.fps);
    } else paintLocal(0);
  }

  function localFrame(cells) {
    const px = new Array(512).fill('000000');
    const ox = art.w <= 7 ? 0 : art.w <= 16 ? 8 : 0;
    const oy = art.h <= 7 ? 4 : 0;
    for (let y = 0; y < art.h; y++) {
      for (let x = 0; x < art.w; x++) {
        const c = cells[y * art.w + x];
        const X = x + ox;
        const Y = y + oy;
        if (c && X < 32 && Y < 16) px[Y * 32 + X] = c.slice(1).toLowerCase();
      }
    }
    return px.join('');
  }

  // ---- saving --------------------------------------------------------------------

  async function save(button) {
    art.name = nameInput.value.trim();
    if (!art.name) { msg.show('Give the drawing a name.', 'error'); nameInput.focus(); return null; }
    let encoded;
    try { encoded = encodeArt(art.frames); } catch (error) { msg.error(error); return null; }
    if (!encoded.palette.length) { msg.show('Draw something first.', 'error'); return null; }
    busy(button, true, 'Saving…');
    msg.show('');
    try {
      const before = new Set((state.library?.art || []).map((a) => a.id));
      const payload = { id: art.id || '', name: art.name, w: art.w, h: art.h, palette: encoded.palette, frames: encoded.frames, fps: art.fps };
      const library = await act('save_art', { art: payload });
      if (!art.id) {
        const added = library.art.filter((a) => !before.has(a.id));
        const hit = added.find((a) => a.name === art.name) || added[added.length - 1];
        if (!hit) throw new Error('Saved, but the new art could not be found.');
        art.id = hit.id;
        history.replaceState(null, '', `#/draw/${encodeURIComponent(art.id)}`);
      }
      savedJSON = JSON.stringify([art.name, art.w, art.h, art.fps, art.frames]);
      msg.show(`${art.name} saved.`);
      preview();
      return art.id;
    } catch (error) {
      msg.error(error);
      return null;
    } finally {
      busy(button, false);
    }
  }
  saveLink.addEventListener('click', () => save(saveLink));
  saveBtn.addEventListener('click', () => save(saveBtn));
  screenBtn.addEventListener('click', async () => {
    const artId = dirty() || !art.id ? await save(screenBtn) : art.id;
    if (!artId) return;
    busy(screenBtn, true, 'Creating…');
    try {
      const sid = await saveScreen(artScreen(artId));
      toast('Screen created. Customize it, then tap Show now.');
      go(`#/customize/${encodeURIComponent(sid)}`);
    } catch (error) { msg.error(error); busy(screenBtn, false); }
  });

  renderSizes();
  renderTools();
  renderFrames();
  requestAnimationFrame(layoutGrid);
  const onResize = () => layoutGrid();
  window.addEventListener('resize', onResize);
  preview();
  return () => { clearInterval(animTimer); live.cancel(); window.removeEventListener('resize', onResize); };
}
