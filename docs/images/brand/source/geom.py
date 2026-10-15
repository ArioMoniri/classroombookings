"""Tiny geometry helpers for orthogonal rounded polygons (stdlib only)."""
import math

def fmt(v):
    v = round(v, 2)
    return str(int(v)) if v == int(v) else f"{v:g}"

def rounded_poly(pts, radii):
    """Closed orthogonal/straight polygon with per-vertex corner radius -> SVG path data."""
    n = len(pts)
    if isinstance(radii, (int, float)):
        radii = [radii] * n
    segs = []
    for i in range(n):
        p0, p1, p2 = pts[i - 1], pts[i], pts[(i + 1) % n]
        r = radii[i]
        din = (p1[0] - p0[0], p1[1] - p0[1]); lin = math.hypot(*din); din = (din[0] / lin, din[1] / lin)
        dout = (p2[0] - p1[0], p2[1] - p1[1]); lout = math.hypot(*dout); dout = (dout[0] / lout, dout[1] / lout)
        a = (p1[0] - din[0] * r, p1[1] - din[1] * r)
        b = (p1[0] + dout[0] * r, p1[1] + dout[1] * r)
        cross = din[0] * dout[1] - din[1] * dout[0]
        sweep = 1 if cross > 0 else 0
        segs.append((a, b, r, sweep))
    d = f"M{fmt(segs[0][1][0])} {fmt(segs[0][1][1])}"
    for i in range(1, n + 1):
        a, b, r, sweep = segs[i % n]
        d += f"L{fmt(a[0])} {fmt(a[1])}"
        if r > 0:
            d += f"A{fmt(r)} {fmt(r)} 0 0 {sweep} {fmt(b[0])} {fmt(b[1])}"
    return d + "Z"

def rot180(pts, c=128):
    return [(2 * c - x, 2 * c - y) for x, y in pts]

def svg(body, vb="0 0 256 256", title="SmartSched"):
    w, h = vb.split()[2:]
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb}" width="{w}" height="{h}" role="img" aria-label="{title}">'
            f'<title>{title}</title>{body}</svg>\n')
