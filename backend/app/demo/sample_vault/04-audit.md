title: The tamper-evident audit trail
classification: PUBLIC
evidence_class: primary_source
description: Platform documentation — audit chain, verification and export (from docs/CONTROL_PLANE.md)
---
# The tamper-evident audit trail

Every consequential operation writes an audit record. Records are sealed into a keyed hash chain when the transaction
commits, and database triggers refuse updates and deletions. Verification recomputes the chain and names the first
record that was changed, deleted or forged.

Auditors can export the trail as a signed ZIP, JSON or CSV with filters. Retention can remove only the oldest verified
records, never records younger than the minimum retention age, and only with a second person's approval for that exact
cut-off; an anchor keeps the remaining chain verifiable.

A normal database table is not immutable: someone holding both the database and the audit key could rebuild the chain.
That is why signed exports should be stored outside the system.
