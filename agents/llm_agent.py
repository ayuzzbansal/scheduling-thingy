import os
import json
import requests
import base64
from flask import Flask, render_template, request, jsonify, redirect, url_for
from dotenv import load_dotenv

# Google API Imports
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


# Load environment variables from a .env file
load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24) # Needed for session management during OAuth

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={GEMINI_API_KEY}"

# --- Gmail API Configuration ---
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.json'

# Define the JSON schema for the model's structured response
SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "isMeetingSuggested": {"type": "BOOLEAN"},
        "meetingDetails": {
            "type": "OBJECT",
            "properties": {
                "topic": {
                    "type": "STRING",
                    "description": "The main topic or reason for the meeting. Infer this from the context of the email."
                },
                "attendees": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "A list of names of people mentioned as potential attendees. Do not include the sender unless they explicitly mention themselves as an attendee."
                },
                "suggestedTimes": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "date": {
                                "type": "STRING",
                                "description": "The suggested date in a clear format (e.g., 'next Tuesday', '2025-10-25')."
                            },
                            "time": {
                                "type": "STRING",
                                "description": "The suggested time, including timezone if mentioned (e.g., '2 PM PST', '10:00 AM')."
                            },
                            "rawText": {
                                "type": "STRING",
                                "description": "The exact text snippet from the email suggesting this time slot."
                            }
                        },
                        "required": ["date", "time", "rawText"]
                    }
                }
            },
            "required": ["topic", "attendees", "suggestedTimes"]
        }
    },
    "required": ["isMeetingSuggested"]
}

def get_gmail_service():
    """Authenticates with the Gmail API and returns a service object."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(google.auth.transport.requests.Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"'{CREDENTIALS_FILE}' not found. Please follow the setup instructions to get this file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
            
    return build('gmail', 'v1', credentials=creds)

@app.route('/fetch-latest-email')
def fetch_latest_email():
    """Fetches the latest unread email and redirects to the main page with its content."""
    try:
        service = get_gmail_service()
        # Get the most recent unread message ID
        results = service.users().messages().list(userId='me', q='is:unread', maxResults=1).execute()
        messages = results.get('messages', [])

        if not messages:
            return redirect(url_for('index', error="No unread emails found."))
        
        msg_id = messages[0]['id']
        message = service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        
        payload = message['payload']
        email_body = ""

        # Find the plain text part of the email
        if "parts" in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        email_body = base64.urlsafe_b64decode(data).decode('utf-8')
                        break
        # Fallback for simple emails with no parts
        elif 'body' in payload and payload['body'].get('data'):
             data = payload['body'].get('data')
             email_body = base64.urlsafe_b64decode(data).decode('utf-8')

        if not email_body:
            return redirect(url_for('index', error="Could not extract text content from the latest email."))

        # Mark the email as read after processing
        service.users().messages().modify(userId='me', id=msg_id, body={'removeLabelIds': ['UNREAD']}).execute()
        
        return redirect(url_for('index', email_body=email_body))

    except FileNotFoundError as e:
        return redirect(url_for('index', error=str(e)))
    except HttpError as error:
        return redirect(url_for('index', error=f"An API error occurred: {error}"))
    except Exception as e:
        return redirect(url_for('index', error=f"An unexpected error occurred: {e}"))


@app.route('/', methods=['GET', 'POST'])
def index():
    """
    Handles both displaying the main page and processing the form submission.
    """
    # Handle GET requests (page load, redirects from fetch)
    error = request.args.get('error')
    email_body = request.args.get('email_body', '')
    result = None

    if request.method == 'POST':
        # Overwrite email_body with form data for analysis
        email_body = request.form.get('email_body', '').strip()

        if not GEMINI_API_KEY:
            error = "GEMINI_API_KEY environment variable not set."
            return render_template('index.html', error=error, email_body=email_body)

        if not email_body:
            error = "Email body cannot be empty."
            return render_template('index.html', error=error, email_body=email_body)

        try:
            prompt = f"""
            You are an intelligent meeting scheduling assistant. Analyze the following email text. Your task is to determine if a meeting is being suggested.\n 
            - If a meeting is suggested, set 'isMeetingSuggested' to true and fill out the 'meetingDetails' object with the topic, attendees, and all suggested time slots.
            - If no meeting is suggested, set 'isMeetingSuggested' to false and the 'meetingDetails' field can be omitted.
            - Be precise in extracting the raw text for suggested times.
            - Infer the meeting topic from the context of the email.
            - Extract all names mentioned as potential attendees.

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
            
            if not content_text:
                block_reason = result_json.get("promptFeedback", {}).get("blockReason")
                if block_reason:
                    raise ValueError(f"Request was blocked: {block_reason}.")
                else:
                    raise ValueError("Could not extract content from the API response.")

            result = json.dumps(json.loads(content_text), indent=2)

        except requests.exceptions.RequestException as e:
            error = f"Network error: {e}"
        except (ValueError, KeyError, IndexError) as e:
            error = f"Error processing API response: {e}"
        except Exception as e:
            error = f"An unexpected error occurred: {e}"

    return render_template('index.html', result=result, error=error, email_body=email_body)

if __name__ == '__main__':
    app.run(debug=True)

