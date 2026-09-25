"""
Authentication & User Management Router.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas.auth import (
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
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
    """Authenticates credentials and returns a JWT access token."""
    stmt = select(User).where(User.email == req.email.lower())
    user = (await db.execute(stmt)).scalar_one_or_none()

    if not user or not verify_password(req.password, user.hashed_password):
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("Your account has been deactivated.")

    token = create_access_token(
        subject=user.id,
        extra_claims={"email": user.email, "is_admin": user.is_admin},
    )

    return ApiResponse(
        message="Login successful.",
        data=TokenResponse(
            access_token=token,
            expires_in_minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES,
        ),
    )


@router.get("/me", response_model=ApiResponse[UserResponse])
async def get_current_user_profile(user: User = Depends(get_current_user)):
    """Retrieves authenticated user profile."""
    return ApiResponse(
        data=UserResponse.model_validate(user)
    )
