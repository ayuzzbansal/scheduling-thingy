import base64, html, quopri
from typing import List, Dict, Tuple, Optional
from email.message import EmailMessage
from googleapiclient.discovery import build
from .oauth import load_user_credentials

# ----- Build Gmail service for a user
def gmail_service(user_email: str):
    creds = load_user_credentials(user_email)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)

# ----- Labels (get or create) -----
def _ensure_label(service, name: str) -> str:
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for lb in labels:
        if lb["name"] == name:
            return lb["id"]
    body = {
        "name": name,
        "labelListVisibility": "labelShow",
        "messageListVisibility": "show",
    }
    created = service.users().labels().create(userId="me", body=body).execute()
    return created["id"]

def add_labels(service, msg_id: str, add: List[str], remove: Optional[List[str]] = None) -> None:
    add_ids = [_ensure_label(service, n) for n in add]
    rem_ids = []
    if remove:
        # map names to ids if they exist
        existing = service.users().labels().list(userId="me").execute().get("labels", [])
        name2id = {lb["name"]: lb["id"] for lb in existing}
        rem_ids = [name2id[n] for n in remove if n in name2id]
    body = {"addLabelIds": add_ids, "removeLabelIds": rem_ids}
    service.users().messages().modify(userId="me", id=msg_id, body=body).execute()

# ----- List unread (with a helpful default query) -----
def list_unread(service, q: str = 'label:INBOX is:unread -in:chats -category:promotions -category:social') -> List[Dict]:
    res = service.users().messages().list(userId="me", q=q, maxResults=10).execute()
    return res.get("messages", []) or []

# ----- Helper: decode payload to plaintext -----
def _decode_part(data_b64: str, charset: Optional[str]) -> str:
    raw = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:  # unknown charset
        return raw.decode("utf-8", errors="replace")

def _extract_body(payload: Dict) -> str:
    # Try text/plain first, fall back to text/html (strip tags rudimentarily)
    def walk(parts):
        for p in parts:
            mime = p.get("mimeType", "")
            body = p.get("body", {})
            data = body.get("data")
            if mime == "text/plain" and data:
                return _decode_part(data, p.get("headers", [{}]))
            if "parts" in p:
                inner = walk(p["parts"])
                if inner:
                    return inner
            if mime == "text/html" and data:
                html_text = _decode_part(data, None)
                # rudimentary HTML → text
                import re
                text = re.sub(r"<br\s*/?>", "\n", html_text, flags=re.I)
                text = re.sub(r"<[^>]+>", "", text)
                return html.unescape(text)
        return None

    if "parts" in payload:
        txt = walk(payload["parts"])
        if txt:
            return txt
    # Sometimes message has only body.data at root
    data = payload.get("body", {}).get("data")
    if data:
        return _decode_part(data, None)
    return ""

def get_message_full(service, msg_id: str) -> Dict:
    m = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
    subject = headers.get("subject", "")
    from_ = headers.get("from", "")
    message_id = headers.get("message-id") or headers.get("message-id".capitalize()) or ""
    thread_id = m.get("threadId")
    body = _extract_body(m["payload"])
    return {
        "id": m["id"],
        "threadId": thread_id,
        "from": from_,
        "subject": subject,
        "message_id": message_id,
        "body": body.strip(),
    }

# ----- Build a reply MIME and send (in-thread) -----
def _build_reply_mime(to_addr: str, subject: str, html_body: str, in_reply_to: Optional[str]) -> str:
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["Subject"] = subject
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(html_body, subtype="html")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
    return raw

def send_reply_raw(service, raw_b64: str, thread_id: Optional[str] = None) -> None:
    body = {"raw": raw_b64}
    if thread_id:
        body["threadId"] = thread_id
    service.users().messages().send(userId="me", body=body).execute()
