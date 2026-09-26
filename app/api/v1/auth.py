"""
Authentication & User Management Router.
"""

from typing import Optional

from fastapi import APIRouter, Depends, status
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_password_reset_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    PasswordForgotRequest,
    PasswordForgotResponse,
    PasswordResetRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=ApiResponse[UserResponse], status_code=status.HTTP_201_CREATED)
async def register(req: UserRegisterRequest, db: AsyncSession = Depends(get_db)):
    """Registers a new user account."""
    stmt = select(User).where(User.email == req.email.lower())
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise ConflictError("An account with this email address already exists.")

    user = User(
        email=req.email.lower(),
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return ApiResponse(
        message="Account registered successfully.",
        data=UserResponse.model_validate(user),
    )


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(req: UserLoginRequest, db: AsyncSession = Depends(get_db)):
    """Authenticates credentials and returns JWT access and refresh tokens."""
    stmt = select(User).where(User.email == req.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("Your account has been deactivated.")

    access_token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "is_admin": user.is_admin},
    )
    refresh_token = create_refresh_token(subject=user.id)

    return ApiResponse(
        message="Login successful.",
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
    )


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_tokens(req: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    """Exchanges a valid refresh token for a new access token and renewed refresh token."""
    payload = decode_refresh_token(req.refresh_token)
    user_id = int(payload.get("sub", 0))

    stmt = select(User).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user:
        raise AuthenticationError("User not found.")
    if not user.is_active:
        raise AuthenticationError("User account has been deactivated.")

    new_access_token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "is_admin": user.is_admin},
    )
    new_refresh_token = create_refresh_token(subject=user.id)

    return ApiResponse(
        message="Tokens refreshed successfully.",
        data=TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            expires_in_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_profile(user: User = Depends(get_current_user)):
    """Retrieves authenticated user profile."""
    return ApiResponse(
        data=UserResponse.model_validate(user)
    )


@router.patch("/me", response_model=ApiResponse[UserResponse])
async def update_current_user_profile(
    req: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates authenticated user profile (e.g. full_name)."""
    if req.full_name is not None:
        user.full_name = req.full_name.strip()

    await db.commit()
    await db.refresh(user)

    return ApiResponse(
        message="Profile updated successfully.",
        data=UserResponse.model_validate(user),
    )


@router.delete("/me", response_model=ApiResponse[None])
async def delete_current_user_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Deletes the authenticated user account and all associated wallet data.
    Required for Google Play & Apple App Store compliance.
    """
    await db.delete(user)
    await db.commit()

    return ApiResponse(
        message="Account and all associated data deleted successfully.",
        data=None,
    )


@router.post("/password/forgot", response_model=ApiResponse[PasswordForgotResponse])
async def forgot_password(
    req: PasswordForgotRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiates password reset flow by verifying email and generating a secure reset token.
    In testing/development, the reset_token is returned in response.
    """
    stmt = select(User).where(User.email == req.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    reset_token: Optional[str] = None
    if user and user.is_active:
        token = create_password_reset_token(email=user.email)
        logger.info(f"Password reset issued for user_id={user.id}")
        # Development returns the token because email delivery is not wired yet.
        # Production keeps the response generic so the token cannot be harvested.
        if not settings.is_production:
            reset_token = token

    return ApiResponse(
        message="If this email is registered, password reset instructions have been issued.",
        data=PasswordForgotResponse(
            message="Password reset instructions issued.",
            reset_token=reset_token,
        ),
    )


@router.post("/password/reset", response_model=ApiResponse[None])
async def reset_password(
    req: PasswordResetRequest,
    db: AsyncSession = Depends(get_db),
):
    """Resets user password using a valid password reset token."""
    payload = decode_password_reset_token(req.token)
    email = payload.get("sub")
    if not email:
        raise AuthenticationError("Invalid reset token payload.")

    stmt = select(User).where(User.email == email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("Account not found or inactive.")

    user.hashed_password = hash_password(req.new_password)
    await db.commit()

    return ApiResponse(
        message="Password has been reset successfully. You may now log in with your new password.",
        data=None,
    )

