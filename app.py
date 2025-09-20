from fastapi import FastAPI
from adapters.google_calender import get_free_slots, get_calendar_service
from google.oauth2.credentials import Credentials
import os, asyncio

app = FastAPI()

# Check if token.json exists, if not create a placeholder
if not os.path.exists("token.json"):
    print("Warning: token.json not found. Please set up Google Calendar API credentials.")
    creds = None
    cal_service = None
else:
    creds = Credentials.from_authorized_user_file("token.json")
    cal_service = get_calendar_service(creds)

@app.get("/free_slots")
async def free_slots_endpoint():
    if cal_service is None:
        return {"error": "Google Calendar API credentials not configured. Please set up token.json"}
    slots = await get_free_slots(cal_service, days=7)
    return {"free_slots": slots}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
