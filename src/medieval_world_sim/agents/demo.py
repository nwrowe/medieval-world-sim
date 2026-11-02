"""Run a reproducible, bounded autonomous NPC world.

python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42
"""
import argparse
import json
from .runner import create_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Five-city autonomous NPC economy")
    parser.add_argument("--npcs", type=int, default=30)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--step-minutes", type=int, default=360,
                        help="NPC decision interval; must divide 1440")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    simulation = create_simulation(args.npcs, args.seed)
    report = simulation.run(args.days, step_minutes=args.step_minutes)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"Five-city NPC economy | seed={args.seed}, NPCs={args.npcs}, days={args.days}")
        print(f"Gold conserved: {report['gold_conserved']} ({report['gold_total']})")
        print(f"Trades: {report['market_trades']}, volume: {report['market_gold_volume']} gold")
        print(f"Gathered: {report['resources_gathered']}, shifts: {report['shifts_completed']}, "
              f"crafted gear: {report['crafted_equipment']}")
        print(f"Decisions: {report['actions']}")
        if report["rejections"]:
            print(f"Rejected proposals (engine enforcement): {report['rejections']}")


if __name__ == "__main__":
    main()
