"""Protects the AI service so only our Node backend can call it.

The AI service is internal. Browsers never talk to it. The backend sends a
secret value in the header "X-Service-Key"; we compare it with AI_SERVICE_KEY
from the .env file.
"""
import hmac
import os

from dotenv import load_dotenv
from fastapi import Header, HTTPException

load_dotenv()


def require_service_key(x_service_key: str = Header(default="")) -> None:
    expected = os.getenv("AI_SERVICE_KEY", "")
    if not expected:
        # Fail closed: if no key is configured, refuse everything
        raise HTTPException(status_code=503, detail="AI_SERVICE_KEY is not configured")
    # compare_digest takes the same time for right and wrong keys (stops timing attacks)
    if not hmac.compare_digest(x_service_key.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Invalid service key")
