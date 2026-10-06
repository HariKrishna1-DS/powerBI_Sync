# Tv Tracker shared backend contract — v1

Target project: `https://qontoybecrqpbjzoajqf.supabase.co`.

Status: implementation and acceptance in progress. The released 2.7.2 application remains on Sheets until a reconciled cutover. A project URL is not authorization to administer a project; deployment uses the owner's authenticated dashboard/CLI.

## Data ownership

PostgreSQL owns workspaces, membership, immutable captures, canonical orders, operation receipts and publisher state. SQLite retains captures and a durable upload outbox on each PC. Sheets becomes a generated report destination. Direct edits to generated tabs must be migrated/reviewed before cutover; they cannot silently compete with PostgreSQL.

Each workspace represents one capture queue/scope and one workbook. Different queue filters require separate workspaces. Viewer, editor and owner roles are checked inside every client RPC. Tables live in an unexposed schema with RLS and no client table grants. Clients get a publishable API key plus a Supabase Auth user session. Privileged keys are server-only.

Capture submissions require the portal's expected and actual row counts to match the uploaded rows. Legacy captures without that evidence and Excel imports cannot be submitted as verified queue captures. The first contract supports printable ASCII order numbers, 1–200 characters, normalized by trimming spaces and case. Other identifiers are rejected for review; extending this requires identical Unicode normalization in PostgreSQL and Python. Order keys use `C` collation so pagination matches the desktop's ordering checks.

## RPC contract

All calls use `POST /rest/v1/rpc/<name>`, an `apikey` header and a user bearer token. HTTPS is mandatory outside local tests. JSON errors are classified by HTTP/SQLSTATE; tokens and raw upstream responses are never included in user errors.

| RPC | Inputs | Contract |
|---|---|---|
| `tv_create_workspace` | stable workspace UUID, name, queue scope | Creates a shadow workspace and owner membership atomically. Retrying the same UUID and configuration returns the existing workspace to its owner. |
| `tv_list_workspaces` | none | Lists only the signed-in user's workspaces and role. |
| `tv_set_member` | workspace UUID, operation UUID, registered user UUID, role/null | Owner-only, audited membership update/removal. Cannot remove or demote oneself. |
| `tv_submit_capture` | workspace UUID, operation UUID, captured timestamp, payload | Validates a complete capture, allocates a shared sequence and stores a receipt in one transaction. Same operation and body returns the original result; a changed body conflicts. |
| `tv_snapshot` | workspace UUID, optional expected revision, order cursor | Returns at most 500 canonical orders plus revision and next cursor. A changed revision forces a consistent restart. |
| `tv_operation` | workspace UUID, operation UUID | Reports accepted/processed/review status; accepted is distinct from published. |
| `tv_edit_order` | workspace UUID, operation UUID, order key, expected version, patch | Optimistic concurrency; stale edits return conflict. Only manual columns are editable. |

Owner membership administration, seed import and activation require explicit owner actions. Worker-only RPCs claim one durable job per workspace, read its consistent input, commit a capture using a revision check, and acknowledge a verified Sheets publication. A crashed publisher is **not** replaced by an expiring lease: Sheets cannot enforce a PostgreSQL fencing token. Recovery requires stopping the old worker, reviewing the Sheets receipt and clearing the exact job token.

Workspace creation, membership changes, capture acceptance, order edits and worker completion have retry receipts. A completed job token can never claim a new job. Reusing a completed token with a different result is rejected. Publication acknowledgment has a database receipt too; the future publisher must additionally verify the receipt in Google Sheets before calling it.

## Processing and recovery

1. Save a capture locally before networking. Assign its operation UUID once and persist it.
2. The outbox retries timeouts/429/5xx with capped backoff and the same operation UUID. Authentication pauses for sign-in; validation and conflicts require review. Newer captures never skip an unresolved earlier local capture.
3. Submission is atomic, but it does not claim orders are processed or published.
4. One trusted worker processes captures with the existing tracker merge and SLA routines. Late captures remain archived for review and do not roll current state backwards. Missing orders imply inferred completion only across validated snapshots of the same queue.
5. Canonical changes, the capture result and pending publication revision commit together.
6. The publisher writes a deterministic full report snapshot and a revision/hash receipt in the same Sheets batch. Lost responses are reconciled against that receipt; publication is acknowledged only after verification.
7. Desktop reads are served from a dated local cache. A failed upload or publisher never discards local data.

