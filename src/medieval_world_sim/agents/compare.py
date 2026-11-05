"""Deterministic multi-seed autonomous NPC playtesting comparison.

No model/network calls. Keep heavy 30-day experiments opt-in rather than in
the commit-time CI pipeline; reduced multi-seed regressions are in unit tests.
"""
import argparse
import json
from pathlib import Path
from statistics import mean, median

from .runner import create_simulation


METRICS = ("cash_change", "gold_per_day", "goal_action_pct",
           "trade_completed", "trade_net_profit", "trade_profit_per_day",
           "trade_loss_cycles", "unsettled_positions",
           "combat_attacks", "combat_victories", "combat_loot",
           "combat_xp", "work_xp", "magic_xp",
           "equipment_owned", "cities_discovered")


def compare(*, first_seed: int = 42, seeds: int = 10,
            days: int = 30, npcs: int = 28,
            step_minutes: int = 360) -> dict:
    if type(seeds) is not int or not 1 <= seeds <= 20:
        raise ValueError("Choose 1–20 seeds")
    if type(days) is not int or not 1 <= days <= 60:
        raise ValueError("Choose 1–60 simulated days")
    if type(first_seed) is not int:
        raise ValueError("Seed must be an integer")
    records = []
    for seed in range(first_seed, first_seed + seeds):
        sim = create_simulation(npcs, seed=seed, playtesters=True)
        report = sim.run(days, step_minutes=step_minutes)
        agents = report["playtesting"]["agents"]
        records.append({
            "seed": seed, "gold_conserved": report["gold_conserved"],
            "rejections": report["rejections"],
            "agents": {persona: {
                **agents["playtest_" + persona]["outcomes"],
                "issue_codes": sorted({issue["code"]
                    for reflection in agents["playtest_" + persona]["reports"]
                    for issue in reflection["issues"]}),
            } for persona in ("explorer", "optimizer")},
        })
    summary = {}
    for persona in ("explorer", "optimizer"):
        summary[persona] = {}
        for key in METRICS:
            values = [row["agents"][persona][key] for row in records]
            summary[persona][key] = {
                "min": min(values), "median": median(values),
                "mean": round(mean(values), 3), "max": max(values),
            }
        summary[persona]["runs_with_loss_cycles"] = sum(
            row["agents"][persona]["trade_loss_cycles"] > 0
            for row in records)
        summary[persona]["issue_frequencies"] = {
            code: sum(code in row["agents"][persona]["issue_codes"]
                      for row in records)
            for code in sorted({code for row in records
                                for code in row["agents"][persona]["issue_codes"]})
        }
    return {
        "configuration": {"first_seed": first_seed, "seeds": seeds,
                          "days": days, "npcs": npcs,
                          "step_minutes": step_minutes},
        "gold_conserved_all": all(row["gold_conserved"] for row in records),
        "rejections_all": {str(row["seed"]): row["rejections"]
                           for row in records if row["rejections"]},
        "summary": summary, "runs": records,
        "limitations": ("Local telemetry reflects rules-based agent behavior, "
                        "not human player sentiment or public-server performance."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare Explorer and Optimizer across bounded seeded worlds")
    parser.add_argument("--first-seed", type=int, default=42)
    parser.add_argument("--seeds", type=int, default=10)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--npcs", type=int, default=28)
    parser.add_argument("--step-minutes", type=int, default=360)
    parser.add_argument("--report-file", type=Path)
    args = parser.parse_args()
    result = compare(first_seed=args.first_seed, seeds=args.seeds,
                     days=args.days, npcs=args.npcs,
                     step_minutes=args.step_minutes)
    output = json.dumps(result, indent=2, sort_keys=True)
    if args.report_file:
        destination = args.report_file.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding="utf-8")
        print("Wrote " + str(destination))
    else:
        print(output)


if __name__ == "__main__":
    main()
