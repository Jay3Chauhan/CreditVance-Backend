"""
Admin create, update, and delete for banners and promotions.
Protected by X-Admin-API-Key or an admin user JWT.
"""

from typing import List

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, verify_admin_key
from app.schemas.common import ApiResponse
from app.schemas.content import (
    BannerResponse,
    BannerUpdateRequest,
    BannerWriteRequest,
    PromotionResponse,
    PromotionUpdateRequest,
    PromotionWriteRequest,
)
from app.services.content_service import content_service

router = APIRouter(prefix="/admin/content", tags=["Admin Content"])


@router.get("/banners", response_model=ApiResponse[List[BannerResponse]])
async def admin_list_banners(
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Every banner, including inactive and expired rows."""
    items = await content_service.list_banners(db, include_inactive=True)
    return ApiResponse(data=items)


@router.post("/banners", response_model=ApiResponse[BannerResponse], status_code=status.HTTP_201_CREATED)
async def admin_create_banner(
    req: BannerWriteRequest,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    created = await content_service.create_banner(db, req)
    return ApiResponse(message="Banner created.", data=created)


@router.patch("/banners/{banner_id}", response_model=ApiResponse[BannerResponse])
async def admin_update_banner(
    banner_id: int,
    req: BannerUpdateRequest,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    updated = await content_service.update_banner(db, banner_id, req)
    return ApiResponse(message="Banner updated.", data=updated)


@router.delete("/banners/{banner_id}", response_model=ApiResponse[None])
async def admin_delete_banner(
    banner_id: int,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    await content_service.delete_banner(db, banner_id)
    return ApiResponse(message="Banner deleted.", data=None)


@router.get("/promotions", response_model=ApiResponse[List[PromotionResponse]])
async def admin_list_promotions(
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    """Every promotion, including inactive and expired rows."""
    items = await content_service.list_promotions(db, include_inactive=True)
    return ApiResponse(data=items)


@router.post(
    "/promotions",
    response_model=ApiResponse[PromotionResponse],
    status_code=status.HTTP_201_CREATED,
)
async def admin_create_promotion(
    req: PromotionWriteRequest,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    created = await content_service.create_promotion(db, req)
    return ApiResponse(message="Promotion created.", data=created)


@router.patch("/promotions/{promotion_id}", response_model=ApiResponse[PromotionResponse])
async def admin_update_promotion(
    promotion_id: int,
    req: PromotionUpdateRequest,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    updated = await content_service.update_promotion(db, promotion_id, req)
    return ApiResponse(message="Promotion updated.", data=updated)


@router.delete("/promotions/{promotion_id}", response_model=ApiResponse[None])
async def admin_delete_promotion(
    promotion_id: int,
    authorized: bool = Depends(verify_admin_key),
    db: AsyncSession = Depends(get_db),
):
    await content_service.delete_promotion(db, promotion_id)
    return ApiResponse(message="Promotion deleted.", data=None)
