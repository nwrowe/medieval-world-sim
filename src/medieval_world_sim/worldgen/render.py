"""Geography-faithful, dependency-free cartographic SVG for world review.

Relief is shaded from the *generated* height field (not decorative randomness),
contours are isolines of the same field, rivers use the saved downstream graph,
and road surfaces reflect inferred infrastructure. No game-state changes occur.
The embedded raster is encoded with the Python standard library; SVG vectors
remain sharp when the atlas is enlarged or exported as a PNG.
"""
from __future__ import annotations

from base64 import b64encode
from html import escape
from math import ceil, floor, hypot, log1p, sin, sqrt

from .hexgrid import center, edge_neighbor, map_size, vertices, SQRT3
from struct import pack
from zlib import compress, crc32

TILE_PX = 14
MARGIN = 28
TOP = 85
BOTTOM = 82
BIOME_COLORS = {
    "ocean": (105, 147, 158), "alpine": (177, 178, 171),
    "mountain": (147, 143, 132), "tundra": (185, 187, 167),
    "wetland": (102, 137, 121), "desert": (217, 189, 129),
    "steppe": (187, 177, 125), "hills": (171, 155, 119),
    "taiga": (95, 125, 108), "rainforest": (76, 117, 92),
    "forest": (112, 147, 106), "grassland": (159, 175, 119),
}


