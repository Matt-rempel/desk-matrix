// Gallery: live hero, lineup browsing, filter chips and shelves of screens.

import { state, subscribe, findScreen, builtins, customs, activeItems, pinnedId, describeScreen } from './store.js';
import { createMatrix, screenMatrix } from './matrix.js';
import { preview, cachedPreview } from './api.js';
import { h, toast } from './ui.js';
import { focusControls, followFlight, unpin, showNow } from './controls.js';

let filter = 'all';

export function render(root) {
  let browse = null; // index into the lineup while browsing, null = follow live
  const heroMatrix = createMatrix({ pitch: 10, glow: true, label: 'What the matrix shows now' });
  const count = h('span', { class: 'mono-note' });
  const name = h('div', { class: 'hero-name' });
  const meta = h('div', { class: 'hero-meta' });
  const dots = h('div', { class: 'dots', 'aria-hidden': 'true' });
  const prev = h('button', { type: 'button', class: 'round-btn', 'aria-label': 'Previous screen in lineup' }, '‹');
  const next = h('button', { type: 'button', class: 'round-btn', 'aria-label': 'Next screen in lineup' }, '›');
  const extra = h('div', { class: 'hero-extra' });
  const customizeLink = h('a', { class: 'btn btn-primary', href: '#/' }, 'Customize');
  const newLink = h('a', { class: 'btn btn-secondary', href: '#/build' }, '+ New screen');
  const nearby = h('div', { class: 'nearby-wrap' });
  const shelvesEl = h('div', { class: 'shelves' });
  const chipsEl = h('div', { class: 'chip-scroll', role: 'group', 'aria-label': 'Filter screens' });
  const bezel = h('div', { class: 'bezel' }, heroMatrix.el);
  const swipeHint = h('p', { class: 'sr-only', 'aria-live': 'polite' });

  root.append(
    h('section', { class: 'hero', 'aria-labelledby': 'now-title' },
      h('div', { class: 'hero-top' }, h('h1', { id: 'now-title', class: 'eyebrow' }, 'On your desk now'), count),
      bezel,
      h('div', { class: 'hero-nav' }, prev, h('div', { class: 'hero-caption' }, name, meta, dots), next),
      extra,
      h('div', { class: 'btn-row' }, customizeLink, newLink),
      swipeHint),
    nearby,
    chipsEl,
    shelvesEl);

  const items = () => activeItems();
  const liveId = () => state.status?.screen_id || pinnedId() || null;

  function liveIndex() {
    const list = items();
    const id = liveId();
    return list.findIndex((it) => it.screen_id === id);
  }

  function shown() {
    const list = items();
    if (browse !== null && list[browse]) {
      return { id: list[browse].screen_id, item: list[browse], index: browse, live: list[browse].screen_id === liveId() };
    }
    const index = liveIndex();
    return { id: liveId(), item: index >= 0 ? list[index] : null, index, live: true };
  }

  function step(delta) {
    const list = items();
    if (!list.length) return;
    const from = browse !== null ? browse : Math.max(0, liveIndex());
    browse = (from + delta + list.length) % list.length;
    if (list[browse].screen_id === liveId()) browse = null;
    renderHero();
    const s = shown();
    const scr = findScreen(s.id);
    swipeHint.textContent = `${scr ? scr.name : 'Screen'}${s.live ? ', live now' : ', preview'}`;
  }
  prev.addEventListener('click', () => step(-1));
  next.addEventListener('click', () => step(1));

  // Swipe on the hero to browse.
  let touchX = null;
  bezel.addEventListener('touchstart', (e) => { touchX = e.touches[0].clientX; }, { passive: true });
  bezel.addEventListener('touchend', (e) => {
    if (touchX === null) return;
    const dx = e.changedTouches[0].clientX - touchX;
    touchX = null;
    if (Math.abs(dx) > 40) step(dx < 0 ? 1 : -1);
  });

  let lastExtraKey = '';
  function renderHero() {
    const list = items();
    const s = shown();
    const screen = findScreen(s.id);
    const pinned = pinnedId();
    prev.disabled = next.disabled = list.length < 2;

    if (s.live) {
      if (state.status?.frame) heroMatrix.setFrame(state.status.frame);
      heroMatrix.el.classList.toggle('is-off', state.settings?.display_enabled === false);
    } else if (screen) {
      heroMatrix.el.classList.remove('is-off');
      const cached = cachedPreview(screen);
      if (cached) heroMatrix.setFrame(cached);
      else preview(screen).then((f) => { if (shown().id === screen.id) heroMatrix.setFrame(f); }).catch(() => {});
    }
    heroMatrix.setLabel(`${s.live ? 'Live' : 'Preview'}: ${screen ? screen.name : 'matrix'}`);

    name.textContent = screen ? screen.name : (state.status?.screen_name || state.status?.title || 'Starting…');
    const family = screen ? describeScreen(screen) : '';
    let detail;
    if (s.live && pinned && pinned === s.id) detail = 'Pinned · stays until you unpin';
    else if (s.live && state.settings?.display_enabled === false) detail = 'Display is off';
    else if (s.item) detail = `${family ? family + ' · ' : ''}shows for ${s.item.seconds || 10} s`;
    else detail = family || (state.statusError ? 'Can’t reach the Pi' : 'Live on the matrix');
    meta.textContent = s.live ? detail : `Preview · ${detail}`;

    if (pinned && s.live && pinned === s.id) count.textContent = 'Pinned';
    else if (list.length && s.index >= 0) count.textContent = `${s.index + 1} of ${list.length} in lineup`;
    else count.textContent = list.length ? 'Interruption' : 'Lineup is empty';

    dots.replaceChildren(...list.map((_, i) => h('i', { class: i === s.index ? 'on' : '' })));
    customizeLink.href = s.id ? `#/customize/${encodeURIComponent(s.id)}` : '#/build';
    customizeLink.classList.toggle('is-disabled', !s.id);

    // Controls below the hero: unpin, timer, habit, show-this-now.
    const t = screen ? JSON.stringify([state.library?.timers, state.library?.habits]) : '';
    const key = [s.id, s.live, pinned, t].join('|');
    if (key !== lastExtraKey) {
      lastExtraKey = key;
      extra.replaceChildren();
      if (pinned && s.live && pinned === s.id) {
        const btn = h('button', { type: 'button', class: 'link-btn' }, 'Back to lineup');
        btn.addEventListener('click', async () => {
          try { await unpin(); toast('Back to your lineup.'); } catch (error) { toast(error.message, 'error'); }
        });
        extra.append(h('div', { class: 'hero-pin' }, h('span', null, 'Pinned with Show now.'), btn));
      }
      if (!s.live && screen) {
        const btn = h('button', { type: 'button', class: 'link-btn' }, 'Show this now');
        btn.addEventListener('click', async () => {
          try { await showNow(screen.id); browse = null; toast(`${screen.name} is on the matrix.`); } catch (error) { toast(error.message, 'error'); }
        });
        extra.append(h('div', { class: 'hero-pin' }, h('span', null, 'Up in your lineup.'), btn));
      }
      const controls = screen ? focusControls(screen, { compact: true }) : null;
      if (controls) extra.append(controls);
    }
  }

  function renderNearby() {
    const planes = state.status?.nearby || [];
    nearby.replaceChildren();
    if (!planes.length) return;
    const unit = state.settings?.distance_unit === 'km' ? 'km' : 'NM';
    const list = h('ul', { class: 'plane-list' }, planes.map((plane) => {
      const dist = Number(plane.distance_nm);
      const shownDist = Number.isFinite(dist) ? Math.round(unit === 'km' ? dist * 1.852 : dist) : '?';
      const follow = h('button', { type: 'button', class: 'btn btn-small btn-secondary', 'aria-label': `Follow ${plane.callsign}` }, 'Follow');
      follow.addEventListener('click', async () => {
        follow.disabled = true;
        try { await followFlight(plane.callsign); } catch (error) { toast(error.message, 'error'); } finally { follow.disabled = false; }
      });
      return h('li', { class: 'plane' },
        h('div', null, h('strong', null, plane.callsign || 'Unknown'),
          h('small', null, `${plane.route ? plane.route + ' · ' : ''}${shownDist} ${unit} · ${plane.altitude_ft != null ? Number(plane.altitude_ft).toLocaleString() + ' ft' : '? ft'}`)),
        follow);
    }));
    const wasOpen = nearby.dataset.open === '1';
    const details = h('details', { class: 'card nearby', open: wasOpen || null },
      h('summary', null, h('span', null, 'Planes nearby'), h('span', { class: 'mono-note' }, String(planes.length))),
      h('p', { class: 'card-note' }, 'Tap Follow to keep a plane on the matrix.'),
      list,
      h('p', { class: 'credit' }, 'Positions: ', h('a', { href: 'https://adsb.fi/', target: '_blank', rel: 'noopener noreferrer' }, 'adsb.fi'),
        ' · Routes: ', h('a', { href: 'https://www.adsbdb.com/', target: '_blank', rel: 'noopener noreferrer' }, 'ADSBdb'), '. Route progress is approximate.'));
    details.addEventListener('toggle', () => { nearby.dataset.open = details.open ? '1' : ''; });
    nearby.append(details);
  }

  function shelfData() {
    const yours = {
      id: 'yours', title: 'Your screens', source: 'On this Pi',
      blurb: 'Screens you built or drew.',
      cards: [
        { action: true, glyph: '+', name: 'Build a screen', tag: 'Pick a layout and blocks', href: '#/build' },
        { action: true, glyph: '▦', name: 'Draw pixel art', tag: 'Sprites, icons, animations', href: '#/draw' },
        ...customs().map((s) => ({ screen: s, href: `#/customize/${encodeURIComponent(s.id)}`, mine: true })),
        ...(state.library?.art || []).map((a) => ({
          screen: { id: a.id, name: a.name, layout: 'full', slots: [{ block: 'art', color: null, options: { art_id: a.id } }], style: { palette: null, motion: 'still' } },
          art: a, href: `#/draw/${encodeURIComponent(a.id)}`,
        })),
      ],
    };
    const byId = new Map(builtins().map((b) => [b.id, b]));
    const shelves = state.catalog.shelves.map((shelf) => ({
      ...shelf,
      cards: shelf.screens.map((id) => byId.get(id)).filter(Boolean).map((s) => ({ screen: s, href: `#/customize/${encodeURIComponent(s.id)}` })),
    })).filter((s) => s.cards.length);
    return [yours, ...shelves];
  }

  function renderChips(shelves) {
    const choices = [{ id: 'all', label: 'All' }, ...shelves.map((s) => ({ id: s.id, label: s.id === 'yours' ? 'Yours' : s.title }))];
    if (!choices.some((c) => c.id === filter)) filter = 'all';
    chipsEl.replaceChildren(...choices.map((c) => {
      const btn = h('button', { type: 'button', class: 'chip', 'aria-pressed': String(c.id === filter) }, c.label);
      btn.addEventListener('click', () => {
        filter = c.id;
        for (const b of chipsEl.children) b.setAttribute('aria-pressed', String(b === btn));
        applyFilter();
      });
      return btn;
    }));
  }

  function applyFilter() {
    for (const section of shelvesEl.children) section.hidden = filter !== 'all' && section.dataset.shelf !== filter;
  }

  function card(c) {
    if (c.action) {
      return h('li', { class: 'shelf-item' }, h('a', { class: 'tile', href: c.href },
        h('span', { class: 'tile-action', 'aria-hidden': 'true' }, c.glyph),
        h('span', { class: 'tile-name' }, c.name), h('span', { class: 'tile-tag' }, c.tag)));
    }
    const live = c.screen.id === state.status?.screen_id;
    const m = screenMatrix(c.screen, { pitch: 4.25, glow: false, label: `${c.screen.name} preview` });
    const tag = c.art ? `Pixel art · ${c.art.w}×${c.art.h}${(c.art.frames || []).length > 1 ? ` · ${c.art.frames.length} frames` : ''}` : describeScreen(c.screen);
    return h('li', { class: 'shelf-item' }, h('a', { class: 'tile', href: c.href, 'aria-label': `${c.screen.name}${live ? ', live now' : ''}. ${tag}` },
      h('span', { class: `tile-frame${c.mine ? ' is-mine' : ''}${live ? ' is-live' : ''}` }, m.el, live ? h('span', { class: 'live-badge' }, 'Live') : null),
      h('span', { class: 'tile-name' }, c.screen.name),
      h('span', { class: 'tile-tag' }, tag)));
  }

  function renderShelves() {
    const shelves = shelfData();
    renderChips(shelves);
    shelvesEl.replaceChildren(...shelves.map((shelf) => {
      const id = `shelf-${shelf.id}`;
      return h('section', { class: 'shelf', 'aria-labelledby': id, dataset: { shelf: shelf.id } },
        h('div', { class: 'shelf-head' }, h('h2', { id, class: 'shelf-title' }, shelf.title), h('span', { class: 'mono-note' }, shelf.source)),
        shelf.blurb ? h('p', { class: 'shelf-blurb' }, shelf.blurb) : null,
        h('ul', { class: 'shelf-row', role: 'list' }, shelf.cards.map(card)));
    }));
    applyFilter();
  }

  let liveShown = state.status?.screen_id;
  renderHero();
  renderNearby();
  renderShelves();

  const unsubscribe = subscribe((what) => {
    if (what === 'status') {
      renderHero();
      renderNearby();
      if (state.status?.screen_id !== liveShown) {
        liveShown = state.status?.screen_id;
        for (const tile of shelvesEl.querySelectorAll('.tile-frame')) tile.classList.remove('is-live');
        renderShelvesLive();
      }
    } else {
      lastExtraKey = '';
      renderHero();
      renderShelves();
    }
  });

  function renderShelvesLive() {
    // Cheap update of the "Live" badge without re-rendering every thumbnail.
    for (const a of shelvesEl.querySelectorAll('.tile')) {
      const href = a.getAttribute('href') || '';
      const id = decodeURIComponent(href.split('/').pop());
      const frame = a.querySelector('.tile-frame');
      if (!frame) continue;
      const live = id === liveShown;
      frame.classList.toggle('is-live', live);
      const badge = frame.querySelector('.live-badge');
      if (live && !badge) frame.append(h('span', { class: 'live-badge' }, 'Live'));
      if (!live && badge) badge.remove();
    }
  }

  return () => { unsubscribe(); };
}
