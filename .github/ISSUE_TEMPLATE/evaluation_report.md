---
name: Evaluation report (buyer / integrator)
about: Report the result of running the 30-minute evaluation guide on your side
labels: evaluation
---
**Environment** — OS / Python version / commit hash:

**Steps run** (tick):
- [ ] `python -m unittest -q test_demo`
- [ ] `python demo.py`
- [ ] `python ledger_verify.py out/governed_ledger.jsonl` → VALID
- [ ] tampered copy → INVALID with the faulty line
- [ ] `python tools/evidence_pack.py` then `--check`
- [ ] `python bench/bench_overhead.py`

**Observed output that differs from the guide** (paste raw output):

**Integration surface of interest** (A2A / MCP tool boundary / audit export / other):

**Request** (evaluation licence, technical call, other):
