// Device: power, brightness, location & time, units, data sources, pairing.

import { state, subscribe, saveSettings, findScreen, act } from './store.js';
import { createMatrix } from './matrix.js';
import { forgetKey } from './api.js';
import { h, toggle, toggleRow, stepper, messageLine, toast, busy, confirmSheet, nextId } from './ui.js';
import { togglePower } from './app.js';

export function render(root) {
  const s = () => state.settings || {};

  // ---- device card ------------------------------------------------------------
  const mini = createMatrix({ pitch: 2.5, glow: false, label: 'What the matrix shows now' });
  const showing = h('div', { class: 'device-showing' });
  const power = toggle({ label: 'Display power', pressed: s().display_enabled !== false, onChange: () => togglePower() });
  root.append(h('section', { class: 'card device-card', 'aria-label': 'Display' },
    h('div', { class: 'thumb-bezel' }, mini.el),
    h('div', { class: 'device-text' },
      h('div', { class: 'row-title strong' }, 'Desk Matrix'),
      h('div', { class: 'row-detail' }, '32 × 16 panel · Raspberry Pi'),
      showing),
    power));

  const updateDevice = () => {
    const st = state.status;
    if (st?.frame) mini.setFrame(st.frame);
    const on = s().display_enabled !== false;
    power.setAttribute('aria-pressed', String(on));
    const scr = findScreen(st?.screen_id);
    showing.textContent = !on ? 'Display off · the Pi stays online' : st ? `Showing ${scr?.name || st.screen_name || st.title || '…'}` : 'Waiting for the Pi';
    showing.classList.toggle('is-off', !on);
  };

  // ---- brightness -------------------------------------------------------------
  const bMsg = messageLine();
  const dayOut = h('output', { class: 'mono-note', for: 'day-b' }, `${s().brightness ?? 85}%`);
  const day = h('input', { id: 'day-b', type: 'range', min: '1', max: '100', value: String(s().brightness ?? 85), class: 'range' });
  day.addEventListener('input', () => { dayOut.textContent = `${day.value}%`; });
  day.addEventListener('change', () => quick({ brightness: Number(day.value) }, bMsg, 'Brightness saved.'));
  const maxStepper = stepper({ label: 'maximum brightness', value: s().brightness_max ?? 100, min: 10, max: 100, step: 5, format: (v) => `${v}%`,
    onChange: debounceSave((v) => quick({ brightness_max: v }, bMsg, 'Ceiling saved.')) });
  const nightFields = h('div', { class: 'sub-rows' });
  const renderNight = () => {
    nightFields.replaceChildren();
    if (!s().night_enabled) return;
    const from = h('input', { id: 'night-start', type: 'time', class: 'input', value: s().night_start || '22:00' });
    const until = h('input', { id: 'night-end', type: 'time', class: 'input', value: s().night_end || '07:00' });
    from.addEventListener('change', () => from.value && quick({ night_start: from.value }, bMsg, 'Night hours saved.'));
    until.addEventListener('change', () => until.value && quick({ night_end: until.value }, bMsg, 'Night hours saved.'));
    nightFields.append(
      h('div', { class: 'field-pair pad-row' },
        h('div', { class: 'field' }, h('label', { class: 'field-label', for: 'night-start' }, 'From'), from),
        h('div', { class: 'field' }, h('label', { class: 'field-label', for: 'night-end' }, 'Until'), until)),
      h('div', { class: 'row row-sub' }, h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, 'Night brightness')),
        stepper({ label: 'night brightness', value: s().night_brightness ?? 30, min: 1, max: 100, step: 1, format: (v) => `${v}%`,
          onChange: debounceSave((v) => quick({ night_brightness: v }, bMsg, 'Night brightness saved.')) })));
  };
  renderNight();
  root.append(group('Brightness', 'bri-h',
    h('div', { class: 'card card-rows' },
      h('div', { class: 'row-stack' }, h('div', { class: 'row-line' }, h('label', { for: 'day-b', class: 'row-title' }, 'Daytime'), dayOut), day),
      toggleRow({ title: 'Follow the lineup', detail: 'Each time of day can have its own level', pressed: s().brightness_follow_lineup !== false,
        onChange: (v) => quick({ brightness_follow_lineup: v }, bMsg, v ? 'Brightness follows the lineup.' : 'Brightness uses the device levels.') }),
      h('div', { class: 'row' }, h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, 'Never brighter than'), h('div', { class: 'row-detail' }, 'A ceiling for your power supply')), maxStepper),
      toggleRow({ title: 'Dim at night', detail: 'Uses a lower level during the hours you choose', pressed: !!s().night_enabled,
        onChange: async (v) => { await quick({ night_enabled: v }, bMsg, v ? 'Night dimming on.' : 'Night dimming off.'); renderNight(); } }),
      nightFields),
    bMsg));

  // ---- location & time ---------------------------------------------------------
  const lMsg = messageLine();
  const f = {};
  const field = (name, label, attrs, hint) => {
    const id = `set-${name}`;
    f[name] = h('input', { id, name, class: 'input', ...attrs, value: s()[name] ?? '' });
    return h('div', { class: 'field' }, h('label', { class: 'field-label', for: id }, label), f[name], hint ? h('p', { class: 'card-note' }, hint) : null);
  };
  const tzList = h('datalist', { id: 'tz-list' });
  try { for (const tz of Intl.supportedValuesOf('timeZone')) tzList.append(h('option', { value: tz })); } catch { /* older browsers */ }
  const geoBtn = h('button', { type: 'button', class: 'btn btn-secondary' }, 'Use this phone’s location');
  geoBtn.addEventListener('click', () => {
    if (!navigator.geolocation) { lMsg.show('This browser can’t share its location. Enter it by hand.', 'error'); return; }
    busy(geoBtn, true, 'Finding you…');
    navigator.geolocation.getCurrentPosition((pos) => {
      busy(geoBtn, false);
      f.lat.value = pos.coords.latitude.toFixed(5);
      f.lon.value = pos.coords.longitude.toFixed(5);
      lMsg.show('Location filled in. Tap Save location to use it.');
    }, (err) => {
      busy(geoBtn, false);
      lMsg.show(err.code === 1 ? 'Location permission was denied. Enter it by hand.' : 'Couldn’t get a location fix. Try again or enter it by hand.', 'error');
    }, { enableHighAccuracy: false, timeout: 15000, maximumAge: 600000 });
  });
  const tzBtn = h('button', { type: 'button', class: 'link-btn' }, 'Use this phone’s time zone');
  tzBtn.addEventListener('click', () => { f.timezone.value = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; f.timezone.focus(); });
  const iconsRow = toggleRow({ title: 'Small flight icons', detail: 'Adds a 7 × 7 mark beside aircraft names', pressed: s().icons_enabled !== false,
    onChange: (v) => quick({ icons_enabled: v }, lMsg, 'Saved.') });
  const saveLoc = h('button', { type: 'submit', class: 'btn btn-primary' }, 'Save location & time');
  const locForm = h('form', { class: 'card card-pad', novalidate: true },
    field('label', 'Short place label', { maxlength: '8', autocapitalize: 'characters', autocomplete: 'off', spellcheck: 'false', required: true }, 'Up to 8 letters or numbers. Shown on flight screens.'),
    h('div', { class: 'field-pair' },
      field('lat', 'Latitude', { type: 'number', step: 'any', min: '-90', max: '90', inputmode: 'decimal', required: true }),
      field('lon', 'Longitude', { type: 'number', step: 'any', min: '-180', max: '180', inputmode: 'decimal', required: true })),
    geoBtn,
    field('timezone', 'Time zone', { list: 'tz-list', autocomplete: 'off', spellcheck: 'false', maxlength: '64', placeholder: 'America/Edmonton', required: true }),
    tzList, tzBtn,
    h('div', { class: 'field-pair' },
      field('radius', 'Flight radius (nm)', { type: 'number', min: '1', max: '250', step: '1', inputmode: 'numeric', required: true }),
      field('max_planes', 'Planes in rotation', { type: 'number', min: '1', max: '5', step: '1', inputmode: 'numeric', required: true })),
    field('rotate', 'Seconds per plane', { type: 'number', min: '8', max: '30', step: '1', inputmode: 'numeric', required: true }),
    saveLoc, lMsg);
  locForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    for (const input of Object.values(f)) {
      if (!input.checkValidity()) { input.reportValidity(); input.focus(); return; }
    }
    const partial = {
      label: f.label.value.trim().toUpperCase(), lat: Number(f.lat.value), lon: Number(f.lon.value),
      timezone: f.timezone.value.trim(), radius: Number(f.radius.value), max_planes: Number(f.max_planes.value), rotate: Number(f.rotate.value),
    };
    busy(saveLoc, true, 'Saving…');
    try { await saveSettings(partial); lMsg.show('Saved. The display will update shortly.'); toast('Location & time saved.'); }
    catch (error) { lMsg.error(error); }
    finally { busy(saveLoc, false); }
  });
  root.append(group('Location & time', 'loc-h', locForm, h('div', { class: 'card card-rows card-gap' }, iconsRow)));

  // ---- units ------------------------------------------------------------------
  const uMsg = messageLine();
  const seg = (name, choices, label) => {
    const groupEl = h('div', { class: 'seg seg-sm', role: 'group', 'aria-label': label });
    const draw = () => groupEl.replaceChildren(...choices.map(([v, text]) => {
      const btn = h('button', { type: 'button', class: 'seg-btn', 'aria-pressed': String((s()[name] || choices[0][0]) === v) }, text);
      btn.addEventListener('click', async () => { await quick({ [name]: v }, uMsg, `${label} set to ${text}.`); draw(); });
      return btn;
    }));
    draw();
    return groupEl;
  };
  root.append(group('Units', 'units-h', h('div', { class: 'card card-rows' },
    h('div', { class: 'row' }, h('div', { class: 'row-title' }, 'Temperature'), seg('temp_unit', [['C', '°C'], ['F', '°F']], 'Temperature')),
    h('div', { class: 'row' }, h('div', { class: 'row-title' }, 'Distance'), seg('distance_unit', [['nm', 'nm'], ['km', 'km']], 'Distance'))), uMsg));

  // ---- data sources -------------------------------------------------------------
  const sourcesHost = h('div', { class: 'card card-rows' });
  const calMsg = messageLine();
  const calInput = h('input', { id: 'ics', type: 'url', class: 'input', value: s().calendar_ics_url || '', maxlength: '512', placeholder: 'https://…/basic.ics', autocomplete: 'off', spellcheck: 'false' });
  const calSave = h('button', { type: 'submit', class: 'btn btn-secondary btn-small' }, 'Save');
  const calForm = h('form', { class: 'sub-form', novalidate: true },
    h('label', { class: 'field-label', for: 'ics' }, 'Calendar ICS link'),
    h('div', { class: 'input-row' }, calInput, calSave),
    h('p', { class: 'card-note' }, 'A private iCal link (Google Calendar › Settings › Secret address). It stays on the Pi. Leave empty to turn off.'),
    calMsg);
  calForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    const url = calInput.value.trim();
    if (url && !/^https?:\/\/\S+$/i.test(url)) { calMsg.show('Use an http:// or https:// link.', 'error'); return; }
    busy(calSave, true, 'Saving…');
    try { await saveSettings({ calendar_ics_url: url }); calMsg.show(url ? 'Calendar link saved.' : 'Calendar turned off.'); }
    catch (error) { calMsg.error(error); }
    finally { busy(calSave, false); }
  });

  const feedsHost = h('div', { class: 'feeds' });
  const renderSources = () => {
    const age = state.status?.data_age;
    const ageOf = (key) => {
      if (age === null || age === undefined) return null;
      if (typeof age === 'number') return age;
      const v = age[key];
      return typeof v === 'number' ? v : null;
    };
    const stateText = (key, fallback) => {
      const a = ageOf(key);
      if (a === null) return [fallback, 'muted'];
      if (a < 120) return ['Live', 'ok'];
      if (a < 3600) return [`${Math.round(a / 60)} min ago`, a < 1800 ? 'ok' : 'warn'];
      return [`${Math.round(a / 3600)} h ago`, 'warn'];
    };
    const row = (name, via, key, fallback) => {
      const [text, cls] = stateText(key, fallback);
      return h('div', { class: 'row' },
        h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, name), h('div', { class: 'row-detail' }, via)),
        h('span', { class: `source-state is-${cls}` }, h('i', { 'aria-hidden': 'true' }), text));
    };
    sourcesHost.replaceChildren(
      row('Aircraft', [link('https://adsb.fi/', 'adsb.fi'), ' positions · ', link('https://www.adsbdb.com/', 'ADSBdb'), ' routes'], 'aircraft', 'When needed'),
      row('Weather', [link('https://open-meteo.com/', 'Open-Meteo'), ' · uses your location'], 'weather', 'When needed'),
      row('Airport METAR', [link('https://aviationweather.gov/', 'aviationweather.gov')], 'metar', 'When needed'),
      row('Sun & ISS', ['Sun calculated on the Pi · ISS from ', link('https://wheretheiss.at/', 'wheretheiss.at')], 'iss', 'Offline'),
      row('Calendar', 'Optional · stays on the Pi', 'calendar', s().calendar_ics_url ? 'Set up' : 'Off'),
      calForm,
      h('div', { class: 'row-stack' }, h('div', { class: 'row-line' }, h('div', { class: 'row-title' }, 'Custom JSON feeds'), h('span', { class: 'mono-note' }, `${(state.library?.feeds || []).length} / 10`)),
        h('p', { class: 'card-note' }, 'Transit, scores, prices, now playing: any JSON URL. Pick a feed in a Feed or Sparkline block.'), feedsHost));
    renderFeeds();
  };

  let editingFeed = null;
  const renderFeeds = () => {
    const feeds = state.library?.feeds || [];
    feedsHost.replaceChildren(...feeds.map((feed) => editingFeed === feed.id ? feedForm(feed) : feedRow(feed)));
    if (editingFeed === 'new') feedsHost.append(feedForm({ id: '', name: '', url: '', path: '', series_path: '', prefix: '', suffix: '', interval_s: 300 }));
    else if (feeds.length < 10) {
      const add = h('button', { type: 'button', class: 'btn btn-dashed btn-small' }, '+ Add a feed');
      add.addEventListener('click', () => { editingFeed = 'new'; renderFeeds(); feedsHost.querySelector('input')?.focus(); });
      feedsHost.append(add);
    }
  };
  const feedRow = (feed) => {
    const live = state.status?.feeds?.[feed.id];
    const edit = h('button', { type: 'button', class: 'link-btn', 'aria-label': `Edit ${feed.name}` }, 'Edit');
    edit.addEventListener('click', () => { editingFeed = feed.id; renderFeeds(); });
    return h('div', { class: 'feed-row' },
      h('div', { class: 'row-text' }, h('div', { class: 'row-title' }, feed.name || feed.id),
        h('div', { class: 'row-detail ellipsis' }, `${feed.path ? feed.path + ' · ' : ''}every ${Math.round((feed.interval_s || 300) / 60)} min${live?.error ? ' · ' + live.error : ''}`)),
      edit);
  };
  const feedForm = (feed) => {
    const fm = messageLine();
    const ids = {};
    const input = (name, label, attrs = {}) => {
      ids[name] = nextId(`feed-${name}`);
      const el = h('input', { id: ids[name], name, class: 'input', value: feed[name] ?? '', autocomplete: 'off', spellcheck: 'false', ...attrs });
      return h('div', { class: 'field' }, h('label', { class: 'field-label', for: ids[name] }, label), el);
    };
    const save = h('button', { type: 'submit', class: 'btn btn-primary btn-small' }, 'Save feed');
    const cancel = h('button', { type: 'button', class: 'btn btn-secondary btn-small' }, 'Cancel');
    const del = feed.id ? h('button', { type: 'button', class: 'btn btn-danger-quiet btn-small' }, 'Delete') : null;
    const form = h('form', { class: 'feed-form', novalidate: true, 'aria-label': feed.id ? `Edit ${feed.name}` : 'New feed' },
      input('name', 'Name', { maxlength: '24', required: true, placeholder: 'Bus 201' }),
      input('url', 'JSON URL', { type: 'url', maxlength: '512', required: true, placeholder: 'https://example.com/data.json' }),
      h('div', { class: 'field-pair' },
        input('path', 'Value path', { maxlength: '128', placeholder: 'data.0.minutes' }),
        input('series_path', 'Series path (optional)', { maxlength: '128', placeholder: 'data.history' })),
      h('div', { class: 'field-pair' },
        input('prefix', 'Prefix', { maxlength: '8', placeholder: '$' }),
        input('suffix', 'Suffix', { maxlength: '8', placeholder: ' MIN' })),
      input('interval_s', 'Check every (seconds)', { type: 'number', min: '60', max: '86400', step: '1', inputmode: 'numeric' }),
      h('div', { class: 'btn-row' }, cancel, del, save), fm);
    cancel.addEventListener('click', () => { editingFeed = null; renderFeeds(); });
    if (del) del.addEventListener('click', async () => {
      if (!(await confirmSheet({ title: `Delete “${feed.name}”?`, text: 'Blocks that use this feed will show NO DATA.' }))) return;
      try { await act('delete_feed', { feed_id: feed.id }); editingFeed = null; renderFeeds(); toast('Feed deleted.'); } catch (error) { fm.error(error); }
    });
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      const val = (n) => form.elements[n].value.trim();
      if (!val('name')) { fm.show('Give the feed a name.', 'error'); form.elements.name.focus(); return; }
      if (!/^https?:\/\/\S+$/i.test(val('url'))) { fm.show('Use an http:// or https:// URL.', 'error'); form.elements.url.focus(); return; }
      const interval = Math.max(60, Number(val('interval_s')) || 300);
      const payload = { id: feed.id || '', name: val('name'), url: val('url'), path: val('path'), series_path: val('series_path'),
        prefix: form.elements.prefix.value, suffix: form.elements.suffix.value, interval_s: interval };
      busy(save, true, 'Saving…');
      try { await act('save_feed', { feed: payload }); editingFeed = null; renderFeeds(); toast('Feed saved.'); }
      catch (error) { fm.error(error); busy(save, false); }
    });
    return form;
  };
  renderSources();
  root.append(group('Data sources', 'src-h', sourcesHost));

  // ---- this browser ---------------------------------------------------------------
  const forget = h('button', { type: 'button', class: 'btn btn-danger-outline' }, 'Forget this browser');
  forget.addEventListener('click', async () => {
    if (!(await confirmSheet({ title: 'Forget this browser?', text: 'You will need the pairing key to connect again.', confirmLabel: 'Forget' }))) return;
    forgetKey();
    location.hash = '#/';
    location.reload();
  });
  root.append(group('This browser', 'br-h', h('div', { class: 'card card-pad' },
    h('div', { class: 'row-title' }, 'Paired with a key'),
    h('div', { class: 'row-detail' }, 'The pairing key stays in this browser tab only. The settings page is private to your network.'),
    forget)));

  updateDevice();
  let lastAgeKey = '';
  const unsubscribe = subscribe((what) => {
    if (what === 'status' || what === 'settings') updateDevice();
    if (what === 'status') {
      const key = JSON.stringify([state.status?.data_age, state.status?.feeds]);
      if (key !== lastAgeKey && !feedsHost.querySelector('form') && !calForm.contains(document.activeElement)) { lastAgeKey = key; renderSources(); }
    }
    if (what === 'library') renderFeeds();
  });
  return () => unsubscribe();
}

function group(title, id, ...children) {
  return h('section', { class: 'group', 'aria-labelledby': id }, h('h2', { id, class: 'eyebrow group-title' }, title), ...children);
}

function link(href, text) {
  return h('a', { href, target: '_blank', rel: 'noopener noreferrer' }, text);
}

async function quick(partial, msg, okText) {
  try {
    await saveSettings(partial);
    msg.show(okText);
  } catch (error) {
    msg.error(error);
  }
}

function debounceSave(fn, ms = 500) {
  let t = 0;
  return (v) => { clearTimeout(t); t = setTimeout(() => fn(v), ms); };
}
