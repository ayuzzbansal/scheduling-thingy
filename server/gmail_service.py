from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText

class GmailTool:
    """A tool for interacting with the Gmail API."""

    def __init__(self, credentials):
        """
        Initializes the GmailTool with user credentials.
        Args:
            credentials: The OAuth 2.0 credentials for the user.
        """
        self.service = build('gmail', 'v1', credentials=credentials)

    def list_recent_emails(self):
        """Lists the 5 most recent emails from the user's inbox."""
        try:
            results = self.service.users().messages().list(userId='me', labelIds=['INBOX'], maxResults=5).execute()
            messages = results.get('messages', [])

            email_list = []
            if not messages:
                return "No messages found."
            else:
                for message in messages:
                    msg = self.service.users().messages().get(userId='me', id=message['id']).execute()
                    payload = msg['payload']
                    headers = payload.get("headers")
                    
                    subject = next((header['value'] for header in headers if header['name'] == 'Subject'), 'No Subject')
                    sender = next((header['value'] for header in headers if header['name'] == 'From'), 'Unknown Sender')
                    
                    email_list.append({
                        "id": msg['id'],
                        "threadId": msg['threadId'],
                        "subject": subject,
                        "from": sender,
                        "snippet": msg['snippet']
                    })
            return email_list
        except HttpError as error:
            return f"An error occurred with the Gmail API: {error}"

    def get_email_body(self, message_id):
        """
        Gets the full plain text body of a specific email.
        Args:
            message_id: The ID of the email message to retrieve.
        Returns:
            The decoded email body as a string, or an error message.
        """
        try:
            message = self.service.users().messages().get(userId='me', id=message_id, format='full').execute()
            payload = message['payload']
            email_body = ""

            if "parts" in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        data = part['body'].get('data')
                        if data:
                            email_body = base64.urlsafe_b64decode(data).decode('utf-8')
                            return email_body
            elif 'body' in payload and payload['body'].get('data'):
                data = payload['body'].get('data')
                email_body = base64.urlsafe_b64decode(data).decode('utf-8')
                return email_body
            
            return "Could not extract plain text content from the email."

        except HttpError as error:
            return f"An error occurred while fetching the email body: {error}"

    def send_reply(self, subject, body, to_email):
        """
        Creates and sends an email reply on behalf of the user.
        Args:
            subject: The subject line of the email.
            body: The plain text body of the email.
            to_email: The recipient's email address.
        Returns:
            The sent message object or an error string.
        """
        try:
            message = MIMEText(body)
            message['to'] = to_email
            message['from'] = 'me' 
            message['subject'] = subject
            
            encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            create_message = {'raw': encoded_message}
            
            send_message = self.service.users().messages().send(userId="me", body=create_message).execute()
            print(f'Message Id: {send_message["id"]}')
            return send_message
        except HttpError as error:
            return f"An error occurred while sending the email: {error}"

