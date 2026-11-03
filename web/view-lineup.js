// Lineup: time-of-day moments, always-on list, interruptions and transitions.

import { state, subscribe, clone, findScreen, customs, liveMomentId, act } from './store.js';
import { screenMatrix } from './matrix.js';
import { h, toggle, stepper, chips, sheet, toast, messageLine, confirmSheet, busy, nextId } from './ui.js';
import { teamPicker, followedTeams, teamsLabel } from './nhl-teams.js';

const DAY_LETTERS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
const INTERRUPTS = [
  { id: 'plane_overhead', name: 'Plane overhead', defaults: { enabled: false, radius_nm: 3, max_alt_ft: 10000, seconds: 20 } },
  { id: 'timer_done', name: 'Timer finished', defaults: { enabled: true } },
  { id: 'rain_soon', name: 'Rain starting', defaults: { enabled: false, minutes: 15 } },
  { id: 'iss_overhead', name: 'ISS passing over', defaults: { enabled: false } },
  { id: 'nhl_live', name: 'NHL games live', defaults: { enabled: false, screen_id: 'nhl-scoreboard', teams: [], mode: 'brief', seconds: 20 } },
  // Pi alerts
  { id: 'pi_hot', name: 'Pi running hot', group: 'pi', defaults: { enabled: true, threshold_c: 75 } },
  { id: 'pi_power', name: 'Low power', group: 'pi', defaults: { enabled: true } },
  { id: 'offline', name: 'Offline', group: 'pi', defaults: { enabled: false, minutes: 5 } },
  { id: 'disk_low', name: 'Storage low', group: 'pi', defaults: { enabled: true, percent: 10 } },
];

