"""Generate a reproducible atlas for inspection without changing existing saves."""
import argparse
import json
from pathlib import Path

from . import generate_world
from .render import render_svg
from .inspect import render_inspector_html
from .history_view import render_history_html
from .history_text import render_chronicle
from .content import export_content_template, load_content


def main():
    parser = argparse.ArgumentParser(description="Generate a seed-based Oathmere world atlas")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--cities", type=int, default=12)
    parser.add_argument("--sites", type=int, default=45)
    parser.add_argument("--cell-km", type=float, default=3.0)
    parser.add_argument("--output", type=Path, default=Path("world-atlas"))
    parser.add_argument("--content", type=Path,
                        help="Optional editable world-content JSON (names, sites, events)")
    args = parser.parse_args()
    authored = load_content(args.content) if args.content else None
    world = generate_world(args.seed, args.width, args.height, args.cities,
                           args.sites, args.cell_km, content=authored)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "world.json").write_text(json.dumps(world.to_dict(), indent=2), encoding="utf-8")
    template = authored if authored is not None else export_content_template(world)
    (args.output / "world-content.template.json").write_text(
        json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8")
    svg = render_svg(world)
    (args.output / "atlas.svg").write_text(svg, encoding="utf-8")
    (args.output / "atlas.html").write_text(render_inspector_html(world, svg), encoding="utf-8")
    (args.output / "history.html").write_text(render_history_html(world, svg),
                                               encoding="utf-8")
    (args.output / "chronicle.md").write_text(render_chronicle(world),
                                              encoding="utf-8")
    print(f"World seed {args.seed}: {len(world.settlements)} settlements, "
          f"{len(world.roads)} roads, {len(world.sites)} exploration sites")
    print(f"Water survey: {sum(t.waterbody == 'lake' for t in world.tiles)} lake hexes, "
          f"{len(world.waterways)} navigable networks, "
          f"{len(world.landmarks)} strategic landmarks")
    print(f"History: {len(world.history.eras)} eras, {len(world.history.ruins)} "
          "historical ruins and abandoned hamlets")
    print(f"Saved {args.output / 'world.json'}, {args.output / 'atlas.svg'}, "
          f"{args.output / 'atlas.html'}, {args.output / 'history.html'}, "
          f"{args.output / 'chronicle.md'} and the editable world-content template")


if __name__ == "__main__":
    main()
