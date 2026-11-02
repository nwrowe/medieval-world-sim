"""Command line entry point for deterministic scenario runs."""

import argparse
import json

from .simulation import World


def main() -> None:
    parser = argparse.ArgumentParser(description="Medieval RPG economic simulation experiment")
    parser.add_argument("--citizens", type=int, default=200)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", action="store_true", help="Output every daily snapshot as JSON")
    args = parser.parse_args()
    if args.days < 0:
        parser.error("--days must be >= 0")

    world = World.create(count=args.citizens, seed=args.seed)
    history = [world.summary()]
    for _ in range(args.days):
        history.append(world.step())

    if args.json:
        print(json.dumps({"configuration": {"citizens": args.citizens, "days": args.days, "seed": args.seed}, "history": history}, indent=2))
    else:
        print("Day   Treasury    Median gold   Gini    Hunger today   Trades   Food stock")
        for s in history:
            if s["day"] == 0 or s["day"] % max(1, args.days // 10) == 0 or s["day"] == args.days:
                print(f'{s["day"]:>3} {s["treasury"]:>10} {s["median_gold"]:>14} {s["gini_gold"]:>6.3f} {s["hungry_citizens_today"]:>14} {s["trades_cumulative"]:>8} {s["stocks"]["food"]:>12}')
        print("\nNote: Fixed-price toy economy, not an AI-agent or production game system.")


if __name__ == "__main__":
    main()
