from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import uuid


def get_calendar_service(credentials: Credentials):
    """Build a Google Calendar API service object."""
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


def list_todays_events(cal_service):
    """List all events for today from the primary calendar."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + "Z"
    today_end = (datetime.utcnow().replace(hour=23, minute=59, second=59, microsecond=0)).isoformat() + "Z"
    events_result = cal_service.events().list(
        calendarId="primary",
        timeMin=today_start,
        timeMax=today_end,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return events_result.get("items", [])


def create_event(cal_service, *, start_iso, end_iso, title, attendees, description=None):
    """Create an event on the primary calendar with Google Meet integration."""
    event_body = {
        "summary": title,
        "start": {"dateTime": start_iso},
        "end": {"dateTime": end_iso},
        "attendees": [{"email": a} for a in attendees],
        "conferenceData": {"createRequest": {"requestId": uuid.uuid4().hex}},
    }
    if description:
        event_body["description"] = description
    created = cal_service.events().insert(
        calendarId="primary", body=event_body, conferenceDataVersion=1, sendUpdates="all"
    ).execute()
    return {"eventId": created.get("id"), "hangoutLink": created.get("hangoutLink")}