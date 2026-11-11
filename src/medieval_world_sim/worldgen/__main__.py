"""Generate a reproducible atlas for inspection without changing existing saves."""
import argparse
import json
from pathlib import Path

from . import generate_world
from .render import render_svg


def main():
    parser = argparse.ArgumentParser(description="Generate a seed-based Oathmere world atlas")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--width", type=int, default=80)
    parser.add_argument("--height", type=int, default=64)
    parser.add_argument("--cities", type=int, default=12)
    parser.add_argument("--sites", type=int, default=45)
    parser.add_argument("--cell-km", type=float, default=3.0)
    parser.add_argument("--output", type=Path, default=Path("world-atlas"))
    args = parser.parse_args()
    world = generate_world(args.seed, args.width, args.height, args.cities,
                           args.sites, args.cell_km)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "world.json").write_text(json.dumps(world.to_dict(), indent=2), encoding="utf-8")
    (args.output / "atlas.svg").write_text(render_svg(world), encoding="utf-8")
    print(f"World seed {args.seed}: {len(world.settlements)} settlements, "
          f"{len(world.roads)} roads, {len(world.sites)} exploration sites")
    print(f"Saved {args.output / 'world.json'} and {args.output / 'atlas.svg'}")


if __name__ == "__main__":
    main()
