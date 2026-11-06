title: How consequential actions are approved
classification: PUBLIC
evidence_class: primary_source
description: Platform documentation — approval levels and the approval lifecycle (from docs/SECURITY.md and docs/CONTROL_PLANE.md)
---
# How consequential actions are approved

Every action an agent can take has a permission level. Level 0 is research, level 1 analysis and recommendations,
level 2 drafting, level 3 reversible internal operations. Level 4 covers external publishing — publishing a listing or
content, live price changes, customer messages, supplier inquiries and product launches. Level 5 covers financial and
contractual actions — ad budgets, purchase orders, supplier agreements and paid experiments.

Level 4 and level 5 actions need a human approval for each action. The policy decision point in the backend decides
the approval category: autonomous, supervised, approval required, restricted (four eyes) or prohibited.

An approval is bound to the exact action and to a hash of its arguments. It expires after a configured time, can be
used only once, can be revoked, and can be delegated to another approver. Nobody may approve their own request or a
request made on their behalf. Silence is never approval: a pending request never becomes approved by waiting.

Agents cannot approve anything, cannot grant themselves permissions and cannot change policies, budgets or the audit
trail. These checks run in the backend, so an instruction written into a prompt or a document cannot override them.
