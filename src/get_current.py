#!/usr/bin/env python
import argparse
import csv
import sys
from typing import Any, Dict, List

import requests

BASE_URL = "https://api.guildwars2.com/v2/commerce/transactions/current"


def fetch_transactions(api_key: str, tx_type: str) -> list[dict]:
    headers = {"Authorization": f"Bearer {api_key}"}
    response = fetch_all_from_endpoint(f"{BASE_URL}/{tx_type}", headers=headers)
    return response


def fetch_all_from_endpoint(
    url: str, headers: Dict[str, str], page_size: int = 200
) -> List[Dict[str, Any]]:
    """Fetches all items from a paginated GW2 API endpoint.

    Uses `X-Page-Total` to determine the total number of pages (0-indexed).
    """
    all_records: List[Dict[str, Any]] = []
    page = 0
    total_pages = 1  # Updated dynamically after the first response

    while page < total_pages:
        params = {"page": page, "page_size": page_size}
        try:
            response = requests.get(
                url, headers=headers, params=params, timeout=10
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list):
                all_records.extend(data)

            # Read total pages from response headers
            header_pages = response.headers.get("X-Page-Total")
            if header_pages:
                total_pages = int(header_pages)

            page += 1

        except requests.RequestException as exc:
            print("Failed fetching page %d from %s: %s", page, url, exc)
            break

    return all_records


def main():
    parser = argparse.ArgumentParser(
        description="Export GW2 current transactions to CSV."
    )
    parser.add_argument("api_key", help="Guild Wars 2 API Key")
    parser.add_argument(
        "-o",
        "--output",
        default="current_transactions.csv",
        help="Output CSV file path (default: current_transactions.csv)",
    )
    args = parser.parse_args()

    rows = []
    for tx_type in ("buys", "sells"):
        try:
            records = fetch_transactions(args.api_key, tx_type)
            for item in records:
                item["type"] = tx_type.rstrip("s")  # "buy" or "sell"
                rows.append(item)
        except requests.HTTPError as exc:
            print(f"Error fetching {tx_type}: {exc}", file=sys.stderr)
            sys.exit(1)

    fieldnames = ["id", "type", "item_id", "price", "quantity", "created"]

    with open(args.output, mode="w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file, fieldnames=fieldnames, extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} transactions to '{args.output}'.")


if __name__ == "__main__":
    main()
