"""Convert capture instants to TitleVision's US Central wall clock."""
from datetime import datetime
from zoneinfo import ZoneInfo

PORTAL_TIMEZONE = ZoneInfo('America/Chicago')


def capture_time(value):
    from monthly_production import local_datetime
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).strip().replace('Z', '+00:00'))
    except ValueError:
        return local_datetime(value)
    # Unzoned portal/import values already represent the source wall clock.
    return parsed.astimezone(PORTAL_TIMEZONE).replace(tzinfo=None) if parsed.tzinfo else parsed
