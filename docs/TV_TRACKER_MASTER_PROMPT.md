# Tv Tracker implementation master prompt

## Objective

Act as the responsible product engineer for Tv Tracker. Implement the applicable P0, P1 and P2 improvements in the ranked improvement roadmap and the calm desktop UI concept, preserving the existing production workflows. Deliver a maintainable Windows desktop application with measured reliability, responsive interactions, clear navigation and verifiable release quality. Treat industry quality as explicit engineering requirements and evidence, never as a claim that all bugs have been eliminated.

## Inputs and baseline

- Repository: HariKrishna1-DS/powerBI_Sync; dedicated desktop branch: `tv-tracker`.
- Baseline version: 2.2.1. Read the current source and recent remote history before changing it.
- Product roadmap: `output/pdf/Tv_Tracker_Ranked_Improvement_Roadmap.pdf`.
- Visual concept: the Tv Tracker Orders desktop mockup approved as the design direction in this conversation. Its data is illustrative. Use the design language across all real workflows, including loading, empty, error and offline states.
- Read `PROJECT_ARCHITECTURE.md`, `docs/DESKTOP_GUIDE.md`, `docs/DESKTOP_UPSTREAM_ALIGNMENT.md` and `docs/TV_TRACKER_2_2_1_QC.md`.
- Electron owns the native window, secure settings, lifecycle and update integration. React owns the interface. The Python engine owns processing and Google Sheets integration. SQLite owns durable local captures and receipts. Google Sheets remains the production authority. Preserve the existing application ID and profile location so upgrades retain users' data.

## Execution contract

1. Inspect instructions, Git state, architecture, current tests and affected code. Refresh remote references. Preserve unrelated changes and existing business data.
2. Map every roadmap rank to an existing implementation, an actionable gap, or a conditional future investment. Record evidence and dependencies. Do not report existing functionality as newly implemented.
3. Validate this brief against the repository and resolve routine implementation choices autonomously. Keep a durable implementation ledger with completed, verified, pending and externally blocked items.
4. Implement in reviewable stages. Continue through verification and necessary fixes. Preserve existing capture, import, comparison, reports, SLA editing, exports, schedules, recovery and update workflows.
5. Do not introduce Redis, PostgreSQL/Neon, DuckDB/Polars or a Tauri rewrite without the adoption evidence specified in the roadmap. Evaluate the Playwright extractor behind a compatible interface before switching production automation.
6. Use isolated profiles and fixtures for destructive or failure-injection tests. Use live production access only for relevant, controlled verification, preserving manual fields and avoiding test records in the real Sheet. Keep secrets out of source, logs, screenshots and bundles.
7. Keep working through solvable problems. Report an external prerequisite precisely when it prevents a release gate; do not invent credentials, claim a signature that does not exist, or claim a live test passed during a portal outage.

## Reliability and data requirements

- Use stable identifiers and defined field ownership. Preserve user-maintained Sheet fields and validate normalized numbers, booleans, blanks, timestamps and identifiers correctly.
- Recover preview numbering before the first connected capture. Retry must be idempotent. Reconcile uncertain writes with persisted receipts and readback.
- Persist useful job state and failure evidence. Preserve committed data through process termination, engine restart and failed updates. Provide versioned backups and verify restoration in an isolated profile.
- Distinguish healthy empty queues, expired authentication, missing portal structure, incomplete pagination, timeout and upstream unavailability. Use bounded retry/backoff where safe. Never promote an incomplete capture or overwrite the last successful result because a portal response is empty or uncertain.
- Label cached, stale, pending, failed and confirmed states accurately. Keep useful offline browsing available. A pending cloud write must not be shown as confirmed.
- Keep heavy work away from the renderer event loop. Bound concurrent expensive operations and provide meaningful progress and cancellation where safely supported.
- Test quota failures, lost responses, invalid data, partial operations, duplicate requests, manual Sheet edits and engine interruption.

## Desktop security and releases

