from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from alembic import command
from alembic.config import Config

DB_PATH = Path("gw2_trade.db").resolve()
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def run_migrations():
    """Runs pending Alembic migrations programmatically up to 'head'."""
    alembic_ini_path = Path(__file__).parent / "alembic.ini"
    alembic_cfg = Config(str(alembic_ini_path))
    # Override URL with the absolute DB path
    alembic_cfg.set_main_option("sqlalchemy.url", DATABASE_URL)
    command.upgrade(alembic_cfg, "head")