def _png_rgb(width: int, height: int, pixels: bytes) -> str:
    """Encode an RGB PNG with no third-party or platform-dependent packages."""
    def chunk(tag: bytes, payload: bytes) -> bytes:
        return pack('>I', len(payload)) + tag + payload + pack('>I', crc32(tag + payload))

    scanlines = bytearray()
    stride = width * 3
    for row in range(height):
        scanlines.append(0)  # PNG filter: None
        scanlines.extend(pixels[row * stride:(row + 1) * stride])
    png = (b'\x89PNG\r\n\x1a\n' +
           chunk(b'IHDR', pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
           chunk(b'IDAT', compress(scanlines, 6)) + chunk(b'IEND', b''))
    return b64encode(png).decode('ascii')


def _terrain_raster(world, tile_px: int) -> str:
    """Rasterize per-hex biome colors with elevation-derived hillshading.

    This intentionally does not interpolate an ocean or biome color across a
    land/water boundary; the transition is exactly the shared hex edge.
    """
    w, h = world.width, world.height
    width, height = map_size(w, h, tile_px)
    heights = [max(0, t.elevation_m) for t in world.tiles]
    output = bytearray((108, 151, 159) * (width * height))
    painted = bytearray(width * height)
    sun = (-0.62, -0.48, 0.62)
    mag = sqrt(sum(v*v for v in sun))
    sun = tuple(v/mag for v in sun)
    for t in world.tiles:
        x, y = t.x, t.y
        left, right = heights[y*w+max(0,x-1)], heights[y*w+min(w-1,x+1)]
        above, below = heights[max(0,y-1)*w+x], heights[min(h-1,y+1)*w+x]
        dx = (right-left)/(2*world.cell_km*1000)
        dy = (below-above)/(2*world.cell_km*1000)
        nx, ny, nz = -dx*14, -dy*14, 1.0
        nmag = sqrt(nx*nx+ny*ny+nz*nz)
        light = (nx*sun[0] + ny*sun[1] + nz*sun[2])/nmag
        shade = max(.62, min(1.26, .79 + .40*light))
        base = BIOME_COLORS[t.biome]
        cx, cy = center(x, y, tile_px)
        for py in range(max(0, ceil(cy-tile_px-.5)),
                        min(height, ceil(cy+tile_px-.5))):
            oy = abs(py+.5-cy)
            half_width = (SQRT3*tile_px*.5 if oy <= tile_px*.5
                          else SQRT3*(tile_px-oy))
            if half_width <= 0:
                continue
            from_x = max(0, ceil(cx-half_width-.5))
            to_x = min(width, ceil(cx+half_width-.5))
            for px in range(from_x, to_x):
                texture = ((px*71+py*113+(px*py*17))%23-11)*.18
                # A gentle intra-cell gradient keeps relief visible while the
                # biome boundaries themselves remain crisp hexagon edges.
                facet = 1 + max(-.035, min(.035,
                    -(px+.5-cx)*dx*.006 - (py+.5-cy)*dy*.006))
                pixel = py*width+px
                painted[pixel] = 1
                pos = pixel*3
                for k in range(3):
                    output[pos+k] = max(0,min(255,round(base[k]*shade*facet+texture)))
    # Straight map frames can include tiny triangular slivers beyond the
    # outermost hexes. Extend the nearest boundary hex rather than leaving
    # conspicuous default-blue triangles over inland northern/southern edges.
    for py in range(height):
        y = max(0,min(h-1,round((py+.5-tile_px)/(1.5*tile_px))))
        row_offset = (y&1)*.5
        for px in range(width):
            pixel = py*width+px
            if painted[pixel]:
                continue
            x = max(0,min(w-1,round((px+.5)/(SQRT3*tile_px)-.5-row_offset)))
            color=BIOME_COLORS[world.tile(x,y).biome]
            off=pixel*3
            output[off:off+3] = bytes(color)
    return _png_rgb(width, height, bytes(output))
def _contour_segments(world, level: int, tile_px: int) -> str:
    """Marching-squares isolines with linear interpolation on height samples."""
    w, h = world.width, world.height
    out = []
    for y in range(h - 1):
        for x in range(w - 1):
            vals = (world.tile(x, y).elevation_m,
                    world.tile(x + 1, y).elevation_m,
                    world.tile(x + 1, y + 1).elevation_m,
                    world.tile(x, y + 1).elevation_m)
            corners = (center(x,y,tile_px), center(x+1,y,tile_px),
                       center(x+1,y+1,tile_px), center(x,y+1,tile_px))
            hits = []
            for a in range(4):
                b = (a + 1) % 4
                if (vals[a] < level) != (vals[b] < level):
                    frac = (level - vals[a]) / (vals[b] - vals[a])
                    ix = corners[a][0] + (corners[b][0] - corners[a][0]) * frac
                    iy = corners[a][1] + (corners[b][1] - corners[a][1]) * frac
                    hits.append((a, ix, iy))
            if len(hits) == 2:
                (_, ax, ay), (_, bx, by) = hits
                out.append(f'M{ax:.1f},{ay:.1f}L{bx:.1f},{by:.1f}')
            elif len(hits) == 4:
                # Keep ambiguous saddles deterministic and locally consistent.
                pairings = ((0, 1), (2, 3)) if sum(vals) / 4 < level else ((0, 3), (1, 2))
                for a, b in pairings:
                    _, ax, ay = hits[a]
                    _, bx, by = hits[b]
                    out.append(f'M{ax:.1f},{ay:.1f}L{bx:.1f},{by:.1f}')
    return ''.join(out)


def _edge_path(world, scale: int, *, coastal: bool) -> str:
    """Unique hex edges, or strictly the edges between land and ocean."""
    segments = []
    for t in world.tiles:
        polygon = vertices(t.x,t.y,scale)
        for e in range(6):
            point = edge_neighbor(t.x,t.y,e)
            in_bounds = 0 <= point[0] < world.width and 0 <= point[1] < world.height
            if coastal:
                if t.elevation_m <= 0 or not in_bounds:
                    continue
                if world.tile(*point).elevation_m > 0:
                    continue
            elif in_bounds and point < (t.x,t.y):
                continue  # don't double-draw edges shared by hexes
            x1,y1 = polygon[e]
            x2,y2 = polygon[(e+1)%6]
            segments.append(f'M{x1:.2f},{y1:.2f}L{x2:.2f},{y2:.2f}')
    return ''.join(segments)


def _coast_and_contours(world, scale: int) -> list[str]:
    parts = ['<g id="elevation-contours" fill="none" stroke-linecap="round">']
    for level in range(300, 3100, 300):
        path = _contour_segments(world, level, scale)
        if path:
            major = level % 600 == 0
            parts.append(f'<path d="{path}" stroke="#504c3f" '
                         f'stroke-width="{1.0 if major else .65}" '
                         f'opacity="{.29 if major else .17}"/>')
    parts.append('</g>')
    coast = _edge_path(world,scale,coastal=True)
    parts.append('<g id="coastline" fill="none" stroke-linejoin="round" '
                 'stroke-linecap="round">')
    # A broad, land-green coastal fringe and a precise darker shoreline line.
    parts.append(f'<path d="{coast}" stroke="#587758" stroke-width="5.3" opacity=".78"/>')
    parts.append(f'<path d="{coast}" stroke="#345e59" stroke-width="1.9" opacity=".94"/>')
    parts.append('</g>')
    return parts


def _hex_grid(world, scale: int) -> list[str]:
    edges = _edge_path(world,scale,coastal=False)
    return ['<g id="hex-grid" fill="none" stroke="#e7dfcc" stroke-width=".65" '
            'stroke-dasharray="2.3 3.7" opacity=".70">',
            f'<path d="{edges}"/>', '</g>']
def _river_paths(world, scale: int) -> list[str]:
    """Draw the directed drainage graph as joined, width-scaled stream segments."""
    parts = ['<g id="river-network" fill="none" stroke-linecap="round" stroke-linejoin="round">']
    widths = (1.3, 2.0, 2.9, 3.9, 5.0)
    buckets: list[list[str]] = [[] for _ in widths]
    for tile in world.tiles:
        if not tile.river or tile.drains_to is None:
            continue
        nx, ny = tile.drains_to
        x1, y1 = (tile.x + .5) * scale, (tile.y + .5) * scale
        x2, y2 = (nx + .5) * scale, (ny + .5) * scale
        # Every river edge is taken from the priority-flood drainage model.
        weight = min(len(widths) - 1, int(log1p(tile.flow / 72) / 1.15))
        buckets[weight].append(f'M{x1:.1f},{y1:.1f}L{x2:.1f},{y2:.1f}')
    for weight, paths in enumerate(buckets):
        if not paths:
            continue
        d = ''.join(paths)
        wid = widths[weight]
        parts.append(f'<path d="{d}" stroke="#345c66" stroke-width="{wid + 1.2:.1f}" opacity=".70"/>')
        parts.append(f'<path d="{d}" stroke="#a6d7dc" stroke-width="{wid:.1f}"/>')
    parts.append('</g>')
    return parts


def _mountain_symbols(world, scale: int) -> list[str]:
    """Show highland ridge texture and multiple snowy crests, not a white band."""
    parts = ['<g id="mountain-relief-hachures" stroke="#534f48" stroke-linecap="round" fill="none">']
    # Engraved slope ticks follow the actual downhill direction, with an
    # irregular but deterministic density. Concentrated above 1,050 m.
    for tile in world.tiles:
        if tile.elevation_m < 1050 or (tile.x * 13 + tile.y * 7 + world.seed) % 4:
            continue
        x, y = tile.x, tile.y
        if not (0 < x < world.width-1 and 0 < y < world.height-1):
            continue
        gx = world.tile(x+1,y).elevation_m - world.tile(x-1,y).elevation_m
        gy = world.tile(x,y+1).elevation_m - world.tile(x,y-1).elevation_m
        steep = hypot(gx,gy)
        if steep < 95:
            continue
        cx,cy=(x+.5)*scale,(y+.5)*scale
        length=min(8,3.2+steep/175)
        dx,dy=gx/steep*length, gy/steep*length
        parts.append(f'<path d="M{cx-dx*.5:.1f},{cy-dy*.5:.1f}L{cx+dx*.5:.1f},{cy+dy*.5:.1f}" '
                     f'stroke-width="{.8 if tile.elevation_m < 1900 else 1.15}" opacity=".40"/>')
    parts.append('</g>')
    # Cartographic peak symbols give the reader an immediate mountain cue.
    # Spread them through the highland zone, with higher summits first.
    candidates = [t for t in world.tiles if t.elevation_m > 1550 and
                  ((t.x * 5 + t.y * 11 + world.seed) % 7) <= 2]
    chosen = []
    for t in sorted(candidates, key=lambda t: (-t.elevation_m, t.y, t.x)):
        if all(hypot(t.x - old.x, t.y - old.y) >= 3.0 for old in chosen):
            chosen.append(t)
        if len(chosen) >= 78:
            break
    parts.append('<g id="summit-markers" stroke="#504e49" stroke-linejoin="round" fill="none" opacity=".9">')
    for t in chosen:
        x, y = (t.x + .5) * scale, (t.y + .5) * scale
        r = 9.1 if t.elevation_m > 2050 else 7
        parts.append(f'<path d="M{x-r:.1f},{y+r*.49:.1f}L{x:.1f},{y-r:.1f}L{x+r:.1f},{y+r*.49:.1f}Z" '
                     'fill="#cbc6b5" fill-opacity=".85" stroke-width="1.35"/>')
        parts.append(f'<path d="M{x:.1f},{y-r:.1f}L{x+r:.1f},{y+r*.49:.1f}L{x:.1f},{y+r*.25:.1f}Z" '
                     'fill="#77756f" fill-opacity=".65" stroke="none"/>')
        if t.elevation_m > 1900:
            parts.append(f'<path d="M{x-r*.46:.1f},{y-r*.30:.1f}L{x:.1f},{y-r:.1f}'
                         f'L{x+r*.41:.1f},{y-r*.32:.1f}L{x+r*.18:.1f},{y-r*.45:.1f}'
                         f'L{x:.1f},{y-r*.18:.1f}L{x-r*.2:.1f},{y-r*.44:.1f}Z" '
                         'fill="#f5efe1" stroke="none"/>')
        parts.append(f'<title>{t.elevation_m:,} m highland</title>')
    parts.append('</g>')
    return parts


def _forest_symbols(world, scale: int) -> list[str]:
    parts = ['<g id="forest-symbols" fill="none" stroke="#385642" stroke-width="1.15" opacity=".47">']
    for tile in world.tiles:
        if tile.biome not in ('forest', 'taiga', 'rainforest'):
            continue
        if ((tile.x * 7 + tile.y * 11 + world.seed * 3) % 19) != 0:
            continue
        x, y = (tile.x + .5) * scale, (tile.y + .5) * scale
        parts.append(f'<path d="M{x:.1f},{y-5:.1f}l-3,5h2l-3,3h6l-3,-3h2z M{x:.1f},{y+3:.1f}v3"/>')
    parts.append('</g>')
    return parts


def _road_paths(world, scale: int) -> list[str]:
    parts = ['<g id="road-network" fill="none" stroke-linejoin="round" stroke-linecap="round">']
    # Bury roads slightly under the river crossings; bridges are drawn last.
    for surface in ('dirt', 'cobblestone'):
        roads = [r for r in world.roads if r.surface == surface]
        for road in roads:
            pts = ' '.join(f'{(x+.5)*scale:.1f},{(y+.5)*scale:.1f}' for x, y in road.path)
            if surface == 'dirt':
                parts.append(f'<polyline class="dirt-road" points="{pts}" stroke="#6e503a" stroke-width="4.0"/>')
                parts.append(f'<polyline points="{pts}" stroke="#d5b079" stroke-width="2.7"/>')
                parts.append(f'<polyline points="{pts}" stroke="#f0d4a0" stroke-width=".75" '
                             'stroke-dasharray="2 5"/>')
            else:
                parts.append(f'<polyline class="cobbled-road" points="{pts}" stroke="#55544e" stroke-width="5.0"/>')
                parts.append(f'<polyline points="{pts}" stroke="#ece1c8" stroke-width="3.3"/>')
                parts.append(f'<polyline points="{pts}" stroke="#898375" stroke-width="1.25" '
                             'stroke-dasharray="1 3"/>')
            # A short bridge deck across the water where a road enters a river.
            for (px, py), (x, y) in zip(road.path, road.path[1:]):
                if not world.tile(x, y).river or world.tile(px, py).river:
                    continue
                cx, cy = (x + .5) * scale, (y + .5) * scale
                vx, vy = x - px, y - py
                length = hypot(vx, vy)
                nx, ny = -vy / length, vx / length
                dx, dy = vx / length, vy / length
                parts.append(f'<path class="road-bridge" d="M{cx-4*dx-4*nx:.1f},{cy-4*dy-4*ny:.1f}'
                             f'L{cx+4*dx-4*nx:.1f},{cy+4*dy-4*ny:.1f}'
                             f'M{cx-4*dx+4*nx:.1f},{cy-4*dy+4*ny:.1f}'
                             f'L{cx+4*dx+4*nx:.1f},{cy+4*dy+4*ny:.1f}" '
                             'stroke="#403d36" stroke-width="1.25"/>')
    parts.append('</g>')
    return parts


def _places(world, scale: int) -> list[str]:
    parts = ['<g id="exploration-sites">']
    for site in world.sites:
        x, y = (site.x + .5) * scale, (site.y + .5) * scale
        parts.append(f'<path d="M{x:.1f},{y-4.2:.1f}L{x+4.2:.1f},{y:.1f}'
                     f'L{x:.1f},{y+4.2:.1f}L{x-4.2:.1f},{y:.1f}Z" '
                     'fill="#633c55" stroke="#f5e6cf" stroke-width="1.2">'
                     f'<title>{escape(site.name)} — {escape(site.kind.replace("_", " "))} '
                     f'(danger {site.danger})</title></path>')
    parts.append('</g><g id="settlements" font-family="Georgia,serif">')
    # Place labels in the least-crowded immediate quadrant, avoiding boundary.
    occupied = []
    for settlement in sorted(world.settlements, key=lambda s: s.id != 'crownreach'):
        x, y = (settlement.x + .5) * scale, (settlement.y + .5) * scale
        cap = settlement.id == 'crownreach'
        r = 6.7 if cap else 4.6
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r+2:.1f}" fill="#34352c" opacity=".48"/>')
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" '
                     f'fill="{"#f3ca6a" if cap else "#f5e0aa"}" stroke="#342e24" stroke-width="1.5">'
                     f'<title>{escape(settlement.name)} ({settlement.livelihood}, population {settlement.population})</title></circle>')
        if cap:
            parts.append(f'<path d="M{x-4:.1f},{y-2:.1f}l2,3 2,-4 2,4 2,-3v6h-8z" fill="#59432e"/>')
        font = 15 if cap else 12.7
        label_width = len(settlement.name) * font * .59
        placements = [(10,-8,'start'), (-10,-8,'end'), (10,18,'start'),(-10,18,'end')]
        def cost(p):
            dx,dy,align=p
            a = x+dx if align=='start' else x+dx-label_width
            b = a+label_width
            top=y+dy-font
            overlap=sum(max(0,min(b,rx)-max(a,lx))*max(0,min(top+font,by)-max(top,ty))
                        for lx,ty,rx,by in occupied)
            outside=max(0, 4-a)+max(0, b-(world.width*scale-4))
            outside+=max(0, 4-top)+max(0, top+font-(world.height*scale-4))
            return overlap*5+outside*40
        dx,dy,align=min(placements,key=cost)
        left=x+dx if align=='start' else x+dx-label_width
        top=y+dy-font
        occupied.append((left,top,left+label_width,top+font))
        common = (f'x="{x+dx:.1f}" y="{y+dy:.1f}" text-anchor="{align}" '
                  f'font-size="{font}" font-weight="{"bold" if cap else "normal"}"')
        # Separate outline and fill: unlike paint-order, this also renders
        # correctly in common PNG rasterizers used for review thumbnails.
        parts.append(f'<text {common} fill="none" stroke="#f5ecd6" '
                     f'stroke-width="4" stroke-linejoin="round">{escape(settlement.name)}</text>')
        parts.append(f'<text {common} fill="#28251f">{escape(settlement.name)}</text>')
    parts.append('</g>')
    return parts


