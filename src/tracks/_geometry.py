"""Circuit layout builder.

Authoring 10 clean circuits by hand-placing raw control points is error prone,
so each layout is described as a sequence of straights and constant-radius
corners.  ``build()`` walks that description like a turtle, dropping a control
point every ~``step`` units, so every corner is a real arc of a chosen radius
and the inside edge can never pinch.

Closure is exact and automatic:

  * every corner angle is scaled by one factor so the angles sum to exactly
    -360 -> the turtle's heading returns to the start heading;
  * exactly two straights are given as ``("s", None)`` and the builder solves
    their two lengths (a 2x2 linear system) so the loop lands back on the start
    position.  If the shape is a little over-long the fixed straights are shrunk
    uniformly until that solve is well-conditioned.

The author only has to get the *relative* sharpness / direction of the corners
and the rough proportions of the shape right, and leave two roughly
perpendicular straights free.

    ("s", length | None)      straight  (None -> solved so the loop closes)
    ("c", angle_deg, radius)   corner   (+angle = left, -angle = right)
"""

from __future__ import annotations

import math


def _walk(start, heading_deg, pieces, step, free_len):
    x, y = float(start[0]), float(start[1])
    h = math.radians(heading_deg)
    pts = [(x, y)]
    free_dirs = []
    for piece in pieces:
        if piece[0] == "s":
            if piece[1] is None:
                free_dirs.append((math.cos(h), math.sin(h)))
                length = free_len
            else:
                length = float(piece[1])
            n = max(1, round(max(length, 1.0) / step))
            dl = length / n
            for _ in range(n):
                x += math.cos(h) * dl
                y += math.sin(h) * dl
                pts.append((x, y))
        elif piece[0] == "c":
            ang = math.radians(piece[1])
            radius = float(piece[2])
            side = 1.0 if piece[1] > 0 else -1.0
            cx = x + math.cos(h + side * math.pi / 2) * radius
            cy = y + math.sin(h + side * math.pi / 2) * radius
            a0 = math.atan2(y - cy, x - cx)
            total = abs(ang)
            n = max(2, round(total * radius / step))
            for k in range(1, n + 1):
                a = a0 + side * total * (k / n)
                x = cx + math.cos(a) * radius
                y = cy + math.sin(a) * radius
                pts.append((x, y))
            h += ang
        else:
            raise ValueError(f"bad layout piece {piece!r}")
    return pts, (x, y), h, free_dirs


def _normalise_turn(pieces):
    total = sum(p[1] for p in pieces if p[0] == "c")
    if abs(total) < 1e-6:
        raise ValueError("layout has no net turn")
    f = -360.0 / total
    return [("c", p[1] * f, p[2]) if p[0] == "c" else p for p in pieces]


def _solve(start, heading_deg, pieces, step):
    _, end0, _, dirs = _walk(start, heading_deg, pieces, step, 0.0)
    if len(dirs) != 2:
        raise ValueError("layout must contain exactly two ('s', None) straights")
    (d1x, d1y), (d2x, d2y) = dirs
    rx, ry = start[0] - end0[0], start[1] - end0[1]
    det = d1x * d2y - d1y * d2x
    if abs(det) < 1e-4:
        raise ValueError("the two free straights are parallel - cannot close")
    l1 = (rx * d2y - ry * d2x) / det
    l2 = (d1x * ry - d1y * rx) / det
    return l1, l2


def build(start, heading_deg, pieces, *, step=140.0, target_length=None):
    pieces = _normalise_turn(list(pieces))

    scale = 1.0
    for _ in range(18):
        scaled = [("s", p[1] * scale) if (p[0] == "s" and p[1] is not None) else p
                  for p in pieces]
        l1, l2 = _solve(start, heading_deg, scaled, step)
        if l1 >= 45.0 and l2 >= 45.0:
            break
        scale *= 0.85
    else:
        raise ValueError(f"cannot close layout (free lengths {l1:.0f}, {l2:.0f} "
                         f"at scale {scale:.2f}) - rework the corner sequence")

    resolved, seen = [], 0
    for p in scaled:
        if p[0] == "s" and p[1] is None:
            resolved.append(("s", l1 if seen == 0 else l2))
            seen += 1
        else:
            resolved.append(p)
    pts, _, _, _ = _walk(start, heading_deg, resolved, step, 0.0)
    pts.pop()

    if target_length:
        peri = sum(math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1])
                   for i in range(len(pts)))
        k = target_length / max(peri, 1.0)
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        pts = [(cx + (x - cx) * k, cy + (y - cy) * k) for x, y in pts]

    return [(round(x, 1), round(y, 1)) for x, y in pts]


def closure_gap(start, heading_deg, pieces, *, step=140.0):
    pts = build(start, heading_deg, pieces, step=step)
    return math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1])
