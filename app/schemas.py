"""Request/response validation models."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, Field, field_validator

from app.services.fares import CLASS_LABELS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")
CODE_RE = re.compile(r"^[A-Z0-9]{1,6}$")


def _code(v: str) -> str:
    v = v.strip().upper()
    if not CODE_RE.match(v):
        raise ValueError("Invalid station or train code")
    return v


class RegisterIn(BaseModel):
    email: str = Field(max_length=254)
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address")
        return v

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        v = " ".join(v.split())
        if not v:
            raise ValueError("Name is required")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        if v.isdigit() or v.isalpha():
            raise ValueError("Password must mix letters and numbers/symbols")
        return v


class LoginIn(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 (OAuth token type, not a secret)
    user: dict


class TripLegIn(BaseModel):
    train_number: str
    from_code: str
    to_code: str

    @field_validator("train_number", "from_code", "to_code")
    @classmethod
    def normalise(cls, v: str) -> str:
        return _code(v)


class TripIn(BaseModel):
    legs: list[TripLegIn] = Field(min_length=1, max_length=2)
    travel_date: date
    travel_class: str
    passengers: int = Field(1, ge=1, le=6)
    note: str = Field("", max_length=200)

    @field_validator("travel_class")
    @classmethod
    def valid_class(cls, v: str) -> str:
        if v not in CLASS_LABELS:
            raise ValueError(f"travel_class must be one of {list(CLASS_LABELS)}")
        return v

    @field_validator("travel_date")
    @classmethod
    def not_past(cls, v: date) -> date:
        if v < date.today():
            raise ValueError("Travel date cannot be in the past")
        return v

    @field_validator("note")
    @classmethod
    def clean_note(cls, v: str) -> str:
        return " ".join(v.split())
