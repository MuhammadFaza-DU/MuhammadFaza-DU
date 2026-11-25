import { mkdir, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const WIDTH = 53;
const HEIGHT = 7;
const DAY = 86_400_000;
const TILE = 22;
const LEFT = 10;
const TOP = 34;
const PALETTES = {
  light: { board: '#ffffff', wall: '#2459c7', text: '#454f5c', cells: ['#ebedf0', '#9be9a8', '#40c463', '#30a14e', '#216e39'], player: '#cf9400' },
  dark: { board: '#0d1117', wall: '#668cff', text: '#b8c4d2', cells: ['#161b22', '#0e4429', '#006d32', '#26a641', '#39d353'], player: '#ffd84d' },
};

function validateCalendar(rows) {
  if (!Array.isArray(rows) || rows.length < 365 || rows.length > WIDTH * HEIGHT) {
    throw new Error('Unexpected public calendar length');
  }
  let previous;
  for (const row of rows) {
    const timestamp = Date.parse(`${row.date}T00:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(row.date) || !Number.isFinite(timestamp) ||
        new Date(timestamp).toISOString().slice(0, 10) !== row.date ||
        (previous === undefined ? new Date(timestamp).getUTCDay() !== 0 : timestamp !== previous + DAY) ||
        !Number.isSafeInteger(row.count) || row.count < 0 ||
        !Number.isInteger(row.level) || row.level < 0 || row.level > 4 ||
        (row.level === 0) !== (row.count === 0)) {
      throw new Error('Invalid or discontinuous public calendar');
    }
    previous = timestamp;
  }
}

export function parseCalendar(html) {
  const attribute = (tag, name) => tag.match(new RegExp(`\\s${name}="([^"]+)"`))?.[1];
  const tips = new Map();
  for (const [, tag, label] of html.matchAll(/<tool-tip\b([^>]+)>([^<]+)<\/tool-tip>/g)) {
    const id = attribute(tag, 'for');
    if (id && !tips.has(id)) tips.set(id, label.trim());
    else if (id) throw new Error('Duplicate public calendar tooltip');
  }
  const rows = [];
  const ids = new Set();
  for (const [, tag] of html.matchAll(/<td\b([^>]*\bdata-date="[^"]+"[^>]*)>/g)) {
    const id = attribute(tag, 'id');
    const level = attribute(tag, 'data-level');
    const label = tips.get(id);
    const digits = label?.match(/^(\d[\d,]*) contributions?\b/)?.[1];
    const count = digits ? Number(digits.replaceAll(',', '')) : label?.startsWith('No contributions ') ? 0 : NaN;
    if (!id || ids.has(id) || !/^[0-4]$/.test(level ?? '')) throw new Error('Invalid public calendar cell');
    ids.add(id);
    rows.push({ date: attribute(tag, 'data-date'), count, level: Number(level) });
  }
  rows.sort((a, b) => a.date.localeCompare(b.date));
  validateCalendar(rows);
  return rows;
}

export function createMaze(width) {
  if (width !== WIDTH) throw new Error('Expected a 53-week maze');
  const blocked = new Set();
  const walls = [];
  function wall(x, y, vertical) {
    const cell = y * width + x;
    const other = cell - (vertical ? 1 : width);
    blocked.add(`${other}:${cell}`);
    walls.push({ x, y, vertical });
  }
  for (let x = 0; x < width; x++) {
    if (![6, 14, 22, 26, 34, 42, 50].includes(x)) wall(x, 2, false);
    if (![4, 12, 20, 28, 36, 44, 52].includes(x)) wall(x, 5, false);
  }
  for (const x of [8, 16, 24, 32, 40, 48]) {
    const y = x % 16 ? 2 : 3;
    wall(x, y, true);
    wall(x, y + 1, true);
  }
  for (const x of [12, 30, 46]) for (const y of [0, 1]) wall(x, y, true);
  for (const x of [6, 22, 40]) for (const y of [5, 6]) wall(x, y, true);
  for (const x of [25, 26, 27]) wall(x, 4, false);
  for (const x of [25, 28]) for (const y of [2, 3]) wall(x, y, true);
  const neighbors = Array.from({ length: width * HEIGHT }, (_, cell) => {
    const x = cell % width, y = Math.floor(cell / width);
    return [x < width - 1 ? cell + 1 : -1, y < HEIGHT - 1 ? cell + width : -1,
      x > 0 ? cell - 1 : -1, y > 0 ? cell - width : -1].filter(next =>
      next >= 0 && !blocked.has(`${Math.min(cell, next)}:${Math.max(cell, next)}`));
  });
  return { width, neighbors, walls };
}

function walk(neighbors, start, accepts) {
  const queue = [start], parent = new Map([[start, -1]]);
  for (const cell of queue) {
    if (accepts(cell)) {
      const result = [cell];
      for (let previous = parent.get(cell); previous !== -1; previous = parent.get(previous)) result.push(previous);
      return result.reverse();
    }
    for (const next of neighbors[cell]) {
      if (!parent.has(next)) { parent.set(next, cell); queue.push(next); }
    }
  }
  return [];
}

export function simulate(rows, { width, neighbors }) {
  validateCalendar(rows);
  const remaining = new Set();
  rows.forEach((row, index) => {
    if (row.count) remaining.add((index % HEIGHT) * width + Math.floor(index / HEIGHT));
  });
  const eaten = new Map();
  const spawn = 3 * width + 26;
  const routes = [[remaining.values().next().value ?? 0], [spawn - 1], [spawn], [spawn + 1], [2 * width + 26]];
  function eat(cell, frame) {
    if (remaining.delete(cell)) eaten.set(cell, frame);
  }
  eat(routes[0][0], 0);
  while (remaining.size) {
    const route = walk(neighbors, routes[0].at(-1), cell => remaining.has(cell));
    if (route.length < 2) throw new Error('Unreachable contribution in maze');
    for (const cell of route.slice(1)) {
      routes[0].push(cell);
      const frame = routes[0].length - 1;
      eat(cell, frame);
      for (let i = 1; i < routes.length; i++) {
        const track = routes[i], here = track.at(-1);
        const target = routes[0][Math.max(0, frame - i * 7)];
        const move = frame > i * 3 && frame % 3 !== i % 3
          ? walk(neighbors, here, step => step === target)[1] : undefined;
        track.push(move !== undefined && move !== cell ? move : here);
      }
    }
  }
  return { routes, eaten };
}

function monthLabels(rows, color) {
  const labels = [];
  for (let index = 0; index < rows.length; index++) {
    const date = new Date(`${rows[index].date}T00:00:00Z`);
    if (index && date.getUTCDate() !== 1) continue;
    const month = new Intl.DateTimeFormat('en', { month: 'short', timeZone: 'UTC' }).format(date);
    const label = date.getUTCMonth() === 0 ? `${month} ${date.getUTCFullYear()}` : month;
    const labelWidth = label.length * 8;
    const previous = labels.at(-1);
    const column = Math.floor(index / HEIGHT);
    const anchor = LEFT + column * TILE;
    const x = Math.min(LEFT + WIDTH * TILE - labelWidth,
      Math.max(anchor, previous ? previous.x + previous.width + 12 : LEFT));
    labels.push({ label, width: labelWidth, x, anchor });
  }
  return `<g fill="${color}" font-family="Segoe UI,Arial,sans-serif" font-size="16" font-weight="500">` +
    labels.map(({ label, x, anchor }) => `<text x="${x}" y="21" data-column-x="${anchor}">${label}</text>`).join('') + '</g>';
}

export function renderCalendar(rows, theme) {
  if (theme !== 'light' && theme !== 'dark') throw new Error('Unknown theme');
  const palette = PALETTES[theme], maze = createMaze(WIDTH);
  const { routes, eaten } = simulate(rows, maze);
  const animated = eaten.size > 0;
  const width = LEFT * 2 + WIDTH * TILE, height = TOP + HEIGHT * TILE + 10;
  const point = cell => [LEFT + (cell % WIDTH + 0.5) * TILE, TOP + (Math.floor(cell / WIDTH) + 0.5) * TILE];
  const end = Math.max(1, routes[0].length - 1);
  const duration = Math.max(3000, end * 175 + 2000);
  const time = index => ((450 + index * 175) / duration * 100).toFixed(5);
  const position = cell => `transform:translate(${point(cell).map(n => `${n}px`).join(',')})`;
  const styles = [
    '@media(prefers-reduced-motion: reduce){.actor{display:none!important}.actor,.actor *,.pellet{animation:none!important}}',
    ':root:target .actor{display:none!important}:root:target .actor,:root:target .actor *,:root:target .pellet{animation:none!important}',
  ];
  if (animated) {
    routes.forEach((route, i) => {
      const keyframes = [`0%{${position(route[0])}}`];
      for (const [index, cell] of route.entries()) keyframes.push(`${time(index)}%{${position(cell)}}`);
      styles.push(`@keyframes route${i}{${keyframes.join('')}100%{${position(route.at(-1))}}}#actor${i}{animation:route${i} ${duration}ms linear infinite}`);
    });
    const turn = routes[0].map((cell, i, route) => {
      const next = route[i + 1] ?? cell;
      const delta = next - cell;
      return delta === 1 ? 0 : delta === -1 ? 180 : delta === WIDTH ? 90 : delta === -WIDTH ? 270 : null;
    });
    for (let i = 0, angle = 0; i < turn.length; i++) { angle = turn[i] ?? angle; turn[i] = angle; }
    styles.push(`@keyframes heading{0%{transform:rotate(${turn[0]}deg)}${turn.map((angle, i) =>
      `${time(i)}%{transform:rotate(${angle}deg)}`).join('')}100%{transform:rotate(${turn.at(-1)}deg)}}` +
      `#heading{animation:heading ${duration}ms step-end infinite}` +
      '@keyframes open-mouth{0%,100%{visibility:visible}50%{visibility:hidden}}' +
      '@keyframes shut-mouth{0%,100%{visibility:hidden}50%{visibility:visible}}' +
      '#open-mouth{animation:open-mouth 260ms step-end infinite}#shut-mouth{animation:shut-mouth 260ms step-end infinite}');
  }
  const cells = Array.from({ length: WIDTH * HEIGHT }, (_, cell) => {
    const [x, y] = point(cell);
    const index = (cell % WIDTH) * HEIGHT + Math.floor(cell / WIDTH);
    const level = rows[index]?.level;
    if (animated && eaten.has(cell)) {
      styles.push(`@keyframes bite${cell}{0%{fill:${palette.cells[level]}}${time(eaten.get(cell))}%,100%{fill:${palette.cells[0]}}}` +
        `#cell${cell}{animation:bite${cell} ${duration}ms step-end infinite}`);
    }
    const fill = level === undefined ? 'none' : palette.cells[level];
    return `<rect class="pellet" id="cell${cell}" x="${x - 10}" y="${y - 10}" width="20" height="20" rx="4" fill="${fill}"/>`;
  }).join('');
  const wall = maze.walls.map(({ x, y, vertical }) =>
    `M${LEFT + x * TILE} ${TOP + y * TILE}${vertical ? 'v' : 'h'}${TILE}`).join('');
  const actor = animated ? routes.map((route, i) => {
    const [x, y] = point(route[0]);
    const sprite = i === 0
      ? `<g id="heading" fill="${palette.player}"><path id="open-mouth" d="M0 0L8 -4A9 9 0 1 0 8 4Z"/><circle id="shut-mouth" r="9" visibility="hidden"/></g>`
      : `<path fill="${['', '#fc5660', '#45d5e6', '#ec83ca', '#ffa34b'][i]}" d="M-8 8V0a8 8 0 0 1 16 0v8l-4-3-4 3-4-3Z"/>` +
        '<path fill="#fff" d="M-5 -1a2.2 2.5 0 1 0 4.4 0 2.2 2.5 0 1 0-4.4 0m6 0a2.2 2.5 0 1 0 4.4 0 2.2 2.5 0 1 0-4.4 0"/>' +
        '<circle cx="-2.4" cy="-0.7" r="1" fill="#172554"/><circle cx="3.6" cy="-0.7" r="1" fill="#172554"/>';
    return `<g class="actor" id="actor${i}" transform="translate(${x} ${y})">${sprite}</g>`;
  }).join('') : '';
  return `<svg id="still" xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">` +
    '<desc>Pac-Man on Muhammad Faza’s public GitHub contribution calendar.</desc>' +
    `<style>${styles.join('\n')}</style><rect width="${width}" height="${height}" fill="${palette.board}"/>` +
    monthLabels(rows, palette.text) + cells +
    `<path d="${wall}" fill="none" stroke="${palette.wall}" stroke-width="1.6" stroke-linecap="round"/>${actor}</svg>`;
}

async function main() {
  const target = process.argv[2] ?? 'dist';
  const response = await fetch('https://github.com/users/MuhammadFaza-DU/contributions', {
    signal: AbortSignal.timeout(30_000), redirect: 'error',
  });
  if (!response.ok) throw new Error(`Public calendar fetch failed: HTTP ${response.status}`);
  const rows = parseCalendar(await response.text());
  const age = (Date.now() - Date.parse(`${rows.at(-1).date}T00:00:00Z`)) / DAY;
  if (age < -1 || age > 3) throw new Error('Public calendar appears stale');
  const light = renderCalendar(rows, 'light'), dark = renderCalendar(rows, 'dark');
  await mkdir(target, { recursive: true });
  await Promise.all([
    writeFile(`${target}/contribution-pacman.svg`, light),
    writeFile(`${target}/contribution-pacman-dark.svg`, dark),
  ]);
  console.log(`Rendered ${rows.length} public calendar days (${rows[0].date} to ${rows.at(-1).date}).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
