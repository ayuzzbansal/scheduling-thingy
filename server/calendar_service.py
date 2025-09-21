from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta, time
import pytz

# --- Fine-Tuning: Hardcode the timezone for the MVP ---
INDIANAPOLIS_TZ = pytz.timezone('America/Indiana/Indianapolis')

class CalendarTool:
    """A tool for interacting with the Google Calendar API."""

    def __init__(self, credentials):
        """Initializes the CalendarTool with user credentials."""
        self.service = build('calendar', 'v3', credentials=credentials)

    def find_free_slots(self, duration_minutes=60):
        """
        Finds the next available time slots in the user's primary calendar, fixed to Indianapolis time.
        """
        try:
            # Get the current time in the specified timezone
            now = datetime.now(INDIANAPOLIS_TZ)
            
            # Set the time range to check: from now until 14 days from now
            time_min = now.isoformat()
            time_max = (now + timedelta(days=14)).isoformat()

            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy='startTime',
                timeZone=INDIANAPOLIS_TZ.zone # Tell Google we are working in this timezone
            ).execute()
            events = events_result.get('items', [])

            # Define working hours (9 AM to 5 PM Indianapolis time)
            work_start_time = time(9, 0)
            work_end_time = time(17, 0)
            
            # Start checking for free slots from the next full hour in Indianapolis time
            check_time = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
            free_slots = []
            
            while check_time < (now + timedelta(days=14)):
                # CORRECTED LINE: Compare the time part of check_time with the work_start_time and work_end_time objects
                if work_start_time <= check_time.time() < work_end_time:
                    is_slot_free = True
                    slot_end_time = check_time + timedelta(minutes=duration_minutes)

                    for event in events:
                        # Convert event times to Indianapolis timezone to be safe
                        event_start_str = event['start'].get('dateTime')
                        event_end_str = event['end'].get('dateTime')
                        
                        if event_start_str and event_end_str:
                            event_start = datetime.fromisoformat(event_start_str).astimezone(INDIANAPOLIS_TZ)
                            event_end = datetime.fromisoformat(event_end_str).astimezone(INDIANAPOLIS_TZ)

                            if max(check_time, event_start) < min(slot_end_time, event_end):
                                is_slot_free = False
                                break
                    
                    if is_slot_free:
                        free_slots.append(check_time)
                        if len(free_slots) >= 5:
                            break
                
                check_time += timedelta(hours=1)

            return free_slots
        except HttpError as error:
            return f"An error occurred with the Calendar API: {error}"

