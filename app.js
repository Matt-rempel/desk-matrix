const form = document.querySelector('#settings-form');
const message = document.querySelector('#message');
const pairing = document.querySelector('#pairing');
const controls = document.querySelector('#controls');
const powerButton = document.querySelector('#power-button');
const powerMessage = document.querySelector('#power-message');
let key = sessionStorage.getItem('flightboard-key') || '';
let savedSettings = null;
if (/^#[0-9a-fA-F]{64}$/.test(location.hash)) {
  key = location.hash.slice(1);
  sessionStorage.setItem('flightboard-key', key);
  history.replaceState(null, '', location.pathname + location.search);
}
function apiFetch(path, options = {}) {
  return fetch(path, {...options, headers: {...options.headers, 'X-Flightboard-Key': key}});
}
const fieldNames = ['label', 'lat', 'lon', 'radius', 'flight', 'max_planes', 'rotate',
  'brightness', 'night_start', 'night_end', 'night_brightness', 'timezone',
  'top_color', 'bottom_color', 'accent_color'];
const numberFields = new Set(['lat', 'lon', 'radius', 'max_planes', 'rotate', 'brightness', 'night_brightness']);

function setMessage(text, error = false) {
  message.textContent = text;
  message.classList.toggle('error', error);
}
function showPowerState(enabled) {
  powerButton.textContent = enabled ? 'Turn display off' : 'Turn display on';
  powerButton.disabled = false;
}

function mode() { return form.querySelector('input[name="mode"]:checked').value; }
function showConditionalFields() {
  document.querySelector('#flight-field').hidden = mode() !== 'flight';
  document.querySelector('#night-fields').hidden = !form.elements.night_enabled.checked;
  document.querySelector('#brightness-value').textContent = `${form.elements.brightness.value}%`;
}
function applySettings(data) {
  for (const name of fieldNames) form.elements[name].value = data[name] ?? '';
  form.querySelector(`input[name="mode"][value="${data.mode}"]`).checked = true;
  form.elements.night_enabled.checked = data.night_enabled;
  form.elements.icons_enabled.checked = data.icons_enabled;
  showPowerState(data.display_enabled);
  showConditionalFields();
}
function collectSettings() {
  const settings = { mode: mode(), night_enabled: form.elements.night_enabled.checked,
    icons_enabled: form.elements.icons_enabled.checked };
  for (const name of fieldNames) {
    const value = form.elements[name].value;
    settings[name] = numberFields.has(name) ? Number(value) : value;
  }
  return settings;
}
async function saveSettings(settings) {
  const response = await apiFetch('/api/settings', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not save settings');
  savedSettings = data;
  applySettings(data);
  setMessage('Saved. The display will update shortly.');
}

form.addEventListener('change', showConditionalFields);
form.elements.brightness.addEventListener('input', showConditionalFields);
powerButton.addEventListener('click', async () => {
  if (!savedSettings) return;
  powerButton.disabled = true;
  powerMessage.textContent = 'Updating…';
  try {
    const response = await apiFetch('/api/display', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({display_enabled: !savedSettings.display_enabled}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not change display power');
    savedSettings.display_enabled = data.display_enabled;
    showPowerState(data.display_enabled);
    powerMessage.textContent = data.display_enabled ? 'Display is on.' : 'Display is off.';
  } catch (error) {
    powerMessage.textContent = error.message;
  } finally {
    powerButton.disabled = false;
  }
});
form.addEventListener('submit', async event => {
  event.preventDefault();
  const button = document.querySelector('#save');
  button.disabled = true;
  setMessage('Saving…');
  try { await saveSettings(collectSettings()); }
  catch (error) { setMessage(error.message, true); }
  finally { button.disabled = false; }
});

async function refreshStatus() {
  if (!key) return;
  try {
    const response = await apiFetch('/api/status');
    const data = await response.json();
    if (!response.ok) throw new Error('Status unavailable');
    const fresh = data.updated_at && Date.now() - new Date(data.updated_at).getTime() < 45000;
    document.querySelector('#connection').textContent = !fresh ? 'Display starting' :
      data.state === 'off' ? 'Display off' : data.state === 'delayed' ? 'Feed delayed' : 'Pi online';
    document.querySelector('#connection').classList.toggle('online', fresh &&
      (data.state === 'live' || data.state === 'off'));
    document.querySelector('#active-title').textContent = data.title || 'Starting…';
    document.querySelector('#active-detail').textContent = data.detail || 'Waiting for flight data';
    const progress = document.querySelector('#flight-progress');
    progress.hidden = data.state === 'off' || data.mode !== 'flight' || data.progress_percent == null;
    if (!progress.hidden) {
      document.querySelector('#progress-bar').value = data.progress_percent;
      document.querySelector('#progress-caption').textContent = `${data.progress_percent}% of route · approximate`;
    }
    document.querySelector('#freshness').textContent = data.updated_at
      ? `Updated ${new Date(data.updated_at).toLocaleTimeString()}` : '';
    document.querySelector('#nearby-card').hidden = data.mode === 'clock';
    const list = document.querySelector('#planes');
    list.replaceChildren();
    if (!data.nearby?.length) {
      const empty = document.createElement('p'); empty.className = 'empty';
      empty.textContent = 'No nearby aircraft in the latest update.'; list.append(empty);
    } else {
      for (const plane of data.nearby) {
        const row = document.createElement('div'); row.className = 'plane';
        const ident = document.createElement('div'); ident.className = 'ident';
        const name = document.createElement('strong'); name.textContent = plane.callsign;
        const info = document.createElement('small');
        info.textContent = `${Math.round(plane.distance_nm)} NM away · ${plane.altitude_ft ?? '?'} ft`;
        ident.append(name, info);
        const button = document.createElement('button'); button.type = 'button';
        button.textContent = 'Follow';
        button.addEventListener('click', async () => {
          const settings = {...savedSettings, mode: 'flight', flight: plane.callsign};
          try { await saveSettings(settings); } catch (error) { setMessage(error.message, true); }
        });
        row.append(ident, button); list.append(row);
      }
    }
  } catch (error) {
    document.querySelector('#connection').textContent = 'Pi offline';
    document.querySelector('#connection').classList.remove('online');
  }
}

async function connect() {
  const response = await apiFetch('/api/settings');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error);
  savedSettings = data;
  applySettings(data);
  pairing.hidden = true;
  controls.hidden = false;
  sessionStorage.setItem('flightboard-key', key);
  refreshStatus();
}
document.querySelector('#pairing-form').addEventListener('submit', async event => {
  event.preventDefault();
  key = document.querySelector('#pairing-key').value.trim();
  try { await connect(); }
  catch (error) { document.querySelector('#pairing-error').textContent = error.message; }
});
if (key) connect().catch(error => {
  sessionStorage.removeItem('flightboard-key');
  key = '';
  document.querySelector('#pairing-error').textContent = error.message;
});
setInterval(refreshStatus, 5000);
