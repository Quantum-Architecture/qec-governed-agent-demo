"""qec_adapter.py — one interface, two backends.

  BACKEND = "localcore"  when the licensed QEC Local Core is importable (evaluation or production licence)
  BACKEND = "shim"       otherwise: the public demonstration shim in qec_shim.py (same observable contract)

The demo scenario, tests and CI never change. What changes is what enforces the rules.
"""
from __future__ import annotations

import hashlib
import json
from decimal import Decimal

try:  # pragma: no cover - exercised only where the Local Core is installed
    from localcore.assurance.trust_plane import TrustPlane  # noqa: F401
    BACKEND = "localcore"
except Exception:  # noqa: BLE001
    BACKEND = "shim"

import qec_shim as shim

Refused = shim.Refused


class _ShimAgent:
    def __init__(self, agent: shim.Agent):
        self._a = agent

    def call(self, tool, args, executor):
        return self._a.call(tool, args, executor)

    def delegate(self, name, tools, max_amount: Decimal, budget: Decimal):
        return _ShimAgent(self._a.delegate(name, shim.Authority(frozenset(tools), max_amount, budget)))


class Governance:
    """Facade used by demo.py. With the Local Core present, replace the body of these three methods by the
    TrustPlane calls (issue_delegation / authorize / AuditChain) — the demo file stays identical."""

    def __init__(self, ledger_path: str, approved_vendors, per_call_max: Decimal, budget: Decimal):
        self.ledger = shim.Ledger(ledger_path)
        config = {"approved_vendors": sorted(approved_vendors), "per_call_max": str(per_call_max), "budget": str(budget)}
        config_hash = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
        self.policy = shim.Policy(self.ledger, approved_vendors, config_hash, shim.approve(config_hash))
        self.per_call_max, self.budget = per_call_max, budget
        if BACKEND == "localcore":
            self.ledger.append("note", {"backend": "localcore detected — wire TrustPlane here for the licensed run"})

    def root_agent(self, name: str, tools) -> _ShimAgent:
        return _ShimAgent(shim.Agent(name, shim.Authority(frozenset(tools), self.per_call_max, self.budget), self.ledger, self.policy))
