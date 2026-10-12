from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import Item


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


def create_items_from_api(
    raw_items: list[dict[str, Any]], session: Optional[Session] = None
) -> None:
    def _insert(s: Session):
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
            )
            s.add(item)
        s.commit()

    if session:
        _insert(session)
    else:
        with SessionLocal() as s:
            _insert(s)
