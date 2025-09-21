import os
import json
import requests
import re
from dotenv import load_dotenv
from datetime import datetime
import pytz

# Import the tools you built
from gmail_service import GmailTool
from calendar_service import CalendarTool

# Load environment variables from a .env file
load_dotenv()

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"

# --- JSON Schema for the AI model ---
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "isMeetingSuggested": {"type": "BOOLEAN"},
        "meetingDetails": {
            "type": "OBJECT",
            "properties": {
                "topic": {"type": "STRING"},
                "attendees": {"type": "ARRAY", "items": {"type": "STRING"}},
                "suggestedTimes": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "date": {"type": "STRING"},
                            "time": {"type": "STRING"},
                            "rawText": {"type": "STRING"}
                        }
                    }
                }
            }
        }
    },
    "required": ["isMeetingSuggested"]
}


class SchedulingAgent:
    """The orchestrator that uses tools and AI to handle scheduling."""

    def __init__(self, credentials):
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables.")
        self.gmail_tool = GmailTool(credentials)
        self.calendar_tool = CalendarTool(credentials)

    def _format_datetime_for_email(self, dt_object):
        """Helper to format a datetime object for a user-friendly email."""
        if isinstance(dt_object, datetime):
            # CORRECTED LINE: Changed '%-I' to '%I' for Windows compatibility
            return dt_object.strftime('%A, %B %d at %I:%M %p %Z')
        return str(dt_object) # Fallback

    def analyze_email_with_ai(self, email_body):
        """Uses the Gemini API to analyze email content."""
        prompt = f"""
        You are an intelligent meeting scheduling assistant. Analyze the following email text. 
        - If a meeting is suggested, set 'isMeetingSuggested' to true.
        - If no meeting is suggested, set 'isMeetingSuggested' to false.
        Email Text:
        ---
        {email_body}
        ---
        """
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            }
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(API_URL, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        
        result_json = response.json()
        content_text = result_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        return json.loads(content_text)

    def run_on_latest_email(self):
        """The main orchestration logic for the agent."""
        print("Agent running: Checking for latest email...")
        
        latest_emails = self.gmail_tool.list_recent_emails()
        if not latest_emails or not isinstance(latest_emails, list):
            return {"status": "No new emails to process or an error occurred."}
        
        latest_email_summary = latest_emails[0]
        email_id = latest_email_summary['id']
        sender_info = latest_email_summary['from']
        
        print(f"Processing email ID: {email_id} | Subject: {latest_email_summary['subject']}")

        email_body = self.gmail_tool.get_email_body(email_id)
        if "error" in str(email_body).lower():
            return {"status": "Failed", "error": email_body}

        try:
            analysis = self.analyze_email_with_ai(email_body)
            print("AI Analysis complete:", analysis)
        except Exception as e:
            return {"status": "Failed", "error": f"AI analysis failed: {e}"}

        if analysis.get("isMeetingSuggested"):
            print("Action: Meeting suggested. Checking calendar...")
            
            free_slots = self.calendar_tool.find_free_slots()
            if not free_slots or not isinstance(free_slots, list):
                return {"status": "Action Failed", "reason": "Could not find any free slots.", "details": free_slots}

            proposed_time_obj = free_slots[0]
            friendly_time = self._format_datetime_for_email(proposed_time_obj)
            
            sender_email_match = re.search(r'<(.+?)>', sender_info)
            if not sender_email_match:
                return {"status": "Action Failed", "reason": "Could not parse sender's email address."}
            
            to_email = sender_email_match.group(1)
            
            subject = f"Re: {latest_email_summary['subject']}"
            body = (
                f"Hello,\n\n"
                f"Thank you for your email.\n\n"
                f"I have checked the calendar and found an available slot at: {friendly_time}\n\n"
                f"Please let me know if this time works for you.\n\n"
                f"Best regards,\n"
                f"Scheduling Assistant"
            )

            print(f"Action: Sending reply to {to_email} with proposed time {friendly_time}")
            send_result = self.gmail_tool.send_reply(subject, body, to_email)

            return {"status": "Action Complete", "action_taken": "Sent email reply with proposed time.", "details": send_result}
        else:
            print("Action: No meeting suggested. No action taken.")
            return {"status": "Complete", "action_taken": "No action required.", "analysis": analysis}

