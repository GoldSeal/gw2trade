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


# In-memory mapping caches
_cached_items: list[tuple[int, str, str]] | None = None
_name_to_id: dict[str, int] | None = None
_id_to_name: dict[int, str] | None = None


def load_item_cache(
    force: bool = False, session: Optional[Session] = None
) -> None:
    """Load or refresh in-memory item name <-> id mappings from the database."""
    global _cached_items, _name_to_id, _id_to_name
    if _cached_items is not None and not force:
        return

    stmt = select(Item.id, Item.name).order_by(Item.id)
    if session:
        rows = session.execute(stmt).all()
    else:
        with SessionLocal() as s:
            rows = s.execute(stmt).all()

    cached: list[tuple[int, str, str]] = []
    name_to_id: dict[str, int] = {}
    id_to_name: dict[int, str] = {}
    for item_id, name in rows:
        name_clean = name or ""
        cached.append((item_id, name_clean, name_clean.lower()))
        id_to_name[item_id] = name_clean
        name_lower = name_clean.lower()
        if name_lower and name_lower not in name_to_id:
            name_to_id[name_lower] = item_id

    _cached_items = cached
    _name_to_id = name_to_id
    _id_to_name = id_to_name


def get_item_name_to_id_mapping() -> dict[str, int]:
    """Get dictionary mapping lowercase item names to item IDs."""
    if _name_to_id is None:
        load_item_cache()
    return _name_to_id if _name_to_id is not None else {}


def get_item_name(item_id: int) -> str | None:
    """Get item name by ID from the in-memory cache."""
    if _id_to_name is None:
        load_item_cache()
    return _id_to_name.get(item_id) if _id_to_name else None


def get_item_id_by_name(name: str) -> int | None:
    """Get item ID by name (case-insensitive) from the in-memory cache."""
    if _name_to_id is None:
        load_item_cache()
    clean = name.strip().lower()
    return _name_to_id.get(clean) if _name_to_id else None


def search_items_by_name(query: str, limit: int = 40) -> list[tuple[int, str]]:
    """Fast in-memory search matching query words. Returns list of (item_id, name)."""
    if _cached_items is None:
        load_item_cache()

    q = query.strip().lower()
    if not q or not _cached_items:
        return []

    words = q.split()
    results = []
    for item_id, name, name_lower in _cached_items:
        if all(w in name_lower for w in words):
            starts_with = name_lower.startswith(q)
            results.append((starts_with, len(name), item_id, name))

    results.sort(key=lambda x: (not x[0], x[1]))
    return [(item_id, name) for _, _, item_id, name in results[:limit]]


def find_items_by_name(query: str, limit: int = 40) -> list[Item]:
    """Find Item model instances matching query using in-memory search + bulk fetch."""
    matches = search_items_by_name(query, limit=limit)
    if not matches:
        return []
    ids = [item_id for item_id, _ in matches]
    items_dict = get_items_by_ids(set(ids))
    return [items_dict[iid] for iid in ids if iid in items_dict]


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
    if _cached_items is not None and inserted > 0:
        load_item_cache(force=True, session=session)
    logger.debug(f"inserted {inserted} items to db")
    return inserted
