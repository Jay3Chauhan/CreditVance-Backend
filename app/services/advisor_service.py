"""
Smart Advisor Recommendation Engine.
Solves: "I have 5+ cards. Which card should I use right now for this purchase?"
Ranks user's cards based on category multipliers, base returns, exclusions, and forex markups.
"""

from typing import Any, Dict, List, Optional
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from loguru import logger
from app.models.card import CreditCard
from app.models.card_tab import CardTab
from app.models.user_card import UserCard
from app.schemas.advisor import (
    CardRecommendationRequest,
    CardRecommendationResponse,
    RecommendedCardItem,
)


class AdvisorService:
    """Intelligent recommendation engine for card selection."""

    def _evaluate_card_return(
        self,
        card: CreditCard,
        earn_tab_content: Optional[Dict[str, Any]],
        category_slug: str,
        spend_amount: float,
        is_international: bool = False,
    ) -> tuple[float, float, float, str, Optional[str], float]:
        """
        Evaluates a card against a category and spend amount.
        Returns: (reward_points, net_reward_value_inr, effective_return_pct, highlight, exclusion_note, forex_markup_applied)
        """
        category_lower = category_slug.lower()
        exclusion_note: Optional[str] = None
        points = 0.0
        gross_value_inr = 0.0
        point_val = 0.25  # Standard default point valuation in INR

        if "infinia" in card.slug or "black" in card.slug:
            point_val = 1.00
        elif "atlas" in card.slug or "regalia" in card.slug:
            point_val = 0.50
        elif "cashback" in card.slug:
            point_val = 1.00
        elif card.point_value_inr:
            point_val = card.point_value_inr

        # Calculate forex markup to apply (including 18% GST)
        forex_markup_applied = 0.0
        if is_international and card.forex_markup_percent:
            forex_markup_applied = round(card.forex_markup_percent * 1.18, 2)

        # 1. Check exclusions in tab data
        if earn_tab_content and "tabData" in earn_tab_content:
            tab_data = earn_tab_content.get("tabData", {})
            exclusions = tab_data.get("exclusions", [])
            for excl in exclusions:
                excl_name = (excl.get("name") or "").lower()
                excl_cat = (excl.get("category") or "").lower()
                if category_lower in excl_name or category_lower in excl_cat:
                    exclusion_note = f"Category '{category_slug}' is an excluded spend on this card (0 rewards)."
                    return 0.0, 0.0, 0.0, "Zero rewards on this category", exclusion_note, forex_markup_applied

            # 2. Check accelerated earn rows
            earn_rows = tab_data.get("earnRows", [])
            
            # If international transaction, check for international specific earn rows first
            matched_row = None
            if is_international:
                for row in earn_rows:
                    r_cat = (row.get("category") or "").lower()
                    r_sub = (row.get("subCategory") or "").lower()
                    r_name = (row.get("name") or "").lower()
                    if "international" in r_cat or "international" in r_sub or "international" in r_name:
                        matched_row = row
                        break

            # If no international row matched, match requested category
            if not matched_row:
                for row in earn_rows:
                    r_cat = (row.get("category") or "").lower()
                    r_sub = (row.get("subCategory") or "").lower()
                    r_name = (row.get("name") or "").lower()
                    if (
                        category_lower in r_cat
                        or category_lower in r_sub
                        or category_lower in r_name
                    ):
                        matched_row = row
                        break

            if matched_row:
                pts_per_unit = float(matched_row.get("points") or 0.0)
                per_amt = float(matched_row.get("per") or 100.0)
                if per_amt > 0:
                    points = (spend_amount / per_amt) * pts_per_unit
                    gross_value_inr = points * point_val
                    gross_eff_pct = (gross_value_inr / spend_amount) * 100.0

                    forex_cost_inr = round(spend_amount * (forex_markup_applied / 100.0), 2)
                    net_value_inr = round(max(0.0, gross_value_inr - forex_cost_inr), 2)
                    eff_pct = round(max(0.0, gross_eff_pct - forex_markup_applied), 2)

                    row_label = matched_row.get("name") or category_slug
                    highlight = f"Accelerated: {pts_per_unit} pts per ₹{int(per_amt)} on {row_label}"
                    if is_international and forex_markup_applied > 0:
                        highlight += f" (net of {forex_markup_applied}% forex markup)"

                    return points, net_value_inr, eff_pct, highlight, None, forex_markup_applied

        # 3. Fallback to base return percentage
        base_pct = card.return_max_percent if card.return_max_percent > 0 else card.return_min_percent
        if base_pct <= 0:
            base_pct = 1.0  # Conservative 1% fallback

        gross_value_inr = (spend_amount * base_pct) / 100.0
        points = gross_value_inr / point_val

        forex_cost_inr = round(spend_amount * (forex_markup_applied / 100.0), 2)
        net_value_inr = round(max(0.0, gross_value_inr - forex_cost_inr), 2)
        eff_pct = round(max(0.0, base_pct - forex_markup_applied), 2)

        highlight = f"Base reward rate: ~{base_pct:.1f}% return"
        if is_international and forex_markup_applied > 0:
            highlight += f" (net of {forex_markup_applied}% forex markup)"

        return round(points, 1), net_value_inr, eff_pct, highlight, None, forex_markup_applied

    async def get_recommendation_for_user(
        self,
        db: AsyncSession,
        user_id: int,
        req: CardRecommendationRequest,
    ) -> CardRecommendationResponse:
        evaluated_items: List[RecommendedCardItem] = []
        insights: List[str] = []

        # Case A: Explicit card IDs passed in request (e.g. Guest mode or explicit card selection)
        if req.card_ids:
            stmt = (
                select(CreditCard)
                .options(
                    selectinload(CreditCard.bank),
                    selectinload(CreditCard.tabs),
                )
                .where(CreditCard.id.in_(req.card_ids))
            )
            cards = (await db.execute(stmt)).scalars().all()

            # If user is authenticated, also check if user has custom nicknames for these cards
            user_holdings_map: Dict[int, UserCard] = {}
            if user_id > 0:
                uc_stmt = (
                    select(UserCard)
                    .where(UserCard.user_id == user_id, UserCard.card_id.in_(req.card_ids))
                )
                user_cards = (await db.execute(uc_stmt)).scalars().all()
                for uc in user_cards:
                    user_holdings_map[uc.card_id] = uc

            for c in cards:
                earn_tab = next(
                    (t.raw_content for t in c.tabs if t.tab_name == "earn-categories"),
                    None,
                )
                pts, val, eff_pct, highlight, excl, forex_applied = self._evaluate_card_return(
                    card=c,
                    earn_tab_content=earn_tab,
                    category_slug=req.category_slug,
                    spend_amount=req.spend_amount,
                    is_international=req.is_international,
                )

                uc = user_holdings_map.get(c.id)
                evaluated_items.append(
                    RecommendedCardItem(
                        user_card_id=uc.id if uc else None,
                        card_id=c.id,
                        card_title=c.title,
                        card_slug=c.slug,
                        bank_name=c.bank.name if c.bank else "Bank",
                        bank_logo_url=c.bank.logo_url if c.bank else None,
                        card_image_url=c.card_image_url or c.web_logo_url,
                        nickname=uc.nickname if uc and uc.nickname else c.display_name,
                        last_4_digits=uc.last_4_digits if uc else None,
                        rank=1,
                        estimated_reward_points=pts,
                        estimated_reward_value_inr=val,
                        effective_return_percent=eff_pct,
                        forex_markup_applied=forex_applied,
                        reward_type="cashback" if "cashback" in c.slug else "points",
                        benefit_highlight=highlight,
                        notes_or_exclusions=excl,
                    )
                )

        # Case B: Authenticated user querying their stored wallet cards
        elif user_id > 0:
            stmt = (
                select(UserCard)
                .options(
                    selectinload(UserCard.card).selectinload(CreditCard.bank),
                    selectinload(UserCard.card).selectinload(CreditCard.tabs),
                )
                .where(UserCard.user_id == user_id, UserCard.is_active == True)
            )
            user_cards = (await db.execute(stmt)).scalars().all()

            if not user_cards:
                insights.append(
                    "You haven't added any cards to your wallet yet. Displaying market benchmark recommendations."
                )
            else:
                for uc in user_cards:
                    c = uc.card
                    earn_tab = next(
                        (t.raw_content for t in c.tabs if t.tab_name == "earn-categories"),
                        None,
                    )

                    pts, val, eff_pct, highlight, excl, forex_applied = self._evaluate_card_return(
                        card=c,
                        earn_tab_content=earn_tab,
                        category_slug=req.category_slug,
                        spend_amount=req.spend_amount,
                        is_international=req.is_international,
                    )

                    evaluated_items.append(
                        RecommendedCardItem(
                            user_card_id=uc.id,
                            card_id=c.id,
                            card_title=c.title,
                            card_slug=c.slug,
                            bank_name=c.bank.name if c.bank else "Bank",
                            bank_logo_url=c.bank.logo_url if c.bank else None,
                            card_image_url=c.card_image_url or c.web_logo_url,
                            nickname=uc.nickname or c.display_name,
                            last_4_digits=uc.last_4_digits,
                            rank=1,
                            estimated_reward_points=pts,
                            estimated_reward_value_inr=val,
                            effective_return_percent=eff_pct,
                            forex_markup_applied=forex_applied,
                            reward_type="cashback" if "cashback" in c.slug else "points",
                            benefit_highlight=highlight,
                            notes_or_exclusions=excl,
                        )
                    )

        # Case C: Unauthenticated guest without explicit card_ids
        else:
            insights.append(
                "Guest recommendation mode. Add cards to your wallet or supply card_ids to rank your cards."
            )

        # Sort evaluated cards by estimated monetary return descending
        evaluated_items.sort(key=lambda x: x.estimated_reward_value_inr, reverse=True)
        for i, item in enumerate(evaluated_items):
            item.rank = i + 1

        top_rec = evaluated_items[0] if evaluated_items else None
        alternatives = evaluated_items[1:] if len(evaluated_items) > 1 else []

        if top_rec:
            insights.append(
                f"Use '{top_rec.nickname}' for a projected return of ₹{top_rec.estimated_reward_value_inr:.2f} ({top_rec.effective_return_percent}% effective return)."
            )
            if req.is_international and top_rec.forex_markup_applied > 0:
                insights.append(
                    f"Deducted {top_rec.forex_markup_applied}% forex markup (inclusive of 18% GST) for foreign currency spend."
                )

        # 2. Find Overall Market Benchmark Card
        benchmark_stmt = (
            select(CreditCard)
            .options(selectinload(CreditCard.bank), selectinload(CreditCard.tabs))
            .where(CreditCard.is_currently_issuing == True)
            .order_by(desc(CreditCard.return_max_percent))
            .limit(5)
        )
        market_cards = (await db.execute(benchmark_stmt)).scalars().all()

        market_benchmark: Optional[RecommendedCardItem] = None
        if market_cards:
            best_m = market_cards[0]
            m_tab = next(
                (t.raw_content for t in best_m.tabs if t.tab_name == "earn-categories"),
                None,
            )
            m_pts, m_val, m_eff_pct, m_hl, _, m_forex = self._evaluate_card_return(
                best_m, m_tab, req.category_slug, req.spend_amount, req.is_international
            )
            market_benchmark = RecommendedCardItem(
                card_id=best_m.id,
                card_title=best_m.title,
                card_slug=best_m.slug,
                bank_name=best_m.bank.name if best_m.bank else "Bank",
                bank_logo_url=best_m.bank.logo_url if best_m.bank else None,
                card_image_url=best_m.card_image_url or best_m.web_logo_url,
                rank=1,
                estimated_reward_points=m_pts,
                estimated_reward_value_inr=m_val,
                effective_return_percent=m_eff_pct,
                forex_markup_applied=m_forex,
                benefit_highlight=m_hl,
            )

        return CardRecommendationResponse(
            category_slug=req.category_slug,
            spend_amount=req.spend_amount,
            top_recommendation=top_rec,
            alternative_cards=alternatives,
            market_benchmark_card=market_benchmark,
            insights=insights,
        )


# Global Singleton Advisor Service
advisor_service = AdvisorService()
