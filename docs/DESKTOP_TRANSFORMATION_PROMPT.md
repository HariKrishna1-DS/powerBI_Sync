# DataTrace Studio — desktop transformation prompt

## Objective
Act as a senior desktop application engineer and product designer. Transform the existing DataTrace Workspace repository into a polished Windows desktop application called DataTrace Studio. Implement and validate the application, rather than stopping at a proposal. It must launch locally without Render, a hosted backend, or a separately installed Python or Node runtime.

## Context and constraints
- Reuse the working React/Vite interface, Python reporting engine, TitleVision extractor, and Google Sheets reconciliation rules where practical.
- Google Sheets remains the production source of truth. Do not reintroduce PostgreSQL. Local SQLite and files are for previews, retry queues, settings, and an explicitly dated offline copy of production data.
- Preserve manual tracker fields, stable preview numbering, append-only history, idempotent retries, missing orders, SLA rules, exports, and scheduling. An order disappearing from a capture does not mean it was completed.
- Preserve existing user files and secrets. Package application code separately from writable per-user data. Never bundle credentials or live customer exports.
- Windows is the initial supported platform. Internet is required for TitleVision extraction and Google Sheets synchronization; the application itself and saved data must remain usable without hosting or an active internet connection.

## Required outcome
1. Deliver a native desktop window, single-instance behavior, reliable local backend startup, graceful shutdown, and clear startup-failure recovery. Use an installer and a portable release archive. Reuse installed Microsoft Edge or Chrome for extraction and explain any browser prerequisite clearly.
2. Provide an in-app Connections screen for spreadsheet and tracker configuration, TitleVision credentials, and importing a Google service-account file. Encrypt secrets with the operating system credential protection API. Never return private keys or saved passwords to the renderer. Validate settings before saving and offer a connection check.
3. Store writable data in the user's application-data directory. Add backup export and document recovery. Show connection status, pending work, and the last successful refresh. Display cached production records with an explicit offline timestamp. Never fabricate live results or silently substitute raw previews for production reports.
4. Keep the renderer sandboxed, disable Node integration, isolate its context, validate IPC senders and payloads, constrain navigation and external links, and authenticate the loopback backend with a per-launch secret. Bind only to loopback. Do not expose the service on the network.
5. Create a coherent desktop interface: restrained typography and spacing, legible tables, clear visual hierarchy, useful empty/loading/error states, accessible dialogs, visible focus, keyboard shortcuts, and responsive layouts. Use local assets and fonts. Every visible control must work.
6. Reduce unnecessary network requests, avoid overlapping polling, use bounded caching and pagination, split large frontend bundles, and keep expensive work outside the UI thread. Measure startup and representative responsiveness; report actual observations rather than unsupported performance claims.
7. Produce reproducible build scripts, dependency lockfiles, setup and troubleshooting documentation, and release artifacts. Remove Render from the default product workflow. Preserve optional development workflows where useful.

## Execution workflow
Inspect the repository and its tests first. Explain the chosen architecture and significant tradeoffs briefly. Implement in coherent steps. Run targeted tests while developing, then the applicable regression suite, frontend build, desktop security/lifecycle checks, and a real packaged-app smoke test. Inspect the actual interface and correct material usability issues. Do not publish, push, or sign with unavailable credentials.

## Acceptance checks
- A packaged Windows build opens without a terminal or a separately installed Python/Node runtime.
- A second launch focuses the original window; quitting releases the backend and its child processes.
- First launch without credentials is useful and explains the next step. Bad credentials and offline conditions produce actionable states.
- Secrets are encrypted on disk, omitted from exports/logs, and unavailable through settings reads. Unauthenticated backend requests and untrusted IPC callers are rejected.
- Data survives restart. Production caching is identified as stale when offline; failed sync keeps its retryable local preview.
- Existing reconciliation, reports, import/export, comparison, SLA, and scheduling invariants pass regression tests.
- The interface works with keyboard navigation and common desktop window sizes. There are no browser console errors in tested flows.
- Installer/portable output and source archive are created and checked. Document anything requiring real credentials, signing certificates, or a different machine to verify.

## Final response
Lead with what was actually delivered. Link the executable/installer, source archive, and this prompt. Summarize the meaningful UX, reliability, and performance changes and the tests that passed. State remaining validation limits precisely. Do not claim zero bugs, universal performance guarantees, or successful live integration without evidence.

## Prompt design reference
This prompt makes the outcome, repository context, constraints, success criteria, and verification requirements explicit, following [OpenAI's prompt engineering guidance](https://developers.openai.com/api/docs/guides/prompt-engineering).
