# Tv Tracker 2.5.0

The desktop workspace now uses a shared teal visual system with warm light surfaces, a dark theme, and a collapsible library sidebar. Settings has one permanent entry above Appearance; Ctrl+, and Quick actions still open it.

## Workspace changes

- Search saved captures by name, date or row count. The selected capture and latest capture are distinct. A capture picker keeps the library available when navigation collapses.
- Switch Data Sheets between All Products, Full Title and Remaining Products. Search, filters, sorting, saved views, pagination and exports retain their existing data contracts. Choose All columns to inspect additional fields.
- Overview restores analytical charts, accessible record drilldowns and custom grouping/format controls. Drilldowns use the actual filtered records. Advanced controls stay behind disclosure buttons.
- Daily reports identify capture sequences. Monthly reports identify the month, production freshness and percentage denominators. Clarification is a production metric; only SLA metrics filter SLA results.
- Extract Queue is the primary action. Sync to Sheets, imports, exports and IST scheduling remain available. Scheduling and product preferences confirm successful writes before updating saved-state feedback.
- Native dialogs support Escape, focus containment and return to the opening control. Loading a report retains the surrounding workspace shell. Existing search and filters survive background data refreshes.

## Reliability and compatibility

This release includes the first-monthly-check correction prepared in 2.4.2: a recently restarted Windows PC no longer delays its initial monthly maintenance check for an hour. Rollover retains its preview and confirmation requirements.

No dependencies, credentials, service endpoints or storage services were added. The desktop vault accepts one new Boolean preference, `sidebarCollapsed`. Existing Windows application identity, user-data directory, encrypted connections, captures and update feed remain compatible.

Styles are consolidated into `style.css`, with shared palette and size tokens in `tokens.css`. The previous layered `desktop.css` and `studio.css` overrides are removed. Synthetic data used by UI tests does not enter production storage.

## Verification

The regression suite covers 100,000-row searching, retained production rows, live refresh, failed syncs, Excel/CSV exports, monthly maintenance, SLA editing and update controls. Additional checks cover capture search, collapsed navigation, sheet groups, sorting, filtered chart drilldowns, keyboard focus, and failed preference/schedule writes.

All seven primary screens are checked in light and dark themes at 1280×800, 1440×900, 1920×1080 and 640×900. Screenshot evidence uses synthetic orders. Build checks also cover updater integrity, vault preservation, packaged lifecycle, and isolated connection recovery. Release publication depends on the verified build results.

## Upgrade

Use **Settings → Updates → Check for updates**, download the offered version, then choose **Restart & install** after active work finishes. First-time users can install the Windows `.exe` from the GitHub release.

The manually published build is unsigned because a Windows signing identity is not configured. Automatic publication remains gated on a valid certificate. Live TitleVision extraction still requires the user's valid saved connection and a responsive TitleVision server; synthetic UI tests do not establish live service availability.
