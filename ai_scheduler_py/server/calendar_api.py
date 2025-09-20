"""
Google Calendar API Service Module

Provides functionality to interact with Google Calendar API for managing events
"""

from datetime import datetime, timedelta
from googleapiclient.discovery import build
from oauth import OAuthManager
from typing import List, Dict, Optional
import pytz

class CalendarService:
    """Service class for Google Calendar API operations"""
    
    def __init__(self):
        self.oauth_manager = OAuthManager()
        self.service = None
        self._initialize_service()
    
    def _initialize_service(self):
        """Initialize Calendar service with OAuth credentials"""
        try:
            creds = self.oauth_manager.get_credentials()
            if creds:
                self.service = build('calendar', 'v3', credentials=creds)
            else:
                print("Calendar service initialization failed: No valid credentials")
        except Exception as e:
            print(f"Calendar service initialization error: {e}")
    
    def get_calendar_list(self) -> List[Dict]:
        """
        Get list of user's calendars
        
        Returns:
            List of calendar dictionaries
        """
        if not self.service:
            return []
        
        try:
            calendar_result = self.service.calendarList().list().execute()
            calendars = calendar_result.get('items', [])
            return calendars
        except Exception as e:
            print(f"Error getting calendar list: {e}")
            return []
    
    def get_events(self, calendar_id: str = 'primary', max_results: int = 10, 
                   time_min: datetime = None, time_max: datetime = None) -> List[Dict]:
        """
        Get events from a calendar
        
        Args:
            calendar_id: Calendar ID (default: 'primary')
            max_results: Maximum number of events to retrieve
            time_min: Minimum time for events (default: now)
            time_max: Maximum time for events (default: 7 days from now)
            
        Returns:
            List of event dictionaries
        """
        if not self.service:
            return []
        
        try:
            if time_min is None:
                time_min = datetime.utcnow()
            if time_max is None:
                time_max = datetime.utcnow() + timedelta(days=7)
            
            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=time_min.isoformat() + 'Z',
                timeMax=time_max.isoformat() + 'Z',
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            return events
        except Exception as e:
            print(f"Error getting events: {e}")
            return []
    
    def create_event(self, summary: str, start_time: datetime, end_time: datetime,
                     description: str = "", location: str = "", attendees: List[str] = None,
                     calendar_id: str = 'primary') -> Optional[Dict]:
        """
        Create a new calendar event
        
        Args:
            summary: Event title
            start_time: Event start time
            end_time: Event end time
            description: Event description
            location: Event location
            attendees: List of attendee email addresses
            calendar_id: Calendar ID to create event in
            
        Returns:
            Created event dictionary or None if failed
        """
        if not self.service:
            return None
        
        try:
            event = {
                'summary': summary,
                'description': description,
                'start': {
                    'dateTime': start_time.isoformat(),
                    'timeZone': 'UTC',
                },
                'end': {
                    'dateTime': end_time.isoformat(),
                    'timeZone': 'UTC',
                },
            }
            
            if location:
                event['location'] = location
            
            if attendees:
                event['attendees'] = [{'email': email} for email in attendees]
            
            created_event = self.service.events().insert(
                calendarId=calendar_id,
                body=event
            ).execute()
            
            return created_event
        except Exception as e:
            print(f"Error creating event: {e}")
            return None
    
    def update_event(self, event_id: str, updates: Dict, calendar_id: str = 'primary') -> Optional[Dict]:
        """
        Update an existing calendar event
        
        Args:
            event_id: ID of the event to update
            updates: Dictionary of fields to update
            calendar_id: Calendar ID containing the event
            
        Returns:
            Updated event dictionary or None if failed
        """
        if not self.service:
            return None
        
        try:
            # Get the existing event
            event = self.service.events().get(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            
            # Apply updates
            for key, value in updates.items():
                event[key] = value
            
            # Update the event
            updated_event = self.service.events().update(
                calendarId=calendar_id,
                eventId=event_id,
                body=event
            ).execute()
            
            return updated_event
        except Exception as e:
            print(f"Error updating event: {e}")
            return None
    
    def delete_event(self, event_id: str, calendar_id: str = 'primary') -> bool:
        """
        Delete a calendar event
        
        Args:
            event_id: ID of the event to delete
            calendar_id: Calendar ID containing the event
            
        Returns:
            Boolean indicating success
        """
        if not self.service:
            return False
        
        try:
            self.service.events().delete(
                calendarId=calendar_id,
                eventId=event_id
            ).execute()
            return True
        except Exception as e:
            print(f"Error deleting event: {e}")
            return False
    
    def find_free_time_slots(self, start_date: datetime, end_date: datetime,
                            duration_minutes: int = 60, calendar_id: str = 'primary') -> List[Dict]:
        """
        Find available time slots in the calendar
        
        Args:
            start_date: Start of search period
            end_date: End of search period
            duration_minutes: Required duration for the slot
            calendar_id: Calendar to search in
            
        Returns:
            List of available time slot dictionaries
        """
        if not self.service:
            return []
        
        try:
            # Get existing events in the time range
            events = self.get_events(
                calendar_id=calendar_id,
                time_min=start_date,
                time_max=end_date,
                max_results=100
            )
            
            # Extract busy periods
            busy_periods = []
            for event in events:
                start = event.get('start', {})
                end = event.get('end', {})
                
                if 'dateTime' in start and 'dateTime' in end:
                    busy_periods.append({
                        'start': datetime.fromisoformat(start['dateTime'].replace('Z', '+00:00')),
                        'end': datetime.fromisoformat(end['dateTime'].replace('Z', '+00:00'))
                    })
            
            # Sort busy periods by start time
            busy_periods.sort(key=lambda x: x['start'])
            
            # Find free slots
            free_slots = []
            current_time = start_date
            
            for busy_period in busy_periods:
                # Check if there's a gap before this busy period
                if current_time + timedelta(minutes=duration_minutes) <= busy_period['start']:
                    free_slots.append({
                        'start': current_time,
                        'end': busy_period['start']
                    })
                
                # Move current time to end of busy period
                current_time = max(current_time, busy_period['end'])
            
            # Check for time after last busy period
            if current_time + timedelta(minutes=duration_minutes) <= end_date:
                free_slots.append({
                    'start': current_time,
                    'end': end_date
                })
            
            return free_slots
        except Exception as e:
            print(f"Error finding free time slots: {e}")
            return []
    
    def get_busy_times(self, start_time: datetime, end_time: datetime,
                       calendars: List[str] = None) -> List[Dict]:
        """
        Get busy times using the freebusy query
        
        Args:
            start_time: Start of query period
            end_time: End of query period
            calendars: List of calendar IDs to check (default: primary)
            
        Returns:
            List of busy time periods
        """
        if not self.service:
            return []
        
        try:
            if calendars is None:
                calendars = ['primary']
            
            body = {
                'timeMin': start_time.isoformat() + 'Z',
                'timeMax': end_time.isoformat() + 'Z',
                'items': [{'id': cal_id} for cal_id in calendars]
            }
            
            freebusy_result = self.service.freebusy().query(body=body).execute()
            
            busy_times = []
            for calendar_id, calendar_data in freebusy_result.get('calendars', {}).items():
                for busy_period in calendar_data.get('busy', []):
                    busy_times.append({
                        'calendar_id': calendar_id,
                        'start': datetime.fromisoformat(busy_period['start'].replace('Z', '+00:00')),
                        'end': datetime.fromisoformat(busy_period['end'].replace('Z', '+00:00'))
                    })
            
            return busy_times
        except Exception as e:
            print(f"Error getting busy times: {e}")
            return []