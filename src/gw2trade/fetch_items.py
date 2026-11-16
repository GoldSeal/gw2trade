"""Script to fetch all items from GW2 API and populate the local database."""

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Sequence

# Ensure src/gw2trade is on sys.path regardless of execution working directory
_SRC_DIR = Path(__file__).resolve().parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import requests
import api
import crud
from db import run_migrations

GW2_ITEMS_URL = f"{api.GW2_BASE_URL}/items"
MAX_BATCH_SIZE = 200
DEFAULT_DELAY = 0.25  # seconds between batch requests (~4 req/s, well below the 10 req/s limit)
MAX_RETRIES = 5

logger = logging.getLogger("fetch_items")


def format_duration(seconds: float) -> str:
    """Format seconds into readable string (e.g. '1m 24s')."""
    sec = int(round(seconds))
    if sec < 60:
        return f"{sec}s"
    minutes = sec // 60
    rem_sec = sec % 60
    if minutes < 60:
        return f"{minutes}m {rem_sec:02d}s"
    hours = minutes // 60
    rem_min = minutes % 60
    return f"{hours}h {rem_min:02d}m {rem_sec:02d}s"


def fetch_batch_with_retry(
    ids: Sequence[int],
    max_retries: int = MAX_RETRIES,
    timeout: float = 15.0,
) -> list[dict]:
    """Fetch item details for a list of IDs with rate limit backoff and transient retries."""
    if not ids:
        return []

    id_str = ",".join(str(i) for i in ids)
    backoff = 2.0

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(
                GW2_ITEMS_URL,
                params={"ids": id_str},
                timeout=timeout,
            )

            # Rate limit exceeded
            if resp.status_code == 429:
                retry_after_hdr = resp.headers.get("Retry-After")
                retry_after = (
                    float(retry_after_hdr) if retry_after_hdr else backoff
                )
                logger.warning(
                    f"Rate limited (HTTP 429). Waiting {retry_after:.1f}s before retry (attempt {attempt}/{max_retries})..."
                )
                time.sleep(retry_after)
                backoff *= 2
                continue

            # 404 means none of the IDs in this batch exist / are accessible
            if resp.status_code == 404:
                logger.debug(
                    f"Batch of {len(ids)} item IDs returned 404 (none valid)."
                )
                return []

            resp.raise_for_status()

            # HTTP 200 or 206 (Partial Content)
            return resp.json()

        except requests.RequestException as exc:
            if attempt == max_retries:
                logger.error(
                    f"Failed to fetch batch after {max_retries} attempts: {exc}"
                )
                raise
            logger.warning(
                f"Request error: {exc}. Retrying in {backoff:.1f}s (attempt {attempt}/{max_retries})..."
            )
            time.sleep(backoff)
            backoff *= 2

    return []


def fetch_all_items(
    batch_size: int = MAX_BATCH_SIZE,
    delay: float = DEFAULT_DELAY,
    limit: int | None = None,
) -> int:
    """Fetch all missing items from the GW2 API and save them into the database.

    Args:
        batch_size: Number of item IDs per API request (max 200).
        delay: Enforced delay in seconds between requests for rate limiting.
        limit: Optional maximum number of missing items to fetch.

    Returns:
        Number of items successfully fetched and stored.
    """
    batch_size = min(max(1, batch_size), MAX_BATCH_SIZE)

    # 1. Ensure DB schema is up to date
    run_migrations()

    # 2. Query all existing item IDs from the local database
    print("Checking items in local database...")
    db_ids = crud.item.get_all_item_ids()
    print(f"Found {len(db_ids)} item(s) already in the database.")

    # 3. Request all available IDs from the GW2 API
    print("Requesting all available item IDs from GW2 API (/v2/items)...")
    api_ids = api.fetch_all_item_ids()
    print(f"GW2 API returned {len(api_ids)} total available item ID(s).")

    # 4. Determine missing item IDs
    missing_ids = sorted(list(set(api_ids) - db_ids))
    if limit is not None and limit > 0:
        missing_ids = missing_ids[:limit]

    total_missing = len(missing_ids)
    if total_missing == 0:
        print("All items are already in the database! Nothing to fetch.")
        return 0

    total_batches = (total_missing + batch_size - 1) // batch_size
    print(
        f"Missing {total_missing} item(s) to fetch in {total_batches} batch(es) "
        f"(batch_size={batch_size}, rate limit delay={delay}s)..."
    )

    # 5. Fetch batches with rate limiting and incremental DB commits
    total_saved = 0
    start_time = time.time()

    for batch_idx in range(total_batches):
        chunk_start = batch_idx * batch_size
        chunk = missing_ids[chunk_start : chunk_start + batch_size]

        batch_t0 = time.time()
        raw_items = fetch_batch_with_retry(chunk)
        if raw_items:
            saved_count = crud.item.create_items_from_api(raw_items)
            total_saved += saved_count

        elapsed = time.time() - start_time
        processed = min(chunk_start + len(chunk), total_missing)
        pct = (processed / total_missing) * 100
        speed = processed / elapsed if elapsed > 0 else 0
        eta_seconds = (total_missing - processed) / speed if speed > 0 else 0

        status_line = (
            f"[{batch_idx + 1}/{total_batches}] "
            f"Fetched: {len(raw_items)} | "
            f"Total: {processed}/{total_missing} ({pct:.1f}%) | "
            f"Speed: {speed:.1f} items/s | "
            f"ETA: {format_duration(eta_seconds)}"
        )
        if batch_idx + 1 < total_batches:
            print(f"\r{status_line}", end="", flush=True)
        else:
            print(f"\r{status_line}", flush=True)

        # Enforce rate limit delay between requests
        batch_duration = time.time() - batch_t0
        if batch_duration < delay and (batch_idx + 1) < total_batches:
            time.sleep(delay - batch_duration)

    total_elapsed = time.time() - start_time
    print(
        f"\nFinished! Successfully fetched and saved {total_saved} item(s) in "
        f"{format_duration(total_elapsed)}."
    )
    return total_saved


def main():
    parser = argparse.ArgumentParser(
        description="Fetch all items from Guild Wars 2 API and populate the database."
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Rate limit delay in seconds between batch requests (default: {DEFAULT_DELAY}s).",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=MAX_BATCH_SIZE,
        help=f"Number of item IDs per API request (max: {MAX_BATCH_SIZE}, default: {MAX_BATCH_SIZE}).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional maximum number of missing items to fetch (useful for partial sync/testing).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging.",
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        fetch_all_items(
            batch_size=args.batch_size,
            delay=args.delay,
            limit=args.limit,
        )
    except KeyboardInterrupt:
        print(
            "\nOperation cancelled by user. Progress up to last batch was saved."
        )
        sys.exit(130)


if __name__ == "__main__":
    main()
