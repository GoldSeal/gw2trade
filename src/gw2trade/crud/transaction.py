from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import CurrentTransaction


def get_in_trade_totals(
    user_id: int, session: Optional[Session] = None
) -> dict[tuple[int, str], int]:
    stmt = (
        select(
            CurrentTransaction.item_id,
            CurrentTransaction.listing_type,
            func.sum(CurrentTransaction.quantity).label("total_in_trade"),
        )
        .where(CurrentTransaction.user_id == user_id)
        .group_by(
            CurrentTransaction.item_id,
            CurrentTransaction.listing_type,
        )
    )

    if session:
        rows = session.execute(stmt).all()
    else:
        with SessionLocal() as s:
            rows = s.execute(stmt).all()

    return {
        (row.item_id, row.listing_type): int(row.total_in_trade) for row in rows
    }


def replace_current_transactions(
    user_id: int,
    transactions: list[dict[str, Any]],
    session: Optional[Session] = None,
) -> None:
    def _replace(s: Session):
        s.query(CurrentTransaction).filter(
            CurrentTransaction.user_id == user_id
        ).delete()

        for tx in transactions:
            record = CurrentTransaction(
                id=tx["id"],
                user_id=user_id,
                item_id=tx["item_id"],
                price=tx["price"],
                quantity=tx["quantity"],
                created=tx["created"],
                listing_type=tx["listing_type"],
            )
            s.add(record)
        s.commit()

    if session:
        _replace(session)
    else:
        with SessionLocal() as s:
            _replace(s)
