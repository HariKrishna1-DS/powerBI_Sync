# Tv Tracker 2.4.2

This patch was prepared but not published separately. Its correction is included in the 2.5.0 workspace release.

Fix the first automatic monthly maintenance check on a recently booted Windows computer. The hourly rate limit now applies only after an actual check; it no longer compares the system's initial monotonic uptime with an artificial zero timestamp.

The regression test simulates startup at 30 seconds of uptime, verifies that the initial month check creates missing empty monthly tabs and prepares a rollover preview without moving production rows, verifies that an immediate repeat is throttled, and verifies that checking resumes after an hour.

All 27 monthly production tests passed locally. Full desktop, interface, engine and packaged checks are required in the GitHub release workflow. The existing 2.4.1 release remains immutable. The current distribution is unsigned because no Windows signing certificate is configured.
