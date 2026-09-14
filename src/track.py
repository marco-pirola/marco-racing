"""A built, collidable, drawable circuit - one definitive implementation.

``Track`` turns a :class:`src.tracks.base.TrackDefinition` (pure data) into
everything the race needs.  There is exactly one geometry model:

    centre line (Catmull-Rom spline)
        |  road_half        -> asphalt edge        (edge_l / edge_r)
        |  + kerb_w          -> kerb outer edge      (kerb_l / kerb_r)
        |  + runoff_w        -> barrier / wall       (wall_l / wall_r, == wall_half)

Rendering and collision both use those same numbers.  Collision is analytic:
for any point we find the nearest centre-line segment, the signed lateral
offset and the local normal.  From the offset (and whether a kerb belongs
there) we get the surface; past ``wall_half`` we know exactly how far and which
way to push the car back, so nothing tunnels even at top speed.

Kerbs are only drawn (and only felt) where the circuit actually turns; their
red/white stripes are keyed to distance travelled along the track, so they stay
even and continuous through corners of any radius and across the start/finish
seam.
"""

from __future__ import annotations

import math
import random

import pygame

from .tracks.base import build_centerline, theme as get_theme
from .utils import angle_diff, clamp, draw_text


class _BakeCamera:
    """Stand-in 'camera' used only to bake ``Track``'s static layer once:
    maps world coordinates 1:1 into that layer's local pixel space (its
    origin is the track's world bounds top-left)."""

    zoom = 1.0

    def __init__(self, origin):
        self._origin = origin

    def world_to_screen(self, world_pos):
        return pygame.Vector2(world_pos) - self._origin


