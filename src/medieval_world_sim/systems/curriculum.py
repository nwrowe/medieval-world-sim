"""Nine medieval schools, eight sequential courses each, completed by simulated time."""
from dataclasses import dataclass
from ..errors import ActionError

DAYS = (4, 6, 8, 10, 13, 17, 22, 30)
SCHOOLS = {
    "grammar": ("Grammar", "Trivium", "intelligence", (
        "Letters and Script", "Parts of Speech", "Reading Manuscripts",
        "Syntax and Form", "Classical Commentary", "Poetic Composition",
        "Scholarly Translation", "Master of Grammar")),
    "rhetoric": ("Rhetoric", "Trivium", "intelligence", (
        "The Spoken Word", "Memorable Arguments", "Letters of Persuasion",
        "Public Oratory", "Petitions and Appeals", "Debate and Rebuttal",
        "Courtly Diplomacy", "Master of Rhetoric")),
    "logic": ("Logic", "Trivium", "intelligence", (
        "Claims and Evidence", "Syllogisms", "Deductive Forms", "Fallacies",
        "Scholastic Questions", "Proof and Refutation",
        "Disputation", "Master of Logic")),
    "arithmetic": ("Arithmetic", "Quadrivium", "intelligence", (
        "Counting and Numerals", "The Abacus", "Weights and Measures",
        "Proportions", "Interest and Exchange", "Merchant Accounts",
        "Advanced Calculation", "Master of Arithmetic")),
    "geometry": ("Geometry", "Quadrivium", "manual", (
        "Lines and Angles", "Surveying Fields", "Shapes and Solids",
        "Masons' Measures", "Architectural Plans", "Water and Land",
        "Fortification Design", "Master of Geometry")),
    "astronomy": ("Astronomy", "Quadrivium", "intelligence", (
        "The Night Sky", "The Calendar", "Moon and Tide",
        "Celestial Movements", "The Astrolabe", "Navigation by Stars",
        "Eclipses and Orbits", "Master of Astronomy")),
    "music": ("Music", "Quadrivium", "intelligence", (
        "Rhythm and Measure", "Chant", "The Monochord", "Intervals",
        "Notation", "Harmony", "Composition", "Master of Music")),
    "latin": ("Latin", "Language and Records", "intelligence", (
        "Latin Letters", "Common Phrases", "Nouns and Cases",
        "Verb Forms", "Scripture and Prayer", "Legal Latin",
        "Scholarly Texts", "Master of Latin")),
    "commerce": ("Commerce & Recordkeeping", "Practical Arts", "manual", (
        "Writing Ledgers", "Counting Stock", "Contracts and Receipts",
        "Weights for Trade", "Bookkeeping", "Merchant Correspondence",
        "Household Management", "Master of Commerce")),
}
# The fifth course in each school is an introduction to applied scholarship.
# These are small cumulative skill improvements; no consumable resource is minted.
STAT_BONUS = (1, 1, 1, 2, 2, 2, 3, 4)

@dataclass
class CourseEnrollment:
    school: str
    index: int
    ends_at: int

class CurriculumSystem:
    def __init__(self, world):
        self.world = world

    def start(self, actor_id: str, school: str) -> dict:
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if school not in SCHOOLS:
            raise ActionError("Unknown school")
        if actor_id in self.world.state.active_courses:
            raise ActionError("Finish your current course first")
        count = self.world.state.completed_courses.get(actor_id, {}).get(school, 0)
        if count >= len(DAYS):
            raise ActionError("School already completed")
        ends_at = self.world.minute + DAYS[count] * 1440
        self.world.state.active_courses[actor_id] = CourseEnrollment(school, count, ends_at)
        self.world._emit("course_started", actor_id, school, count, ends_at)
        return {"school": school, "index": count, "ends_at": ends_at}

    def settle(self, now: int) -> None:
        for actor_id, enrollment in list(self.world.state.active_courses.items()):
            if now < enrollment.ends_at:
                continue
            actor = self.world.actors[actor_id]
            school = enrollment.school
            if self.world.state.completed_courses.get(actor_id, {}).get(school, 0) != enrollment.index:
                raise AssertionError("Out-of-order curriculum completion")
            self.world.state.completed_courses.setdefault(actor_id, {})[school] = enrollment.index + 1
            stat = SCHOOLS[school][2]
            bonus = STAT_BONUS[enrollment.index]
            setattr(actor.work, stat, getattr(actor.work, stat) + bonus)
            self.world._emit("course_completed", actor_id, school, enrollment.index, stat, bonus)
            del self.world.state.active_courses[actor_id]
            if enrollment.index == 7:
                self.world._emit("school_graduated", actor_id, school)

    def view(self, actor_id: str) -> dict:
        counts = self.world.state.completed_courses.get(actor_id, {})
        active = self.world.state.active_courses.get(actor_id)
        schools = []
        for key, (name, tradition, stat, titles) in SCHOOLS.items():
            count = counts.get(key, 0)
            schools.append({
                "id": key, "name": name, "tradition": tradition,
                "stat": stat, "complete": count == 8,
                "completed": count, "total": 8,
                "courses": [{"name": title, "days": DAYS[i], "stat_bonus": STAT_BONUS[i],
                             "completed": i < count, "active": bool(active and active.school == key and active.index == i),
                             "available": i == count and not active}
                            for i, title in enumerate(titles)],
            })
        return {"schools": schools, "active": None if not active else {
            "school": active.school, "index": active.index,
            "remaining_minutes": max(0, active.ends_at - self.world.minute),
            "ends_at": active.ends_at}}
