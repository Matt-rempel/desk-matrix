// Shared secondary team picker for NHL screens and live alerts.
import { state } from './store.js';
import { h, sheet, nextId } from './ui.js';

export function followedTeams(options = {}) {
  const values = Array.isArray(options.teams) && options.teams.length
    ? options.teams : [options.team || 'CGY'];
  return [...new Set(values)];
}

export function teamsLabel(teams) {
  return teams.length <= 4 ? teams.join(', ') : `${teams.slice(0, 3).join(', ')} +${teams.length - 3}`;
}

function teamMark(team) {
  const canvas = h('canvas', { width: 28, height: 28, class: 'nhl-team-mark', 'aria-hidden': 'true' });
  const ctx = canvas.getContext('2d');
  const logo = team.logo;
  if (logo?.rows?.length) {
    const ox = Math.floor((14 - logo.rows[0].length) / 2);
    const oy = Math.floor((14 - logo.rows.length) / 2);
    logo.rows.forEach((row, y) => [...row].forEach((char, x) => {
      if (char === '.') return;
      ctx.fillStyle = logo.palette[parseInt(char, 36)];
      ctx.fillRect((ox + x) * 2, (oy + y) * 2, 2, 2);
    }));
  }
  return h('span', { class: 'nhl-team-icon' }, canvas);
}

export function teamPicker({ value, onChange, detail = 'Choose one or more teams' }) {
  let teams = [...value];
  const summary = h('span', { class: 'row-detail' }, teamsLabel(teams));
  const button = h('button', { type: 'button', class: 'nhl-teams-control',
    'aria-label': 'Choose NHL teams', 'aria-haspopup': 'dialog' },
  h('span', { class: 'row-text' }, h('span', { class: 'row-title' }, 'Teams to follow'), summary),
  h('span', { class: 'nhl-team-count' }, String(teams.length)), h('span', { 'aria-hidden': 'true' }, '›'));
  button.addEventListener('click', () => {
    const draft = new Set(teams);
    const available = [...(state.catalog?.nhlTeams || [])].sort((a, b) => a.name.localeCompare(b.name));
    const searchId = nextId('team-search');
    const input = h('input', { id: searchId, type: 'search', class: 'input', placeholder: 'Search teams',
      autocomplete: 'off', 'aria-label': 'Search NHL teams' });
    const count = h('p', { class: 'nhl-picker-count', role: 'status', 'aria-live': 'polite' });
    const list = h('div', { class: 'nhl-team-list', role: 'group', 'aria-label': 'NHL teams' });
    const done = h('button', { type: 'button', class: 'btn btn-primary' }, 'Done');
    const sync = () => {
      count.textContent = draft.size ? `${draft.size} ${draft.size === 1 ? 'team' : 'teams'} selected` : 'Choose at least one team';
      done.disabled = draft.size === 0;
    };
    const draw = () => {
      const query = input.value.trim().toLocaleLowerCase();
      const matches = available.filter(t => `${t.name} ${t.code}`.toLocaleLowerCase().includes(query));
      list.replaceChildren(...matches.map(team => {
        const check = h('span', { class: 'nhl-team-check', 'aria-hidden': 'true' }, draft.has(team.code) ? '✓' : '');
        const row = h('button', { type: 'button', class: 'nhl-team-choice',
          'aria-label': `${team.name} (${team.code})`, 'aria-pressed': String(draft.has(team.code)) },
        teamMark(team), h('span', { class: 'row-text' }, h('span', { class: 'row-title' }, team.name),
          h('span', { class: 'row-detail' }, team.code)), check);
        row.addEventListener('click', () => {
          if (draft.has(team.code)) draft.delete(team.code); else draft.add(team.code);
          row.setAttribute('aria-pressed', String(draft.has(team.code)));
          check.textContent = draft.has(team.code) ? '✓' : '';
          sync();
        });
        return row;
      }));
      if (!matches.length) list.append(h('p', { class: 'sheet-text' }, 'No teams match your search.'));
    };
    const picker = sheet({ title: 'Follow NHL teams', body: [
      h('p', { class: 'sheet-text nhl-picker-help' }, detail),
      h('div', { class: 'nhl-picker-search' }, h('label', { class: 'sr-only', for: searchId }, 'Search NHL teams'), input, count),
      list, h('div', { class: 'nhl-picker-footer' }, done)] });
    picker.dialog.classList.add('nhl-team-sheet');
    input.addEventListener('input', draw);
    done.addEventListener('click', () => {
      if (!draft.size) return;
      teams = [...draft];
      summary.textContent = teamsLabel(teams);
      button.querySelector('.nhl-team-count').textContent = String(teams.length);
      onChange([...teams]);
      picker.close();
    });
    sync();draw();
  });
  return button;
}
