"""Adversarial tests: every test proves a refusal or a detection, never a promise."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import qec_shim as shim  # noqa: E402


class TestScenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.td = tempfile.mkdtemp()
        p = subprocess.run([sys.executable, os.path.join(os.path.dirname(__file__), "demo.py"), "--json", "--out", cls.td],
                           capture_output=True, text=True, check=True)
        cls.r = json.loads(p.stdout)

    def test_ungoverned_agent_is_exploited(self):
        u = self.r["ungoverned"]
        self.assertEqual(u["paid_to_attacker"], "48000.00")
        self.assertEqual(u["paid_to_unapproved"], "2500.00")
        self.assertEqual(len(u["emails_to_external"]), 1)

    def test_governed_agent_loses_nothing(self):
        g = self.r["governed"]
        self.assertEqual(g["paid_to_attacker"], "0")
        self.assertEqual(g["paid_to_unapproved"], "0")
        self.assertEqual(g["over_budget"], "0")
        self.assertEqual(g["emails_to_external"], [])
        codes = {c for _, _, c in g["refusals"]}
        self.assertEqual(codes, {"amount_over_ceiling", "external_recipient", "vendor_not_approved", "budget_exhausted",
                                 "tool_not_delegated", "authority_escalation"})

    def test_ledger_verifies_and_tampering_is_detected(self):
        self.assertTrue(self.r["ledger_valid"])
        self.assertTrue(self.r["tampered_detected"])
        self.assertEqual(self.r["ledger_verify_output"], "VALID")

    def test_every_execution_is_preceded_by_a_journaled_allow(self):
        with open(self.r["governed"]["ledger"], encoding="utf-8") as f:
            lines = [json.loads(x) for x in f if x.strip()]
        allowed = {rec["hash"] for rec in lines if rec["kind"] == "tool_allowed"}
        for rec in lines:
            if rec["kind"] == "tool_executed":
                self.assertIn(rec["payload"]["decision_hash"], allowed)


class TestShimContract(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.ledger = shim.Ledger(os.path.join(self.td, "l.jsonl"))
        h = "c" * 64
        self.policy = shim.Policy(self.ledger, {"V"}, h, shim.approve(h))
        self.agent = shim.Agent("a", shim.Authority(frozenset({"schedule_payment"}), Decimal("100"), Decimal("150")), self.ledger, self.policy)

    def test_float_money_is_refused(self):
        with self.assertRaises(shim.Refused):
            self.agent.call("schedule_payment", {"vendor": "V", "amount": 10.5, "iban": "x"}, lambda t, a: {})

    def test_budget_is_exact_decimal_not_float(self):
        ex = lambda t, a: {}  # noqa: E731
        for _ in range(10):
            self.agent.call("schedule_payment", {"vendor": "V", "amount": "10.01", "iban": "x"}, ex)
        self.assertEqual(self.agent.spent, Decimal("100.10"))
        with self.assertRaises(shim.Refused) as c:
            self.agent.call("schedule_payment", {"vendor": "V", "amount": "49.91", "iban": "x"}, ex)
        self.assertEqual(c.exception.code, "budget_exhausted")

    def test_config_drift_is_fail_closed(self):
        self.policy.config_approval = "forged"
        with self.assertRaises(shim.Refused) as c:
            self.agent.call("schedule_payment", {"vendor": "V", "amount": "1", "iban": "x"}, lambda t, a: {})
        self.assertEqual(c.exception.code, "config_drift")

    def test_child_cannot_exceed_parent(self):
        with self.assertRaises(shim.Refused):
            self.agent.delegate("kid", shim.Authority(frozenset({"schedule_payment", "send_email"}), Decimal("1"), Decimal("1")))
        with self.assertRaises(shim.Refused):
            self.agent.delegate("kid", shim.Authority(frozenset({"schedule_payment"}), Decimal("101"), Decimal("1")))
        kid = self.agent.delegate("kid", shim.Authority(frozenset({"schedule_payment"}), Decimal("50"), Decimal("50")))
        with self.assertRaises(shim.Refused):
            kid.delegate("grandkid", shim.Authority(frozenset({"schedule_payment"}), Decimal("60"), Decimal("50")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
