// <canvas> LED matrix: paints a 3072-hex frame (512 × RRGGBB, row-major) as dots.

import { preview, cachedPreview, debounce } from './api.js';

export const COLS = 32;
export const ROWS = 16;
const UNLIT = '#1A1A1D';
const BACKGROUND = '#060607';
const BLANK = '0'.repeat(3072);

const observed = new WeakMap();
let resizeObserver = null;

function observer() {
  if (!resizeObserver && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const matrix = observed.get(entry.target);
        if (matrix) matrix.draw();
      }
    });
  }
  return resizeObserver;
}

/**
 * Create a matrix display.
 * @param {object} opts
 * @param {number} opts.pitch  design pitch in CSS px per LED (max size)
 * @param {boolean} [opts.glow]
 * @param {string} [opts.label] accessible description
 */
export function createMatrix({ pitch = 10, glow = true, label = '', className = '' } = {}) {
  const wrap = document.createElement('div');
  wrap.className = 'matrix' + (className ? ' ' + className : '');
  wrap.style.setProperty('--matrix-max', `${COLS * pitch}px`);
  wrap.style.setProperty('--matrix-radius', `${Math.max(2, pitch * 0.6).toFixed(1)}px`);
  const canvas = document.createElement('canvas');
  canvas.className = 'matrix-canvas';
  canvas.setAttribute('role', 'img');
  canvas.setAttribute('aria-label', label || 'LED matrix preview');
  canvas.width = COLS * pitch;
  canvas.height = ROWS * pitch;
  wrap.append(canvas);

  let frame = BLANK;
  let drawnKey = '';

  const matrix = {
    el: wrap,
    canvas,
    get frame() { return frame; },
    setLabel(text) { canvas.setAttribute('aria-label', text || 'LED matrix preview'); },
    setFrame(hex) {
      if (typeof hex !== 'string' || hex.length !== 3072) hex = BLANK;
      if (hex === frame && drawnKey) return;
      frame = hex;
      drawnKey = '';
      matrix.draw();
    },
    draw() {
      const cssWidth = wrap.clientWidth || canvas.clientWidth || COLS * pitch;
      const dpr = Math.min(3, window.devicePixelRatio || 1);
      const w = Math.max(32, Math.round(cssWidth * dpr));
      const h = Math.round(w / 2);
      const key = `${w}:${frame.length}`;
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      } else if (drawnKey === key) {
        return;
      }
      paint(canvas, frame, glow);
      drawnKey = key;
    },
    destroy() {
      const ro = observer();
      if (ro) ro.unobserve(wrap);
    },
  };
  observed.set(wrap, matrix);
  const ro = observer();
  if (ro) ro.observe(wrap);
  requestAnimationFrame(() => matrix.draw());
  return matrix;
}

function paint(canvas, frame, glow) {
  const ctx = canvas.getContext('2d');
  const W = canvas.width;
  const p = W / COLS;
  const d = Math.max(1, p * 0.8);
  const off = (p - d) / 2;
  const unlitR = d * 0.42;
  const radius = d * 0.3;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, W, canvas.height);
  ctx.fillStyle = BACKGROUND;
  ctx.fillRect(0, 0, W, canvas.height);

  // Unlit dots first, in one path.
  ctx.fillStyle = UNLIT;
  ctx.beginPath();
  for (let y = 0; y < ROWS; y++) {
    for (let x = 0; x < COLS; x++) {
      const k = (y * COLS + x) * 6;
      if (frame.startsWith('000000', k)) {
        const cx = x * p + p / 2;
        const cy = y * p + p / 2;
        ctx.moveTo(cx + unlitR, cy);
        ctx.arc(cx, cy, unlitR, 0, Math.PI * 2);
      }
    }
  }
  ctx.fill();

  // Lit LEDs, grouped by colour to keep the number of fills small.
  const groups = new Map();
  for (let i = 0; i < COLS * ROWS; i++) {
    const hex = frame.substr(i * 6, 6);
    if (hex === '000000') continue;
    let list = groups.get(hex);
    if (!list) groups.set(hex, (list = []));
    list.push(i);
  }
  const blur = glow ? p * 0.9 : 0;
  for (const [hex, cells] of groups) {
    const color = '#' + hex;
    ctx.fillStyle = color;
    if (blur) {
      ctx.shadowBlur = blur;
      ctx.shadowColor = color + '66';
    } else {
      ctx.shadowBlur = 0;
      ctx.shadowColor = 'transparent';
    }
    ctx.beginPath();
    for (const i of cells) {
      const x = (i % COLS) * p + off;
      const y = Math.floor(i / COLS) * p + off;
      roundRect(ctx, x, y, d, d, radius);
    }
    ctx.fill();
  }
  ctx.shadowBlur = 0;
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.moveTo(x + r, y);
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
}

/** A matrix that renders a screen definition through /api/preview. */
export function screenMatrix(screen, opts = {}) {
  const m = createMatrix(opts);
  const cached = cachedPreview(screen);
  if (cached) m.setFrame(cached);
  else preview(screen).then((f) => m.setFrame(f)).catch(() => m.el.classList.add('matrix-error'));
  return m;
}

/**
 * Keep a matrix in sync with an editor's working copy: debounced (150 ms)
 * and ignoring responses that arrive after a newer request.
 */
export function livePreview(matrix, { onError, ms = 150 } = {}) {
  let seq = 0;
  const run = (screen) => {
    const mine = ++seq;
    const cached = cachedPreview(screen);
    if (cached) { matrix.setFrame(cached); return; }
    matrix.el.classList.add('matrix-busy');
    preview(screen).then((frame) => {
      if (mine === seq) matrix.setFrame(frame);
    }).catch((error) => {
      if (mine === seq && onError) onError(error);
    }).finally(() => {
      if (mine === seq) matrix.el.classList.remove('matrix-busy');
    });
  };
  const debounced = debounce(run, ms);
  return {
    now: (screen) => { debounced.cancel(); run(screen); },
    update: (screen) => {
      const cached = cachedPreview(screen);
      if (cached) { debounced.cancel(); seq++; matrix.setFrame(cached); return; }
      debounced(screen);
    },
    cancel: () => { debounced.cancel(); seq++; },
  };
}
