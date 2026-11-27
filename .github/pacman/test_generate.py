import unittest
import xml.etree.ElementTree as ET

from generate import build, demo


class MazeAnimationTest(unittest.TestCase):
    def test_rendered_routes_close_and_do_not_cross_walls(self):
        xml, duration, deaths = build(demo())
        root = ET.fromstring(xml)
        ns = {"s": "http://www.w3.org/2000/svg"}
        lines = root.findall(".//s:line[@stroke='#668cff']", ns)
        self.assertGreater(len(lines), 80)
        walls = [
            tuple(float(line.get(point)) for point in ("x1", "y1", "x2", "y2"))
            for line in lines
        ]
        routes = root.findall(".//s:animateTransform[@type='translate']", ns)
        self.assertEqual(len(routes), 5)
        self.assertEqual(len(deaths), 2)
        for index, route in enumerate(routes):
            times = list(map(float, route.get("keyTimes").split(";")))
            points = [tuple(map(float, pair.split())) for pair in route.get("values").split(";")]
            self.assertEqual((times[0], times[-1]), (0, 1))
            self.assertEqual(points[0], points[-1])
            self.assertGreater(len(set(points)), 10)
            for (x, y), (nx, ny), t, nt in zip(points, points[1:], times, times[1:]):
                if index == 0 and any(abs(nt * duration - respawn) < .002 for _, respawn in deaths):
                    self.assertEqual((nx, ny), points[0])
                    continue
                distance = abs(nx - x) + abs(ny - y)
                self.assertIn(distance, (0, 22))
                self.assertTrue(x == nx or y == ny)
                if distance:
                    self.assertGreaterEqual((nt - t) * duration, 0.14)
                for a, b, c, d in walls:
                    crosses = (
                        a == c and min(x, nx) < a < max(x, nx) and b <= y <= d
                        or b == d and min(y, ny) < b < max(y, ny) and a <= x <= c
                    )
                    self.assertFalse(crosses, ((x, y), (nx, ny), (a, b, c, d)))

    def test_deaths_have_a_ghost_at_impact_and_distinct_life_routes(self):
        xml, duration, deaths = build(demo())
        root = ET.fromstring(xml)
        ns = {"s": "http://www.w3.org/2000/svg"}
        routes = root.findall(".//s:animateTransform[@type='translate']", ns)
        tracks = [route.get("values").split(";") for route in routes]
        timeline = [float(value) * duration for value in routes[0].get("keyTimes").split(";")]
        self.assertEqual(len(deaths), 2)
        self.assertIsNotNone(root.find(".//s:animate[@attributeName='visibility']", ns))
        starts = [0]
        for impact, respawn in deaths:
            frame = min(range(len(timeline)), key=lambda i: abs(timeline[i] - impact))
            self.assertIn(tracks[0][frame], [track[frame] for track in tracks[1:]])
            starts.append(min(range(len(timeline)), key=lambda i: abs(timeline[i] - respawn)))
        openings = {tuple(tracks[0][start:start + 12]) for start in starts}
        self.assertEqual(len(openings), 3)

    def test_still_keeps_grid_and_walls_without_animation(self):
        xml, _, _ = build(demo(), snapshot=0)
        root = ET.fromstring(xml)
        ns = {"s": "http://www.w3.org/2000/svg"}
        self.assertEqual(root.find("s:rect", ns).get("fill"), "#0d1117")
        self.assertGreater(len(root.findall("s:rect[@width='20'][@height='20'][@rx='4']", ns)), 365)
        self.assertIsNotNone(root.find(".//s:line[@stroke='#668cff']", ns))
        self.assertIsNone(root.find(".//s:animateTransform", ns))


if __name__ == "__main__":
    unittest.main()
