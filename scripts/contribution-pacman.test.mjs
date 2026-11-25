import assert from 'node:assert/strict';
import test from 'node:test';
import { parseCalendar, createMaze, simulate, renderCalendar } from './contribution-pacman.mjs';

function days(countFor, length = 368) {
  return Array.from({ length }, (_, i) => {
    const count = countFor(i);
    return { date: new Date(Date.UTC(2025, 10, 23 + i)).toISOString().slice(0, 10),
      count, level: Math.min(count, 4) };
  });
}

function html(rows) {
  return rows.map(({ date, count, level }, i) => (
    `<td id="d-${i}" data-date="${date}" data-level="${level}"></td>` +
    `<tool-tip for="d-${i}">${count ? `${count} contributions` : 'No contributions'} on this day</tool-tip>`
  )).join('');
}

test('public calendar preserves every date, count, and level', () => {
  const rows = days(i => i % 19 === 0 ? 12 : 0);
  assert.deepEqual(parseCalendar(html(rows)), rows);
});

test('rejects missing, duplicate, contradictory, or discontinuous calendar input', () => {
  const rows = days(() => 0);
  assert.throws(() => parseCalendar('<html>Access denied</html>'), /calendar/i);
  assert.throws(() => parseCalendar(html(rows.slice(1))), /calendar/i);
  assert.throws(() => parseCalendar(html([...rows.slice(0, 367), rows[366]])), /calendar/i);
  assert.throws(() => parseCalendar(html(rows).replace('data-level="0"', 'data-level="4"')), /calendar/i);
  assert.throws(() => parseCalendar(html(rows).replace('<tool-tip for="d-0">', '<tool-tip for="missing">')), /calendar/i);
});

test('every cell is reachable; every blocked edge is blocked in both directions', () => {
  const maze = createMaze(53);
  const seen = new Set([0]), queue = [0];
  for (const cell of queue) for (const next of maze.neighbors[cell]) {
    assert.ok(maze.neighbors[next].includes(cell));
    assert.ok([1, 53].includes(Math.abs(cell - next)));
    if (!seen.has(next)) { seen.add(next); queue.push(next); }
  }
  assert.equal(seen.size, 371);
  assert.ok(maze.walls.length > 80);
});

for (const [name, count] of [['empty', () => 0], ['sparse', i => i % 23 === 0 ? 4 : 0], ['dense', () => 1]]) {
  test(`${name} grid: legal steps for all actors and no lost or invented contributions`, () => {
    const rows = days(count);
    const maze = createMaze(53);
    const game = simulate(rows, maze);
    for (const route of game.routes) {
      assert.equal(route.length, game.routes[0].length);
      for (const [index, cell] of route.entries()) {
        assert.ok(maze.neighbors[cell]);
        if (index && cell !== route[index - 1]) assert.ok(maze.neighbors[route[index - 1]].includes(cell));
      }
    }
    assert.equal(game.eaten.size, rows.filter(day => day.count > 0).length);
    assert.equal([...game.eaten.keys()].reduce((n, cell) => n + rows[(cell % 53) * 7 + Math.floor(cell / 53)].count, 0),
      rows.reduce((n, row) => n + row.count, 0));
    assert.ok(game.routes[0].length <= 1200);
  });
}

test('month labels mark January, SVG is deterministic, and light/dark have the same routes', () => {
  const rows = days(i => i % 9 === 0 ? 3 : 0);
  const light = renderCalendar(rows, 'light');
  const dark = renderCalendar(rows, 'dark');
  assert.equal(dark, renderCalendar(rows, 'dark'));
  assert.match(dark, /Jan 2026/);
  assert.equal([...dark.matchAll(/<text\b[^>]*>([^<]+)<\/text>/g)].map(match => match[1]).join(' '),
    'Nov Dec Jan 2026 Feb Mar Apr May Jun Jul Aug Sep Oct Nov');
  assert.match(dark, /font-family="[^"]*sans-serif"/);
  assert.match(dark, /#668cff/);
  assert.match(light, /#2459c7/);
  assert.match(dark, /prefers-reduced-motion:\s*reduce/);
  assert.doesNotMatch(dark, /<script\b|\bhref=|<image\b|<animate\b/);
  const paths = svg => svg.match(/@keyframes route\d+\{[^}]+(?:\}[^}]+)*?\}\}/g);
  assert.ok(paths(dark)?.length);
  assert.deepEqual(paths(light), paths(dark));
});

test('empty calendar is a static board; invalid dates and unsupported theme fail closed', () => {
  const rows = days(() => 0);
  assert.doesNotMatch(renderCalendar(rows, 'dark'), /@keyframes route/);
  assert.throws(() => renderCalendar(rows, 'unknown'), /theme/i);
  assert.throws(() => renderCalendar([{ ...rows[0], date: '2025-02-30' }, ...rows.slice(1)], 'dark'), /calendar/i);
});

test('future days are blank, not styled as actual zero-contribution days', () => {
  const svg = renderCalendar(days(() => 0), 'dark');
  assert.match(svg, /id="cell370"[^>]+fill="none"/);
  assert.match(svg, /id="cell0"[^>]+fill="#161b22"/);
});

test('embedded images can select a static board without relying on SVG media inheritance', () => {
  const svg = renderCalendar(days(i => i === 2 ? 1 : 0), 'dark');
  assert.match(svg, /^<svg\b[^>]*\bid="still"/);
  assert.match(svg, /:root:target \.actor\{display:none!important\}/);
  assert.match(svg, /:root:target \.pellet\{animation:none!important\}/);
});
