// Desk Matrix settings: boot, pairing, hash router, shell and status polling.

import { api, hasKey, setKey, forgetKey, takeKeyFromHash, setUnauthorizedHandler } from './api.js';
import { state, loadAll, setStatus, setSettings, subscribe } from './store.js';
import { h, toast } from './ui.js';
import * as gallery from './view-gallery.js';
import * as customize from './view-customize.js';
import * as build from './view-build.js';
import * as draw from './view-draw.js';
import * as lineup from './view-lineup.js';
import * as device from './view-device.js';

const main = document.getElementById('main');
let cleanup = null;
let loaded = false;
let pairingMessage = '';

// ---- Routing ----------------------------------------------------------------

export function parseRoute(hash = location.hash) {
  const raw = hash.replace(/^#\/?/, '');
  const [path, query = ''] = raw.split('?');
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const params = Object.fromEntries(new URLSearchParams(query));
  const name = parts[0] || '';
  const table = {
    '': ['gallery', gallery, true], customize: ['customize', customize, false],
    build: ['build', build, false], draw: ['draw', draw, false],
    lineup: ['lineup', lineup, true], device: ['device', device, true],
  };
  const hit = table[name] || table[''];
  return { name: hit[0], view: hit[1], top: hit[2], id: parts[1] || null, params };
}

export function go(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function route() {
  if (!hasKey() || !loaded) {
    if (!hasKey()) showPairing();
    return;
  }
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  // A sheet left open (e.g. browser Back while it is showing) would cover the new view.
  for (const dialog of document.querySelectorAll('dialog.sheet[open]')) dialog.close();
  const r = parseRoute();
  main.replaceChildren();
  document.body.dataset.route = r.name;
  const page = h('div', { class: 'page' });
  if (r.top) page.append(shellHeader(), navBar(r.name));
  const body = h('div', { class: 'page-body' });
  page.append(body);
  main.append(page);
  cleanup = r.view.render(body, { id: r.id, params: r.params, go }) || null;
  const titles = { gallery: 'Screens', customize: 'Customize', build: 'Build a screen', draw: 'Pixel studio', lineup: 'Lineup', device: 'Device' };
  document.title = `${titles[r.name] || 'Screens'} · Desk Matrix`;
  window.scrollTo(0, 0);
  // Move focus for screen-reader users when navigating between views.
  const heading = main.querySelector('h1');
  if (heading && document.activeElement === document.body) {
    heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
  }
}

// ---- Shell ------------------------------------------------------------------

function logo() {
  const pattern = [1, 0, 1, 0, 1, 0, 1, 0, 1];
  return h('span', { class: 'logo', 'aria-hidden': 'true' }, pattern.map((on) => h('i', { class: on ? 'on' : '' })));
}

let pillEl = null;
let powerEl = null;

function shellHeader() {
  pillEl = h('span', { class: 'pill', role: 'status', 'aria-live': 'polite' }, h('i', { 'aria-hidden': 'true' }), h('span', { class: 'pill-text' }, 'Connecting'));
  powerEl = h('button', { type: 'button', class: 'icon-btn power-btn', 'aria-label': 'Turn display off' });
  powerEl.append(powerIcon());
  powerEl.addEventListener('click', togglePower);
  const el = h('header', { class: 'topbar' },
    h('a', { class: 'brand', href: '#/', 'aria-label': 'Desk Matrix home' }, logo(), h('span', { class: 'brand-name' }, 'desk matrix')),
    h('div', { class: 'topbar-right' }, pillEl, powerEl));
  updateShell();
  return el;
}

function powerIcon() {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('width', '18');
  svg.setAttribute('height', '18');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('fill', 'none');
  svg.setAttribute('stroke', 'currentColor');
  svg.setAttribute('stroke-width', '2');
  svg.setAttribute('stroke-linecap', 'round');
  for (const d of ['M12 3v8', 'M6.3 7.3a8 8 0 1 0 11.4 0']) {
    const path = document.createElementNS(ns, 'path');
    path.setAttribute('d', d);
    svg.append(path);
  }
  return svg;
}

function navBar(active) {
  const items = [['gallery', '#/', 'Screens'], ['lineup', '#/lineup', 'Lineup'], ['device', '#/device', 'Device']];
  return h('nav', { class: 'segnav', 'aria-label': 'Sections' },
    items.map(([id, href, label]) => h('a', { href, class: 'segnav-item', 'aria-current': id === active ? 'page' : null }, label)));
}

export function connection() {
  const s = state.status;
  if (state.statusError || !s) return { cls: state.statusError ? 'offline' : 'pending', text: state.statusError ? 'Offline' : 'Connecting' };
  const updated = s.updated_at ? Date.parse(s.updated_at) : NaN;
  const fresh = Number.isFinite(updated) ? Date.now() - updated < 45000 : !!s.frame;
  if (s.state === 'off' || state.settings?.display_enabled === false) return { cls: 'off', text: 'Display off' };
  if (!fresh || s.state === 'starting') return { cls: 'pending', text: 'Starting' };
  if (s.state === 'delayed') return { cls: 'warn', text: 'Feed delayed' };
  return { cls: 'online', text: 'Online' };
}

function updateShell() {
  if (pillEl && pillEl.isConnected) {
    const c = connection();
    pillEl.className = `pill pill-${c.cls}`;
    pillEl.querySelector('.pill-text').textContent = c.text;
  }
  if (powerEl && powerEl.isConnected) {
    const on = state.settings?.display_enabled !== false;
    powerEl.setAttribute('aria-label', on ? 'Turn display off' : 'Turn display on');
    powerEl.setAttribute('aria-pressed', String(on));
    powerEl.classList.toggle('is-off', !on);
    powerEl.title = on ? 'Turn display off' : 'Turn display on';
  }
}

export async function togglePower() {
  if (!state.settings) return;
  const next = state.settings.display_enabled === false;
  if (powerEl) powerEl.disabled = true;
  try {
    const data = await api.display(next);
    setSettings({ ...state.settings, ...(data || {}), display_enabled: data && 'display_enabled' in data ? data.display_enabled : next });
    toast(next ? 'Display is on.' : 'Display is off. The Pi stays online.');
    pollStatus();
  } catch (error) {
    toast(error.message, 'error');
  } finally {
    if (powerEl) powerEl.disabled = false;
  }
}

subscribe((what) => { if (what === 'status' || what === 'settings' || what === 'all') updateShell(); });

// ---- Status polling (every 2 s, paused while hidden) -------------------------

let pollTimer = 0;
let polling = false;

async function pollStatus() {
  if (!hasKey() || !loaded || polling) return;
  polling = true;
  try {
    const status = await api.status();
    setStatus(status, null);
  } catch (error) {
    if (error.status !== 401) setStatus(null, error);
  } finally {
    polling = false;
  }
}

function schedulePolling() {
  clearInterval(pollTimer);
  pollTimer = 0;
  if (document.hidden || !loaded) return;
  pollStatus();
  pollTimer = setInterval(pollStatus, 2000);
}
document.addEventListener('visibilitychange', schedulePolling);

// ---- Pairing ----------------------------------------------------------------

function showPairing(message = pairingMessage) {
  if (cleanup) { try { cleanup(); } catch { /* ignore */ } cleanup = null; }
  clearInterval(pollTimer);
  document.body.dataset.route = 'pairing';
  document.title = 'Pair · Desk Matrix';
  const input = h('input', {
    id: 'pairing-key', type: 'password', autocomplete: 'off', spellcheck: 'false', required: true,
    inputmode: 'text', 'aria-describedby': 'pairing-help pairing-error', minlength: '64', maxlength: '64',
  });
  const error = h('p', { id: 'pairing-error', class: 'msg is-error', role: 'alert' }, message || '');
  const submit = h('button', { type: 'submit', class: 'btn btn-primary' }, 'Connect');
  const form = h('form', { class: 'pair-form', novalidate: true },
    h('label', { for: 'pairing-key', class: 'field-label' }, 'Pairing key'), input, submit, error);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const value = input.value.trim();
    if (!/^[0-9a-fA-F]{64}$/.test(value)) {
      error.textContent = 'The pairing key is 64 letters and numbers (0–9, a–f).';
      input.focus();
      return;
    }
    submit.disabled = true;
    submit.textContent = 'Connecting…';
    setKey(value);
    pairingMessage = '';
    const ok = await start();
    if (!ok) { submit.disabled = false; submit.textContent = 'Connect'; }
  });
  main.replaceChildren(h('section', { class: 'pair', 'aria-labelledby': 'pair-title' },
    h('div', { class: 'brand brand-lg' }, logo(), h('span', { class: 'brand-name' }, 'desk matrix')),
    h('h1', { id: 'pair-title', class: 'pair-title' }, 'Connect this browser'),
    h('p', { id: 'pairing-help', class: 'pair-text' },
      'Enter the pairing key shown in the Pi installation terminal, or open the pairing link from it. The key stays in this browser tab only.'),
    form));
  if (!message) input.focus();
}

setUnauthorizedHandler((message) => {
  forgetKey();
  loaded = false;
  pairingMessage = message || 'The pairing key was not accepted. Enter it again.';
  showPairing(pairingMessage);
});

async function start() {
  try {
    await loadAll();
    loaded = true;
    route();
    schedulePolling();
    return true;
  } catch (error) {
    if (error.status === 401) return false; // handler already showed pairing
    loaded = false;
    main.replaceChildren(h('section', { class: 'pair' },
      h('h1', { class: 'pair-title' }, 'Can’t load settings'),
      h('p', { class: 'msg is-error', role: 'alert' }, error.message),
      h('button', { type: 'button', class: 'btn btn-primary', on: { click: () => start() } }, 'Try again')));
    return false;
  }
}

window.addEventListener('hashchange', () => {
  if (takeKeyFromHash()) { start(); return; }
  route();
});

takeKeyFromHash();
if (hasKey()) start();
else showPairing();
