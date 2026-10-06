# Tv Tracker 2.7.1 — shared publishing and import review

## Fixes

- Every updated PC can capture and publish to the same workbook. An atomic, workbook-wide job slot covers reads, calculations and writes; competing jobs wait with bounded backoff. A permanent designated writer is no longer required.
- Shared preview numbers are reserved before capture or queue-file import. A failed, unpublished capture cannot cause another PC to reuse its number. Gaps are intentional; reserved numbers are never recycled.
- Existing shared history is recovered before capture or sync. Conflicting local captures are retained and reported rather than overwriting shared history.
- An interrupted publishing slot requires deliberate recovery in **Data Sheets → Storage and recovery → Shared publishing**. First stop Tv Tracker on the computer running that job. Slots never expire automatically while a writer might still be active.
- Excel imports merge formatting-equivalent duplicates and complementary blank fields. Genuine conflicts show the order number, source workbook/tab/row and differing fields. Users explicitly choose a source row and validate again; choices are bound to the exact uploaded files. Imports never activate automatically.
- Daily Orders now explains uncertain SLA timing and can filter affected orders. Missing dates/times and inferred completion remain outside confirmed SLA totals; no timestamps are fabricated.

## Four-PC rollout

1. Stop scheduled captures and finish/stop running sync jobs on **all PCs** using the workbook.
2. Update every PC to **2.7.1** through Connections & settings → Updates.
3. Keep each PC's saved Google key and spreadsheet configuration. Existing valid keys continue to work.
4. Resume capture/publishing. The first new job migrates the workbook control protocol; older app versions become read-only for this workbook.
5. If a PC loses its connection or crashes during publishing, stop that app before releasing the interrupted slot from another updated PC.

Updating every writer before resuming is necessary: migration cannot cancel a request already sent by an older version. Google Sheets edits and external scripts do not participate in the app's coordination protocol.

## Validation scope

Backend concurrency tests cover simultaneous claims, four sequential writers, unique reservations, lost replies, ownership loss and explicit recovery. Import tests cover complementary duplicates, genuine conflicts and stale review selections. Interface tests cover conflict review, uncertainty filtering, recovery confirmation, responsive layouts and automated accessibility. Live API acceptance uses the separate synthetic QA workbook; production rows are not changed.

The release pipeline must pass the actual installed **2.7.0 → 2.7.1** NSIS upgrade, failed installer handoff recovery and restoration of its real pre-update backup before publishing. Release downloads are compared with the generated artifacts before stable publication.

The four client computers themselves are not remotely accessible from this workspace. Live QA uses four logical clients; physical-PC rollout still needs the sequence above. Invalid source timing needs correction in the source workbook, and genuine duplicate order rows need a user source choice.
