import os
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import json
from google.auth.transport.requests import Request as GoogleAuthRequest

# Import the tool classes
from gmail_service import GmailTool
from calendar_service import CalendarTool

app = FastAPI()

# --- Configuration is the same ---
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar'
]
REDIRECT_URI = 'http://127.0.0.1:8000/callback'
TOKEN_FILE = "token.json"

credentials = None

# --- Credential loading/saving functions are the same ---
def load_credentials():
    global credentials
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as token:
            creds_data = json.load(token)
        credentials = Credentials.from_authorized_user_info(creds_data, SCOPES)
    
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(GoogleAuthRequest())
            save_credentials()
        else:
            credentials = None

def save_credentials():
    global credentials
    if credentials:
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': credentials.scopes
        }
        with open(TOKEN_FILE, 'w') as token:
            json.dump(creds_data, token)

@app.on_event("startup")
async def startup_event():
    load_credentials()
    if credentials:
        print("Credentials loaded successfully.")
    else:
        print("No valid credentials found. Please log in.")

# --- Login/Callback endpoints are the same ---
@app.get("/")
async def root():
    if not credentials or not credentials.valid:
        return {"message": "Welcome! Please log in.", "login_url": "/login"}
    return {"message": "You are logged in."}

@app.get("/login")
async def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline', include_granted_scopes='true', prompt='consent'
    )
    return RedirectResponse(authorization_url)

@app.get("/callback")
async def callback(request: Request):
    global credentials
    code = request.query_params.get('code')
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, scopes=SCOPES, redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code)
    credentials = flow.credentials
    save_credentials()
    return RedirectResponse("/")

# --- API endpoints now use the Tool classes ---
@app.get("/fetch-emails")
async def fetch_emails():
    if not credentials or not credentials.valid:
        return RedirectResponse("/login")

    gmail_tool = GmailTool(credentials)
    emails = gmail_tool.list_recent_emails()
    
    return JSONResponse(content={"emails": emails})

@app.get("/find-free-slots")
async def find_calendar_slots():
    if not credentials or not credentials.valid:
        return RedirectResponse("/login")
            
    # 1. Create an instance of the CalendarTool
    calendar_tool = CalendarTool(credentials)
    # 2. Call the method on the instance
    slots = calendar_tool.find_free_slots()
    
    return JSONResponse(content={"free_slots": slots})

@app.get("/send-test-email")
async def send_test_email():
    if not credentials or not credentials.valid:
        return RedirectResponse("/login")

    gmail_tool = GmailTool(credentials)
    
    test_recipient = "gautamvirbhatia@gmail.com" 
    subject = "Test Email from AI Scheduling Assistant (Class-based)"
    body = "This test confirms that the class-based GmailTool is working correctly."

    result = gmail_tool.send_reply(subject, body, test_recipient)

    if "error" in str(result).lower():
        return JSONResponse(content={"status": "Failed", "details": result})
    else:
        return JSONResponse(content={"status": "Success", "message_details": result})