def render_svg(world) -> str:
    """Render a geographically faithful map; does not mutate world or saved data."""
    s = TILE_PX
    map_w, map_h = world.width * s, world.height * s
    width, height = map_w + 2 * MARGIN, map_h + TOP + BOTTOM
    seed_text = f'{world.seed}'
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-labelledby="title desc">',
        '<title id="title">Oathmere — shaded relief survey atlas</title>',
        '<desc id="desc">Procedurally generated shaded mountains, labeled contours, connected drainage, '
        'cobblestone trade roads, dirt roads, river bridges, settlements and exploration sites.</desc>',
        '<rect width="100%" height="100%" fill="#e9dec3"/>',
        f'<path d="M{MARGIN},68H{width-MARGIN}" stroke="#977c52" stroke-width="1"/>',
        '<text x="29" y="36" font-family="Georgia,serif" font-size="26" '
        'font-weight="bold" fill="#433a2d" letter-spacing="1.9">OATHMERE</text>',
        '<text x="31" y="56" font-family="Georgia,serif" font-size="13" '
        'font-style="italic" fill="#71624a">The Royal Survey · Geographical Atlas</text>',
        f'<text x="{width-30}" y="38" text-anchor="end" font-family="Georgia,serif" '
        'font-size="13" fill="#584d3d">'
        f'SEED {escape(seed_text)}  ·  {world.width * world.cell_km:g} × '
        f'{world.height * world.cell_km:g} KM</text>',
        f'<text x="{width-30}" y="55" text-anchor="end" font-family="Georgia,serif" '
        'font-size="10" fill="#85775b" letter-spacing=".7">'
        f'RELIEF · DRAINAGE · ROADWAYS · FRONTIER</text>',
        f'<defs><clipPath id="map-frame"><rect x="{MARGIN}" y="{TOP}" '
        f'width="{map_w}" height="{map_h}"/></clipPath></defs>',
        f'<g clip-path="url(#map-frame)"><g transform="translate({MARGIN},{TOP})">',
        f'<image id="shaded-relief" x="0" y="0" width="{map_w}" height="{map_h}" '
        f'href="data:image/png;base64,{_terrain_raster(world,s)}"/>',
    ]
    parts.extend(_coast_and_contours(world, s))
    parts.extend(_forest_symbols(world, s))
    parts.extend(_mountain_symbols(world, s))
    parts.extend(_river_paths(world, s))
    parts.extend(_road_paths(world, s))
    parts.extend(_places(world, s))
    # Scale bar sits inside map, but above map detail.
    bar = min(150, max(55, 30 / world.cell_km * s))
    parts.extend([
        f'<g transform="translate(20,{map_h-29})">',
        f'<rect x="-10" y="-16" width="{bar+59:.1f}" height="44" rx="4" '
        'fill="#efe4cc" fill-opacity=".86" stroke="#998865" stroke-width=".75"/>',
        f'<path d="M0,8h{bar/2:.1f}v8H0z" fill="#4b483f"/>'
        f'<path d="M{bar/2:.1f},8h{bar/2:.1f}v8h-{bar/2:.1f}z" fill="#e6d8bd" stroke="#4b483f" stroke-width="1"/>',
        f'<text x="0" y="3" font-size="10" fill="#3d382e">0</text>',
        f'<text x="{bar:.1f}" y="3" text-anchor="end" font-size="10" fill="#3d382e">30 km</text>',
        '</g>',
        f'<g transform="translate({map_w-39},43)" fill="none" stroke="#f6ead0" stroke-width="3">',
        '<path d="M0,-24L-11,13 0,7 11,13Z"/>',
        '<path d="M0,-24L-11,13 0,7 11,13Z" fill="#3c493e" stroke="#443d32" stroke-width="1.3"/>',
        '<path d="M0,-21L0,7 11,13Z" fill="#f4e6c7" stroke="none"/>',
        '<text x="0" y="-31" font-size="14" fill="#fff7de" stroke="#4b4435" '
        'stroke-width="2.2" paint-order="stroke" text-anchor="middle">N</text>',
        '</g>',
        '</g></g>',
        f'<rect x="{MARGIN}" y="{TOP}" width="{map_w}" height="{map_h}" fill="none" '
        'stroke="#78664a" stroke-width="2"/>',
        f'<path d="M{MARGIN},{height-53}H{width-MARGIN}" stroke="#9b855f" stroke-width=".9"/>',
    ])
    legend = [
        ('#8e8b80', 'High relief'), ('#f3f0e6', 'Snow & ice'),
        ('#9ecbd5', 'Rivers'), ('#ece1c8', 'Cobbled road'),
        ('#d5b079', 'Dirt road'), ('#f3ca6a', 'Settlement'),
        ('#633c55', 'Ruins / dungeons'),
    ]
    spacing = (width - 2 * MARGIN) / len(legend)
    for i, (color, title) in enumerate(legend):
        lx = MARGIN + i * spacing + 7
        ly = height - 29
        if 'road' in title:
            parts.append(f'<path d="M{lx},{ly-4}h23" stroke="{color}" stroke-width="4" '
                         f'stroke-linecap="round"/>')
            parts.append(f'<path d="M{lx},{ly-4}h23" stroke="#665a4c" stroke-width=".9" '
                         'stroke-dasharray="1 3"/>')
        elif 'Rivers' in title:
            parts.append(f'<path d="M{lx},{ly-4}q7,-6 13,0t13,0" fill="none" '
                         f'stroke="{color}" stroke-width="3"/>')
        else:
            parts.append(f'<circle cx="{lx+7}" cy="{ly-4}" r="5" fill="{color}" '
                         'stroke="#544d43" stroke-width=".6"/>')
        parts.append(f'<text x="{lx+31}" y="{ly}" font-size="11.3" '
                     f'font-family="Georgia,serif" fill="#4a4032">{escape(title)}</text>')
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'
