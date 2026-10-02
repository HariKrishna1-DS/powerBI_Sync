"""Reconcile full-row status colors, including Free Site, without editing values."""
from datatrace_sync import target_worksheet
from tracker_formatting import ensure_tracker_formatting


def main():
    book, _ = target_worksheet()
    count = ensure_tracker_formatting(book)
    print(f'Applied {count} formatting requests; worksheet values unchanged.')


if __name__ == '__main__':
    main()
