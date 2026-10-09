// Shared actions: saving screens, show now, timers, habits, following a flight.

import { state, act, customs, findScreen, clone, screenForSave, timerIdFor, habitIdFor, deviceNow } from './store.js';
import { h, toast } from './ui.js';

/** save_screen; resolves to the saved screen's id (new ids found by diffing). */
export async function saveScreen(screen) {
  const before = new Set(customs().map((s) => s.id));
  const payload = screenForSave(screen);
  const library = await act('save_screen', { screen: payload });
  if (payload.id) return payload.id;
  const added = library.screens.filter((s) => !before.has(s.id));
  const match = added.find((s) => s.name === payload.name) || added[added.length - 1];
  return match ? match.id : null;
}

export async function showNow(screenId, seconds) {
  const fields = { screen_id: screenId };
  if (seconds) fields.seconds = seconds;
  await act('show_now', fields);
}

export async function unpin() {
  await act('unpin', {});
}

/** Follow a callsign: reuse or create a custom copy of sky-follow, then show it now. */
export async function followFlight(callsign) {
  const cs = String(callsign || '').trim().toUpperCase();
  if (!cs) return;
  const base = findScreen('sky-follow');
  let screen = customs().find((s) => s.based_on === 'sky-follow' && /^Follow /.test(s.name));
  screen = screen ? clone(screen) : base ? { ...clone(base), id: '', based_on: 'sky-follow' } : {
    id: '', layout: 'two', based_on: null, style: { palette: null, motion: 'still' },
    slots: [{ block: 'flight', color: null, options: {} }, { block: 'progress', color: null, options: { source: 'flight' } }],
  };
  screen.name = `Follow ${cs}`.slice(0, 32);
  for (const slot of screen.slots) {
    if (slot.block === 'flight') slot.options = { ...(slot.options || {}), source: 'follow', callsign: cs };
  }
  const id = await saveScreen(screen);
  if (id) await showNow(id);
  toast(`Following ${cs} on the matrix.`);
}

// ---- Timers -------------------------------------------------------------------

function timerRemaining(t) {
  if (!t) return null;
  if (t.state === 'running' && t.ends_at) return Math.max(0, Math.round(t.ends_at - Date.now() / 1000));
  if (Number.isFinite(t.remaining_s)) return t.remaining_s;
  return null;
}

function mmss(s) {
  if (s === null || s === undefined) return '--:--';
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, '0')}`;
}

/**
 * Start/pause/reset row for a screen with a timer, "Done today" for a habit.
 * Returns null when the screen has neither.
 */
export function focusControls(screen, { compact = false } = {}) {
  const timerId = timerIdFor(screen);
  const habitId = habitIdFor(screen);
  if (!timerId && !habitId) return null;
  const box = h('div', { class: compact ? 'focus-row is-compact' : 'focus-row', role: 'group', 'aria-label': timerId ? 'Timer controls' : 'Habit' });
  const msg = h('span', { class: 'sr-only', role: 'status', 'aria-live': 'polite' });

  if (timerId) {
    const t = state.library?.timers?.[timerId];
    const status = t?.state || 'idle';
    const slot = screen.slots.find((s) => s.block === 'timer');
    const work = Number(slot?.options?.work_min) || t?.work_min || 25;
    const brk = Number(slot?.options?.break_min) || t?.break_min || 5;
    const remaining = timerRemaining(t) ?? work * 60;
    const label = h('span', { class: 'focus-time' }, mmss(remaining));
    const phase = h('span', { class: 'focus-phase' }, status === 'idle' ? `${work} / ${brk} min` : `${t?.phase === 'break' ? 'Break' : 'Focus'} · ${status}`);
    const run = async (op, done) => {
      try {
        const fields = { timer_id: timerId, op };
        if (op === 'start') { fields.work_min = work; fields.break_min = brk; }
        await act('timer', fields);
        msg.textContent = done;
      } catch (error) { toast(error.message, 'error'); }
    };
    const main = status === 'running'
      ? h('button', { type: 'button', class: 'btn btn-small btn-primary', on: { click: () => run('pause', 'Timer paused') } }, 'Pause')
      : status === 'paused'
        ? h('button', { type: 'button', class: 'btn btn-small btn-primary', on: { click: () => run('resume', 'Timer running') } }, 'Resume')
        : h('button', { type: 'button', class: 'btn btn-small btn-primary', on: { click: () => run('start', 'Timer started') } }, 'Start');
    const reset = h('button', { type: 'button', class: 'btn btn-small btn-secondary', disabled: status === 'idle', on: { click: () => run('reset', 'Timer reset') } }, 'Reset');
    const skip = h('button', { type: 'button', class: 'btn btn-small btn-secondary', disabled: status === 'idle', 'aria-label': 'Skip to the next phase', on: { click: () => run('skip', 'Skipped to the next phase') } }, 'Skip');
    box.append(h('div', { class: 'focus-info' }, label, phase), h('div', { class: 'focus-actions' }, main, reset, compact ? null : skip));
    if (status === 'running' && t?.ends_at) {
      const tick = setInterval(() => {
        if (!label.isConnected) { clearInterval(tick); return; }
        label.textContent = mmss(timerRemaining(t));
      }, 1000);
    }
  }

  if (habitId) {
    const today = deviceNow().date;
    const done = (state.library?.habits?.[habitId] || []).includes(today);
    const days = state.library?.habits?.[habitId] || [];
    const btn = h('button', { type: 'button', class: done ? 'btn btn-small btn-done' : 'btn btn-small btn-primary', 'aria-pressed': String(done) },
      done ? '✓ Done today' : 'Done today');
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      try {
        await act('habit', { habit_id: habitId, date: today, done: !done });
        msg.textContent = done ? 'Unmarked for today' : 'Marked done for today';
      } catch (error) { toast(error.message, 'error'); btn.disabled = false; }
    });
    box.append(h('div', { class: 'focus-info' },
      h('span', { class: 'focus-time' }, `${streak(days, today)}`),
      h('span', { class: 'focus-phase' }, 'day streak')), h('div', { class: 'focus-actions' }, btn));
  }
  box.append(msg);
  return box;
}

function streak(days, today) {
  const set = new Set(days);
  let n = 0;
  const d = new Date(`${today}T12:00:00Z`);
  if (!set.has(today)) d.setUTCDate(d.getUTCDate() - 1);
  while (set.has(d.toISOString().slice(0, 10))) { n += 1; d.setUTCDate(d.getUTCDate() - 1); }
  return n;
}
