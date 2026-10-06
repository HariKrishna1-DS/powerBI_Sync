# Tv Tracker release and deployment policy

## Distribution

The owner selected the no-purchase distribution route used for 2.5.3 and 2.6.0.
`desktop/distribution-policy.json` makes that a version-independent policy. A
Windows installer may have a valid Authenticode signature or be unsigned.
Invalid, untrusted, damaged and unrecognized signature results fail publication.
Unsigned releases disclose the unknown-publisher warning. A checksum checks
download integrity; it does not provide a verified publisher identity.

The updater retains its fixed GitHub repository, SHA-512 download verification,
stable-only updates, downgrade prevention, explicit restart/install and
pre-install backup. No certificate-validation override was added to the client.

## Publication

Pushing `tv-tracker` builds and tests the candidate without publishing it.
After live acceptance, run **Tv Tracker desktop release** on `tv-tracker` with
`publish_release` enabled. This deliberately separates automatic tests from
the maintainer's decision that the candidate is suitable for clients.

The workflow creates a draft, uploads the installer, blockmap, feed, portable
ZIP, source ZIP and SHA256SUMS.txt, downloads the hosted assets and compares
every asset with the validated build before publishing. Any failure leaves the
draft unpublished. Existing public version tags are never replaced.

## Required acceptance record

Record the commit, version, exact installer hash, test machine/Windows version,
time, result and recovery evidence for each item:

1. Complete and incomplete portal capture with current live pagination.
2. Publication/source switching and charts in an authorized representative
   workbook; verify no unrelated tabs or custom fields are lost.
3. Two cooperating installations: only the designated writer writes. Stop the
   old writer before a deliberate transfer. The protocol is not a distributed
   transaction against manual edits or older software; Google permissions are
   the external security boundary.
4. Install the exact candidate over 2.6.0 in an isolated test installation;
   confirm captures, connections, settings and report source survive. Verify
   rollback/recovery using the resulting pre-update backup.
5. Sleep/resume, internet loss, portal failure and repeated retry on the target
   workstation; supplement deterministic tests with an observed sustained run.
6. Keyboard, screen-reader and supported Windows display scaling checks.
   Automated axe checks complement these checks; they do not certify them.
7. Verify the existing service-account connection and permissions. The owner
   explicitly deferred rotation and requested compatibility with valid existing
   keys; rotation is not a version-specific updater prerequisite. Track the
   exposed-key risk until the replacement is imported and verified, then revoke
   the old key after dependent installations are migrated. Keep workbook access
   restricted to intended users.
8. Confirm recovery archives have protected storage and an independent copy.
   Version 2.7.0 encrypts desktop exports with a user-supplied password and
   automatic safety copies with Windows current-user protection. Existing ZIPs
   require the explicit **Protect older backups** action. Export a portable
   backup to a second drive: Windows-bound copies alone do not cover loss of
   the machine or Windows account. Cloud cleanup retains the five newest
   recorded generated-backup operations and archives eligible older tabs before
   deletion. Raw capture history and unrecognized tabs remain untouched.

Do not mark an unperformed check as passed. A release can remain a local
candidate while account access or representative-machine evidence is missing.

## 2.7.0 candidate checkpoint — 6 October 2026

Backend (232), desktop (26) and browser (63) tests passed. Real isolated Google
Sheets publishing, empty-category clearing, writer conflict rejection, and
encrypted cloud archive/restore passed, including formulas and notes. Packaged
lifecycle, report, corrupt-vault recovery and stalled-engine shutdown passed.
A 303-second packaged run completed 18 cycles with two simulated renderer
network interruptions and no renderer errors or capture loss. These checks do
not establish multi-day reliability or Windows sleep/resume behavior.

The owner created a replacement Google key, but its downloaded JSON is not yet
available locally; the supplied service_account.json still contains the old key.
The app has not been migrated and the old key has not been revoked. Existing
valid keys remain compatible with 2.7.0 without bypassing Google validation. Current
saved settings also lack portal credentials, so the attempted live capture did
not reach the portal. The 2.6.0 updater downloaded the exact 2.7.0 installer over
an isolated loopback feed with matching SHA-512. Simulated installer handoff
failure recovered the engine, and 2.7.0 reopened the profile with captures,
encrypted connections and preferences preserved. Actual NSIS upgrade and hosted-asset verification remain
release gates. Pushing this source candidate does not activate client updates.