function randomHex(n) {
  const bytes = new Uint8Array(n / 2);
  crypto.getRandomValues(bytes);
  return [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
}

function hours(m) {
  const fmt = (t) => (t || '').replace(/^0(\d)/, '$1');
  return `${fmt(m.start)} – ${fmt(m.end)}`;
}

export function daysLabel(days) {
  const d = [...new Set(days || [])].sort();
  if (!d.length || d.length === 7) return 'Every day';
  if (d.join() === '0,1,2,3,4') return 'Weekdays';
  if (d.join() === '5,6') return 'Weekends';
  return d.map((i) => DAY_NAMES[i].slice(0, 3)).join(' ');
}

export function render(root, { params }) {
  let lu = clone(state.library.lineup);
  let savedJSON = JSON.stringify(lu);
  const open = new Set();
  const moreOpen = new Set();
  const itemKeys = new WeakMap();
  let itemSheet = null;
  const dirty = () => JSON.stringify(lu) !== savedJSON;

  const list = h('div', { class: 'moments' });
  const alwaysHost = h('div');
  const intHost = h('div', { class: 'card card-rows' });
  const piHost = h('div', { class: 'card card-rows' });
  const trHost = h('div');
  const msg = messageLine();
  const saveBar = h('div', { class: 'savebar', role: 'region', 'aria-label': 'Unsaved lineup changes', hidden: true });
  const saveBtn = h('button', { type: 'button', class: 'btn btn-primary btn-small' }, 'Save lineup');
  const discardBtn = h('button', { type: 'button', class: 'btn btn-secondary btn-small' }, 'Discard');
  saveBar.append(h('span', { class: 'savebar-text' }, 'Unsaved changes'), discardBtn, saveBtn);

  const addMoment = h('button', { type: 'button', class: 'btn btn-secondary lineup-add-schedule' }, '+ Add schedule');
  addMoment.addEventListener('click', () => {
    const m = { id: `m-${randomHex(8)}`, name: 'New schedule', start: '09:00', end: '17:00', days: [0, 1, 2, 3, 4], brightness: null, screens: [] };
    lu.moments.push(m);
    open.add(m.id);
    changed();
    requestAnimationFrame(() => document.getElementById(`name-${m.id}`)?.focus());
  });

  root.append(
    h('section', { class: 'pad intro' },
      h('h1', { class: 'page-title' }, 'Lineup'),
      h('p', { class: 'lead' }, 'Your screens play in order. Tap one to adjust its timing.')),
    h('section', { class: 'block', 'aria-labelledby': 'always-h' },
      h('h2', { id: 'always-h', class: 'section-title' }, 'Default screens'),
      h('p', { class: 'lead' }, 'Plays whenever no schedule is active.'), alwaysHost),
    h('section', { class: 'block', 'aria-labelledby': 'schedules-h' },
      h('h2', { id: 'schedules-h', class: 'section-title' }, 'Schedules'),
      h('p', { class: 'lead' }, 'Different screens for different parts of your day.'), list, addMoment),
    h('section', { class: 'block lineup-extras', 'aria-label': 'More lineup settings' },
      foldout('Live alerts', 'Flights, weather, timers and games.', intHost),
      foldout('Device alerts', 'Connection, power, temperature and storage.', piHost),
      foldout('Transitions', 'How screens switch.', trHost)),
    h('div', { class: 'pad-x' }, msg),
    saveBar);

  function foldout(title, description, body) {
    return h('details', { class: 'lineup-foldout' },
      h('summary', null, h('span', { class: 'foldout-copy' }, h('strong', null, title),
        h('span', { class: 'row-detail' }, description)), h('span', { class: 'foldout-arrow', 'aria-hidden': 'true' }, '›')),
      h('div', { class: 'foldout-body' }, body));
  }

  function changed() {
    renderAll();
  }

  function syncBar() {
    saveBar.hidden = !dirty();
    document.body.classList.toggle('has-savebar', dirty());
  }

  // ---- moment cards ----------------------------------------------------------

  function renderMoments() {
    const liveId = liveMomentId();
    list.replaceChildren(...lu.moments.map((m, mi) => {
      const isLive = m.id === liveId;
      const editing = open.has(m.id);
      const titleId = `mt-${m.id}`;
      const editBtn = h('button', { type: 'button', class: 'link-btn', 'aria-expanded': String(editing), 'aria-controls': editing ? `ed-${m.id}` : null }, editing ? 'Close' : 'Edit schedule');
      editBtn.addEventListener('click', () => { if (editing) open.delete(m.id); else open.add(m.id); renderMoments(); });
      const card = h('section', { class: `moment${isLive ? ' is-live' : ''}`, 'aria-labelledby': titleId, dataset: { id: m.id } },
        h('div', { class: 'moment-head' },
          h('div', { class: 'moment-titles' },
            h('h2', { id: titleId, class: 'moment-name' }, m.name || 'Untitled'),
            h('div', { class: 'moment-hours' }, `${hours(m)} · ${daysLabel(m.days)}`)),
          isLive ? h('span', { class: 'now-badge' }, 'Now') : null,
          editBtn),
        editing ? momentEditor(m, mi) : null,
        itemsEditor(m.screens, m.name));
      return card;
    }));
    if (!lu.moments.length) list.append(h('p', { class: 'card-note' }, 'No schedules yet. Your default screens play all day.'));
  }

  function itemKey(it) {
    if (!itemKeys.has(it)) itemKeys.set(it, nextId('queue-item'));
    return itemKeys.get(it);
  }

  function itemsEditor(items, listName) {
    const ol = h('ol', { class: 'queue-list', 'aria-label': `Screens in ${listName}` });
    items.forEach((it, i) => {
      const scr = findScreen(it.screen_id);
      const name = scr ? scr.name : 'Missing screen';
      const button = h('button', { type: 'button', id: itemKey(it), class: 'queue-entry',
        'aria-label': `Edit ${name}, position ${i + 1} in ${listName}` },
        h('span', { class: 'queue-order', 'aria-hidden': 'true' }, i + 1),
        h('span', { class: 'queue-thumb' }, scr ? screenMatrix(scr, { pitch: 2, glow: false, label: `${name} preview` }).el : '?'),
        h('span', { class: 'queue-copy' }, h('span', { class: 'queue-name' }, name),
          h('span', { class: 'queue-duration' }, `${it.seconds || 10} seconds`)),
        h('span', { class: 'queue-chevron', 'aria-hidden': 'true' }, '›'));
      button.addEventListener('click', () => editItem(items, it, listName));
      ol.append(h('li', null, button));
    });
    const add = h('button', { type: 'button', class: 'queue-add', 'aria-label': `Add a screen to ${listName}` }, '+ Add screen');
    add.addEventListener('click', () => pickScreen(listName, (sid) => {
      items.push({ screen_id: sid, seconds: 15 });
      changed();
    }));
    return h('div', { class: 'queue' },
      h('div', { class: 'queue-heading' }, h('h3', null, 'Screens'),
        h('span', { class: 'row-detail' }, items.length > 1 ? 'Plays in this order' : '')),
      items.length ? ol : h('p', { class: 'queue-empty' }, 'Add a screen to start this lineup.'), add);
  }

  function editItem(items, it, listName) {
    const scr = findScreen(it.screen_id);
    const name = scr?.name || 'Missing screen';
    const durationId = nextId('duration');
    const values = [...new Set([...Array.from({ length: 60 }, (_, i) => (i + 1) * 5), it.seconds || 10])].sort((a, b) => a - b);
    const duration = h('select', { id: durationId, class: 'input' }, values.map((seconds) =>
      h('option', { value: seconds, selected: seconds === (it.seconds || 10) }, `${seconds} seconds`)));
    duration.addEventListener('change', () => { it.seconds = Number(duration.value); changed(); });
    const i = items.indexOf(it);
    const move = (delta) => {
      const index = items.indexOf(it), next = index + delta;
      if (index < 0 || next < 0 || next >= items.length) return;
      [items[index], items[next]] = [items[next], items[index]];
      itemSheet.close(); changed();
    };
    const up = h('button', { type: 'button', class: 'btn btn-secondary', disabled: i === 0 }, 'Move earlier');
    const down = h('button', { type: 'button', class: 'btn btn-secondary', disabled: i === items.length - 1 }, 'Move later');
    up.addEventListener('click', () => move(-1)); down.addEventListener('click', () => move(1));
    const remove = h('button', { type: 'button', class: 'btn btn-danger-quiet' }, 'Remove from lineup');
    remove.addEventListener('click', () => {
      const index = items.indexOf(it);
      if (index < 0) return;
      items.splice(index, 1); itemSheet.close(); changed();
      toast(`${name} removed. Save the lineup to apply.`);
    });
    itemSheet = sheet({ title: 'Screen settings', body: [
      h('div', { class: 'queue-settings-preview' }, scr ? screenMatrix(scr, { pitch: 4, glow: false, label: `${name} preview` }).el : null,
        h('strong', null, name)),
      h('div', { class: 'field' }, h('label', { class: 'field-label', for: durationId }, 'Show for'), duration),
      h('div', { class: 'queue-move' }, up, down), remove,
      h('p', { class: 'card-note' }, 'Save the lineup to apply your changes.')],
      onClose: () => {
        itemSheet = null;
        const selector = items.includes(it) ? `#${itemKey(it)}` : `[aria-label="Add a screen to ${cssq(listName)}"]`;
        focusLater(selector);
      },
    });
  }

  function momentEditor(m, mi) {
    const nameId = `name-${m.id}`;
    const startId = nextId('start');
    const endId = nextId('end');
    const nameInput = h('input', { id: nameId, class: 'input', value: m.name, maxlength: '24' });
    nameInput.addEventListener('input', () => { m.name = nameInput.value; syncBar(); });
    // Update the card title in place: re-rendering here would run inside another
    // render's replaceChildren() when the change fires on blur (removing the input).
    nameInput.addEventListener('change', () => {
      const title = document.getElementById(`mt-${m.id}`);
      if (title) title.textContent = m.name || 'Untitled';
    });
    const start = h('input', { id: startId, type: 'time', class: 'input', value: m.start, required: true });
    const end = h('input', { id: endId, type: 'time', class: 'input', value: m.end, required: true });
    start.addEventListener('change', () => { if (start.value) { m.start = start.value; changed(); } });
    end.addEventListener('change', () => { if (end.value) { m.end = end.value; changed(); } });
    const days = h('div', { class: 'days', role: 'group', 'aria-label': 'Days' }, DAY_LETTERS.map((letter, d) => {
      const on = (m.days || []).includes(d);
      const btn = h('button', { type: 'button', class: 'day', 'aria-pressed': String(on), 'aria-label': DAY_NAMES[d] }, letter);
      btn.addEventListener('click', () => {
        const set = new Set(m.days || []);
        if (set.has(d)) set.delete(d); else set.add(d);
        m.days = [...set].sort();
        changed();
      });
      return btn;
    }));
    const ownBright = m.brightness !== null && m.brightness !== undefined;
    const brightVal = h('output', { class: 'mono-note' }, ownBright ? `${m.brightness}%` : '');
    const slider = h('input', { type: 'range', min: '1', max: '100', value: String(m.brightness || 60), class: 'range', 'aria-label': `Brightness for ${m.name}`, hidden: !ownBright });
    slider.addEventListener('input', () => { m.brightness = Number(slider.value); brightVal.textContent = `${slider.value}%`; syncBar(); });
    const brightToggle = toggle({ label: 'Custom brightness', pressed: ownBright, onChange: (v) => { m.brightness = v ? Number(slider.value) : null; changed(); } });
    const del = h('button', { type: 'button', class: 'btn btn-danger-quiet btn-small' }, 'Delete schedule');
    del.addEventListener('click', async () => {
      if (!(await confirmSheet({ title: `Delete “${m.name}”?`, text: 'Its screens stay in the gallery. Save the lineup to apply.' }))) return;
      lu.moments.splice(mi, 1);
      changed();
    });
    const upM = h('button', { type: 'button', class: 'btn btn-secondary', 'aria-label': `Move ${m.name} earlier in the list`, disabled: mi === 0 }, 'Move earlier');
    const downM = h('button', { type: 'button', class: 'btn btn-secondary', 'aria-label': `Move ${m.name} later in the list`, disabled: mi === lu.moments.length - 1 }, 'Move later');
    upM.addEventListener('click', () => { [lu.moments[mi - 1], lu.moments[mi]] = [lu.moments[mi], lu.moments[mi - 1]]; changed(); });
    downM.addEventListener('click', () => { [lu.moments[mi + 1], lu.moments[mi]] = [lu.moments[mi], lu.moments[mi + 1]]; changed(); });

    const more = foldout('More schedule options', 'Brightness, priority and deletion.', [
      h('div', { class: 'row row-flat' }, h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, 'Custom brightness'),
        h('div', { class: 'row-detail' }, 'Used when Device › Follow the lineup is on')), brightVal, brightToggle), slider,
      h('p', { class: 'card-note' }, 'If schedules overlap, the earlier one in the list is used.'),
      h('div', { class: 'queue-move' }, upM, downM), del]);
    more.open = moreOpen.has(m.id);
    more.addEventListener('toggle', () => {
      if (!more.isConnected) return;
      if (more.open) moreOpen.add(m.id); else moreOpen.delete(m.id);
    });
    return h('div', { class: 'moment-editor', id: `ed-${m.id}` },
      h('div', { class: 'field' }, h('label', { class: 'field-label', for: nameId }, 'Name'), nameInput),
      h('div', { class: 'field-pair time-pair' },
        h('div', { class: 'field' }, h('label', { class: 'field-label', for: startId }, 'Starts'), start),
        h('div', { class: 'field' }, h('label', { class: 'field-label', for: endId }, 'Ends'), end)),
      m.start === m.end ? h('p', { class: 'msg is-error' }, 'Start and end must differ.') : null,
      h('div', { class: 'field' }, h('div', { class: 'field-label' }, 'Days'), days),
      more);
  }

  function renderAlways() {
    alwaysHost.replaceChildren(h('div', { class: 'moment default-lineup' }, itemsEditor(lu.always, 'Default screens')));
  }

  // ---- interruptions & transitions ---------------------------------------------

  function renderInterrupts() {
    intHost.replaceChildren();
    piHost.replaceChildren();
    for (const def of INTERRUPTS) {
      const host = def.group === 'pi' ? piHost : intHost;
      const cfg = { ...def.defaults, ...(lu.interrupts[def.id] || {}) };
      lu.interrupts[def.id] = cfg;
      const detail = interruptDetail(def.id, cfg);
      const detailId = nextId('int');
      const row = h('div', { class: 'row' },
        h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, def.name), h('div', { class: 'row-detail', id: detailId }, detail)),
        toggle({ label: def.name, pressed: !!cfg.enabled, describedBy: detailId, onChange: (v) => { cfg.enabled = v; renderInterrupts(); syncBar(); } }));
      host.append(row);
      if (cfg.enabled) {
        const extra = interruptParams(def.id, cfg);
        if (extra) host.append(extra);
      }
    }
  }

  function interruptDetail(id, cfg) {
    const unit = state.settings?.distance_unit === 'km' ? 'km' : 'nm';
    const r = unit === 'km' ? Math.round((cfg.radius_nm || 0) * 1.852) : cfg.radius_nm;
    switch (id) {
      case 'plane_overhead': return `Within ${r} ${unit} and below ${Number(cfg.max_alt_ft).toLocaleString()} ft · show for ${cfg.seconds} s`;
      case 'timer_done': return 'Flash the panel three times';
      case 'rain_soon': return `${cfg.minutes} minutes ahead · once per hour`;
      case 'iss_overhead': return 'When the ISS is within about 1,500 km · once per pass';
      case 'nhl_live': {
        const screen = findScreen(cfg.screen_id);
        const teams = followedTeams({ ...screen?.slots?.find(s => s.block === 'nhl')?.options,
          ...(cfg.teams?.length ? { teams: cfg.teams } : {}) });
        return `${teamsLabel(teams)} · ${cfg.mode === 'game' ? 'Rotate live games' : `Starts and scores · ${cfg.seconds} s`}`;
      }
      case 'pi_hot': return `CPU at ${cfg.threshold_c}°C or more · every 10 min while hot`;
      case 'pi_power': return 'Under-voltage or throttling · every 30 min while it lasts';
      case 'offline': return `No internet for ${cfg.minutes} min · then hourly`;
      case 'disk_low': return `Less than ${cfg.percent}% of the SD card free · every 6 hours`;
      default: return '';
    }
  }

  function interruptParams(id, cfg) {
    const refresh = () => { renderInterrupts(); syncBar(); };
    if (id === 'nhl_live') {
      const screens = [...(state.catalog?.builtins || []), ...(state.library?.screens || [])]
        .filter((screen) => (screen.slots || []).some((slot) => slot.block === 'nhl'));
      const inputId = nextId('nhl-screen');
      const select = h('select', { id: inputId, class: 'input' }, screens.map((screen) => {
        return h('option', { value: screen.id, selected: screen.id === cfg.screen_id }, screen.name);
      }));
      select.addEventListener('change', () => { cfg.screen_id = select.value; refresh(); });
      const mode = chips({ label: 'NHL alert behavior', value: cfg.mode,
        choices: [{ id: 'brief', label: 'Brief alerts' }, { id: 'game', label: 'Follow live games' }],
        onChange: (value) => { cfg.mode = value; refresh(); } });
      const screenOptions = findScreen(cfg.screen_id)?.slots?.find(slot => slot.block === 'nhl')?.options || {};
      const teams = followedTeams(cfg.teams?.length ? { teams: cfg.teams } : screenOptions);
      return h('div', { class: 'sub-rows' },
        h('div', { class: 'pad-row' }, teamPicker({ value: teams,
          detail: 'Get logo scoreboards for these teams. Shared matchups appear once. Save the lineup to apply your choices.',
          onChange: value => { cfg.teams = value; refresh(); } })),
        h('div', { class: 'field pad-row nhl-mode-field' }, h('div', { class: 'field-label' }, 'When it appears'), mode),
        h('p', { class: 'card-note' }, cfg.mode === 'game'
          ? 'Rotate live games every 10 seconds, including intermissions. Return to your lineup when they finish.'
          : 'Show each game at puck drop and when its score changes. Other alerts wait their turn.'),
        cfg.mode === 'brief' ? paramRow('Show for', stepper({ label: 'seconds', value: cfg.seconds,
          min: 5, max: 120, step: 5, format: (v) => `${v} s`, onChange: (v) => { cfg.seconds = v; refresh(); } })) : null,
        h('details', { class: 'nhl-appearance pad-row' }, h('summary', {}, 'Scoreboard appearance'),
          h('div', { class: 'field' }, h('label', { class: 'field-label', for: inputId }, 'Use colors and shots setting from'), select,
            h('p', { class: 'card-note' }, 'Alerts always use team logos. Teams above override the screen’s team selection.'))));
    }
    if (id === 'plane_overhead') {
      return h('div', { class: 'sub-rows' },
        paramRow('Radius', stepper({ label: 'radius in nautical miles', value: cfg.radius_nm, min: 1, max: 25, format: (v) => `${v} nm`, onChange: (v) => { cfg.radius_nm = v; refresh(); } })),
        paramRow('Below', stepper({ label: 'maximum altitude', value: cfg.max_alt_ft, min: 1000, max: 40000, step: 1000, format: (v) => `${v / 1000}k ft`, onChange: (v) => { cfg.max_alt_ft = v; refresh(); } })),
        paramRow('Show for', stepper({ label: 'seconds', value: cfg.seconds, min: 5, max: 120, step: 5, format: (v) => `${v} s`, onChange: (v) => { cfg.seconds = v; refresh(); } })));
    }
    if (id === 'pi_hot') {
      return h('div', { class: 'sub-rows' },
        paramRow('At', stepper({ label: 'temperature in degrees Celsius', value: cfg.threshold_c, min: 55, max: 85, format: (v) => `${v}°C`, onChange: (v) => { cfg.threshold_c = v; refresh(); } })));
    }
    if (id === 'offline') {
      return h('div', { class: 'sub-rows' },
        paramRow('After', stepper({ label: 'minutes offline', value: cfg.minutes, min: 5, max: 60, step: 5, format: (v) => `${v} min`, onChange: (v) => { cfg.minutes = v; refresh(); } })));
    }
    if (id === 'disk_low') {
      return h('div', { class: 'sub-rows' },
        paramRow('Below', stepper({ label: 'percent free', value: cfg.percent, min: 5, max: 50, step: 5, format: (v) => `${v}%`, onChange: (v) => { cfg.percent = v; refresh(); } })));
    }
    if (id === 'rain_soon') {
      return h('div', { class: 'sub-rows' },
        paramRow('Warn', stepper({ label: 'minutes ahead', value: cfg.minutes, min: 5, max: 60, step: 5, format: (v) => `${v} min`, onChange: (v) => { cfg.minutes = v; refresh(); } })));
    }
    return null;
  }

  function paramRow(label, control) {
    return h('div', { class: 'row row-sub' }, h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, label)), control);
  }

  function renderTransitions() {
    trHost.replaceChildren(chips({
      label: 'Between screens', value: lu.transition, className: 'grid-4', chipClass: 'tile-btn tile-btn-sm',
      choices: state.catalog.transitions.map((t) => ({ id: t.id, label: t.name })),
      onChange: (v) => { lu.transition = v; renderMoments(); syncBar(); },
    }));
  }

  function renderAll() {
    renderMoments();
    renderAlways();
    renderInterrupts();
    renderTransitions();
    syncBar();
  }

  // ---- picker sheets -------------------------------------------------------------

  function pickScreen(target, onPick) {
    const groups = [
      { title: 'Your screens', screens: customs() },
      ...state.catalog.shelves.map((s) => ({ title: s.title, screens: s.screens.map((id) => findScreen(id)).filter(Boolean) })),
    ].filter((g) => g.screens.length);
    let s = null;
    const body = groups.map((g) => h('section', { class: 'pick-group' },
      h('h3', { class: 'eyebrow' }, g.title),
      h('ul', { class: 'pick-grid', role: 'list' }, g.screens.map((scr) => {
        const btn = h('button', { type: 'button', class: 'pick' }, screenMatrix(scr, { pitch: 3, glow: false, label: '' }).el, h('span', { class: 'pick-name' }, scr.name));
        btn.addEventListener('click', () => { s.close(); onPick(scr.id); toast(`${scr.name} added. Save the lineup to apply.`); });
        return h('li', null, btn);
      }))));
    s = sheet({ title: `Add to ${target}`, body });
  }

  function addToSheet(screenId, seconds) {
    const scr = findScreen(screenId);
    if (!scr) return;
    const targets = [{ id: '__always', name: 'Default screens', detail: 'When no schedule is active' },
      ...lu.moments.map((m) => ({ id: m.id, name: m.name, detail: `${hours(m)} · ${daysLabel(m.days)}` }))];
    let s = null;
    const body = [
      h('div', { class: 'add-preview' }, screenMatrix(scr, { pitch: 4, glow: false, label: `${scr.name} preview` }).el, h('strong', null, scr.name)),
      h('ul', { class: 'target-list', role: 'list' }, targets.map((t) => {
        const btn = h('button', { type: 'button', class: 'target' }, h('span', { class: 'target-name' }, t.name), h('span', { class: 'target-detail' }, t.detail));
        btn.addEventListener('click', async () => {
          const items = t.id === '__always' ? lu.always : lu.moments.find((m) => m.id === t.id).screens;
          items.push({ screen_id: screenId, seconds: Math.min(300, Math.max(5, Number(seconds) || 15)) });
          s.close();
          await save(null, `${scr.name} added to ${t.name}.`);
        });
        return h('li', null, btn);
      })),
    ];
    s = sheet({ title: `Add “${scr.name}” to…`, body });
  }

  // ---- saving ------------------------------------------------------------------------

  async function save(button, doneText = 'Lineup saved.') {
    for (const m of lu.moments) {
      if (!m.name.trim()) { msg.show('Every time of day needs a name.', 'error'); return; }
      if (m.start === m.end) { msg.show(`${m.name}: start and end must differ.`, 'error'); return; }
    }
    if (button) busy(button, true, 'Saving…');
    try {
      const lib = await act('save_lineup', { lineup: lu });
      lu = clone(lib.lineup);
      savedJSON = JSON.stringify(lu);
      msg.show(doneText);
      toast(doneText);
      renderAll();
    } catch (error) {
      msg.error(error);
      syncBar();
    } finally {
      if (button) busy(button, false);
    }
  }
  saveBtn.addEventListener('click', () => save(saveBtn));
  discardBtn.addEventListener('click', () => {
    lu = clone(state.library.lineup);
    savedJSON = JSON.stringify(lu);
    open.clear();
    moreOpen.clear();
    renderAll();
    msg.show('Changes discarded.');
  });

  renderAll();
  savedJSON = JSON.stringify(lu); // interrupts defaults filled in by the first render

  if (params.add) {
    const sid = params.add;
    const secs = params.seconds;
    history.replaceState(null, '', '#/lineup');
    requestAnimationFrame(() => addToSheet(sid, secs));
  }

  const unsubscribe = subscribe((what) => {
    if (what === 'status') {
      const liveId = liveMomentId();
      for (const card of list.querySelectorAll('.moment')) {
        const isLive = card.dataset.id === liveId;
        if (card.classList.contains('is-live') !== isLive) { renderMoments(); break; }
      }
    } else if (what === 'library' && !dirty()) {
      itemSheet?.close();
      lu = clone(state.library.lineup);
      renderAll();
      savedJSON = JSON.stringify(lu);
    }
  });

  return () => { itemSheet?.close(); unsubscribe(); document.body.classList.remove('has-savebar'); };
}

function cssq(s) { return String(s).replace(/["\\]/g, '\\$&'); }
function focusLater(selector) {
  requestAnimationFrame(() => { const el = document.querySelector(selector); if (el && !el.disabled) el.focus(); });
}
