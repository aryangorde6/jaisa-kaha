"""make rule-log: Switch's own log says who set an agent's rule, and an admin's change
after Mom's is caught. The lines below have the shape Switch 0.31.0 logs (UTC)."""

import unittest

from jaisa import rulelog

P = "[process_id=x tenant_id=default]"
REG = f"2026-11-06T13:00:00 INFO  [switch_core.bridges.agent.protocol.agent_core] {P} Registered agent: pothi (abc-1)"
MOM = f"2026-11-06T13:02:00 INFO  [switch_core.gateway.agents] {P} Updated addressing policy for agent pothi (1 rules) by user Mom"
ADMIN = f"2026-11-06T20:00:00 INFO  [switch_core.gateway.agents] {P} Updated addressing policy for agent pothi (2 rules) by user Admin"
EARLY = f"2026-11-06T13:01:00 INFO  [switch_core.gateway.agents] {P} Updated addressing policy for agent pothi (1 rules) by user Aryan"
TAPE = f"2026-11-05T13:56:47 INFO  [switch_core.gateway.agents] {P} Updated addressing policy for agent tape (1 rules) by user Aryan"
NOISE = f"2026-11-06T13:03:00 INFO  [uvicorn.error] {P} connection open"


def run(argv, *lines):
    said = []
    code = rulelog.run(argv, "\n".join(lines) + "\n", out=said.append)
    return code, "\n".join(said)


class RuleLog(unittest.TestCase):
    def test_only_mom_set_the_rule(self):
        code, said = run(["pothi", "--by", "Mom"], REG, NOISE, MOM, TAPE)
        self.assertEqual(code, 0)
        self.assertIn("Fri 06 Nov 18:32:00  pothi    rule set (1 rule)", said)  # UTC 13:02 is IST 18:32
        self.assertIn("changes by anyone else since then: 0.", said)
        self.assertNotIn("tape", said)

    def test_an_admin_change_after_mom_is_caught(self):
        code, said = run(["Pothi", "--by", "Mom"], REG, MOM, ADMIN)
        self.assertEqual(code, 1)
        self.assertIn("rule set (2 rules)     by user Admin", said)
        self.assertIn("changes by anyone else since then: 1.", said)

    def test_a_change_before_mom_is_shown_but_not_counted_against_her(self):
        code, said = run(["pothi", "--by", "Mom"], REG, EARLY, MOM)
        self.assertEqual(code, 0)
        self.assertIn("by user Aryan", said)
        self.assertIn("(before that, set 1 time(s) by someone else)", said)

    def test_mom_never_set_it(self):
        self.assertEqual(run(["pothi", "--by", "Mom"], REG, EARLY)[0], 1)
        self.assertEqual(run(["pothi", "--by", "Mom"], NOISE)[0], 1)

    def test_everything_and_the_start_time(self):
        code, said = run(["--started", "2026-11-05T12:49:26.967905366Z"], TAPE, REG, MOM)
        self.assertEqual(code, 0)
        self.assertIn("since the container started Thu 05 Nov 18:19:26 IST", said)
        self.assertEqual(said.count("\n  "), 3)

    def test_bad_arguments(self):
        self.assertEqual(run(["--by", "Mom"], MOM)[0], 2)
        self.assertEqual(run(["pothi", "--by"], MOM)[0], 2)
        self.assertEqual(run(["pothi", "tape"], MOM)[0], 2)


if __name__ == "__main__":
    unittest.main()
