# Tv Tracker 1.0.9

Date: 21 October 2026. Branch: `tv-tracker-app`.

## ETA assignment in SLA Status

ETA Comments now recognize the complete words Abstract, abstractor and abstractors, ignoring case. EOD or sooner also counts as abstractor evidence when the comment does not name an abstractor.

The date immediately before EOD or sooner determines the assignment group:

- An ETA date matching today in India time goes to **Need to Assign ABS**.
- Any other ETA date, or no valid date beside EOD/sooner, goes to **Assign to ABS**.

Received and fee-approved dates elsewhere in the comment do not affect this comparison. Dates without a year use the current year. For example, an ETA of 10/22 EOD or sooner goes to Assign to ABS on October 21, Need to Assign ABS on October 22, and Assign to ABS on October 23.

Selected saved previews recheck the rule against today without rewriting the capture. Duplicate task rows count each Order Number once using the strongest queue rule. Status Reason explains the comparison. Extraction, SLA summaries, Excel exports and Google Sheets use the same assignment rule.

Completion evidence, specific queue rules and manual SLA status edits retain priority. Existing connections, captures, imported files, selected-preview reporting and backup compatibility remain available.

## Windows release

This release continues the existing unsigned Windows distribution. Windows may show an unknown-publisher warning. The release workflow verifies the installer, portable ZIP, source ZIP, update metadata and checksums before publication.
