# Tv Tracker — ordered multi-PC setup and deployment

Prepared 7 October 2026 for the Supabase release candidate. Follow the numbered steps in order. The public 2.7.2 release does not include this complete shared-workspace implementation. Do not distribute an unreleased build as a validated production release.

## 1. Choose responsibilities and one office worker

- Choose one Windows PC that can stay powered on, connected to the internet, signed into Windows and running Tv Tracker. This is the office worker. Closing to the tray keeps the app running; Workspace → Quit stops it.
- Use a named owner application account on that PC. Use separate named editor accounts for operators and viewer accounts for people who only read reports.
- Use **one** Supabase project, **one** production workspace and **one** Google workbook for the team. Do not create a project or workspace on each PC.
- An operator needs an **application account in Supabase Authentication**, not a Supabase dashboard/developer account. A person can use their application account on more than one PC. Separate accounts for separate people provide a meaningful audit trail.
- The office PC is an availability dependency: clients can retain captures locally and upload to Supabase when available, but Sheets publication waits while the worker is offline. There is no automatic second-worker takeover.

| Item | Shared centrally | Each client PC | Office/admin only |
|---|---|---|---|
| Project URL and publishable API key | Same project | Configure in app | Keep deployment record |
| Application account | Auth user identity | Sign in separately | Create/invite users and grant membership |
| Workspace ID, queue scope, order versions | Supabase | Select permitted workspace | Create, reconcile and activate once |
| Orders, reporting source/imports, capacity, SLA corrections, month ownership | Supabase canonical data | Read/write according to role | Govern retention and database recovery |
| Capture sequence and retry receipts | Supabase | Keep own durable upload IDs | Worker processes jobs in sequence |
| SQLite captures, pending uploads, report cache, UI preferences | No | Local Windows profile | Back up office worker state too |
| Google service-account JSON key | No | **Do not distribute** | Import into office app's encrypted vault |
| Google workbook | Derived report | Viewer link if needed | Service account has Editor access |
| Supabase database password, secret/service-role API key, dashboard account | No | **Never distribute** | Privileged administration only; desktop worker does not require service-role key |

## 2. Verify the Supabase project once

1. Administrator: open the project dashboard for `qontoybecrqpbjzoajqf`. The application URL is `https://qontoybecrqpbjzoajqf.supabase.co`.
2. Confirm the project is running, the correct region and availability plan are selected, and email/password Authentication is enabled for the application's accounts.
3. Verify migrations `202610060001` through `202610070009` were applied in order. On this project they were applied through the dashboard SQL editor. **Do not replay them**; reconcile the Supabase CLI migration history before a later CLI `db push`. Migration 009 returns stale-save conflicts promptly rather than using a database serialization error that can trigger repeated server retries.
4. Keep `tv_tracker` private. Its tables have RLS enabled and no anonymous/authenticated direct table grants. Authenticated clients use restricted public RPCs with workspace membership checks. Do not expose this schema or grant blanket table access to make a client error disappear.
5. Copy the **publishable** key from the project's API Keys page. This desktop configuration accepts `sb_publishable_…`; it rejects administrator/secret keys. Record the URL and publishable key in your deployment instructions, not a private database password.
6. Inspect your plan's backup facilities and schedule protected exports if managed backup/restore does not meet your needs. Perform an isolated database restore rehearsal before accepting production dependency on Supabase. A local Tv Tracker workspace backup is **not** a backup of the shared PostgreSQL database.
7. If using invitations or password-reset mail, configure the project's email delivery and complete the account/password setup in the user's browser. The desktop currently signs in with email and password; it does not consume invitation links or provide self-registration.

