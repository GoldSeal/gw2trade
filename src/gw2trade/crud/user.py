from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import SessionLocal
from models import User


def get_first_user(session: Optional[Session] = None) -> Optional[User]:
    if session:
        return session.scalars(select(User).order_by(User.id)).first()
    with SessionLocal() as s:
        return s.scalars(select(User).order_by(User.id)).first()


def get_all_users(session: Optional[Session] = None) -> list[User]:
    if session:
        return list(session.scalars(select(User).order_by(User.id)).all())
    with SessionLocal() as s:
        return list(s.scalars(select(User).order_by(User.id)).all())


def get_user_by_id(
    user_id: int, session: Optional[Session] = None
) -> Optional[User]:
    if session:
        return session.get(User, user_id)
    with SessionLocal() as s:
        return s.get(User, user_id)


def create_user(
    name: str, api_key: str, session: Optional[Session] = None
) -> User:
    if session:
        new_user = User(name=name, api_key=api_key)
        session.add(new_user)
        session.commit()
        return new_user

    with SessionLocal() as s:
        new_user = User(name=name, api_key=api_key)
        s.add(new_user)
        s.commit()
        s.refresh(new_user)
        return new_user
