#!/usr/bin/env python3
import argparse
import bisect
from collections import deque
import datetime
import json
import math
import os
import random
import urllib.request

PITCH, CELL, X0, Y0, LABEL_Y, H = 22, 20, 11, 57, 43, 242
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}
BG, TEXT = "#0d1117", "#b8c4d2"
GHOSTS = ["#ff5c5c", "#f5a3d6", "#4ee0f0", "#ffa845"]
STEP, HOLD = 0.18, 1.2
DEATH_STEPS, RESPAWN_STEPS = 3, 5
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

QUERY = """query($login:String!){user(login:$login){contributionsCollection{contributionCalendar{weeks{contributionDays{date weekday contributionLevel}}}}}}"""


def fetch(user, token):
    body = json.dumps({"query": QUERY, "variables": {"login": user}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json", "User-Agent": "pacman-graph"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.load(r)
    if "errors" in data or not data.get("data", {}).get("user"):
        raise SystemExit("GraphQL error: " + json.dumps(data.get("errors", "user not found")))
    weeks = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    return [[(d["weekday"], LEVELS[d["contributionLevel"]], d["date"]) for d in w["contributionDays"]] for w in weeks]


def demo(seed=7):
    rng = random.Random(seed)
    today = datetime.date(2026, 11, 27)
    start = today - datetime.timedelta(days=364)
    start -= datetime.timedelta(days=(start.weekday() + 1) % 7)
    weeks, d = [], start
    while d <= today:
        week = []
        for _ in range(7):
            if d <= today:
                lv = rng.choices([0, 1, 2, 3, 4], [55, 18, 12, 9, 6])[0]
                week.append(((d.weekday() + 1) % 7, lv, d.isoformat()))
            d += datetime.timedelta(days=1)
        weeks.append(week)
    return weeks


class Track:
    def __init__(self, pts):
        self.pts = pts
        self.t = [p[0] for p in pts]

    def at(self, t):
        t = min(max(t, self.t[0]), self.t[-1])
        i = bisect.bisect_right(self.t, t)
        if i >= len(self.pts):
            return self.pts[-1][1:]
        a, b = self.pts[i - 1], self.pts[i]
        k = (t - a[0]) / (b[0] - a[0])
        return tuple(a[j] + (b[j] - a[j]) * k for j in range(1, len(a)))


def ctr(c, r):
    return X0 + c * PITCH + CELL / 2, Y0 + r * PITCH + CELL / 2


def shortest_path(neighbors, start, targets):
    queue = deque([start])
    parents = {start: None}
    while queue:
        cell = queue.popleft()
        if cell in targets:
            path = []
            while cell is not None:
                path.append(cell)
                cell = parents[cell]
            return path[::-1]
        for nxt in neighbors[cell]:
            if nxt not in parents:
                parents[nxt] = cell
                queue.append(nxt)
    raise ValueError("No path through the maze")


def make_maze(cols):
    walls = []

    def wall(x, y, vertical):
        other = (x - 1, y) if vertical else (x, y - 1)
        if 0 <= x < cols and 0 <= other[0] < cols:
            walls.append((x, y, vertical, frozenset(((x, y), other))))

    if cols >= 53:
        for x in range(cols):
            if x not in (6, 14, 22, 26, 34, 42, 50):
                wall(x, 2, False)
            if x not in (4, 12, 20, 28, 36, 44, 52):
                wall(x, 5, False)
        for x in (8, 16, 24, 32, 40, 48):
            y = 2 if x % 16 else 3
            wall(x, y, True)
            wall(x, y + 1, True)
        for x in (12, 30, 46):
            for y in (0, 1):
                wall(x, y, True)
        for x in (6, 22, 40):
            for y in (5, 6):
                wall(x, y, True)
        for x in (25, 26, 27):
            wall(x, 4, False)
        for x in (25, 28):
            for y in (2, 3):
                wall(x, y, True)
    blocked = {edge for *_, edge in walls}
    neighbors = {}
    for x in range(cols):
        for y in range(7):
            cell = (x, y)
            neighbors[cell] = [
                nxt for nxt in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1))
                if 0 <= nxt[0] < cols and 0 <= nxt[1] < 7 and frozenset((cell, nxt)) not in blocked
            ]
    return neighbors, [(x, y, vertical) for x, y, vertical, _ in walls]


