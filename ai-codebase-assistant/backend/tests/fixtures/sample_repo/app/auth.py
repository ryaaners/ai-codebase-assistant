"""Authentication module."""
import hashlib
from typing import Optional

from app.models import User
from app.db import Database


class AuthService:
    """Handles user authentication and session management."""

    def __init__(self, db: Database):
        self.db = db

    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """Validates credentials, checks the password hash, and returns a token."""
        user = self.db.find_user(username)
        if user is None:
            return None
        if not self._check_password(user, password):
            return None
        return self._create_session(user)

    def _check_password(self, user, password: str) -> bool:
        return hash_password(password) == user.password_hash

    def _create_session(self, user: User) -> str:
        token = generate_token(user.id)
        self.db.save_session(user.id, token)
        return token


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def generate_token(user_id: int) -> str:
    return hashlib.sha1(str(user_id).encode()).hexdigest()


def unused_helper():
    """Never called from anywhere in this fixture -- used to test dead code detection."""
    return 42
