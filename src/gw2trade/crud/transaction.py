import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Collection, Optional

from db import SessionLocal
from models import CurrentTransaction, HistoricTransaction, ReListing
from sqlalchemy import func, select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def parse_datetime_utc(val: Any) -> datetime:
    """Convert string or aware datetime to naive UTC datetime."""
    if isinstance(val, str):
        val = datetime.fromisoformat(val)
    if isinstance(val, datetime):
        if val.tzinfo is not None:
            return val.astimezone(timezone.utc).replace(tzinfo=None)
        return val
    return datetime.min


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
                created=parse_datetime_utc(tx["created"]),
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
        .order_by(
            HistoricTransaction.purchased.desc(),
            HistoricTransaction.id.desc(),
        )
        .limit(1)
    )
    if session:
        return session.execute(stmt).scalar_one_or_none()
    else:
        with SessionLocal() as s:
            return s.execute(stmt).scalar_one_or_none()


def add_historic_transactions(
    user_id: int,
    transactions: list[dict[str, Any]],
    session: Optional[Session] = None,
) -> None:
    def _add(s: Session):
        if not transactions:
            return

        incoming_ids = [tx["id"] for tx in transactions]
        existing_ids: set[int] = set()
        for i in range(0, len(incoming_ids), 500):
            chunk = incoming_ids[i : i + 500]
            ids = s.scalars(
                select(HistoricTransaction.id).where(
                    HistoricTransaction.user_id == user_id,
                    HistoricTransaction.id.in_(chunk),
                )
            ).all()
            existing_ids.update(ids)

        added = False
        for tx in transactions:
            if tx["id"] in existing_ids:
                continue
            purchased_val = parse_datetime_utc(tx["purchased"])
            created_val = parse_datetime_utc(tx["created"])
            record = HistoricTransaction(
                id=tx["id"],
                user_id=user_id,
                item_id=tx["item_id"],
                price=tx["price"],
                quantity=tx["quantity"],
                created=created_val,
                listing_type=tx["listing_type"],
                purchased=purchased_val,
            )
            s.add(record)
            existing_ids.add(tx["id"])
            added = True
        if added:
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
            created=parse_datetime_utc(tx["created"]),
            listing_type=tx["listing_type"],
            purchased=parse_datetime_utc(tx["purchased"]),
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
            created=parse_datetime_utc(tx["created"]),
            listing_type=tx["listing_type"],
        )
        for tx in collection
    ]


def add_re_listings(
    user_id: int,
    transactions: list[Any],
    session: Optional[Session] = None,
) -> None:
    def _add(s: Session):
        for tx in transactions:
            try:
                tx_id = tx.id if hasattr(tx, "id") else tx["id"]
                existing = s.scalar(
                    select(ReListing).where(
                        ReListing.id == tx_id,
                        ReListing.user_id == user_id,
                    )
                )
                if existing:
                    continue

                if isinstance(tx, dict):
                    record = ReListing(
                        id=tx["id"],
                        user_id=user_id,
                        item_id=tx["item_id"],
                        price=tx["price"],
                        quantity=tx["quantity"],
                        created=parse_datetime_utc(tx["created"]),
                        listing_type=tx["listing_type"],
                    )
                else:
                    record = ReListing(
                        id=tx.id,
                        user_id=user_id,
                        item_id=tx.item_id,
                        price=tx.price,
                        quantity=tx.quantity,
                        created=parse_datetime_utc(tx.created),
                        listing_type=tx.listing_type,
                    )
                s.add(record)
            except Exception:
                logger.error("failed to insert relisting", exc_info=True)
        s.commit()

    if session:
        _add(session)
    else:
        with SessionLocal() as s:
            _add(s)


def get_relisted_totals_since(
    user_id: int,
    start_date: Optional[datetime] = None,
    session: Optional[Session] = None,
) -> dict[tuple[int, str], int]:
    """Sum relisted quantities on or after start_date (or all if start_date is None)."""
    stmt = select(ReListing).where(ReListing.user_id == user_id)
    if start_date is not None:
        stmt = stmt.where(ReListing.created >= start_date)

    if session:
        relistings = list(session.scalars(stmt).all())
    else:
        with SessionLocal() as s:
            relistings = list(s.scalars(stmt).all())

    relist_map: dict[tuple[int, str], int] = defaultdict(int)
    for r in relistings:
        relist_map[(r.item_id, r.listing_type)] += r.quantity
    return dict(relist_map)


def get_item_relistings(
    user_id: int,
    item_id: int,
    session: Optional[Session] = None,
) -> list[ReListing]:
    """Get all relistings for a specific item and user ordered by created descending."""
    stmt = (
        select(ReListing)
        .where(ReListing.user_id == user_id, ReListing.item_id == item_id)
        .order_by(ReListing.created.desc())
    )
    if session:
        return list(session.scalars(stmt).all())
    with SessionLocal() as s:
        return list(s.scalars(stmt).all())


def get_item_historic_transactions(
    user_id: int,
    item_id: int,
    session: Optional[Session] = None,
) -> list[HistoricTransaction]:
    """Get all historic transactions for a specific item and user ordered by purchased descending."""
    stmt = (
        select(HistoricTransaction)
        .where(
            HistoricTransaction.user_id == user_id,
            HistoricTransaction.item_id == item_id,
        )
        .order_by(HistoricTransaction.purchased.desc())
    )
    if session:
        return list(session.scalars(stmt).all())
    with SessionLocal() as s:
        return list(s.scalars(stmt).all())
