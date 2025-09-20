from sqlmodel import Session, select
from models.db_models import Message
from typing import List

def get_thread_history(session: Session, thread_id: str, max_messages: int = 10) -> str:
    results = session.exec(
        select(Message)
        .where(Message.thread_id == thread_id)
        .order_by(Message.timestamp)
        .limit(max_messages)
    ).all()

    if not results:
        return "No messages found for this thread."

    history: List[str] = []

    for msg in results:
        formatted = f"{msg.timestamp.strftime('%Y-%m-%d %H:%M')} - {msg.sender}:\n{msg.content.strip()}\n"
        history.append(formatted)

    return "\n".join(history)
