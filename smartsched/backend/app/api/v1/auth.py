from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DB, CurrentUser
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models import User
from app.schemas.auth import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, db: DB) -> TokenOut:
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalar_one_or_none()
    if user is None or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "user disabled")
    token = create_access_token(user.email, {"uid": user.id, "role": user.role})
    return TokenOut(access_token=token, expires_in=get_settings().jwt_expire_minutes * 60)


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> User:
    return user
