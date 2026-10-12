import assert from 'node:assert/strict';
import test from 'node:test';

const KEY = 'a'.repeat(64);
const NAME = 'flightboard-key';
let moduleNumber = 0;

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
