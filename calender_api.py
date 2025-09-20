# calendar_api.py
from dataclasses import dataclass
from typing import List, Optional, Tuple
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from dateutil import parser as date_parser
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import uuid
import logging
import math

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@dataclass
class Slot:
    """Represents a concrete time window (ISO strings include timezone offset)."""
    start_iso: str
    end_iso: str
    tz: str


def get_calendar_service(credentials):
    """
    Build a Google Calendar API service object.
    `credentials` should be a google.oauth2.credentials.Credentials object.
    """
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def _iso_to_dt(iso: str) -> datetime:
    return date_parser.isoparse(iso)


def _dt_to_iso(dt: datetime) -> str:
    # returns ISO with offset e.g. 2025-09-21T15:00:00-04:00
    return dt.isoformat()


def is_free(cal_service, slot: Slot) -> bool:
    """
    Return True if the calendar 'primary' has no busy blocks between slot.start_iso and slot.end_iso.
    Uses FreeBusy API.
    """
    try:
        body = {
            "timeMin": slot.start_iso,
            "timeMax": slot.end_iso,
            "timeZone": slot.tz,
            "items": [{"id": "primary"}],
        }
        resp = cal_service.freebusy().query(body=body).execute()
        busy = resp.get("calendars", {}).get("primary", {}).get("busy", [])
        is_free = len(busy) == 0
        logger.debug("FreeBusy query: %s -> busy intervals: %s", body, busy)
        return is_free
    except HttpError as e:
        logger.exception("Calendar FreeBusy API error: %s", e)
        # Conservative: treat as not free when API fails (so we don't double-book)
        return False


