import requests

GW2_BASE_URL = "https://api.guildwars2.com/v2"


def fetch_user_transactions(api_key: str) -> list:
    headers = {"Authorization": f"Bearer {api_key}"}
    endpoints = {
        "buy": f"{GW2_BASE_URL}/commerce/transactions/current/buys",
        "sell": f"{GW2_BASE_URL}/commerce/transactions/current/sells",
    }

    fetched_transactions = []
    for l_type, base_url in endpoints.items():
        res = fetch_from_endpoint(base_url, headers)
        for item in res:
            item["listing_type"] = l_type
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


def fetch_from_endpoint(url: str, headers: dict) -> list:
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
            result.append(item)
        page += 1
    return result


def fetch_with_ids(
    url: str, headers: dict, ids: list, extra: dict = {}
) -> list:
    batch_size = 200
    result = []
    for i in range(0, len(ids), batch_size):
        batch = ids[i : i + batch_size]
        params = {"ids": batch}
        params.update(extra)
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        for item in resp.json():
            result.append(item)
    return result
