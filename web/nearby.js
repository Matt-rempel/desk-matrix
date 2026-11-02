// Nearby aircraft rows shared by the gallery and the flight editor.
import { h } from './ui.js';
import { api } from './api.js';

export function planeCredits() {
  return h('p', { class: 'credit' }, 'Positions: ',
    h('a', { href: 'https://adsb.fi/', target: '_blank', rel: 'noopener noreferrer' }, 'adsb.fi'),
    ' · Routes: ', h('a', { href: 'https://www.adsbdb.com/', target: '_blank', rel: 'noopener noreferrer' }, 'ADSBdb'),
    '. Route progress is approximate.');
}

export function planeList(planes, { distanceUnit = 'nm', action = 'Follow', onChoose, selected = '' } = {}) {
  const unit = distanceUnit === 'km' ? 'km' : 'NM';
  return h('ul', { class: 'plane-list' }, planes.map((plane) => {
    const distance = plane.distance_nm == null ? NaN : Number(plane.distance_nm);
    const shownDistance = Number.isFinite(distance) ? Math.round(unit === 'km' ? distance * 1.852 : distance) : '?';
    const button = h('button', { type: 'button', class: 'btn btn-small btn-secondary',
      'aria-label': `${action} ${plane.callsign}`, dataset: { callsign: plane.callsign },
      'aria-pressed': action === 'Use' ? String(plane.callsign === selected) : null,
    }, action === 'Use' && plane.callsign === selected ? 'Selected' : action);
    button.addEventListener('click', async () => {
      button.disabled = true;
      try { await onChoose(plane); } finally { button.disabled = false; }
    });
    return h('li', { class: 'plane' },
      h('div', null, h('strong', null, plane.callsign || 'Unknown'),
        h('small', null, `${plane.route ? plane.route + ' · ' : ''}${shownDistance} ${unit} · ${plane.altitude_ft != null ? Number(plane.altitude_ft).toLocaleString() + ' ft' : '? ft'}`)),
      button);
  }));
}

export function nearbyPicker({ distanceUnit, selected, onChoose }) {
  const count = h('span', { class: 'mono-note' }, '…');
  const note = h('p', { class: 'card-note', role: 'status', 'aria-live': 'polite' }, 'Looking for nearby planes…');
  const list = h('div');
  const refresh = h('button', { type: 'button', class: 'btn btn-small btn-secondary' }, 'Refresh planes');
  const picker = h('details', { class: 'card nearby flight-picker', open: true },
    h('summary', null, h('span', null, 'Planes nearby'), count),
    h('p', { class: 'card-note' }, 'Tap Use to fill in this screen’s callsign. Save when you’re ready.'),
    note, list, refresh, planeCredits());
  let timer;
  let loading = false;
  let rendered = '';

  function syncSelection() {
    for (const button of list.querySelectorAll('button')) {
      const active = button.dataset.callsign === selected();
      button.setAttribute('aria-pressed', String(active));
      button.textContent = active ? 'Selected' : 'Use';
    }
  }

  async function update() {
    clearTimeout(timer);
    if (!picker.isConnected || !picker.open || loading) return;
    loading = refresh.disabled = true;
    let delay = 20000;
    try {
      const result = await api.nearby();
      if (!picker.isConnected) return;
      const planes = result.planes || [];
      const signature = JSON.stringify(planes);
      if (signature !== rendered) {
        rendered = signature;
        list.replaceChildren(planeList(planes, { distanceUnit, action: 'Use', selected: selected(),
          onChoose: (plane) => { onChoose(plane.callsign); syncSelection(); } }));
      }
      count.textContent = String(planes.length);
      note.textContent = result.state === 'error' ? 'Could not refresh the flight feed. Try again shortly.'
        : result.state === 'checking' ? 'Looking for nearby planes…'
          : planes.length ? '' : 'No planes in range right now. You can enter a flight or callsign below.';
      note.hidden = !note.textContent;
      if (result.state === 'checking') delay = 2000;
    } catch (error) {
      if (picker.isConnected) { note.hidden = false; note.textContent = error.message; }
    } finally {
      loading = refresh.disabled = false;
      if (picker.isConnected && picker.open) timer = setTimeout(update, delay);
    }
  }
  refresh.addEventListener('click', update);
  picker.addEventListener('toggle', () => { if (picker.open) update(); else clearTimeout(timer); });
  queueMicrotask(update);
  return { el: picker, syncSelection };
}
