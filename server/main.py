import os
import json
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request as GoogleAuthRequest

# --- FIX for InsecureTransportError ---
# This tells the OAuth library that it's okay to use HTTP for local testing.
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

# Import your tools
from gmail_service import GmailTool
from agent_service import SchedulingAgent
from calendar_service import CalendarTool

# --- Configuration ---
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/calendar'
]
TOKEN_FILE = 'token.json'
CLIENT_SECRETS_FILE = 'client_secrets.json'
if not os.path.exists(CLIENT_SECRETS_FILE):
    if os.path.exists('client_secret.json'):
        CLIENT_SECRETS_FILE = 'client_secret.json'

app = FastAPI()
credentials = None

# --- Credential Handling ---

def save_credentials(creds):
    """Saves credentials to the token.json file."""
    with open(TOKEN_FILE, "w") as token:
        token.write(creds.to_json())
    print("INFO:     Credentials saved to token.json")

def load_credentials():
    """Loads credentials from token.json, refreshing if necessary."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
            save_credentials(creds) 
            print("INFO:     Token was expired and has been refreshed.")
        except Exception as e:
            print(f"ERROR:    Failed to refresh token: {e}")
            return None
    return creds

@app.on_event("startup")
async def startup_event():
    """On startup, load credentials from a file if they exist."""
    global credentials
    credentials = load_credentials()
    if credentials:
        print("INFO:     Credentials loaded successfully.")
    else:
        print("INFO:     No valid credentials found. Please log in.")
    print("INFO:     Application startup complete.")

# --- Authentication Endpoints ---

@app.get("/login")
def login():
    """Initiates the OAuth 2.0 login flow."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        raise HTTPException(status_code=404, detail=f"{CLIENT_SECRETS_FILE} not found.")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES, redirect_uri='http://127.0.0.1:8000/callback')
    authorization_url, _ = flow.authorization_url()
    return RedirectResponse(authorization_url)

@app.get("/callback")
def callback(request: Request):
    """Handles the callback from Google's OAuth 2.0 server."""
    global credentials
    state = request.query_params.get('state')
    
    flow = InstalledAppFlow.from_client_secrets_file(
        CLIENT_SECRETS_FILE, SCOPES, state=state, redirect_uri='http://127.0.0.1:8000/callback')
    
    authorization_response = str(request.url)
    flow.fetch_token(authorization_response=authorization_response)
    
    credentials = flow.credentials
    save_credentials(credentials)
    
    return RedirectResponse(url='/')

# --- Tool & Agent Endpoints ---

@app.get("/")
def home():
    if not credentials:
        return {"message": "Welcome! Please log in.", "login_url": "/login"}
    return {"message": "Authentication successful! You can now use the agent endpoints."}

@app.get("/process-latest-email")
def process_latest_email():
    """Runs the full scheduling agent on the latest email."""
    if not credentials:
        return RedirectResponse('/login')
    agent = SchedulingAgent(credentials)
    result = agent.run_on_latest_email()
    return JSONResponse(content=result)

# The following endpoints are useful for testing individual tools
@app.get("/fetch-emails")
def fetch_emails():
    if not credentials: return RedirectResponse('/login')
    gmail_tool = GmailTool(credentials)
    return JSONResponse(content={"emails": gmail_tool.list_recent_emails()})

@app.get("/find-free-slots")
def find_free_slots():
    if not credentials: return RedirectResponse('/login')
    calendar_tool = CalendarTool(credentials)
    return JSONResponse(content={"free_slots": calendar_tool.find_free_slots()})

