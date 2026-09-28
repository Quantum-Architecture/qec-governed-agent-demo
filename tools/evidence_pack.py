#!/usr/bin/env python3
"""evidence_pack.py — produces a self-describing evidence file a buyer can archive and re-check.

What it records: SHA-256 of every source file, the test run (command, exit code, output), the demo run, the public
verifier's verdict on the demo ledger and on a deliberately tampered copy, and the environment. The file is itself
hash-chained into a one-line footer so any later edit is detectable with `python tools/evidence_pack.py --check <file>`.

No secret is used or expected. Signing (Ed25519) is done by the licensed runtime, outside this repository.

  python tools/evidence_pack.py                 # writes evidence/evidence_<UTC>.json
  python tools/evidence_pack.py --check evidence/evidence_2026-09-27T00-00-00Z.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SOURCES = ["demo.py", "qec_shim.py", "qec_adapter.py", "ledger_verify.py", "test_demo.py"]


def sha256_file(p: str) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd: list[str], cwd: str = ROOT) -> dict:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    shown = ["python" if x == sys.executable else x for x in cmd]
    def clean(text: str) -> str:
        return text.replace(ROOT + os.sep, "").replace(ROOT, ".")
    return {"command": " ".join(shown), "exit_code": p.returncode, "stdout": clean(p.stdout[-4000:]), "stderr": clean(p.stderr[-2000:])}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def build() -> dict:
    ev = {
        "schema": "qec-public-evidence/1",
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scope": "public demonstration repository — shim semantics, not the licensed runtime",
        "environment": {"python": platform.python_version(), "system": platform.system(), "machine": platform.machine()},
        "sources": {s: sha256_file(os.path.join(ROOT, s)) for s in SOURCES if os.path.exists(os.path.join(ROOT, s))},
    }
    ev["tests"] = run([sys.executable, "-m", "unittest", "-q", "test_demo"])
    ev["demo"] = run([sys.executable, "demo.py"])
    ledger = os.path.join(ROOT, "out", "governed_ledger.jsonl")
    if os.path.exists(ledger):
        ev["ledger_sha256"] = sha256_file(ledger)
        ev["verify_intact"] = run([sys.executable, "ledger_verify.py", os.path.relpath(ledger, ROOT)])
        tampered = os.path.join(ROOT, "out", "evidence_tampered.jsonl")
        with open(ledger, encoding="utf-8") as f:
            lines = f.read().split("\n")
        if len(lines) > 5:
            lines[4] = lines[4].replace('"seq": 5', '"seq": 55', 1) if '"seq": 5' in lines[4] else lines[4][:-1] + " "
        with open(tampered, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        ev["verify_tampered"] = run([sys.executable, "ledger_verify.py", os.path.relpath(tampered, ROOT)])
    ev["summary"] = {
        "tests_passed": ev["tests"]["exit_code"] == 0,
        "demo_ran": ev["demo"]["exit_code"] == 0,
        "intact_ledger_valid": ev.get("verify_intact", {}).get("stdout", "").strip().startswith("VALID"),
        "tampered_ledger_detected": ev.get("verify_tampered", {}).get("stdout", "").strip().startswith("INVALID"),
    }
    ev["evidence_hash"] = hashlib.sha256(canonical({k: v for k, v in ev.items() if k != "evidence_hash"})).hexdigest()
    return ev


def check(path: str) -> int:
    with open(path, encoding="utf-8") as f:
        ev = json.load(f)
    expect = ev.pop("evidence_hash", None)
    got = hashlib.sha256(canonical(ev)).hexdigest()
    ok = expect == got
    print(("VALID" if ok else "INVALID") + f"  evidence_hash={got}")
    for k, v in ev.get("summary", {}).items():
        print(f"  {k}: {v}")
    return 0 if ok and all(ev.get("summary", {}).values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    if a.check:
        return check(a.check)
    ev = build()
    os.makedirs(os.path.join(ROOT, "evidence"), exist_ok=True)
    out = a.out or os.path.join(ROOT, "evidence", "evidence_" + ev["generated_utc"].replace(":", "-") + ".json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(ev, f, indent=2, ensure_ascii=False)
    print(json.dumps(ev["summary"], indent=2))
    print("evidence:", out, "\nevidence_hash:", ev["evidence_hash"])
    return 0 if all(ev["summary"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
