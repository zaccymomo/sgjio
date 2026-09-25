"""Request and response shapes shared across routers."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import UserRole, UserType


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    role: UserRole
    user_type: UserType | None
    created_at: datetime


class SignInRequest(BaseModel):
    # Not validated as an email on purpose: any wrong input gets the same general
    # "email or password is incorrect" message (SCRUM-62 AC2, SCRUM-68 AC2).
    email: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)


class SignInResponse(BaseModel):
    user: UserOut


class ErrorDetail(BaseModel):
    """Shape of `detail` in every error response the front ends need to understand."""

    code: str
    message: str
