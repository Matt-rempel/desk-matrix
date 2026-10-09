// App state: catalog, library, settings and live status, plus helpers that
// normalize the catalog so views don't care about small shape differences.

import { api } from './api.js';

export const state = {
  catalog: null,      // normalized, see normalizeCatalog
  rawCatalog: null,
  library: null,      // as returned by the server (Contract 4)
  settings: null,     // GET /api/settings
  status: null,       // GET /api/status
  statusError: null,
  statusAt: 0,
};

const listeners = new Set();
export function subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); }
function emit(what) { for (const fn of [...listeners]) fn(what); }

export async function loadAll() {
  const [catalog, library, settings] = await Promise.all([api.catalog(), api.library(), api.settings()]);
  state.rawCatalog = catalog;
  state.catalog = normalizeCatalog(catalog);
  state.library = normalizeLibrary(library);
  state.settings = settings;
  emit('all');
}

export function setLibrary(library) {
  state.library = normalizeLibrary(library);
  emit('library');
  return state.library;
}

export function setSettings(settings) {
  state.settings = settings;
  emit('settings');
}

export function setStatus(status, error = null) {
  if (status) { state.status = status; state.statusAt = Date.now(); }
  state.statusError = error;
  emit('status');
}

/** Run one library action; the server answers with the full library. */
export async function act(action, fields) {
  const library = await api.action(action, fields);
  return setLibrary(library);
}

export async function saveSettings(partial) {
  const settings = await api.saveSettings(partial);
  setSettings(settings);
  return settings;
}

// ---- Catalog normalization ------------------------------------------------

const LAYOUT_NAMES = {
  full: 'Full panel', two: 'Two rows', icon2: 'Icon + 2 rows', bigsmall: 'Big + small',
  three: 'Three rows', split: 'Side by side',
};
const LAYOUT_ORDER = ['icon2', 'two', 'bigsmall', 'three', 'split', 'full'];
const SLOT_WHERE = {
  full: ['Whole panel'], two: ['Top row', 'Bottom row'],
  icon2: ['Left column', 'Top right', 'Bottom right'], bigsmall: ['Large top', 'Thin bottom'],
  three: ['Row 1', 'Row 2', 'Row 3'], split: ['Left half', 'Right half'],
};
const TITLE = (id) => String(id).replace(/[_-]+/g, ' ').replace(/^\w/, (c) => c.toUpperCase());

function asEntries(value) {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((item) => (typeof item === 'string' ? [item, { id: item }] : [item.id, item]));
  }
  return Object.entries(value);
}

function rect(r) {
  if (Array.isArray(r)) return { x: r[0], y: r[1], w: r[2], h: r[3] };
  return { x: r.x, y: r.y, w: r.w, h: r.h };
}

