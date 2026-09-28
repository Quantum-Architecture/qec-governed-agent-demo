#!/usr/bin/env python3
"""bench_overhead.py — measures what governance costs, on the PUBLIC SHIM, on this machine.

Reports the median and p95 latency of: one allowed decision (policy + budget + journal + execute),
one refused decision (journaled refusal), one delegation check, and the cost of verifying the resulting ledger.
Numbers are for the demonstration shim (pure Python, JSON on disk); they are not a claim about the licensed runtime.

  python bench/bench_overhead.py            # 2 000 decisions
  python bench/bench_overhead.py --n 20000 --json bench/result.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import qec_shim as shim  # noqa: E402


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix="qec_bench_")
    path = os.path.join(tmp, "ledger.jsonl")
    ledger = shim.Ledger(path)
    config_hash = "b" * 64
    policy = shim.Policy(ledger, {"Nordic Paper AB"}, config_hash, shim.approve(config_hash))
    root = shim.Agent("root", shim.Authority(frozenset({"schedule_payment", "send_email"}), Decimal("1000"), Decimal("10000000")), ledger, policy)

    def executor(tool, args):
        return {"ok": True}

    allowed, refused, deleg = [], [], []
    for i in range(a.n):
        t = time.perf_counter()
        root.call("schedule_payment", {"vendor": "Nordic Paper AB", "amount": "1"}, executor)
        allowed.append(time.perf_counter() - t)
        t = time.perf_counter()
        try:
            root.call("schedule_payment", {"vendor": "Unknown Ltd", "amount": "1"}, executor)
        except shim.Refused:
            pass
        refused.append(time.perf_counter() - t)
        t = time.perf_counter()
        try:
            root.delegate("child", shim.Authority(frozenset({"schedule_payment"}), Decimal("2000"), Decimal("1")))
        except shim.Refused:
            pass
        deleg.append(time.perf_counter() - t)
    # verification cost with the public verifier (separate process, as a buyer would run it)
    verifier = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ledger_verify.py")
    t = time.perf_counter()
    p = subprocess.run([sys.executable, verifier, path], capture_output=True, text=True)
    verify_s = time.perf_counter() - t
    with open(path, encoding="utf-8") as f:
        lines = sum(1 for _ in f)
    res = {
        "shim": "public demonstration shim (not the licensed runtime)",
        "python": platform.python_version(), "machine": platform.machine(), "system": platform.system(),
        "decisions": a.n,
        "allowed_decision_us": {"median": round(statistics.median(allowed) * 1e6, 1), "p95": round(pct(allowed, 95) * 1e6, 1)},
        "refused_decision_us": {"median": round(statistics.median(refused) * 1e6, 1), "p95": round(pct(refused, 95) * 1e6, 1)},
        "delegation_check_us": {"median": round(statistics.median(deleg) * 1e6, 1), "p95": round(pct(deleg, 95) * 1e6, 1)},
        "ledger_lines": lines, "ledger_bytes": os.path.getsize(path),
        "verify_seconds": round(verify_s, 3), "verify_result": p.stdout.strip().splitlines()[0] if p.stdout else p.stderr.strip()[:80],
    }
    print(json.dumps(res, indent=2))
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(res, f, indent=2)
    return 0 if res["verify_result"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
