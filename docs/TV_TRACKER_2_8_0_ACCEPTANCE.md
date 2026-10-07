# Tv Tracker 2.8.0 — acceptance and release record

7 October 2026. [Candidate validation and review](https://github.com/HariKrishna1-DS/powerBI_Sync/pull/1). Public release and production cutover are separate gates. The last verified public branch is 2.7.2 at `6b020c0`.

## Implemented architecture

- Each installation keeps its own encrypted settings, SQLite captures, durable operation IDs and offline report cache.
- Named admin/manager application users share one Supabase workspace with full application permissions (`owner` role), including capture, reporting, settings and team management. Each person must be explicitly admitted. Existing restricted roles remain enforced for compatibility; public registration does not grant access.
- Transactional capture sequencing, immutable imports, optimistic order/report versions and idempotent receipts prevent duplicate processing and silent stale saves.
- One fixed office worker processes shared captures and publishes derived Sheets reports. Its durable job token survives restart and protected backup/restore. Jobs do not expire automatically into a second writer.
- Sheets uploads stage privately, verify hashes, recheck existing report digests and commit the report/receipt together. Unknown tabs and manual canonical fields are preserved. Small staging transfers share bounded requests.
- Existing direct Sheets workflows remain available outside shared mode. Shared clients never perform legacy cloud-history mutations.

## Changes completed in this phase

| Area | Result |
|---|---|
| Reporting source and capacity | Shared immutable Excel imports, versioned source/target changes; imported reporting does not replace canonical tracker orders |
| Monthly workflows | Shared reviewed setup/import/rollover, consistent canonical/monthly schemas, preserved month ownership and archived-month restrictions |
| SLA | Precise recorded timing eligibility, versioned manual corrections with timing provenance; inferred completion remains distinguishable |
| Admin/manager access | Full app access is the default team grant; migration 010 rechecks membership under the workspace lock so competing removals cannot remove all administrators |
| Cross-PC import retries | Migration 008 reuses identical immutable imports; different content with the same identity is rejected |
| Stale-save failure | Migration 009 uses explicit HTTP 409 instead of a PostgreSQL serialization code that can cause repeated PostgREST retries |
| Worker outages | Friendly credential/network/quota errors, retained job identity, bounded retry delay; local upload receipts can still reconcile |
| Sheets storage | Reclaims only this workspace's disposable staging, checks peak grid capacity before uploading, keeps existing visible reports on failure |
| Office-PC replacement | Owner-only adoption of the registered identity after protected state/token checks and explicit old-worker-stop acknowledgement |
| UI | Owner team controls and recovery acknowledgement, responsive dialogs, viewer capture, schedule, import and monthly/SLA write controls disabled, accurate shared-data source and acceptance/publication messages |
| Release gates | Fresh database contract checks now also block publication; installer acceptance baseline advanced to 2.7.2 |

## Evidence collected

| Check | Verified result |
|---|---|
| Full engine regression before final history guard | 330 tests passed |
| Final shared-client history guard and report safety | 20 tests passed |
| Focused conflict/recovery/monthly/reporting/SLA | 51 tests passed |
| Bounded publisher and worker failures | 17 tests passed |
| Final shared capture/schedule/routes regression | 24 tests passed; existing viewer schedule cannot start a browser or upload |
| Desktop Auth/settings/update/recovery rules | 41 tests passed |
| Focused monthly/owner/viewer/source UI | 14 tests passed; shared acceptance, offline provenance and missing-Google-key refresh errors verified |
| Full desktop UI before the final source-label corrections | 74 tests passed, including light/dark layouts, keyboard controls and viewer permissions |
| Packaged lifecycle | Passed: first launch, protected settings, backup restoration, restart persistence and safe browser handoff |
| Packaged reporting | Passed: multi-workbook import, source isolation, SLA deadline equality, Excel export and reload persistence |
| Packaged connection recovery | Passed: unreadable-vault startup, accessible update controls, encrypted backup restoration and restart |
| Packaged stalled-engine shutdown | Passed: bounded quit, engine termination and preserved capture after restart |
| Representative performance | Passed on 7,000 orders / 35 captures: clean-environment status median 35.13 ms, warm cache 125.54 ms, unchanged response 276 bytes; reporting median 1,215.29 ms |
| Lint and production dependency audit | Passed; no known vulnerabilities reported by the configured audits |
| Source credential-format scan | Passed; supplements credential rotation, not a substitute for it |
| Hosted migrations | 001–009 applied; 010 passed fresh-database/restore verification and awaits application; 005–009 received explicit owner approval |
| Hosted synthetic feature acceptance | Shared import retry, source isolation, simultaneous capacity conflicts, monthly import/setup/rollover, stale SLA rejection and manual-field preservation passed |
| Hosted publication | Synthetic workspace reached published revision 12; unrelated notes retained; production workbook unchanged |
| Real packaged shared client | Existing encrypted sign-in, owner controls, two canonical QA orders, monthly reports and Excel export passed without Google credentials or office-worker authority on the client |
| PostgreSQL dump/restore contract | Migrations 001–010 passed 27 tests, including full manager access and competing admin removals; synthetic database restored into a second database with identical records/functions/grants/RLS, then all 27 tests passed again |

The four concurrent save sessions used one owner account on one physical PC. This proves the API conflict behavior, not four-machine operational acceptance. The fresh PostgreSQL and synthetic restore checks passed in GitHub run 37578929223. This validates the database recovery mechanism; it does not establish or rehearse the hosted production project's backup service.

## Remaining release/rollout gates

1. Require a passing final-commit Windows build and actual 2.7.2 installer upgrade/recovery tests in GitHub; current check status and logs are attached to pull request #1. Verify the exact release artifacts and manifest before making an updater release public.
2. Rotate the previously exposed Google key on the owner's side. Valid old keys remain compatible; revoked keys cannot be made valid by the application.
3. Establish and rehearse shared PostgreSQL backup/restore independently of portable local workspace backups. Monitor database storage; no automatic deletion of canonical orders or retry receipts is enabled.
4. Confirm older capture/publish jobs are stopped on every PC, re-review the current production workbook, and approve its one-time migration before activation. Production is still shadow/unseeded.
5. Perform supervised four-PC acceptance with separate operator accounts and the registered office worker, including overlapping captures, outages, sleep/resume and a sustained normal working shift.

The app cannot guarantee availability while the office PC is shut down, sleeping or disconnected. Captures remain local or accepted in Supabase until that worker resumes. Generated Sheets tabs should be read-only for operators: Google Sheets cannot fence an arbitrary human edit occurring during the final commit window.

For the exact execution order, accounts, configuration and recovery procedure, follow [the multi-PC deployment guide](TV_TRACKER_MULTI_PC_DEPLOYMENT.md).