export function normalizeCatalog(raw) {
  const c = raw || {};
  const layouts = asEntries(c.layouts).map(([id, v]) => {
    const slotsRaw = Array.isArray(v) ? v : (v.slots || v.rects || []);
    const slots = slotsRaw.map((r, i) => ({ ...rect(r), where: (v.where && v.where[i]) || SLOT_WHERE[id]?.[i] || `Slot ${i + 1}` }));
    return { id, name: (!Array.isArray(v) && v.name) || LAYOUT_NAMES[id] || TITLE(id), slots };
  }).sort((a, b) => order(LAYOUT_ORDER, a.id) - order(LAYOUT_ORDER, b.id));

  const palettes = asEntries(c.palettes).map(([id, v]) => ({
    id, name: v.name || TITLE(id),
    primary: v.primary ?? v.a ?? v.grad ?? '#F4F2EE',
    secondary: v.secondary ?? v.b ?? '#8C8A84',
    glow: v.glow || null,
  }));

  const blocks = asEntries(c.blocks).map(([id, v]) => ({
    id, name: v.name || TITLE(id), glyph: v.glyph || id.slice(0, 3).toUpperCase(),
    category: v.category || 'other', options: v.options || {},
    min_w: Number(v.min_w) || 1, min_h: Number(v.min_h) || 1, needs: v.needs || [],
  }));

  const named = (list, names) => asEntries(list).map(([id, v]) => ({ id, name: v.name || names[id] || TITLE(id), glyph: v.glyph || null }));
  const motions = named(c.motions || ['still', 'breathe', 'slide', 'sparkle'],
    { still: 'Still', breathe: 'Breathe', slide: 'Slide in', sparkle: 'Sparkle' });
  const transitions = named(c.transitions || ['cut', 'slide', 'dissolve', 'wipe'],
    { cut: 'Cut', slide: 'Slide', dissolve: 'Dissolve', wipe: 'Pixel wipe' });
  const icons = asEntries(c.icons).map(([id]) => id);

  const builtins = asEntries(c.builtins).map(([id, v]) => ({ ...v, id: v.id || id }));
  const shelves = asEntries(c.shelves).map(([id, v]) => ({
    id: v.id || id, title: v.title || v.name || TITLE(id), blurb: v.blurb || '', source: v.source || '',
    screens: (v.screens || v.screen_ids || v.items || v.ids || []).map((s) => (typeof s === 'string' ? s : s.id)),
  }));
  // Builtins that no shelf lists still get a home.
  const shelved = new Set(shelves.flatMap((s) => s.screens));
  // Builtins that only back legacy ids (e.g. time-simple) stay out of the gallery.
  const legacyTargets = new Set(Object.values(c.legacy_ids || {}));
  const loose = builtins.filter((b) => !shelved.has(b.id) && !legacyTargets.has(b.id) && !b.hidden).map((b) => b.id);
  if (loose.length) shelves.push({ id: 'more', title: 'More', blurb: 'Other built-in screens.', source: '', screens: loose });

  const colors = Array.isArray(c.colors) && c.colors.length
    ? c.colors.map((x) => (typeof x === 'string' ? { c: x, name: x } : { c: x.c || x.color, name: x.name || x.c || x.color }))
    : null;
  const art = Array.isArray(c.art) ? c.art : [];

  return {
    layouts, palettes, blocks, motions, transitions, icons, builtins, shelves, colors, art,
    layoutById: new Map(layouts.map((l) => [l.id, l])),
    paletteById: new Map(palettes.map((p) => [p.id, p])),
    blockById: new Map(blocks.map((b) => [b.id, b])),
    builtinById: new Map(builtins.map((b) => [b.id, b])),
  };
}

function order(list, id) { const i = list.indexOf(id); return i < 0 ? 99 : i; }

export function normalizeLibrary(raw) {
  const lib = raw && typeof raw === 'object' ? { ...raw } : {};
  lib.screens = Array.isArray(lib.screens) ? lib.screens : [];
  lib.art = Array.isArray(lib.art) ? lib.art : [];
  lib.feeds = Array.isArray(lib.feeds) ? lib.feeds : [];
  lib.habits = lib.habits && typeof lib.habits === 'object' ? lib.habits : {};
  lib.timers = lib.timers && typeof lib.timers === 'object' ? lib.timers : {};
  const lu = lib.lineup && typeof lib.lineup === 'object' ? { ...lib.lineup } : {};
  lu.always = Array.isArray(lu.always) ? lu.always : [];
  lu.moments = Array.isArray(lu.moments) ? lu.moments : [];
  lu.transition = lu.transition || 'cut';
  lu.interrupts = lu.interrupts || {};
  lib.lineup = lu;
  lib.pinned = lib.pinned || null;
  return lib;
}

// ---- Lookups ----------------------------------------------------------------

export function builtins() { return state.catalog ? state.catalog.builtins : []; }
export function customs() { return state.library ? state.library.screens : []; }
export function isBuiltin(id) { return !!state.catalog?.builtinById.has(id); }
export function findScreen(id) {
  if (!id) return null;
  return state.catalog?.builtinById.get(id) || customs().find((s) => s.id === id) || null;
}
export function layoutOf(id) { return state.catalog?.layoutById.get(id) || null; }
export function blockOf(id) { return state.catalog?.blockById.get(id) || null; }
/** Library art plus the catalog's built-in art (builtin-pet, builtin-heart…). */
export function allArt() {
  const mine = state.library?.art || [];
  const ids = new Set(mine.map((a) => a.id));
  return [...mine, ...(state.catalog?.art || []).filter((a) => !ids.has(a.id))];
}
export function paletteOf(id) { return id ? state.catalog?.paletteById.get(id) || null : null; }

/** A screen's family: builtin family, or inherited from the builtin it was based on. */
export function familyOf(screen) {
  if (!screen) return null;
  if (screen.family) return screen.family;
  const base = screen.based_on && state.catalog?.builtinById.get(screen.based_on);
  return base ? base.family || null : null;
}

