import os
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from googleapiclient.discovery import build
from .state import init_db
from .oauth import router as oauth_router, load_user_credentials
from .gmail_api import gmail_service, list_unread, get_message_full, add_labels, _build_reply_mime, send_reply_raw

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev"))

app.include_router(oauth_router)

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/me")
def me():
    # Who am I? (uses whichever user you last authorized)
    # For multi-user, store selected email in session; for MVP, fetch from tokens table.
    # Here we just try to read profile using the first token we find.
    from .state import get_session, Token
    with get_session() as s:
        t = s.exec(Token.__table__.select()).first()
        if not t:
            return {"connected": False}
        creds = load_user_credentials(t.user_email)
        gmail = build("gmail", "v1", credentials=creds)
        profile = gmail.users().getProfile(userId="me").execute()
        return {"connected": True, "email": profile["emailAddress"]}

@app.get("/gmail/list_unread")
def api_list_unread():
    from .state import get_session, Token
    with get_session() as s:
        t = s.exec(Token.__table__.select()).first()
        if not t:
            raise HTTPException(400, "No connected account. Go to /auth/google")
        svc = gmail_service(t.user_email)
    msgs = list_unread(svc)
    return {"count": len(msgs), "messages": msgs}

@app.get("/gmail/peek_one_and_reply")
def api_peek_and_reply():
    from .state import get_session, Token
    with get_session() as s:
        t = s.exec(Token.__table__.select()).first()
        if not t:
            raise HTTPException(400, "No connected account.")
        svc = gmail_service(t.user_email)

    msgs = list_unread(svc)
    if not msgs:
        return {"info": "No unread emails."}

    m = get_message_full(svc, msgs[0]["id"])
    # Mark as processing (create or use your labels)
    add_labels(svc, m["id"], add=["ai/processing"])

    # Build a polite reply IN THE SAME THREAD
    to_addr = m["from"]
    subject = f"Re: {m['subject']}".strip()
    html = f"""<p>Hi,</p>
               <p>This is a test automated reply confirming we can read and reply in-thread.</p>
               <p>Original snippet:<br/><pre>{m['body'][:200]}</pre></p>
               <p>—AI Scheduler (test)</p>"""
    raw = _build_reply_mime(to_addr=to_addr, subject=subject, html_body=html, in_reply_to=m["message_id"])
    send_reply_raw(svc, raw_b64=raw, thread_id=m["threadId"])

    # Done
    add_labels(svc, m["id"], add=["ai/finished"], remove=["ai/processing"])

    return {"replied_to": m["id"], "threadId": m["threadId"], "subject": m["subject"]}
