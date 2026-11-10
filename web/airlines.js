// The catalog shares airline identities with the matrix renderer.
import { state } from './store.js';
import { h } from './ui.js';

export function airlineFor(plane, airlines = state.catalog?.airlines || []) {
  const code = String(plane?.icao || plane?.callsign || '').replace(/[\s-]+/g, '').toUpperCase();
  return airlines.find(airline => airline.prefixes.some(prefix =>
    code.startsWith(prefix) && /^[0-9]$/.test(code.charAt(prefix.length))))
    || airlines.find(airline => airline.hints.includes(plane?.icon)) || null;
}

export function airlineBadge(plane) {
  const airline = airlineFor(plane);
  const badge = h('span', { class: 'airline-badge', title: airline?.name || 'Aircraft',
    role: 'img', 'aria-label': airline?.name || 'Aircraft', dataset: { airline: airline?.id || 'unknown' } });
  const fallback = () => {
    badge.classList.add('airline-unknown');
    badge.replaceChildren(h('span', { 'aria-hidden':'true' }, '✈'));
  };
  if (airline) {
    const img = h('img', { src:airline.image, alt:'', width:52, height:36, decoding:'async' });
    img.addEventListener('error', fallback, { once:true });
    badge.append(img);
  } else fallback();
  return badge;
}

export function flightIdentity(plane) {
  const airline = airlineFor(plane);
  return h('div', { class:'flight-identity' }, airlineBadge(plane),
    h('span', null, airline?.name || 'Aircraft', h('small', null, plane.callsign || '')));
}
