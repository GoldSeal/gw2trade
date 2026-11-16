import logging
from typing import Any, Optional

from db import SessionLocal
from models import Item
from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def get_missing_item_ids(
    item_ids: set[int], session: Optional[Session] = None
) -> set[int]:
    if not item_ids:
        return set()

    if session:
        existing = set(
            session.scalars(select(Item.id).where(Item.id.in_(item_ids))).all()
        )
        return item_ids - existing

    with SessionLocal() as s:
        existing = set(
            s.scalars(select(Item.id).where(Item.id.in_(item_ids))).all()
        )
        return item_ids - existing


def get_items_by_ids(
    item_ids: set[int], session: Optional[Session] = None
) -> dict[int, Item]:
    if not item_ids:
        return {}

    if session:
        items = session.scalars(select(Item).where(Item.id.in_(item_ids))).all()
        return {item.id: item for item in items}

    with SessionLocal() as s:
        items = s.scalars(select(Item).where(Item.id.in_(item_ids))).all()
        return {item.id: item for item in items}


def get_all_item_ids(session: Optional[Session] = None) -> set[int]:
    """Get all item IDs currently stored in the database."""
    stmt = select(Item.id)
    if session:
        return set(session.scalars(stmt).all())
    with SessionLocal() as s:
        return set(s.scalars(stmt).all())


def get_item_by_id(
    item_id: int, session: Optional[Session] = None
) -> Optional[Item]:
    if session:
        return session.get(Item, item_id)
    with SessionLocal() as s:
        return s.get(Item, item_id)


def create_items_from_api(
    raw_items: list[dict[str, Any]], session: Optional[Session] = None
) -> int:
    def _insert(s: Session) -> int:
        count = 0
        for raw in raw_items:
            item = Item(
                id=raw["id"],
                name=raw.get("name", "Unknown Item"),
                icon=raw.get("icon"),
                chat_link=raw.get("chat_link", ""),
                description=raw.get("description"),
                type=raw.get("type", "Unknown"),
                rarity=raw.get("rarity", "Basic"),
                level=raw.get("level", 0),
                vendor_value=raw.get("vendor_value", 0),
                default_skin=raw.get("default_skin"),
                flags=raw.get("flags", []),
                game_types=raw.get("game_types", []),
                restrictions=raw.get("restrictions", []),
                upgrade_into=raw.get("upgrade_into"),
                upgrades_from=raw.get("upgrades_from"),
                details=raw.get("details"),
            )
            s.add(item)
            count += 1
        s.commit()
        return count

    if session:
        inserted = _insert(session)
    else:
        with SessionLocal() as s:
            inserted = _insert(s)
    logger.debug(f"inserted {inserted} items to db")
    return inserted
