from fastapi import FastAPI, Request

from app.auth import AuthService
from app.db import Database

app = FastAPI()
db = Database()
auth_service = AuthService(db)


@app.post("/login")
def login(request: Request):
    """Login endpoint. Delegates to AuthService."""
    body = request.json()
    token = auth_service.authenticate_user(body["username"], body["password"])
    if token is None:
        return {"error": "invalid credentials"}
    return {"token": token}


@app.get("/health")
def health_check():
    return {"status": "ok"}