## Cutover gates

- Run real PostgreSQL tests: unauthenticated/cross-workspace denial, viewer write denial, duplicate requests, simultaneous submissions/edits, crash recovery and late capture handling.
- Run the existing completion/SLA regression suite against the backend adapter.
- Import a read-only snapshot of current tracker rows; preserve identifiers/manual columns; reject duplicate identities and report reconciliation counts/hash.
- Rehearse with synthetic data in a restricted workbook. Stop old direct-Sheets writers before activating PostgreSQL.
- Verify owner membership, server secrets, backup/restore, deployed worker health and four-PC acceptance before enabling the desktop switch or releasing an installer.
- A free project is suitable for evaluation; production availability/backup requirements must be checked against the chosen Supabase plan. No paid plan is selected automatically.

References: [Supabase API keys](https://supabase.com/docs/guides/getting-started/api-keys), [database functions](https://supabase.com/docs/guides/database/functions), [RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Preparation checkpoint — 2026-10-06

Branch: `codex/supabase-backend`, based on released 2.7.2. No release version change, production workbook mutation, or cloud migration has been performed by this checkpoint.

Implemented locally:

- Transactional schema and restricted RPCs for workspace membership, immutable captures, optimistic edits, consistent report pagination, exclusive jobs and durable receipts.
- Desktop-side transport and durable SQLite upload queue, not yet connected to the application's live capture routes. Backups preserve operation IDs and validate upload integrity; deletion/retention protect unresolved uploads.
- Central processing adapter using the existing merge, completion and SLA routines. Manual assignments/comments survive processing; inferred completion remains distinguishable from recorded completion.
- Restart-safe shadow worker with a persistent job token and local process lock. It deliberately refuses active publishing. Its RPC transport must be supplied by the eventual server host.
- PostgreSQL contract tests using an isolated Docker container; Python regression tests; a database-only GitHub Actions workflow. The workflow does not deploy or publish an installer.

Local verification at this checkpoint: **12 PostgreSQL acceptance tests passed; 279 Python regression tests passed; syntax/undefined-name lint passed.** The database tests cover anonymous/viewer/cross-workspace denial, four concurrent submissions, idempotent creation/edits/membership/worker receipts, stale edits, incomplete captures, exclusive job ownership, late captures and publication acknowledgment. Python tests additionally cover upload retry IDs, session pauses, consistent snapshot refresh, backup/restore, corruption, retention, manual fields, completion/SLA behavior and worker restart. These results do not constitute hosted Supabase or four-PC end-to-end acceptance.

Still required before users can use Supabase:

1. Access the owner account for the supplied project; inspect project settings, Auth and existing schema before applying anything. No privileged key belongs in a desktop installer.
2. Select the central worker host. An always-on office PC avoids a separate host bill but publication stops while it is offline. A managed worker improves availability and may add hosting costs. Captures must remain queued through either outage.
3. Implement encrypted desktop Auth/session refresh, workspace selection and explicit backend routing. Add UI states for accepted, processing, review and published; test the four client accounts.
4. Complete baseline import/reconciliation, controlled activation, stopped-worker recovery and cloud retention/backup policies. Current worker claims return the complete canonical dataset; profile and bound this before cutover at the real workbook size. Desktop snapshots currently cap at 100,000 rows.
5. Implement the central Sheets publisher with deterministic report content and an atomic revision/hash receipt; rehearse lost responses, conflicting writers and restart recovery against the restricted synthetic workbook.
6. Stop legacy direct-Sheets writers, verify cloud reconciliation and backups, then activate deliberately. Run build → install → in-app update → recovery before publishing a new release.

### Reproducing local acceptance

The local harness expects an isolated `postgres:17-alpine` container named `tvtracker-db-qa-` followed by ten lowercase hex characters, with that name saved to ignored `.desktop-build/supabase-qa-container.txt`. It uses Docker exec without host ports. Never point the harness at a production database. Each run creates a fresh database inside that QA container and applies every migration.

```text
python supabase/tests/run_database_tests.py
python -m unittest discover -s gsheet_dashboard -p 'test_*.py'
```

For the Python suite, make the repository root, `gsheet_dashboard`, and installed backend dependencies available on `PYTHONPATH`. The PostgreSQL harness provides test-only Auth roles; it verifies database permissions and transactions, not Supabase's hosted JWT gateway or Auth service. Hosted acceptance remains mandatory.
