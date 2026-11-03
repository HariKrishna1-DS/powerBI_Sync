# Tv Tracker 1.0.14

Released November 3, 2026.

- TypingModule tasks with Task Status Available (including portal variants such as Avavilable) map to Typing in Progress in SLA Status and queue extraction sync.
- Typing in Progress status reasoning records Available task status when applied.
- Expiration calculation includes fallback to capture-time anchors for yearless deadline timestamps, ensuring consistent SLA category classification across raw queue exports.

Local captures and encrypted connections are retained. Existing previews retain their original captured fields.

The Windows installer follows the existing unsigned release process. Windows may show an unknown-publisher warning.
