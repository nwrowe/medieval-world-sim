"""Career-slot capacity, qualifications, expiring offers and private letters."""
import unittest

from medieval_world_sim.content.staffing import positions, capacity, openings, OFFER_MINUTES
from medieval_world_sim.core.engine import WorldEngine
from medieval_world_sim.core.entities import Actor
from medieval_world_sim.errors import ActionError
from medieval_world_sim.web.economy_projection import economy_projection, incoming_job_offers


class CareerTests(unittest.TestCase):
    def world(self, industry="forge"):
        world = WorldEngine([
            Actor("owner", "human", gold=500),
            Actor("alice", "human", gold=100),
            Actor("bob", "human", gold=100),
            Actor("cara", "human", gold=100),
            Actor("dana", "human", gold=100),
        ])
        world.found_company("owner", "craft_house", industry, 100)
        return world, world.companies["craft_house"]

    def test_growth_tracks_paid_company_shifts_and_differs_by_industry(self):
        w, company = self.world("forge")
        self.assertEqual(capacity(company), 3)
        self.assertEqual(len(positions(company)), 3)
        company.shifts_completed = 12
        self.assertEqual(capacity(company), 6)
        company.shifts_completed = 36
        self.assertEqual(capacity(company), 10)
        company.shifts_completed = 168
        self.assertEqual(capacity(company), 18)
        self.assertEqual(positions(company)[-1]["requirements"]["manual"], 24)
        bakery, shop = self.world("bakery")
        shop.shifts_completed = 168
        self.assertEqual(capacity(shop), 15)
        w.assert_invariants()
        bakery.assert_invariants()

    def test_applicants_are_individual_and_cannot_skip_qualification(self):
        w, company = self.world()
        with self.assertRaises(ActionError):
            w.company_apply_role("alice", company.id, "0")
        w.company_set_hiring("owner", company.id, True)
        with self.assertRaises(ActionError):
            w.company_apply_role("alice", company.id, "99")
        w.company_apply_role("alice", company.id, "0")
        company = w.companies[company.id]  # Rollback of invalid action replaced world state.
        self.assertIn("alice", company.applicants)
        self.assertEqual(company.applicant_positions["alice"], "0")
        w.company_accept_applicant("owner", company.id, "alice", 4, "0")
        self.assertNotIn("alice", company.applicants)
        self.assertEqual(company.offer_positions["alice"], "0")
        w.accept_job("alice", company.id)
        self.assertEqual(company.employee_positions["alice"], "0")
        self.assertEqual(company.employees["alice"].gold, 4)
        with self.assertRaises(ActionError):
            w.company_accept_applicant("owner", company.id, "bob", 4, "1")
        company = w.companies[company.id]
        company.shifts_completed = 168
        with self.assertRaises(ActionError):
            w.offer_job_position("owner", company.id, "bob", 3, "17")
        w.assert_invariants()

    def test_positions_reserved_and_decline_frees_slot(self):
        w, company = self.world()
        for who, position in (("alice", "0"), ("bob", "1"), ("cara", "2")):
            w.offer_job_position("owner", company.id, who, 3, position)
        self.assertEqual(len(openings(company, w.minute)), 0)
        with self.assertRaises(ActionError):
            w.offer_job_position("owner", company.id, "dana", 3, "1")
        company = w.companies[company.id]
        w.decline_job("bob", company.id)
        self.assertNotIn("bob", company.job_offers)
        w.offer_job_position("owner", company.id, "dana", 3, "1")
        w.assert_invariants()

    def test_48_hour_expiry_and_private_letter(self):
        w, company = self.world()
        names = {x: x.title() for x in w.actors}
        w.offer_job_position("owner", company.id, "alice", 8, "0")
        letters = incoming_job_offers(w, "alice", names)
        self.assertEqual(len(letters), 1)
        self.assertEqual(letters[0]["position_id"], "0")
        self.assertEqual(letters[0]["wage"]["gold"], 8)
        self.assertEqual(letters[0]["expires_in_minutes"], OFFER_MINUTES)
        self.assertEqual(incoming_job_offers(w, "bob", names), [])
        self.assertEqual(len(economy_projection(w, "alice", names)["job_offers"]), 1)
        w.state.minute += OFFER_MINUTES
        self.assertEqual(incoming_job_offers(w, "alice", names), [])
        with self.assertRaises(ActionError):
            w.accept_job("alice", company.id)
        self.assertEqual(len(openings(company, w.minute)), 3)
        w.offer_job_position("owner", company.id, "alice", 5, "0")
        self.assertEqual(len(incoming_job_offers(w, "alice", names)), 1)
        w.assert_invariants()


if __name__ == "__main__":
    unittest.main()
