from typing import Any, Optional

from db import SessionLocal
from models import WantedItem
from sqlalchemy import select
from sqlalchemy.orm import Session


def get_wanted_items(
    user_id: int, session: Optional[Session] = None
) -> list[WantedItem]:
    stmt = select(WantedItem).where(WantedItem.user_id == user_id)
    if session:
        return list(session.scalars(stmt).all())
    with SessionLocal() as s:
        return list(s.scalars(stmt).all())


def get_distinct_crafts(
    user_id: int, session: Optional[Session] = None
) -> list[str]:
    stmt = (
        select(WantedItem.craft).where(WantedItem.user_id == user_id).distinct()
    )
    if session:
        return list(session.scalars(stmt).all())
    with SessionLocal() as s:
        return list(s.scalars(stmt).all())


def get_item_craft(
    user_id: int, item_id: int, session: Optional[Session] = None
) -> str:
    stmt = select(WantedItem.craft).where(
        WantedItem.user_id == user_id,
        WantedItem.item_id == item_id,
    )
    if session:
        return session.scalar(stmt) or "Unassigned"
    with SessionLocal() as s:
        return s.scalar(stmt) or "Unassigned"


def upsert_target_item(
    user_id: int,
    item_id: int,
    listing_type: str,
    target_quantity: int,
    craft: str,
    note: str = "",
    note2: str = "",
    sold: int = 0,
    re_listed: int = 0,
    session: Optional[Session] = None,
) -> None:
    def _upsert(s: Session):
        existing = s.scalar(
            select(WantedItem).where(
                WantedItem.user_id == user_id,
                WantedItem.item_id == item_id,
                WantedItem.listing_type == listing_type,
            )
        )
        if existing:
            existing.target_quantity = target_quantity
            existing.craft = craft
            existing.note = note
            existing.note2 = note2
            existing.sold = sold
            existing.re_listed = re_listed
        else:
            s.add(
                WantedItem(
                    user_id=user_id,
                    item_id=item_id,
                    target_quantity=target_quantity,
                    listing_type=listing_type,
                    craft=craft,
                    note=note,
                    note2=note2,
                    sold=sold,
                    re_listed=re_listed,
                )
            )

        # Synchronize craft discipline across all listing types of this item
        other_targets = s.scalars(
            select(WantedItem).where(
                WantedItem.user_id == user_id,
                WantedItem.item_id == item_id,
            )
        ).all()
        for ot in other_targets:
            ot.craft = craft

        s.commit()

    if session:
        _upsert(session)
    else:
        with SessionLocal() as s:
            _upsert(s)


def set_attribute(
    user_id: int,
    item_id: int,
    listing_type: str,
    attribute_name: str,
    value: Any,
    session: Optional[Session] = None,
) -> None:
    """Sets any valid column attribute on a WantedItem, creating it if it doesn't exist.

    If setting 'craft', also synchronizes that craft across all listing types
    for this item.
    """
    if not hasattr(WantedItem, attribute_name):
        raise AttributeError(f"WantedItem has no attribute '{attribute_name}'")

    def _apply(s: Session):
        target = s.scalar(
            select(WantedItem).where(
                WantedItem.user_id == user_id,
                WantedItem.item_id == item_id,
                WantedItem.listing_type == listing_type,
            )
        )
        if target:
            setattr(target, attribute_name, value)
        else:
            # Look up craft if setting an unrelated attribute on a new row
            craft_val = (
                value
                if attribute_name == "craft"
                else get_item_craft(user_id, item_id, session=s)
            )
            target = WantedItem(
                user_id=user_id,
                item_id=item_id,
                target_quantity=0,
                listing_type=listing_type,
                craft=craft_val,
                note="",
                note2="",
            )
            setattr(target, attribute_name, value)
            s.add(target)

        # Synchronize craft discipline across other listings of this item
        if attribute_name == "craft":
            other_targets = s.scalars(
                select(WantedItem).where(
                    WantedItem.user_id == user_id,
                    WantedItem.item_id == item_id,
                )
            ).all()
            for ot in other_targets:
                ot.craft = value

        s.commit()

    if session:
        _apply(session)
    else:
        with SessionLocal() as s:
            _apply(s)


def set_item_craft(
    user_id: int,
    item_id: int,
    listing_type: str,
    craft: str,
    session: Optional[Session] = None,
) -> None:
    set_attribute(user_id, item_id, listing_type, "craft", craft, session)


def set_target_quantity(
    user_id: int,
    item_id: int,
    listing_type: str,
    target_quantity: int,
    session: Optional[Session] = None,
) -> None:
    set_attribute(
        user_id,
        item_id,
        listing_type,
        "target_quantity",
        target_quantity,
        session,
    )


def set_target_note(
    user_id: int,
    item_id: int,
    listing_type: str,
    note: str,
    session: Optional[Session] = None,
) -> None:
    set_attribute(user_id, item_id, listing_type, "note", note, session)


def set_target_note2(
    user_id: int,
    item_id: int,
    listing_type: str,
    note2: str,
    session: Optional[Session] = None,
) -> None:
    set_attribute(user_id, item_id, listing_type, "note2", note2, session)


def update_sold_relisted_counts(
    user_id: int, sold_map: dict[int, int], re_list_map: dict[int, int]
) -> None:
    sold_items = set(sold_map.keys())
    re_listed_items = set(re_list_map.keys())
    all_ids = sold_items.union(re_listed_items)
    with SessionLocal() as s:
        stmt = select(WantedItem).where(
            WantedItem.user_id == user_id,
            WantedItem.item_id.in_(all_ids),
            WantedItem.listing_type == "sell",
        )
        all_items = s.scalars(stmt).all()
        all_items_map = {item.item_id: item for item in all_items}
        for item_id in all_ids:
            existing = all_items_map.get(item_id)
            if existing:
                existing.sold += sold_map.get(item_id, 0)
                existing.re_listed += re_list_map.get(item_id, 0)
            else:
                target = WantedItem(
                    user_id=user_id,
                    item_id=item_id,
                    target_quantity=0,
                    listing_type="sell",
                    craft=get_item_craft(user_id, item_id, session=s),
                    note="",
                    note2="",
                    sold=sold_map.get(item_id, 0),
                    re_listed=re_list_map.get(item_id, 0),
                )
                s.add(target)
        s.commit()


def delete_target_item(
    user_id: int,
    item_id: int,
    listing_type: str,
    session: Optional[Session] = None,
) -> None:
    def _delete(s: Session):
        target = s.scalar(
            select(WantedItem).where(
                WantedItem.user_id == user_id,
                WantedItem.item_id == item_id,
                WantedItem.listing_type == listing_type,
            )
        )
        if target:
            s.delete(target)
            s.commit()

    if session:
        _delete(session)
    else:
        with SessionLocal() as s:
            _delete(s)
