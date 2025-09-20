from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import asyncio

# ---------- Calendar helpers ----------
def get_calendar_service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)

# your helper functions: parse_time_str, subtract_busy_from_window, split_into_slots, etc.

async def run_blocking(fn, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

# ---------- Main adapter function ----------
async def get_free_slots(cal_service, days=7, duration_min=45, work_start="09:00", work_end="18:00",
                         tz="America/Indiana/Indianapolis", snap_minutes=30):
    """
    Returns list of free slots JSON that your CalendarAgent can return to LLM.
    """
    owner_tz = ZoneInfo(tz)
    now_local = datetime.now(tz=owner_tz)
    search_start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    search_end_local = (search_start_local + timedelta(days=days)).replace(hour=23, minute=59, second=59, microsecond=0)

    # freebusy query
    time_min = search_start_local.astimezone(ZoneInfo("UTC")).isoformat()
    time_max = search_end_local.astimezone(ZoneInfo("UTC")).isoformat()
    body = {"timeMin": time_min, "timeMax": time_max, "timeZone": tz, "items": [{"id": "primary"}]}

    resp = await run_blocking(cal_service.freebusy().query, body=body).execute()
    busy_periods_raw = resp.get("calendars", {}).get("primary", {}).get("busy", [])
    busy_periods = []
    for b in busy_periods_raw:
        bstart = datetime.fromisoformat(b["start"]).astimezone(owner_tz)
        bend = datetime.fromisoformat(b["end"]).astimezone(owner_tz)
        busy_periods.append((bstart, bend))

    # build free slots
    work_start_h, work_start_m = [int(x) for x in work_start.split(":")]
    work_end_h, work_end_m = [int(x) for x in work_end.split(":")]
    all_free_slots = []

    for day_offset in range(days):
        day_local = search_start_local + timedelta(days=day_offset)
        window_start = day_local.replace(hour=work_start_h, minute=work_start_m)
        window_end = day_local.replace(hour=work_end_h, minute=work_end_m)
        if window_end <= now_local and day_offset == 0:
            continue
        busy_for_day = [(max(bstart, window_start), min(bend, window_end)) 
                        for bstart, bend in busy_periods if not (bend <= window_start or bstart >= window_end)]
        free_segments = subtract_busy_from_window(window_start, window_end, busy_for_day)
        slots = split_into_slots(free_segments, duration_min, snap_to_minutes=snap_minutes)
        for s, e in slots:
            if e <= now_local + timedelta(minutes=1):
                continue
            all_free_slots.append({"start_iso": s.isoformat(), "end_iso": e.isoformat(), "tz": tz})
    return all_free_slots