def maze_routes(cells, cols, neighbors):
    remaining = {cell for cell, (level, _) in cells.items() if level}
    start = min(remaining or cells)
    player = [start]
    targets = sorted(remaining)
    paths = [shortest_path(neighbors, start, {cell}) for cell in neighbors]
    openings = [path for path in paths if len(path) >= 8] or paths
    used = []
    impacts = {}
    for life in range(3):
        band = set(targets[life * len(targets) // 3:(life + 1) * len(targets) // 3])
        focus = min(band) if band else (min(cols - 1, life * cols // 3), life * 3)
        opening = min(openings, key=lambda path: (
            max((next((i for i, (a, b) in enumerate(zip(path, prior)) if a != b),
                      min(len(path), len(prior))) for prior in used), default=0),
            abs(path[-1][0] - focus[0]) + abs(path[-1][1] - focus[1]),
            len(path),
            path[-1],
        ))
        used.append(opening)
        player.extend(opening[1:])
        remaining.difference_update(opening)
        while pending := (band if life < 2 else set(targets)) & remaining:
            route = shortest_path(neighbors, player[-1], pending)[1:]
            player.extend(route)
            remaining.difference_update(route)
        if life < 2:
            impact = len(player) - 1
            impacts[impact] = (life, impact + RESPAWN_STEPS)
            player.extend([player[-1]] * (RESPAWN_STEPS - 1))
            player.append(start)
    player.extend(shortest_path(neighbors, player[-1], {start})[1:])

    routes = [player]
    hidden = {frame for impact, (_, respawn) in impacts.items() for frame in range(impact + 1, respawn)}
    for index in range(4):
        catch = next((frame for frame, (ghost, _) in impacts.items() if ghost == index), None)
        routes.append(ghost_route(neighbors, player, hidden, index, catch, routes[1:]))
    return routes, [(impact * STEP, respawn * STEP) for impact, (_, respawn) in impacts.items()]


def ghost_route(neighbors, player, hidden, index, catch, earlier_ghosts):
    # Work backward so an ambush and the return home are both reachable without jumps.
    moves = {cell: (*adjacent, cell) for cell, adjacent in neighbors.items()}
    end = len(player) - 1
    home = player[catch] if catch is not None else (max(x for x, _ in neighbors) // 2, index)
    homes = sorted(neighbors, key=lambda cell: (
        abs(cell[0] - home[0]) + abs(cell[1] - home[1]), cell,
    ))

    def allowed(frame, cell):
        if frame == catch:
            return cell == player[frame]
        return frame in hidden or cell != player[frame]

    def crosses(frame, here, nxt):
        return (frame not in hidden and frame + 1 not in hidden
                and here == player[frame + 1] and nxt == player[frame])

    for spawn in homes:
        if not allowed(0, spawn) or any(ghost[0] == spawn for ghost in earlier_ghosts):
            continue
        viable = [set() for _ in player]
        viable[end] = {spawn}
        for frame in range(end - 1, -1, -1):
            viable[frame] = {
                cell for cell, adjacent in moves.items()
                if allowed(frame, cell) and any(
                    nxt in viable[frame + 1] and not crosses(frame, cell, nxt) for nxt in adjacent
                )
            }
        if spawn not in viable[0]:
            continue
        ghost = [spawn]
        for frame in range(1, end + 1):
            here = ghost[-1]
            target = player[max(0, frame - (index + 1) * 7)]
            candidates = [
                cell for cell in moves[here]
                if cell in viable[frame] and not crosses(frame - 1, here, cell)
            ]
            ghost.append(min(candidates, key=lambda cell: (
                sum(cell == other[frame] for other in earlier_ghosts),
                0 if frame % 4 != index or cell == here else 1,
                abs(cell[0] - target[0]) + abs(cell[1] - target[1]),
                cell == here,
                cell,
            )))
        return ghost
    raise ValueError("No collision-safe closed ghost route")


def wedge(a, r=9.0):
    x, y = r * math.cos(math.radians(a)), r * math.sin(math.radians(a))
    return f"M0 0L{x:.2f} {-y:.2f}A{r} {r} 0 1 0 {x:.2f} {y:.2f}Z"


def ghost_shape(color):
    return (
        f'<path fill="{color}" d="M-10 10V-1A10 10 0 0 1 10 -1V10L6.7 7L3.3 10L0 7L-3.3 10L-6.7 7Z"/>'
        '<circle cx="-3.5" cy="-2" r="3" fill="#fff"/><circle cx="3.5" cy="-2" r="3" fill="#fff"/>'
        '<circle cx="-2.5" cy="-2" r="1.5" fill="#1b2a6b"/><circle cx="4.5" cy="-2" r="1.5" fill="#1b2a6b"/>'
    )


def keyframes(series, D, fmt):
    kt = ";".join(f"{min(max(t / D, 0), 1):.5f}" for t, *_ in series)
    vals = ";".join(fmt(*v) for _, *v in series)
    return kt, vals


def build(weeks, snapshot=None):
    cells = {}
    for c, w in enumerate(weeks):
        for wd, lv, date in w:
            cells[(c, wd)] = (lv, date)
    cols = len(weeks)
    W = cols * PITCH + 20
    neighbors, walls = make_maze(cols)
    routes, deaths = maze_routes(cells, cols, neighbors)
    end = (max(map(len, routes)) - 1) * STEP
    D = end + HOLD
    tracks = [
        Track([(i * STEP, *ctr(*cell)) for i, cell in enumerate(route)] + [(D, *ctr(*route[0]))])
        for route in routes
    ]
    eat = {}
    heads = []
    for i, (x, y) in enumerate(routes[0]):
        eat.setdefault((x, y), max(i * STEP, 0.04))
        if i + 1 < len(routes[0]):
            nx, ny = routes[0][i + 1]
            angle = {(1, 0): 0, (0, 1): 90, (-1, 0): 180, (0, -1): 270}.get((nx - x, ny - y))
            if angle is not None and (not heads or heads[-1][1] != angle):
                heads.append((i * STEP, angle))
    if heads:
        heads += [((len(routes[0]) - 1) * STEP, heads[0][1]), (D, heads[0][1])]
    else:
        heads = [(0.0, 0), (D, 0)]
    restore = end + HOLD / 2

    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    o.append("<desc>Pac-Man on Muhammad Faza's public GitHub contribution calendar.</desc>")
    o.append(f'<rect width="{W}" height="{H}" rx="20" fill="{BG}"/>')
    o.append(f'<g fill="{TEXT}" font-family="Segoe UI,Arial,sans-serif" font-size="16" font-weight="500">')
    last_m, last_c = None, -9
    for c, w in enumerate(weeks):
        m = int(w[0][2][5:7])
        if m != last_m and c - last_c >= 3:
            label = MONTHS[m - 1] + (" " + w[0][2][:4] if m == 1 else "")
            o.append(f'<text x="{X0 + c * PITCH - 1}" y="{LABEL_Y}">{label}</text>')
            last_c = c
        last_m = m
    o.append("</g>")

    for (c, r), (lv, _) in sorted(cells.items()):
        x, y = X0 + c * PITCH, Y0 + r * PITCH
        o.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{PALETTE[0]}"/>')
    for (c, r), (lv, _) in sorted(cells.items()):
        if lv == 0:
            continue
        x, y = X0 + c * PITCH, Y0 + r * PITCH
        if snapshot is None:
            kt = f"0;{eat[(c, r)] / D:.5f};{restore / D:.5f};1"
            o.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{PALETTE[lv]}">'
                f'<animate attributeName="opacity" calcMode="discrete" dur="{D:.3f}s" repeatCount="indefinite" '
                f'keyTimes="{kt}" values="1;0;1;1"/></rect>'
            )
        elif snapshot < eat[(c, r)] or snapshot >= restore:
            o.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="4" fill="{PALETTE[lv]}"/>')

    for x, y, vertical in walls:
        sx, sy = X0 + x * PITCH, Y0 + y * PITCH
        if vertical:
            x1, y1, x2, y2 = sx - 1, sy - 1, sx - 1, sy + PITCH - 1
        else:
            x1, y1, x2, y2 = sx - 1, sy - 1, sx + PITCH - 1, sy - 1
        o.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#668cff" stroke-width="1.2"/>')

    dur = f'dur="{D:.3f}s" repeatCount="indefinite"'
    if snapshot is None:
        kt, vals = keyframes(tracks[0].pts, D, lambda x, y: f"{x:.1f} {y:.1f}")
        hkt, hv = keyframes(heads, D, lambda a: f"{a}")
        visible, scale, spin = [(0, "visible")], [(0, 1)], [(0, 0)]
        for impact, respawn in deaths:
            vanish = impact + DEATH_STEPS * STEP
            visible += [(vanish, "hidden"), (respawn, "visible")]
            scale += [(impact, 1), (vanish, 0), (respawn - STEP / 2, 0), (respawn, 1)]
            spin += [(impact, 0), (vanish, 360), (respawn - STEP / 2, 360), (respawn, 0)]
        vkt, vv = keyframes([*visible, (D, "visible")], D, str)
        skt, sv = keyframes([*scale, (D, 1)], D, str)
        rkt, rv = keyframes([*spin, (D, 0)], D, str)
        o.append(f'<g><animateTransform attributeName="transform" type="translate" calcMode="linear" {dur} keyTimes="{kt}" values="{vals}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="rotate" calcMode="discrete" {dur} keyTimes="{hkt}" values="{hv}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="rotate" calcMode="linear" {dur} keyTimes="{rkt}" values="{rv}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="scale" calcMode="linear" {dur} keyTimes="{skt}" values="{sv}"/>')
        o.append(f'<animate attributeName="visibility" calcMode="discrete" {dur} keyTimes="{vkt}" values="{vv}"/>')
        o.append(
            f'<path fill="#ffd400" d="{wedge(38)}"><animate attributeName="d" dur="0.36s" repeatCount="indefinite" '
            f'values="{wedge(38)};{wedge(3)};{wedge(38)}"/></path>'
        )
        o.append("</g></g></g></g>")
        for gi, g in enumerate(tracks[1:]):
            gk, gv = keyframes(g.pts, D, lambda x, y: f"{x:.1f} {y:.1f}")
            o.append(
                f'<g><animateTransform attributeName="transform" type="translate" calcMode="linear" {dur} keyTimes="{gk}" values="{gv}"/>'
                f"{ghost_shape(GHOSTS[gi])}</g>"
            )
    else:
        px, py = tracks[0].at(snapshot)
        ang = [a for t, a in heads if t <= snapshot]
        ang = ang[-1] if ang else heads[0][1]
        if not any(impact + DEATH_STEPS * STEP <= snapshot < respawn for impact, respawn in deaths):
            o.append(f'<g transform="translate({px:.1f} {py:.1f}) rotate({ang})"><path fill="#ffd400" d="{wedge(30)}"/></g>')
        for gi, g in enumerate(tracks[1:]):
            gx, gy = g.at(snapshot)
            o.append(f'<g transform="translate({gx:.1f} {gy:.1f})">{ghost_shape(GHOSTS[gi])}</g>')
    o.append("</svg>")
    return "\n".join(o), D, deaths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user")
    ap.add_argument("--out", default="dist")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--snapshot", type=float)
    a = ap.parse_args()
    if a.demo:
        weeks = demo()
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not a.user or not token:
            raise SystemExit("need --user and GH_TOKEN")
        weeks = fetch(a.user, token)
    os.makedirs(a.out, exist_ok=True)
    if a.snapshot is not None:
        svg, _, _ = build(weeks, snapshot=a.snapshot)
        open(os.path.join(a.out, "snapshot.svg"), "w", encoding="utf-8").write(svg)
        return
    svg, D, _ = build(weeks)
    open(os.path.join(a.out, "contribution-pacman-dark.svg"), "w", encoding="utf-8").write(svg)
    still, _, _ = build(weeks, snapshot=0)
    open(os.path.join(a.out, "contribution-pacman-still-dark.svg"), "w", encoding="utf-8").write(still)
    print(f"ok: duration={D:.1f}s")


if __name__ == "__main__":
    main()
