"""
Reward Calculator API Router.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_db
from app.schemas.calculator import (
    AnnualCalculatorRequest,
    AnnualCalculatorResponse,
    RewardCalculateRequest,
    RewardCalculateResponse,
)
from app.schemas.common import ApiResponse
from app.services.calculator_service import calculator_service

router = APIRouter(prefix="/calculator", tags=["Reward Calculator"])


@router.post("/calculate", response_model=ApiResponse[RewardCalculateResponse])
async def calculate_reward(
    req: RewardCalculateRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Computes reward points, monetary value in INR, and comparison savings
    against optimal market cards for any card and spend category.
    """
    result = await calculator_service.calculate_reward(db, req)
    return ApiResponse(
        message="Reward calculation completed.",
        data=result,
    )


@router.post("/annual", response_model=ApiResponse[AnnualCalculatorResponse])
async def calculate_annual_reward(
    req: AnnualCalculatorRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Computes comprehensive annual reward breakdown across multiple categories,
    evaluating fee waiver status and net portfolio return.
    """
    result = await calculator_service.calculate_annual_reward(db, req)
    return ApiResponse(
        message="Annual reward calculation completed successfully.",
        data=result,
    )

