import assert from 'node:assert/strict';
import test from 'node:test';

const KEY = 'a'.repeat(64);
const NAME = 'flightboard-key';
let moduleNumber = 0;

test('NHL team picker keeps legacy single-team choices and describes multiple teams', async () => {
  const { followedTeams, teamsLabel } = await import('./web/nhl-teams.js');
  assert.deepEqual(followedTeams({ team: 'EDM', teams: [] }), ['EDM']);
  assert.deepEqual(followedTeams({ team: 'CGY', teams: ['EDM', 'VAN', 'EDM'] }), ['EDM', 'VAN']);
  assert.equal(teamsLabel(['CGY', 'EDM']), 'CGY, EDM');
  assert.equal(teamsLabel(['CGY', 'EDM', 'VAN', 'SJS', 'TOR']), 'CGY, EDM, VAN +2');
});

test('NHL clocks opt into live previews and scores never reuse a cached frame', async () => {
  const { hasLiveClock } = await import('./web/matrix.js');
  const screen = { layout: 'full', slots: [{ block: 'nhl', options: { team: 'CGY', display: 'logos' } }] };
  assert.equal(hasLiveClock(screen), true);
  assert.equal(hasLiveClock({ slots: [{ block: 'text' }] }), false);
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();api.setKey(KEY);
  const previous = globalThis.fetch;let calls = 0;
  globalThis.fetch = async () => ({ ok: true, status: 200,
    json: async () => ({ frames: [(++calls === 1 ? 'a' : 'b').repeat(12288)] }) });
  try {
    const first = await api.preview(screen);
    assert.equal(api.cachedPreview(screen), null);
    const second = await api.preview(screen);
    assert.notEqual(first, second);
    assert.equal(calls, 2);
  } finally { globalThis.fetch = previous; }
});

test('font and size changes preserve the other choice and legacy screen options', async () => {
  const { fontSettings, chooseFont } = await import('./web/fonts.js');
  const legacy = { display: ['standard', 'xl'], block: ['block', 'auto'], max: ['standard', 'max'],
    '3x5': ['standard', 'tiny'] };
  for (const [font, [family, size]] of Object.entries(legacy)) {
    const options = { font, colon_blink: true };
    assert.deepEqual(fontSettings(options, legacy), { family, size });
    assert.deepEqual(options, { font, colon_blink: true });
    chooseFont(options, { family: 'outline' }, legacy);
    assert.deepEqual(fontSettings(options, legacy), { family: 'outline', size });
    chooseFont(options, { size: 'max' }, legacy);
    assert.deepEqual(fontSettings(options, legacy), { family: 'outline', size: 'max' });
    assert.equal(options.font, font);
    assert.equal(options.colon_blink, true);
  }
});

test('retired palettes remain resolvable without appearing in either picker', async () => {
  const { normalizeCatalog } = await import('./web/store.js');
  const catalog = normalizeCatalog({
    palettes: { aurora: { name: 'Aurora', primary: ['#53F5C8', '#8B9CFF'] } },
    legacy_palettes: { paper: { name: 'Paper', primary: '#F4F2EE' },
      night: { name: 'Night red', primary: '#FF3B2F' } },
  });
  assert.deepEqual(catalog.palettes.map((p) => p.id), ['aurora']);
  assert.equal(catalog.paletteById.get('paper').primary, '#F4F2EE');
  assert.equal(catalog.paletteById.get('night').primary, '#FF3B2F');
});

function memoryStorage() {
  const entries = new Map();
  return {
    getItem: (name) => entries.get(name) ?? null,
    setItem: (name, value) => entries.set(name, String(value)),
    removeItem: (name) => entries.delete(name),
  };
}

function blockedStorage() {
  const blocked = () => { throw new Error('Storage unavailable'); };
  return { getItem: blocked, setItem: blocked, removeItem: blocked };
}

function loadApi() {
  moduleNumber += 1;
  return import(`./web/api.js?storage-test=${moduleNumber}`);
}

test('pairing survives a new browser session', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();
  api.setKey(KEY);
  assert.equal(localStorage.getItem(NAME), KEY);
  assert.equal(sessionStorage.getItem(NAME), null);

  globalThis.sessionStorage = memoryStorage();
  const reopened = await loadApi();
  assert.equal(reopened.hasKey(), true);
  assert.equal(reopened.getKey(), KEY);
});

test('old session pairing migrates to persistent storage', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  sessionStorage.setItem(NAME, KEY);
  const api = await loadApi();
  assert.equal(api.hasKey(), true);
  assert.equal(localStorage.getItem(NAME), KEY);
  assert.equal(sessionStorage.getItem(NAME), null);
});

test('forgetting clears persistent and legacy storage', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();
  api.setKey(KEY);
  sessionStorage.setItem(NAME, KEY);
  api.forgetKey();
  assert.equal(api.hasKey(), false);
  assert.equal(localStorage.getItem(NAME), null);
  assert.equal(sessionStorage.getItem(NAME), null);
  assert.equal((await loadApi()).hasKey(), false);
});

test('blocked persistent storage keeps a session fallback', async () => {
  globalThis.localStorage = blockedStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();
  api.setKey(KEY);
  assert.equal(sessionStorage.getItem(NAME), KEY);
  assert.equal((await loadApi()).hasKey(), true);
});

test('forgetting in another tab reloads an open paired tab', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  let storageHandler;
  let reloads = 0;
  globalThis.window = { addEventListener: (name, callback) => {
    if (name === 'storage') storageHandler = callback;
  } };
  globalThis.location = { reload: () => { reloads += 1; } };
  try {
    const api = await loadApi();
    api.setKey(KEY);
    localStorage.removeItem(NAME);
    storageHandler({ key: NAME, newValue: null });
    assert.equal(reloads, 1);
    assert.equal(sessionStorage.getItem(NAME), null);
  } finally {
    delete globalThis.window;
    delete globalThis.location;
  }
});

test('animated preview requests a fresh frame at the selected elapsed time', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();
  api.setKey(KEY);
  const originalFetch = globalThis.fetch;
  let sent;
  globalThis.fetch = async (path, init) => {
    sent = { path, init };
    return { ok: true, status: 200, json: async () => ({ frames: ['f'.repeat(12288)] }) };
  };
  try {
    const screen = { layout: 'full', slots: [{ block: 'time', options: { colon_blink: true } }],
      style: { motion: 'slide' } };
    assert.equal(await api.previewFrame(screen, 0.2), 'f'.repeat(12288));
    assert.equal(sent.path, '/api/preview');
    assert.equal(sent.init.headers['X-Flightboard-Key'], KEY);
    assert.deepEqual(JSON.parse(sent.init.body), {
      screens: [api.previewable(screen)], elapsed: 0.2, animate: true,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test('follow-flight previews refresh after a check instead of caching a missing flight', async () => {
  globalThis.localStorage = memoryStorage();
  globalThis.sessionStorage = memoryStorage();
  const api = await loadApi();
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {
    requests += 1;
    return { ok: true, status: 200, json: async () => ({ frames: [String(requests).repeat(12288)] }) };
  };
  try {
    const screen = { layout: 'full', slots: [{ block: 'flight', options: { source: 'follow', callsign: 'WS2231' } }] };
    assert.equal(await api.preview(screen), '1'.repeat(12288));
    assert.equal(api.cachedPreview(screen), null);
    assert.equal(await api.preview(screen), '2'.repeat(12288));
    assert.equal(requests, 2);
  } finally { globalThis.fetch = originalFetch; }
});
