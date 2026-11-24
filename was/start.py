"""WAS 진입점.

    uvicorn start:app --reload --port 8000
"""
from app.application import Application

app = Application().api
