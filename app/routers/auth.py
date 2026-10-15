"""Registration, login and current-user endpoints."""

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.db import session
from app.deps import user_db
from app.schemas import LoginIn, RegisterIn, TokenOut
from app.security import create_token, current_user_id, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Verifying against a dummy hash keeps login timing similar for unknown emails
_DUMMY_HASH = hash_password("dummy-password-1")


def _token_response(request: Request, user: dict) -> TokenOut:
    s = request.app.state.settings
    token = create_token(user["id"], request.app.state.secret, s.token_minutes)
    return TokenOut(access_token=token, user={"id": user["id"], "name": user["name"], "email": user["email"]})


@router.post("/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterIn, request: Request, path=Depends(user_db)):
    try:
        with session(path) as conn:
            cur = conn.execute("INSERT INTO users (email, name, password_hash) VALUES (?, ?, ?)",
                               (body.email, body.name, hash_password(body.password)))
            user = {"id": cur.lastrowid, "name": body.name, "email": body.email}
    except sqlite3.IntegrityError:
        raise HTTPException(409, "An account with this email already exists") from None
    return _token_response(request, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, path=Depends(user_db)):
    with session(path) as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (body.email.strip().lower(),)).fetchone()
    stored = row["password_hash"] if row else _DUMMY_HASH
    if not verify_password(body.password, stored) or row is None:
        raise HTTPException(401, "Incorrect email or password")
    return _token_response(request, dict(row))


@router.get("/me")
def me(user_id: int = Depends(current_user_id), path=Depends(user_db)):
    with session(path) as conn:
        row = conn.execute("SELECT id, name, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None:
        raise HTTPException(401, "Account no longer exists")
    return dict(row)
