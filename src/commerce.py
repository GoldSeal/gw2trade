import logging
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import Session, create_engine, select, sessionmaker

from .models import Base, CurrentTransaction, HistoricTransaction, Item, User

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GW2_BASE_URL = "https://api.guildwars2.com/v2"


# ============================================================================
# GW2 API Client Functions
# ============================================================================


def get_user_transactions(api_key: str) -> Dict[str, List[Dict[str, Any]]]:
    """Fetches all current and historic buy/sell transactions for a user."""
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoints = {
        "current_buys": f"{GW2_BASE_URL}/commerce/transactions/current/buys",
        "current_sells": f"{GW2_BASE_URL}/commerce/transactions/current/sells",
        "history_buys": f"{GW2_BASE_URL}/commerce/transactions/history/buys",
        "history_sells": f"{GW2_BASE_URL}/commerce/transactions/history/sells",
    }

    results: Dict[str, List[Dict[str, Any]]] = {}

    for key, url in endpoints.items():
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            results[key] = response.json()
        except requests.RequestException as exc:
            logger.error("Failed to fetch %s: %s", key, exc)
            results[key] = []

    return results


def get_item_data(item_id: int) -> Optional[Dict[str, Any]]:
    """Fetches item information by ID from the GW2 API."""
    url = f"{GW2_BASE_URL}/items/{item_id}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        logger.error("Failed to fetch item ID %s: %s", item_id, exc)
        return None


# ============================================================================
# Synchronization Logic
# ============================================================================
def add_user(session: Session, name: str, api_key: str) -> None:
    users = session.scalars(select(User)).all()
    for user in users:
        if user.name == name:
            raise ValueError(f"user with name {name} already exists")
    session.add(User(id=len(users) + 1, name=name, api_key=api_key))
    session.commit()


def update_commerce(session: Session) -> None:
    """Synchronizes commerce transactions and items for all registered users."""
    users = session.scalars(select(User)).all()
    referenced_item_ids: set[int] = set()

    for user in users:
        logger.info("Processing commerce transactions for user: %s", user.name)
        tx_data = get_user_transactions(user.api_key)

        # 1. Replace CurrentTransactions for this user
        existing_current = session.scalars(
            select(CurrentTransaction).where(
                CurrentTransaction.user_id == user.id
            )
        ).all()
        for record in existing_current:
            session.delete(record)

        for record in tx_data.get("current_buys", []):
            session.add(
                CurrentTransaction(
                    id=record["id"],
                    user_id=user.id,
                    item_id=record["item_id"],
                    price=record["price"],
                    quantity=record["quantity"],
                    created=record["created"],
                    listing_type="buy",
                )
            )
            referenced_item_ids.add(record["item_id"])

        for record in tx_data.get("current_sells", []):
            session.add(
                CurrentTransaction(
                    id=record["id"],
                    user_id=user.id,
                    item_id=record["item_id"],
                    price=record["price"],
                    quantity=record["quantity"],
                    created=record["created"],
                    listing_type="sell",
                )
            )
            referenced_item_ids.add(record["item_id"])

        # 2. Add HistoricTransactions not already stored for this user
        existing_history_ids = set(
            session.scalars(
                select(HistoricTransaction.id).where(
                    HistoricTransaction.user_id == user.id
                )
            ).all()
        )

        all_history = [
            (tx, "buy") for tx in tx_data.get("history_buys", [])
        ] + [(tx, "sell") for tx in tx_data.get("history_sells", [])]

        for record, listing_type in all_history:
            referenced_item_ids.add(record["item_id"])
            if record["id"] not in existing_history_ids:
                session.add(
                    HistoricTransaction(
                        id=record["id"],
                        user_id=user.id,
                        item_id=record["item_id"],
                        price=record["price"],
                        quantity=record["quantity"],
                        created=record["created"],
                        purchased=record["purchased"],
                        listing_type=listing_type,
                    )
                )
                existing_history_ids.add(record["id"])

        session.flush()

    # 3. Fetch missing Item records
    if referenced_item_ids:
        existing_item_ids = set(
            session.scalars(
                select(Item.id).where(Item.id.in_(referenced_item_ids))
            ).all()
        )
        missing_item_ids = referenced_item_ids - existing_item_ids

        logger.info("Found %d missing items to fetch.", len(missing_item_ids))
        for item_id in missing_item_ids:
            item_raw = get_item_data(item_id)
            if not item_raw:
                continue

            item = Item(
                id=item_raw["id"],
                chat_link=item_raw.get("chat_link", ""),
                name=item_raw.get("name", ""),
                icon=item_raw.get("icon"),
                description=item_raw.get("description"),
                type=item_raw.get("type", ""),
                rarity=item_raw.get("rarity", ""),
                level=item_raw.get("level", 0),
                vendor_value=item_raw.get("vendor_value", 0),
                default_skin=item_raw.get("default_skin"),
                flags=item_raw.get("flags", []),
                game_types=item_raw.get("game_types", []),
                restrictions=item_raw.get("restrictions", []),
                upgrade_into=item_raw.get("upgrade_into"),
                upgrades_from=item_raw.get("upgrades_from"),
                details=item_raw.get("details"),
            )
            session.add(item)

    session.commit()
    logger.info("Commerce update completed successfully.")


if __name__ == "__main__":
    engine = create_engine("sqlite:///gw2_commerce.db", echo=False)
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as session:
        # Run the update
        update_commerce(session)
