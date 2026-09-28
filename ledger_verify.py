#!/usr/bin/env python3
"""Verbatim logic of the public verifier github.com/Quantum-Architecture/ledger-verify (fetched 2026-09-25); imports split for lint."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

GENESIS = "0" * 64

def canonical_payload(record: dict) -> bytes:
    payload = {k: record[k] for k in sorted(record) if k != "hash"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

def digest(record: dict) -> str:
    return hashlib.sha256(canonical_payload(record)).hexdigest()

def verify(path: Path):
    errors, prev = [], GENESIS
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {idx}: invalid JSON: {exc}")
                continue
            if rec.get("prev_hash") != prev:
                errors.append(f"line {idx}: prev_hash mismatch")
            expected = digest(rec)
            if rec.get("hash") != expected:
                errors.append(f"line {idx}: hash mismatch")
            prev = rec.get("hash", "")
    return (not errors, errors)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ledger", type=Path)
    args = ap.parse_args()
    ok, errors = verify(args.ledger)
    if ok:
        print("VALID")
        raise SystemExit(0)
    print("INVALID")
    for e in errors:
        print(f"- {e}")
    raise SystemExit(1)

if __name__ == "__main__":
    main()
