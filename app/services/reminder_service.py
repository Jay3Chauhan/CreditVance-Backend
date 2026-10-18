"""
Which wallet reminders are worth a push, and the copy those pushes use.
The in-app list still returns every upcoming date. Push only fires on the
offsets the user opted into (by default the due day, the day before, and 3 days before).
"""

from app.models.user_card import UserCard
from app.schemas.device_token import CardReminderItem
from app.services.billing import days_until_day_of_month

DEFAULT_DUE_REMINDER_DAYS = [0, 1, 3]
DEFAULT_STATEMENT_REMINDER_DAYS = [0, 1]


def build_reminders(user_cards: list[UserCard]) -> list[CardReminderItem]:
    """In-app reminder list. Same wording the wallet screen already expects."""
    reminders: list[CardReminderItem] = []
    for uc in user_cards:
        card = uc.card
        title = card.display_name if card else (uc.nickname or "Card")
        bank = card.bank.name if card and card.bank else "Bank"
        card_title = card.title if card else title
        nickname = uc.nickname or title

        if uc.due_day:
            diff_due = days_until_day_of_month(uc.due_day)
            if diff_due == 0:
                msg = f"Payment for {nickname} is due today!"
            elif diff_due <= 5:
                msg = f"Payment for {nickname} is due in {diff_due} days (Day {uc.due_day})."
            else:
                msg = f"Upcoming bill due on Day {uc.due_day} of each month."
            reminders.append(
                CardReminderItem(
                    user_card_id=uc.id,
                    nickname=nickname,
                    card_title=card_title,
                    bank_name=bank,
                    statement_day=uc.statement_day or uc.billing_cycle_day,
                    due_day=uc.due_day,
                    days_until_due=diff_due,
                    reminder_type="due_date",
                    message=msg,
                )
            )

        stmt_day = uc.statement_day or uc.billing_cycle_day
        if stmt_day:
            diff_stmt = days_until_day_of_month(stmt_day)
            if diff_stmt == 0:
                msg = f"Statement for {nickname} generates today!"
            elif diff_stmt <= 3:
                msg = f"Statement for {nickname} generates in {diff_stmt} days."
            else:
                msg = f"Statement generates on Day {stmt_day} of each month."
            reminders.append(
                CardReminderItem(
                    user_card_id=uc.id,
                    nickname=nickname,
                    card_title=card_title,
                    bank_name=bank,
                    statement_day=stmt_day,
                    due_day=uc.due_day,
                    days_until_statement=diff_stmt,
                    reminder_type="statement_date",
                    message=msg,
                )
            )

    reminders.sort(key=lambda item: min(item.days_until_due or 99, item.days_until_statement or 99))
    return reminders


def select_push_reminders(
    reminders: list[CardReminderItem],
    due_days: list[int],
    statement_days: list[int],
) -> list[CardReminderItem]:
    """Keep only reminders whose countdown matches a day the user wants pushed."""
    due_offsets = set(due_days)
    statement_offsets = set(statement_days)
    chosen: list[CardReminderItem] = []
    for item in reminders:
        if item.reminder_type == "due_date" and item.days_until_due in due_offsets:
            chosen.append(item)
        elif item.reminder_type == "statement_date" and item.days_until_statement in statement_offsets:
            chosen.append(item)
    return chosen


def push_title(item: CardReminderItem) -> str:
    name = item.nickname
    if item.reminder_type == "due_date":
        days = item.days_until_due or 0
        if days == 0:
            return f"{name} payment is due today"
        if days == 1:
            return f"{name} payment is due tomorrow"
        return f"{name} payment is due in {days} days"
    days = item.days_until_statement or 0
    if days == 0:
        return f"{name} statement is ready"
    if days == 1:
        return f"{name} statement arrives tomorrow"
    return f"{name} statement in {days} days"


def push_data(item: CardReminderItem) -> dict[str, str]:
    """FCM data values must be strings. `route` is what the app should open."""
    return {
        "type": item.reminder_type,
        "route": "/wallet",
        "user_card_id": str(item.user_card_id),
        "days_until_due": "" if item.days_until_due is None else str(item.days_until_due),
        "days_until_statement": "" if item.days_until_statement is None else str(item.days_until_statement),
    }
