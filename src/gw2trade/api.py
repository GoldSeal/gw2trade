import logging

import requests

GW2_BASE_URL = "https://api.guildwars2.com/v2"


logger = logging.getLogger(__name__)


def fetch_user_sell_listing(api_key: str) -> list:
    endpoint = f"{GW2_BASE_URL}/commerce/transactions/current/sells"
    return fetch_transactions_from_endpoint(api_key, endpoint, "sell")


def fetch_user_historic_transactions(
    api_key: str, newest_transaction_db: dict
) -> list:
    """Fetch the user's historic sell transactions from the API.
    Args:
        api_key: The API key for the user.
        newest_transaction_db: The newest transaction in the database

    Returns:
        A list of historic sell transactions.
    """
    endpoint = f"{GW2_BASE_URL}/commerce/transactions/history/sells"
    return fetch_transactions_from_endpoint(
        api_key, endpoint, "sell", newest_transaction_db
    )


def fetch_transactions_from_endpoint(
    api_key: str, endpoint: str, listing_type: str, fence_transaction: dict = {}
) -> list:
    headers = {"Authorization": f"Bearer {api_key}"}

    fetched_transactions = []
    res = fetch_from_endpoint(endpoint, headers, fence_transaction)
    for item in res:
        item["listing_type"] = listing_type
    fetched_transactions.extend(res)
    return fetched_transactions


def fetch_user_recipes(api_key: str) -> list:
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoint_1 = f"{GW2_BASE_URL}/account/recipes"
    recipe_ids = fetch_from_endpoint(endpoint_1, headers)
    endpoint_2 = f"{GW2_BASE_URL}/recipes"
    recipes = fetch_with_ids(
        endpoint_2, {}, recipe_ids, {"v": "2022-03-09T02:00:00.000Z"}
    )
    return recipes


def fetch_user_characters(api_key: str) -> list:
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoint = f"{GW2_BASE_URL}/characters?ids=all"
    return fetch_from_endpoint(endpoint, headers)


def fetch_from_endpoint(url: str, headers: dict, fence_item: dict = {}) -> list:
    result = []
    page = 0
    total_pages = 1
    while page < total_pages:
        resp = requests.get(
            url,
            headers=headers,
            params={"page": page, "page_size": 200},
            timeout=10,
        )
        resp.raise_for_status()
        total_pages = int(resp.headers.get("X-Page-Total", 1))

        for item in resp.json():
            if fence_item and item == fence_item:
                return result
            result.append(item)
        page += 1
    return result


def fetch_items_by_ids(ids: list) -> list:
    if not ids:
        return []
    try:
        return fetch_with_ids(
            f"{GW2_BASE_URL}/items", headers={}, ids=ids, timeout=10
        )
    except requests.RequestException:
        logger.error("failed to fetch items", exc_info=True)
        return []


def fetch_with_ids(
    url: str,
    headers: dict,
    ids: list,
    extra: dict | None = None,
    timeout: float | None = None,
) -> list:
    batch_size = 200
    result = []
    extra = extra or {}
    logger.debug(f"about to fetch {len(ids)} objects from {url}")
    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        params = {"ids": ",".join(str(item_id) for item_id in batch)}
        params.update(extra)
        resp = requests.get(
            url, headers=headers, params=params, timeout=timeout
        )
        resp.raise_for_status()
        for item in resp.json():
            result.append(item)
        logger.debug(f"got {len(result)} objects")
    return result
