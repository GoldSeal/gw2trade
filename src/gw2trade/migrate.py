import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

# Import your Base metadata and models
from models import Base
from sqlalchemy import JSON, DateTime, create_engine, text


def parse_datetime(val: Any) -> Any:
    """Parse string representations of datetimes into datetime objects."""
    if not isinstance(val, str) or not val.strip():
        return val

    # Normalize ISO format ending in 'Z'
    clean_val = val.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(clean_val)
    except ValueError:
        pass

    # Common fallback datetime formats
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue

    return val


def parse_json(val: Any) -> Any:
    """Decode raw JSON strings from SQLite so SQLAlchemy can re-encode them."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return val
    return val


def migrate(old_db_path: str, new_db_path: str, force: bool = False):
    if not os.path.exists(old_db_path):
        print(
            f"Error: Old database not found at '{old_db_path}'", file=sys.stderr
        )
        sys.exit(1)

    # if os.path.exists(new_db_path):
    #    if not force:
    #        print(
    #            f"Error: Destination database '{new_db_path}' already exists. "
    #            f"Use --force to overwrite it.",
    #            file=sys.stderr,
    #        )
    #        sys.exit(1)
    #    os.remove(new_db_path)

    # Ensure target directory exists if a path with subfolders was given
    new_dir = os.path.dirname(new_db_path)
    if new_dir:
        os.makedirs(new_dir, exist_ok=True)

    old_engine = create_engine(f"sqlite:///{old_db_path}")
    new_engine = create_engine(f"sqlite:///{new_db_path}")

    # print("Creating new database schema...")
    # Base.metadata.create_all(new_engine)

    with (
        old_engine.connect() as old_conn,
        new_engine.begin() as new_conn,
    ):
        # sorted_tables ensures foreign keys are respected during insertion
        for table in Base.metadata.sorted_tables:
            print(f"Migrating table: {table.name}...")

            check_table = old_conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name=:name"
                ),
                {"name": table.name},
            ).scalar()

            if not check_table:
                print(f"  Skipping {table.name} (not found in source database)")
                continue

            datetime_cols = {
                c.name for c in table.columns if isinstance(c.type, DateTime)
            }
            json_cols = {
                c.name for c in table.columns if isinstance(c.type, JSON)
            }

            rows = (
                old_conn.execute(text(f"SELECT * FROM {table.name}"))
                .mappings()
                .all()
            )

            if not rows:
                print(f"  {table.name} is empty.")
                continue

            transformed_rows = []
            for row in rows:
                row_dict: Dict[str, Any] = dict(row)

                # Convert string timestamps to datetime objects
                for col in datetime_cols:
                    if col in row_dict and row_dict[col] is not None:
                        row_dict[col] = parse_datetime(row_dict[col])

                # Parse JSON strings so SQLAlchemy doesn't double-serialize
                for col in json_cols:
                    if col in row_dict and row_dict[col] is not None:
                        row_dict[col] = parse_json(row_dict[col])

                transformed_rows.append(row_dict)

            new_conn.execute(table.insert(), transformed_rows)
            print(f"  Migrated {len(transformed_rows)} rows.")

    print(f"\nMigration completed successfully! Target: {new_db_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Migrate data from an old SQLite database to a new schema."
    )
    parser.add_argument(
        "old_db",
        metavar="OLD_DB",
        type=str,
        help="Path to the source SQLite database file",
    )
    parser.add_argument(
        "new_db",
        metavar="NEW_DB",
        type=str,
        help="Path to the target SQLite database file to be created",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="Overwrite the target database file if it already exists",
    )

    args = parser.parse_args()
    migrate(args.old_db, args.new_db, force=args.force)


if __name__ == "__main__":
    main()
