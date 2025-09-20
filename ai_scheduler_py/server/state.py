from sqlmodel import Field, SQLModel, create_engine, Session, select
from datetime import datetime
from typing import Optional

DB_URL = "sqlite:///./data.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

class Token(SQLModel, table=True):
    user_email: str = Field(primary_key=True)
    access_token: str
    refresh_token: str
    expiry: datetime

def init_db():
    SQLModel.metadata.create_all(engine)

def get_session():
    return Session(engine)
