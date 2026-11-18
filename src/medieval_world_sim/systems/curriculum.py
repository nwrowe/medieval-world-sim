"""Ten university schools, with eight freely selectable paid courses each."""
from dataclasses import dataclass
from ..errors import ActionError
from ..core.transactions import transfer_gold

DAYS = (4, 6, 8, 10, 13, 17, 22, 30)
SCHOOLS = {
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
    "commerce": ("Commerce", "Practical Arts", "manual", (
        "Writing Ledgers", "Counting Stock", "Contracts and Receipts",
        "Weights for Trade", "Bookkeeping", "Merchant Correspondence",
        "Household Management", "Master of Commerce")),
    "writing": ("Writing & Recordkeeping", "Practical Arts", "intelligence", (
        "Penmanship", "Scripts and Inks", "Letters and Notices", "Legal Records",
        "Land Registers", "Archival Methods", "Royal Chancery", "Master Scribe")),
    "physical": ("Physical Training", "Martial Arts", "endurance", (
        "Stretching and Conditioning", "Footwork and Balance", "Running and Marching",
        "Wrestling", "Load Bearing", "Climbing and Mobility",
        "Endurance Trials", "Master of Conditioning")),
    "weapons": ("Weapons Training", "Martial Arts", "manual", (
        "Combat Stance", "Unarmed Technique", "Dagger Drills", "Sword Foundations",
        "Axe Handling", "Archery Fundamentals", "Defensive Maneuvers",
        "Master of Arms")),
}

CURRENT_SCHOOLS = SCHOOLS
COURSE_FEES = (8, 12, 16, 20, 25, 30, 40, 50)
MARTIAL_CAPSTONES = {"physical": ("max_hp", 5), "weapons": ("strength", 1)}
# The fifth course in each school is an introduction to applied scholarship.
# These are small cumulative skill improvements; no consumable resource is minted.
STAT_BONUS = (1, 1, 1, 2, 2, 2, 3, 4)
CAPSTONE_PERKS = {
    "music": ("endurance", 2),
    "astronomy": ("manual", 2),
    "commerce": ("intelligence", 2),
    "writing": ("manual", 2),
    "physical": ("manual", 2),
    "weapons": ("endurance", 2),
}

@dataclass
class CourseEnrollment:
    school: str
    index: int
    ends_at: int

class CurriculumSystem:
    def __init__(self, world):
        self.world = world

    def choose(self, actor_id: str, school: str, index: int) -> dict:
        """Enroll in any unfinished course; capstone requires seven prior courses."""
        actor = self.world._actor(actor_id)
        self.world._at_city(actor)
        if school not in CURRENT_SCHOOLS:
            raise ActionError("Unknown university school")
        if type(index) is not int or not 0 <= index < len(DAYS):
            raise ActionError("Unknown course")
        if actor_id in self.world.state.active_courses:
            raise ActionError("Finish your current course first")
        done = self.completed_indices(actor_id, school)
        if index in done:
            raise ActionError("Course already completed")
        # Course VIII requires completing the other seven first.
        if (index == len(DAYS) - 1 and
                not set(range(len(DAYS) - 1)).issubset(done)):
            raise ActionError("Complete the other seven courses before Master training")
        price = COURSE_FEES[index]
        if actor.gold < price:
            raise ActionError("Insufficient gold for tuition")
        transfer_gold(self.world, actor, None, price)
        ends_at = self.world.minute + DAYS[index] * 1440
        self.world.state.active_courses[actor_id] = CourseEnrollment(school, index, ends_at)
        self.world._emit("course_started", actor_id, school, index, ends_at)
        self.world._emit("course_tuition_paid", actor_id, school, index, price)
        return {"school": school, "index": index, "ends_at": ends_at, "tuition": price}

    def completed_indices(self, actor_id: str, school: str) -> set[int]:
        return self.world.state.chosen_courses.get(actor_id, {}).get(school, set())

    def settle(self, now: int) -> None:
        for actor_id, enrollment in list(self.world.state.active_courses.items()):
            if now < enrollment.ends_at:
                continue
            actor = self.world.actors[actor_id]
            school = enrollment.school
            if enrollment.index in self.completed_indices(actor_id, school):
                raise AssertionError("Duplicate completed university course")
            self.world.state.chosen_courses.setdefault(actor_id, {}).setdefault(
                school, set()).add(enrollment.index)
            stat = SCHOOLS[school][2]
            bonus = STAT_BONUS[enrollment.index]
            setattr(actor.work, stat, getattr(actor.work, stat) + bonus)
            self.world._emit("course_completed", actor_id, school, enrollment.index, stat, bonus)
            del self.world.state.active_courses[actor_id]
            if len(self.completed_indices(actor_id, school)) == 8:
                perk = CAPSTONE_PERKS.get(school)
                if perk is not None:
                    attribute, amount = perk
                    setattr(actor.work, attribute, getattr(actor.work, attribute) + amount)
                    self.world._emit("school_capstone_perk", actor_id, school, attribute, amount)
                martial = MARTIAL_CAPSTONES.get(school)
                if martial:
                    attribute, amount = martial
                    setattr(actor, attribute, getattr(actor, attribute) + amount)
                    if attribute == "max_hp":
                        actor.hp += amount
                    self.world._emit("school_martial_perk", actor_id, school, attribute, amount)
                self.world._emit("school_graduated", actor_id, school)
                # Graduation grants exactly one merit; automatic, not repeatable.
                self.world.merit_system.claim(actor_id, "school:" + school)

    def view(self, actor_id: str) -> dict:
        active = self.world.state.active_courses.get(actor_id)
        schools = []
        for key, (name, tradition, stat, titles) in CURRENT_SCHOOLS.items():
            completed = self.completed_indices(actor_id, key)
            count = len(completed)
            schools.append({
                "id": key, "name": name, "tradition": tradition,
                "stat": stat, "complete": count == 8,
                "completed": count, "total": 8,
                "capstone_perk": ({"stat": CAPSTONE_PERKS[key][0],
                                  "bonus": CAPSTONE_PERKS[key][1]}
                                 if key in CAPSTONE_PERKS else None),
                "martial_perk": ({"stat": MARTIAL_CAPSTONES[key][0],
                                  "bonus": MARTIAL_CAPSTONES[key][1]}
                                 if key in MARTIAL_CAPSTONES else None),
                "courses": [{"name": title, "days": DAYS[i], "tuition": COURSE_FEES[i],
                             "stat_bonus": STAT_BONUS[i],
                             "completed": i in completed,
                             "active": bool(active and active.school == key and active.index == i),
                             "available": i not in completed and not active and
                               (i != len(DAYS) - 1 or
                                set(range(len(DAYS) - 1)).issubset(completed)),
                             "prerequisites_missing": (
                                 sorted(set(range(len(DAYS) - 1)) - completed)
                                 if i == len(DAYS) - 1 else [])}
                            for i, title in enumerate(titles)],
            })
        return {"schools": schools, "active": None if not active else {
            "school": active.school, "index": active.index,
            "remaining_minutes": max(0, active.ends_at - self.world.minute),
            "ends_at": active.ends_at}}
