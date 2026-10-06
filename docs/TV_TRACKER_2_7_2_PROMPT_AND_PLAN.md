# Tv Tracker reliability work: prompt and implementation decision

## Execution prompt

Act as the maintainer of Tv Tracker. Diagnose the Google Sheets HTTP 429 read-quota failure reported on 2.7.1 and the misleading credential warning that accompanies it. Inspect the current repository and request paths before editing. Preserve saved captures, encrypted connections, completion/SLA evidence rules, monthly reports, import review, and verified update integrity.

For the existing four-PC deployment, reduce redundant reads, batch compatible reads, budget all Sheets requests by service account within each installation, and implement bounded quota recovery with Retry-After and jitter. Do not blindly replay writes with an unknown outcome. Preserve the workbook publishing lock, fresh ownership checks and commit receipts. Persist deferred capture retries across restarts, retain ordering, and safely resume the specific quota failures created by 2.7.1. Keep permanent validation/permission failures manual.

Keep the interface responsive while Sheets refreshes or waits. Show dated cached data, explicit refresh/retry status and accurate error categories. A user pressing Refresh must not bypass quota cooldown. Keep compatibility for API consumers expecting a full synchronous response; make background refresh opt-in.

Validate transport budgets for four clients, retries, interrupted operations, duplicate recovery, backup/restore, UI states, responsive layouts and the packaged application. Publish only after source checks, build, regression tests, artifact integrity, actual 2.7.1 installer upgrade and recovery checks pass. Explain what was measured and what remains unverified; do not claim all physical client PCs were tested remotely.

For the longer-term shared backend, use authenticated PostgreSQL (Supabase preferred), a local SQLite cache/outbox and a single central Sheets publisher. Require an account-owned project and end-to-end migration validation before enabling it. Do not replace the live data source with an unconfigured dependency or describe an inactive integration as deployed.

## Review of the prompt

- Names the observed failure and the affected release.
- Specifies the four-PC operating envelope and compatibility requirements.
- Preserves irreversible data and ownership safeguards.
- Distinguishes safe quota retries from uncertain write outcomes.
- Defines meaningful acceptance checks and release gates.
- Separates the deployable Sheets repair from a cloud migration requiring project access.
- Requires an honest report of remaining limits.

## Decision

Ship the quota repair as 2.7.2 on the existing stack. The four computers must all upgrade: old clients do not honor the new request budget. Each installation budgets 12 reads and 12 writes per rolling 61 seconds per service account, leaving aggregate headroom under the default 60-per-minute quotas for four installations. Other programs using the same account can still cause quota responses; bounded cooldown and retained captures handle those cases.

Metadata is reused briefly within a connection and invalidated on mutation and after claiming a publishing job. Values and job ownership tokens are never cached by the transport. Header-only batch reads replace full-table formatting scans; month snapshots use batched formula reads. Reports normally refresh at most once every two minutes per installation; an explicit refresh can request earlier data, while quota cooldown remains mandatory.

PostgreSQL remains the target architecture for larger concurrent deployments. Enabling it requires a user-owned project, authentication/roles, central write API, durable outbox, conflict review, central publishing, migration reconciliation and real four-PC acceptance. No cloud migration is activated by this patch.
