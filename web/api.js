// HTTP helpers: pairing key, JSON requests, error handling and batched previews.

const KEY_NAME = 'flightboard-key';
const KEY_RE = /^[0-9a-fA-F]{64}$/;
let key = '';
let onUnauthorized = () => {};

try { key = sessionStorage.getItem(KEY_NAME) || ''; } catch { key = ''; }

/** Accept a pairing link: `#key=<64 hex>` or the older `#<64 hex>`. */
export function takeKeyFromHash() {
  const hash = location.hash.slice(1);
  const match = hash.match(/^(?:key=)?([0-9a-fA-F]{64})$/) || hash.match(/[?&]key=([0-9a-fA-F]{64})/);
  if (!match) return false;
  setKey(match[1]);
  history.replaceState(null, '', location.pathname + location.search + '#/');
  return true;
}

export function getKey() { return key; }
export function hasKey() { return KEY_RE.test(key); }
export function setKey(value) {
  key = String(value || '').trim();
  try {
    if (key) sessionStorage.setItem(KEY_NAME, key);
    else sessionStorage.removeItem(KEY_NAME);
  } catch { /* storage blocked: key lives for this page only */ }
}
export function forgetKey() { setKey(''); }
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

export async function request(path, { method = 'GET', body } = {}) {
  const headers = { 'X-Flightboard-Key': key };
  const init = { method, headers, cache: 'no-store' };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, init);
  } catch {
    throw new ApiError('Could not reach the Pi. Check that it is on and connected.', 0);
  }
  let data = null;
  try { data = await response.json(); } catch { data = null; }
  if (response.status === 401) {
    onUnauthorized(data && data.error);
    throw new ApiError((data && data.error) || 'Pair this browser again', 401);
  }
  if (!response.ok) {
    throw new ApiError((data && data.error) || `Request failed (${response.status})`, response.status);
  }
  return data;
}

export const api = {
  catalog: () => request('/api/catalog'),
  library: () => request('/api/library'),
  settings: () => request('/api/settings'),
  status: () => request('/api/status'),
  saveSettings: (partial) => request('/api/settings', { method: 'POST', body: partial }),
  display: (enabled) => request('/api/display', { method: 'POST', body: { display_enabled: enabled } }),
  action: (action, fields = {}) => request('/api/library', { method: 'POST', body: { action, ...fields } }),
};

// ---- Previews -------------------------------------------------------------
// Callers ask for one screen at a time; requests made in the same tick are
// merged into POST /api/preview batches of at most 40 screens. Results are
// cached by the screen's JSON so re-renders don't refetch.

const MAX_BATCH = 40;
const CACHE_LIMIT = 300;
const cache = new Map();
let queue = [];
let scheduled = false;

function cacheKey(screen) {
  // Only the fields the renderer uses; names do not change pixels.
  return JSON.stringify([screen.layout, screen.slots, screen.style || null]);
}

function remember(k, frame) {
  cache.set(k, frame);
  if (cache.size > CACHE_LIMIT) cache.delete(cache.keys().next().value);
}

export function cachedPreview(screen) {
  return cache.get(cacheKey(screen)) || null;
}

export function preview(screen) {
  const k = cacheKey(screen);
  if (cache.has(k)) return Promise.resolve(cache.get(k));
  const pending = queue.find((item) => item.k === k);
  if (pending) return pending.promise;
  let resolve, reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  queue.push({ k, screen: previewable(screen), resolve, reject, promise });
  if (!scheduled) {
    scheduled = true;
    queueMicrotask(flush);
  }
  return promise;
}

/** Strip UI-only fields before sending a screen to the renderer. */
export function previewable(screen) {
  const out = {
    id: screen.id || '',
    name: screen.name || 'Preview',
    layout: screen.layout,
    slots: (screen.slots || []).map((slot) => ({
      block: slot.block,
      color: slot.color ?? null,
      options: { ...(slot.options || {}) },
    })),
    style: { palette: screen.style?.palette ?? null, motion: screen.style?.motion || 'still' },
    based_on: screen.based_on ?? null,
  };
  return out;
}

async function flush() {
  scheduled = false;
  const items = queue;
  queue = [];
  for (let i = 0; i < items.length; i += MAX_BATCH) {
    const chunk = items.slice(i, i + MAX_BATCH);
    try {
      const data = await request('/api/preview', { method: 'POST', body: { screens: chunk.map((it) => it.screen) } });
      const frames = (data && data.frames) || [];
      chunk.forEach((item, n) => {
        const frame = frames[n];
        if (typeof frame === 'string' && frame.length === 3072) {
          remember(item.k, frame);
          item.resolve(frame);
        } else {
          item.reject(new ApiError('Preview unavailable', 500));
        }
      });
    } catch (error) {
      chunk.forEach((item) => item.reject(error));
    }
  }
}

/** Debounce helper for editors (default 150 ms). */
export function debounce(fn, ms = 150) {
  let timer = 0;
  const wrapped = (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
  wrapped.cancel = () => clearTimeout(timer);
  return wrapped;
}
