"""
Reward Calculator Service.
Computes offline reward points, monetary valuation, comparison against market leaders, and annual savings.
"""

from typing import Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.core.exceptions import NotFoundError
from app.models.card import CreditCard
from app.models.card_tab import CardTab
from app.schemas.calculator import (
    CardRewardSummary,
    RewardCalculateRequest,
    RewardCalculateResponse,
)
from app.services.advisor_service import advisor_service


class CalculatorService:
    """Offline reward calculation engine."""

    async def calculate_reward(
        self, db: AsyncSession, req: RewardCalculateRequest
    ) -> RewardCalculateResponse:
        # 1. Fetch User Selected Card
        stmt = (
            select(CreditCard)
            .options(selectinload(CreditCard.bank), selectinload(CreditCard.tabs))
            .where(CreditCard.id == req.card_id)
        )
        user_card_model = (await db.execute(stmt)).scalar_one_or_none()
        if not user_card_model:
            raise NotFoundError(f"Credit card with ID {req.card_id} not found.")

        # Find earn-categories tab
        earn_tab = next(
            (t.raw_content for t in user_card_model.tabs if t.tab_name == "earn-categories"),
            None,
        )

        pts, worth, ret_pct, _, _ = advisor_service._evaluate_card_return(
            card=user_card_model,
            earn_tab_content=earn_tab,
            category_slug=req.category_slug,
            spend_amount=req.spend_amount,
        )

        user_summary = CardRewardSummary(
            card_id=user_card_model.id,
            card_name=user_card_model.display_name,
            bank_name=user_card_model.bank.name if user_card_model.bank else "Bank",
            card_image_link=user_card_model.card_image_url or user_card_model.web_logo_url,
            reward_points=pts,
            reward_worth=worth,
            is_cashback_card="cashback" in user_card_model.slug,
            return_percentage=ret_pct,
        )

        # 2. Find Best Market Benchmark Card
        benchmark_stmt = (
            select(CreditCard)
            .options(selectinload(CreditCard.bank), selectinload(CreditCard.tabs))
            .where(CreditCard.is_currently_issuing == True)
            .order_by(desc(CreditCard.return_max_percent))
            .limit(1)
        )
        benchmark_card = (await db.execute(benchmark_stmt)).scalar_one_or_none()

        if benchmark_card and benchmark_card.id != user_card_model.id:
            b_tab = next(
                (t.raw_content for t in benchmark_card.tabs if t.tab_name == "earn-categories"),
                None,
            )
            b_pts, b_worth, b_pct, _, _ = advisor_service._evaluate_card_return(
                card=benchmark_card,
                earn_tab_content=b_tab,
                category_slug=req.category_slug,
                spend_amount=req.spend_amount,
            )
            suggested_summary = CardRewardSummary(
                card_id=benchmark_card.id,
                card_name=benchmark_card.display_name,
                bank_name=benchmark_card.bank.name if benchmark_card.bank else "Bank",
                card_image_link=benchmark_card.card_image_url or benchmark_card.web_logo_url,
                reward_points=b_pts,
                reward_worth=b_worth,
                is_cashback_card="cashback" in benchmark_card.slug,
                return_percentage=b_pct,
            )
            annual_savings = max(0.0, (b_worth - worth) * 12.0)
            suggested_is_same = False
        else:
            suggested_summary = user_summary
            annual_savings = 0.0
            suggested_is_same = True

        return RewardCalculateResponse(
            user_card=user_summary,
            suggested_card=suggested_summary,
            annual_savings=round(annual_savings, 2),
            suggested_card_is_same=suggested_is_same,
        )


# Global Singleton Calculator Service
calculator_service = CalculatorService()
