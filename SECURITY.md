# Security policy

**Scope.** This repository is a public demonstration of governance semantics (a shim). It contains no licensed runtime,
no secret, no private key and no customer data. Reports about the licensed QEC runtime are handled under the evaluation
licence, not here.

**Reporting.** E-mail contact@quantumexcellium.com. Please include the
commit hash, a minimal reproduction and, if relevant, the ledger lines. We acknowledge within 5 working days.
Coordinated disclosure: 90 days, shorter by agreement. No bounty programme at this time.

**What counts as a finding here.** A way to make `qec_shim.py` execute a tool call that policy, budget or delegation
should have refused; a way to make `ledger_verify.py` report VALID on a rewritten ledger; a way to make
`tools/evidence_pack.py --check` accept a modified evidence file.

**What does not.** Prompt injection in `demo.py` inputs — that is what the demo exercises on purpose; the shim's lack of
identity, trusted time or encryption — documented limits (see README, "Limits").
