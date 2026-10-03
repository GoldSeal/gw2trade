from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )

    current_transactions: Mapped[List["CurrentTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    historic_transactions: Mapped[List["HistoricTransaction"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    wanted_items: Mapped[List["WantedItem"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    recipes: Mapped[List["Recipe"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_link: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    icon: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    rarity: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    vendor_value: Mapped[int] = mapped_column(Integer, nullable=False)
    default_skin: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Complex / nested types stored as JSON in SQLite
    flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    game_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    restrictions: Mapped[List[str]] = mapped_column(JSON, default=list)
    upgrade_into: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True
    )
    upgrades_from: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(
        JSON, nullable=True
    )
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSON, nullable=True
    )


class OpenTransaction(Base):
    """Abstract base table class for active commerce listings."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), primary_key=True
    )
    item_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[str] = mapped_column(String(50), nullable=False)
    listing_type: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # 'buy' or 'sell'


class CurrentTransaction(OpenTransaction):
    __tablename__ = "current_transactions"

    user: Mapped["User"] = relationship(back_populates="current_transactions")


class HistoricTransaction(OpenTransaction):
    __tablename__ = "historic_transactions"

    purchased: Mapped[str] = mapped_column(String(50), nullable=False)

    user: Mapped["User"] = relationship(back_populates="historic_transactions")


class WantedItem(Base):
    __tablename__ = "wanted_items"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_quantity: Mapped[int] = mapped_column(Integer, default=0)
    listing_type: Mapped[str] = mapped_column(String(10), default="buy")
    craft: Mapped[str] = mapped_column(
        String(15), default="Unassigned", server_default="Unassigned"
    )
    note: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, default=""
    )

    user: Mapped["User"] = relationship(back_populates="wanted_items")


class Recipe(Base):
    __tablename__ = "recipes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(30), nullable=False)
    output_item_id: Mapped[int] = mapped_column(Integer, nullable=False)
    output_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    time_to_craft_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    disciplines: Mapped[List[str]] = mapped_column(JSON, default=list)
    min_rating: Mapped[int] = mapped_column(Integer, nullable=False)
    flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    ingredients: Mapped[List[str]] = mapped_column(JSON, default=list)
    guild_ingredients: Mapped[Optional[list]] = mapped_column(
        JSON, nullable=True, default=list
    )
    output_upgrade_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True
    )
    chat_link: Mapped[str] = mapped_column(String(50), nullable=False)

    user: Mapped["User"] = relationship(back_populates="recipes")


class Character(Base):
    __tablename__ = "characters"
    # id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(30), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    race: Mapped[str] = mapped_column(String(10), nullable=False)
    gender: Mapped[str] = mapped_column(String(10), nullable=False)
    flags: Mapped[List[str]] = mapped_column(JSON, default=list)
    profession: Mapped[str] = mapped_column(String(15), nullable=False)
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    guild: Mapped[str] = mapped_column(String(40), nullable=True)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    created: Mapped[str] = mapped_column(String(25), nullable=False)
    deaths: Mapped[int] = mapped_column(Integer, nullable=False)
    crafting: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    backstory: Mapped[List[str]] = mapped_column(JSON, default=list)
    wvw_abilities: Mapped[List] = mapped_column(JSON, default=list)
    equipment: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    recipes: Mapped[List[int]] = mapped_column(JSON, default=list)
    training: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    bags: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    equipment_pvp: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
    specializations: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
    skills: Mapped[Dict[str, Any]] = mapped_column(JSON, default=list)
