from typing import Optional, List
from sqlmodel import SQLModel, Field, JSON
from datetime import datetime

class Message(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    thread_id: str = Field(index=True)
    sender: Optional[str] = None
    subject: Optional[str] = None
    content: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Thread(SQLModel, table=True):
    thread_id: str = Field(primary_key=True, index=True)
    status: str = Field(default="new")
    negotiation_count: int = Field(default=0)
    proposed_times: Optional[List[dict]] = Field(
        default=None, sa_column=JSON()
    )
    owner_approval: bool = Field(default=False)
    requester_email: Optional[str] = None
    owner_email: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
﻿