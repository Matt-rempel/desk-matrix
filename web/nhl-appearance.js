// Team selection is independent of appearance; identical saved looks need one choice.
import { followedTeams, teamsLabel } from './nhl-teams.js';

function appearanceKey(screen) {
  const slot = screen.slots.find(s => s.block === 'nhl');
  const opt = slot.options || {};
  const palette = screen.style?.palette ?? null;
  return JSON.stringify([
    palette, screen.style?.motion || 'still',
    palette ? null : slot.color ?? '#F4F2EE', palette ? null : opt.accent ?? '#FFB23F',
    opt.show_shots ?? true, opt.h24 ?? false,
    opt.font || 'auto', opt.font_family ?? null, opt.font_size ?? null,
  ]);
}

export function nhlAppearanceChoices(builtins, saved, selectedId) {
  const all = [...builtins, ...saved].filter(s => s.slots?.some(slot => slot.block === 'nhl'));
  const defaultScreen = all.find(s => s.id === 'nhl-scoreboard');
  const candidates = [defaultScreen, ...saved].filter(s => s && !s.hidden && s.slots?.some(slot => slot.block === 'nhl'));
  const groups = new Map();
  for (const screen of candidates) {
    const key = appearanceKey(screen);
    if (groups.has(key)) continue;
    const isDefault = screen.id === 'nhl-scoreboard';
    const teams = followedTeams(screen.slots.find(s => s.block === 'nhl').options);
    groups.set(key, { id: screen.id, saved: !isDefault,
      label: isDefault ? 'Default scoreboard' : `Saved: ${screen.name} · ${teamsLabel(teams)}` });
  }
  const choices = [...groups.values()];
  const totals = new Map();const seen = new Map();
  for (const c of choices) totals.set(c.label, (totals.get(c.label) || 0) + 1);
  for (const c of choices) {
    const label = c.label;
    seen.set(label, (seen.get(label) || 0) + 1);
    if (totals.get(label) > 1) c.label += ` (${seen.get(label)})`;
  }
  const selected = all.find(s => s.id === selectedId);
  return { choices, selected: (selected && groups.get(appearanceKey(selected))?.id) || defaultScreen?.id };
}
