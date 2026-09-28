"""qec_shim.py — PUBLIC DEMONSTRATION SHIM (not the QEC product).

This file re-implements, in ~150 lines, the *observable contract* of four QEC mechanisms so that the
demo scenario runs anywhere with zero dependencies:

  1. policy before execution   - every tool call is checked, then journaled, then executed (or refused)
  2. exact-decimal budget       - Decimal only; a cumulative ceiling that cannot be exceeded
  3. delegation non-escalation  - a child agent can never hold more authority than its parent
  4. hash-chained ledger        - every decision is a record verifiable by the public verifier
                                  (github.com/Quantum-Architecture/ledger-verify): same format.

What it is NOT: the QEC Local Core (signed delegations, proof-of-possession, ledger-attested state,
drift sentinel, replay capsules, cost meter, vendor packs). When the Local Core is installed the demo
uses it instead (see qec_adapter.py). Numbers here are demo numbers, not benchmarks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

GENESIS = "0" * 64


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class Ledger:
    """Append-only, hash-chained, ledger-verify compatible (fields prev_hash + hash)."""

    def __init__(self, path: str):
        self.path, self.prev, self.seq = path, GENESIS, 0
        with open(path, "w", encoding="utf-8"):
            pass

    def append(self, kind: str, payload: dict) -> dict:
        rec = {"seq": self.seq + 1, "ts_utc": _now(), "kind": kind, "payload": payload, "prev_hash": self.prev}
        rec["hash"] = hashlib.sha256(canonical(rec)).hexdigest()
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.prev, self.seq = rec["hash"], rec["seq"]
        return rec


class Refused(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class Authority:
    """What an agent may do. Child ⊆ parent is enforced at delegation time."""
    tools: frozenset
    max_amount: Decimal            # per-call ceiling for money-moving tools
    budget: Decimal                # cumulative ceiling over the session

    def contains(self, other: "Authority") -> bool:
        return other.tools <= self.tools and other.max_amount <= self.max_amount and other.budget <= self.budget


@dataclass
class Agent:
    name: str
    authority: Authority
    ledger: Ledger
    policy: "Policy"
    parent: str | None = None
    spent: Decimal = field(default_factory=lambda: Decimal("0"))

    def delegate(self, child_name: str, authority: Authority) -> "Agent":
        if not self.authority.contains(authority):
            self.ledger.append("delegation_refused", {"parent": self.name, "child": child_name, "code": "authority_escalation"})
            raise Refused("authority_escalation", f"{child_name} asks more than {self.name} holds")
        self.ledger.append("delegation", {"parent": self.name, "child": child_name, "tools": sorted(authority.tools),
                                          "max_amount": str(authority.max_amount), "budget": str(authority.budget)})
        return Agent(child_name, authority, self.ledger, self.policy, parent=self.name)

    def call(self, tool: str, args: dict, executor) -> dict:
        """policy → journal → execute. Nothing executes before it is journaled as allowed."""
        amount = Decimal(str(args.get("amount", "0")))
        if not isinstance(args.get("amount", "0"), (str, int)) and "amount" in args:
            raise Refused("float_forbidden", "money must be str/int, never float")
        try:
            if tool not in self.authority.tools:
                raise Refused("tool_not_delegated", tool)
            self.policy.check(self, tool, args)
            if amount > self.authority.max_amount:
                raise Refused("amount_over_ceiling", f"{amount} > {self.authority.max_amount}")
            if self.spent + amount > self.authority.budget:
                raise Refused("budget_exhausted", f"{self.spent} + {amount} > {self.authority.budget}")
        except Refused as r:
            self.ledger.append("tool_refused", {"agent": self.name, "tool": tool, "args": _s(args), "code": r.code, "detail": r.detail})
            raise
        rec = self.ledger.append("tool_allowed", {"agent": self.name, "tool": tool, "args": _s(args)})
        result = executor(tool, args)
        self.spent += amount
        self.ledger.append("tool_executed", {"agent": self.name, "tool": tool, "decision_hash": rec["hash"], "result": _s(result)})
        return result


def _s(x):
    if isinstance(x, Decimal):
        return str(x)
    if isinstance(x, dict):
        return {k: _s(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_s(v) for v in x]
    return x


class Policy:
    """Declarative allow/deny evaluated BEFORE execution. Rules are plain data, journaled once at start."""

    def __init__(self, ledger: Ledger, approved_vendors: set[str], config_hash: str, config_approval: str | None):
        self.approved_vendors = set(approved_vendors)
        self.config_hash, self.config_approval = config_hash, config_approval
        ledger.append("policy_loaded", {"approved_vendors": sorted(self.approved_vendors), "config_hash": config_hash,
                                        "config_approval": config_approval})

    def check(self, agent: Agent, tool: str, args: dict) -> None:
        # drift: a configuration whose hash is not covered by an approval is refused fail-closed
        if self.config_approval != hashlib.sha256(("approve:" + self.config_hash).encode()).hexdigest():
            raise Refused("config_drift", "policy configuration changed without signed approval")
        if tool == "schedule_payment" and args.get("vendor") not in self.approved_vendors:
            raise Refused("vendor_not_approved", str(args.get("vendor")))
        if tool == "send_email" and not str(args.get("to", "")).endswith("@example-corp.test"):
            raise Refused("external_recipient", str(args.get("to")))


def approve(config_hash: str) -> str:
    """Stand-in for a signed operator approval (the product uses Ed25519 signatures)."""
    return hashlib.sha256(("approve:" + config_hash).encode()).hexdigest()