class Track:
    # --- kerb tuning ------------------------------------------------- #
    KERB_CURV_THRESH = 11.0    # curvature (deg / 100u) above which it's "a corner"
    KERB_DILATE = 80.0         # kerb reaches this far into corner entry / exit
    KERB_STRIPE = 46.0         # world units per red/white segment
    BARRIER_THICK = 7.0        # visual thickness of the wall, world units

    def __init__(self, definition):
        d = self.definition = definition
        self.theme = get_theme(d.theme)
        self.road_half = float(d.road_half)
        self.kerb_w = float(d.kerb_w)
        self.runoff_w = float(d.runoff_w)
        self.kerb_outer = self.road_half + self.kerb_w
        self.wall_half = self.road_half + self.kerb_w + self.runoff_w
        self.laps = int(d.laps)
        self.ai_grip_bonus = float(d.ai_grip_bonus)

        self.points = build_centerline(d)
        self.n = n = len(self.points)

        # --- tangents / normals / arc length ---------------------- #
        self.tangents: list[pygame.Vector2] = []
        self.normals: list[pygame.Vector2] = []
        for i in range(n):
            t = self.points[(i + 1) % n] - self.points[(i - 1) % n]
            t = t.normalize() if t.length_squared() > 1e-9 else pygame.Vector2(1, 0)
            self.tangents.append(t)
            self.normals.append(pygame.Vector2(-t.y, t.x))

        self.seg_len: list[float] = []
        self.cum_len: list[float] = [0.0]
        for i in range(n):
            self.seg_len.append(max((self.points[(i + 1) % n] - self.points[i]).length(), 1e-4))
            self.cum_len.append(self.cum_len[-1] + self.seg_len[i])
        self.length = self.cum_len[-1]

        # --- the one set of boundary polylines ------------------- #
        rh, ko, wh = self.road_half, self.kerb_outer, self.wall_half
        self.edge_l = [self.points[i] + self.normals[i] * rh for i in range(n)]
        self.edge_r = [self.points[i] - self.normals[i] * rh for i in range(n)]
        self.kerb_l = [self.points[i] + self.normals[i] * ko for i in range(n)]
        self.kerb_r = [self.points[i] - self.normals[i] * ko for i in range(n)]
        self.wall_l = [self.points[i] + self.normals[i] * wh for i in range(n)]
        self.wall_r = [self.points[i] - self.normals[i] * wh for i in range(n)]
        ih = wh - self.BARRIER_THICK
        self.inner_l = [self.points[i] + self.normals[i] * ih for i in range(n)]
        self.inner_r = [self.points[i] - self.normals[i] * ih for i in range(n)]

        # --- curvature: signed degrees of heading change per 100 units of
        #     arc, measured over a fixed ~150-unit window so it is independent
        #     of node spacing.  ~0 on a straight, ~15-30 in a medium corner,
        #     ~45-70 in a hairpin.  Used by the AI and by kerb placement.
        w_units = 150.0
        win = max(1, int(w_units / (self.length / n)))
        sc = [0.0] * n
        for i in range(n):
            a, b = self.tangents[(i - win) % n], self.tangents[(i + win) % n]
            dtheta = angle_diff(math.degrees(math.atan2(b.y, b.x)),
                                math.degrees(math.atan2(a.y, a.x)))
            arc = sum(self.seg_len[(i - win + k) % n] for k in range(2 * win)) or 1.0
            sc[i] = dtheta / arc * 100.0
        self.signed_curv = [(sc[(i - 1) % n] + 2 * sc[i] + sc[(i + 1) % n]) / 4.0
                            for i in range(n)]
        self.curvature = [abs(v) for v in self.signed_curv]
        look = max(2, int(200.0 / (self.length / n)))
        self.corner_speed = [
            clamp(1.0 - max(self.curvature[(i + k) % n] for k in range(look)) / 95.0,
                  0.32, 1.0)
            for i in range(n)
        ]

        # --- where kerbs belong (corners, both sides, dilated) --- #
        self.kerb_on = self._compute_kerb_on()

        self.bounds = self._compute_bounds()

        # --- start / finish on the longest straight ------------- #
        seg_per_node = self.length / n
        run = max(4, int(1000 / seg_per_node))
        best_i, best_score = 0, float("inf")
        for i in range(n):
            ahead = sum(self.curvature[(i + k) % n] for k in range(run))
            behind = sum(self.curvature[(i - k) % n] for k in range(run // 2))
            if ahead + 0.6 * behind < best_score:
                best_score, best_i = ahead + 0.6 * behind, i
        self.start_node = (best_i + run // 2) % n
        self.start_arc = self.cum_len[self.start_node]

        # --- checkpoints (index 0 == start / finish) ------------ #
        self.checkpoint_count = max(3, int(d.checkpoint_count))
        self.checkpoint_nodes = [(self.start_node + round(k * n / self.checkpoint_count)) % n
                                 for k in range(self.checkpoint_count)]
        self.gates = []
        for order, node in enumerate(self.checkpoint_nodes):
            p, nrm = self.points[node], self.normals[node]
            self.gates.append({
                "order": order, "node": node,
                "a": p + nrm * (wh + 12), "b": p - nrm * (wh + 12),
                "center": pygame.Vector2(p),
            })

        self.start_pos = pygame.Vector2(self.points[self.start_node])
        self.start_angle = math.degrees(math.atan2(self.tangents[self.start_node].y,
                                                   self.tangents[self.start_node].x))

        # --- precomputed render geometry ----------------------- #
        self._kerb_quads = self._build_kerb_quads()
        self._start_quads = self._build_start_quads()
        self._decor = self._build_decor()
        self._texture = self._build_texture()
        self._wash = None
        self._wash_size = None

        # --- static layer: everything above is world-fixed and never
        #     changes after construction, so it is painted once (below,
        #     lazily on first draw()) into one Surface and simply
        #     cropped + scaled + blitted every frame afterwards, instead
        #     of re-walking every node / re-issuing hundreds of draw
        #     calls per frame. ------------------------------------------ #
        self._static_layer = None
        self._static_origin = None
        self._scale_buf = None

    # ================================================================ #
    #  Geometry helpers
    # ================================================================ #
    def _compute_bounds(self):
        xs = [p.x for p in self.wall_l] + [p.x for p in self.wall_r]
        ys = [p.y for p in self.wall_l] + [p.y for p in self.wall_r]
        pad = 600
        return pygame.Rect(min(xs) - pad, min(ys) - pad,
                           max(xs) - min(xs) + pad * 2, max(ys) - min(ys) + pad * 2)

    def _compute_kerb_on(self):
        n = self.n
        strong = [self.curvature[i] > self.KERB_CURV_THRESH for i in range(n)]
        dil = max(1, int(self.KERB_DILATE / (self.length / n)))
        on = [False] * n
        for i in range(n):
            if any(strong[j % n] for j in range(i - dil, i + dil + 1)):
                on[i] = True
        return on

    def _arc_pn(self, arc: float):
        """(point, unit normal) at raw arc length ``arc`` (0..length)."""
        arc %= self.length
        lo, hi = 0, self.n
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cum_len[mid + 1] < arc:
                lo = mid + 1
            else:
                hi = mid
        i = min(lo, self.n - 1)
        t = clamp((arc - self.cum_len[i]) / self.seg_len[i], 0.0, 1.0)
        p = self.points[i].lerp(self.points[(i + 1) % self.n], t)
        tan = self.tangents[i].lerp(self.tangents[(i + 1) % self.n], t)
        tan = tan.normalize() if tan.length_squared() > 1e-9 else self.tangents[i]
        return p, pygame.Vector2(-tan.y, tan.x)

    def _kerb_runs(self):
        """Contiguous arc ranges (a0, a1) where a kerb should be drawn."""
        mask, n = self.kerb_on, self.n
        if not any(mask):
            return []
        if all(mask):
            return [(0.0, self.length)]
        start = next(i for i in range(n) if not mask[i])
        runs, open_arc = [], None
        for k in range(n + 1):
            i = (start + k) % n
            if mask[i] and open_arc is None:
                open_arc = self.cum_len[i]
            elif not mask[i] and open_arc is not None:
                end = self.cum_len[i]
                if end <= open_arc:
                    end += self.length
                runs.append((open_arc, end))
                open_arc = None
        return runs

    def _build_kerb_quads(self):
        rh, ko = self.road_half, self.kerb_outer
        a_col, b_col = self.theme["kerb_a"], self.theme["kerb_b"]
        quads = []
        for a0, a1 in self._kerb_runs():
            arc = a0
            while arc < a1 - 1e-3:
                arc2 = min(arc + self.KERB_STRIPE, a1)
                p0, n0 = self._arc_pn(arc)
                p1, n1 = self._arc_pn(arc2)
                col = a_col if int(arc / self.KERB_STRIPE) % 2 == 0 else b_col
                quads.append(([p0 + n0 * rh, p1 + n1 * rh,
                               p1 + n1 * ko, p0 + n0 * ko], col))          # left
                quads.append(([p0 - n0 * rh, p1 - n1 * rh,
                               p1 - n1 * ko, p0 - n0 * ko], col))          # right
                arc = arc2
        return quads

    def _build_start_quads(self):
        node = self.start_node
        p, nrm, tan = self.points[node], self.normals[node], self.tangents[node]
        cols, depth = 8, 44
        cell = 2 * self.road_half / cols
        out = []
        for c in range(cols):
            base = p + nrm * ((c - cols / 2) * cell)
            for row in range(2):
                col = (238, 238, 238) if (c + row) % 2 == 0 else (24, 24, 28)
                out.append(([
                    base + tan * (row * depth - depth),
                    base + tan * ((row + 1) * depth - depth),
                    base + nrm * cell + tan * ((row + 1) * depth - depth),
                    base + nrm * cell + tan * (row * depth - depth),
                ], col))
        return out

    # ================================================================ #
    #  Query API
    # ================================================================ #
    def starting_grid(self, count: int):
        """(pos, angle) per car, two-wide, following the line backwards."""
        grid = []
        side_amt = min(46.0, self.road_half * 0.40)
        for i in range(count):
            back = 58.0 + (i // 2) * 96.0
            p, tan, hint = self.node_at_progress((-back) % self.length)
            nrm = pygame.Vector2(-tan.y, tan.x)
            pos = p + nrm * ((-1 if i % 2 == 0 else 1) * side_amt)
            s = self.sample(pos, hint)
            if s["surface"] == "grass" or s["wall"]:
                pos = s["closest"] + s["normal"] * clamp(
                    s["offset"], -self.road_half * 0.55, self.road_half * 0.55)
            grid.append((pygame.Vector2(pos),
                         math.degrees(math.atan2(tan.y, tan.x))))
        return grid

    def sample(self, pos, hint: int = 0):
        """Locate ``pos`` relative to the circuit.

        Keys: node, t, closest, tangent, normal, offset (signed, + = left of
        travel), progress (from the start line), surface (track|kerb|grass),
        side (L|R), wall, wall_normal, penetration, dist_to_wall.
        """
        pos = pygame.Vector2(pos)

        def scan(indices):
            bd, bb = float("inf"), None
            for raw in indices:
                i = raw % self.n
                a = self.points[i]
                ab = self.points[(i + 1) % self.n] - a
                seg2 = ab.length_squared()
                tt = clamp((pos - a).dot(ab) / seg2, 0.0, 1.0) if seg2 > 1e-9 else 0.0
                proj = a + ab * tt
                d2 = (pos - proj).length_squared()
                if d2 < bd:
                    bd, bb = d2, (i, tt, proj)
            return bd, bb

        best_d2, best = scan(range(hint - 5, hint + 15))
        if best is None or best_d2 > (self.wall_half * 1.3) ** 2:
            step = max(1, self.n // 56)
            _, coarse = scan(range(0, self.n, step))
            cd2, cbest = scan(range(coarse[0] - step, coarse[0] + step + 2))
            if best is None or cd2 < best_d2:
                best_d2, best = cd2, cbest

        i, t, proj = best
        tangent = self.tangents[i].lerp(self.tangents[(i + 1) % self.n], t)
        tangent = tangent.normalize() if tangent.length_squared() > 1e-9 else self.tangents[i]
        normal = pygame.Vector2(-tangent.y, tangent.x)
        offset = (pos - proj).dot(normal)
        dist = abs(offset)
        progress = (self.cum_len[i] + self.seg_len[i] * t - self.start_arc) % self.length

        has_kerb = self.kerb_on[i] or self.kerb_on[(i + 1) % self.n]
        if dist <= self.road_half:
            surface = "track"
        elif has_kerb and dist <= self.kerb_outer:
            surface = "kerb"
        else:
            surface = "grass"

        wall = dist >= self.wall_half
        wall_normal, penetration = pygame.Vector2(), 0.0
        if wall:
            wall_normal = normal * (-1.0 if offset > 0 else 1.0)
            penetration = dist - self.wall_half

        return {
            "node": i, "t": t, "closest": proj,
            "tangent": tangent, "normal": normal,
            "offset": offset, "progress": progress,
            "surface": surface, "side": "L" if offset > 0 else "R",
            "wall": wall, "wall_normal": wall_normal, "penetration": penetration,
            "dist_to_wall": self.wall_half - dist,
        }

    def node_at_progress(self, progress: float):
        """(point, unit tangent, node index) at a start-line-relative progress."""
        arc = (progress + self.start_arc) % self.length
        lo, hi = 0, self.n
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cum_len[mid + 1] < arc:
                lo = mid + 1
            else:
                hi = mid
        i = min(lo, self.n - 1)
        t = clamp((arc - self.cum_len[i]) / self.seg_len[i], 0.0, 1.0)
        p = self.points[i].lerp(self.points[(i + 1) % self.n], t)
        tan = self.tangents[i].lerp(self.tangents[(i + 1) % self.n], t)
        tan = tan.normalize() if tan.length_squared() > 1e-9 else self.tangents[i]
        return p, tan, i

    def point_ahead(self, progress: float, distance: float):
        return self.node_at_progress(progress + distance)[0]

    def node_index_at_progress(self, progress: float) -> int:
        return self.node_at_progress(progress)[2]

    def signed_curvature_ahead(self, progress: float, distance: float) -> float:
        i0 = self.node_index_at_progress(progress)
        span = max(1, int(distance / max(1.0, self.length / self.n)))
        worst = 0.0
        for k in range(span):
            c = self.signed_curv[(i0 + k) % self.n]
            if abs(c) > abs(worst):
                worst = c
        return worst

    def corner_speed_ahead(self, progress: float, distance: float) -> float:
        i0 = self.node_index_at_progress(progress)
        span = max(1, int(distance / max(1.0, self.length / self.n)))
        return min(self.corner_speed[(i0 + k) % self.n] for k in range(span))

    # ================================================================ #
    #  Decoration / texture (built once, drawn culled)
    # ================================================================ #
    def _build_decor(self):
        kinds = self.theme["decor"]
        if not kinds:
            return []
        rng = random.Random(hash(self.definition.id) & 0xFFFFFF)
        items = []
        arc = 0.0
        while arc < self.length:
            arc += rng.uniform(150, 320)
            p, nrm = self._arc_pn(arc)
            for _ in range(rng.randint(1, 2)):
                side = 1 if rng.random() < 0.5 else -1
                dist = self.wall_half + rng.uniform(50, 460)
                pos = p + nrm * (side * dist)
                # skip if that lands on another part of the circuit
                if abs(self.sample(pos, 0)["offset"]) < self.wall_half + 30:
                    continue
                items.append(self._make_decor(rng.choice(kinds), pos, rng))
        return [it for it in items if it]

    def _make_decor(self, kind, pos, rng):
        if kind == "building":
            return ("rect", pos, rng.uniform(140, 340), rng.uniform(140, 360),
                    rng.choice([(60, 62, 72), (70, 72, 82), (52, 54, 64)]))
        if kind == "warehouse":
            return ("rect", pos, rng.uniform(260, 460), rng.uniform(160, 240),
                    rng.choice([(96, 92, 84), (110, 104, 94)]))
        if kind == "container":
            return ("rect", pos, rng.uniform(90, 150), rng.uniform(44, 60),
                    rng.choice([(180, 90, 60), (60, 120, 150), (150, 140, 60), (90, 140, 90)]))
        if kind == "tank":
            return ("circle", pos, rng.uniform(60, 110), 0, (150, 150, 156))
        if kind == "tree":
            return ("circle", pos, rng.uniform(24, 52), 0,
                    rng.choice([(40, 92, 46), (34, 80, 40), (48, 104, 52)]))
        if kind == "rock":
            return ("circle", pos, rng.uniform(28, 72), 0,
                    rng.choice([(120, 112, 100), (100, 94, 84), (138, 128, 116)]))
        if kind == "dune":
            return ("dune", pos, rng.uniform(220, 460), rng.uniform(80, 170),
                    rng.choice([(214, 182, 122), (204, 170, 110)]))
        if kind == "water":
            return ("blob", pos, rng.uniform(300, 620), rng.uniform(240, 460),
                    rng.choice([(58, 140, 182), (66, 154, 196)]))
        if kind == "palm":
            return ("circle", pos, rng.uniform(20, 34), 0, (46, 110, 60))
        if kind == "light":
            return ("glow", pos, rng.uniform(46, 92), 0,
                    rng.choice([(120, 220, 255), (255, 210, 120)]))
        if kind == "neon":
            return ("glow", pos, rng.uniform(60, 120), 0,
                    rng.choice([(255, 80, 170), (90, 240, 255), (170, 120, 255)]))
        if kind == "pylon":
            return ("rect", pos, rng.uniform(24, 34), rng.uniform(220, 360), (86, 86, 96))
        if kind == "stand":
            return ("stand", pos, rng.uniform(320, 560), rng.uniform(90, 130),
                    (150, 152, 160))
        if kind == "billboard":
            return ("rect", pos, rng.uniform(120, 200), rng.uniform(70, 110),
                    rng.choice([(220, 90, 80), (80, 160, 200), (230, 200, 90)]))
        return None

    def _build_texture(self):
        rng = random.Random((hash(self.definition.id) >> 3) & 0xFFFFFF)
        spots = []
        for _ in range(int(self.n * 0.55)):
            i = rng.randrange(self.n)
            off = rng.uniform(-self.road_half * 0.82, self.road_half * 0.82)
            spots.append((self.points[i] + self.normals[i] * off, rng.uniform(14, 38)))
        return spots

    # ================================================================ #
    #  Rendering
    # ================================================================ #
    @staticmethod
    def _ring(camera, left, right):
        return ([camera.world_to_screen(p) for p in left]
                + [camera.world_to_screen(p) for p in reversed(right)])

    def draw(self, surface, camera, *, debug=False):
        th = self.theme
        if self._static_layer is None:
            self._build_static_layer()

        self._draw_ground(surface, camera)
        self._blit_static_layer(surface, camera)

        if th["ambient"]:
            size = surface.get_size()
            if self._wash_size != size:
                self._wash = pygame.Surface(size, pygame.SRCALPHA)
                self._wash.fill(th["ambient"])
                self._wash_size = size
            surface.blit(self._wash, (0, 0))

        if debug:
            self.draw_debug(surface, camera)

    def _build_static_layer(self):
        """Paint every world-fixed layer (run-off, asphalt, texture, edge
        lines, kerbs, centre dashes, barrier, start grid, checkpoint hints,
        decor) once into one Surface, in world-space 1:1 pixels.  ``draw()``
        then just crops+scales the visible part of this instead of redoing
        all of that work (and hundreds of world->screen conversions) every
        single frame."""
        th = self.theme
        b = self.bounds
        origin = pygame.Vector2(b.x, b.y)
        layer = pygame.Surface((b.w, b.h), pygame.SRCALPHA)
        cam = _BakeCamera(origin)
        z = cam.zoom

        # run-off band (whole corridor), then asphalt on top -> the strip left
        # showing between them IS the run-off
        pygame.draw.polygon(layer, th["runoff"], self._ring(cam, self.wall_l, self.wall_r))
        pygame.draw.polygon(layer, th["asphalt"], self._ring(cam, self.edge_l, self.edge_r))
        self._draw_texture(layer, cam, None)

        # painted edge line everywhere
        self._polyline(layer, cam, self.edge_l, th["line"], max(1, int(2 * z)))
        self._polyline(layer, cam, self.edge_r, th["line"], max(1, int(2 * z)))

        # kerbs - corners only, arc-striped, glued to the edge
        self._draw_kerbs(layer, cam, None)

        # centre dashes
        for i in range(0, self.n, 5):
            pygame.draw.line(layer, th["line"],
                             cam.world_to_screen(self.points[i]),
                             cam.world_to_screen(self.points[(i + 2) % self.n]),
                             max(1, int(3 * z)))

        # solid barrier at wall_half
        self._draw_barrier(layer, cam)

        # start / finish + checkpoint hints
        for quad, col in self._start_quads:
            pygame.draw.polygon(layer, col, [cam.world_to_screen(q) for q in quad])
        self._draw_checkpoint_hints(layer, cam, None)

        self._draw_decor(layer, cam, None)

        self._static_layer = layer
        self._static_origin = origin

    def _blit_static_layer(self, surface, camera):
        layer = self._static_layer
        vis = camera.visible_rect()
        crop = pygame.Rect(round(vis.x - self._static_origin.x),
                           round(vis.y - self._static_origin.y),
                           max(1, round(vis.w)), max(1, round(vis.h)))
        crop = crop.clip(layer.get_rect())
        if crop.w <= 0 or crop.h <= 0:
            return

        dest_size = (max(1, round(crop.w * camera.zoom)),
                     max(1, round(crop.h * camera.zoom)))
        if self._scale_buf is None or self._scale_buf.get_size() != dest_size:
            self._scale_buf = pygame.Surface(dest_size, pygame.SRCALPHA)
        sub = layer.subsurface(crop)
        pygame.transform.scale(sub, dest_size, self._scale_buf)

        dest_pos = camera.world_to_screen((crop.x + self._static_origin.x,
                                           crop.y + self._static_origin.y))
        surface.blit(self._scale_buf, dest_pos)

    @staticmethod
    def _polyline(surface, camera, world_pts, color, width):
        pygame.draw.lines(surface, color, True,
                          [camera.world_to_screen(p) for p in world_pts], width)

    def _draw_ground(self, surface, camera):
        th = self.theme
        surface.fill(th["ground"])
        vis = camera.visible_rect()
        stripe = 320
        x = int(vis.left // stripe) * stripe
        toggle = int(x // stripe) % 2
        while x < vis.right + stripe:
            if toggle:
                tl = camera.world_to_screen((x, vis.top - 30))
                br = camera.world_to_screen((x + stripe, vis.bottom + 30))
                pygame.draw.rect(surface, th["ground_dark"],
                                 pygame.Rect(tl, (br.x - tl.x, br.y - tl.y)))
            x += stripe
            toggle ^= 1

    def _draw_decor(self, surface, camera, vis):
        z = camera.zoom
        for kind, p, w, h, col in self._decor:
            if vis is not None and not vis.collidepoint(p):
                continue
            sp = camera.world_to_screen(p)
            if kind == "rect":
                rect = pygame.Rect(0, 0, max(2, w * z), max(2, h * z))
                rect.center = sp
                pygame.draw.rect(surface, tuple(int(c * 0.6) for c in col),
                                 rect.move(5 * z, 7 * z), border_radius=int(3 * z))
                pygame.draw.rect(surface, col, rect, border_radius=int(3 * z))
                pygame.draw.rect(surface, tuple(min(255, c + 20) for c in col),
                                 rect, width=max(1, int(2 * z)), border_radius=int(3 * z))
            elif kind == "circle":
                pygame.draw.circle(surface, tuple(int(c * 0.55) for c in col),
                                   (sp.x + 4 * z, sp.y + 5 * z), max(1, int(w * z)))
                pygame.draw.circle(surface, col, sp, max(1, int(w * z)))
            elif kind == "blob":
                rect = pygame.Rect(0, 0, max(4, w * z), max(4, h * z))
                rect.center = sp
                pygame.draw.ellipse(surface, col, rect)
            elif kind == "dune":
                rect = pygame.Rect(0, 0, max(4, w * z), max(4, h * z))
                rect.center = sp
                pygame.draw.ellipse(surface, col, rect)
            elif kind == "glow":
                r = max(2, int(w * z))
                g = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
                pygame.draw.circle(g, (*col, 55), (r, r), r)
                pygame.draw.circle(g, (*col, 150), (r, r), max(2, r // 3))
                surface.blit(g, g.get_rect(center=sp))
            elif kind == "stand":
                rect = pygame.Rect(0, 0, max(6, w * z), max(4, h * z))
                rect.center = sp
                pygame.draw.rect(surface, (70, 72, 80), rect)
                for k in range(4):
                    band = pygame.Rect(rect.x, rect.y + k * rect.h // 4, rect.w, max(1, rect.h // 8))
                    pygame.draw.rect(surface, (200, 205, 214) if k % 2 else (150, 60, 60), band)

    def _draw_texture(self, surface, camera, vis):
        dark = self.theme["asphalt_dark"]
        z = camera.zoom
        for p, r in self._texture:
            if vis is not None and not vis.collidepoint(p):
                continue
            pygame.draw.circle(surface, dark, camera.world_to_screen(p), max(1, int(r * z)))

    def _draw_kerbs(self, surface, camera, vis):
        for quad, col in self._kerb_quads:
            if vis is not None and not vis.collidepoint(quad[0]):
                continue
            pygame.draw.polygon(surface, col, [camera.world_to_screen(q) for q in quad])

    def _draw_barrier(self, surface, camera):
        col = self.theme["barrier"]
        hi = tuple(min(255, c + 26) for c in col)
        z = camera.zoom
        pygame.draw.polygon(surface, col, self._ring(camera, self.wall_l, self.inner_l))
        pygame.draw.polygon(surface, col, self._ring(camera, self.inner_r, self.wall_r))
        self._polyline(surface, camera, self.wall_l, hi, max(1, int(1.5 * z)))
        self._polyline(surface, camera, self.wall_r, hi, max(1, int(1.5 * z)))

    def _draw_checkpoint_hints(self, surface, camera, vis):
        z = camera.zoom
        for g in self.gates[1:]:
            if vis is not None and not vis.collidepoint(g["center"]):
                continue
            node = g["node"]
            a = g["center"] + self.normals[node] * self.road_half
            b = g["center"] - self.normals[node] * self.road_half
            pygame.draw.line(surface, (255, 255, 255), camera.world_to_screen(a),
                             camera.world_to_screen(b), max(1, int(2 * z)))

    # ================================================================ #
    #  Debug view
    # ================================================================ #
    def draw_debug(self, surface, camera, cars=None, ai_targets=None):
        z = camera.zoom

        def poly(pts, col, w=1):
            pygame.draw.lines(surface, col, True,
                              [camera.world_to_screen(p) for p in pts], max(1, int(w)))

        poly(self.points, (0, 255, 120), 1)               # centre line
        poly(self.edge_l, (255, 225, 40), 1)              # road edge
        poly(self.edge_r, (255, 225, 40), 1)
        poly(self.kerb_l, (255, 150, 40), 1)              # kerb outer edge
        poly(self.kerb_r, (255, 150, 40), 1)
        poly(self.wall_l, (255, 60, 60), max(1, int(2)))  # wall collision
        poly(self.wall_r, (255, 60, 60), max(1, int(2)))

        for g in self.gates:                              # checkpoints
            col = (255, 255, 255) if g["order"] == 0 else (0, 210, 255)
            pygame.draw.line(surface, col, camera.world_to_screen(g["a"]),
                             camera.world_to_screen(g["b"]), 2)
            pygame.draw.circle(surface, col, camera.world_to_screen(g["center"]), 4)

        if cars:
            for c in cars:
                s = self.sample(c.pos, getattr(c, "progress_hint", 0))
                col = ((255, 70, 70) if s["wall"] else
                       (255, 160, 40) if s["surface"] != "track" else (0, 255, 120))
                pygame.draw.line(surface, col, camera.world_to_screen(c.pos),
                                 camera.world_to_screen(s["closest"]), 2)
                pygame.draw.circle(surface, col, camera.world_to_screen(s["closest"]), 4)

        for tgt in (ai_targets or []):                    # AI waypoints
            pygame.draw.circle(surface, (255, 110, 255), camera.world_to_screen(tgt), 6, 2)

        legend = [("centre line", (0, 255, 120)), ("road edge", (255, 225, 40)),
                  ("kerb outer", (255, 150, 40)), ("wall / collision", (255, 60, 60)),
                  ("checkpoint", (0, 210, 255)), ("AI target", (255, 110, 255))]
        for k, (label, col) in enumerate(legend):
            y = 150 + k * 18
            pygame.draw.rect(surface, col, pygame.Rect(surface.get_width() - 190, y + 3, 14, 10))
            draw_text(surface, label, (surface.get_width() - 170, y), size=14, color=col)