Supabase documents [publishable versus secret keys](https://supabase.com/docs/guides/getting-started/api-keys), [Auth users](https://supabase.com/docs/guides/auth/managing-user-data) and [database backups and plan-dependent recovery](https://supabase.com/docs/guides/platform/backups). Project dashboard membership and application workspace membership are separate.

## 3. Prepare Google Sheets once, on the admin/office side

1. Select the existing production workbook. Current destination: `1xjQ3yaDpMgvp3cRSQM-SfF8UBnbTcW_HWpZp_aN5-a8`.
2. Confirm the Google Sheets API is enabled in the service account's Google Cloud project.
3. Share only the required workbook with the publishing service account as Editor. Operators normally need Viewer access to generated reports. Restrict general access according to your production-data policy.
4. Import the Google service-account JSON through the office app's Connections settings. Do not put the JSON in the installer, Git repository, chat, or client-PC setup bundle.
5. A valid existing key remains supported; a key that Google has revoked will fail. The previously exposed key still requires owner rotation: generate a replacement, import and verify it on the office PC, then revoke the exposed key. Compatibility does not make an exposed credential safe.
6. Generated report tabs are read-only projections. Make corrections through Tv Tracker. Unrelated user tabs are retained. Direct changes to a generated tab stop publication when its digest differs; Sheets has no transaction-level compare-and-swap against an arbitrary human edit during the final commit.
7. Keep the synthetic acceptance workbook separate from production. Do not select a QA workspace or bind production to its ID.

## 4. Install and configure the office PC

1. Obtain the verified Windows x64 installer from the official `HariKrishna1-DS/powerBI_Sync` GitHub release. Confirm its version matches the release notes. Use the NSIS `.exe` installer for normal deployments.
2. Run the installer as the intended Windows user and launch Tv Tracker. The packaged app includes its engine and extraction dependencies. Clients do **not** need Python, Node, npm, PostgreSQL, Redis, Docker or Supabase CLI.
3. Install/use supported Google Chrome or Microsoft Edge for TitleVision capture; select the browser executable only if automatic detection fails.
4. Settings → Connections: configure the TitleVision queue URL and that operator's existing TitleVision credentials. The queue must exactly match the production workspace scope. Current queue: `https://tv.datatracetitle.com/Queues.aspx?qid=23656`.
5. Configure the production Sheets URL and import the service-account JSON on this office PC. Save and verify the connection.
6. Settings → Shared workspace → Project connection: save the project URL and publishable key.
7. Sign in using the owner **application** account, not the Supabase dashboard login. The app protects session credentials with Windows encryption; it does not retain the entered application password.
8. For the first deployment only, create the first shared workspace. If the existing owner workspace is listed, select it instead of creating another. The initial mode is shadow/validation.
9. Do not select **Run office worker** until the reviewed activation in step 6 is complete.

## 5. Create users and grant application access

1. Administrator: Supabase dashboard → Authentication → Users. Create/invite one application user for each person. Have the user complete their password setup privately. Do not send passwords through this repository or copy the owner's app profile to other PCs.
2. Copy that user's UUID from Authentication. Verify the person and UUID before granting access.
3. Owner in Tv Tracker: Settings → Shared workspace → choose the production workspace → **Team access**.
4. Paste the UUID, choose **Editor** (capture and change shared data) or **Viewer** (read reports), review the confirmation and save team access.
5. Give the user the project URL, publishable key, approved installer and exact queue URL. They sign in with their own application account and refresh their workspace list.
6. For removal, choose **Remove workspace access** and save. Server RPCs check membership on each call. A disconnected PC may still have previously downloaded local data; remove/protect that local profile under your organization's offboarding policy.
7. Do not give ordinary operators owner permissions or Supabase project-dashboard administration. Team access in this release deliberately offers editor/viewer/removal, not automatic owner promotion.

## 6. Review and activate production once

1. Before cutover, keep a recoverable copy of the production workbook and export an encrypted portable Tv Tracker backup from the office PC. Verify that the backup opens/restores in an isolated test installation.
2. Stop scheduled captures, pending direct Sheets publishing and old Tv Tracker jobs on **every** PC. Confirm with each operator; a local check cannot prove the other PCs stopped.
3. Owner, office PC: Shared workspace → choose the real production workspace → **Production migration · office PC** → **Review production baseline**.
4. Compare Full Search/Remaining counts, status totals and next shared preview number with the workbook. Review retains manual columns, monthly ownership and the encrypted snapshot. Duplicate identities stop migration. It does not recalculate historical timing.
5. If the workbook changed, review again. The app rechecks the baseline digest before seeding/binding; an old review cannot silently replace newer workbook data.
6. Check both acknowledgements only after verifying the snapshot and confirming that all older jobs stopped. Click **Activate reviewed workspace**.
7. Activation imports the canonical baseline transactionally, preserves shared sequence, binds the workbook and registers this PC's fixed worker identity. The workbook's central protocol blocks old direct writer paths.
8. Click **Run office worker on this PC**. Keep this owner session and app running. Check that the database revision reaches the Sheets published revision, with no pending/conflicting job.
9. Export a new portable backup after activation; it now contains the registered migration/worker recovery material. Copy the password-encrypted backup to protected storage outside the office PC. Store its password separately.
10. Enable the intended schedule after one supervised capture → upload → process → publish cycle passes. Do not enable duplicate automatic schedules on every PC unless that frequency is intentional.

## 7. Configure each additional PC, in order

1. Install the same verified release under the intended Windows user. Use the installer; do not copy the installed application directory or another user's encrypted profile.
2. Configure its browser and exact TitleVision queue. Add that person's TitleVision credentials if they capture queues. A report-only user does not need portal credentials.
3. Enter the same Supabase URL and publishable key in Shared workspace. Ordinary clients do not need the Google JSON key.
4. Sign in using that person's application account.
5. Refresh workspaces; select the existing **active production** workspace. If absent, ask the owner to grant membership. If still shadow, wait for activation. Do not create a replacement workspace to bypass either condition.
6. Click **Use this shared workspace**. Do **not** select Run office worker on an operator PC.
7. Confirm the correct workspace name and shared reports load. The Live Google Sheets link opens the bound production workbook.
8. An editor: perform one supervised capture. Confirm local retention, accepted upload, central processing and published revision. A viewer: confirm reads work and write actions are denied.
9. Repeat on all four PCs with separate users; include overlapping captures and simultaneous changes. Confirm no duplicate sequence numbers and that stale changes require refresh.
10. Export that PC's portable backup if its local capture history/offline uploads need recovery. Do not restore another operator's workspace backup into a live client: unresolved outbox records retain their original workspace and actor receipts.

## 8. Understand sync, clashes and failure states

| Situation | Expected behavior | Action |
|---|---|---|
| Two PCs submit captures together | Supabase allocates unique shared sequence numbers transactionally | Let the worker process; local capture IDs remain local |
| Upload succeeds but its reply is lost | Retry reuses the durable operation UUID and returns the original receipt | Retry; do not manufacture another operation |
| Two users save an old report/month/order version | First valid change commits; stale change receives conflict | Refresh, review the current values and retry deliberately |
| Same immutable report imported on two PCs | Same import identity/data is reused | No duplicate canonical orders are created |
| Captures arrive late/out of order | Evidence is retained; processing flags review rather than rolling state backward | Review the capture/report evidence |
| Portal is down or capture is incomplete | Capture cannot falsely complete missing orders | Retry after recovery; do not force an empty capture |
| Office worker is offline | Accepted captures remain queued; published revision stays older | Restart the registered office worker |
| Client is offline | Captures/operation IDs remain local; dated report cache may be shown | Reconnect and retry; cached values are not new server writes |
| Auth expires/revoked | Sign-in is required; pending operations are retained | Sign in with the same permitted account |
| Sheets returns 429/5xx | Worker retains durable job and retries; clients do not each poll Sheets | Allow backoff; repeated clicking does not raise Google quotas |
| Generated tab edited directly | Digest check stops publication instead of erasing detected edits | Preserve edits, compare with canonical data and reconcile through admin review |
| Worker crashes after Sheets commit | Original token plus receipt reconcile the committed publication | Restart with the same profile/recovery token |

Received, processed and published are distinct states. Queue disappearance is inferred completion, not independently confirmed delivery. SLA statistics exclude uncertain/inferred timing; an exact recorded deadline is On Time. Cancelled/suspended/open orders do not receive a fabricated SLA result.

## 9. Back up and replace the office PC

1. While healthy, export password-encrypted portable workspace backups regularly and after activation. Copy them to protected storage on another device. Test restoration; do not rely solely on backup creation succeeding.
2. Separately retain administrator-controlled PostgreSQL backups with tested restoration. Preserve canonical orders, memberships, capture evidence, operation receipts, reporting/monthly state and any unfinished job. Do not independently trim idempotency receipts or delete pending captures.
3. Before replacing the worker, stop the old app and disable its ability to restart. Restore the newest portable backup on the replacement Windows PC through the app's Restore workflow.
4. Configure the Google JSON/workbook, exact queue and Supabase connection separately; credentials are excluded from portable workspace backups. Sign in as the workspace owner.
5. Select the active production workspace → **Recover office worker on a replacement PC**. Confirm that the previous worker cannot restart. Click **Verify restored worker recovery**.
6. Recovery verifies the encrypted activation plan matches the registered worker/workbook. If a central job exists, the restored token must own that exact job. It does not clear a job or allocate another worker identity.
7. Only after verification succeeds, click **Run office worker on this PC**. Confirm publication resumes and export a fresh protected backup.
8. If the pending job's token was not backed up, keep the job and both recovery copies intact. An administrator must reconcile the database and Sheets receipt in a controlled maintenance window. Do not delete `tv_tracker.jobs` or the workbook fence to make the error disappear.

## 10. Local files, environment and startup

- Normal profile: `%APPDATA%\DataTrace Studio` (historical name deliberately retained for upgrades). `settings.vault` contains Windows-encrypted connections/session; `workspace\previews` contains local SQLite captures/outbox; `workspace\migration-snapshots` and `workspace\shared-worker` contain protected migration/job recovery state.
- Portable backup export covers workspace data and recovery material, **not** Supabase database contents, Windows-encrypted credentials, browser profiles or another PC's settings vault.
- End-user installation needs **no environment variables or editable `.env` file**. Set connections inside the app. The installer includes the engine, UI and extractor.
- Developer/test variables (`DATATRACE_TEST_USER_DATA`, `DATATRACE_PYTHON`, `DATATRACE_DESKTOP_TOKEN`) are implementation/test controls, not deployment instructions; do not set them on client PCs. Never distribute an engine token.
- Leave Windows clock/timezone correct. Keep an office session running and configure Start at login if desired. The worker currently runs inside the desktop application, not as a Windows service.
- Use Workspace → Quit for a deliberate shutdown. An updater checks for active work, saves recovery material and installs only after an explicit user action. Do not force-kill a publishing worker during routine upgrades.

## 11. Release and four-PC acceptance

1. Build from the tested commit; run backend, database, desktop, UI, security and performance gates.
2. Verify all release assets: installer, installer blockmap, Windows ZIP, source ZIP and `latest.yml` version/SHA-512/size. Publish the complete tested set together.
3. On an isolated Windows test installation, upgrade the actual previous public version using the candidate artifact; verify settings, captures, pending operations and worker tokens survive. Test installation failure and recovery.
4. On the four real PCs, verify editor/viewer isolation, overlapping captures, shared source/targets, monthly rollover, SLA corrections, outages, duplicate retries and stale saves. Rehearse office-worker restart/replacement without a second publisher.
5. Run a supervised full shift with intentional offline and sleep/resume cases. Record results, duration and recovery. Automated concurrency tests on one PC do not prove this four-PC or sustained gate.
6. Release only after required evidence and credential/backup operational requirements are satisfied. Keep the production cutover separate from publishing an installer: an update must not silently activate or migrate a customer's workbook.

## Admin distribution checklist

**Distribute:** official installer, release notes, this guide, project URL/publishable key, exact queue URL, existing workspace name/ID and each user's private account-setup instructions.

**Retain on admin/office side:** Google private JSON, owner app session, Supabase dashboard/database credentials, database backups, protected worker backups/passwords, migration decisions and release authority.

**Do not copy:** `settings.vault`, Chromium `Local State`, another user's browser data, raw Google private keys or a project-wide Supabase secret/service-role key.

**Current validation limits:** production remains unactivated until all old writers are confirmed stopped and reconciliation is approved. Four physical PCs, a sustained shift, the final candidate's installer update/recovery and the previously exposed Google key's rotation remain operational release gates unless recorded as complete in the candidate validation report.
