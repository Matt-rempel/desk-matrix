// Font appearance and size are independent; old screens remain untouched until edited.
import { state, blockOf } from './store.js';
import { h, chips } from './ui.js';

export function fontSettings(options, legacy = state.catalog?.legacyFonts || {}) {
  const [family, size] = legacy[options.font] || ['standard', 'auto'];
  return { family: options.font_family ?? family, size: options.font_size ?? size };
}

export function chooseFont(options, choice, legacy = state.catalog?.legacyFonts || {}) {
  const current = fontSettings(options, legacy);
  options.font_family = choice.family ?? current.family;
  options.font_size = choice.size ?? current.size;
}

export function fontControls(options, onChange) {
  const current = fontSettings(options);
  const wrap = h('div', { class: 'font-controls' });
  const group = h('div', { class: 'font-choices', role: 'group', 'aria-label': 'Font' });
  for (const face of state.catalog?.fontFamilies || []) {
    const sample = h('canvas', { class: 'font-sample', width: 128, height: 64, 'aria-hidden': 'true' });
    paintFontSample(sample, face.sample);
    const button = h('button', { type: 'button', class: 'font-choice', dataset: { font: face.id },
      'aria-pressed': String(current.family === face.id) }, sample, h('span', null, face.name));
    button.addEventListener('click', () => {
      chooseFont(options, { family: face.id });
      for (const other of group.children) other.setAttribute('aria-pressed', String(other === button));
      onChange(options);
    });
    group.append(button);
  }
  const spec = blockOf('time')?.options?.font_size;
  wrap.append(h('div', { class: 'field' }, h('div', { class: 'field-label' }, 'Font'), group));
  if (spec) wrap.append(h('div', { class: 'field' }, h('div', { class: 'field-label' }, 'Size'),
    chips({ label: 'Size', value: current.size,
      choices: spec.choices.map(id => ({ id, label: spec.labels?.[id] || id })),
      onChange: size => { chooseFont(options, { size }); onChange(options); } })));
  return wrap;
}

function paintFontSample(canvas, frame) {
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#060607';
  ctx.fillRect(0, 0, 128, 64);
  if (typeof frame !== 'string' || frame.length !== 12288) return;
  for (let i = 0; i < 2048; i++) {
    const color = frame.slice(i * 6, i * 6 + 6);
    ctx.fillStyle = color === '000000' ? '#1A1A1D' : '#' + color;
    ctx.fillRect(i % 64 * 2, Math.floor(i / 64) * 2, 1.5, 1.5);
  }
}
