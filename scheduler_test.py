from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import datetime
import smtplib
from email.mime.text import MIMEText
import uvicorn

# ============ AGENTS ============

class CalendarAgent:
    def __init__(self):
        # Mock events for now (replace with Google Calendar API integration)
        self.events = [
            {"title": "Team Standup", "date": "2025-09-21", "time": "10:00", "attendees": ["alice@example.com"]},
            {"title": "Client Call", "date": "2025-09-21", "time": "14:00", "attendees": ["client@example.com"]},
            {"title": "Project Review", "date": "2025-09-22", "time": "11:30", "attendees": ["bob@example.com"]},
        ]

    def get_todays_events(self):
        today = datetime.date.today().isoformat()
        return [e for e in self.events if e["date"] == today]


class EmailAgent:
    def __init__(self, smtp_server="smtp.gmail.com", smtp_port=587, username=None, password=None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.username = username
        self.password = password

    def draft_email(self, event):
        subject = f"Reminder: {event['title']} at {event['time']}"
        body = f"""
Hello,

This is a reminder for the upcoming event:

Title: {event['title']}
Date: {event['date']}
Time: {event['time']}

See you there!
"""
        return subject, body

    def send_email(self, recipient, subject, body):
        if not self.username or not self.password:
            print(f"[SIMULATION] Sending email to {recipient}: {subject}\n{body}")
            return f"[SIMULATION] Email to {recipient}: {subject}"

        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = self.username
        msg["To"] = recipient

        with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
            server.starttls()
            server.login(self.username, self.password)
            server.sendmail(self.username, [recipient], msg.as_string())
        return f"✅ Email sent to {recipient}"


class OrchestratorAgent:
    def __init__(self, calendar_agent, email_agent):
        self.calendar_agent = calendar_agent
        self.email_agent = email_agent

    def get_event_emails(self):
        events = self.calendar_agent.get_todays_events()
        results = []
        for event in events:
            subject, body = self.email_agent.draft_email(event)
            results.append({"event": event, "subject": subject, "body": body})
        return results

    def send_all(self):
        events = self.calendar_agent.get_todays_events()
        logs = []
        for event in events:
            subject, body = self.email_agent.draft_email(event)
            for attendee in event["attendees"]:
                result = self.email_agent.send_email(attendee, subject, body)
                logs.append(result)
        return logs


# ============ FASTAPI APP ============

app = FastAPI()

cal_agent = CalendarAgent()
email_agent = EmailAgent(username=None, password=None)  # set creds later if needed
orchestrator = OrchestratorAgent(cal_agent, email_agent)


@app.get("/", response_class=HTMLResponse)
async def home():
    emails = orchestrator.get_event_emails()
    today = datetime.date.today().isoformat()

    html = f"<h1>📅 Events for {today}</h1>"
    if not emails:
        html += "<p>No events today ✅</p>"
    else:
        for e in emails:
            html += f"""
            <div style="border:1px solid #ddd; padding:10px; margin:10px;">
              <h2>{e['event']['title']} ({e['event']['time']})</h2>
              <p><b>Attendees:</b> {', '.join(e['event']['attendees'])}</p>
              <p><b>Draft Subject:</b> {e['subject']}</p>
              <pre>{e['body']}</pre>
            </div>
            """
        html += '<form action="/send" method="post"><button type="submit">📨 Send All Emails</button></form>'
    return html


@app.post("/send", response_class=HTMLResponse)
async def send_emails():
    logs = orchestrator.send_all()
    html = "<h1>📨 Email Results</h1>"
    for log in logs:
        html += f"<p>{log}</p>"
    html += '<p><a href="/">⬅️ Back</a></p>'
    return html


# ============ MAIN RUNNER ============

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
