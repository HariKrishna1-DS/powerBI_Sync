# Tv Tracker 2.8.1 — capture and publishing recovery

This maintenance release addresses the failures found during the 2.8.0 production setup assessment.

- Portal extraction reads Telerik's live item/page counters when no visible pager is shown. Counts, identities and page sequence must agree. Unknown historical captures stay unverified; their absence evidence cannot silently complete orders.
- Monthly publishing reuses existing worksheet IDs across capitalization differences and the legacy `Remaining_Search_<MONTH>_<YEAR>` name. Existing tracker rename migrations remain supported. Central publishing still refuses to replace an unreviewed worksheet.
- Migration preserves the highest next preview number from local history, retained workbook references and the legacy shared reservation counter. Activation rechecks the reviewed sequence.
- A network failure followed by an unreadable publication receipt stops automatic replay. Captures remain available for reconciliation and retry after connectivity returns.
- The primary raw worksheet can recover by its known `Sheet1` name if its original gid no longer exists.
- Pending publication has a waiting indicator. A successful report read is identified separately from capture publication. Unverified capture warnings explain their limitations.
- Default comparisons advance to the latest consecutive captures; explicitly selected historical comparisons stay selected. Primary navigation opens the section at the top.
- Restored credentials under a setup hold are described as paused, rather than incorrectly described as missing.

## Upgrade and setup

1. Keep automatic jobs on the other PCs stopped during the production migration.
2. Install the verified 2.8.1 installer over the existing app. Keep the same Windows user; do not uninstall/delete the profile. Export a protected backup first.
3. Confirm saved captures, credentials and settings are retained. Earlier unverified captures will not become verified merely by upgrading.
4. Resolve any difference between the live tracker and a recovery backup before selecting the canonical baseline. Do not overwrite newer live values with an older backup.
5. Follow [the multi-PC deployment guide](TV_TRACKER_MULTI_PC_DEPLOYMENT.md), sections 6–7: review the production baseline, activate it once, register the office publisher, then connect the other PCs to the same active workspace.
6. Verify one fresh capture end to end: expected row count equals extracted count; upload accepted; central processing completed; Sheets receipt verified; published revision catches up.
7. Only then enable the intended capture schedule. Keep one office worker running; clients submit through Supabase rather than writing directly to Sheets.

Each person needs an application Auth identity with workspace membership, not a separate Supabase project or dashboard account. Distribute the installer and public project configuration. Keep Google JSON, encrypted owner profiles, passwords and privileged database credentials off client setup bundles.

## Release gates

Run engine, desktop, extractor and UI regressions; lint and dependency audits; packaged lifecycle, report, backup/recovery and shutdown checks; and the 2.8.0 → 2.8.1 updater rehearsal. Verify installer/feed checksums before publication. CI executes actual NSIS upgrade and recovery on a disposable Windows runner.

Successful automated checks do not certify historical SLA timestamps, rotate an exposed Google key, or establish sustained reliability on the four physical PCs. Those deployment checks remain separate and must be recorded honestly.
