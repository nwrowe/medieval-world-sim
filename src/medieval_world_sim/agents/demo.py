"""Run a reproducible, bounded autonomous NPC world.

python -m medieval_world_sim.agents.demo --npcs 50 --days 30 --seed 42
"""
import argparse
import json
from pathlib import Path
from .critics import OpenAIChatCritic
from .runner import create_simulation


def main() -> None:
    parser = argparse.ArgumentParser(description="Five-city autonomous NPC economy")
    parser.add_argument("--npcs", type=int, default=30)
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--step-minutes", type=int, default=360,
                        help="NPC decision interval; must divide 1440")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--playtest", action="store_true",
                        help="Add isolated Explorer and Optimizer test characters")
    parser.add_argument("--reflect-every", type=int, default=30,
                        help="Meaningful decisions between reflections (default: 30)")
    parser.add_argument("--llm-model", default=None,
                        help="Explicitly enable a model critic; requires OPENAI_API_KEY")
    parser.add_argument("--report-file", default=None,
                        help="Write bounded structured JSON findings to this path")
    args = parser.parse_args()
    if args.llm_model and not args.playtest:
        parser.error("--llm-model requires --playtest")
    if args.report_file and not args.playtest:
        parser.error("--report-file requires --playtest")
    critic = OpenAIChatCritic(args.llm_model) if args.llm_model else None
    simulation = create_simulation(args.npcs, args.seed,
                                   playtesters=args.playtest,
                                   reflection_every=args.reflect_every,
                                   critic=critic)
    report = simulation.run(args.days, step_minutes=args.step_minutes)
    if args.report_file:
        destination = Path(args.report_file).expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report["playtesting"], indent=2,
                                          sort_keys=True), encoding="utf-8")
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
        if args.playtest:
            summary = report["playtesting"]["aggregate"]
            print("Playtest reflections: " + str(summary["report_counts"]))
            print("Shared issue signals: " + str(summary["common_issue_codes"]))
            if args.report_file:
                print("Structured feedback saved to " + str(args.report_file))


if __name__ == "__main__":
    main()
