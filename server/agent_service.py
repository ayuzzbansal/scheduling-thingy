import os
import json
import requests
from dotenv import load_dotenv
from datetime import timedelta, datetime

from gmail_service import GmailTool
from calendar_service import CalendarTool

# Load environment variables from a .env file
load_dotenv()

class SchedulingAgent:
    """The main agent that orchestrates the scheduling process."""
    def __init__(self, credentials):
        self.gmail_tool = GmailTool(credentials)
        self.calendar_tool = CalendarTool(credentials)
        self.gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={self.gemini_api_key}"
        self.schema = {
            "type": "OBJECT",
            "properties": {
                "isMeetingSuggested": {"type": "BOOLEAN"},
                "meetingDetails": {
                    "type": "OBJECT",
                    "properties": {
                        "topic": {"type": "STRING"},
                        "attendees": {"type": "ARRAY", "items": {"type": "STRING"}},
                    },
                }
            },
            "required": ["isMeetingSuggested"]
        }

    def analyze_email_with_ai(self, email_body):
        """Sends email content to Gemini for analysis."""
        # Get the current date to provide context to the LLM
        current_date = datetime.now().strftime("%A, %B %d, %Y")
        
        prompt = f"""
        Analyze the following email to determine if a meeting is being suggested.
        The current date is {current_date}. Use this to interpret relative dates like "tomorrow" or "next week".
        
        - If a meeting is suggested, set 'isMeetingSuggested' to true and extract the meeting topic.
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
                "responseSchema": self.schema,
            }
        }
        headers = {'Content-Type': 'application/json'}
        response = requests.post(self.api_url, headers=headers, json=payload)
        response.raise_for_status()
        
        result_json = response.json()
        content_text = result_json.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '{}')
        return json.loads(content_text)

    def run_on_latest_email(self):
        """Runs the full agent process on the latest email."""
        try:
            latest_email = self.gmail_tool.get_latest_email()
            if not latest_email:
                return {"status": "Complete", "action_taken": "No new emails found."}

            email_body = self.gmail_tool.get_email_body(latest_email['id'])
            analysis = self.analyze_email_with_ai(email_body)

            if analysis.get("isMeetingSuggested"):
                print("Meeting suggested, checking calendar...")
                suggested_slot = self.calendar_tool.find_free_slots()

                if suggested_slot:
                    start_time = suggested_slot
                    end_time = start_time + timedelta(hours=1)
                    
                    # Get user and sender emails for the invite
                    user_email = self.gmail_tool.get_user_email()
                    sender_email = latest_email['sender']
                    attendees = [user_email, sender_email]

                    # Create the event
                    event_summary = analysis.get("meetingDetails", {}).get("topic", "Meeting")
                    created_event = self.calendar_tool.create_event(start_time, end_time, event_summary, attendees)
                    meet_link = created_event.get('hangoutLink', 'N/A')
                    
                    # Send a confirmation email with the Meet link
                    formatted_time = start_time.strftime("%A, %B %d at %I:%M %p %Z")
                    reply_subject = f"Re: {latest_email['subject']}"
                    reply_body = (
                        f"Hello,\n\n"
                        f"Based on your request for '{event_summary}', I have scheduled a tentative meeting for us.\n\n"
                        f"A calendar invitation for {formatted_time} has been sent to you.\n\n"
                        f"You can join the video call here: {meet_link}\n\n"
                        f"Best regards,\n"
                        f"Scheduling Assistant"
                    )
                    
                    self.gmail_tool.send_reply(latest_email['sender'], reply_subject, reply_body, latest_email['thread_id'])
                    return {"status": "Complete", "action_taken": "Calendar event created and confirmation email sent."}
                else:
                    # Handle case where no slots are free (optional for MVP)
                    return {"status": "Complete", "action_taken": "Meeting suggested but no free slots were found."}

            else:
                return {"status": "Complete", "action_taken": "No action required.", "analysis": analysis}

        except Exception as e:
            print(f"An error occurred in the agent: {e}")
            return {"status": "Failed", "error": str(e)}

