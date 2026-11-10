"""Dependency-free review atlas. The SVG is generated data, not gameplay authority."""
from __future__ import annotations

from html import escape

BIOME_COLORS = {
    "ocean": "#7396a2", "alpine": "#e1e4df", "mountain": "#8e8a80",
    "tundra": "#bbc2b3", "wetland": "#668d78", "desert": "#d4bb80",
    "steppe": "#b9b487", "hills": "#a39d79", "taiga": "#567c68",
    "rainforest": "#47745a", "forest": "#74936b", "grassland": "#a5b88a",
}


def render_svg(world) -> str:
    tile_size = 10
    width, height = world.width * tile_size, world.height * tile_size
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
             'role="img" aria-labelledby="title desc">',
             '<title id="title">Generated Oathmere atlas</title>',
             '<desc id="desc">Geography-first world: biomes, rivers, roads, settled towns and wilderness sites.</desc>']
    for tile in world.tiles:
        parts.append(f'<rect x="{tile.x * tile_size}" y="{tile.y * tile_size}" '
                     f'width="{tile_size}" height="{tile_size}" fill="{BIOME_COLORS[tile.biome]}"/>')
    for tile in world.tiles:
        if tile.river:
            x, y = (tile.x + .5) * tile_size, (tile.y + .5) * tile_size
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.0" fill="#94c8d6"/>')
    for road in world.roads:
        coords = " ".join(f"{(x + .5) * tile_size:.1f},{(y + .5) * tile_size:.1f}" for x, y in road.path)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="#ddcb93" '
                     'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>')
    for site in world.sites:
        x, y = (site.x + .5) * tile_size, (site.y + .5) * tile_size
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.7" fill="#7c3650" '
                     'stroke="#f7e4ce" stroke-width=".8">'
                     f'<title>{escape(site.name)} (danger {site.danger})</title></circle>')
    for settlement in world.settlements:
        x, y = (settlement.x + .5) * tile_size, (settlement.y + .5) * tile_size
        capital = settlement.id == 'crownreach'
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{5 if capital else 3.7}" '
                     'fill="#f5e4a4" stroke="#3f3024" stroke-width="1.2"/>'
                     f'<text x="{x + 6:.1f}" y="{y - 6:.1f}" font-size="11" '
                     'font-family="Georgia,serif" fill="#221d16" stroke="#eee4c7" '
                     'stroke-width="2.5" paint-order="stroke">'
                     f'{escape(settlement.name)}</text>')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"
