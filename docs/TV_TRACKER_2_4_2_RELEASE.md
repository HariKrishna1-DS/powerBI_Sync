# Tv Tracker 2.4.2

Fix the first automatic monthly maintenance check on a recently booted Windows computer. The hourly rate limit now applies only after an actual check; it no longer compares the system's initial monotonic uptime with an artificial zero timestamp.

The regression test simulates startup at 30 seconds of uptime, verifies that the initial month check creates missing empty monthly tabs and prepares a rollover preview without moving production rows, verifies that an immediate repeat is throttled, and verifies that checking resumes after an hour.

All 27 monthly production tests passed locally. Full desktop, interface, engine and packaged checks are required in the GitHub release workflow before publishing this patch. The existing 2.4.1 release remains immutable; 2.4.2 supersedes it after validation. The current distribution is unsigned because no Windows signing certificate is configured.
