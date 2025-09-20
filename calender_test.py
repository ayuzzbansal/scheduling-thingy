# tests/test_calendar_api.py
import unittest
from unittest.mock import Mock
from datetime import datetime, timezone, timedelta
from calendar_api import Slot, is_free, suggest_slots, create_event, _dt_to_iso
from zoneinfo import ZoneInfo

class TestCalendarAPI(unittest.TestCase):

    def test_is_free_true_when_no_busy(self):
        mock_service = Mock()
        mock_service.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {"primary": {"busy": []}}
        }
        slot = Slot(start_iso="2025-09-21T15:00:00-04:00", end_iso="2025-09-21T15:30:00-04:00", tz="America/Indiana/Indianapolis")
        self.assertTrue(is_free(mock_service, slot))

    def test_is_free_false_when_busy(self):
        mock_service = Mock()
        mock_service.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {"primary": {"busy": [{"start": "2025-09-21T15:00:00-04:00", "end": "2025-09-21T16:00:00-04:00"}]}}
        }
        slot = Slot(start_iso="2025-09-21T15:30:00-04:00", end_iso="2025-09-21T16:00:00-04:00", tz="America/Indiana/Indianapolis")
        self.assertFalse(is_free(mock_service, slot))

    def test_suggest_slots_basic(self):
        # Setup busy at 15:00-16:00, expect suggestion at 09:00 (if window) or 16:00 etc.
        mock_service = Mock()
        # We'll return a busy block across the whole day
        mock_service.freebusy.return_value.query.return_value.execute.return_value = {
            "calendars": {"primary": {"busy": [
                {"start": "2025-09-22T15:00:00-04:00", "end": "2025-09-22T16:00:00-04:00"}
            ]}}
        }
        anchor_iso = "2025-09-22T08:00:00-04:00"
        slots = suggest_slots(mock_service, anchor_iso=anchor_iso, duration_min=30, days=1, working_start="09:00", working_end="17:00", tz="America/Indiana/Indianapolis")
        # Expect at least one suggestion (09:00) and no overlap with 15:00 busy
        self.assertTrue(len(slots) >= 1)
        for s in slots:
            self.assertFalse(s.start_iso.startswith("2025-09-22T15:"))  # not in busy slot

    def test_create_event_returns_id(self):
        mock_service = Mock()
        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "evt123", "hangoutLink": "https://meet.google.com/abc-defg-hij"
        }
        slot = Slot(start_iso="2025-09-23T10:00:00-04:00", end_iso="2025-09-23T10:45:00-04:00", tz="America/Indiana/Indianapolis")
        resp = create_event(mock_service, slot=slot, title="Test", attendees=["alice@example.com"])
        self.assertEqual(resp["eventId"], "evt123")
        self.assertIn("hangoutLink", resp)

if __name__ == "__main__":
    unittest.main()