- Preserve context isolation, sandboxing, narrow validated IPC, authenticated loopback access, restricted navigation and encrypted local credentials.
- Redact diagnostic data and validate paths, inputs and outbound destinations. Exclude production credentials and captures from source/release archives.
- Replace the previously exposed service-account key when a replacement is available; never distribute it with the app. Record credential rotation as an external prerequisite if account access is unavailable.
- Improve update states, integrity checks, active-work protection and migration recovery. Windows release signing requires an actual signing identity; configure and verify it when available, otherwise clearly leave signed distribution blocked.
- A GitHub source push is followed by a tested package/release pipeline before clients can update. Ensure CI also runs for source changes that do not increment the release version. Preserve the existing compatible update channel unless a tested transition is implemented.

## UI design and behavior

Create an original, cohesive Tv Tracker interface inspired by the clarity of Apple desktop software, while retaining familiar Windows behavior.

- Use a restrained blue accent, neutral surfaces, clear typography, consistent spacing, delicate separators and legible status indicators. Preserve useful table density.
- Organize the product around Overview, Orders, Captures, Reports, Activity and Settings. Keep comparisons within the capture workflow and daily/monthly reports within Reports; preserve all existing actions.
- Use a compact sidebar, a focused main workspace and an optional order inspector. Make Capture now prominent and give each screen an understandable primary action.
- Provide quick search, clear filters, saved views, useful order detail/history and visible data freshness. Preserve user context when background refresh completes.
- Build functioning views from real API data. Do not hardcode sample counts, statuses, fake histories or nonfunctional buttons from the concept image.
- Support comfortable resizing, keyboard navigation, visible focus, accessible names, appropriate contrast, screen-reader status announcements, light/dark/system preference and reduced motion. Ensure dialogs manage focus and can be dismissed safely.
- Cover setup, credential/connection checks, capture progress, comparison, sync retry, exports, reports, schedules, updates, backup and restore in the same design system.
- Empty states and errors should describe what happened and the next action without exposing implementation internals or blaming an upstream server without evidence.

## Performance and maintainability

- Profile before replacing working architecture. Reuse existing dependencies where reasonable.
- Use pagination/windowing, deferred or indexed search, lazy-loaded heavy views, cancellation of stale requests and cache invalidation appropriate to the measured workload.
- Keep Google Sheets batching efficient and preserve field ownership under concurrent edits. Introduce an indexed SQLite production replica only if profiling justifies it and test invalidation/recovery.
- Share reporting rules between UI and exports; maintain downstream schema compatibility. Offer useful selective exports alongside the full workbook.
- Make configuration, validation, adapters, IPC/API contracts and error handling understandable and testable. Add redacted support diagnostics and operational documentation.
- Strengthen schedule behavior across missed runs, sleep/wake and restarts, and document the catch-up policy.

## Verification and completion

Run focused tests as each stage changes, then run the affected full regression suites and a packaged Windows lifecycle check. Inspect the real rendered interface at supported window sizes and themes, including dialogs and failure states. Compare UI/report/export totals. Verify retained settings, captures and receipts across upgrades and restore drills.

Measure the roadmap targets on a recorded reference environment: interaction acknowledgement, navigation, search, startup, idle CPU and repeated-job memory. Report measurements and dataset sizes; do not present targets as achieved results. A longer reliability campaign and representative-user usability study remain separately identified when not executable in this session.

The final report must contain: implementation summary; mapping of all 22 roadmap ranks; files changed; dependency/configuration changes; test and visual evidence; performance measurements; intentional differences from the concept; remaining issues and exact external prerequisites; and a usable build or clearly identified build limitation. Keep the source and release status explicit. Do not label the release fully validated until its required gates pass.

## Brief validation before implementation

Validated against the 2.2.1 source and refreshed remote branch on 2 October 2026.

- Scope: P0-P2 implementation and UI, with P3 evaluation conditional on need.
- Architecture: local Electron/React/Python/SQLite with Google Sheets production authority; no new hosting requirement.
- Compatibility: keep app ID/profile, manual fields, preview numbering and existing product workflows.
- Design: original visual concept translated into functional states, accessible controls and actual data.
- Completion: concrete tests and measurements, with signing, credential rotation, portal availability and user studies reported separately when externally dependent.
- Sequencing: inspect, map, implement, test, render, package and report. No promise of universal bug-free behavior.

Validation result: coherent and executable. Proceed with the current desktop architecture and keep the implementation ledger accurate as evidence changes.
