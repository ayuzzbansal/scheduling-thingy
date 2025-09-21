from datetime import datetime, time, timedelta
import pytz
from googleapiclient.discovery import build

class CalendarTool:
    """A tool for interacting with the Google Calendar API."""
    def __init__(self, credentials):
        self.service = build('calendar', 'v3', credentials=credentials)
        self.timezone = 'America/Indiana/Indianapolis' # Hardcoded for MVP

    def find_free_slots(self, duration_minutes=60):
        """
        Finds the next available slot on the calendar for tomorrow between 9am and 5pm.
        """
        tz = pytz.timezone(self.timezone)
        tomorrow = datetime.now(tz).date() + timedelta(days=1)
        
        start_of_day = tz.localize(datetime.combine(tomorrow, time(9, 0)))
        end_of_day = tz.localize(datetime.combine(tomorrow, time(17, 0)))

        # Get all events for the target day
        events_result = self.service.events().list(
            calendarId='primary', 
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(), 
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        busy_slots = events_result.get('items', [])

        # Find a free slot
        current_time = start_of_day
        while current_time + timedelta(minutes=duration_minutes) <= end_of_day:
            is_free = True
            for event in busy_slots:
                event_start = datetime.fromisoformat(event['start'].get('dateTime'))
                event_end = datetime.fromisoformat(event['end'].get('dateTime'))
                
                # Check for overlap
                if max(current_time, event_start) < min(current_time + timedelta(minutes=duration_minutes), event_end):
                    is_free = False
                    current_time = event_end # Jump to the end of the busy slot
                    break
            
            if is_free:
                return current_time # Found a free slot
            
        return None # No free slot found

    def create_event(self, start_time, end_time, summary, attendees):
        """
        Creates a new event on the primary calendar and invites attendees.
        `attendees` should be a list of email addresses.
        """
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': self.timezone,
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': self.timezone,
            },
            'attendees': [{'email': email} for email in attendees],
            'reminders': {
                'useDefault': True,
            },
            # Add a Google Meet link
            'conferenceData': {
                'createRequest': {
                    'requestId': f"{start_time.isoformat()}-{summary}",
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet'
                    }
                }
            }
        }

        created_event = self.service.events().insert(
            calendarId='primary', 
            body=event,
            sendNotifications=True, # This sends the invite to attendees
            conferenceDataVersion=1
        ).execute()
        
        print(f"Event created: {created_event.get('htmlLink')}")
        return created_event

