# Consensus Protocols

Supported protocols:

- `raft`: queen-authoritative tie-breaking
- `bft`: quorum fraction based agreement
- `simple_majority`: majority vote

Consensus results can require human approval when risk crosses `require_approval_above_risk`.
