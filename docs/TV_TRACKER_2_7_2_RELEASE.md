# Tv Tracker 2.7.2 — Google Sheets quota recovery

2.7.1 could exhaust the shared Google service account's read quota and label a 429 as a connection configuration error. Four PCs increased repeated metadata reads, report refreshes and formatting scans. Short whole-operation retries compounded the load.

## Changes

- Conservative per-account request budgets across connections and threads in each installation; designed for four PCs sharing the default Google quota.
- Three bounded transport attempts for quota rejections, honoring Retry-After with randomized cooldown. Other write failures remain governed by existing receipt/reconciliation logic.
- Batched month reads and header-only formatting reads; short metadata reuse with mutation invalidation. Ownership reads stay fresh.
- Durable, ordered capture retries with a five-attempt recovery cap. 2.7.1 failures specifically containing the Google 429 quota message resume automatically after upgrade.
- Background report refresh with dated saved data and accurate quota/refresh messages. Normal report cache freshness is two minutes; manual refresh remains available subject to cooldown.
- Backup and retention support for retry records.
- Installer acceptance baseline advances to the public 2.7.1 release.

## Rollout

Stop old capture/sync jobs and update every participating PC to 2.7.2. Retain each PC's existing workspace. No credential reimport is required for an active key. An interrupted publishing slot still requires explicit recovery only after the previous job has stopped; the app never steals an active slot on a timer.

This patch continues using Google Sheets. It does not provision or migrate to Supabase/PostgreSQL. The request budget is for four installations, not an unlimited multi-user service. Other programs using the same Google account can consume the remaining quota. A central backend is the next architectural step.

## Verification

Local checks completed on 6 October 2026:

- 258 backend tests passed; 46 focused recovery/regression tests passed after the final receipt changes.
- 26 desktop unit tests and 68 browser UI tests passed, including light/dark themes, short windows, cached browsing during refresh, and quota recovery.
- A real restricted QA workbook passed sequential publishing from four logical clients, retained the original raw rows, and fetched formatting headers in one batch request. This does not constitute testing four physical PCs.
- Reporting benchmark median: 842 ms; configured performance budgets passed.
- Python dependency audit, scoped lint, and credential-format scan passed.
- Packaged lifecycle, report import/export and encrypted connection recovery checks passed. The final 13 transport/retry tests also passed, including the five-attempt recovery cap.

Publication also requires packaged lifecycle/report/recovery/shutdown checks and the hosted actual installed 2.7.1-to-2.7.2 upgrade gate. The release workflow blocks publishing if these fail. Physical acceptance on all four customer PCs and sustained operation remain deployment checks; fixture tests cannot replace them.