def _merge_intervals(intervals: List[Tuple[datetime, datetime]]) -> List[Tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals_sorted = sorted(intervals, key=lambda x: x[0])
    merged = [intervals_sorted[0]]
    for start, end in intervals_sorted[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def suggest_slots(
    cal_service,
    *,
    anchor_iso: str,
    duration_min: int,
    days: int,
    working_start: str = "09:00",
    working_end: str = "18:00",
    tz: str = "America/Indiana/Indianapolis",
    max_suggestions: int = 3,
    step_minutes: int = 30,
) -> List[Slot]:
    """
    Return up to `max_suggestions` Slot objects after anchor_iso within the next `days`.
    Strategy:
      1. Compute overall search window (first working start -> last working end).
      2. Query freeBusy once for that window (more efficient).
      3. For each day, compute working window and find gaps >= duration_min that align to step_minutes (:00/:30).
      4. Return earliest matching slots.
    """
    tzinfo = ZoneInfo(tz)
    anchor_dt = _iso_to_dt(anchor_iso).astimezone(tzinfo)

    # Build per-day working windows
    start_date = anchor_dt.date()
    end_date = (anchor_dt + timedelta(days=days)).date()

    # overall range for freebusy query (start at first day's working_start, end at last day's working_end)
    def day_work_range(d: datetime.date):
        start_time = time.fromisoformat(working_start)
        end_time = time.fromisoformat(working_end)
        start_dt = datetime.combine(d, start_time).replace(tzinfo=tzinfo)
        end_dt = datetime.combine(d, end_time).replace(tzinfo=tzinfo)
        return start_dt, end_dt

    overall_start = day_work_range(start_date)[0]
    overall_end = day_work_range(end_date)[1]

    # Query freebusy for entire window
    try:
        fb_body = {
            "timeMin": _dt_to_iso(overall_start),
            "timeMax": _dt_to_iso(overall_end),
            "timeZone": tz,
            "items": [{"id": "primary"}],
        }
        fb_resp = cal_service.freebusy().query(body=fb_body).execute()
        busy_raw = fb_resp.get("calendars", {}).get("primary", {}).get("busy", [])
    except HttpError as e:
        logger.exception("FreeBusy API failure: %s", e)
        busy_raw = []

    # Convert busy_raw to list of (dt, dt) in tz
    busy_intervals = []
    for b in busy_raw:
        try:
            s = _iso_to_dt(b["start"]).astimezone(tzinfo)
            e = _iso_to_dt(b["end"]).astimezone(tzinfo)
            busy_intervals.append((s, e))
        except Exception:
            continue
    busy_intervals = _merge_intervals(busy_intervals)

    suggestions: List[Slot] = []

    # Helper to generate aligned start times between start_dt and end_dt
    def generate_aligned_starts(start_dt: datetime, end_dt: datetime):
        # round up start_dt to nearest step_minutes
        minute = (start_dt.minute // step_minutes) * step_minutes
        base = start_dt.replace(minute=minute, second=0, microsecond=0)
        if base < start_dt:
            base += timedelta(minutes=step_minutes)
        cur = base
        while cur + timedelta(minutes=duration_min) <= end_dt:
            yield cur
            cur += timedelta(minutes=step_minutes)

    # For each day, build busy intervals overlapped with that day's working window and find gaps
    for single_day in (start_date + timedelta(days=n) for n in range((end_date - start_date).days + 1)):
        if len(suggestions) >= max_suggestions:
            break
        day_start, day_end = day_work_range(single_day)

        # If anchor day, ensure we don't propose before anchor
        if single_day == anchor_dt.date():
            day_start = max(day_start, anchor_dt)

        # Extract busy intervals overlapping this day's window
        overlapping = []
        for bstart, bend in busy_intervals:
            if bend <= day_start or bstart >= day_end:
                continue
            overlapping.append((max(bstart, day_start), min(bend, day_end)))
        overlapping = _merge_intervals(overlapping)

        # iterate through gaps: from pointer to each busy start, then after last busy
        pointer = day_start
        for bstart, bend in overlapping:
            # produce candidate starts between pointer and bstart
            for candidate_start in generate_aligned_starts(pointer, bstart):
                candidate_end = candidate_start + timedelta(minutes=duration_min)
                suggestions.append(
                    Slot(start_iso=_dt_to_iso(candidate_start), end_iso=_dt_to_iso(candidate_end), tz=tz)
                )
                if len(suggestions) >= max_suggestions:
                    break
            if len(suggestions) >= max_suggestions:
                break
            # move pointer after this busy block
            pointer = max(pointer, bend)
        if len(suggestions) >= max_suggestions:
            break

        # After busy list, try between pointer and day_end
        for candidate_start in generate_aligned_starts(pointer, day_end):
            candidate_end = candidate_start + timedelta(minutes=duration_min)
            suggestions.append(
                Slot(start_iso=_dt_to_iso(candidate_start), end_iso=_dt_to_iso(candidate_end), tz=tz)
            )
            if len(suggestions) >= max_suggestions:
                break

    # Final guard: ensure suggestions are unique & sorted
    unique = []
    seen = set()
    for s in suggestions:
        key = (s.start_iso, s.end_iso)
        if key not in seen:
            unique.append(s)
            seen.add(key)
    return unique[:max_suggestions]


def create_event(
    cal_service,
    *,
    slot: Slot,
    title: str,
    attendees: List[str],
    add_meet: bool = True,
    description: Optional[str] = None,
) -> dict:
    """
    Create an event on the primary calendar.
    Returns dict with at least {'eventId': ..., 'hangoutLink': ... (maybe None)}
    """
    event_body = {
        "summary": title,
        "start": {"dateTime": slot.start_iso, "timeZone": slot.tz},
        "end": {"dateTime": slot.end_iso, "timeZone": slot.tz},
        "attendees": [{"email": a} for a in attendees],
    }
    if description:
        event_body["description"] = description
    if add_meet:
        event_body["conferenceData"] = {"createRequest": {"requestId": uuid.uuid4().hex}}

    try:
        insert_kwargs = {"calendarId": "primary", "body": event_body, "sendUpdates": "all"}
        if add_meet:
            insert_kwargs["conferenceDataVersion"] = 1
        created = cal_service.events().insert(**insert_kwargs).execute()
        logger.info("Created event: %s", created.get("id"))
        return {"eventId": created.get("id"), "hangoutLink": created.get("hangoutLink")}
    except HttpError as e:
        logger.exception("Calendar insert error: %s", e)
        raise


# -- Optional utility for buffer times: shrink available slots by buffer minutes
def add_buffer(slot: Slot, before_min=5, after_min=5) -> Slot:
    s = _iso_to_dt(slot.start_iso)
    e = _iso_to_dt(slot.end_iso)
    s2 = s + timedelta(minutes=before_min)
    e2 = e - timedelta(minutes=after_min)
    return Slot(start_iso=_dt_to_iso(s2), end_iso=_dt_to_iso(e2), tz=slot.tz)
