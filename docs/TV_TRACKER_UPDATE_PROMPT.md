# Tv Tracker: connection setup and desktop updates

## Implementation prompt

Act as a senior Windows desktop engineer maintaining this repository. Inspect the existing Electron main/preload, React settings, Python engine, encrypted configuration, packaging, tests, and Git history before editing. Preserve the Tv Tracker desktop architecture and branch segregation.

Deliver two working outcomes:
1. Diagnose the first-capture Google Sheets connection error. Validate the supplied spreadsheet and locally supplied service-account key with read-only requests. Configure the installed app through its encrypted settings, preserve existing credentials and local data, and verify that preview numbering resumes after the highest existing preview. Never bypass recovery to hide a connection failure or write production data during diagnostics.
2. Provide an explicit Windows update workflow using electron-updater and GitHub Releases for HariKrishna1-DS/powerBI_Sync. Users must be able to check, download, see progress/errors, and choose when to restart/install. Only release tested, versioned installers from the desktop branch. Do not install raw commits, embed GitHub tokens, accept renderer-controlled update feeds, silently download/install, downgrade, or interrupt active capture/sync work.

Before implementation, describe the findings, affected files, dependencies, and risks. Adapt existing services and UI instead of introducing duplicate infrastructure. Keep the existing Windows application/profile identity so upgrades retain encrypted credentials, captures, schedules, and preferences. Use narrow validated IPC, integrity verification, and graceful engine shutdown. Handle offline requests, missing releases, repeated clicks, retries, and development mode explicitly.

Add CI that runs meaningful tests and builds release artifacts on a desktop version bump, stages all updater assets before publication, and never overwrites an existing published version. Document the maintainer release steps and the one-time manual upgrade required for older versions without an updater.

Verify backend recovery and failures, updater transitions and active-job guards, frontend compilation, real packaged Electron lifecycle, and clean source/installer packaging. Keep private keys, passwords, tokens, and user captures out of logs, commits, documentation, and archives. Report what was changed, exact test outcomes, configuration actually verified, deliverable paths, and anything not verified. Do not claim end-to-end installation testing unless a real update was installed.

## Implementation plan

- Confirmed: the service account opens Production_data and read-only recovery finds 29 previews through preview34. Diagnose and repair the installed profile configuration without replacing user data.
- Add `desktop/updater.cjs`, narrow main/preload commands, and an Updates settings section. Use electron-updater 6.8.9 with the existing NSIS installer and stable app ID.
- Improve the engine's recovery error and connection test so setup verifies preview recovery and reports actionable failures.
- Add desktop release CI, updater/recovery tests, release documentation, and version 2.2.0 packaging.
- Risks: Windows encryption must remain tied to the existing profile; installation must wait for jobs to finish; unsigned installers may display Windows reputation prompts; existing 2.1.0 users need one manual installer run. Cloud writes are outside connection diagnostics.

Prompt structure follows [OpenAI's prompting guidance](https://developers.openai.com/api/docs/guides/prompt-engineering). Update design follows [electron-builder's supported update workflow](https://www.electron.build/docs/features/auto-update/).
