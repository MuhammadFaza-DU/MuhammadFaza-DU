#!/usr/bin/env python3
import argparse
import bisect
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
STEP, DEATH, HOLD, SPAN = 0.09, 1.5, 1.6, 2.6
EVENT_FRACTIONS = (0.2, 0.47, 0.74)
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


def build_pacman(cells, cols):
    route = []
    for c in range(cols):
        rows = sorted(r for (cc, r) in cells if cc == c)
        route += [(c, r) for r in (rows[::-1] if c % 2 else rows)]
    event_idx = {int(len(route) * f) for f in EVENT_FRACTIONS}
    x, y = ctr(*route[0])
    pts, eat, heads, events = [(0.0, x, y)], {}, [], []
    t = 0.0
    eat[route[0]] = 0.0
    for i in range(1, len(route)):
        nx, ny = ctr(*route[i])
        dist = math.hypot(nx - x, ny - y)
        dt = STEP * max(1.0, dist / PITCH)
        dx, dy = nx - x, ny - y
        ang = (0 if dx > 0 else 180) if abs(dx) >= abs(dy) else (90 if dy > 0 else 270)
        if not heads or heads[-1][1] != ang:
            heads.append((t, ang))
        t += dt
        pts.append((t, nx, ny))
        x, y = nx, ny
        if i in event_idx:
            events.append((t, x, y))
            t += DEATH
            pts.append((t, x, y))
        eat[route[i]] = t
    end = t
    return Track(pts), eat, heads, events, end


def make_ghosts(seed, pac, events, D, W):
    rng = random.Random(seed)
    xmin, xmax, ymin, ymax = X0 + 10, W - 20, Y0 + 10, Y0 + 6 * PITCH + 10
    out = []
    for gi in range(4):
        mine = [e for k, e in enumerate(events) if k % 4 == gi]
        times = [i * SPAN for i in range(int(D // SPAN) + 1) if i * SPAN < D - SPAN]
        times = [t for t in times if all(not (e[0] - 3.2 < t < e[0] + 3.0) for e in mine)]
        wps, prev = [], None
        for t in times:
            for _ in range(40):
                x, y = rng.uniform(xmin, xmax), rng.uniform(ymin, ymax)
                if abs(x - pac.at(t)[0]) >= 230 and (prev is None or math.hypot(x - prev[0], y - prev[1]) <= 520):
                    break
            wps.append((t, x, y))
            prev = (x, y)
        for te, ex, ey in mine:
            side = 1 if ex < (xmin + xmax) / 2 else -1
            qx = min(max(ex + side * 200, xmin), xmax)
            rx = min(max(ex - side * 220, xmin), xmax)
            wps += [(te - 1.0, qx, ey), (te, ex, ey), (te + 1.3, rx, ey)]
        wps.sort()
        wps.append((D, wps[0][1], wps[0][2]))
        out.append(Track(wps))
    return out


def valid(ghosts, pac, events, D):
    windows = [(e[0], e[0] + DEATH) for e in events]
    t = 0.0
    while t < D:
        if not any(a <= t <= b for a, b in windows):
            px, py = pac.at(t)
            for gi, g in enumerate(ghosts):
                gx, gy = g.at(t)
                if math.hypot(gx - px, gy - py) < 24:
                    mine = [e for k, e in enumerate(events) if k % 4 == gi]
                    if not any(e[0] - 0.4 <= t <= e[0] for e in mine):
                        return False
        t += 0.03
    return True


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
    pac, eat, heads, events, end = build_pacman(cells, cols)
    D = end + HOLD
    ghosts = None
    for seed in range(1, 800):
        ghosts = make_ghosts(seed, pac, events, D, W)
        if valid(ghosts, pac, events, D):
            break
    restore = end + HOLD / 2

    scale = [(0.0, 1.0)]
    spin = [(0.0, 0.0)]
    for te, _, _ in events:
        scale += [(te, 1.0), (te + 0.7, 0.0), (te + 1.15, 0.0), (te + 1.4, 1.0)]
        spin += [(te, 0.0), (te + 0.7, 720.0), (te + 1.4, 720.0), (te + 1.41, 0.0)]
    scale.append((D, 1.0))
    spin.append((D, 0.0))

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

    dur = f'dur="{D:.3f}s" repeatCount="indefinite"'
    if snapshot is None:
        kt, vals = keyframes(pac.pts, D, lambda x, y: f"{x:.1f} {y:.1f}")
        hk = [(0.0, heads[0][1])] + heads[1:] if heads[0][0] > 0 else list(heads)
        hk.append((D, hk[-1][1]))
        hkt, hv = keyframes(hk, D, lambda a: f"{a}")
        skt, sv = keyframes(scale, D, lambda s: f"{s:.2f}")
        rkt, rv = keyframes(spin, D, lambda a: f"{a:.0f}")
        o.append(f'<g><animateTransform attributeName="transform" type="translate" calcMode="linear" {dur} keyTimes="{kt}" values="{vals}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="rotate" calcMode="discrete" {dur} keyTimes="{hkt}" values="{hv}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="rotate" calcMode="linear" {dur} keyTimes="{rkt}" values="{rv}"/>')
        o.append(f'<g><animateTransform attributeName="transform" type="scale" calcMode="linear" {dur} keyTimes="{skt}" values="{sv}"/>')
        o.append(
            f'<path fill="#ffd400" d="{wedge(38)}"><animate attributeName="d" dur="0.36s" repeatCount="indefinite" '
            f'values="{wedge(38)};{wedge(3)};{wedge(38)}"/></path>'
        )
        o.append("</g></g></g></g>")
        for gi, g in enumerate(ghosts):
            gk, gv = keyframes(g.pts, D, lambda x, y: f"{x:.1f} {y:.1f}")
            o.append(
                f'<g><animateTransform attributeName="transform" type="translate" calcMode="linear" {dur} keyTimes="{gk}" values="{gv}"/>'
                f"{ghost_shape(GHOSTS[gi])}</g>"
            )
    else:
        px, py = pac.at(snapshot)
        sc = Track(scale).at(snapshot)[0]
        ang = [a for t, a in heads if t <= snapshot]
        ang = ang[-1] if ang else heads[0][1]
        if sc > 0.01:
            o.append(f'<g transform="translate({px:.1f} {py:.1f}) rotate({ang}) scale({sc:.2f})"><path fill="#ffd400" d="{wedge(30)}"/></g>')
        for gi, g in enumerate(ghosts):
            gx, gy = g.at(snapshot)
            o.append(f'<g transform="translate({gx:.1f} {gy:.1f})">{ghost_shape(GHOSTS[gi])}</g>')
    o.append("</svg>")
    return "\n".join(o), D, events


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
        svg, D, ev = build(weeks, snapshot=a.snapshot)
        open(os.path.join(a.out, "snapshot.svg"), "w", encoding="utf-8").write(svg)
        return
    svg, D, ev = build(weeks)
    open(os.path.join(a.out, "contribution-pacman-dark.svg"), "w", encoding="utf-8").write(svg)
    still_t = D * 0.35
    for te, _, _ in ev:
        if te <= still_t <= te + DEATH + 1.0:
            still_t = te + DEATH + 1.0
    still, _, _ = build(weeks, snapshot=still_t)
    open(os.path.join(a.out, "contribution-pacman-still-dark.svg"), "w", encoding="utf-8").write(still)
    print(f"ok: duration={D:.1f}s deaths={len(ev)}")


if __name__ == "__main__":
    main()
