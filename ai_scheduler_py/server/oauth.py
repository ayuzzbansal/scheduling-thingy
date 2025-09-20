import os, datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlmodel import select
from .state import Token, get_session

router = APIRouter(prefix="/auth", tags=["auth"])

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI")

def _client_config():
    return {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }

@router.get("/google")
def auth_google(request: Request):
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session["oauth_state"] = state
    return RedirectResponse(auth_url)

@router.get("/callback")
def auth_callback(request: Request, state: str, code: str):
    saved_state = request.session.get("oauth_state")
    if not saved_state or saved_state != state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")

    flow = Flow.from_client_config(_client_config(), SCOPES, redirect_uri=REDIRECT_URI)
    flow.fetch_token(code=code)
    creds = flow.credentials  # type: Credentials

    # Figure out the user’s email via Gmail profile
    gmail = build("gmail", "v1", credentials=creds)
    profile = gmail.users().getProfile(userId="me").execute()
    user_email = profile["emailAddress"]

    # Persist tokens
    with get_session() as s:
        expiry_dt = datetime.datetime.fromtimestamp(creds.expiry.timestamp())
        existing = s.get(Token, user_email)
        if existing:
            existing.access_token = creds.token
            existing.refresh_token = creds.refresh_token or existing.refresh_token
            existing.expiry = expiry_dt
        else:
            s.add(Token(user_email=user_email,
                        access_token=creds.token,
                        refresh_token=creds.refresh_token,
                        expiry=expiry_dt))
        s.commit()

    return RedirectResponse(url=f"/me")

def load_user_credentials(user_email: str) -> Credentials:
    with get_session() as s:
        t = s.get(Token, user_email)
        if not t:
            raise RuntimeError("No tokens stored for user")
        creds = Credentials(
            token=t.access_token,
            refresh_token=t.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES,
        )
        # Refresh if needed
        if not creds.valid and creds.refresh_token:
            from google.auth.transport.requests import Request as GRequest
            creds.refresh(GRequest())
            # persist refreshed token
            t.access_token = creds.token
            t.expiry = datetime.datetime.fromtimestamp(creds.expiry.timestamp())
            s.add(t); s.commit()
        return creds
