# app.py

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import smtplib
from email.mime.text import MIMEText
import uuid
import uvicorn

# ============ CALENDAR CORE ============

def get_calendar_service(credentials: Credentials):
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)

def list_todays_events(cal_service):
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

# ============ EMAIL AGENT ============

class EmailAgent:
    def __init__(self, username=None, password=None):
        self.username = username
        self.password = password
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587

    def draft_email(self, event):
        subject = f"Reminder: {event['summary']} at {event['start']['dateTime']}"
        body = f"""
Hello,

This is a reminder for the event:

Title: {event['summary']}
Start: {event['start']['dateTime']}
End: {event['end']['dateTime']}

See you there!
"""
        return subject, body

    def send_email(self, recipient, subject, body):
        if not self.username or not self.password:
            print(f"[SIMULATION] Sending to {recipient}: {subject}")
            return f"[SIMULATION] {recipient}: {subject}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = recipient

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, [recipient], msg.as_string())
        return f"✅ Sent to {recipient}"

# ============ FASTAPI APP ============

app = FastAPI()

# --- you must set up credentials beforehand (for demo, assume token.json exists) ---
import os, json
if os.path.exists("token.json"):
    creds = Credentials.from_authorized_user_file("token.json", ["https://www.googleapis.com/auth/calendar"])
    cal_service = get_calendar_service(creds)
else:
    cal_service = None

email_agent = EmailAgent()  # fill creds if you want real send

@app.get("/", response_class=HTMLResponse)
async def home():
    if not cal_service:
        return "<h2>❌ No Google credentials found. Run OAuth first.</h2>"

    events = list_todays_events(cal_service)
    today = datetime.utcnow().date().isoformat()

    html = f"<h1>📅 Events for {today}</h1>"
    if not events:
        html += "<p>No events today ✅</p>"
    else:
        for e in events:
            subject, body = email_agent.draft_email(e)
            attendees = ", ".join([a["email"] for a in e.get("attendees", [])])
            html += f"""
            <div style="border:1px solid #ddd; padding:10px; margin:10px;">
              <h2>{e['summary']}</h2>
              <p><b>When:</b> {e['start']['dateTime']} - {e['end']['dateTime']}</p>
              <p><b>Attendees:</b> {attendees}</p>
              <p><b>Draft Subject:</b> {subject}</p>
              <pre>{body}</pre>
            </div>
            """
        html += '<form action="/send" method="post"><button type="submit">📨 Send All Emails</button></form>'
    return html

@app.post("/send", response_class=HTMLResponse)
async def send_emails():
    events = list_todays_events(cal_service)
    logs = []
    for e in events:
        subject, body = email_agent.draft_email(e)
        for attendee in e.get("attendees", []):
            logs.append(email_agent.send_email(attendee["email"], subject, body))
    html = "<h1>📨 Results</h1>"
    for l in logs:
        html += f"<p>{l}</p>"
    html += '<p><a href="/">⬅️ Back</a></p>'
    return html

# ============ MAIN ============

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
