# Tv Tracker implementation ledger

Started 2 October 2026 from `854fd2b`, version 2.2.1, on `tv-tracker`. The refreshed remote matched the local baseline. The validated brief is `TV_TRACKER_MASTER_PROMPT.md`; test and build evidence is in `TV_TRACKER_2_3_0_REVIEW.md`.

Version 2.3.0 is a local release candidate. It advances the roadmap; it does not establish that every target or public-release gate has passed.

| Rank | Priority | Requirement | Implementation and evidence | Remaining work |
| --- | --- | --- | --- | --- |
| 01 | P0 | Sync correctness | Preserved receipts, readback, manual-field ownership and normalization. Added connected-import numbering recovery and capture/import exclusion. Engine regressions pass. | Fresh production capture/readback acceptance. |
| 02 | P0 | Durable recovery | Bounded SQLite operation history, interrupted-run detection, backup integration and recovery backup before update shutdown. | Extended process-kill and upgrade campaign. |
| 03 | P0 | Portal resilience | Retained bounded extraction/incomplete-result protections. Actual desktop extractor passes a two-page fixture with decoy-table exclusion. | Healthy-empty, expired-login and changing-portal acceptance over time. |
| 04 | P0 | Security | Preserved vault, authenticated loopback, sandbox and IPC boundaries. Added private diagnostics and CSV formula neutralization. | Rotate exposed Google key; independent review. |
| 05 | P0 | Signed safe updates | Always-run CI, read-only PR validation, separate publication, signature gate and recovery backup before update shutdown. | Authorized signing identity and signed update trial. |
| 06 | P0 | QA release gates | Expanded engine, browser, native and extractor checks; retained tested CI artifacts. | Observe remote CI after push; 200-run operational campaign. |
| 07 | P1 | Responsiveness | Deferred/cached search, reusable collator, bounded rows, serial polling and lazy charts. Measured 100,000-row search. | Cold search exceeds 300 ms; reference-device navigation/startup and soak profiling. |
| 08 | P1 | Indexed cache | Existing dated production cache and SQLite captures retained. | Measure real volumes/invalidation before another data representation. |
| 09 | P1 | Sheets efficiency | Existing shared reads, batching, readback and targeted invalidation retained and tested. | Production quota/request measurements. |
| 10 | P1 | Playwright pilot | Playwright drives UI tests; existing production extractor validated on isolated portal fixture. | Separate Playwright extractor pilot and authenticated parity comparison remain pending. |
| 11 | P1 | Calm interface | Implemented Overview, Orders, inspector, saved views, status pills, themes and shared surfaces. | Representative-user usability review. |
| 12 | P1 | Accessibility | Accessible names, dialog focus, visible focus, reduced motion, themes and 1440/1024/800/640 px checks. | Full screen-reader/contrast audit; no certification claimed. |
| 13 | P1 | Diagnostics | Durable Activity entries and authenticated metadata-only export. | Review usefulness in real support cases. |
| 14 | P2 | Scheduling | Atomic writes, bounded inputs, existing network-anchored IST/catch-up/overlap behavior tested. | Real sleep/wake and multi-day soak. |
| 15 | P2 | Order workflows | Filters, search, 12 named views, sort, pagination, inspector and latest-100-capture history; search survives refresh. | Native appearance/views persist in the encrypted settings vault; browser development uses local storage. Preferences are excluded from workspace ZIPs. |
| 16 | P2 | Reporting | Existing daily/monthly/SLA and full export preserved; safe filtered CSV added. | Representative large-workbook acceptance. |
| 17 | P2 | Maintainability | Separated new workspace UI, tokens and journal; documented API/recovery/release contracts. | Further legacy server/report decomposition can be staged. |
| 18 | P3 | DuckDB/Polars | Deferred; no demonstrated analytics need. | Representative benchmark before adoption. |
| 19 | P3 | Collaboration | Shared Sheets workflow preserved. | Define roles/conflicts/audit before a server product. |
| 20 | P3 | PostgreSQL/Neon | Deferred; local desktop remains independent of hosted DB. | Reconsider for centralized multi-user requirements. |
| 21 | P3 | Redis | Deferred; no distributed worker fleet. | Adopt only for a measured distributed queue/cache need. |
| 22 | P3 | Tauri | Deferred; no architecture/profile rewrite. | Compare measured gains against migration cost. |

## External release evidence

- Rotate the Google key exposed in the conversation and import its replacement locally. Never commit it.
- Supply a legitimate Windows signing identity and verify a signed update through the existing channel.
- Complete a fresh capture and Sheets readback while TitleVision returns a verifiable queue. Prior QC saw an empty/timeout state; this run does not establish current portal availability.
- Complete extended reliability, performance, accessibility and user studies. Targets are not passing results.

Optional cloud/database products are intentionally deferred. The extractor pilot and unmet performance targets are pending, not counted as implemented.
