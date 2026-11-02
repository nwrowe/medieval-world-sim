"""Choose the live five-city prototype, combat demo or archived economy baseline."""
import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Medieval World Sim experiment runner")
    parser.add_argument("--scenario", choices=("regional", "combat"), default="regional")
    parser.add_argument("--legacy", action="store_true", help="Run the original one-town benchmark")
    parser.add_argument("--citizens", type=int, default=200)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--json", action="store_true", help="Structured output for the legacy benchmark")
    args = parser.parse_args()

    if not args.legacy:
        if args.scenario == "combat":
            from .combat_demo import main as scenario
        else:
            from .regional_demo import main as scenario
        scenario()
        return

    from .experiments.legacy_economy import World
    if args.days < 0:
        parser.error("--days must be >= 0")
    world = World.create(count=args.citizens, seed=args.seed)
    history = [world.summary()]
    for _ in range(args.days):
        history.append(world.step())
    if args.json:
        print(json.dumps({
            "configuration": {"citizens": args.citizens, "days": args.days, "seed": args.seed},
            "history": history
        }, indent=2))
    else:
        for entry in history:
            print(entry)


if __name__ == "__main__":
    main()
