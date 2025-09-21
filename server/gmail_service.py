import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build

class GmailTool:
    """A tool for interacting with the Gmail API."""
    def __init__(self, credentials):
        self.service = build('gmail', 'v1', credentials=credentials)

    def get_user_email(self):
        """Gets the authenticated user's primary email address."""
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return profile.get('emailAddress')
        except Exception as e:
            print(f"An error occurred getting user email: {e}")
            return None

    def list_recent_emails(self, count=5):
        """Lists the most recent emails."""
        results = self.service.users().messages().list(userId='me', maxResults=count).execute()
        messages = results.get('messages', [])
        
        email_list = []
        for message in messages:
            msg = self.service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload']['headers']
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'N/A')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), 'N/A')
            email_list.append({
                "id": msg['id'],
                "threadId": msg['threadId'],
                "subject": subject,
                "from": sender,
                "snippet": msg['snippet']
            })
        return email_list

    def get_latest_email(self):
        """Gets the single most recent email, including sender and thread ID."""
        results = self.service.users().messages().list(userId='me', maxResults=1).execute()
        messages = results.get('messages', [])
        if not messages:
            return None
        
        msg_id = messages[0]['id']
        msg = self.service.users().messages().get(userId='me', id=msg_id).execute()
        headers = msg['payload']['headers']
        
        sender_header = next((h['value'] for h in headers if h['name'] == 'From'), '')
        # Extract just the email from a "Name <email@example.com>" format
        sender_email = sender_header.split('<')[-1].strip('>') if '<' in sender_header else sender_header

        return {
            "id": msg_id,
            "thread_id": msg['threadId'],
            "sender": sender_email,
            "subject": next((h['value'] for h in headers if h['name'] == 'Subject'), 'N/A')
        }
        
    def get_email_body(self, msg_id):
        """Gets the plain text body of a specific email."""
        msg = self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        payload = msg['payload']
        body = ""

        if "parts" in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data')
                    if data:
                        body = base64.urlsafe_b64decode(data).decode('utf-8')
                        break
        elif 'body' in payload and payload['body'].get('data'):
            data = payload['body'].get('data')
            body = base64.urlsafe_b64decode(data).decode('utf-8')
        
        return body

    def send_reply(self, to, subject, message_text, thread_id):
        """Sends a reply email within a specific thread."""
        message = MIMEText(message_text)
        message['to'] = to
        message['subject'] = subject
        
        create_message = {
            'raw': base64.urlsafe_b64encode(message.as_bytes()).decode(),
            'threadId': thread_id
        }
        
        sent_message = self.service.users().messages().send(userId='me', body=create_message).execute()
        print(f"Reply sent to {to}, Message ID: {sent_message['id']}")

