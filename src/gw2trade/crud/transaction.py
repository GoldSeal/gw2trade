from collections import defaultdict
from datetime import datetime
from typing import Any, Collection, Optional

from db import SessionLocal
from models import CurrentTransaction, HistoricTransaction
from sqlalchemy import func, select
from sqlalchemy.exc import NoResultFound
from sqlalchemy.orm import Session


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
) -> list[CurrentTransaction]:
    def _replace(s: Session):
        old_listings = (
            s.query(CurrentTransaction)
            .filter(CurrentTransaction.user_id == user_id)
            .all()
        )

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
                created=datetime.fromisoformat(tx["created"]),
                listing_type=tx["listing_type"],
            )
            s.add(record)
        s.commit()

        return old_listings

    if session:
        return _replace(session)
    else:
        with SessionLocal() as s:
            return _replace(s)


def get_newest_transaction(
    user_id: int,
    session: Optional[Session] = None,
) -> HistoricTransaction | None:
    """Get the newest transaction in the database."""
    stmt = (
        select(HistoricTransaction)
        .where(HistoricTransaction.user_id == user_id)
        .order_by(HistoricTransaction.created.desc())
        .limit(1)
    )
    if session:
        return session.execute(stmt).scalar_one()
    else:
        with SessionLocal() as s:
            try:
                return s.execute(stmt).scalar_one()
            except NoResultFound:
                return


def add_historic_transactions(
    user_id: int,
    transactions: list[dict[str, Any]],
    session: Optional[Session] = None,
) -> None:
    def _add(s: Session):
        for tx in transactions:
            record = HistoricTransaction(
                id=tx["id"],
                user_id=user_id,
                item_id=tx["item_id"],
                price=tx["price"],
                quantity=tx["quantity"],
                created=datetime.fromisoformat(tx["created"]),
                listing_type=tx["listing_type"],
                purchased=datetime.fromisoformat(tx["purchased"]),
            )
            s.add(record)
        s.commit()

    if session:
        _add(session)
    else:
        with SessionLocal() as s:
            _add(s)


def get_historic_transactions(
    user_id: int,
    start_date: datetime,
    session: Optional[Session] = None,
) -> list[HistoricTransaction]:
    stmt = select(HistoricTransaction).where(
        HistoricTransaction.user_id == user_id,
        HistoricTransaction.purchased >= start_date,
    )

    if session:
        return list(session.scalars(stmt).all())
    with SessionLocal() as s:
        return list(s.scalars(stmt).all())


def get_sold_totals_since(
    user_id: int,
    start_date: datetime,
    session: Optional[Session] = None,
) -> dict[tuple[int, str], int]:
    """Sum historic sale quantities purchased on or after start_date."""
    transactions = get_historic_transactions(user_id, start_date, session)
    sold_map: dict[tuple[int, str], int] = defaultdict(int)
    for tx in transactions:
        sold_map[(tx.item_id, tx.listing_type)] += tx.quantity
    return dict(sold_map)


def convert2hist_trans(
    collection: Collection, user_id
) -> list[HistoricTransaction]:
    return [
        HistoricTransaction(
            id=tx["id"],
            user_id=user_id,
            item_id=tx["item_id"],
            price=tx["price"],
            quantity=tx["quantity"],
            created=datetime.fromisoformat(tx["created"]),
            listing_type=tx["listing_type"],
            purchased=datetime.fromisoformat(tx["purchased"]),
        )
        for tx in collection
    ]


def convert2curr_trans(
    collection: Collection, user_id
) -> list[CurrentTransaction]:
    return [
        CurrentTransaction(
            id=tx["id"],
            user_id=user_id,
            item_id=tx["item_id"],
            price=tx["price"],
            quantity=tx["quantity"],
            created=datetime.fromisoformat(tx["created"]),
            listing_type=tx["listing_type"],
        )
        for tx in collection
    ]
