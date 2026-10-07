# Tv Tracker 2.8.0 — coordinated shared workspaces

This version adds a Supabase-backed workspace for multiple operators. Each PC keeps its local captures and retry queue; shared operations use transactional sequencing, duplicate-safe receipts and version checks. One registered office PC processes captures and publishes Google Sheets reports.

- Shared Excel reporting sources, capacity targets, monthly setup/import/rollover and SLA corrections preserve canonical tracker orders and manual fields.
- Stale saves return a clear conflict instead of silently overwriting changes or repeatedly retrying inside PostgREST.
- Publishing stages and verifies reports, checks workbook capacity and retains the previous visible reports on failure. Quota/network errors retain their job identity and use bounded retry delays.
- Every admitted admin/manager has full application access, including team management and protected office-worker recovery. Individual sign-ins and audited membership grants preserve accountability; publishing remains coordinated through one office PC.
- Existing direct Google Sheets workflows remain available. Upgrading does **not** automatically migrate or activate a production workbook.

## Setup required for shared use

Follow [the ordered multi-PC deployment guide](https://github.com/HariKrishna1-DS/powerBI_Sync/blob/tv-tracker/docs/TV_TRACKER_MULTI_PC_DEPLOYMENT.md). Users need individual application sign-ins and membership in the same workspace; they do not need Supabase dashboard accounts. Only the office worker needs the Google service-account JSON. Never distribute a Supabase service-role key.

Stop older capture/publishing jobs on every PC before the owner reviews and seeds the production workbook. Keep the office worker running and awake. If it stops, accepted work waits safely until it resumes.

Review [the acceptance record](https://github.com/HariKrishna1-DS/powerBI_Sync/blob/tv-tracker/docs/TV_TRACKER_2_8_0_ACCEPTANCE.md) for completed checks and operational rollout gates. Valid existing Google keys remain compatible; a previously exposed key still needs owner-side rotation. Local workspace backups do not replace shared PostgreSQL backups.
