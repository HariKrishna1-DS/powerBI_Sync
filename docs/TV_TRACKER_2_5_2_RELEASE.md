# Tv Tracker 2.5.2 — report accuracy and workspace polish

## Behavior

- Monthly Google Sheets views now appear as a matched pair: `Full_search_OCT_2026` and `Remaining_OCT_2026`. Remaining includes every other product, regardless of the app's selected chart products. Subsequent active months use the same naming convention. These are derived views; production trackers remain the authoritative owners and totals do not double-count them.
- Existing Full Search column order is preserved. Views include tracker details and additional raw capture fields, are sorted by arrival time, and have consecutive serial numbers. Raw capture history remains unchanged.
- Status conditional formatting follows the shared Sheet palette across managed tabs and Excel exports. It preserves unrelated conditional rules and follows future status edits.
- Only Completed and Delivered orders with a valid, precise Out Time and SLA deadline receive On Time or Missing. Completion at the deadline is On Time. Open, cancelled and suspended orders remain blank. Date-only values, elapsed-hour fields and impossible completion chronology require review instead of an invented result. A negative countdown alone does not prove a completed order missed its deadline.
- An Out Time alone no longer changes an order's status to Completed and Delivered. Existing manual fields and explicit statuses remain authoritative.
- Overview, orders, daily and monthly metrics use theme-aware category accents. Attention and missed SLA use red, completion uses gold, clarification uses purple, and other categories retain distinct restrained accents.
- Daily metric padding and number baselines are consistent. Monthly controls share a baseline and wrap on narrow windows. Dark and light surfaces, borders, navigation selection and status pills have clearer contrast.
- A collapsed or narrow sidebar shows a theme icon instead of a clipped System label. System, Light and Dark menu choices have icons, a selected checkmark, arrow/Home/End navigation, Escape dismissal, focus return and saved selection. The menu is outside the sidebar's clipping region.
- Quick actions explicitly focuses its search field after the native dialog opens. Theme-save errors keep the confirmed selection and fit short windows. Settings footer buttons share a height and baseline; form scrolling reserves space around fields. Secondary text tokens meet a 4.5:1 contrast floor on the checked common surfaces in both themes.
- Native shutdown uses a bounded engine request, avoiding a long wait if its shutdown reply stalls. The explicit quit path retains its existing active-work confirmation and termination fallback. A packaged regression checks both bounded shutdown and saved capture persistence after restart.

## Live Sheet verification — 5 October 2026

- Full Search view: 149 orders; Remaining view: 371 orders.
- Authoritative production records: 7,257, unchanged.
- 117 ambiguous SLA labels cleared: 8 Full Search and 109 Remaining.
- Every original production cell outside Free Site was compared using formula rendering and preserved, including manual details, statuses and timestamps.
- Atomic cloud backups were created before replacing affected production trackers and the existing Full Search view. A durable operation receipt prevented duplicate application after a verification request timed out. Readback subsequently passed.
- Existing daily/monthly comparison counts and reporting columns were preserved; only applicable SLA counts were repaired.

## Validation

- Backend: 177 tests passed, including completion eligibility, exact SLA boundary, negative countdowns, date precision, both trackers, derived views, repeated sync, exports and existing monthly maintenance.
- Desktop: 20 settings, encrypted vault, update state and release integrity tests passed.
- Frontend: all 45 checks passed together on the final source. Focus, contrast and footer alignment regressions found by the deeper review were corrected. Coverage includes both themes, four primary-screen window sizes, three settings window sizes, form/overlay geometry, keyboard focus, theme persistence, report controls, update states, export failures, sync failures and 100,000-row search.
- Production frontend and self-contained engine builds passed. No new dependencies or credentials are embedded in the build.
- Final packaged app: all 16 lifecycle checks passed, including import, backup/restore, single instance, renderer isolation, authenticated loopback, encrypted settings and theme persistence. No renderer errors were recorded.
- Final packaged recovery: locked-vault startup, accessible Updates, protected preference writes, encrypted backup recovery and two clean restarts passed in isolated profiles.
- Final packaged stalled-shutdown regression passed: explicit quit took 8.3 seconds with an intentionally unresponsive shutdown reply; the engine stopped and the saved capture remained available after restart.
- Release manifest SHA-512 and installer version 2.5.2 were verified. The portable ZIP passed integrity checks. All six frontend build files matched the final source build in the engine, unpacked app and portable ZIP; local credential files were absent.
- Extractor: browser defaults and two-page/decoy-grid fixtures passed (two checks); this used intercepted test pages, not a successful live portal capture.
- Local installation exited successfully. The installed native app reports 2.5.2, reads all 7,257 real Sheet orders and recovered 35 captures through the saved connection test. The next capture is preview41. The four original CSV/XLSX capture exports were byte-for-byte unchanged.
- Native review verified Overview accents, Daily metric alignment, Monthly picker/export alignment, Settings tabs, current update status without downgrade, collapsed icon theme selection, Light/System appearance and Quick Actions focus/dismissal. The app was left open in System appearance.

## UI and control-flow review coverage

| Area | Review and verification |
| --- | --- |
| Main screens | Overview, Data Sheets, Daily Orders, Monthly report, Changes, Captures and Activity in Light and Dark; 1280×800, 1440×900, 1920×1080 and 640×900 viewports; no unintended page overflow. |
| Settings | Connections, Workspace and Updates at 1440×900, 1280×620 and 640×620; dialog bounds, scrolling, input visibility and footer geometry. |
| Navigation | Expanded and collapsed sidebar, selected states, icon theme menu, capture search and retained selection. |
| Keyboard and dialogs | Quick Actions initial focus, focus return, Escape, theme arrow/Home/End navigation, menu dismissal and saved preferences. |
| Reports | Daily metric padding and baselines; month/export control alignment and narrow-window wrapping; selected reporting period and chart drilldowns. |
| Data controls | Search, sorting, column filters, order inspector, saved views, pagination, bulk selection and literal CSV field handling. |
| Failures | Theme-save and preference-save failures, failed exports with retry, connection failure, interrupted sync guidance, failed SLA edits, update gates and unreadable vault recovery. |
| Large data | Paginated 100,000-order search and serial polling checks; final native lifecycle without renderer errors. |

These checks cover the implemented changes and their connected workflows. External portal uptime and every possible production input cannot be guaranteed by a local QC run.

## Operational notes

This is the 2.5.2 build on the `tv-tracker` branch. Release publication follows build/test validation. No Windows signing certificate is configured; automatic publication retains its signing gate. An explicitly requested manual release follows the existing distribution process and must clearly state its unsigned status.

The real local profile has a working Google Sheets connection but no saved TitleVision username/password. A read-only check of 42 authorized Tv Tracker profiles and 37 vault files found no real credentials to recover. Re-enter these in Connections and save before live queue extraction. Google Sheets reporting and capture-number recovery were verified independently. A successful live TitleVision capture was not claimed; it also depends on portal availability. Missing local credentials are not embedded in, or supplied by, a distributed installer.

The local upgrade backup is in the ignored `.desktop-build/local-upgrade-2.5.2-backup` directory. Keep that private: it contains saved workspace data and encrypted connection files. Cloud backups and source/installer archives serve different purposes; the source archive excludes local captures and credential files.