export function describeScreen(screen) {
  if (!screen) return '';
  if (screen.tag) return screen.tag;
  const base = screen.based_on && state.catalog?.builtinById.get(screen.based_on);
  if (base) return `Based on ${base.name}`;
  const names = (screen.slots || []).map((s) => blockOf(s.block)?.name).filter((n) => n && n !== 'Empty');
  return names.length ? names.slice(0, 3).join(' · ') : 'Built from blocks';
}

/** Deep copy that is safe to edit. */
export function clone(value) { return JSON.parse(JSON.stringify(value)); }

/** Keep only the fields of Contract 2 for save_screen. */
export function screenForSave(screen) {
  return {
    id: screen.id || '',
    name: String(screen.name || '').trim() || 'My screen',
    layout: screen.layout,
    slots: (screen.slots || []).map((s) => ({ block: s.block, color: s.color ?? null, options: { ...(s.options || {}) } })),
    style: { palette: screen.style?.palette ?? null, motion: screen.style?.motion || 'still' },
    based_on: screen.based_on ?? null,
  };
}

/** Default option values for a block. */
export function defaultOptions(blockId) {
  const meta = blockOf(blockId);
  const out = {};
  if (!meta) return out;
  for (const [name, spec] of Object.entries(meta.options || {})) {
    if (spec && spec.default !== undefined) out[name] = spec.default;
  }
  return out;
}

// ---- Time helpers (device time zone) ---------------------------------------

export function deviceZone() {
  const tz = state.settings?.timezone;
  try { if (tz) { Intl.DateTimeFormat('en', { timeZone: tz }); return tz; } } catch { /* fall through */ }
  return undefined;
}

/** {date: 'YYYY-MM-DD', hm: 'HH:MM', weekday: 0..6 (Mon = 0)} in the device zone. */
export function deviceNow(at = new Date()) {
  const parts = {};
  const fmt = new Intl.DateTimeFormat('en-GB', {
    timeZone: deviceZone(), year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23', weekday: 'short',
  });
  for (const p of fmt.formatToParts(at)) parts[p.type] = p.value;
  const days = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
  return {
    date: `${parts.year}-${parts.month}-${parts.day}`,
    hm: `${parts.hour === '24' ? '00' : parts.hour}:${parts.minute}`,
    weekday: days[parts.weekday] ?? 0,
  };
}

export function momentMatches(moment, now = deviceNow()) {
  const { start, end, days } = moment;
  if (!start || !end) return false;
  const dayList = Array.isArray(days) && days.length ? days : [0, 1, 2, 3, 4, 5, 6];
  if (start < end) return dayList.includes(now.weekday) && start <= now.hm && now.hm < end;
  // Crosses midnight: the part after midnight belongs to the previous day.
  if (now.hm >= start) return dayList.includes(now.weekday);
  if (now.hm < end) return dayList.includes((now.weekday + 6) % 7);
  return false;
}

/** The moment that is playing: status.moment when the Pi reports it, else computed. */
export function liveMomentId() {
  const lu = state.library?.lineup;
  if (!lu) return null;
  const reported = state.status?.moment;
  if (reported !== undefined && reported !== null && state.status) {
    const name = typeof reported === 'object' ? (reported.id || reported.name) : reported;
    const hit = lu.moments.find((m) => m.id === name || m.name === name);
    return hit ? hit.id : null;
  }
  if (state.status && 'moment' in state.status) return null;
  const hit = lu.moments.find((m) => momentMatches(m));
  return hit ? hit.id : null;
}

/** The list of lineup items currently playing. */
export function activeItems() {
  const lu = state.library?.lineup;
  if (!lu) return [];
  const id = liveMomentId();
  const moment = id && lu.moments.find((m) => m.id === id);
  if (moment && moment.screens.length) return moment.screens;
  return lu.always;
}

export function pinnedId() {
  const p = state.status?.pinned ?? state.library?.pinned;
  if (!p) return null;
  return typeof p === 'string' ? p : p.screen_id || null;
}

/** Timer/habit ids used by a screen's blocks. */
export function timerIdFor(screen) {
  const slot = (screen?.slots || []).find((s) => s.block === 'timer' || (s.block === 'progress' && s.options?.source === 'timer'));
  if (!slot) return null;
  return slot.options?.timer_id || screen.id;
}
export function habitIdFor(screen) {
  const slot = (screen?.slots || []).find((s) => s.block === 'habit_week');
  if (!slot) return null;
  return slot.options?.habit_id || screen.id;
}

export function fmtSeconds(s) {
  s = Math.max(0, Math.round(Number(s) || 0));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  const r = s % 60;
  return r ? `${m} m ${r} s` : `${m} min`;
}
