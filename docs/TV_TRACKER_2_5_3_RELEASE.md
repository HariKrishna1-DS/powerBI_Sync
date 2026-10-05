# Tv Tracker 2.5.3

Monthly views now use the Full Search production tracker's exact column order,
including its custom columns. Extra raw queue fields stay in capture history.
Existing monthly views are backed up before their schema is replaced.

Saved captures has a dedicated scrollable area. Navigation and settings remain
fixed; shorter windows reduce navigation spacing before reducing the capture
area. Capture rows retain their two-line labels, selection state and search.

## Completion and SLA rule

For an order present in a saved preview and absent from a subsequent valid
preview, the first missing preview's timestamp becomes its Out Time and its
status becomes Completed and Delivered. Repeated syncs retain that timestamp.
Cancelled and suspended rows are excluded. Existing precise manual Out Time
values are retained. A returning order reopens when its Out Time matches an
inferred transition in the archive; unrelated manual completion times remain.

Only completed rows with valid Out Time and SLA Expiration receive Free Site:
On Time when Out Time is at or before the deadline, otherwise Missing. Out Time
before In-Time is invalid and stays unclassified. A relative SLA countdown is
anchored to the last capture containing the order, not the time of repair.

Empty, duplicate-ID, invalid-time and nonchronological captures break the
comparison sequence. These snapshots cannot close all outstanding orders.
Missing orders that were never observed in saved history are not assigned an
invented completion time. Explicit monthly archive tabs remain unchanged.

Inference records the first *observed absence*, not a server-certified delivery
event. Captures must cover the same complete queue; arbitrary filtered imports
cannot establish this guarantee. Failed extraction does not save a capture.

## Verification

Backend regressions cover exact schemas, atomic backups, repeated-sync recovery,
first disappearance, return and subsequent disappearance, terminal exceptions,
manual timestamps, invalid snapshots, IST capture offsets and deadline equality.
UI checks cover 35 saved captures at 500, 620, 720 and 900 pixels tall, independent
scrolling, pinned controls, search and selection, plus existing desktop workflows
and both appearance themes.

Local verification passed: 186 backend tests, 20 desktop tests and 49 browser UI
tests. Packaged lifecycle, encrypted-settings recovery and stalled-engine shutdown
checks passed; the stalled shutdown completed in 7.5 seconds. The live Sheet
repair retained all 7,257 production rows, corrected 625 rows and verified both
26-column monthly views (149 Full Search rows, 371 Remaining rows). Raw history
and unrelated tracker fields were checked unchanged after the write.

No dependencies or new configuration are required. Existing credentials and
capture history stay in the user's local profile. Windows signing remains
dependent on the repository's existing certificate configuration.
