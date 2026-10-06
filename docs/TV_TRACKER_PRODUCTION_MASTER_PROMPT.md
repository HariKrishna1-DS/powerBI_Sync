# Tv Tracker: reporting expansion and production hardening

## Objective and precedence

Act as the engineer responsible for a dependable Windows desktop product. Extend Tv Tracker 2.6.0 using `updates_traker.pdf` as the highest-priority functional specification, followed by the owner's ten production-readiness improvements. Preserve working capture, matching, manual fields, monthly ownership, exports, encrypted connections and update compatibility. Follow direct user clarifications over examples in the PDF. Read and inspect before editing. Do not claim production readiness without evidence.

## PDF requirements

1. Daily Orders: Date, Received, Completed, Clarification, Cancelled, Vendor Pending, In-House Pending, On time SLA, Missed SLA. Normalize case/spacing. Assign to ABS maps to Vendor Pending; Need to assign ABS remains in-house until assigned. Status buckets must be mutually exclusive. Clarify whether daily rows describe received-date cohorts or independent daily events; do not reproduce contradictory sample totals.
2. Capacity Report: the same operational buckets plus Capacity and Ext capacity; daily detail, monthly totals, year-to-date totals, and a received/completed/target chart. Targets are editable, validated and distinct from actual counts. Do not invent historical targets or working-day calendars.
3. Import multiple .xlsx workbooks/sheets in one operation. Validate schemas, dates, identities, duplicate/conflicting orders and file limits before activation. Show an import summary and actionable errors. Imported data must not be mistaken for a complete portal queue or infer completion through absence.
4. Add explicit Tracker report and Import Excel report sources. All production dashboards, daily/monthly/capacity reports, exports and published reporting views must use the chosen source consistently. Preserve original tracker data and imports so switching is reversible. Failed publishing must be visible and safely retryable.
5. Full_search_<MON>_<YEAR> and Remaining_<MON>_<YEAR> use the Full Search production schema including custom columns. Keep current names compatible; accept the PDF's Remaining_Search spelling as an alias if needed.
6. Present only useful reporting tabs: All Products, the monthly full/remaining views, Daily Orders, Capacity Report, Monthly Orders, Status Report. Internal canonical data/receipts required by the app must remain recoverable. Prepare a concrete migration/cleanup preview before destructive live deletion; hiding internal tabs is the reversible initial implementation.
7. Selecting a daily date must provide the corresponding Google Sheets report location without destroying other dates or changing another user's view. Use a verified sheet ID/range link and preserve all daily rows.

## Ten hardening requirements

1. Validate capture completeness and attach completion provenance. Separate confirmed delivery from inferred disappearance; do not present uncertain SLA evidence as exact. Retain cancelled/suspended exceptions and equality-at-deadline On Time behavior.
2. Enforce designated-writer operation for a shared workbook; read-only installations must not sync or schedule writes. Explain the limits of client-side checks and protect against stale writes with existing fingerprints/receipts.
3. Make backup creation and restore limits consistent; validate manifest integrity/counts and restore compatibility. Investigate the previous visible/disk capture-count discrepancy without replacing production data.
4. Redact secrets consistently, protect credentials, exclude sensitive files from bundles and improve local-data protection. Key rotation and Google permissions require actual account access; report them as owner/external actions until verified, never pretend they occurred.
5. Define a consistent release policy compatible with the owner's no-purchase requirement. Retain artifact integrity, validation and explicit installation controls. Test failure recovery and do not publish an unverified release.
6. Bound generated backup/history growth using transparent retention and recoverable archiving. Never silently delete raw business history.
7. Test normal/failure/duplicate/stale/offline/interrupted paths, schedules and cross-client conflicts. Distinguish deterministic simulation from actual multi-day and live-service evidence.
8. Measure the entire process tree, response sizes and representative search/report latency with repeatable fixtures; enforce realistic regression budgets rather than claiming an unmeasured speedup.
9. Use a cohesive theme and accessible responsive controls. Test keyboard/focus/dialog behavior, light/dark contrast, supported widths and scaling. Avoid clipped or cramped sidebar/report controls.
10. Put new responsibilities in focused modules, consolidate shared reporting rules, add enforceable quality/security checks and document migration-specific constants. Avoid a speculative rewrite or unnecessary services/dependencies.

## Execution and acceptance

- Record a requirement-to-code-to-test matrix and unresolved assumptions before implementation.
- Implement in reviewable stages: shared reporting rules; import/source persistence; cloud views; UI; recovery/security/retention; quality gates; release verification.
- Reuse the current Electron/React/Python/SQLite/Sheets architecture. No Redis or PostgreSQL without demonstrated need.
- Use fixture workbooks and disposable profiles for tests. Preserve the installed profile and production workbook while validating migrations.
- Require arithmetic reconciliation, duplicate safety, deterministic source switching, consistent exports, formula preservation and meaningful network/authentication errors.
- Run existing regressions plus tests that prove new behavior. Inspect actual rendered UI. Document measured results and limitations.
- Release only after applicable acceptance checks pass. Report any remaining identity/account permissions, sustained real-world checks or publication blocks accurately.
- Deliver the implemented result, tested behavior, changed files, configuration/migration instructions, and a concise completed/pending matrix. Never describe partial checks as proof of a bug-free product.

## Validation of this prompt

The PDF has been read as text and all four pages inspected visually. Sample capacity values and conflicting daily totals are explicitly treated as requirements to clarify. The prompt covers every PDF feature and all ten hardening items, separates UI preferences from shared data mutations, preserves recoverability, and defines evidence-based completion. It does not authorize unsafe deletion, fabricate identity verification, or claim live testing from mocks.
