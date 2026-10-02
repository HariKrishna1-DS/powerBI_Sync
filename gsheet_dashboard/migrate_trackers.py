"""Initialize default trackers and sync retained local captures, in chronological order."""
import time
from datatrace_sync import BASE_DIR
from order_reporting import automatic_sync_frame
from preview_store import PreviewStore
from tracker_sync import sync_trackers


def main():
    store = PreviewStore(BASE_DIR / 'previews')
    sync_trackers(on_progress=lambda message: print(message, flush=True))
    for number in store.pending_syncs():
        frame, _ = automatic_sync_frame(store.get(number), store=store)
        for attempt in range(3):
            try:
                sync_trackers(frame, on_progress=lambda message: print(message, flush=True))
                store.mark_synced(number)
                report = frame.attrs.get('pass_report', {})
                print(f"preview{number}: added={report.get('added', 0)}, updated={report.get('updated', 0)}, unchanged={report.get('unchanged', 0)}", flush=True)
                break
            except Exception as exc:
                if attempt == 2:
                    store.mark_failed(number, str(exc))
                    raise
                time.sleep(5 * (attempt + 1))


if __name__ == '__main__':
    main()
