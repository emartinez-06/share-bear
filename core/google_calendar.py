"""
Google Calendar API: weekly preset pickup slots in the app, events.insert when a user books.

Requires a service account JSON and a destination calendar shared to that service account.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/calendar']


def is_pickup_calendar_configured() -> bool:
    has_key_json = bool((getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY_JSON', '') or '').strip())
    has_key_path = bool((settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH or '').strip())
    return bool(
        (has_key_json or has_key_path)
        and settings.GOOGLE_SLOT_SOURCE_CALENDAR_IDS
    )


def _get_credentials() -> service_account.Credentials:
    key_json = (getattr(settings, 'GOOGLE_SERVICE_ACCOUNT_KEY_JSON', '') or '').strip()
    if key_json:
        try:
            payload = json.loads(key_json)
        except json.JSONDecodeError as e:
            raise RuntimeError('GOOGLE_SERVICE_ACCOUNT_KEY_JSON is invalid JSON') from e
        return service_account.Credentials.from_service_account_info(payload, scopes=SCOPES)
    path = (settings.GOOGLE_SERVICE_ACCOUNT_KEY_PATH or '').strip()
    if not path:
        raise RuntimeError('Google service-account credentials are not configured')
    return service_account.Credentials.from_service_account_file(path, scopes=SCOPES)


def get_calendar_service():
    creds = _get_credentials()
    creds.refresh(Request())
    return build('calendar', 'v3', credentials=creds, cache_discovery=False)


def _destination_calendar_id() -> str:
    ids = settings.GOOGLE_SLOT_SOURCE_CALENDAR_IDS
    return ids[0] if ids else ''


def _parse_hhmm(s: str) -> time:
    parts = (s or '').strip().split(':')
    h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    return time(h, m)


def _row_is_hourly(sl: dict) -> bool:
    v = sl.get('hourly')
    return v is True or v == 1 or str(v).lower() == 'true'


def _generate_all_preset_instances(
    *,
    time_min: datetime,
    time_max: datetime,
) -> list[tuple[datetime, datetime]]:
    """Return (start, end) aware datetimes in the configured local timezone."""
    tz_name = getattr(settings, 'GOOGLE_PICKUP_TIMEZONE', 'America/Chicago') or 'UTC'
    tz = ZoneInfo(tz_name)
    defs: list[dict] = list(getattr(settings, 'PICKUP_WEEKLY_SLOT_DEFINITIONS', []) or [])
    out: list[tuple[datetime, datetime]] = []
    d: date = time_min.astimezone(tz).date()
    end_date = time_max.astimezone(tz).date()
    while d <= end_date:
        wk = d.weekday()
        for sl in defs:
            try:
                if int(sl.get('weekday', -1)) != wk:
                    continue
                if _row_is_hourly(sl):
                    t_first = _parse_hhmm(str(sl.get('first', '09:00')))
                    t_last = _parse_hhmm(str(sl.get('last_start', '17:00')))
                    cursor = datetime.combine(d, t_first, tzinfo=tz)
                    last_start = datetime.combine(d, t_last, tzinfo=tz)
                    if last_start < cursor:
                        continue
                    while cursor <= last_start:
                        slot_end = cursor + timedelta(hours=1)
                        if slot_end <= cursor:
                            break
                        if slot_end < time_min.astimezone(tz):
                            cursor += timedelta(hours=1)
                            continue
                        if cursor > time_max.astimezone(tz):
                            break
                        out.append((cursor, slot_end))
                        cursor += timedelta(hours=1)
                    continue
                t0 = _parse_hhmm(str(sl.get('start', '09:00')))
                t1 = _parse_hhmm(str(sl.get('end', '09:30')))
            except (TypeError, ValueError) as e:
                logger.warning('Invalid weekly slot row %r: %s', sl, e)
                continue
            start = datetime.combine(d, t0, tzinfo=tz)
            end = datetime.combine(d, t1, tzinfo=tz)
            if end <= start:
                continue
            if end < time_min.astimezone(tz):
                continue
            if start > time_max.astimezone(tz):
                continue
            out.append((start, end))
        d += timedelta(days=1)
    return out


def _slot_taken_in_db(start: datetime) -> bool:
    from core.models import AIQuote

    return (
        AIQuote.objects.filter(pickup_starts_at=start)
        .exclude(google_event_id='')
        .exclude(google_event_id__isnull=True)
        .exists()
    )


def _same_instant(a: datetime, b: datetime) -> bool:
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return abs((a - b).total_seconds()) < 1.0


def _time_bounds_for_listing() -> tuple[datetime, datetime]:
    time_min = datetime.now(timezone.utc)
    time_max = time_min + timedelta(
        days=int(getattr(settings, 'GOOGLE_PICKUP_SLOT_DAYS_AHEAD', 30) or 30)
    )
    return time_min, time_max


def resolve_available_preset_slot(
    calendar_id: str,
    start: datetime,
    end: datetime,
) -> tuple[datetime, datetime] | None:
    """
    If (start, end) matches a generated preset in the next window, return canonical (s, e) from
    the generator; otherwise None. If the slot is already booked in the DB, return None.
    """
    if not is_pickup_calendar_configured() or calendar_id != _destination_calendar_id():
        return None
    time_min, time_max = _time_bounds_for_listing()
    for s, e in _generate_all_preset_instances(time_min=time_min, time_max=time_max):
        if _same_instant(s, start) and _same_instant(e, end):
            if _slot_taken_in_db(s):
                return None
            return s, e
    return None


def make_slot_post_key(calendar_id: str, start: datetime, end: datetime) -> str:
    payload = {
        'c': calendar_id,
        's': start.isoformat(),
        'e': end.isoformat(),
    }
    raw = json.dumps(payload, sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


def parse_slot_post_key(key: str) -> tuple[str, datetime, datetime] | None:
    if not (key or '').strip():
        return None
    pad = '=' * (-len(key) % 4)
    try:
        raw = base64.urlsafe_b64decode(key + pad)
        d = json.loads(raw.decode())
        c = d.get('c') or ''
        s_raw = d['s'].replace('Z', '+00:00') if isinstance(d['s'], str) else d['s']
        e_raw = d['e'].replace('Z', '+00:00') if isinstance(d['e'], str) else d['e']
        s = datetime.fromisoformat(s_raw)
        e = datetime.fromisoformat(e_raw)
        if not c:
            return None
        return c, s, e
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        logger.error('Invalid slot key: %s', e)
        return None


def list_available_pickup_slots(
    *,
    time_min: datetime | None = None,
    time_max: datetime | None = None,
) -> list[dict]:
    """
    Preset weekly slots in the app; excludes slots already booked (DB) or in the past.
    Google Calendar is empty until a user books; we create events on insert.
    """
    if not is_pickup_calendar_configured():
        return []
    cal_id = _destination_calendar_id()
    if not cal_id:
        return []

    if time_min is None:
        time_min = datetime.now(timezone.utc)
    if time_max is None:
        days = int(getattr(settings, 'GOOGLE_PICKUP_SLOT_DAYS_AHEAD', 30) or 30)
        time_max = time_min + timedelta(days=days)
    if time_min.tzinfo is None:
        time_min = time_min.replace(tzinfo=timezone.utc)
    if time_max.tzinfo is None:
        time_max = time_max.replace(tzinfo=timezone.utc)

    instances = _generate_all_preset_instances(time_min=time_min, time_max=time_max)
    title = (getattr(settings, 'PICKUP_EVENT_TITLE', 'SHARE Bear — Item pickup') or 'Pickup').strip()

    out: list[dict] = []
    for start, end in instances:
        if end <= time_min:
            continue
        if _slot_taken_in_db(start):
            continue
        out.append(
            {
                'calendarId': cal_id,
                'summary': title,
                'htmlLink': '',
                'start': start,
                'end': end,
                'postKey': make_slot_post_key(cal_id, start, end),
            }
        )
    out.sort(key=lambda x: (x.get('start') or datetime.min.replace(tzinfo=timezone.utc)))
    return out


# Backwards compatibility for tests / imports
def list_candidate_slots(**kwargs) -> list[dict]:
    return list_available_pickup_slots(**kwargs)


def get_event(calendar_id: str, event_id: str) -> dict | None:
    if not is_pickup_calendar_configured():
        return None
    try:
        service = get_calendar_service()
        return (
            service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )
    except HttpError as e:
        logger.error('events.get failed: %s', e)
        return None


def _parse_google_datetime(
    t: dict,
    *,
    event_tz: str | None,
) -> datetime | None:
    if not t:
        return None
    if 'dateTime' in t:
        s = t['dateTime']
        if s.endswith('Z'):
            s = s[:-1] + '+00:00'
        return datetime.fromisoformat(s)
    if 'date' in t:
        d = t['date']
        tz = ZoneInfo(event_tz or 'UTC')
        return datetime.combine(
            datetime.strptime(d, '%Y-%m-%d').date(), datetime.min.time(), tzinfo=tz
        )
    return None


def event_start_end_aware(event: dict) -> tuple[datetime | None, datetime | None]:
    cal_tz = getattr(settings, 'GOOGLE_PICKUP_TIMEZONE', 'America/Chicago') or 'UTC'
    s = _parse_google_datetime(event.get('start') or {}, event_tz=cal_tz)
    e = _parse_google_datetime(event.get('end') or {}, event_tz=cal_tz)
    return s, e


def _event_datetime_for_google_api(dt: datetime, tz_name: str) -> dict[str, str]:
    """dateTime is wall clock in the given timeZone (no offset) per Calendar API style."""
    tz = ZoneInfo(tz_name)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)
    return {
        'dateTime': local.strftime('%Y-%m-%dT%H:%M:%S'),
        'timeZone': tz_name,
    }


def create_pickup_event(
    calendar_id: str,
    start: datetime,
    end: datetime,
    *,
    user_email: str,
    user_label: str,
    quote_ids: list[int],
    item_names: list[str],
) -> dict | None:
    """
    Create a new Google Calendar event (slot was empty in Calendar until this insert).
    """
    if not is_pickup_calendar_configured():
        return None
    tz = getattr(settings, 'GOOGLE_PICKUP_TIMEZONE', 'America/Chicago') or 'UTC'
    qids = ','.join(str(i) for i in quote_ids)
    inames = ' | '.join(item_names) if item_names else ''
    desc = (
        f'SHARE Bear buy-back pickup (scheduled in app).\n'
        f'User: {user_label}'
        + (f" <{user_email}>\n" if user_email else '\n')
        + f'Quote IDs: {qids}\n'
        f'Items: {inames}\n'
    )
    title = (getattr(settings, 'PICKUP_EVENT_TITLE', 'SHARE Bear — Item pickup') or 'Pickup').strip()
    body: dict = {
        'summary': title,
        'description': desc,
        # So htmlLink is viewable to the booking user without calendar-owner-only access
        'visibility': 'public',
        'start': _event_datetime_for_google_api(start, tz),
        'end': _event_datetime_for_google_api(end, tz),
        'extendedProperties': {
            'private': {
                'shareBearBooked': '1',
                'shareBearQuoteIds': qids,
            }
        },
    }
    if user_email:
        body['attendees'] = [
            {'email': user_email, 'responseStatus': 'needsAction'},
        ]
    try:
        service = get_calendar_service()
        return (
            service.events()
            .insert(calendarId=calendar_id, body=body, sendUpdates='none')
            .execute()
        )
    except HttpError as e:
        status = getattr(getattr(e, 'resp', None), 'status', None)
        logger.error('events.insert failed (status=%s): %s', status, e)
        if status == 403:
            raise RuntimeError(
                'Google Calendar permission denied (403). Share the calendar with the service account and grant event edit access.'
            ) from e
        if status == 404:
            raise RuntimeError(
                'Google Calendar ID not found (404). Check GOOGLE_SLOT_SOURCE_CALENDAR_IDS.'
            ) from e
        raise RuntimeError('Google Calendar booking failed. Please try again.') from e


def verify_slot_still_available(calendar_id: str, start: datetime, end: datetime) -> bool:
    """True if the slot is a valid, still-available preset (matches list_available_pickup_slots)."""
    return resolve_available_preset_slot(calendar_id, start, end) is not None
