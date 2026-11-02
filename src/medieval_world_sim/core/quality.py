"""Worker skill, company facilities, and product-quality formulas.

Kept separate from command implementation to allow new industries to reuse it.
"""
from dataclasses import dataclass


ALLOWED_PERKS = frozenset({"training", "meal", "medical"})


@dataclass(frozen=True)
class CompanyQuality:
    effectiveness: int
    stars: int
    suggested_daily_sales: int


def worker_effectiveness(worker, industry: str) -> float:
    w = worker.work
    # Skill matters more after multiple shifts in this particular industry.
    special = w.experience.get(industry, 0)
    return 0.45 * w.manual + 0.35 * w.intelligence + 0.20 * w.endurance + 0.35 * min(100, special)


def suggested_wage(worker, industry: str) -> int:
    return max(2, int(2 + worker_effectiveness(worker, industry) / 12))


def company_quality(world, company) -> CompanyQuality:
    staff = [world.actors[aid] for aid in sorted(company.employees) if aid in world.actors]
    team = sum(worker_effectiveness(a, company.industry) for a in staff) / len(staff) if staff else 0
    score = min(100, round(12 + 11 * company.facility_level
                          + 0.7 * team + min(20, company.shifts_completed // 3)))
    return CompanyQuality(score, max(1, min(5, (score + 19) // 20)),
                          max(1, (score + 19) // 20))
