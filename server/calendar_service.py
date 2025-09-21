from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta, timezone

class CalendarTool:
    """A tool for interacting with the Google Calendar API."""

    def __init__(self, credentials):
        """
        Initializes the CalendarTool with user credentials.
        Args:
            credentials: The OAuth 2.0 credentials for the user.
        """
        self.service = build('calendar', 'v3', credentials=credentials)

    def find_free_slots(self, duration_minutes=60):
        """
        Finds free 1-hour slots in the user's calendar for the next business day.
        Args:
            duration_minutes: The duration of the meeting in minutes.
        Returns:
            A list of available start times or an error string.
        """
        try:
            # Set time range to check: tomorrow from 9 AM to 5 PM
            now = datetime.now(timezone.utc)
            tomorrow = now.date() + timedelta(days=1)
            start_of_day = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 9, 0, 0, tzinfo=timezone.utc)
            end_of_day = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 17, 0, 0, tzinfo=timezone.utc)

            # Get the user's busy times
            events_result = self.service.events().list(
                calendarId='primary', 
                timeMin=start_of_day.isoformat(),
                timeMax=end_of_day.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            busy_times = events_result.get('items', [])
            
            # --- Find the gaps ---
            free_slots = []
            previous_event_end = start_of_day

            for event in busy_times:
                event_start_str = event['start'].get('dateTime', event['start'].get('date'))
                event_start = datetime.fromisoformat(event_start_str)

                # Check the gap between the last event and this one
                gap_duration = event_start - previous_event_end
                if gap_duration >= timedelta(minutes=duration_minutes):
                    free_slots.append(previous_event_end.isoformat())

                previous_event_end_str = event['end'].get('dateTime', event['end'].get('date'))
                previous_event_end = datetime.fromisoformat(previous_event_end_str)

            # Check the final gap between the last event and the end of the day
            final_gap_duration = end_of_day - previous_event_end
            if final_gap_duration >= timedelta(minutes=duration_minutes):
                free_slots.append(previous_event_end.isoformat())

            return free_slots

        except HttpError as error:
            return f"An error occurred with the Calendar API: {error}"

